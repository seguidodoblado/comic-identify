"""Página «Identificar»: carga de la portada, búsqueda y lista de candidatos."""
from pathlib import Path
from threading import Thread

from ..comicinfo import MetadataError, read_info
from ..comicvine import ComicVineClient
from ..covers import (
    COMIC_EXTENSIONS,
    IMAGE_EXTENSIONS,
    cover_to_png,
    extract_cover,
    list_pages,
)
from ..gcd import GcdIndex
from ..i18n import _
from ..identify import (
    CATALOG_SOURCES,
    identify,
    search_gcd,
    search_marvel,
    search_tebeosfera,
)
from ..library import Library
from ..metadata import delete_info
from ..metaform import (
    describe_info,
)
from ..settings import (
    GCD_DB,
    LIBRARY_DB,
    METADATA_LOG,
    TEBEOSFERA_DB,
    UNIVERSOMARVEL_DB,
)
from ..sources import GROUPS, SHOP_GROUPS, SHOPS, SOURCES, search_url, shop_url
from ..tebeosfera import TebeosferaIndex
from ..universomarvel import (
    UniversoMarvelIndex,
)
from .constants import (
    COMICVINE_HOST,
    COVER_WIDTH,
    FALLBACK_ICON,
    INITIAL_STATUS,
    LIVE_DELAY_MS,
    META_MAX_HEIGHT,
)
from .widgets import (
    Gdk,
    GLib,
    Gtk,
    Pango,
    icon_button,
    later,
    pick_icon,
    webkit_available,
)


