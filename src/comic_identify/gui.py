"""Interfaz GTK4; coordina la selección de portada y presenta los candidatos."""
import sys
from pathlib import Path
from threading import Event, Thread

from . import __version__
from .assistant import PROMPT, build_argv, build_prompt, prepare_workspace, shell_argv
from .collection import build_series, ranges
from .comicinfo import CATEGORIES, MetadataError, build_xml, read_info
from .comicvine import ComicVineClient, ComicVineError
from .covers import (
    COMIC_EXTENSIONS,
    IMAGE_EXTENSIONS,
    cover_to_png,
    extract_cover,
    list_pages,
    read_page,
    thumbnail_bytes,
)
from .gcd import GcdIndex, build_index
from .gcstar import (
    VOCABULARY_FIELDS,
    GCstarError,
    format_name,
    series_text,
    vocabulary,
)
from .gcstar import transfer as gcstar_transfer
from .gcstar import undo_last as undo_gcstar
from .icons import ensure_icons, icon_file
from .identify import Candidate, identify, search_gcd
from .library import Library
from .metadata import differs, write_batch
from .metadata import undo_last as undo_metadata
from .metaform import (
    common_value,
    describe_info,
    file_changes,
    initial_category,
    initial_form,
    merge_values,
    series_changes,
    suggest_fields,
)
from .naming import (
    FLAGS,
    MAX_NAME_BYTES,
    VARIABLES,
    Values,
    check_pattern,
    detect_number,
    missing_content_years,
    natural_key,
    number_width,
    pad_number,
    parse_name,
    render,
    series_values,
    suggest_values,
)
from .originals import content_years, find_volumes
from .renamer import rename_file, rename_series, undo_last
from .settings import GCD_DB, GCSTAR_LOG, LIBRARY_DB, METADATA_LOG, RENAME_LOG, Settings
from .sources import SOURCES, search_url

COMICVINE_API_URL = "https://comicvine.gamespot.com/api/"
GCD_DOWNLOAD_URL = "https://www.comics.org/download/"
GCD_SITE = "https://www.comics.org/"
COMICVINE_HOST, GCD_HOST = "comicvine.gamespot.com", "www.comics.org"
FALLBACK_ICON = "applications-internet-symbolic"
SERIES_FILTERS = ["Incompletas", "Todas", "Sin todos sus metadatos", "Sin total indicado"]
SERIES_SHOWN = 300
PAGE_MAX_SIDE = 1600   # las páginas se reducen a esto para mostrarlas: un escaneo enorme no bloquea la ventana
PAGES_CACHED = 8
TERMINAL_FONT = "Ubuntu Sans Mono, Monospace"   # tipografía del terminal del asistente (Regular); la 2.ª es el respaldo
TERMINAL_FONT_SIZE = 11
VIEWER_MAX_SIDE = 3200   # lado máximo de la página en la ventana grande (letra pequeña legible sin agotar la memoria)
AUTHOR = "Jose Antonio Seguido Doblado"
REPO_URL = "https://github.com/seguidodoblado/comic-identify"
LICENSE_TEXT = ("Este programa es software libre: se distribuye bajo la GNU General Public License, versión 3. "
                "El texto completo está en el archivo LICENSE del repositorio y en https://www.gnu.org/licenses/gpl-3.0.html.")
INDEX_ICON = ("view-refresh-symbolic", "emblem-synchronizing-symbolic")
STOP_ICON = ("process-stop-symbolic", "window-close-symbolic")
DEFAULT_PATTERN = Settings.pattern
WINDOW_HEIGHT = 820
COVER_WIDTH = 440
META_MAX_HEIGHT = 260   # alto máximo del panel del ComicInfo.xml; si hay más campos, se desplaza
WINDOW_WIDTH = 1500   # ancho por defecto: los siete botones de arriba caben en una línea
PREVIEW_WIDTH = 520
ASSISTANT_WIDTH = 760   # el terminal necesita ~80 columnas
LIVE_DELAY_MS = 300   # pausa al teclear antes de buscar en GCD
INITIAL_STATUS = "Escribe un título para buscar, o abre, pega o arrastra un cómic (CBR/CBZ/CB7) o una imagen de portada."


