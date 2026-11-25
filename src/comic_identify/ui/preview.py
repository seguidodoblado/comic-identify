"""Panel derecho: ficha web o nativa de la fuente elegida."""
import json
from dataclasses import asdict
from pathlib import Path
from threading import Thread

from .. import tebeosfera as tebeosfera_site
from ..comicvine import ComicVineClient, ComicVineError
from ..gcd import issue_id_from_url
from ..gcd_api import GcdApiClient, GcdApiError
from ..i18n import _
from ..identify import (
    CATALOG_SOURCES,
    Candidate,
    alternative_candidate,
    attach_cover,
    gcd_issue_candidate,
    marvel_issue_candidate,
    page_candidate,
    tebeosfera_alternative,
    tebeosfera_entry,
    tebeosfera_issue_candidate,
    tebeosfera_page_candidate,
)
from ..settings import (
    TEBEOSFERA_DB,
    UNIVERSOMARVEL_DB,
)
from ..tebeosfera import TebeosferaClient, TebeosferaError, TebeosferaIndex
from ..universomarvel import Entry as MarvelEntry
from ..universomarvel import (
    UniversoMarvelClient,
    UniversoMarvelError,
    UniversoMarvelIndex,
    ficha_page,
)
from . import webfilter
from .constants import (
    ASSISTANT_WIDTH,
    GCD_HOST,
    GCD_SITE,
    MAX_ALTERNATIVES,
    MIN_PANEL_WIDTH,
    PANEL_FRAME,
    PREVIEW_WIDTH,
    WINDOW_WIDTH,
)
from .widgets import (
    Gdk,
    GLib,
    Gtk,
    Pango,
    gi,
    icon_button,
    later,
    pick_icon,
    webkit_available,
)


