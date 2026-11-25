"""Visor de páginas del cómic abierto."""
from pathlib import Path
from threading import Thread

from ..covers import (
    read_page,
    thumbnail_bytes,
)
from ..i18n import _
from .constants import (
    PAGE_MAX_SIDE,
    PAGES_CACHED,
    VIEWER_MAX_SIDE,
)
from .widgets import (
    Gdk,
    GLib,
    Gtk,
    icon_button,
    later,
    pick_icon,
)


class ViewerMixin:
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
            ("go-first-symbolic", _("Primera página")), ("go-previous-symbolic", _("Página anterior")),
            ("go-next-symbolic", _("Página siguiente")), ("go-last-symbolic", _("Última página")))]
        label = Gtk.Label(width_chars=17)
        actual = Gtk.ToggleButton(label=_("Tamaño real"), tooltip_text=_("Muestra la página sin reducirla (con barras de desplazamiento)"))
        close = icon_button(("window-close-symbolic",), _("Cerrar"))
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
            label.set_text(_("Página {state} de {count}").format(state=state['index'] + 1, count=count) + ("…" if loading else ""))
            window.set_title(_("{name} — página {state} de {count}").format(name=name, state=state['index'] + 1, count=count) if count > 1 else name)
            for button in buttons[:2]:
                button.set_sensitive(state["index"] > 0)
            for button in buttons[2:]:
                button.set_sensitive(state["index"] < count - 1)

        def ready(index, request, data):
            if request != state["request"]:
                return
            if data is None:
                refresh_bar()
                self.status.set_text(_("No se pudo leer la página {index} para ampliarla.").format(index=index + 1))
                return
            cache[index] = data
            try:
                picture.set_paintable(Gdk.Texture.new_from_bytes(GLib.Bytes.new(data)))
            except GLib.Error:
                self.status.set_text(_("No se pudo mostrar esta página."))
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
        self.page_label.set_text(_("Página {page_index} de {count}").format(page_index=self.page_index + 1, count=count) + ("…" if loading else ""))
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
            self.status.set_text(_("No se pudo leer la página {index} de este archivo.").format(index=index + 1))
            return
        if len(self._page_cache) >= PAGES_CACHED:
            self._page_cache.pop(next(iter(self._page_cache)))
        self._page_cache[index] = data
        self._show_page(data)

    def _show_page(self, data: bytes):
        try:
            self.picture.set_paintable(Gdk.Texture.new_from_bytes(GLib.Bytes.new(data)))
        except GLib.Error:
            self.status.set_text(_("No se pudo mostrar esta página."))
        self._update_pages()
