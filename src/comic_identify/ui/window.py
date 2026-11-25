"""Ventana principal y aplicación GTK."""
import sys
from pathlib import Path
from threading import Event, Thread

from ..i18n import _
from ..identify import (
    Candidate,
)
from ..settings import (
    Settings,
)
from ..sources import SHOPS, SOURCES
from .assistant import AssistantMixin
from .backup import BackupMixin
from .constants import (
    COMICVINE_HOST,
    CSS,
    FALLBACK_ICON,
    GCD_HOST,
    PREVIEW_WIDTH,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from .gcstar import GcstarMixin
from .icons import ensure_icons, icon_file
from .identify import IdentifyMixin
from .library import LibraryMixin
from .metadata import MetadataMixin
from .normalizers import NormalizersMixin
from .preview import PreviewMixin
from .results import ResultsMixin
from .settings import SettingsMixin
from .theming import is_dark_theme, theme_variant
from .viewer import ViewerMixin
from .widgets import (
    Gdk,
    Gio,
    GLib,
    Gtk,
    later,
    pick_icon,
    theme_state,
)


class Window(AssistantMixin, BackupMixin, GcstarMixin, IdentifyMixin, LibraryMixin, MetadataMixin, NormalizersMixin, PreviewMixin, ResultsMixin, SettingsMixin, ViewerMixin, Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Comic Identify")
        self.set_default_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
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
        self._web_filter_ready, self._web_pending = False, ""   # el panel web espera a sus reglas de bloqueo
        self._big_covers: dict[str, bytes] = {}   # portadas grandes de ComicVine ya descargadas
        self._native_url = ""
        self.icon_widgets: dict[str, list] = {}   # host -> imágenes que muestran su icono
        self.logo_widgets: dict[str, list] = {}    # editorial -> logotipos de las filas que esperan el suyo
        self._logo_requested: set[str] = set()
        self.cache_dir = Path(GLib.get_user_cache_dir()) / "comic-identify"
        self.icon_dir = self.cache_dir / "icons"
        self.logo_dir = self.cache_dir / "logos"   # logotipos de editoriales (ver logos.py)
        self.source_file: Path | None = None   # CBR/CBZ abierto: el que se puede normalizar
        self.selected: Candidate | None = None
        self._marvel_request = 0   # descarta la respuesta de una ficha si ya se eligió otra cosa
        self._gcd_api_request = 0  # igual, para la consulta a la API pública de GCD (último recurso)
        self._generation = 0   # sube al limpiar: descarta los resultados de una búsqueda ya en marcha
        self.assistant_box = None   # página del panel con el terminal, mientras hay sesión
        self.assistant_terminal = None
        self._panel_width = PREVIEW_WIDTH
        notebook = self.notebook = Gtk.Notebook()
        for page, icons, title in ((self._identify_page(), ("edit-find", "system-search"), _("Identificar")),
                                   (self._library_page(), ("folder-documents", "view-grid", "emblem-documents"),
                                    _("Mi colección")),
                                   (self._settings_page(), ("preferences-system",), _("Ajustes"))):
            tab = Gtk.Box(spacing=6)
            tab.append(Gtk.Image(icon_name=pick_icon(*icons)))
            tab.append(Gtk.Label(label=title))
            notebook.append_page(page, tab)
        self.set_child(notebook)
        self.connect("close-request", self._auto_backup)
        GLib.idle_add(lambda: (self._restore_session(), GLib.SOURCE_REMOVE)[1])
        self._refresh_library()
        Thread(target=self._load_icons, daemon=True).start()
        paste = Gtk.Shortcut(trigger=Gtk.ShortcutTrigger.parse_string("<Control>v"),
                             action=Gtk.CallbackAction.new(lambda *_args: self._paste() or True))
        controller = Gtk.ShortcutController()
        controller.add_shortcut(paste)
        self.add_controller(controller)

    @staticmethod
    def _box(orientation=Gtk.Orientation.VERTICAL, spacing=10):
        return Gtk.Box(orientation=orientation, spacing=spacing, margin_top=12, margin_bottom=12,
                       margin_start=12, margin_end=12)

    # ---- Iconos de las webs ------------------------------------------------------------
    def _icon(self, host: str, size: int):
        image = Gtk.Image(icon_name=pick_icon(FALLBACK_ICON), pixel_size=size)   # reserva si la web no da su icono
        self.icon_widgets.setdefault(host, []).append(image)
        if (cached := icon_file(host, self.icon_dir)) is not None:
            image.set_from_file(str(cached))
        return image

    def _icon_ready(self, host: str, path: Path):
        for image in self.icon_widgets.get(host, []):
            image.set_from_file(str(path))

    def _load_icons(self):
        """Descarga (una sola vez, luego caché) los iconos de las webs; en segundo plano."""
        wanted = ([(source.host, False) for source in (*SOURCES, *SHOPS)]
                  + [(COMICVINE_HOST, True), (GCD_HOST, True)])
        ensure_icons(wanted, self.icon_dir, lambda host, path: later(self._icon_ready, host, path))

    # ---- Identificar -------------------------------------------------------------------


class App(Gtk.Application):
    def __init__(self):
        # HANDLES_OPEN: un archivo pasado a una segunda ejecución llega a la ventana ya abierta.
        super().__init__(application_id="io.github.seguidodoblado.ComicIdentify", flags=Gio.ApplicationFlags.HANDLES_OPEN)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        gtk_settings = Gtk.Settings.get_default()
        theme_state["system"] = gtk_settings.get_property("gtk-theme-name")
        chosen = Settings.load().dark_mode
        theme_state["dark"] = is_dark_theme(theme_state["system"]) if chosen is None else chosen
        if chosen is not None:   # antes de presentar la ventana: en caliente Cinnamon no repinta
            gtk_settings.set_property("gtk-theme-name", theme_variant(theme_state["system"], chosen))

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

def run_app(initial_image: Path | None = None) -> None:
    # Con "python3 -m" argv[0] es la ruta de __main__.py y GTK derivaría de ahí el WM_CLASS; se fija para que coincida
    # con StartupWMClass del .desktop y el panel muestre el icono.
    GLib.set_prgname("comic-identify")
    App().run([sys.argv[0]] + ([str(initial_image)] if initial_image is not None else []))