class PreviewMixin:
    def _preview_panel(self):
        self.preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, visible=False)
        self.preview.set_size_request(PREVIEW_WIDTH, -1)
        header = Gtk.Box(spacing=8)
        self.preview_title = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END)   # se recorta antes que ensanchar el panel
        self.assistant_back = icon_button(("go-previous-symbolic",), _("Volver al asistente"), visible=False)
        self.assistant_back.connect("clicked", lambda _b: self._open_preview(
            _("Asistente de IA"), "", "assistant", ASSISTANT_WIDTH))
        self.preview_link = Gtk.LinkButton(uri=GCD_SITE, label=_("Abrir en el navegador"))
        self.use_ficha = Gtk.Button(label=_("Usar esta ficha"), visible=False, css_classes=["suggested-action"], tooltip_text=(
            _("Es la ficha de un ejemplar de Universo Marvel, Tebeosfera o GCD: la usa para rellenar los metadatos")))
        self.use_ficha.connect("clicked", self._use_web_ficha)
        close = Gtk.Button(icon_name=pick_icon("window-close-symbolic"), tooltip_text=_("Cerrar el panel"))
        close.connect("clicked", self._close_preview)
        for widget in (self.preview_title, self.use_ficha, self.preview_link, self.assistant_back, close):
            header.append(widget)
        # hhomogeneous=False: solo la página visible cuenta para el ancho (por defecto un Stack reserva el de la más ancha,
        # aunque esté oculta, y tras usar el terminal el panel de WebKit seguía ocupando su ancho)
        self.preview_stack = Gtk.Stack(vexpand=True, hhomogeneous=False)
        self.preview_stack.add_named(self._native_view(), "native")
        self.preview.append(header)
        self.preview.append(self.preview_stack)
        return self.preview

    def _native_view(self):
        """Ficha propia para ComicVine: su web va cargada de publicidad, la API da lo necesario."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        grid = Gtk.Grid(column_spacing=14, row_spacing=6)
        self.native_values = {}
        for row, (key, label) in enumerate((("name", _("Nombre:")), ("year", _("Año:")), ("issue", _("Issue:")))):
            caption = Gtk.Label(xalign=0, yalign=0)
            caption.set_markup(f"<big><b>{label}</b></big>")
            value = Gtk.Label(xalign=0, wrap=True, hexpand=True)
            grid.attach(caption, 0, row, 1, 1)
            grid.attach(value, 1, row, 1, 1)
            self.native_values[key] = value
        self.native_picture = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.CONTAIN, vexpand=True)
        attribution = Gtk.LinkButton(uri="https://comicvine.gamespot.com/", halign=Gtk.Align.START,
                                     label=_("Datos e imagen de Comic Vine"))
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
        elif candidate.source in CATALOG_SOURCES and candidate.extra.get("level") == "series" and (
                self._is_single_issue(candidate) or self.number.get_text().strip()):
            self._resolve_catalog(candidate)
        elif (candidate.source == "GCD" and candidate.url.startswith(GCD_SITE)) or (
                candidate.source in CATALOG_SOURCES and candidate.url):
            if webkit_available():
                self._show_web(candidate.url, _("Ficha de {candidate_source}").format(candidate_source=candidate.source) if candidate.source in CATALOG_SOURCES
                               else _("Ficha de Grand Comics Database"))
            else:   # sin WebKit no hay panel para esas webs: se abre en el navegador
                Gtk.UriLauncher.new(candidate.url).launch(self, None, lambda *_args: None)

    @staticmethod
    def _is_single_issue(series: Candidate) -> bool:
        """Un candidato de nivel «serie» que ya es la ficha de un número (un especial, un libro): no pide número."""
        if series.source == "Tebeosfera":
            return bool(series.extra.get("single"))
        return series.extra["page"].startswith("esp/")

    def _resolve_catalog(self, series: Candidate):
        """Consulta (una sola vez: luego queda en la base local) la ficha del número escrito de una serie de
        Universo Marvel o Tebeosfera, y la pone entre los resultados como un candidato con sus datos."""
        number = self.number.get_text().strip()
        site = series.source
        single = self._is_single_issue(series)
        self._marvel_request += 1
        request = self._marvel_request
        self._start_search_progress("marvel")
        image = self.image   # la portada abierta, para compararla con la de la ficha
        if webkit_available() and not (self.webview and self.webview.get_uri() == series.url):
            self._show_web(series.url, _("Serie en {site}").format(site=site))   # mientras tanto, la propia web
        self.status.set_text(_("Consultando la ficha en {site}…").format(site=site) if single else
                             _("Buscando el nº {number} de «{series_title}» en {site}…").format(number=number, series_title=series.title, site=site))

        def run():
            try:
                candidate, others = (self._fetch_tebeosfera if site == "Tebeosfera" else self._fetch_marvel)(
                    series, number, image)
            except (UniversoMarvelError, TebeosferaError, OSError) as error:
                later(self._marvel_resolved, request, series, None, _("No se pudo consultar {site}: {error}").format(site=site, error=error))
                return
            if candidate is None:
                later(self._marvel_resolved, request, series, None, _("«{series_title}» no tiene el nº {number} en {site} (o no está catalogado todavía).").format(series_title=series.title, number=number, site=site) + (_(" Elige una de sus fichas en la lista.") if others else ""),
                      others)
            else:
                later(self._marvel_resolved, request, series, candidate, "")
        Thread(target=run, daemon=True).start()

    @staticmethod
    def _fetch_marvel(series: Candidate, number: str, image) -> tuple[Candidate | None, list[Candidate]]:
        entry = MarvelEntry(series.extra.get("index_publisher", ""), series.extra.get("section", ""), series.title,
                            series.extra["page"])
        client = UniversoMarvelClient(UniversoMarvelIndex(UNIVERSOMARVEL_DB))
        issue = client.find_issue(entry, number)
        if issue is None:
            # una serie que lista sus fichas por título (Amalgam…) no tiene «nº 1»: se ofrecen tal cual
            others = [i for i in client.series_issues(entry) if i.page.startswith("esp/")][:MAX_ALTERNATIVES]
            return None, [alternative_candidate(entry, i) for i in others]
        ficha = client.ficha(issue.page)
        candidate = marvel_issue_candidate(entry, issue, ficha)
        try:   # la portada: una petición más la primera vez; si falla, la ficha vale igual
            if ficha.cover_image:
                attach_cover(candidate, client.cover(ficha.cover_image), image)
        except (UniversoMarvelError, OSError):
            pass
        return candidate, []

    @staticmethod
    def _fetch_tebeosfera(series: Candidate, number: str, image) -> tuple[Candidate | None, list[Candidate]]:
        entry = tebeosfera_entry(series)
        client = TebeosferaClient(TebeosferaIndex(TEBEOSFERA_DB))
        issue = client.find_issue(entry, number)
        if issue is None:   # los números más cercanos al escrito, para elegir a mano
            return None, [tebeosfera_alternative(entry, i) for i in client.nearest(entry, number, MAX_ALTERNATIVES)]
        ficha = client.ficha(issue.page)
        candidate = tebeosfera_issue_candidate(entry, issue, ficha)
        try:
            if ficha.cover_image:
                attach_cover(candidate, client.cover(ficha.cover_image), image)
        except (TebeosferaError, OSError):
            pass
        return candidate, []

    def _marvel_resolved(self, request: int, series: Candidate, candidate: Candidate | None, problem: str,
                         alternatives: list[Candidate] = ()):
        if request != self._marvel_request:
            return   # lo ha sustituido otra consulta (o se ha limpiado): ella se ocupa de la barra
        self._stop_search_progress("marvel")
        if self.selected is not series:
            return   # se ha elegido otra cosa mientras tanto
        if candidate is None:
            if alternatives:   # las fichas de esa serie, para elegir una (la serie deja de estar elegida)
                rest = [c for c in self.candidates if c is not series]
                self._show_candidates([*alternatives, *rest])
            self.status.set_text(problem)
            return
        rest = [c for c in self.candidates if c is not series]
        self._show_candidates([candidate, *rest])
        self.results.select_row(self.results.get_row_at_index(0))
        match = _(" · {candidate_similarity:.0%} de parecido con tu portada").format(candidate_similarity=candidate.similarity) if candidate.similarity is not None else ""
        self.status.set_text(_("Ficha de {candidate_source}: {candidate_title} · {candidate_subtitle}{match}").format(candidate_source=candidate.source, candidate_title=candidate.title, candidate_subtitle=candidate.subtitle, match=match))

    def _screen_width(self) -> int | None:
        monitor = Gdk.Display.get_default().get_monitor_at_surface(self.get_surface()) if self.get_surface() else None
        return monitor.get_geometry().width if monitor is not None else None

    def _panel_room(self, wanted: int) -> int:
        """El ancho que puede tener el panel derecho sin que la ventana se salga de la pantalla: lo que se pide, o lo
        que quede tras lo mínimo que necesita la parte izquierda (con tu tamaño de letra puede ser más que aquí)."""
        screen = self._screen_width()
        if screen is None:
            return wanted
        left_minimum = self.body.measure(Gtk.Orientation.HORIZONTAL, -1)[0]
        return max(MIN_PANEL_WIDTH, min(wanted, screen - left_minimum - PANEL_FRAME))

    def _resize_for_panel(self, delta: int):
        """La ventana crece o se encoge lo que el panel, pero nunca pasa del ancho de la pantalla y, si está maximizada
        o a pantalla completa, no se toca: el panel se reparte el ancho que ya hay."""
        if self.is_maximized() or self.is_fullscreen():
            return
        width = self.get_width() + delta
        if (screen := self._screen_width()) is not None:
            width = min(width, screen)
        self.set_default_size(max(width, WINDOW_WIDTH if delta < 0 else 0), self.get_height())

    def _open_preview(self, title: str, url: str, page: str, width: int = PREVIEW_WIDTH):
        width = self._panel_room(width)
        if not self.preview.get_visible():   # la ventana crece para no aplastar la lista
            self._resize_for_panel(width)
            self.preview.set_visible(True)
        elif width != self._panel_width:
            self._resize_for_panel(width - self._panel_width)
        self._panel_width = width
        self.preview.set_size_request(width, -1)
        self.preview_title.set_text(title)
        self.preview_link.set_uri(url or GCD_SITE)
        self.preview_link.set_visible(bool(url))
        self.preview_stack.set_visible_child_name(page)
        self.assistant_back.set_visible(self.assistant_box is not None and page != "assistant")

    def _show_web(self, url: str, title: str = _("Ficha de Grand Comics Database")):
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
            # sin cookies en disco (el panel no guarda ninguna) y, con las reglas de `webfilter`, sin cookies de las webs
            (data / "cookies.sqlite").unlink(missing_ok=True)   # las que dejó la versión anterior
            self.webview = WebKit.WebView(network_session=session, vexpand=True)
            self.webview.connect("notify::favicon", self._favicon_changed)
            self.webview.connect("notify::uri", self._web_uri_changed)
            self.preview_stack.add_named(self.webview, "web")
            self._web_filter_ready = False
            store = WebKit.UserContentFilterStore.new(str(cache / "filters"))
            store.save("tebeosfera", GLib.Bytes.new(webfilter.rules_json()), None, self._web_filter_saved)
        self._open_preview(title, url, "web")
        self._web_pending = url
        if self._web_filter_ready:
            self.webview.load_uri(url)   # si no, se carga en cuanto están compiladas las reglas (unos milisegundos)

    def _web_filter_saved(self, store, result):
        """Las reglas de bloqueo (ver `webfilter`) ya están compiladas: se aplican y se carga la página pedida. Si no se
        pudieron compilar, la página carga igual, sin bloqueos."""
        try:
            self.webview.get_user_content_manager().add_filter(store.save_finish(result))
        except GLib.Error:
            pass
        self._web_filter_ready = True
        if self._web_pending:
            self.webview.load_uri(self._web_pending)

    @staticmethod
    def _catalog_page(uri: str) -> tuple[str, str]:
        """(fuente, ruta o id) si `uri` es la ficha de un ejemplar de Universo Marvel, Tebeosfera o GCD; si no, vacío."""
        if page := ficha_page(uri):
            return "Universo Marvel", page
        if page := tebeosfera_site.ficha_page(uri):
            return "Tebeosfera", page
        if (issue_id := issue_id_from_url(uri)) is not None:
            return "GCD", str(issue_id)
        return "", ""

    def _web_uri_changed(self, webview, _param):
        """Al navegar hasta la ficha de un ejemplar, se ofrece usarla (si no es ya la elegida)."""
        site, page = self._catalog_page(webview.get_uri())
        key = "issue_id" if site == "GCD" else "SpanishPage"
        chosen = self.selected is not None and str(self.selected.extra.get(key, "")) == page
        self.use_ficha.set_visible(bool(page) and not chosen)

    def _use_web_ficha(self, _button):
        """La ficha que se ve en el panel pasa a ser el resultado elegido, con todos sus datos."""
        site, page = self._catalog_page(self.webview.get_uri())
        if not page:
            return
        self.use_ficha.set_visible(False)
        if site == "GCD":
            self._use_gcd_ficha(int(page))
            return
        title = self.webview.get_title() or page
        stub = tebeosfera_page_candidate(title, page) if site == "Tebeosfera" else page_candidate(title, page)
        self.results.unselect_all()
        self.selected = stub
        self._resolve_catalog(stub)

    def _use_gcd_ficha(self, issue_id: int):
        """GCD ya está entero en local: al contrario que Universo Marvel y Tebeosfera, no hace falta consultar nada,
        así que se resuelve al momento. Si el número no está en el índice (uno nuevo, o de un país que no se
        importa), se consulta como último recurso su API pública."""
        gcd = self._gcd()
        hit = gcd.issue_by_id(issue_id) if gcd is not None else None
        if hit is not None:
            self._show_gcd_candidate(gcd_issue_candidate(hit))
            return
        self._gcd_api_request += 1
        request = self._gcd_api_request
        self._start_search_progress("gcd_api")
        self.status.set_text(_("Ese número no está en tu índice de GCD: consultando su API pública…"))

        def run():
            try:
                hit, details = GcdApiClient().issue(issue_id)
            except GcdApiError as error:
                later(self._gcd_api_resolved, request, None, None, str(error))
            else:
                later(self._gcd_api_resolved, request, hit, details, "")
        Thread(target=run, daemon=True).start()

    def _gcd_api_resolved(self, request: int, hit, details, problem: str):
        if request != self._gcd_api_request:
            return   # se ha limpiado o elegido otra cosa mientras tanto
        self._stop_search_progress("gcd_api")
        if hit is None:
            self.status.set_text(_("No se pudo consultar la API pública de GCD: {problem}").format(problem=problem))
            return
        candidate = gcd_issue_candidate(hit)
        candidate.extra["ApiIssueDetails"] = json.dumps(asdict(details), ensure_ascii=False)
        self._show_gcd_candidate(candidate)

    def _show_gcd_candidate(self, candidate: Candidate):
        self.results.unselect_all()
        self._show_candidates([candidate, *self.candidates])
        self.results.select_row(self.results.get_row_at_index(0))
        self.status.set_text(_("Ficha de GCD: {candidate_title} · {candidate_subtitle}").format(candidate_title=candidate.title, candidate_subtitle=candidate.subtitle))

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
        self._open_preview(_("Ficha de ComicVine"), candidate.url, "native")
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
            self._resize_for_panel(-self._panel_width)
            self.preview.set_visible(False)
        self._drop_assistant()
        if self.webview is not None:   # libera los procesos de WebKit
            self.preview_stack.remove(self.webview)
            self.webview = None
        self.results.unselect_all()