def run_gui(initial_image: Path | None = None) -> None:
    try:
        import gi
        gi.require_version("Gdk", "4.0")
        gi.require_version("Gtk", "4.0")
        from gi.repository import Gdk, Gio, GLib, Gtk, Pango
    except (ImportError, ValueError) as error:
        raise RuntimeError("GTK 4/PyGObject no está instalado.") from error

    # Con "python3 -m" argv[0] es la ruta de __main__.py y GTK derivaría de ahí el WM_CLASS;
    # se fija para que coincida con StartupWMClass del .desktop y el panel muestre el icono.
    GLib.set_prgname("comic-identify")

    def webkit_available() -> bool:
        """WebKitGTK 6.0 instalado (se comprueba sin cargarlo; solo se importa al abrir una ficha)."""
        return "6.0" in gi.Repository.get_default().enumerate_versions("WebKit")

    def vte_available() -> bool:
        """Terminal embebible para GTK4 (gir1.2-vte-3.91), comprobado sin cargarlo."""
        return "3.91" in gi.Repository.get_default().enumerate_versions("Vte")

    def pick_icon(*names: str) -> str:
        """El primer icono simbólico de la lista que exista en el tema del usuario ('' si ninguno)."""
        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        return next((name for name in names if theme.has_icon(name)), "")

    def icon_button(icons: tuple[str, ...], text: str, **properties):
        """Botón con un icono del tema y su texto; `set_icon_button` cambia ambos en caliente."""
        image = Gtk.Image(icon_name=pick_icon(*icons))
        label = Gtk.Label(label=text)
        content = Gtk.Box(spacing=6)
        content.append(image)
        content.append(label)
        button = Gtk.Button(child=content, **properties)
        button.icon_widget, button.label_widget = image, label
        return button

    def set_icon_button(button, icons: tuple[str, ...], text: str):
        button.icon_widget.set_from_icon_name(pick_icon(*icons))
        button.label_widget.set_text(text)

    def later(function, *args):
        """Ejecuta `function` en el hilo de la interfaz una sola vez."""
        def call():
            function(*args)
            return GLib.SOURCE_REMOVE
        GLib.idle_add(call)

    class Window(Gtk.ApplicationWindow):
        def __init__(self, app):
            super().__init__(application=app, title="Comic Identify")
            self.set_default_size(WINDOW_WIDTH, WINDOW_HEIGHT)
            self.settings = Settings.load()
            self.image: Path | None = None
            self.busy = False
            self.cancel = Event()
            self.indexing = False
            self.candidates: list[Candidate] = []
            self.library_matches: list[Candidate] = []   # dependen de la imagen, no del título
            self._quiet = False       # true mientras se escriben los campos por código
            self._live_timer = 0
            self.webview = None   # se crea al abrir la primera ficha: WebKit consume memoria
            self._big_covers: dict[str, bytes] = {}   # portadas grandes de ComicVine ya descargadas
            self._native_url = ""
            self.icon_widgets: dict[str, list] = {}   # host -> imágenes que muestran su icono
            self.cache_dir = Path(GLib.get_user_cache_dir()) / "comic-identify"
            self.icon_dir = self.cache_dir / "icons"
            self.source_file: Path | None = None   # CBR/CBZ abierto: el que se puede normalizar
            self.selected: Candidate | None = None
            self._generation = 0   # sube al limpiar: descarta los resultados de una búsqueda ya en marcha
            self.assistant_box = None   # página del panel con el terminal, mientras hay sesión
            self.assistant_terminal = None
            self._panel_width = PREVIEW_WIDTH
            notebook = self.notebook = Gtk.Notebook()
            notebook.append_page(self._identify_page(), Gtk.Label(label="Identificar"))
            notebook.append_page(self._library_page(), Gtk.Label(label="Mi colección"))
            notebook.append_page(self._settings_page(), Gtk.Label(label="Ajustes"))
            self.set_child(notebook)
            self._refresh_library()
            Thread(target=self._load_icons, daemon=True).start()
            paste = Gtk.Shortcut(trigger=Gtk.ShortcutTrigger.parse_string("<Control>v"),
                                 action=Gtk.CallbackAction.new(lambda *_: self._paste() or True))
            controller = Gtk.ShortcutController()
            controller.add_shortcut(paste)
            self.add_controller(controller)

        @staticmethod
        def _box(orientation=Gtk.Orientation.VERTICAL, spacing=10):
            return Gtk.Box(orientation=orientation, spacing=spacing, margin_top=12, margin_bottom=12,
                           margin_start=12, margin_end=12)

        # ---- Iconos de las webs ------------------------------------------------------------
        def _icon(self, host: str, size: int):
            image = Gtk.Image(icon_name=FALLBACK_ICON, pixel_size=size)   # reserva si la web no da su icono
            self.icon_widgets.setdefault(host, []).append(image)
            if (cached := icon_file(host, self.icon_dir)) is not None:
                image.set_from_file(str(cached))
            return image

        def _icon_ready(self, host: str, path: Path):
            for image in self.icon_widgets.get(host, []):
                image.set_from_file(str(path))

        def _load_icons(self):
            """Descarga (una sola vez, luego caché) los iconos de las webs; en segundo plano."""
            wanted = [(source.host, False) for source in SOURCES] + [(COMICVINE_HOST, True), (GCD_HOST, True)]
            ensure_icons(wanted, self.icon_dir, lambda host, path: later(self._icon_ready, host, path))

        # ---- Identificar -------------------------------------------------------------------
        def _identify_page(self):
            page = self._box()
            controls = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=7, column_spacing=8,
                                   row_spacing=6, homogeneous=False)   # los botones pasan a otra línea si no caben
            open_button = icon_button(("document-open-symbolic", "folder-open-symbolic"), "Abrir…", tooltip_text=(
                "Abre un cómic (CBR, CBZ, CB7) o una imagen de portada; también puedes pegarla o arrastrarla"))
            paste_button = icon_button(("edit-paste-symbolic",), "Pegar", tooltip_text=(
                "Pega una imagen copiada, o un cómic (CBR, CBZ, CB7) o imagen copiados en el gestor de archivos (Ctrl+V)"))
            open_button.connect("clicked", self._choose_image)
            paste_button.connect("clicked", lambda _: self._paste())
            self.ask_button = icon_button(("utilities-terminal-symbolic", "dialog-question-symbolic"),
                                          "Preguntar a la IA", sensitive=False, tooltip_text=(
                "Abre un terminal con tu propia sesión (Claude Code, OpenCode…) para que identifique la portada"))
            self.ask_button.connect("clicked", self._ask_ai)
            self.normalize_button = icon_button(("document-edit-symbolic",), "Normalizar nombre…", sensitive=False,
                                                tooltip_text=(
                "Renombra el CBR/CBZ con el patrón de Estructura.md (abre un cómic o elige una coincidencia de "
                "«Mi colección» para activarlo). Actúa sobre el archivo original, no sobre una copia."))
            self.normalize_button.connect("clicked", self._normalize)
            folder_button = icon_button(("folder-symbolic", "folder-open-symbolic"), "Normalizar carpeta…",
                                        tooltip_text=("Renombra una carpeta-serie y numera los archivos de dentro "
                                                      "(elige antes una serie de GCD para rellenar sus datos)"))
            folder_button.connect("clicked", self._choose_series_folder)
            meta_folder = icon_button(("document-properties-symbolic", "document-edit-symbolic"), "Metadatos carpeta…",
                                      tooltip_text="Escribe el ComicInfo.xml (serie, editorial, categoría…) en todos los "
                                                   "cómics de una carpeta")
            meta_folder.connect("clicked", self._choose_metadata_folder)
            self.metadata_button = icon_button(("document-properties-symbolic", "document-edit-symbolic"),
                                               "Metadatos archivo…", sensitive=False, tooltip_text=(
                "Escribe el ComicInfo.xml del cómic abierto o de la coincidencia de «Mi colección» elegida, en el archivo "
                "original"))
            self.metadata_button.connect("clicked", self._metadata_file)
            for widget in (open_button, paste_button, self.ask_button, self.normalize_button, folder_button,
                           self.metadata_button, meta_folder):
                controls.append(widget)
            self.status = Gtk.Label(label=INITIAL_STATUS, xalign=0, wrap=True)   # sin ajuste, un estado largo obliga a ensanchar la ventana
            self.picture = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.CONTAIN, vexpand=True)
            self.picture.set_size_request(300, 190)   # se encoge sola si falta altura: debajo van los botones, las flechas y los metadatos
            self.cover_placeholder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                                             halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
            self.cover_placeholder.add_css_class("dim-label")
            self.cover_placeholder.append(Gtk.Image(icon_name="comic-identify", pixel_size=96))
            self.cover_placeholder.append(Gtk.Label(label="Ningún cómic abierto"))
            self.cover_overlay = Gtk.Overlay(vexpand=True)   # muestra un icono genérico mientras no hay portada
            self.cover_overlay.set_child(self.picture)
            self.cover_overlay.add_overlay(self.cover_placeholder)

            self.query = Gtk.Entry(placeholder_text="Título a buscar", hexpand=True)
            self.number = Gtk.Entry(placeholder_text="Nº", width_chars=6)
            self.publisher = Gtk.Entry(placeholder_text="Editorial / distribuidor (Panini, Planeta, Forum…)",
                                       hexpand=True)
            self.year = Gtk.Entry(placeholder_text="Año", width_chars=6)
            content = Gtk.Box(spacing=6)
            content.append(self._icon(COMICVINE_HOST, 16))
            content.append(Gtk.Label(label="Buscar en ComicVine"))
            search = Gtk.Button(child=content, tooltip_text=(
                "Busca en ComicVine con estos datos (necesita su clave gratuita, en Ajustes)"))
            search.connect("clicked", lambda _: self._search(*self._fields()))
            for entry in (self.query, self.publisher):
                entry.connect("activate", lambda _e: search.emit("clicked"))
            for entry in (self.query, self.number, self.publisher, self.year):
                entry.connect("changed", self._typed)
            refine = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            clear = icon_button(("edit-clear-all-symbolic", "edit-clear-symbolic"), "Limpiar",
                                tooltip_text="Quita todos los datos: campos, resultados, portada y panel")
            clear.add_css_class("suggested-action")   # verde en este tema
            clear.connect("clicked", self._reset)
            for widgets in ((self.query, self.number, search), (self.publisher, self.year, clear)):
                line = Gtk.Box(spacing=8)
                for widget in widgets:
                    line.append(widget)
                refine.append(line)
            self.results = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
            self.results.connect("row-selected", self._row_selected)
            scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
            scroll.set_child(self.results)

            self.web_extra = Gtk.CheckButton(label="Incluir también la editorial y el año", active=True, tooltip_text=(
                "Añade la editorial y el año a la búsqueda de las webs; si no salen resultados, desmárcalo"))
            menu_content = Gtk.Box(spacing=6)
            menu_content.append(Gtk.Image(icon_name=pick_icon("web-browser-symbolic", FALLBACK_ICON)))
            menu_content.append(Gtk.Label(label="Buscar en otras webs"))
            menu_content.append(Gtk.Image(icon_name=pick_icon("pan-down-symbolic")))
            popover = Gtk.Popover()
            entries = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6,
                              margin_start=6, margin_end=6)
            entries.append(Gtk.Label(label="Se abre en tu navegador", xalign=0, margin_start=6, margin_bottom=4,
                                     css_classes=["dim-label"]))
            for source in SOURCES:
                content = Gtk.Box(spacing=8)
                content.append(self._icon(source.host, 16))
                content.append(Gtk.Label(label=source.name, xalign=0))
                entry = Gtk.Button(child=content, has_frame=False, tooltip_text=f"Busca en {source.host}")
                entry.connect("clicked", lambda _b, n=source.name: (popover.popdown(), self._open_source(n)))
                entries.append(entry)
            popover.set_child(entries)
            web_menu = Gtk.MenuButton(child=menu_content, popover=popover, tooltip_text=(
                "Abre en tu navegador la búsqueda del título en la web que elijas"))
            self.web_menu = web_menu
            sources = Gtk.Box(spacing=12)
            sources.append(web_menu)
            sources.append(self.web_extra)
            side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            side.append(refine)
            side.append(sources)
            side.append(scroll)
            self.pages: list[str] = []      # páginas del cómic abierto; la primera es la portada
            self.page_index = self._page_request = 0
            self._page_cache: dict[int, bytes] = {}
            self.page_buttons = []
            for icon, tip, target in (("go-first-symbolic", "Primera página (la portada)", lambda: 0),
                                      ("go-previous-symbolic", "Página anterior", lambda: self.page_index - 1),
                                      ("go-next-symbolic", "Página siguiente", lambda: self.page_index + 1),
                                      ("go-last-symbolic", "Última página (la contraportada)", lambda: len(self.pages) - 1)):
                button = Gtk.Button(icon_name=pick_icon(icon), tooltip_text=tip)
                button.connect("clicked", lambda _b, t=target: self._go_page(t()))
                self.page_buttons.append(button)
            self.page_label = Gtk.Label(width_chars=17)
            self.page_nav = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER, visible=False)
            for widget in (*self.page_buttons[:2], self.page_label, *self.page_buttons[2:]):
                self.page_nav.append(widget)
            self.export_cover_button = icon_button(("image-x-generic-symbolic", "insert-image-symbolic"),
                                                    "Extraer portada…", sensitive=False, halign=Gtk.Align.CENTER,
                                                    tooltip_text=(
                "Guarda la portada como imagen junto al archivo, con su mismo nombre (para usarla, por ejemplo, "
                "de portada en GCstar); no la recodifica, así que conserva su calidad original"))
            self.export_cover_button.connect("clicked", self._export_cover)
            self.gcstar_button = icon_button(("send-to-symbolic", "document-send-symbolic"), "Transferir a GCstar…",
                                             sensitive=False, halign=Gtk.Align.CENTER, tooltip_text=(
                "Añade el cómic a tu colección de GCstar (créditos, editorial, año, páginas, portada y "
                "contraportada) sin tocar el resto de su archivo .gcs; configúralo en Ajustes"))
            self.gcstar_button.connect("clicked", self._open_gcstar_transfer)
            cover_actions = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
            cover_actions.append(self.export_cover_button)
            cover_actions.append(self.gcstar_button)
            click = Gtk.GestureClick()   # doble clic: la página a la vista, en una ventana grande
            click.connect("pressed", lambda _g, presses, _x, _y: presses == 2 and self._open_viewer())
            self.picture.add_controller(click)
            self.meta_heading = Gtk.Label(label="ComicInfo.xml", xalign=0)
            self.meta_heading.add_css_class("heading")
            self.meta_grid = Gtk.Grid(column_spacing=10, row_spacing=2, margin_end=8)
            meta_scroll = Gtk.ScrolledWindow(min_content_height=70, max_content_height=META_MAX_HEIGHT,
                                             propagate_natural_height=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
            meta_scroll.set_child(self.meta_grid)
            self.meta_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, visible=False, margin_top=4)
            self.meta_box.append(self.meta_heading)
            self.meta_box.append(meta_scroll)
            cover = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            cover.set_size_request(COVER_WIDTH, -1)   # ancho fijo: una portada es vertical y solo gana con el alto
            for widget in (self.cover_overlay, cover_actions, self.page_nav, self.meta_box):   # la portada se queda con el alto que sobra
                cover.append(widget)
            body = Gtk.Box(spacing=12)
            body.append(cover)
            body.append(side)
            paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True, shrink_start_child=False,
                              shrink_end_child=False, resize_end_child=False)
            paned.set_start_child(body)
            paned.set_end_child(self._preview_panel())
            for widget in (controls, self.status, paned):
                page.append(widget)
            drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
            drop.connect("drop", self._dropped)
            page.add_controller(drop)
            return page

        def _open_source(self, name: str):
            title, number, publisher, year = self._fields()
            if not self.web_extra.get_active():
                publisher = year = ""
            try:
                url = search_url(name, title, number, publisher, year)
            except ValueError:
                self.status.set_text(f"Escribe un título para buscarlo en {name}.")
                return
            Gtk.UriLauncher.new(url).launch(self, None, lambda *_: None)

        def _choose_image(self, _button):
            images = Gtk.FileFilter(name="Cómics (CBR/CBZ/CB7) e imágenes")
            images.add_mime_type("image/*")
            for extension in COMIC_EXTENSIONS:
                images.add_suffix(extension.lstrip("."))
            dialog = Gtk.FileDialog(title="Abrir cómic o imagen de portada", default_filter=images)
            dialog.open(self, None, self._image_chosen)

        def _image_chosen(self, dialog, result):
            try:
                self._load(Path(dialog.open_finish(result).get_path()))
            except GLib.Error:
                pass  # Selección cancelada.

        def _open_file(self, path: Path):
            """Abre un cómic o una imagen (arrastrados o pegados); cualquier otro archivo se rechaza con un aviso."""
            if path.suffix.lower() in (*COMIC_EXTENSIONS, *IMAGE_EXTENSIONS):
                self._load(path)
            else:
                self.status.set_text(f"«{path.name}» no es un cómic (CBR, CBZ, CB7) ni una imagen.")

        def _dropped(self, _target, files, _x, _y):
            paths = [f.get_path() for f in files.get_files() if f.get_path()]
            if paths:
                self._open_file(Path(paths[0]))
            return bool(paths)

        def _paste(self):
            """Pega lo que haya en el portapapeles: un archivo copiado en el gestor de archivos (un cómic o una
            imagen) o una imagen copiada."""
            clipboard = self.get_clipboard()
            if clipboard.get_formats().contain_gtype(Gdk.FileList.__gtype__):
                clipboard.read_value_async(Gdk.FileList, GLib.PRIORITY_DEFAULT, None, self._pasted_files)
            else:
                clipboard.read_texture_async(None, self._pasted)

        def _pasted_files(self, clipboard, result):
            try:
                paths = [f.get_path() for f in clipboard.read_value_finish(result).get_files() if f.get_path()]
            except GLib.Error:
                paths = []
            if paths:
                self._open_file(Path(paths[0]))
            else:
                self.status.set_text("El portapapeles no contiene un archivo que se pueda abrir.")

        def _pasted(self, clipboard, result):
            try:
                texture = clipboard.read_texture_finish(result)
            except GLib.Error:
                texture = None
            if texture is None:
                self.status.set_text("El portapapeles no contiene una imagen ni un cómic copiado.")
                return
            target = Path(GLib.get_user_cache_dir()) / "comic-identify" / "pegada.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            texture.save_to_png(str(target))
            self._load(target)

        def _load(self, path: Path):
            """Abre una imagen o un CBR/CBZ. Leer la portada de un archivo puede tardar (hasta ~1 s, más con
            escaneos enormes), así que se hace en un hilo para que la ventana no se congele."""
            self._generation += 1   # invalida cualquier carga o búsqueda anterior
            generation = self._generation
            if path.suffix.lower() not in COMIC_EXTENSIONS:
                self._finish_load(path, None, generation)
                return
            self.status.set_text(f"Leyendo la portada de {path.name}…")
            Thread(target=self._extract_cover, args=(path, generation), daemon=True).start()

        def _extract_cover(self, comic: Path, generation: int):
            target = self.cache_dir / f"portada_{generation}.png"
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                cover_to_png(comic, target)
            except (OSError, ValueError) as error:
                later(self._load_failed, comic, error, generation)
            else:
                later(self._finish_load, target, comic, generation)

        def _load_failed(self, comic: Path, error, generation: int):
            if generation == self._generation:   # si llegó otra carga, este error ya no importa
                self.status.set_text(f"No se pudo leer la portada de {comic.name}: {error}")

        def _finish_load(self, image: Path, source: Path | None, generation: int):
            if generation != self._generation:
                if source is not None:   # portada extraída de una carga que ya no vale
                    image.unlink(missing_ok=True)
                return
            for old in self.cache_dir.glob("portada_*.png"):   # portadas extraídas de cargas anteriores
                if old != image:
                    old.unlink(missing_ok=True)
            self.source_file = source
            self.image = image
            self._set_pages([])
            self.meta_box.set_visible(False)
            self.picture.set_tooltip_text("Doble clic para verla más grande")
            if source is not None:
                Thread(target=self._read_source, args=(source, generation), daemon=True).start()
            self.ask_button.set_sensitive(True)
            self._update_normalize()
            self.picture.set_filename(str(image))
            self.cover_placeholder.set_visible(False)
            self._set_fields("", "", "", "")
            self.library_matches = []
            self._search("", "")

        def _set_pages(self, pages: list[str]):
            """Fija las páginas del cómic abierto y vuelve a la portada; con una sola página no hay nada que navegar."""
            self.pages, self.page_index, self._page_cache = pages, 0, {}
            self._page_request += 1     # descarta lo que se estuviera leyendo del cómic anterior
            self._update_pages()

        def _read_source(self, source: Path, generation: int):
            """En otro hilo: las páginas del archivo y su ComicInfo.xml (leer un RAR lanza `unrar`)."""
            later(self._pages_listed, source, list_pages(source), generation)
            self._read_meta(source, generation)

        def _read_meta(self, source: Path, generation: int):
            try:
                info, error = read_info(source), ""
            except MetadataError as problem:
                info, error = {}, str(problem)
            later(self._show_meta, source, info, error, generation)

        def _refresh_meta(self):
            if self.source_file is not None:
                Thread(target=self._read_meta, args=(self.source_file, self._generation), daemon=True).start()

        def _show_meta(self, source: Path, info: dict, error: str, generation: int):
            if generation != self._generation or source != self.source_file:
                return
            while (child := self.meta_grid.get_first_child()) is not None:
                self.meta_grid.remove(child)
            rows = describe_info(info)
            if error or not rows:
                text = f"No se pudo leer: {error}" if error else "Este archivo no tiene ComicInfo.xml."
                self.meta_grid.attach(Gtk.Label(label=text, xalign=0, wrap=True, css_classes=["dim-label"]), 0, 0, 2, 1)
            for row, (label, value) in enumerate(rows):
                key = Gtk.Label(label=label, xalign=0, yalign=0, css_classes=["dim-label"])
                shown = Gtk.Label(xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, selectable=True,
                                  width_chars=18, max_width_chars=40)
                if value.startswith(("http://", "https://")):
                    escaped = GLib.markup_escape_text(value)
                    shown.set_markup(f'<a href="{escaped}">{escaped}</a>')
                else:
                    shown.set_text(value)
                self.meta_grid.attach(key, 0, row, 1, 1)
                self.meta_grid.attach(shown, 1, row, 1, 1)
            self.meta_box.set_visible(True)

        def _viewer_size(self) -> tuple[int, int]:
            """Tamaño de la ventana grande: casi toda la altura de la pantalla y la proporción de una página."""
            try:
                area = self.get_display().get_monitor_at_surface(self.get_surface()).get_geometry()
            except (AttributeError, TypeError, GLib.Error):
                return 760, 960
            height = int(area.height * 0.9)
            return min(int(height * 0.8), int(area.width * 0.9)), height

        def _open_viewer(self):
            """La página que se está viendo, grande, con las mismas flechas y el teclado (←, →, Inicio, Fin, Esc)."""
            if self.image is None:
                return
            comic, pages = self.source_file, list(self.pages)
            loose = comic is None or not pages    # imagen suelta, o un archivo cuyas páginas no se pudieron listar
            count, name = (1, self.image.name) if loose else (len(pages), comic.name)
            state = {"index": 0 if loose else self.page_index, "request": 0}
            cache: dict[int, bytes] = {}
            width, height = self._viewer_size()
            window = Gtk.Window(title=name, transient_for=self, default_width=width, default_height=height)
            picture = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.CONTAIN, hexpand=True, vexpand=True)
            scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
            scroll.set_child(picture)
            buttons = [Gtk.Button(icon_name=pick_icon(icon), tooltip_text=tip) for icon, tip in (
                ("go-first-symbolic", "Primera página"), ("go-previous-symbolic", "Página anterior"),
                ("go-next-symbolic", "Página siguiente"), ("go-last-symbolic", "Última página"))]
            label = Gtk.Label(width_chars=17)
            actual = Gtk.ToggleButton(label="Tamaño real", tooltip_text="Muestra la página sin reducirla (con barras de desplazamiento)")
            close = icon_button(("window-close-symbolic",), "Cerrar")
            bar = Gtk.Box(spacing=6, margin_top=6, margin_bottom=6, margin_start=8, margin_end=8)
            for widget in (*buttons[:2], label, *buttons[2:], actual):
                bar.append(widget)
            close.set_halign(Gtk.Align.END)
            close.set_hexpand(True)
            bar.append(close)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            box.append(scroll)
            box.append(bar)
            window.set_child(box)

            def refresh_bar(loading=False):
                label.set_text(f"Página {state['index'] + 1} de {count}" + ("…" if loading else ""))
                window.set_title(f"{name} — página {state['index'] + 1} de {count}" if count > 1 else name)
                for button in buttons[:2]:
                    button.set_sensitive(state["index"] > 0)
                for button in buttons[2:]:
                    button.set_sensitive(state["index"] < count - 1)

            def ready(index, request, data):
                if request != state["request"]:
                    return
                if data is None:
                    refresh_bar()
                    self.status.set_text(f"No se pudo leer la página {index + 1} para ampliarla.")
                    return
                cache[index] = data
                try:
                    picture.set_paintable(Gdk.Texture.new_from_bytes(GLib.Bytes.new(data)))
                except GLib.Error:
                    self.status.set_text("No se pudo mostrar esta página.")
                refresh_bar()

            def read(index, request):
                try:
                    data = self.image.read_bytes() if loose else read_page(comic, pages[index])
                except OSError:
                    data = None
                later(ready, index, request, thumbnail_bytes(data, VIEWER_MAX_SIDE) if data else None)

            def show(index):
                state["index"] = max(0, min(index, count - 1))
                state["request"] += 1
                if state["index"] in cache:
                    ready(state["index"], state["request"], cache[state["index"]])
                    return
                refresh_bar(loading=True)
                Thread(target=read, args=(state["index"], state["request"]), daemon=True).start()

            def key(_controller, keyval, _code, _mods):
                target = {Gdk.KEY_Left: state["index"] - 1, Gdk.KEY_Page_Up: state["index"] - 1,
                          Gdk.KEY_Right: state["index"] + 1, Gdk.KEY_Page_Down: state["index"] + 1,
                          Gdk.KEY_Home: 0, Gdk.KEY_End: count - 1}.get(keyval)
                if keyval == Gdk.KEY_Escape:
                    window.close()
                elif target is not None:
                    show(target)
                return target is not None or keyval == Gdk.KEY_Escape

            for button, target in zip(buttons, (lambda: 0, lambda: state["index"] - 1, lambda: state["index"] + 1,
                                                lambda: count - 1), strict=True):
                button.connect("clicked", lambda _b, t=target: show(t()))
            actual.connect("toggled", lambda b: picture.set_can_shrink(not b.get_active()))
            close.connect("clicked", lambda _b: window.close())
            controller = Gtk.EventControllerKey()
            controller.connect("key-pressed", key)
            window.add_controller(controller)
            for widget in (*buttons, actual):
                widget.set_focusable(False)   # que las flechas del teclado no muevan el foco entre botones
            self.viewer = {"window": window, "picture": picture, "label": label, "actual": actual}   # para las pruebas
            show(state["index"])
            window.present()

        def _pages_listed(self, source: Path, pages: list[str], generation: int):
            if generation == self._generation and source == self.source_file:
                self._set_pages(pages)

        def _update_pages(self, loading: bool = False):
            count = len(self.pages)
            self.page_nav.set_visible(count > 1)
            self.page_label.set_text(f"Página {self.page_index + 1} de {count}" + ("…" if loading else ""))
            for button in self.page_buttons[:2]:
                button.set_sensitive(self.page_index > 0)
            for button in self.page_buttons[2:]:
                button.set_sensitive(self.page_index < count - 1)

        def _go_page(self, index: int):
            """Muestra otra página bajo la portada. Solo cambia lo que se ve: la búsqueda sigue usando la portada."""
            if not self.pages or self.source_file is None:
                return
            self.page_index = max(0, min(index, len(self.pages) - 1))
            self._page_request += 1
            if self.page_index == 0 and self.image is not None:
                self.picture.set_filename(str(self.image))
                self._update_pages()
            elif self.page_index in self._page_cache:
                self._show_page(self._page_cache[self.page_index])
            else:
                self._update_pages(loading=True)
                Thread(target=self._read_page, args=(self.source_file, self.pages[self.page_index], self.page_index,
                                                     self._page_request), daemon=True).start()

        def _read_page(self, comic: Path, name: str, index: int, request: int):
            data = read_page(comic, name)
            later(self._page_ready, index, request, thumbnail_bytes(data, PAGE_MAX_SIDE) if data else None)

        def _page_ready(self, index: int, request: int, data: bytes | None):
            if request != self._page_request:   # ya se pidió otra página o se abrió otro cómic
                return
            if data is None:
                self._update_pages()
                self.status.set_text(f"No se pudo leer la página {index + 1} de este archivo.")
                return
            if len(self._page_cache) >= PAGES_CACHED:
                self._page_cache.pop(next(iter(self._page_cache)))
            self._page_cache[index] = data
            self._show_page(data)

        def _show_page(self, data: bytes):
            try:
                self.picture.set_paintable(Gdk.Texture.new_from_bytes(GLib.Bytes.new(data)))
            except GLib.Error:
                self.status.set_text("No se pudo mostrar esta página.")
            self._update_pages()

        def _reset(self, _button=None):
            """Vuelve al estado inicial: sin campos, resultados, portada, ficha ni sesión de IA."""
            self._generation += 1
            self.busy = False
            if self._live_timer:
                GLib.source_remove(self._live_timer)
                self._live_timer = 0
            self._set_fields("", "", "", "")
            self.image = self.source_file = None
            self._set_pages([])
            self.meta_box.set_visible(False)
            self.picture.set_tooltip_text(None)
            self.picture.set_paintable(None)
            self.cover_placeholder.set_visible(True)
            self.library_matches = []
            self._show_candidates([])
            self.selected = None
            self._close_preview(None)
            self.ask_button.set_sensitive(False)
            self._update_normalize()
            self.status.set_text(INITIAL_STATUS)

        def _fields(self) -> tuple[str, str, str, str]:
            """Título, número, editorial y año, sin espacios sobrantes."""
            return tuple(entry.get_text().strip() for entry in (self.query, self.number, self.publisher, self.year))

        def _search(self, query: str, number: str, publisher: str = "", year: str = ""):
            if self.busy or self.image is None:
                return
            self.busy = True
            key = self.settings.api_key.strip()
            client = ComicVineClient(key) if key else None
            Thread(target=self._work, args=(self.image, client, query, number, publisher, year, self._generation),
                   daemon=True).start()

        def _work(self, image, client, query, number, publisher, year, generation):
            library = Library(LIBRARY_DB) if LIBRARY_DB.exists() else None
            gcd = self._gcd()
            try:
                outcome = identify(image, library, client, query, number,
                                   progress=lambda message: later(self._progress, message, generation), gcd=gcd,
                                   publisher=publisher, year=year)
            except Exception as error:  # noqa: BLE001 - se muestra al usuario, no debe cerrar la app
                later(self._failed, error, generation)
            else:
                later(self._show, outcome, generation)

        def _progress(self, message: str, generation: int):
            if generation == self._generation:
                self.status.set_text(message)

        def _failed(self, error, generation=None):
            if generation is not None and generation != self._generation:
                return   # se ha limpiado mientras tanto
            self.busy = False
            self.status.set_text(f"No se pudo procesar la imagen: {error}")

        def _show(self, outcome, generation=None):
            if generation is not None and generation != self._generation:
                return   # se ha limpiado mientras tanto
            self.busy = False
            if outcome.issue_number and not self.number.get_text():   # p. ej. del código de barras
                self._set_fields(number=outcome.issue_number)
            self.library_matches = [c for c in outcome.candidates if c.source == "Mi colección"]
            self._show_candidates(outcome.candidates)
            summary = [f"Código de barras: {outcome.barcode}"] if outcome.barcode else []
            summary += outcome.notes
            if not outcome.candidates and not outcome.notes:
                summary.append("Sin resultados; prueba a corregir el título o el número.")
            if outcome.candidates:
                summary.append(f"{len(outcome.candidates)} candidato(s), de más a menos parecido.")
            self._add_panel_hint(summary, outcome.candidates)
            self.status.set_text(" · ".join(summary))

        def _add_panel_hint(self, summary, candidates):
            if any(c.source == "ComicVine" or (c.source == "GCD" and webkit_available()) for c in candidates):
                summary.append("Haz clic en una sugerencia para ver su ficha a la derecha.")

        def _show_candidates(self, candidates):
            self.results.unselect_all()
            while (row := self.results.get_first_child()) is not None:
                self.results.remove(row)
            self.candidates = list(candidates)
            for candidate in self.candidates:
                self.results.append(self._row(candidate))

        # ---- Búsqueda al vuelo en GCD (local: sin red ni límites) -----------------------------
        @staticmethod
        def _gcd():
            index = GcdIndex(GCD_DB)
            return index if index.is_ready() else None

        def _set_fields(self, query=None, number=None, publisher=None, year=None):
            self._quiet = True
            for entry, text in ((self.query, query), (self.number, number),
                                (self.publisher, publisher), (self.year, year)):
                if text is not None:
                    entry.set_text(text)
            self._quiet = False

        def _typed(self, _entry):
            if self._quiet:
                return
            if self._live_timer:
                GLib.source_remove(self._live_timer)
            self._live_timer = GLib.timeout_add(LIVE_DELAY_MS, self._live_search)

        def _live_search(self):
            self._live_timer = 0
            query, number, publisher, year = self._fields()
            gcd = self._gcd()
            if gcd is None:
                self.status.set_text("Importa el volcado de GCD (pestaña Ajustes) para buscar mientras escribes; "
                                     "«Buscar en ComicVine» consulta ComicVine.")
            elif len(query) < 2:
                self._show_candidates(self.library_matches)
            else:
                hits = search_gcd(gcd, query, number, publisher, year)
                self._show_candidates(self.library_matches + hits)
                summary = [f"{len(hits)} sugerencia(s) de GCD para «{query}»" if hits
                           else f"Sin resultados en GCD para «{query}»"]
                summary.append("«Buscar en ComicVine» lo consulta también.")
                self._add_panel_hint(summary, hits)
                self.status.set_text(" · ".join(summary))
            return GLib.SOURCE_REMOVE

        # ---- Normalizar el nombre del archivo ---------------------------------------------------
        def _normalize_target(self) -> Path | None:
            """El CBR/CBZ abierto o, si no, el archivo de la coincidencia de «Mi colección» elegida."""
            if self.source_file is not None and self.source_file.is_file():
                return self.source_file
            if self.selected is not None and self.selected.path is not None and self.selected.path.is_file():
                return self.selected.path
            return None

        def _update_normalize(self):
            target = self._normalize_target()
            self.normalize_button.set_sensitive(target is not None)
            self.metadata_button.set_sensitive(target is not None)
            self.export_cover_button.set_sensitive(target is not None)
            self.gcstar_button.set_sensitive(target is not None and bool(self.settings.gcstar_path.strip()))

        # ---- Extraer la portada como imagen (para catalogadores externos como GCstar) -----------
        def _export_cover(self, _button):
            target = self._normalize_target()
            if target is None:
                return
            self.status.set_text(f"Extrayendo la portada de {target.name}…")

            def work():
                try:
                    saved = extract_cover(target, target.with_suffix(""))
                except (OSError, ValueError) as error:
                    later(self._export_cover_failed, error)
                else:
                    later(self._export_cover_done, saved)
            Thread(target=work, daemon=True).start()

        def _export_cover_done(self, saved: Path):
            self.status.set_text(f"Portada guardada como «{saved.name}», junto al archivo.")

        def _export_cover_failed(self, error):
            self.status.set_text(f"No se pudo extraer la portada: {error}")

        # ---- Transferir a GCstar ---------------------------------------------------------------------
        def _open_gcstar_transfer(self, _button):
            target = self._normalize_target()
            gcs_path = Path(self.settings.gcstar_path.strip()) if self.settings.gcstar_path.strip() else None
            if target is None or gcs_path is None:
                return
            self.status.set_text(f"Leyendo {target.name} y {gcs_path.name}…")

            def work():
                try:
                    info = read_info(target)
                    read_error = ""
                except MetadataError as error:
                    info, read_error = {}, str(error)
                try:
                    text = gcs_path.read_text(encoding="utf-8")
                except OSError as error:
                    later(self._gcstar_prep_failed, str(error))
                    return
                vocab = {field_name: vocabulary(text, field_name) for field_name in VOCABULARY_FIELDS}
                pages = len(list_pages(target))
                later(self._open_gcstar_dialog, target, info, read_error, gcs_path, vocab, pages)
            Thread(target=work, daemon=True).start()

        def _gcstar_prep_failed(self, message: str):
            self.status.set_text(f"No se pudo preparar la transferencia a GCstar: {message}")

        def _open_gcstar_dialog(self, target: Path, info: dict, read_error: str, gcs_path: Path, vocab: dict,
                                page_count: int):
            window = Gtk.Window(title="Transferir a GCstar", transient_for=self, modal=True, default_width=640)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=14, margin_bottom=14,
                          margin_start=16, margin_end=16)
            window.set_child(box)
            head = Gtk.Label(xalign=0, wrap=True)
            head.set_markup(f"<b>Archivo:</b> {GLib.markup_escape_text(target.name)}\n"
                            f"<b>Colección:</b> {GLib.markup_escape_text(str(gcs_path))}")
            box.append(head)
            if read_error or not info:
                warning = Gtk.Label(xalign=0, wrap=True, label=(
                    f"No se pudo leer el ComicInfo.xml: {read_error}" if read_error else
                    "Este archivo no tiene ComicInfo.xml todavía: se transferirá con muy pocos datos. Si quieres "
                    "los créditos, la editorial, el año…, escribe antes los metadatos."))
                warning.add_css_class("warning" if read_error else "dim-label")
                box.append(warning)
            series = series_text(info.get("Series", ""), info.get("Volume", ""))
            preview = Gtk.Label(xalign=0, wrap=True, selectable=True)
            preview.set_markup(f"<b>{GLib.markup_escape_text(format_name(series, info.get('Number', ''), info.get('Title', '')))}</b>")
            box.append(preview)
            details = ", ".join(part for part in (
                info.get("Publisher", ""), info.get("Year", ""), f"{page_count} páginas" if page_count else "") if part)
            if details:
                box.append(Gtk.Label(label=details, xalign=0, wrap=True, css_classes=["dim-label"]))

            box.append(Gtk.Label(label="Campos propios de GCstar (se sugiere lo que ya usas en tu colección):",
                                 xalign=0))
            grid = Gtk.Grid(column_spacing=10, row_spacing=6)
            fields = {"type": "Tipo", "category": "Categoría", "format": "Formato", "collection": "Colección"}
            gcstar_entries: dict[str, Gtk.Entry] = {}
            for row, (key, label) in enumerate(fields.items()):
                entry = Gtk.Entry(hexpand=True)
                store = Gtk.ListStore(str)
                for value in vocab.get(key, []):
                    store.append([value])
                completion = Gtk.EntryCompletion(model=store, text_column=0, inline_completion=True)
                entry.set_completion(completion)
                gcstar_entries[key] = entry
                grid.attach(Gtk.Label(label=label, xalign=0), (row % 2) * 2, row // 2, 1, 1)
                grid.attach(entry, (row % 2) * 2 + 1, row // 2, 1, 1)
            box.append(grid)
            back_check = Gtk.CheckButton(label="Incluir también la contraportada (última página)", active=True,
                                        sensitive=page_count > 1)
            box.append(back_check)

            problem = Gtk.Label(xalign=0, wrap=True, css_classes=["error"])
            buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
            cancel = icon_button(STOP_ICON, "Cancelar")
            apply = icon_button(("emblem-ok-symbolic", "object-select-symbolic"), "Transferir")
            apply.add_css_class("suggested-action")
            for widget in (cancel, apply):
                buttons.append(widget)
            for widget in (problem, buttons):
                box.append(widget)

            def do_transfer(_button):
                for widget in (cancel, apply):
                    widget.set_sensitive(False)
                problem.set_text("")
                gcstar_fields = {key: entry.get_text().strip() for key, entry in gcstar_entries.items()}
                folders = [Path(f) for f in self.settings.folders]
                include_back = back_check.get_active()

                def work():
                    try:
                        result = gcstar_transfer(target, info, gcstar_fields, gcs_path, folders, GCSTAR_LOG,
                                                 include_back)
                    except GCstarError as error:
                        later(self._gcstar_transfer_failed, window, cancel, apply, problem, str(error))
                    else:
                        later(self._gcstar_transfer_done, window, result)
                Thread(target=work, daemon=True).start()
            cancel.connect("clicked", lambda _b: window.close())
            apply.connect("clicked", do_transfer)
            window.present()

        def _gcstar_transfer_failed(self, window, cancel, apply, problem, message: str):
            for widget in (cancel, apply):
                widget.set_sensitive(True)
            problem.set_text(message)

        def _gcstar_transfer_done(self, window, result):
            window.close()
            where = (f" Portada en «{result.image.name}»" + (f" y contraportada en «{result.backpic.name}»."
                    if result.backpic else ".") if result.image else " Sin portada (el archivo no está bajo "
                    "ninguna carpeta de «Mi colección»).")
            self.status.set_text(f"Transferido a GCstar (elemento nº {result.item_id}).{where}")

        def _undo_gcstar(self, _button):
            self.gcstar_undo_button.set_sensitive(False)
            self.gcstar_info.set_text("Deshaciendo…")

            def run():
                try:
                    later(self._gcstar_undone, undo_gcstar(GCSTAR_LOG), None)
                except (OSError, LookupError, GCstarError) as error:
                    later(self._gcstar_undone, None, error)
            Thread(target=run, daemon=True).start()

        def _gcstar_undone(self, result, error):
            self.gcstar_undo_button.set_sensitive(True)
            if error is not None:
                self.gcstar_info.set_text(f"No se pudo deshacer: {error}")
                return
            text = ("Deshecha la última transferencia." if result.removed else
                   "El elemento ya no estaba tal cual en el .gcs (se ha editado desde entonces): no se ha tocado.")
            if result.images:
                text += f" Se borraron {len(result.images)} imagen(es)."
            if result.skipped_images:
                text += f" {len(result.skipped_images)} imagen(es) habían cambiado desde entonces y no se tocaron."
            self.gcstar_info.set_text(text)

        def _normalize(self, _button):
            target = self._normalize_target()
            if target is None:
                return
            if self.selected is not None:
                values, from_gcd = suggest_values(self.selected), self.selected.source == "GCD"
            else:   # sin sugerencia elegida: lo que haya en los campos de búsqueda
                title, number, _publisher, year = self._fields()
                values, from_gcd = Values(nombre=title, numero=number, edicion=year), False
            self._open_normalizer(target, values, from_gcd)

        def _open_normalizer(self, target: Path, values: Values, from_gcd: bool):
            window = Gtk.Window(title="Normalizar nombre", transient_for=self, modal=True, default_width=720)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=14, margin_bottom=14,
                          margin_start=16, margin_end=16)
            window.set_child(box)
            current = Gtk.Label(xalign=0, wrap=True, selectable=False)
            current.set_markup(f"<b>Archivo:</b> {GLib.markup_escape_text(target.name)}")
            box.append(current)
            where = Gtk.Label(xalign=0, wrap=True, label=(
                f"En {target.parent}. Se renombra este mismo archivo, no una copia; se puede deshacer desde Ajustes."))
            where.add_css_class("dim-label")
            box.append(where)

            grid = Gtk.Grid(column_spacing=12, row_spacing=6)
            entries: dict[str, Gtk.Editable] = {}
            fields = (("nombre", "Nombre", "serie u OneShot"), ("volumen", "Volumen", "8 → «Volumen 8»"),
                      ("contenido", "Contenido [años]", "años del material original: 1991 o 1991-1993"),
                      ("edicion", "Edición (años)", "años de la edición que tienes"),
                      ("sello", "Sello", "solo el que ves impreso en el ejemplar"), ("numero", "Nº", "opcional"))
            flag = Gtk.DropDown.new_from_strings(["(ninguna)", *FLAGS.values()])
            flag.set_selected(([""] + list(FLAGS.values())).index(values.bandera) if values.bandera in FLAGS.values() else 0)
            for row, (key, label, hint) in enumerate(fields[:2] + (("bandera", "Bandera", ""),) + fields[2:]):
                grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
                widget = flag if key == "bandera" else Gtk.Entry(text=getattr(values, key), hexpand=True,
                                                                  placeholder_text=hint)
                if key != "bandera":
                    entries[key] = widget
                grid.attach(widget, 1, row, 1, 1)
                if key == "contenido":   # el dato que no se sabe solo: ayuda para averiguarlo en ComicVine
                    find = Gtk.Button(child=self._button_content("Buscar en ComicVine…"), tooltip_text=(
                        "Busca los años originales en ComicVine a partir del título original y los números"))
                    find.connect("clicked", lambda _b: self._open_original_lookup(window, entries))
                    grid.attach(find, 2, row, 1, 1)
            box.append(grid)
            if from_gcd:
                note = Gtk.Label(xalign=0, wrap=True, label=(
                    "El sello y los años vienen de GCD, transcritos por otro colaborador: compruébalos con el "
                    "ejemplar. El año real del contenido en ediciones españolas no se sabe solo: ponlo tú o "
                    "búscalo con el botón de ComicVine."))
                note.add_css_class("dim-label")
                box.append(note)

            box.append(Gtk.Label(label="Patrón (variables: " + ", ".join("{" + v + "}" for v in VARIABLES) + "):",
                                 xalign=0, wrap=True))
            pattern_row = Gtk.Box(spacing=8)
            pattern = Gtk.Entry(text=self.settings.pattern, hexpand=True)
            reset = icon_button(("edit-undo-symbolic", "view-refresh-symbolic"), "Restablecer")
            reset.connect("clicked", lambda _b: pattern.set_text(DEFAULT_PATTERN))
            pattern_row.append(pattern)
            pattern_row.append(reset)
            box.append(pattern_row)

            preview = Gtk.Label(xalign=0, wrap=True)
            problem = Gtk.Label(xalign=0, wrap=True)
            problem.add_css_class("error")
            hint = Gtk.Label(xalign=0, wrap=True)
            hint.add_css_class("dim-label")
            box.append(Gtk.Label(label="Nombre resultante:", xalign=0))
            box.append(preview)
            box.append(hint)
            box.append(problem)

            buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
            cancel = icon_button(("process-stop-symbolic", "window-close-symbolic"), "Cancelar")
            apply = icon_button(("emblem-ok-symbolic", "object-select-symbolic"), "Renombrar")
            apply.add_css_class("suggested-action")
            buttons.append(cancel)
            buttons.append(apply)
            box.append(buttons)

            def current_values() -> Values:
                chosen = flag.get_selected()
                return Values(bandera=list(FLAGS.values())[chosen - 1] if chosen else "",
                              **{key: entry.get_text() for key, entry in entries.items()})

            state = {"stem": None}

            def refresh(*_args):
                state["stem"] = None
                try:
                    stem = render(pattern.get_text(), current_values())
                except ValueError as error:
                    preview.set_text("")
                    problem.set_text(str(error))
                    apply.set_sensitive(False)
                    return
                new = target.with_name(stem + target.suffix)
                preview.set_markup(f"<big><b>{GLib.markup_escape_text(new.name)}</b></big>")
                hint.set_text("Sin años del contenido: el nombre llevará solo (años de la edición). Si más adelante "
                              "los averiguas, se completa volviendo a normalizar."
                              if missing_content_years(pattern.get_text(), current_values()) else "")
                if not stem:
                    problem.set_text("El nombre resultante está vacío.")
                elif new == target:
                    problem.set_text("Es el nombre que ya tiene.")
                elif new.exists():
                    problem.set_text("Ya existe un archivo con ese nombre en la carpeta; no se sobrescribe.")
                else:
                    problem.set_text("")
                    state["stem"] = stem
                apply.set_sensitive(state["stem"] is not None)

            def do_rename(_button):
                library = Library(LIBRARY_DB) if LIBRARY_DB.exists() else None
                try:
                    check_pattern(pattern.get_text())
                    new = rename_file(target, state["stem"], RENAME_LOG, library)
                except (OSError, ValueError) as error:
                    problem.set_text(f"No se pudo renombrar: {error}")
                    return
                self.settings.pattern = pattern.get_text()
                self.settings.save()
                if self.source_file == target:
                    self.source_file = new
                if self.selected is not None and self.selected.path == target:
                    self.selected.path = new
                self.status.set_text(f"Renombrado: {target.name} → {new.name}")
                self._update_normalize()
                window.close()

            for entry in (*entries.values(), pattern):
                entry.connect("changed", refresh)
            flag.connect("notify::selected", refresh)
            cancel.connect("clicked", lambda _b: window.close())
            apply.connect("clicked", do_rename)
            self.normalizer = {"window": window, "entries": entries, "flag": flag, "pattern": pattern,
                               "preview": preview, "problem": problem, "apply": apply, "hint": hint}   # para las pruebas
            refresh()
            window.present()
            for entry in entries.values():   # sin texto resaltado al abrir
                entry.select_region(0, 0)
            entries["contenido"].grab_focus()   # es el dato que casi siempre hay que poner a mano

        def _button_content(self, text: str):
            content = Gtk.Box(spacing=6)
            content.append(self._icon(COMICVINE_HOST, 16))
            content.append(Gtk.Label(label=text))
            return content

        def _open_original_lookup(self, parent, entries, first_default: str = "", last_default: str = ""):
            """Averigua los años del material original con ComicVine: título original → serie → años."""
            window = Gtk.Window(title="Años del material original", transient_for=parent, modal=True,
                                default_width=560, default_height=460)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12,
                          margin_start=14, margin_end=14)
            window.set_child(box)
            box.append(Gtk.Label(xalign=0, wrap=True, label=(
                "Escribe el título original (en inglés) y los números americanos que recoge la edición; "
                "los años salen de las fechas de portada de ComicVine.")))
            title = Gtk.Entry(placeholder_text="Título original, p. ej. Captain Marvel", hexpand=True)
            first = Gtk.Entry(placeholder_text="Nº inicial", width_chars=9, text=first_default or (
                entries["numero"].get_text() if "numero" in entries else ""))
            last = Gtk.Entry(placeholder_text="Nº final (opcional)", width_chars=16, text=last_default)
            search = Gtk.Button(child=self._button_content("Buscar series"))
            line = Gtk.Box(spacing=8)
            for widget in (first, last, search):
                line.append(widget)
            listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
            scroll = Gtk.ScrolledWindow(vexpand=True)
            scroll.set_child(listing)
            info = Gtk.Label(xalign=0, wrap=True)
            buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
            cancel = icon_button(("process-stop-symbolic", "window-close-symbolic"), "Cancelar")
            use = icon_button(("emblem-ok-symbolic", "object-select-symbolic"), "Usar estos años", sensitive=False)
            use.add_css_class("suggested-action")
            buttons.append(cancel)
            buttons.append(use)
            for widget in (title, line, scroll, info, buttons):
                box.append(widget)

            volumes: list = []
            key = self.settings.api_key.strip()
            if not key:
                info.set_text("Necesitas la clave gratuita de ComicVine (pestaña Ajustes) para esta búsqueda.")
                search.set_sensitive(False)

            def fail(error):
                info.set_text(str(error))
                search.set_sensitive(True)

            def search_done(found):
                volumes[:] = found
                while (row := listing.get_first_child()) is not None:
                    listing.remove(row)
                for volume in found:
                    listing.append(Gtk.Label(label=volume.label, xalign=0, margin_top=4, margin_bottom=4,
                                             margin_start=6))
                info.set_text(f"{len(found)} serie(s). Elige la que recoge tu edición." if found
                              else "ComicVine no encuentra esa serie: prueba con el título original en inglés.")
                search.set_sensitive(True)

            def do_search(_widget):
                search.set_sensitive(False)
                info.set_text("Buscando en ComicVine…")

                def work():
                    try:
                        found = find_volumes(ComicVineClient(key), title.get_text())
                    except (ComicVineError, ValueError) as error:
                        later(fail, error)
                    else:
                        later(search_done, found)
                Thread(target=work, daemon=True).start()

            def do_use(_widget):
                row = listing.get_selected_row()
                if row is None:
                    return
                volume = volumes[row.get_index()]
                use.set_sensitive(False)
                info.set_text("Consultando las fechas de portada…")

                def work():
                    try:
                        years = content_years(ComicVineClient(key), volume.id, first.get_text(), last.get_text())
                    except (ComicVineError, LookupError, ValueError) as error:
                        later(lambda e=error: (info.set_text(str(e)), use.set_sensitive(True)))
                    else:
                        later(finish, years, volume)
                Thread(target=work, daemon=True).start()

            def finish(years, volume):
                entries["contenido"].set_text(years)
                self.status.set_text(f"Años del contenido: {years} (portadas de {volume.name} {volume.start_year} en ComicVine).")
                window.close()

            search.connect("clicked", do_search)
            title.connect("activate", do_search)
            listing.connect("row-selected", lambda _l, row: use.set_sensitive(row is not None))
            cancel.connect("clicked", lambda _b: window.close())
            use.connect("clicked", do_use)
            self.lookup = {"window": window, "title": title, "first": first, "last": last, "search": search,
                           "listing": listing, "use": use, "info": info}   # para las pruebas
            window.present()
            title.grab_focus()

        # ---- Normalizar una carpeta-serie y renumerar su contenido --------------------------------
        def _choose_series_folder(self, _button):
            Gtk.FileDialog(title="Carpeta de la serie").select_folder(self, None, self._series_folder_chosen)

        def _series_folder_chosen(self, dialog, result):
            try:
                folder = Path(dialog.select_folder_finish(result).get_path())
            except GLib.Error:
                return
            self._start_series_normalizer(folder)

        def _start_series_normalizer(self, folder: Path):
            files = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in COMIC_EXTENSIONS),
                           key=lambda p: natural_key(p.name))
            if not files:
                self.status.set_text(f"No hay archivos CBR/CBZ directamente en {folder.name}.")
                return
            info, gcd = None, self._gcd()
            if gcd is not None and self.selected is not None and self.selected.series_id:
                info = gcd.series_info(self.selected.series_id)
            if info is not None:
                values, from_gcd = series_values(info), True
            else:   # sin serie de GCD elegida: lo tecleado, o el nombre de la carpeta
                title, _number, _publisher, year = self._fields()
                values, from_gcd = Values(nombre=title or folder.name, edicion=year), False
            self._open_series_normalizer(folder, files, values, from_gcd)

        def _open_series_normalizer(self, folder: Path, files: list[Path], values: Values, from_gcd: bool):
            window = Gtk.Window(title="Normalizar carpeta", transient_for=self, modal=True, default_width=900,
                                default_height=760)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12,
                          margin_start=14, margin_end=14)
            window.set_child(box)
            head = Gtk.Label(xalign=0, wrap=True)
            head.set_markup(f"<b>Carpeta:</b> {GLib.markup_escape_text(str(folder))}  ({len(files)} archivos)")
            box.append(head)

            detected = [(path, *detect_number(path.stem)) for path in files]
            numbers = [int(n) for _p, n, _d in detected if n]
            grid = Gtk.Grid(column_spacing=12, row_spacing=6)
            entries: dict[str, Gtk.Entry] = {}
            flag = Gtk.DropDown.new_from_strings(["(ninguna)", *FLAGS.values()])
            flag.set_selected(([""] + list(FLAGS.values())).index(values.bandera)
                              if values.bandera in FLAGS.values() else 0)
            fields = (("nombre", "Nombre (serie)", ""), ("volumen", "Volumen", "8 → «Volumen 8»"), ("bandera", "Bandera", ""),
                      ("contenido", "Contenido [años]", "años del material original: 1999-2001"),
                      ("edicion", "Edición (años)", "2000-2002; 2011- si sigue publicándose"),
                      ("sello", "Sello", "solo el que ves impreso en los ejemplares"))
            for row, (key, label, hint) in enumerate(fields):
                grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
                widget = flag if key == "bandera" else Gtk.Entry(text=getattr(values, key), hexpand=True,
                                                                  placeholder_text=hint)
                if key != "bandera":
                    entries[key] = widget
                grid.attach(widget, 1, row, 1, 1)
                if key == "contenido":
                    find = icon_button(("system-search-symbolic",), "Buscar en ComicVine…", tooltip_text=(
                        "Averigua los años del material original a partir del título original y los números"))
                    find.connect("clicked", lambda _b: self._open_original_lookup(
                        window, entries, str(min(numbers)) if numbers else "",
                        str(max(numbers)) if len(numbers) > 1 else ""))
                    grid.attach(find, 2, row, 1, 1)
            box.append(grid)
            if from_gcd:
                note = Gtk.Label(xalign=0, wrap=True, label=(
                    "Nombre, país, años de la serie y sello vienen de GCD (transcritos por otro colaborador): "
                    "compruébalos. Los años del contenido original no se saben solos: ponlos tú o búscalos en ComicVine."))
                note.add_css_class("dim-label")
                box.append(note)

            box.append(Gtk.Label(label="Patrón de la carpeta:", xalign=0))
            folder_pattern = Gtk.Entry(text=self.settings.pattern, hexpand=True)
            box.append(folder_pattern)
            box.append(Gtk.Label(xalign=0, wrap=True, label=(
                "Cada archivo se llamará como la carpeta resultante más « #01», « #02»… Se usa el número que ya trae "
                "cada nombre, así que los huecos se respetan.")))

            result = Gtk.Label(xalign=0, wrap=True)
            box.append(Gtk.Label(label="Carpeta resultante:", xalign=0))
            box.append(result)

            listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            rows = []
            for path, number, doubtful in detected:
                line = Gtk.Box(spacing=8, margin_top=3, margin_bottom=3, margin_start=6, margin_end=6)
                include = Gtk.CheckButton(active=True, tooltip_text="Renombrar este archivo")
                old = Gtk.Label(label=path.name, xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.MIDDLE,
                                width_chars=28, max_width_chars=40)
                entry = Gtk.Entry(text=str(int(number)) if number else "", width_chars=5, placeholder_text="Nº",
                                  tooltip_text="Número de ejemplar de este archivo")
                new = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.MIDDLE, width_chars=28,
                                max_width_chars=44)
                note = Gtk.Label(xalign=0, width_chars=22)
                for widget in (include, old, entry, Gtk.Label(label="→"), new, note):
                    line.append(widget)
                listing.append(line)
                rows.append({"path": path, "include": include, "entry": entry, "new": new, "note": note,
                             "doubtful": doubtful, "name": None, "number": None})
            scroll = Gtk.ScrolledWindow(vexpand=True, min_content_height=240)
            scroll.set_child(listing)
            box.append(scroll)
            summary = Gtk.Label(xalign=0, wrap=True)
            problem = Gtk.Label(xalign=0, wrap=True)
            problem.add_css_class("error")
            buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
            cancel = icon_button(("process-stop-symbolic", "window-close-symbolic"), "Cancelar")
            apply = icon_button(("emblem-ok-symbolic", "object-select-symbolic"), "Renombrar carpeta y archivos")
            apply.add_css_class("suggested-action")
            for widget in (cancel, apply):
                buttons.append(widget)
            for widget in (summary, problem, buttons):
                box.append(widget)

            state = {"folder_stem": None}

            def current_values() -> Values:
                chosen = flag.get_selected()
                return Values(bandera=list(FLAGS.values())[chosen - 1] if chosen else "",
                              **{key: entry.get_text() for key, entry in entries.items()})

            def refresh(*_args):
                blocking, state["folder_stem"] = [], None
                try:
                    folder_stem = render(folder_pattern.get_text(), current_values())
                except ValueError as error:
                    result.set_text("")
                    problem.set_text(str(error))
                    apply.set_sensitive(False)
                    return
                new_folder = folder.with_name(folder_stem) if folder_stem else folder
                result.set_markup(f"<big><b>{GLib.markup_escape_text(new_folder.name)}</b></big>")
                if not folder_stem:
                    blocking.append("El nombre de la carpeta resultante está vacío.")
                elif new_folder != folder and new_folder.exists():
                    blocking.append(f"Ya existe una carpeta llamada «{new_folder.name}».")
                included = [r for r in rows if r["include"].get_active()]
                for r in rows:
                    text = r["entry"].get_text().strip()
                    r["number"] = int(text) if text.isdigit() else None
                width = number_width([r["number"] for r in included if r["number"] is not None])
                moving = {r["path"].name for r in included}
                taken: dict[str, int] = {}
                for r in rows:
                    r["name"], message = None, ""
                    if not r["include"].get_active():
                        r["new"].set_text("(no se renombra)")
                    elif r["number"] is None:
                        r["new"].set_text("—")
                        message = "Sin número"
                        blocking.append(f"{r['path'].name}: escribe su número o exclúyelo.")
                    else:
                        if not folder_stem:
                            message = "Nombre vacío"
                        else:
                            r["name"] = f"{folder_stem} #{pad_number(r['number'], width)}{r['path'].suffix}"
                            if len(r["name"].encode()) > MAX_NAME_BYTES:
                                message = "Nombre demasiado largo"
                                blocking.append("El nombre de los archivos es demasiado largo para el sistema de archivos.")
                            r["new"].set_text(r["name"])
                            taken[r["name"]] = taken.get(r["name"], 0) + 1
                            message = "revisa el número" if r["doubtful"] else ""
                    r["note"].set_text(message)
                existing = {p.name for p in folder.iterdir()}
                for r in rows:
                    if r["name"] is None:
                        continue
                    if taken[r["name"]] > 1:
                        r["note"].set_text("Repetido")
                        blocking.append(f"Hay varios archivos con el número de «{r['name']}».")
                    elif r["name"] in existing and r["name"] not in moving:
                        r["note"].set_text("Ya existe")
                        blocking.append(f"«{r['name']}» ya existe y no forma parte del lote.")
                changes = [r for r in rows if r["name"] and r["name"] != r["path"].name]
                summary.set_text(f"{len(changes)} archivo(s) se renombran · "
                                 f"{sum(1 for r in rows if r['name'] == r['path'].name)} ya tienen ese nombre · "
                                 f"{sum(1 for r in rows if not r['include'].get_active())} sin tocar")
                extra = f" (y {len(blocking) - 1} problema(s) más)" if len(blocking) > 1 else ""
                problem.set_text(blocking[0] + extra if blocking else "")
                apply.set_sensitive(not blocking and (bool(changes) or new_folder != folder))
                state["folder_stem"] = folder_stem

            def do_apply(_button):
                library = Library(LIBRARY_DB) if LIBRARY_DB.exists() else None
                moves = [(r["path"], folder / r["name"]) for r in rows if r["name"] and r["name"] != r["path"].name]
                try:
                    new_folder = rename_series(folder, state["folder_stem"], moves, RENAME_LOG, library)
                except (OSError, ValueError) as error:
                    problem.set_text(f"No se pudo renombrar (no se ha cambiado nada): {error}")
                    return
                self.settings.pattern = folder_pattern.get_text()
                self.settings.save()
                if self.source_file is not None and folder in self.source_file.parents:
                    renamed = dict(moves).get(self.source_file, self.source_file)
                    self.source_file = new_folder / renamed.name
                self.status.set_text(f"Carpeta renombrada a «{new_folder.name}» y {len(moves)} archivo(s) renumerados.")
                self._update_normalize()
                window.close()

            for entry in (*entries.values(), folder_pattern, *(r["entry"] for r in rows)):
                entry.connect("changed", refresh)
            for r in rows:
                r["include"].connect("toggled", refresh)
            flag.connect("notify::selected", refresh)
            cancel.connect("clicked", lambda _b: window.close())
            apply.connect("clicked", do_apply)
            self.series_normalizer = {"window": window, "entries": entries, "flag": flag, "rows": rows, "result": result,
                                      "summary": summary, "problem": problem, "apply": apply,
                                      "folder_pattern": folder_pattern}   # para las pruebas
            refresh()
            window.present()
            for entry in entries.values():   # sin texto resaltado al abrir
                entry.select_region(0, 0)
            entries["contenido"].grab_focus()

        # ---- Metadatos (ComicInfo.xml) de una carpeta o de un archivo ----------------------------
        def _choose_metadata_folder(self, _button):
            Gtk.FileDialog(title="Carpeta con los cómics").select_folder(self, None, self._metadata_folder_chosen)

        def _metadata_folder_chosen(self, dialog, result):
            try:
                folder = Path(dialog.select_folder_finish(result).get_path())
            except GLib.Error:
                return
            files = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in COMIC_EXTENSIONS),
                           key=lambda p: natural_key(p.name))
            if not files:
                self.status.set_text(f"No hay archivos de cómic directamente en {folder.name}.")
                return
            self._start_metadata(folder, files)

        def _metadata_file(self, _button):
            target = self._normalize_target()
            if target is not None:
                self._start_metadata(target, [target])

        def _start_metadata(self, where: Path, files: list[Path]):
            self.status.set_text(f"Leyendo los metadatos de {len(files)} archivo(s)…")

            def read():   # en otro hilo: un RAR se lee lanzando `unrar`
                infos = []
                for path in files:
                    try:
                        infos.append((read_info(path), ""))
                    except MetadataError as error:
                        infos.append((None, str(error)))
                later(self._metadata_loaded, where, files, infos)
            Thread(target=read, daemon=True).start()

        def _metadata_loaded(self, where: Path, files: list[Path], infos: list):
            self.status.set_text(f"Metadatos leídos de {len(files)} archivo(s).")
            gcd = self._gcd()
            info = None
            if gcd is not None and self.selected is not None and self.selected.series_id:
                info = gcd.series_info(self.selected.series_id)
            title, _number, publisher, _year = self._fields()
            values = merge_values(parse_name(where.stem if where.is_file() else where.name),
                                  series_values(info) if info is not None else None, title)
            self._open_metadata_dialog(where, files, infos, values, publisher, info)

        def _open_metadata_dialog(self, where: Path, files: list[Path], infos: list, values: Values, publisher: str,
                                  gcd_info):
            good = [i for i, _error in infos if i is not None]
            texts, baseline = initial_form(good, suggest_fields(values, publisher, gcd_info))
            window = Gtk.Window(title="Metadatos", transient_for=self, modal=True, default_width=960, default_height=700)
            outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12,
                            margin_start=14, margin_end=14)
            window.set_child(outer)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)   # todo lo que puede crecer va aquí dentro,
            content = Gtk.ScrolledWindow(vexpand=True, margin_end=4)         # con desplazamiento propio: los botones de
            content.set_child(box)                                          # abajo siempre quedan a la vista
            outer.append(content)
            head = Gtk.Label(xalign=0, wrap=True)
            head.set_markup(f"<b>{'Carpeta' if where.is_dir() else 'Archivo'}:</b> {GLib.markup_escape_text(str(where))}"
                            f"  ({len(files)} archivo{'s' if len(files) != 1 else ''})")
            box.append(head)
            original = Gtk.Label(xalign=0, wrap=True, label=(
                "Los metadatos se escriben en los propios archivos, no en copias (antes se verifica una copia de cada "
                "uno); cada lote se puede deshacer desde Ajustes."))
            original.add_css_class("dim-label")
            box.append(original)

            labels = {"Series": ("Serie", "nombre de la serie"), "Volume": ("Volumen", "8"),
                      "Publisher": ("Editorial", "Panini, Planeta…"), "Imprint": ("Sello", "el impreso en el ejemplar"),
                      "Year": ("Año", "2000"), "Count": ("Total de números", "los que tiene la serie"),
                      "LanguageISO": ("Idioma", "es, en…"), "Web": ("Web", "ficha de GCD u otra"),
                      "Notes": ("Notas", "años del contenido original…")}
            layout = (("Series", "Volume"), ("Publisher", "Imprint"), ("Year", "Count"), ("LanguageISO",), ("Web",),
                      ("Notes",))
            grid = Gtk.Grid(column_spacing=10, row_spacing=6)
            entries: dict[str, Gtk.Entry] = {}
            for row, keys in enumerate(layout):
                for index, key in enumerate(keys):
                    label, hint = labels[key]
                    value, absent = common_value(good, key)
                    varied = not value and not absent
                    entry = Gtk.Entry(text=texts[key], hexpand=True, placeholder_text=(
                        "(distinto en cada archivo: se deja como está)" if varied else hint))
                    entries[key] = entry
                    grid.attach(Gtk.Label(label=label, xalign=0), index * 2, row, 1, 1)
                    span = 3 if len(keys) == 1 and key in ("Web", "Notes") else 1
                    grid.attach(entry, index * 2 + 1, row, span, 1)
            box.append(grid)
            note = Gtk.Label(xalign=0, wrap=True, label=(
                "Se rellena con lo que ya tienen los archivos y, en lo demás, con la serie de GCD y el nombre. Un campo "
                "vacío no se toca; si quitas un valor que todos tenían, se borra. Revisa lo que viene de GCD."))
            note.add_css_class("dim-label")
            box.append(note)

            box.append(Gtk.Label(label="Créditos (se aplican a todos los archivos del lote):", xalign=0))
            credit_labels = {"Writer": ("Guion", "quien escribe"), "Penciller": ("Lápiz", "quien dibuja"),
                             "Inker": ("Tinta", "quien entinta"), "Colorist": ("Color", "quien colorea"),
                             "Letterer": ("Rotulación", "quien rotula"), "CoverArtist": ("Portada", "quien dibuja la portada")}
            credit_layout = (("Writer", "Penciller"), ("Inker", "Colorist"), ("Letterer", "CoverArtist"))
            credit_grid = Gtk.Grid(column_spacing=10, row_spacing=6)
            for row, keys in enumerate(credit_layout):
                for index, key in enumerate(keys):
                    label, hint = credit_labels[key]
                    value, absent = common_value(good, key)
                    varied = not value and not absent
                    entry = Gtk.Entry(text=texts[key], hexpand=True, placeholder_text=(
                        "(distinto en cada archivo: se deja como está)" if varied else hint))
                    entries[key] = entry
                    credit_grid.attach(Gtk.Label(label=label, xalign=0), index * 2, row, 1, 1)
                    credit_grid.attach(entry, index * 2 + 1, row, 1, 1)
            box.append(credit_grid)

            box.append(Gtk.Label(label="Categoría (la eliges tú; se guarda en las etiquetas):", xalign=0))
            radios = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4, column_spacing=12,
                                 row_spacing=4, homogeneous=False)
            first, wanted = None, initial_category(good)
            options = {}
            for name in ("", *CATEGORIES):
                radio = Gtk.CheckButton(label=name or "(no cambiar)", active=(name == wanted))
                if first is None:
                    first = radio
                else:
                    radio.set_group(first)
                options[name] = radio
                radios.append(radio)
            box.append(radios)

            listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            rows = []
            for path, (info, error) in zip(files, infos, strict=True):
                number = detect_number(path.stem)[0] or (info or {}).get("Number", "")
                line = Gtk.Box(spacing=8, margin_top=3, margin_bottom=3, margin_start=6, margin_end=6)
                include = Gtk.CheckButton(active=info is not None, sensitive=info is not None,
                                          tooltip_text="Escribir los metadatos de este archivo")
                name = Gtk.Label(label=path.name, xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.MIDDLE,
                                 width_chars=26, max_width_chars=40, tooltip_text=error or str(path))
                number_entry = Gtk.Entry(text=number, width_chars=5, placeholder_text="Nº",
                                         tooltip_text="Número de ejemplar (se toma del nombre del archivo)")
                title_entry = Gtk.Entry(text=(info or {}).get("Title", ""), width_chars=22, hexpand=True,
                                        placeholder_text="Título del ejemplar (opcional)")
                state_label = Gtk.Label(xalign=0, width_chars=18, ellipsize=Pango.EllipsizeMode.END, tooltip_text=error)
                for widget in (include, name, number_entry, title_entry, state_label):
                    line.append(widget)
                listing.append(line)
                rows.append({"path": path, "info": info, "error": error, "include": include, "number": number_entry,
                             "title": title_entry, "state": state_label, "changes": None})
            scroll = Gtk.ScrolledWindow(min_content_height=140, max_content_height=320, propagate_natural_height=True)
            scroll.set_child(listing)
            box.append(scroll)
            summary = Gtk.Label(xalign=0, wrap=True)
            problem = Gtk.Label(xalign=0, wrap=True)
            problem.add_css_class("error")
            buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
            cancel = icon_button(STOP_ICON, "Cancelar")
            apply = icon_button(("emblem-ok-symbolic", "object-select-symbolic"), "Escribir metadatos")
            apply.add_css_class("suggested-action")
            for widget in (cancel, apply):
                buttons.append(widget)
            for widget in (summary, problem, buttons):   # fuera del área que se desplaza: siempre a la vista
                outer.append(widget)
            state = {"busy": False}

            def chosen_category() -> str:
                return next((name for name, radio in options.items() if radio.get_active()), "")

            def refresh(*_args):
                if state["busy"]:
                    return
                series = series_changes({key: entry.get_text() for key, entry in entries.items()}, baseline)
                blocking = ""
                try:
                    build_xml(None, series)   # valida números y fechas antes de tocar nada
                except MetadataError as error:
                    blocking = str(error)
                category = chosen_category()
                pending = same = 0
                for r in rows:
                    r["changes"] = None
                    if r["error"]:
                        r["state"].set_text("no se puede leer")
                    elif not r["include"].get_active():
                        r["state"].set_text("sin tocar")
                    elif blocking:
                        r["state"].set_text("—")
                    else:
                        changes = file_changes(series, category, r["number"].get_text(), r["title"].get_text(), r["info"])
                        if differs(r["info"], changes):
                            r["changes"] = changes
                            r["state"].set_text("se modifica" if r["info"] else "se crea")
                            pending += 1
                        else:
                            r["state"].set_text("ya está igual")
                            same += 1
                skipped = sum(1 for r in rows if not r["include"].get_active() or r["error"])
                summary.set_text(f"{pending} archivo(s) se modifican · {same} ya están igual · {skipped} sin tocar")
                problem.set_text(blocking)
                apply.set_sensitive(bool(pending) and not blocking)

            def finished(result):
                state["busy"] = False
                self._refresh_series()
                if self.source_file in result.written:
                    self._refresh_meta()
                self.status.set_text(
                    f"Metadatos escritos en {len(result.written)} archivo(s)"
                    + (f"; {len(result.unchanged)} ya estaban igual" if result.unchanged else "")
                    + (f". {len(result.failed)} fallaron: " + "; ".join(f"{p.name}: {e}" for p, e in result.failed[:3])
                       if result.failed else "."))
                if result.failed and not result.written:
                    problem.set_text("No se ha escrito nada: " + "; ".join(f"{p.name}: {e}" for p, e in result.failed[:3]))
                    for widget in (cancel, apply):
                        widget.set_sensitive(True)
                    return
                window.close()

            def do_apply(_button):
                items = [(r["path"], r["changes"]) for r in rows if r["changes"]]
                state["busy"] = True
                for widget in (cancel, apply):
                    widget.set_sensitive(False)
                library = Library(LIBRARY_DB) if LIBRARY_DB.exists() else None

                def progress(done, total):
                    later(summary.set_text, f"Escribiendo… {done}/{total}")

                def run():
                    later(finished, write_batch(items, METADATA_LOG, library, progress))
                Thread(target=run, daemon=True).start()

            for entry in (*entries.values(), *(r["number"] for r in rows), *(r["title"] for r in rows)):
                entry.connect("changed", refresh)
            for radio in options.values():
                radio.connect("toggled", refresh)
            for r in rows:
                r["include"].connect("toggled", refresh)
            cancel.connect("clicked", lambda _b: window.close())
            apply.connect("clicked", do_apply)
            self.metadata_dialog = {"window": window, "entries": entries, "options": options, "rows": rows,
                                    "summary": summary, "problem": problem, "apply": apply}   # para las pruebas
            refresh()
            window.present()
            entries["Series"].grab_focus()

        def _undo_metadata(self, _button):
            library = Library(LIBRARY_DB) if LIBRARY_DB.exists() else None
            self.metadata_undo_button.set_sensitive(False)
            self.metadata_undo_info.set_text("Deshaciendo…")

            def run():
                try:
                    later(self._metadata_undone, undo_metadata(METADATA_LOG, library), None)
                except (OSError, LookupError, ValueError) as error:
                    later(self._metadata_undone, None, error)
            Thread(target=run, daemon=True).start()

        def _metadata_undone(self, result, error):
            self.metadata_undo_button.set_sensitive(True)
            self._refresh_series()
            self._refresh_meta()
            if error is not None:
                self.metadata_undo_info.set_text(f"No se pudo deshacer: {error}")
                return
            text = f"Deshecho el último lote: {len(result.restored)} archivo(s) restaurados."
            if result.skipped:
                text += f" {len(result.skipped)} omitidos: " + "; ".join(f"{p.name} ({why})" for p, why in result.skipped[:3])
            self.metadata_undo_info.set_text(text)

        def _undo_rename(self, _button):
            library = Library(LIBRARY_DB) if LIBRARY_DB.exists() else None
            try:
                pairs = undo_last(RENAME_LOG, library)
            except (OSError, LookupError, ValueError) as error:
                self.undo_info.set_text(f"No se pudo deshacer: {error}")
                return
            for current, original in pairs:
                if self.source_file == current:
                    self.source_file = original
            first, last = pairs[0], pairs[-1]
            self.undo_info.set_text(f"Deshecho: {first[0].name} → {first[1].name}" if len(pairs) == 1 else
                                    f"Deshecho un lote de {len(pairs)} renombrado(s), el último: "
                                    f"{last[0].name} → {last[1].name}")
            self._update_normalize()

        # ---- Asistente de IA: terminal embebido con la CLI del usuario, en el panel --------------
        def _ask_ai(self, _button):
            if self.image is None:
                return
            if not vte_available():
                self.status.set_text("Falta el terminal embebido: instala el paquete gir1.2-vte-3.91.")
                return
            work = Path(GLib.get_user_cache_dir()) / "comic-identify" / "ai"
            try:
                prepare_workspace(self.image, work)
                image_name = next(work.glob("portada.*")).name
                argv = build_argv(self.settings.assistant, build_prompt(image_name, self.settings.prompt))
            except (OSError, ValueError) as error:
                self.status.set_text(f"No se pudo preparar el asistente: {error}")
                return
            self._open_assistant(work, argv)

        def _open_assistant(self, work: Path, argv: list[str]):
            gi.require_version("Vte", "3.91")
            from gi.repository import Vte
            self._drop_assistant()   # una sola sesión a la vez
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            self.assistant_note = Gtk.Label(xalign=0, wrap=True, label=(
                f"Sesión de «{argv[0]}» con tu propia cuenta. Revisa cada permiso que te pida: "
                "esta aplicación no ve tus credenciales."))
            terminal = Vte.Terminal(vexpand=True, hexpand=True)
            font = Pango.FontDescription()
            font.set_family(TERMINAL_FONT)
            font.set_weight(Pango.Weight.NORMAL)
            font.set_size(TERMINAL_FONT_SIZE * Pango.SCALE)
            terminal.set_font(font)
            terminal.set_scrollback_lines(10000)
            terminal.connect("child-exited", lambda _t, _status: self.assistant_note.set_text(
                "La sesión ha terminado. Pulsa × para cerrar el panel."))
            box.append(self.assistant_note)
            box.append(terminal)
            self.preview_stack.add_named(box, "assistant")
            self.assistant_box, self.assistant_terminal = box, terminal
            self._open_preview("Asistente de IA", "", "assistant", ASSISTANT_WIDTH)
            # child_setup y child_setup_data quedan a None; -1 = sin límite de tiempo; sin cancelable.
            terminal.spawn_async(Vte.PtyFlags.DEFAULT, str(work), shell_argv(argv), None, GLib.SpawnFlags.SEARCH_PATH,
                                 None, None, -1, None, self._assistant_spawned)
            terminal.grab_focus()

        def _assistant_spawned(self, _terminal, _pid, error, *_data):
            if error is not None:
                self.status.set_text(f"No se pudo lanzar el asistente: {error.message}")
                self._close_preview(None)

        def _drop_assistant(self):
            """Cierra la sesión (al destruir el terminal, el proceso recibe SIGHUP)."""
            if self.assistant_box is not None:
                self.preview_stack.remove(self.assistant_box)
                self.assistant_box = self.assistant_terminal = None
            self.assistant_back.set_visible(False)

        # ---- Panel de la ficha: web de GCD (WebKit) o ficha nativa de ComicVine ---------------
        def _preview_panel(self):
            self.preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, visible=False)
            self.preview.set_size_request(PREVIEW_WIDTH, -1)
            header = Gtk.Box(spacing=8)
            self.preview_title = Gtk.Label(xalign=0, hexpand=True)
            self.assistant_back = icon_button(("go-previous-symbolic",), "Volver al asistente", visible=False)
            self.assistant_back.connect("clicked", lambda _b: self._open_preview(
                "Asistente de IA", "", "assistant", ASSISTANT_WIDTH))
            self.preview_link = Gtk.LinkButton(uri=GCD_SITE, label="Abrir en el navegador")
            close = Gtk.Button(icon_name="window-close-symbolic", tooltip_text="Cerrar el panel")
            close.connect("clicked", self._close_preview)
            for widget in (self.preview_title, self.preview_link, self.assistant_back, close):
                header.append(widget)
            self.preview_stack = Gtk.Stack(vexpand=True)
            self.preview_stack.add_named(self._native_view(), "native")
            self.preview.append(header)
            self.preview.append(self.preview_stack)
            return self.preview

        def _native_view(self):
            """Ficha propia para ComicVine: su web va cargada de publicidad, la API da lo necesario."""
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            grid = Gtk.Grid(column_spacing=14, row_spacing=6)
            self.native_values = {}
            for row, (key, label) in enumerate((("name", "Nombre:"), ("year", "Año:"), ("issue", "Issue:"))):
                caption = Gtk.Label(xalign=0, yalign=0)
                caption.set_markup(f"<big><b>{label}</b></big>")
                value = Gtk.Label(xalign=0, wrap=True, hexpand=True)
                grid.attach(caption, 0, row, 1, 1)
                grid.attach(value, 1, row, 1, 1)
                self.native_values[key] = value
            self.native_picture = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.CONTAIN, vexpand=True)
            attribution = Gtk.LinkButton(uri="https://comicvine.gamespot.com/", halign=Gtk.Align.START,
                                         label="Datos e imagen de Comic Vine")
            for widget in (grid, self.native_picture, attribution):
                box.append(widget)
            return box

        def _row_selected(self, _box, row):
            if row is None or row.get_index() >= len(self.candidates):
                self.selected = None
                self._update_normalize()
                return
            candidate = self.candidates[row.get_index()]
            self.selected = candidate
            self._update_normalize()
            if candidate.source == "ComicVine":
                self._show_native(candidate)
            elif candidate.source == "GCD" and candidate.url.startswith(GCD_SITE):
                if webkit_available():
                    self._show_web(candidate.url)
                else:   # sin WebKit no hay panel para la web de GCD: se abre en el navegador
                    Gtk.UriLauncher.new(candidate.url).launch(self, None, lambda *_: None)

        def _open_preview(self, title: str, url: str, page: str, width: int = PREVIEW_WIDTH):
            if not self.preview.get_visible():   # la ventana crece para no aplastar la lista
                self.set_default_size(self.get_width() + width, self.get_height())
                self.preview.set_visible(True)
            elif width != self._panel_width:
                self.set_default_size(self.get_width() + width - self._panel_width, self.get_height())
            self._panel_width = width
            self.preview.set_size_request(width, -1)
            self.preview_title.set_text(title)
            self.preview_link.set_uri(url or GCD_SITE)
            self.preview_link.set_visible(bool(url))
            self.preview_stack.set_visible_child_name(page)
            self.assistant_back.set_visible(self.assistant_box is not None and page != "assistant")

        def _show_web(self, url: str):
            if self.webview is None:
                gi.require_version("WebKit", "6.0")
                from gi.repository import WebKit
                data, cache = (Path(base()) / "comic-identify" / "webkit"
                               for base in (GLib.get_user_data_dir, GLib.get_user_cache_dir))
                data.mkdir(parents=True, exist_ok=True)
                cache.mkdir(parents=True, exist_ok=True)
                # Sesión propia y persistente (no la de tu navegador): guarda la cookie de Cloudflare
                # y evita repetir su comprobación en cada ficha.
                session = WebKit.NetworkSession.new(str(data), str(cache))
                session.get_website_data_manager().set_favicons_enabled(True)   # desactivados por defecto
                self.webview = WebKit.WebView(network_session=session, vexpand=True)
                self.webview.connect("notify::favicon", self._favicon_changed)
                self.preview_stack.add_named(self.webview, "web")
            self._open_preview("Ficha de Grand Comics Database", url, "web")
            self.webview.load_uri(url)

        def _favicon_changed(self, webview, _param):
            """comics.org bloquea la descarga directa de su icono; el motor del panel sí lo recibe al mostrar una ficha."""
            texture = webview.get_favicon()
            if texture is None or GCD_HOST not in (webview.get_uri() or ""):
                return
            target = self.icon_dir / f"{GCD_HOST}.png"
            if not target.exists():
                self.icon_dir.mkdir(parents=True, exist_ok=True)
                texture.save_to_png(str(target))
                (self.icon_dir / f"{GCD_HOST}.none").unlink(missing_ok=True)
                self._icon_ready(GCD_HOST, target)

        def _show_native(self, candidate: Candidate):
            name = candidate.series or candidate.title
            if candidate.issue_name:
                name += f" — {candidate.issue_name}"
            shown = {"name": name, "year": candidate.year or "—",
                     "issue": f"#{candidate.number}" if candidate.number else "—"}
            for key, text in shown.items():
                self.native_values[key].set_markup(f"<big>{GLib.markup_escape_text(text)}</big>")
            self._set_picture(candidate.cover)   # la miniatura ya descargada, mientras llega la grande
            self._open_preview("Ficha de ComicVine", candidate.url, "native")
            self._native_url = candidate.image_url
            if candidate.image_url and candidate.image_url in self._big_covers:
                self._set_picture(self._big_covers[candidate.image_url])
            elif candidate.image_url and self.settings.api_key.strip():
                client = ComicVineClient(self.settings.api_key.strip())
                Thread(target=self._download_big, args=(client, candidate.image_url), daemon=True).start()

        def _download_big(self, client, url: str):
            try:
                data = client.download(url)
            except ComicVineError:
                return   # se queda la miniatura
            later(self._big_ready, url, data)

        def _big_ready(self, url: str, data: bytes):
            self._big_covers[url] = data
            if url == self._native_url:   # solo si sigue seleccionada esa sugerencia
                self._set_picture(data)

        def _set_picture(self, data: bytes | None):
            if not data:
                self.native_picture.set_paintable(None)
                return
            try:
                self.native_picture.set_paintable(Gdk.Texture.new_from_bytes(GLib.Bytes.new(data)))
            except GLib.Error:
                self.native_picture.set_paintable(None)

        def _close_preview(self, _button):
            if self.preview.get_visible():
                self.set_default_size(max(self.get_width() - self._panel_width, WINDOW_WIDTH), self.get_height())
                self.preview.set_visible(False)
            self._drop_assistant()
            if self.webview is not None:   # libera los procesos de WebKit
                self.preview_stack.remove(self.webview)
                self.webview = None
            self.results.unselect_all()

        @staticmethod
        def _row(candidate: Candidate):
            row = Gtk.Box(spacing=12, margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
            thumb = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.CONTAIN)
            thumb.set_size_request(70, 105)
            thumb.set_visible(bool(candidate.cover))   # GCD no tiene imagen: no reservar el hueco
            if candidate.cover:
                try:
                    thumb.set_paintable(Gdk.Texture.new_from_bytes(GLib.Bytes.new(candidate.cover)))
                except GLib.Error:
                    pass
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True, valign=Gtk.Align.CENTER)
            title = Gtk.Label(xalign=0, wrap=True)
            title.set_markup(f"<b>{GLib.markup_escape_text(candidate.title)}</b>  "
                             f"<small>{candidate.source}</small>")
            text.append(title)
            if candidate.subtitle:
                text.append(Gtk.Label(label=candidate.subtitle, xalign=0, wrap=True))
            if candidate.similarity is not None:
                verdict = "Coincidencia probable" if candidate.is_match else "Poco parecida"
                score = Gtk.Label(label=f"{verdict} · {candidate.similarity:.0%} de parecido", xalign=0)
                score.add_css_class("success" if candidate.is_match else "dim-label")
                text.append(score)
            elif candidate.source == "GCD":
                how = "Coincide el código de barras" if candidate.exact else "Por título; portada sin comparar"
                score = Gtk.Label(label=how, xalign=0)
                score.add_css_class("success" if candidate.exact else "dim-label")
                text.append(score)
            row.append(thumb)
            row.append(text)
            if candidate.path:
                open_folder = icon_button(("folder-open-symbolic",), "Abrir carpeta", valign=Gtk.Align.CENTER)
                open_folder.connect("clicked", lambda _b, p=candidate.path: Gtk.FileLauncher.new(
                    Gio.File.new_for_path(str(p))).open_containing_folder(None, None, lambda *_: None))
                row.append(open_folder)
            return row

        # ---- Mi colección ------------------------------------------------------------------
        def _library_page(self):
            page = self._box()
            controls = Gtk.Box(spacing=8)
            add = icon_button(("folder-new-symbolic", "list-add-symbolic"), "Añadir carpeta…")
            add.connect("clicked", self._add_folder)
            self.index_button = icon_button(INDEX_ICON, "Indexar / actualizar")
            self.index_button.connect("clicked", self._toggle_index)
            controls.append(add)
            controls.append(self.index_button)
            self.folders = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            scroll = Gtk.ScrolledWindow(min_content_height=60, max_content_height=130, propagate_natural_height=True)
            scroll.set_child(self.folders)
            self.index_progress = Gtk.ProgressBar(show_text=True)
            self.index_info = Gtk.Label(xalign=0, wrap=True)

            title = Gtk.Label(xalign=0, label="Series de la colección (por carpeta y metadatos):")
            title.add_css_class("heading")
            self.series_filter = Gtk.DropDown.new_from_strings(SERIES_FILTERS)
            self.series_filter.connect("notify::selected", self._show_series)
            self.series_search = Gtk.SearchEntry(placeholder_text="Buscar una serie…", hexpand=True)
            self.series_search.connect("search-changed", self._show_series)
            refresh = icon_button(("view-refresh-symbolic",), "Actualizar lista", tooltip_text=(
                "Vuelve a calcular la lista con lo indexado (indexa antes para leer los metadatos nuevos)"))
            refresh.connect("clicked", lambda _b: self._refresh_series())
            filters = Gtk.Box(spacing=8)
            for widget in (self.series_filter, self.series_search, refresh):
                filters.append(widget)
            self.series_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            series_scroll = Gtk.ScrolledWindow(vexpand=True)
            series_scroll.set_child(self.series_list)
            self.series_info = Gtk.Label(xalign=0, wrap=True)
            self.series_reports = []
            for widget in (controls, scroll, self.index_progress, self.index_info, title, filters, series_scroll,
                           self.series_info):
                page.append(widget)
            return page

        def _about(self, _button):
            about = Gtk.AboutDialog(
                transient_for=self, modal=True, program_name="Comic Identify", version=__version__,
                logo_icon_name="comic-identify", authors=[AUTHOR], copyright=f"© 2026 {AUTHOR}",
                comments=("Identifica un cómic a partir de su portada, normaliza los nombres de archivos y carpetas y "
                          "escribe metadatos ComicInfo.xml."),
                website=REPO_URL, website_label=REPO_URL.removeprefix("https://"),
                license_type=Gtk.License.CUSTOM, license=LICENSE_TEXT, wrap_license=True)
            about.add_credit_section("Datos de terceros", [
                "Grand Comics Database (CC BY-SA 4.0) https://www.comics.org/",
                "Comic Vine https://comicvine.gamespot.com/"])
            about.present()

        def _refresh_series(self):
            """Recalcula las series con lo que hay en el índice y las muestra."""
            self.series_reports = build_series(Library(LIBRARY_DB).series_rows()) if LIBRARY_DB.exists() else []
            self._show_series()

        def _show_series(self, *_args):
            while (row := self.series_list.get_first_child()) is not None:
                self.series_list.remove(row)
            mode, needle = SERIES_FILTERS[self.series_filter.get_selected()], self.series_search.get_text().strip().lower()
            keep = {"Incompletas": lambda r: bool(r.missing), "Todas": lambda r: True,
                    "Sin todos sus metadatos": lambda r: r.tagged < r.files,
                    "Sin total indicado": lambda r: r.count is None}[mode]
            shown = [r for r in self.series_reports if keep(r) and needle in r.name.lower()]
            for report in shown[:SERIES_SHOWN]:
                parts = [f"{len(report.owned)} de {report.count}" if report.count else
                         f"{len(report.owned)} números (total sin indicar)"]
                if report.mixed:
                    parts.append("varias series en la carpeta (números repetidos): sin comprobar")
                if report.starts_at:
                    parts.append(f"empieza en el {report.starts_at}")
                if report.missing:
                    parts.append("faltan " + ranges(report.missing))
                if report.sparse:
                    parts.append("números sueltos: no se buscan huecos sin el total")
                if report.strays:
                    parts.append("fuera de la serie: " + ranges(report.strays) + " (¿de otra serie?)")
                if report.duplicated and not report.mixed:
                    parts.append("repetidos: " + ranges(report.duplicated))
                if report.other:
                    parts.append(f"{report.other} sin número entero")
                parts.append(f"metadatos {report.tagged}/{report.files}")
                if report.category:
                    parts.append(report.category)
                line = Gtk.Box(spacing=8, margin_top=4, margin_bottom=4, margin_start=6, margin_end=6)
                text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
                name = Gtk.Label(xalign=0, wrap=True, tooltip_text=report.folder)
                name.set_markup(f"<b>{GLib.markup_escape_text(report.name)}</b>")
                detail = Gtk.Label(label=" · ".join(parts), xalign=0, wrap=True)
                detail.add_css_class({"completa": "success", "incompleta": "warning"}.get(report.status, "dim-label"))
                text.append(name)
                text.append(detail)
                open_folder = icon_button(("folder-open-symbolic",), "Abrir carpeta", valign=Gtk.Align.CENTER)
                open_folder.connect("clicked", lambda _b, f=report.folder: Gtk.FileLauncher.new(
                    Gio.File.new_for_path(f)).launch(None, None, lambda *_: None))
                line.append(text)
                line.append(open_folder)
                self.series_list.append(line)
            incomplete = sum(1 for r in self.series_reports if r.missing)
            self.series_info.set_text(
                f"{len(self.series_reports)} serie(s) reconocidas, {incomplete} con huecos"
                + (f" · se muestran las primeras {SERIES_SHOWN} de {len(shown)}: afina el filtro" if len(shown) > SERIES_SHOWN
                   else f" · {len(shown)} en la lista")
                + ". Una carpeta suelta sin metadatos ni nombre normalizado no cuenta como serie."
                if self.series_reports else
                "Todavía no hay series: indexa la colección y escribe metadatos o normaliza los nombres de las carpetas.")

        def _refresh_library(self):
            while (row := self.folders.get_first_child()) is not None:
                self.folders.remove(row)
            for folder in self.settings.folders:
                line = Gtk.Box(spacing=8, margin_top=4, margin_bottom=4, margin_start=6, margin_end=6)
                line.append(Gtk.Label(label=folder, xalign=0, hexpand=True))
                remove = icon_button(("list-remove-symbolic",), "Quitar")
                remove.connect("clicked", lambda _b, f=folder: self._remove_folder(f))
                line.append(remove)
                self.folders.append(line)
            total = Library(LIBRARY_DB).count() if LIBRARY_DB.exists() else 0
            self.index_info.set_text(f"{total} portada(s) indexada(s). Las carpetas se recorren "
                                     "con subcarpetas; los archivos ya indexados no se releen.")
            self._refresh_series()

        def _add_folder(self, _button):
            Gtk.FileDialog(title="Carpeta de cómics").select_folder(self, None, self._folder_chosen)

        def _folder_chosen(self, dialog, result):
            try:
                folder = dialog.select_folder_finish(result).get_path()
            except GLib.Error:
                return
            if folder not in self.settings.folders:
                self.settings.folders.append(folder)
                self.settings.save()
                self._refresh_library()

        def _remove_folder(self, folder):
            if self.indexing:   # el índice está en uso: SQLite bloquearía el borrado
                self.index_info.set_text("Espera a que termine la indexación (o cancélala) para quitar carpetas.")
                return
            self.settings.folders.remove(folder)
            self.settings.save()
            if LIBRARY_DB.exists():
                Library(LIBRARY_DB).forget_folder(Path(folder))
            self._refresh_library()

        def _toggle_index(self, _button):
            if self.indexing:
                self.cancel.set()
                return
            if not self.settings.folders:
                self.index_info.set_text("Añade primero alguna carpeta.")
                return
            self.cancel.clear()
            self.indexing = True
            set_icon_button(self.index_button, STOP_ICON, "Cancelar")
            Thread(target=self._index, args=([Path(f) for f in self.settings.folders],), daemon=True).start()

        def _index(self, folders):
            def progress(done, total):
                later(self.index_progress.set_fraction, done / total)
                later(self.index_progress.set_text, f"{done}/{total}")
            try:
                stats = Library(LIBRARY_DB).index(folders, progress, self.cancel)
                message = (f"Nuevas: {stats.indexed} · sin cambios: {stats.unchanged} · "
                           f"ilegibles: {stats.failed} · eliminadas: {stats.removed} · "
                           f"metadatos leídos en archivos ya indexados: {stats.refreshed}")
                if stats.failed_files:
                    shown = stats.failed_files[:5]
                    more = f" (y {stats.failed - len(shown)} más)" if stats.failed > len(shown) else ""
                    message += ("\nIlegibles: " + ", ".join(f"{Path(f).name} ({reason})" for f, reason in shown)
                                + more)
                if stats.unavailable:
                    message += ("\nSin acceso o vacías (su índice se conserva): "
                                + ", ".join(stats.unavailable))
            except Exception as error:  # noqa: BLE001
                message = f"Error al indexar: {error}"
            later(self._index_done, message)

        def _index_done(self, message):
            self.indexing = False
            set_icon_button(self.index_button, INDEX_ICON, "Indexar / actualizar")
            self._refresh_library()
            self.index_info.set_text(self.index_info.get_text() + "\n" + message)

        # ---- Ajustes -----------------------------------------------------------------------
        def _credit(self, host: str, title: str, text: str, url: str):
            """Logo, nombre, qué aporta y enlace de una de las fuentes de datos."""
            row = Gtk.Box(spacing=12)
            row.append(self._icon(host, 32))
            column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
            heading = Gtk.Label(xalign=0)
            heading.set_markup(f"<b>{GLib.markup_escape_text(title)}</b>")
            body = Gtk.Label(label=text, xalign=0, wrap=True)
            link = Gtk.LinkButton(uri=url, label=url.removeprefix("https://").rstrip("/"), halign=Gtk.Align.START)
            for widget in (heading, body, link):
                column.append(widget)
            row.append(column)
            return row

        def _settings_page(self):
            page = self._box()
            about = icon_button(("help-about-symbolic", "dialog-information-symbolic"), "Acerca de…",
                                halign=Gtk.Align.END, tooltip_text="Versión, autor, licencia y datos de terceros")
            about.connect("clicked", self._about)
            page.append(about)   # arriba: la página es larga y así se ve al entrar
            page.append(Gtk.Label(xalign=0, wrap=True, label=(
                "Esta aplicación se apoya en el trabajo de dos comunidades de colaboradores, que son las que "
                "han hecho el trabajo duro:")))
            page.append(self._credit(COMICVINE_HOST, "Comic Vine", (
                "Enciclopedia colaborativa de cómics con una API gratuita. Aporta series, números y portadas, "
                "que la aplicación compara visualmente con la tuya; es más fuerte en ediciones americanas."),
                "https://comicvine.gamespot.com/"))
            page.append(self._credit(GCD_HOST, "Grand Comics Database (GCD)", (
                "Base de datos abierta y colaborativa de cómics de todo el mundo, mantenida por voluntarios. "
                "De ella sale el índice de ediciones en español (España y Latinoamérica): títulos, números, "
                "editoriales y sellos. Datos con licencia CC BY-SA 4.0."), GCD_SITE))
            page.append(Gtk.Separator(margin_top=6, margin_bottom=6))
            page.append(Gtk.Label(label="Clave de la API de ComicVine (gratuita):", xalign=0))
            self.key = Gtk.PasswordEntry(show_peek_icon=True, text=self.settings.api_key)
            save = icon_button(("document-save-symbolic",), "Guardar", halign=Gtk.Align.START)
            save.connect("clicked", self._save_key)
            self.key_info = Gtk.Label(xalign=0)
            for widget in (self.key, save, Gtk.LinkButton(uri=COMICVINE_API_URL, label="Obtener una clave",
                                                          halign=Gtk.Align.START), self.key_info):
                page.append(widget)

            page.append(Gtk.Separator(margin_top=6, margin_bottom=6))
            page.append(Gtk.Label(xalign=0, wrap=True, label=(
                "Grand Comics Database (ediciones en español, sin límites ni conexión). Descarga el volcado "
                "SQLite desde comics.org (requiere cuenta gratuita), descomprímelo e impórtalo aquí una vez.")))
            self.gcd_button = icon_button(("document-open-symbolic", "folder-download-symbolic"),
                                          "Importar volcado de GCD…", halign=Gtk.Align.START)
            self.gcd_button.connect("clicked", self._choose_gcd)
            self.gcd_info = Gtk.Label(xalign=0, wrap=True)
            attribution = Gtk.LinkButton(uri="https://www.comics.org/", halign=Gtk.Align.START,
                                         label="Datos de Grand Comics Database (CC BY-SA 4.0)")
            for widget in (Gtk.LinkButton(uri=GCD_DOWNLOAD_URL, label="Descargar el volcado",
                                          halign=Gtk.Align.START), self.gcd_button, self.gcd_info, attribution):
                page.append(widget)
            self._refresh_gcd()

            page.append(Gtk.Separator(margin_top=6, margin_bottom=6))
            page.append(Gtk.Label(xalign=0, wrap=True, label=(
                "Asistente de IA (botón «Preguntar a la IA»): comando que se abre en un terminal con tu propia "
                "sesión. {prompt} se sustituye por el mensaje. Ejemplos: «claude {prompt}», «codex {prompt}», "
                "«opencode --prompt {prompt}».")))
            self.assistant_entry = Gtk.Entry(text=self.settings.assistant)
            page.append(self.assistant_entry)
            page.append(Gtk.Label(xalign=0, wrap=True, label=(
                "Mensaje que sustituye a {prompt} ({image} es la portada que se le pasa). Se puede cambiar para "
                "pedirle otras cosas o usar otras webs:")))
            self.prompt_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD, top_margin=6, bottom_margin=6, left_margin=8,
                                            right_margin=8)
            self.prompt_view.get_buffer().set_text(self.settings.prompt)
            prompt_scroll = Gtk.ScrolledWindow(min_content_height=130, max_content_height=220,
                                               propagate_natural_height=True, has_frame=True)
            prompt_scroll.set_child(self.prompt_view)
            save_command = icon_button(("document-save-symbolic",), "Guardar comando y mensaje")
            save_command.connect("clicked", self._save_assistant)
            reset_prompt = icon_button(("edit-undo-symbolic", "view-refresh-symbolic"), "Restablecer el mensaje",
                                       tooltip_text="Vuelve al mensaje que trae la aplicación")
            reset_prompt.connect("clicked", lambda _b: self.prompt_view.get_buffer().set_text(PROMPT))
            buttons = Gtk.Box(spacing=8, halign=Gtk.Align.START)
            buttons.append(save_command)
            buttons.append(reset_prompt)
            self.assistant_info = Gtk.Label(xalign=0, wrap=True)
            for widget in (prompt_scroll, buttons, self.assistant_info):
                page.append(widget)

            page.append(Gtk.Separator(margin_top=6, margin_bottom=6))
            page.append(Gtk.Label(xalign=0, wrap=True, label=(
                "Normalización de nombres: cada renombrado queda registrado y se puede deshacer, de uno en uno, "
                "del último al primero.")))
            undo = icon_button(("edit-undo-symbolic", "view-refresh-symbolic"), "Deshacer el último renombrado",
                               halign=Gtk.Align.START)
            undo.connect("clicked", self._undo_rename)
            self.undo_info = Gtk.Label(xalign=0, wrap=True)
            for widget in (undo, self.undo_info):
                page.append(widget)
            page.append(Gtk.Label(xalign=0, wrap=True, label=(
                "Metadatos: cada escritura queda registrada con el ComicInfo.xml anterior. Deshacer revierte el último "
                "lote entero, sin pisar archivos que se hayan modificado o movido después.")))
            self.metadata_undo_button = icon_button(("edit-undo-symbolic", "view-refresh-symbolic"),
                                                    "Deshacer el último lote de metadatos", halign=Gtk.Align.START)
            self.metadata_undo_button.connect("clicked", self._undo_metadata)
            self.metadata_undo_info = Gtk.Label(xalign=0, wrap=True)
            for widget in (self.metadata_undo_button, self.metadata_undo_info):
                page.append(widget)

            page.append(Gtk.Separator(margin_top=6, margin_bottom=6))
            page.append(Gtk.Label(xalign=0, wrap=True, label=(
                "Transferir a GCstar (botón «Transferir a GCstar…»): añade el cómic a una colección de GCstar sin "
                "tocar el resto de su archivo .gcs, con su portada y contraportada junto a él, con la misma "
                "convención de nombres que ya uses. Necesita que la carpeta del cómic esté en «Mi colección», "
                "arriba, para saber dónde ponerlas.")))
            self.gcstar_entry = Gtk.Entry(text=self.settings.gcstar_path, hexpand=True,
                                          placeholder_text="Archivo .gcs de tu colección")
            choose_gcstar = icon_button(("document-open-symbolic", "folder-open-symbolic"), "Elegir archivo .gcs…")
            choose_gcstar.connect("clicked", self._choose_gcstar)
            gcstar_line = Gtk.Box(spacing=8)
            gcstar_line.append(self.gcstar_entry)
            gcstar_line.append(choose_gcstar)
            save_gcstar = icon_button(("document-save-symbolic",), "Guardar", halign=Gtk.Align.START)
            save_gcstar.connect("clicked", self._save_gcstar_path)
            self.gcstar_undo_button = icon_button(("edit-undo-symbolic", "view-refresh-symbolic"),
                                                  "Deshacer la última transferencia a GCstar", halign=Gtk.Align.START)
            self.gcstar_undo_button.connect("clicked", self._undo_gcstar)
            self.gcstar_info = Gtk.Label(xalign=0, wrap=True)
            for widget in (gcstar_line, save_gcstar, self.gcstar_undo_button, self.gcstar_info):
                page.append(widget)
            scroll = Gtk.ScrolledWindow()   # la página es más alta que la ventana
            scroll.set_child(page)
            return scroll

        def _save_assistant(self, _button):
            command = self.assistant_entry.get_text().strip()
            try:
                build_argv(command, "prueba")
            except ValueError as error:
                self.assistant_info.set_text(f"Comando no válido: {error}")
                return
            buffer = self.prompt_view.get_buffer()
            prompt = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False).strip()
            self.settings.assistant, self.settings.prompt = command, prompt or PROMPT
            self.settings.save()
            self.assistant_info.set_text("Comando y mensaje guardados." if prompt else
                                         "Comando guardado; el mensaje estaba vacío y se usa el de la aplicación.")

        def _refresh_gcd(self):
            index = GcdIndex(GCD_DB)
            if index.is_ready():
                series, issues = index.counts()
                self.gcd_info.set_text(f"Índice de GCD: {series} series y {issues} números.")
            elif GCD_DB.exists():
                self.gcd_info.set_text("El índice de GCD es de una versión anterior: vuelve a importar el "
                                       "volcado para actualizarlo (tarda unos segundos).")
            else:
                self.gcd_info.set_text("Todavía no has importado el volcado de GCD.")

        def _choose_gcd(self, _button):
            dump = Gtk.FileFilter(name="Volcado SQLite de GCD")
            for pattern in ("*.db", "*.sqlite", "*.sqlite3"):
                dump.add_pattern(pattern)
            Gtk.FileDialog(title="Volcado de GCD", default_filter=dump).open(self, None, self._gcd_chosen)

        def _gcd_chosen(self, dialog, result):
            try:
                source = Path(dialog.open_finish(result).get_path())
            except GLib.Error:
                return
            self.gcd_button.set_sensitive(False)
            Thread(target=self._import_gcd, args=(source,), daemon=True).start()

        def _import_gcd(self, source: Path):
            try:
                build_index(source, GCD_DB, lambda message: later(self.gcd_info.set_text, message))
            except Exception as error:  # noqa: BLE001 - se muestra al usuario
                later(self.gcd_info.set_text, f"No se pudo importar: {error}")
            else:
                later(self._refresh_gcd)
            later(self.gcd_button.set_sensitive, True)

        def _save_key(self, _button):
            self.settings.api_key = self.key.get_text().strip()
            self.settings.save()
            self.key_info.set_text("Clave guardada.")

        def _choose_gcstar(self, _button):
            gcs_filter = Gtk.FileFilter(name="Colección de GCstar")
            gcs_filter.add_pattern("*.gcs")
            Gtk.FileDialog(title="Archivo .gcs de GCstar", default_filter=gcs_filter).open(self, None,
                                                                                          self._gcstar_path_chosen)

        def _gcstar_path_chosen(self, dialog, result):
            try:
                self.gcstar_entry.set_text(dialog.open_finish(result).get_path())
            except GLib.Error:
                pass  # Selección cancelada.

        def _save_gcstar_path(self, _button):
            self.settings.gcstar_path = self.gcstar_entry.get_text().strip()
            self.settings.save()
            self._update_normalize()
            self.gcstar_info.set_text("Ruta guardada." if self.settings.gcstar_path else
                                      "Ruta guardada (vacía): el botón «Transferir a GCstar…» queda desactivado.")

    class App(Gtk.Application):
        def __init__(self):
            # HANDLES_OPEN: un archivo pasado a una segunda ejecución llega a la ventana ya abierta.
            super().__init__(application_id="com.example.ComicIdentify", flags=Gio.ApplicationFlags.HANDLES_OPEN)

        def _window(self):
            windows = self.get_windows()
            window = windows[0] if windows else Window(self)
            window.present()
            return window

        def do_activate(self):
            self._window()

        def do_open(self, files, _count, _hint):
            path = files[0].get_path() if files else None
            window = self._window()
            if path:
                window._load(Path(path))

    App().run([sys.argv[0]] + ([str(initial_image)] if initial_image is not None else []))
