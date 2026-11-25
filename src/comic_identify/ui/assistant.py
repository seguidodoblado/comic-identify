"""Asistente de IA (terminal embebido)."""
from pathlib import Path

from ..assistant import PROMPT, build_argv, build_prompt, prepare_workspace, shell_argv
from ..i18n import _
from .constants import (
    ASSISTANT_WIDTH,
    TERMINAL_FONT,
    TERMINAL_FONT_SIZE,
)
from .widgets import (
    GLib,
    Gtk,
    Pango,
    gi,
    vte_available,
)


class AssistantMixin:
    def _ask_ai(self, _button):
        if self.image is None:
            return
        if not vte_available():
            self.status.set_text(_("Falta el terminal embebido: instala el paquete gir1.2-vte-3.91."))
            return
        work = Path(GLib.get_user_cache_dir()) / "comic-identify" / "ai"
        try:
            prepare_workspace(self.image, work)
            image_name = next(work.glob("portada.*")).name
            argv = build_argv(self.settings.assistant, build_prompt(image_name, self.settings.prompt))
        except (OSError, ValueError) as error:
            self.status.set_text(_("No se pudo preparar el asistente: {error}").format(error=error))
            return
        self._open_assistant(work, argv)

    def _open_assistant(self, work: Path, argv: list[str]):
        gi.require_version("Vte", "3.91")
        from gi.repository import Vte
        self._drop_assistant()   # una sola sesión a la vez
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.assistant_note = Gtk.Label(xalign=0, wrap=True, label=(
            _("Sesión de «{argv}» con tu propia cuenta. Revisa cada permiso que te pida: esta aplicación no ve tus credenciales.").format(argv=argv[0])))
        terminal = Vte.Terminal(vexpand=True, hexpand=True)
        font = Pango.FontDescription()
        font.set_family(TERMINAL_FONT)
        font.set_weight(Pango.Weight.NORMAL)
        font.set_size(TERMINAL_FONT_SIZE * Pango.SCALE)
        terminal.set_font(font)
        terminal.set_scrollback_lines(10000)
        terminal.connect("child-exited", lambda _t, _status: self.assistant_note.set_text(
            _("La sesión ha terminado. Pulsa × para cerrar el panel.")))
        box.append(self.assistant_note)
        box.append(terminal)
        self.preview_stack.add_named(box, "assistant")
        self.assistant_box, self.assistant_terminal = box, terminal
        self._open_preview(_("Asistente de IA"), "", "assistant", ASSISTANT_WIDTH)
        # child_setup y child_setup_data quedan a None; -1 = sin límite de tiempo; sin cancelable.
        terminal.spawn_async(Vte.PtyFlags.DEFAULT, str(work), shell_argv(argv), None, GLib.SpawnFlags.SEARCH_PATH,
                             None, None, -1, None, self._assistant_spawned)
        terminal.grab_focus()

    def _assistant_spawned(self, _terminal, _pid, error, *_data):
        if error is not None:
            self.status.set_text(_("No se pudo lanzar el asistente: {error_message}").format(error_message=error.message))
            self._close_preview(None)

    def _drop_assistant(self):
        """Cierra la sesión (al destruir el terminal, el proceso recibe SIGHUP)."""
        if self.assistant_box is not None:
            self.preview_stack.remove(self.assistant_box)
            self.assistant_box = self.assistant_terminal = None
        self.assistant_back.set_visible(False)

    # ---- Panel de la ficha: web de GCD (WebKit) o ficha nativa de ComicVine ---------------
    def _save_assistant(self, _button):
        command = self.assistant_entry.get_text().strip()
        try:
            build_argv(command, "prueba")
        except ValueError as error:
            self.assistant_info.set_text(_("Comando no válido: {error}").format(error=error))
            return
        buffer = self.prompt_view.get_buffer()
        prompt = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False).strip()
        self.settings.assistant, self.settings.prompt = command, prompt or PROMPT
        self.settings.save()
        self.assistant_info.set_text(_("Comando y mensaje guardados.") if prompt else
                                     _("Comando guardado; el mensaje estaba vacío y se usa el de la aplicación."))
