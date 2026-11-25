"""Transferencia de fichas a GCstar."""
from pathlib import Path
from threading import Thread

from ..comicinfo import MetadataError, category_of, read_info
from ..covers import (
    list_pages,
)
from ..gcstar import (
    VOCABULARY_FIELDS,
    GCstarError,
    format_name,
    series_text,
    suggest_type,
    vocabulary,
)
from ..gcstar import transfer as gcstar_transfer
from ..gcstar import undo_last as undo_gcstar
from ..i18n import _
from ..identify import (
    CATALOG_SOURCES,
)
from ..settings import (
    GCSTAR_LOG,
)
from .constants import (
    STOP_ICON,
)
from .widgets import (
    GLib,
    Gtk,
    icon_button,
    later,
)


class GcstarMixin:
    def _open_gcstar_transfer(self, _button):
        target = self._normalize_target()
        gcs_path = Path(self.settings.gcstar_path.strip()) if self.settings.gcstar_path.strip() else None
        if target is None or gcs_path is None:
            return
        self.status.set_text(_("Leyendo {target_name} y {gcs_path_name}…").format(target_name=target.name, gcs_path_name=gcs_path.name))

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
            origin = suggest_type(target, [Path(f) for f in self.settings.folders])
            later(self._open_gcstar_dialog, target, info, read_error, gcs_path, vocab, pages, origin)
        Thread(target=work, daemon=True).start()

    def _gcstar_prep_failed(self, message: str):
        self.status.set_text(_("No se pudo preparar la transferencia a GCstar: {message}").format(message=message))

    def _open_gcstar_dialog(self, target: Path, info: dict, read_error: str, gcs_path: Path, vocab: dict,
                            page_count: int, origin: str):
        window = Gtk.Window(title=_("Transferir a GCstar"), transient_for=self, modal=True, default_width=640)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=14, margin_bottom=14,
                      margin_start=16, margin_end=16)
        window.set_child(box)
        head = Gtk.Label(xalign=0, wrap=True)
        head.set_markup(_("<b>Archivo:</b> {markup_escape_text}\n<b>Colección:</b> {markup_escape_text_2}").format(markup_escape_text=GLib.markup_escape_text(target.name), markup_escape_text_2=GLib.markup_escape_text(str(gcs_path))))
        box.append(head)
        if read_error or not info:
            warning = Gtk.Label(xalign=0, wrap=True, label=(
                _("No se pudo leer el ComicInfo.xml: {read_error}").format(read_error=read_error) if read_error else
                _("Este archivo no tiene ComicInfo.xml todavía: se transferirá con muy pocos datos. Si quieres "
                "los créditos, la editorial, el año…, escribe antes los metadatos.")))
            warning.add_css_class("warning" if read_error else "dim-label")
            box.append(warning)
        series = series_text(info.get("Series", ""), info.get("Volume", ""))
        preview = Gtk.Label(xalign=0, wrap=True, selectable=True)
        preview.set_markup(f"<b>{GLib.markup_escape_text(format_name(series, info.get('Number', ''), info.get('Title', '')))}</b>")
        box.append(preview)
        details = ", ".join(part for part in (
            info.get("Publisher", ""), info.get("Year", ""), _("{page_count} páginas").format(page_count=page_count) if page_count else "") if part)
        if details:
            box.append(Gtk.Label(label=details, xalign=0, wrap=True, css_classes=["dim-label"]))

        box.append(Gtk.Label(label=_("Campos propios de GCstar (se sugiere lo que ya usas en tu colección):"),
                             xalign=0))
        grid = Gtk.Grid(column_spacing=10, row_spacing=6)
        fields = {"type": "Tipo", "category": "Categoría", "format": "Formato", "collection": "Colección",
                  "cost": "Coste", "isbn": "ISBN"}
        prefill = {"category": category_of(info.get("Tags", "")),   # ya la conocemos por nuestra propia Categoría
                  "format": info.get("Format", ""),   # el de ComicInfo.xml (p. ej. «Tomo tapa blanda» de la ficha)
                  "type": origin}   # Europeo/Americano/Manga, según la carpeta de Mi colección (ver ORIGIN_BY_FOLDER)
        if self.selected is not None and self.selected.source in CATALOG_SOURCES:
            # el precio no existe en ComicInfo.xml: solo se conoce por la ficha elegida (y se puede corregir aquí)
            prefill["cost"] = self.selected.extra.get("Cost", "")
            prefill["isbn"] = self.selected.extra.get("ISBN", "")
        elif (details := self._gcd_issue_details(self._gcd())) is not None:   # o por el número elegido de GCD
            prefill["cost"], prefill["isbn"] = details.cost, details.isbn
        gcstar_entries: dict[str, Gtk.Entry] = {}
        for row, (key, label) in enumerate(fields.items()):
            entry = Gtk.Entry(hexpand=True, text=prefill.get(key, ""))
            store = Gtk.ListStore(str)
            for value in vocab.get(key, []):
                store.append([value])
            completion = Gtk.EntryCompletion(model=store, text_column=0, inline_completion=True)
            entry.set_completion(completion)
            gcstar_entries[key] = entry
            grid.attach(Gtk.Label(label=label, xalign=0), (row % 2) * 2, row // 2, 1, 1)
            grid.attach(entry, (row % 2) * 2 + 1, row // 2, 1, 1)
        box.append(grid)
        back_check = Gtk.CheckButton(label=_("Incluir también la contraportada (última página)"), active=True,
                                    sensitive=page_count > 1)
        box.append(back_check)

        problem = Gtk.Label(xalign=0, wrap=True, css_classes=["error"])
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = icon_button(STOP_ICON, _("Cancelar"))
        apply = icon_button(("emblem-ok-symbolic", "object-select-symbolic"), _("Transferir"))
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
        self.gcstar_dialog = {"window": window, "entries": gcstar_entries, "apply": apply,
                              "problem": problem}   # para las pruebas
        window.present()

    def _gcstar_transfer_failed(self, window, cancel, apply, problem, message: str):
        for widget in (cancel, apply):
            widget.set_sensitive(True)
        problem.set_text(message)

    def _gcstar_transfer_done(self, window, result):
        window.close()
        where = (_(" Portada en «{name}»").format(name=result.image.name) + (_(" y contraportada en «{name}».").format(name=result.backpic.name)
                if result.backpic else ".") if result.image else _(" Sin portada (el archivo no está bajo "
                "ninguna carpeta de «Mi colección»)."))
        self.status.set_text(_("Transferido a GCstar (elemento nº {result_item_id}).{where}").format(result_item_id=result.item_id, where=where))

    def _undo_gcstar(self, _button):
        self.gcstar_undo_button.set_sensitive(False)
        self.gcstar_info.set_text(_("Deshaciendo…"))

        def run():
            try:
                later(self._gcstar_undone, undo_gcstar(GCSTAR_LOG), None)
            except (OSError, LookupError, GCstarError) as error:
                later(self._gcstar_undone, None, error)
        Thread(target=run, daemon=True).start()

    def _gcstar_undone(self, result, error):
        self.gcstar_undo_button.set_sensitive(True)
        if error is not None:
            self.gcstar_info.set_text(_("No se pudo deshacer: {error}").format(error=error))
            return
        text = (_("Deshecha la última transferencia.") if result.removed else
               _("El elemento ya no estaba tal cual en el .gcs (se ha editado desde entonces): no se ha tocado."))
        if result.images:
            text += _(" Se borraron {result_images_count} imagen(es).").format(result_images_count=len(result.images))
        if result.skipped_images:
            text += _(" {result_skipped_images_count} imagen(es) habían cambiado desde entonces y no se tocaron.").format(result_skipped_images_count=len(result.skipped_images))
        self.gcstar_info.set_text(text)