class IdentifyMixin:
    def _identify_page(self):
        page = self._box()
        controls = self._identify_controls()
        cover = self._identify_cover_column()
        side = self._identify_search_side()
        body = self.body = Gtk.Box(spacing=12, margin_end=12)   # aire entre esto y el panel de la derecha
        body.append(cover)
        body.append(side)
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True, shrink_start_child=False,
                          shrink_end_child=False, resize_end_child=False)
        paned.set_start_child(body)
        paned.set_end_child(self._preview_panel())
        for widget in (controls, self.status, self.search_progress, paned):
            page.append(widget)
        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._dropped)
        page.add_controller(drop)
        return page

    def _identify_controls(self):
        """Barra de botones de arriba: abrir, pegar, IA, normalizar y metadatos."""
        controls = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=7, column_spacing=8,
                               row_spacing=6, homogeneous=False)   # los botones pasan a otra línea si no caben
        open_button = icon_button(("document-open-symbolic", "folder-open-symbolic"), _("Abrir…"), tooltip_text=(
            _("Abre un cómic (CBR, CBZ, CB7) o una imagen de portada; también puedes pegarla o arrastrarla")))
        paste_button = icon_button(("edit-paste-symbolic",), _("Pegar"), tooltip_text=(
            _("Pega una imagen copiada, o un cómic (CBR, CBZ, CB7) o imagen copiados en el gestor de archivos (Ctrl+V)")))
        open_button.connect("clicked", self._choose_image)
        paste_button.connect("clicked", lambda _button: self._paste())
        self.ask_button = icon_button(("utilities-terminal-symbolic", "dialog-question-symbolic"),
                                      _("Preguntar a la IA"), sensitive=False, tooltip_text=(
            _("Abre un terminal con tu propia sesión (Claude Code, OpenCode…) para que identifique la portada")))
        self.ask_button.connect("clicked", self._ask_ai)
        self.normalize_button = icon_button(("document-edit-symbolic",), _("Normalizar nombre…"), sensitive=False,
                                            tooltip_text=(
            _("Renombra el CBR/CBZ con el patrón de Estructura.md (abre un cómic o elige una coincidencia de "
            "«Mi colección» para activarlo). Actúa sobre el archivo original, no sobre una copia.")))
        self.normalize_button.connect("clicked", self._normalize)
        folder_button = icon_button(("folder-symbolic", "folder-open-symbolic"), _("Normalizar carpeta…"),
                                    tooltip_text=(_("Renombra una carpeta-serie y numera los archivos de dentro "
                                                  "(elige antes una serie de GCD para rellenar sus datos)")))
        folder_button.connect("clicked", self._choose_series_folder)
        meta_folder = icon_button(("document-properties-symbolic", "document-edit-symbolic"), _("Metadatos carpeta…"),
                                  tooltip_text=_("Escribe el ComicInfo.xml (serie, editorial, categoría…) en todos los "
                                               "cómics de una carpeta"))
        meta_folder.connect("clicked", self._choose_metadata_folder)
        self.metadata_button = icon_button(("document-properties-symbolic", "document-edit-symbolic"),
                                           _("Metadatos archivo…"), sensitive=False, tooltip_text=(
            _("Escribe el ComicInfo.xml del cómic abierto o de la coincidencia de «Mi colección» elegida, en el archivo "
            "original")))
        self.metadata_button.connect("clicked", self._metadata_file)
        for widget in (open_button, paste_button, self.ask_button, self.normalize_button, folder_button,
                       self.metadata_button, meta_folder):
            controls.append(widget)
        return controls

    def _identify_cover_column(self):
        """Columna izquierda: portada, sus acciones, navegación de páginas y panel del ComicInfo.xml."""
        self.status = Gtk.Label(label=INITIAL_STATUS, xalign=0, wrap=True)   # sin ajuste, un estado largo obliga a ensanchar la ventana
        self.search_progress = Gtk.ProgressBar(show_text=False, visible=False)   # solo mientras se consulta a
        self._search_pulse_id = 0
        self._progress_jobs: set[str] = set()   # quién la mantiene encendida: ComicVine, Universo Marvel…                                              # ComicVine: tarda varios segundos
        self.picture = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.CONTAIN, vexpand=True)
        self.picture.set_size_request(300, 190)   # se encoge sola si falta altura: debajo van los botones, las flechas y los metadatos
        self.cover_placeholder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                                         halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.cover_placeholder.add_css_class("dim-label")
        self.cover_placeholder.append(Gtk.Image(icon_name="comic-identify", pixel_size=96))
        self.cover_placeholder.append(Gtk.Label(label=_("Ningún cómic abierto")))
        self.cover_overlay = Gtk.Overlay(vexpand=True)   # muestra un icono genérico mientras no hay portada
        self.cover_overlay.set_child(self.picture)
        self.cover_overlay.add_overlay(self.cover_placeholder)

        self.pages: list[str] = []      # páginas del cómic abierto; la primera es la portada
        self.page_index = self._page_request = 0
        self._page_cache: dict[int, bytes] = {}
        self.page_buttons = []
        for icon, tip, target in (("go-first-symbolic", _("Primera página (la portada)"), lambda: 0),
                                  ("go-previous-symbolic", _("Página anterior"), lambda: self.page_index - 1),
                                  ("go-next-symbolic", _("Página siguiente"), lambda: self.page_index + 1),
                                  ("go-last-symbolic", _("Última página (la contraportada)"), lambda: len(self.pages) - 1)):
            button = Gtk.Button(icon_name=pick_icon(icon), tooltip_text=tip)
            button.connect("clicked", lambda _b, t=target: self._go_page(t()))
            self.page_buttons.append(button)
        self.page_label = Gtk.Label(width_chars=17)
        self.page_nav = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER, visible=False)
        for widget in (*self.page_buttons[:2], self.page_label, *self.page_buttons[2:]):
            self.page_nav.append(widget)
        self.export_cover_button = icon_button(("image-x-generic-symbolic", "insert-image-symbolic"),
                                                _("Extraer portada…"), sensitive=False, halign=Gtk.Align.CENTER,
                                                tooltip_text=(
            _("Guarda la portada como imagen junto al archivo, con su mismo nombre (para usarla, por ejemplo, "
            "de portada en GCstar); no la recodifica, así que conserva su calidad original")))
        self.export_cover_button.connect("clicked", self._export_cover)
        self.gcstar_button = icon_button(("send-to-symbolic", "document-send-symbolic"), _("Transferir a GCstar…"),
                                         sensitive=False, halign=Gtk.Align.CENTER, tooltip_text=(
            _("Añade el cómic a tu colección de GCstar (créditos, editorial, año, páginas, portada y "
            "contraportada) sin tocar el resto de su archivo .gcs; configúralo en Ajustes")))
        self.gcstar_button.connect("clicked", self._open_gcstar_transfer)
        cover_actions = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        cover_actions.append(self.export_cover_button)
        cover_actions.append(self.gcstar_button)
        click = Gtk.GestureClick()   # doble clic: la página a la vista, en una ventana grande
        click.connect("pressed", lambda _g, presses, _x, _y: presses == 2 and self._open_viewer())
        self.picture.add_controller(click)
        self.meta_heading = Gtk.Label(label=_("ComicInfo.xml"), xalign=0)
        self.meta_heading.add_css_class("heading")
        self.delete_meta_button = icon_button(("edit-delete-symbolic", "user-trash-symbolic"), _("Eliminar datos"),
                                              sensitive=False, tooltip_text=(
            _("Quita el ComicInfo.xml entero de este archivo (el propio archivo no se toca); se puede deshacer con "
            "«Deshacer» en Ajustes, como cualquier otra escritura de metadatos")))
        self.delete_meta_button.add_css_class("destructive-action")
        self.delete_meta_button.connect("clicked", self._delete_meta)
        meta_header = Gtk.Box(spacing=6)
        meta_header.append(self.meta_heading)
        meta_header.append(self.delete_meta_button)
        self.meta_grid = Gtk.Grid(column_spacing=10, row_spacing=2, margin_end=8)
        meta_scroll = Gtk.ScrolledWindow(min_content_height=70, max_content_height=META_MAX_HEIGHT,
                                         propagate_natural_height=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        meta_scroll.set_child(self.meta_grid)
        self.meta_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, visible=False, margin_top=4)
        self.meta_box.append(meta_header)
        self.meta_box.append(meta_scroll)
        cover = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        cover.set_size_request(COVER_WIDTH, -1)   # ancho fijo: una portada es vertical y solo gana con el alto
        for widget in (self.cover_overlay, cover_actions, self.page_nav, self.meta_box):   # la portada se queda con el alto que sobra
            cover.append(widget)
        return cover

    def _identify_search_side(self):
        """Columna central: búsqueda, menús de webs y tiendas, y resultados."""
        refine = self._identify_search_fields()
        scroll = self._identify_results()
        web_menu = self._identify_web_menu()
        buy_menu = self._identify_buy_menu()
        sources = Gtk.Box(spacing=12)
        sources.append(web_menu)
        sources.append(buy_menu)
        sources.append(self.web_extra)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        side.append(refine)
        side.append(sources)
        side.append(scroll)
        return side

    def _identify_search_fields(self):
        """Campos de búsqueda (título, número, editorial, año) y sus botones."""
        self.query = Gtk.Entry(placeholder_text=_("Título a buscar"), hexpand=True)
        self.number = Gtk.Entry(placeholder_text=_("Nº"), width_chars=6)
        self.publisher = Gtk.Entry(placeholder_text=_("Editorial / distribuidor (Panini, Planeta, Forum…)"),
                                   hexpand=True)
        self.year = Gtk.Entry(placeholder_text=_("Año"), width_chars=6)
        content = Gtk.Box(spacing=6)
        content.append(self._icon(COMICVINE_HOST, 16))
        content.append(Gtk.Label(label=_("Buscar en ComicVine")))
        search = Gtk.Button(child=content, tooltip_text=(
            _("Busca en ComicVine con estos datos (necesita su clave gratuita, en Ajustes)")))
        search.connect("clicked", lambda _button: self._search(*self._fields()))
        for entry in (self.query, self.publisher):
            entry.connect("activate", lambda _e: search.emit("clicked"))
        for entry in (self.query, self.number, self.publisher, self.year):
            entry.connect("changed", self._typed)
        refine = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        clear = icon_button(("edit-clear-all-symbolic", "edit-clear-symbolic"), _("Limpiar"),
                            tooltip_text=_("Quita todos los datos: campos, resultados, portada y panel"))
        clear.add_css_class("suggested-action")   # verde en este tema
        clear.connect("clicked", self._reset)
        for widgets in ((self.query, self.number, search), (self.publisher, self.year, clear)):
            line = Gtk.Box(spacing=8)
            for widget in widgets:
                line.append(widget)
            refine.append(line)
        return refine

    def _identify_results(self):
        """Lista de resultados con su desplazamiento."""
        self.results = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.results.connect("row-selected", self._row_selected)
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll.set_child(self.results)
        return scroll

    def _identify_web_menu(self):
        """Menú «Buscar en otras webs» y la casilla de editorial y año."""
        self.web_extra = Gtk.CheckButton(label=_("Incluir también la editorial y el año"), active=True, tooltip_text=(
            _("Añade la editorial y el año a la búsqueda de las webs y de las tiendas; si no salen resultados, desmárcalo")))
        menu_content = Gtk.Box(spacing=6)
        menu_content.append(Gtk.Image(icon_name=pick_icon("web-browser-symbolic", FALLBACK_ICON)))
        menu_content.append(Gtk.Label(label=_("Buscar en otras webs")))
        menu_content.append(Gtk.Image(icon_name=pick_icon("pan-down-symbolic")))
        popover = Gtk.Popover()
        entries = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6,
                          margin_start=6, margin_end=6)
        entries.append(Gtk.Label(label=_("Se abre en tu navegador"), xalign=0, margin_start=6, margin_bottom=4,
                                 css_classes=["dim-label"]))
        all_content = Gtk.Box(spacing=8)
        all_content.append(Gtk.Image(icon_name=pick_icon("edit-select-all-symbolic", FALLBACK_ICON), pixel_size=16))
        all_content.append(Gtk.Label(label=_("Todas"), xalign=0))
        all_button = Gtk.Button(child=all_content, has_frame=False,
                                tooltip_text=_("Busca en las {SOURCES_count} webs, cada una en su pestaña").format(SOURCES_count=len(SOURCES)))
        all_button.connect("clicked", lambda _b: (popover.popdown(), self._open_all_sources()))
        entries.append(all_button)
        entries.append(Gtk.Separator(margin_top=2, margin_bottom=2))
        for category in GROUPS:
            entries.append(Gtk.Label(label=category, xalign=0, margin_start=6, margin_top=6,
                                     css_classes=["heading"]))
            for source in (s for s in SOURCES if s.category == category):
                content = Gtk.Box(spacing=8)
                content.append(self._icon(source.host, 16))
                content.append(Gtk.Label(label=source.name, xalign=0))
                entry = Gtk.Button(child=content, has_frame=False, tooltip_text=_("Busca en {source_host}").format(source_host=source.host))
                entry.connect("clicked", lambda _b, n=source.name: (popover.popdown(), self._open_source(n)))
                entries.append(entry)
        popover.set_child(entries)
        web_menu = Gtk.MenuButton(child=menu_content, popover=popover, tooltip_text=(
            _("Abre en tu navegador la búsqueda del título en la web que elijas")))
        self.web_menu = web_menu
        return web_menu

    def _identify_buy_menu(self):
        """Menú «Comprar»."""
        buy_content = Gtk.Box(spacing=6)
        buy_content.append(Gtk.Image(icon_name=pick_icon("shopping-cart-symbolic", "package-x-generic-symbolic",
                                                         "emblem-shared-symbolic", FALLBACK_ICON)))
        buy_content.append(Gtk.Label(label=_("Comprar")))
        buy_content.append(Gtk.Image(icon_name=pick_icon("pan-down-symbolic")))
        buy_popover = Gtk.Popover()
        buy_entries = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6,
                              margin_start=6, margin_end=6)
        buy_entries.append(Gtk.Label(label=_("Busca el ejemplar en tu navegador"), xalign=0, margin_start=6,
                                     margin_bottom=4, css_classes=["dim-label"]))
        all_shops = Gtk.Box(spacing=8)
        all_shops.append(Gtk.Image(icon_name=pick_icon("edit-select-all-symbolic", FALLBACK_ICON), pixel_size=16))
        all_shops.append(Gtk.Label(label=_("Todas"), xalign=0))
        all_shops_button = Gtk.Button(child=all_shops, has_frame=False,
                                      tooltip_text=_("Busca en las {SHOPS_count} tiendas, cada una en su pestaña").format(SHOPS_count=len(SHOPS)))
        all_shops_button.connect("clicked", lambda _b: (buy_popover.popdown(), self._open_all_shops()))
        buy_entries.append(all_shops_button)
        buy_entries.append(Gtk.Separator(margin_top=2, margin_bottom=2))
        for group in SHOP_GROUPS:
            buy_entries.append(Gtk.Label(label=group, xalign=0, margin_start=6, margin_top=6,
                                         css_classes=["heading"]))
            for shop in (s for s in SHOPS if s.category == group):
                shop_line = Gtk.Box(spacing=8)
                shop_line.append(self._icon(shop.host, 16))
                shop_line.append(Gtk.Label(label=shop.name, xalign=0))
                shop_button = Gtk.Button(child=shop_line, has_frame=False, tooltip_text=_("Busca en {shop_host}").format(shop_host=shop.host))
                shop_button.connect("clicked", lambda _b, n=shop.name: (buy_popover.popdown(), self._open_shop(n)))
                buy_entries.append(shop_button)
        buy_popover.set_child(buy_entries)
        buy_menu = Gtk.MenuButton(child=buy_content, popover=buy_popover, tooltip_text=(
            _("Abre en tu navegador la búsqueda del ejemplar en una tienda o en una web de segunda mano "
            "(Forum y Vértice ya no publican: solo se encuentran de segunda mano)")))
        self.buy_menu = buy_menu
        return buy_menu

    def _open_source(self, name: str):
        title, number, publisher, year = self._fields()
        if not self.web_extra.get_active():
            publisher = year = ""
        try:
            url = search_url(name, title, number, publisher, year)
        except ValueError:
            self.status.set_text(_("Escribe un título para buscarlo en {name}.").format(name=name))
            return
        Gtk.UriLauncher.new(url).launch(self, None, lambda *_args: None)

    def _shop_terms(self) -> tuple[str, str, str, str]:
        """Qué buscar al comprar: el resultado elegido (serie, número y editorial o sello) o, si no hay ninguno con
        datos, lo escrito en los campos; con la casilla desmarcada, sin editorial ni año."""
        title, number, publisher, year = self._fields()
        chosen = self.selected
        if chosen is not None and chosen.source in ("GCD", *CATALOG_SOURCES) and chosen.series:
            title, number = chosen.series, chosen.number or number
            publisher, year = chosen.brand or chosen.publisher or publisher, chosen.year or year
        if not self.web_extra.get_active():
            publisher = year = ""
        return title, number, publisher, year

    def _open_shop(self, name: str):
        try:
            url = shop_url(name, *self._shop_terms())
        except ValueError:
            self.status.set_text(_("Escribe un título (o elige un resultado) para buscarlo en {name}.").format(name=name))
            return
        Gtk.UriLauncher.new(url).launch(self, None, lambda *_args: None)

    def _open_all_shops(self):
        try:
            urls = [shop_url(shop.name, *self._shop_terms()) for shop in SHOPS]
        except ValueError:
            self.status.set_text(_("Escribe un título (o elige un resultado) para buscarlo en las tiendas."))
            return
        for url in urls:
            Gtk.UriLauncher.new(url).launch(self, None, lambda *_args: None)
        self.status.set_text(_("Abriendo la búsqueda en {SHOPS_count} tiendas, cada una en su pestaña…").format(SHOPS_count=len(SHOPS)))

    def _open_all_sources(self, _button=None):
        title, number, publisher, year = self._fields()
        if not title.strip():
            self.status.set_text(_("Escribe un título para buscarlo."))
            return
        if not self.web_extra.get_active():
            publisher = year = ""
        for source in SOURCES:
            Gtk.UriLauncher.new(search_url(source.name, title, number, publisher, year)).launch(
                self, None, lambda *_args: None)
        self.status.set_text(_("Abriendo la búsqueda en {SOURCES_count} webs, cada una en su pestaña…").format(SOURCES_count=len(SOURCES)))

    def _choose_image(self, _button):
        images = Gtk.FileFilter(name=_("Cómics (CBR/CBZ/CB7) e imágenes"))
        images.add_mime_type("image/*")
        for extension in COMIC_EXTENSIONS:
            images.add_suffix(extension.lstrip("."))
        dialog = Gtk.FileDialog(title=_("Abrir cómic o imagen de portada"), default_filter=images)
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
            self.status.set_text(_("«{path_name}» no es un cómic (CBR, CBZ, CB7) ni una imagen.").format(path_name=path.name))

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
            self.status.set_text(_("El portapapeles no contiene un archivo que se pueda abrir."))

    def _pasted(self, clipboard, result):
        try:
            texture = clipboard.read_texture_finish(result)
        except GLib.Error:
            texture = None
        if texture is None:
            self.status.set_text(_("El portapapeles no contiene una imagen ni un cómic copiado."))
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
        self.status.set_text(_("Leyendo la portada de {path_name}…").format(path_name=path.name))
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
            self.status.set_text(_("No se pudo leer la portada de {comic_name}: {error}").format(comic_name=comic.name, error=error))

    def _finish_load(self, image: Path, source: Path | None, generation: int):
        if generation != self._generation:
            if source is not None:   # portada extraída de una carga que ya no vale
                image.unlink(missing_ok=True)
            return
        for old in self.cache_dir.glob("portada_*.png"):   # portadas extraídas de cargas anteriores
            if old != image:
                old.unlink(missing_ok=True)
        if self.preview.get_visible():   # el panel era de otro cómic (o de su sesión de IA): un elemento nuevo lo cierra
            self._close_preview(None)
        self.source_file = source
        self.image = image
        self._set_pages([])
        self.meta_box.set_visible(False)
        self.delete_meta_button.set_sensitive(False)
        self.picture.set_tooltip_text(_("Doble clic para verla más grande"))
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

    def _delete_meta(self, _button):
        """Quita el ComicInfo.xml entero del archivo abierto (no campo a campo): para empezar de cero. Se puede
        deshacer, como cualquier otra escritura de metadatos, con «Deshacer» en Ajustes."""
        target = self.source_file
        if target is None:
            return
        self.delete_meta_button.set_sensitive(False)

        def run():
            library = Library(LIBRARY_DB) if LIBRARY_DB.exists() else None
            try:
                removed = delete_info(target, METADATA_LOG, library)
            except MetadataError as error:
                later(self._meta_deleted, target, None, error)
            else:
                later(self._meta_deleted, target, removed, None)
        Thread(target=run, daemon=True).start()

    def _meta_deleted(self, target: Path, removed: bool | None, error):
        if error is not None:
            self.status.set_text(_("No se pudo eliminar el ComicInfo.xml de {target_name}: {error}").format(target_name=target.name, error=error))
        elif removed:
            self.status.set_text(_("ComicInfo.xml de {target_name} eliminado. «Deshacer» en Ajustes lo recupera.").format(target_name=target.name))
        else:
            self.status.set_text(_("{target_name} ya no tenía ComicInfo.xml.").format(target_name=target.name))
        self._refresh_series()
        if target == self.source_file:
            self._refresh_meta()

    def _show_meta(self, source: Path, info: dict, error: str, generation: int):
        if generation != self._generation or source != self.source_file:
            return
        while (child := self.meta_grid.get_first_child()) is not None:
            self.meta_grid.remove(child)
        rows = describe_info(info)
        self.delete_meta_button.set_sensitive(bool(rows))
        if error or not rows:
            text = _("No se pudo leer: {error}").format(error=error) if error else _("Este archivo no tiene ComicInfo.xml.")
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

    def _reset(self, _button=None):
        """Vuelve al estado inicial: sin campos, resultados, portada, ficha ni sesión de IA."""
        self._generation += 1
        self._marvel_request += 1   # lo que aún venga de Universo Marvel o Tebeosfera ya no interesa
        self.busy = False
        self._stop_search_progress()
        if self._live_timer:
            GLib.source_remove(self._live_timer)
            self._live_timer = 0
        self._set_fields("", "", "", "")
        self.image = self.source_file = None
        self._set_pages([])
        self.meta_box.set_visible(False)
        self.delete_meta_button.set_sensitive(False)
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
        if client is not None:   # consultar ComicVine tarda varios segundos (varias peticiones seguidas);
            self._start_search_progress()   # GCD y la propia colección son locales y no lo necesitan
        Thread(target=self._work, args=(self.image, client, query, number, publisher, year, self._generation),
               daemon=True).start()

    def _start_search_progress(self, job: str = "comicvine"):
        """Barra pulsante bajo el estado mientras dura algún trabajo lento de red (ComicVine, Universo Marvel);
        sigue encendida hasta que terminan todos."""
        self._progress_jobs.add(job)
        self.search_progress.set_visible(True)
        if not self._search_pulse_id:
            self.search_progress.pulse()
            self._search_pulse_id = GLib.timeout_add(150, lambda: (self.search_progress.pulse(), True)[1])

    def _stop_search_progress(self, job: str | None = None):
        """Termina el trabajo `job` (o todos, sin argumento); la barra se apaga cuando no queda ninguno."""
        if job is None:
            self._progress_jobs.clear()
        else:
            self._progress_jobs.discard(job)
        if self._progress_jobs:
            return
        if self._search_pulse_id:
            GLib.source_remove(self._search_pulse_id)
            self._search_pulse_id = 0
        self.search_progress.set_visible(False)

    def _work(self, image, client, query, number, publisher, year, generation):
        library = Library(LIBRARY_DB) if LIBRARY_DB.exists() else None
        gcd = self._gcd()
        try:
            outcome = identify(image, library, client, query, number,
                               progress=lambda message: later(self._progress, message, generation), gcd=gcd,
                               publisher=publisher, year=year, marvel=self._marvel(),
                               tebeosfera=self._tebeosfera())
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
        self._stop_search_progress("comicvine")
        self.status.set_text(_("No se pudo procesar la imagen: {error}").format(error=error))

    def _show(self, outcome, generation=None):
        if generation is not None and generation != self._generation:
            return   # se ha limpiado mientras tanto
        self.busy = False
        self._stop_search_progress("comicvine")
        if outcome.issue_number and not self.number.get_text():   # p. ej. del código de barras
            self._set_fields(number=outcome.issue_number)
        self.library_matches = [c for c in outcome.candidates if c.source == "Mi colección"]
        self._show_candidates(outcome.candidates)
        summary = [_("Código de barras: {outcome_barcode}").format(outcome_barcode=outcome.barcode)] if outcome.barcode else []
        summary += outcome.notes
        if not outcome.candidates and not outcome.notes:
            summary.append(_("Sin resultados; prueba a corregir el título o el número."))
        if outcome.candidates:
            summary.append(_("{outcome_candidates_count} candidato(s), de más a menos parecido.").format(outcome_candidates_count=len(outcome.candidates)))
        self._add_panel_hint(summary, outcome.candidates)
        self.status.set_text(" · ".join(summary))

    def _add_panel_hint(self, summary, candidates):
        if any(c.source == "ComicVine" or (c.source in ("GCD", *CATALOG_SOURCES) and webkit_available())
               for c in candidates):
            summary.append(_("Haz clic en una sugerencia para ver su ficha a la derecha."))

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

    @staticmethod
    def _marvel():
        index = UniversoMarvelIndex(UNIVERSOMARVEL_DB)
        return index if index.is_ready() else None

    @staticmethod
    def _tebeosfera():
        index = TebeosferaIndex(TEBEOSFERA_DB)
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
        gcd, marvel, tebeosfera = self._gcd(), self._marvel(), self._tebeosfera()
        if gcd is None and marvel is None and tebeosfera is None:
            self.status.set_text(_("Importa el volcado de GCD o descarga el índice de Universo Marvel o de Tebeosfera "
                                 "(pestaña Ajustes) para buscar mientras escribes; «Buscar en ComicVine» consulta ComicVine."))
        elif len(query) < 2:
            self._show_candidates(self.library_matches)
        else:
            hits = search_gcd(gcd, query, number, publisher, year) if gcd is not None else []
            marvel_hits = search_marvel(marvel, query, publisher) if marvel is not None else []
            tebeosfera_hits = search_tebeosfera(tebeosfera, query, publisher) if tebeosfera is not None else []
            catalog_hits = marvel_hits + tebeosfera_hits
            self._show_candidates(self.library_matches + tebeosfera_hits + marvel_hits + hits)
            found = ([_("{hits_count} de GCD").format(hits_count=len(hits))] if gcd is not None else []) + (
                [_("{marvel_hits_count} de Universo Marvel").format(marvel_hits_count=len(marvel_hits))] if marvel is not None else []) + (
                [_("{tebeosfera_hits_count} de Tebeosfera").format(tebeosfera_hits_count=len(tebeosfera_hits))] if tebeosfera is not None else [])
            summary = [_("Sugerencias para «{query}»: {found}").format(query=query, found=', '.join(found)) if hits or catalog_hits
                       else _("Sin resultados para «{query}»").format(query=query)]
            summary.append(_("«Buscar en ComicVine» lo consulta también."))
            self._add_panel_hint(summary, hits + catalog_hits)
            self.status.set_text(" · ".join(summary))
        return GLib.SOURCE_REMOVE

    # ---- Normalizar el nombre del archivo ---------------------------------------------------
    def _export_cover(self, _button):
        target = self._normalize_target()
        if target is None:
            return
        self.status.set_text(_("Extrayendo la portada de {target_name}…").format(target_name=target.name))

        def work():
            try:
                saved = extract_cover(target, target.with_suffix(""))
            except (OSError, ValueError) as error:
                later(self._export_cover_failed, error)
            else:
                later(self._export_cover_done, saved)
        Thread(target=work, daemon=True).start()

    def _export_cover_done(self, saved: Path):
        self.status.set_text(_("Portada guardada como «{saved_name}», junto al archivo.").format(saved_name=saved.name))

    def _export_cover_failed(self, error):
        self.status.set_text(_("No se pudo extraer la portada: {error}").format(error=error))

    # ---- Transferir a GCstar ---------------------------------------------------------------------
