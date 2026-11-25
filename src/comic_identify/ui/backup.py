"""Copias de seguridad y restauración."""
import sys
from pathlib import Path
from threading import Thread

from .. import __version__
from .. import backup as backup_module
from ..i18n import _
from .widgets import (
    GLib,
    Gtk,
    icon_button,
    later,
)


class BackupMixin:
    def _backup_dir(self) -> Path | None:
        text = self.settings.backup_dir.strip()
        return Path(text).expanduser() if text else None

    def _refresh_backup_info(self):
        folder = self._backup_dir()
        self.backup_now_button.set_sensitive(folder is not None)
        self.backup_restore_button.set_sensitive(folder is not None)
        if folder is None:
            self.backup_info.set_text(_("Elige una carpeta para activar las copias."))
            return
        backups = backup_module.list_backups(folder)
        if not backups:
            self.backup_info.set_text(_("Todavía no hay copias en esa carpeta."))
            return
        last = backups[0]
        self.backup_info.set_text(_("{backups_count} copia(s). La última: {last_created:%d/%m/%Y %H:%M} ({get}).").format(backups_count=len(backups), last_created=last.created, get=backup_module.KIND_LABELS.get(last.kind, last.kind)))

    def _choose_backup_dir(self, _button):
        Gtk.FileDialog(title=_("Carpeta de las copias de seguridad")).select_folder(self, None, self._backup_dir_chosen)

    def _backup_dir_chosen(self, dialog, result):
        try:
            self.backup_entry.set_text(dialog.select_folder_finish(result).get_path())
        except GLib.Error:
            pass  # Selección cancelada.

    def _save_backup_settings(self, _button):
        self.settings.backup_dir = self.backup_entry.get_text().strip()
        self.settings.backup_keep = self.backup_keep.get_value_as_int()
        self.settings.save()
        self._refresh_backup_info()

    def _backup_now(self, _button):
        folder = self._backup_dir()
        if folder is None:
            return
        if self.indexing:
            self.backup_info.set_text(_("Hay una indexación en marcha: espera a que termine para copiar."))
            return
        self.backup_now_button.set_sensitive(False)
        self.backup_info.set_text(_("Copiando…"))

        def run():
            try:
                archive = backup_module.create(folder, backup_module.MANUAL, version=__version__)
            except backup_module.BackupError as error:
                later(self._backup_done, None, error)
            else:
                later(self._backup_done, archive, None)
        Thread(target=run, daemon=True).start()

    def _backup_done(self, archive, error):
        self.backup_now_button.set_sensitive(True)
        if error is not None:
            self.backup_info.set_text(_("No se pudo copiar: {error}").format(error=error))
            return
        self._refresh_backup_info()
        self.backup_info.set_text(_("Copia guardada: {archive_name}. {get_text}").format(archive_name=archive.name, get_text=self.backup_info.get_text()))

    def _auto_backup(self, _window):
        """Al cerrar: una copia automática si algo ha cambiado desde la última. Nunca impide cerrar."""
        folder = self._backup_dir()
        if folder is None or self.indexing:
            return False
        try:
            if not backup_module.unchanged_since_last(folder):
                backup_module.create(folder, backup_module.AUTO, version=__version__)
                backup_module.prune(folder, self.settings.backup_keep)
        except (backup_module.BackupError, OSError) as error:
            print(_("Copia de seguridad automática fallida: {error}").format(error=error), file=sys.stderr)
        return False

    def _open_restore(self, _button):
        folder = self._backup_dir()
        if folder is None:
            return
        if self.indexing:
            self.backup_info.set_text(_("Hay una indexación en marcha: espera a que termine para restaurar."))
            return
        backups = backup_module.list_backups(folder)
        if not backups:
            self.backup_info.set_text(_("No hay copias que restaurar en esa carpeta."))
            return
        window = Gtk.Window(title=_("Restaurar una copia"), transient_for=self, modal=True, default_width=640,
                            default_height=460)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12,
                      margin_start=14, margin_end=14)
        window.set_child(box)
        box.append(Gtk.Label(xalign=0, wrap=True, label=(
            _("Elige la copia. Antes de sustituir nada se comprueba que está íntegra y se guarda una copia del "
            "estado actual («antes de restaurar»), por si te arrepientes."))))
        listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        for info in backups:
            what = ", ".join(info.names)
            row = Gtk.Label(xalign=0, wrap=True, margin_top=4, margin_bottom=4, margin_start=6, label=(
                f"{info.created:%d/%m/%Y %H:%M:%S} · {backup_module.KIND_LABELS.get(info.kind, info.kind)} · "
                f"{info.size / 1_048_576:.1f} MB\n{what}"))
            listing.append(row)
        scroll = Gtk.ScrolledWindow(vexpand=True, has_frame=True)
        scroll.set_child(listing)
        box.append(scroll)
        info_label = Gtk.Label(xalign=0, wrap=True)
        box.append(info_label)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = icon_button(("process-stop-symbolic", "window-close-symbolic"), _("Cancelar"))
        restore = icon_button(("document-revert-symbolic", "edit-undo-symbolic"), _("Restaurar"), sensitive=False)
        restore.add_css_class("destructive-action")
        buttons.append(cancel)
        buttons.append(restore)
        box.append(buttons)
        cancel.connect("clicked", lambda _b: window.close())
        listing.connect("row-selected", lambda _l, row: restore.set_sensitive(row is not None))

        def do_restore(_button):
            row = listing.get_selected_row()
            if row is None:
                return
            archive = backups[row.get_index()].path
            restore.set_sensitive(False)
            cancel.set_sensitive(False)
            info_label.set_text(_("Restaurando…"))

            def run():
                try:
                    result = backup_module.restore(archive, version=__version__)
                except backup_module.BackupError as error:
                    later(failed, error)
                else:
                    later(done, result)

            def failed(error):
                info_label.set_text(_("No se ha restaurado nada: {error}").format(error=error))
                cancel.set_sensitive(True)
                restore.set_sensitive(True)

            def done(result):
                window.close()
                self._reload_settings()
                self._refresh_gcd()
                self._refresh_marvel()
                self._refresh_tebeosfera()
                self._refresh_library()
                self._refresh_backup_info()
                self.backup_info.set_text(
                    _("Restaurado: {result_restored}. Estado anterior guardado en «{name}».").format(result_restored=', '.join(result.restored), name=result.safety.name if result.safety else _("ninguna copia (no había datos)")))
            Thread(target=run, daemon=True).start()
        restore.connect("clicked", do_restore)
        window.present()
