"""Piezas comunes de la interfaz GTK: carga de GTK, iconos y el cuadro de notas.

Este módulo importa GTK al cargarse; solo lo importa `window`, que a su vez lo carga `run_gui` (así los comandos sin
interfaz no necesitan PyGObject).
"""
import gi

gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: F401

from .theming import icon_choice


def webkit_available() -> bool:
    """WebKitGTK 6.0 instalado (se comprueba sin cargarlo; solo se importa al abrir una ficha)."""
    return "6.0" in gi.Repository.get_default().enumerate_versions("WebKit")

def vte_available() -> bool:
    """Terminal embebible para GTK4 (gir1.2-vte-3.91), comprobado sin cargarlo."""
    return "3.91" in gi.Repository.get_default().enumerate_versions("Vte")

theme_state = {"dark": False, "system": ""}   # modo elegido y tema GTK que tenía el sistema al arrancar

def pick_icon(*names: str) -> str:
    """El primer icono de la lista que exista en el tema del usuario ('' si ninguno): simbólico en el modo oscuro y
    de color en el claro (ver theming.icon_choice)."""
    theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
    return icon_choice(names, theme_state["dark"], theme.has_icon)

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

class NotesBox(Gtk.ScrolledWindow):
    """Texto de varias líneas con la interfaz mínima de un Gtk.Entry (get_text, set_text y la señal «changed»)."""

    def __init__(self, text: str = "", tooltip: str = ""):
        super().__init__(hexpand=True, has_frame=True, min_content_height=88, max_content_height=200,
                         propagate_natural_height=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        if tooltip:
            self.set_tooltip_text(tooltip)
        self.view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=4, bottom_margin=4, left_margin=6,
                                 right_margin=6)
        self.buffer = self.view.get_buffer()
        self.buffer.set_text(text)
        self.set_child(self.view)

    def get_text(self) -> str:
        return self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), False)

    def set_text(self, text: str):
        self.buffer.set_text(text)

    def connect(self, signal, callback, *args):
        if signal == "changed":
            return self.buffer.connect("changed", lambda _buffer: callback(self, *args))
        return super().connect(signal, callback, *args)

    def grab_focus(self):
        return self.view.grab_focus()