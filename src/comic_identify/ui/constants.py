"""Constantes de la interfaz."""
from ..i18n import _
from ..settings import Settings

COMICVINE_API_URL = "https://comicvine.gamespot.com/api/"
GCD_DOWNLOAD_URL = "https://www.comics.org/download/"
GCD_SITE = "https://www.comics.org/"
COMICVINE_HOST, GCD_HOST = "comicvine.gamespot.com", "www.comics.org"
FALLBACK_ICON = "applications-internet-symbolic"
MAX_ALTERNATIVES = 30   # fichas que se ofrecen de una serie cuyo número no se encuentra
SERIES_FILTERS = [_("Incompletas"), _("Todas"), _("Sin todos sus metadatos"), _("Sin total indicado")]
SERIES_SHOWN = 300
PAGE_MAX_SIDE = 1600   # las páginas se reducen a esto para mostrarlas: un escaneo enorme no bloquea la ventana
PAGES_CACHED = 8
TERMINAL_FONT = "Ubuntu Sans Mono, Monospace"   # tipografía del terminal del asistente (Regular); la 2.ª es el respaldo
TERMINAL_FONT_SIZE = 11
VIEWER_MAX_SIDE = 3200   # lado máximo de la página en la ventana grande (letra pequeña legible sin agotar la memoria)
AUTHOR = "Jose Antonio Seguido Doblado"
AUTHOR_EMAIL = "jose.antonio.seguido@gmail.com"
REPO_URL = "https://github.com/seguidodoblado/comic-identify"
INDEX_ICON = ("view-refresh-symbolic", "emblem-synchronizing-symbolic")
STOP_ICON = ("process-stop-symbolic", "window-close-symbolic")
DEFAULT_PATTERN = Settings.pattern
WINDOW_HEIGHT = 820
COVER_WIDTH = 440
META_MAX_HEIGHT = 260   # alto máximo del panel del ComicInfo.xml; si hay más campos, se desplaza
WINDOW_WIDTH = 1500   # ancho por defecto: los siete botones de arriba caben en una línea
PREVIEW_WIDTH = 520
ASSISTANT_WIDTH = 760   # el terminal necesita ~80 columnas
MIN_PANEL_WIDTH = 420   # lo mínimo que se le deja al panel derecho si la pantalla no da para más
PANEL_FRAME = 40   # lo que ocupan el separador y los márgenes junto al panel derecho (~27 px), con holgura
# Fuente de cada resultado -> (web de la que se toma el icono, clase CSS de su color)
SOURCE_STYLES = {"GCD": (GCD_HOST, "source-gcd"), "Universo Marvel": ("fichas.universomarvel.com", "source-marvel"),
                 "Tebeosfera": ("www.tebeosfera.com", "source-tebeosfera"),
                 "ComicVine": (COMICVINE_HOST, "source-comicvine")}
CSS = b"""
.source-chip { color: white; font-weight: bold; font-size: 0.85em; border-radius: 9px; padding: 1px 9px; }
.source-gcd { background-color: #7e57c2; }
.source-marvel { background-color: #d32f2f; }
.source-tebeosfera { background-color: #ef6c00; }
.source-comicvine { background-color: #2e7d32; }
.publisher-badge { background-color: alpha(currentColor, 0.12); border-radius: 9px; padding: 1px 9px; font-size: 0.85em; }
"""
RESTORE_VARIABLE = "COMIC_IDENTIFY_RESTORE"   # estado que pasa el proceso que se reinicia por el tema
LIVE_DELAY_MS = 300   # pausa al teclear antes de buscar en GCD
INITIAL_STATUS = _("Escribe un título para buscar, o abre, pega o arrastra un cómic (CBR/CBZ/CB7) o una imagen de portada.")
