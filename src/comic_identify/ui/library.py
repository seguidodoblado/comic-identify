"""Pestaña «Mi colección»."""
from pathlib import Path
from threading import Thread

from ..collection import build_series, ranges
from ..i18n import _
from ..library import Library
from ..settings import (
    LIBRARY_DB,
)
from .constants import (
    INDEX_ICON,
    SERIES_FILTERS,
    SERIES_SHOWN,
    STOP_ICON,
)
from .widgets import (
    Gio,
    GLib,
    Gtk,
    icon_button,
    later,
    set_icon_button,
)


class LibraryMixin:
    def _library_page(self):
        page = self._box()
        controls = Gtk.Box(spacing=8)
        add = icon_button(("folder-new-symbolic", "list-add-symbolic"), _("Añadir carpeta…"))
        add.connect("clicked", self._add_folder)
        self.index_button = icon_button(INDEX_ICON, _("Indexar / actualizar"))
        self.index_button.connect("clicked", self._toggle_index)
        controls.append(add)
        controls.append(self.index_button)
        self.folders = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        scroll = Gtk.ScrolledWindow(min_content_height=60, max_content_height=130, propagate_natural_height=True)
        scroll.set_child(self.folders)
        self.index_progress = Gtk.ProgressBar(show_text=True)
        self.index_info = Gtk.Label(xalign=0, wrap=True)

        title = Gtk.Label(xalign=0, label=_("Series de la colección (por carpeta y metadatos):"))
        title.add_css_class("heading")
        self.series_filter = Gtk.DropDown.new_from_strings(SERIES_FILTERS)
        self.series_filter.connect("notify::selected", self._show_series)
        self.series_search = Gtk.SearchEntry(placeholder_text=_("Buscar una serie…"), hexpand=True)
        self.series_search.connect("search-changed", self._show_series)
        refresh = icon_button(("view-refresh-symbolic",), _("Actualizar lista"), tooltip_text=(
            _("Vuelve a calcular la lista con lo indexado (indexa antes para leer los metadatos nuevos)")))
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

    def _refresh_series(self):
        """Recalcula las series con lo que hay en el índice y las muestra."""
        self.series_reports = build_series(Library(LIBRARY_DB).series_rows()) if LIBRARY_DB.exists() else []
        self._show_series()

    def _show_series(self, *_args):
        while (row := self.series_list.get_first_child()) is not None:
            self.series_list.remove(row)
        needle = self.series_search.get_text().strip().lower()
        # en el orden de SERIES_FILTERS: incompletas, todas, sin todos sus metadatos y sin total indicado
        keep = (lambda r: bool(r.missing), lambda r: True, lambda r: r.tagged < r.files,
                lambda r: r.count is None)[self.series_filter.get_selected()]
        shown = [r for r in self.series_reports if keep(r) and needle in r.name.lower()]
        for report in shown[:SERIES_SHOWN]:
            parts = [_("{owned} de {total}").format(owned=len(report.owned), total=report.count) if report.count else
                     _("{report_owned_count} números (total sin indicar)").format(report_owned_count=len(report.owned))]
            if report.mixed:
                parts.append(_("varias series en la carpeta (números repetidos): sin comprobar"))
            if report.starts_at:
                parts.append(_("empieza en el {report_starts_at}").format(report_starts_at=report.starts_at))
            if report.missing:
                parts.append(_("faltan ") + ranges(report.missing))
            if report.sparse:
                parts.append(_("números sueltos: no se buscan huecos sin el total"))
            if report.strays:
                parts.append(_("fuera de la serie: ") + ranges(report.strays) + _(" (¿de otra serie?)"))
            if report.duplicated and not report.mixed:
                parts.append(_("repetidos: ") + ranges(report.duplicated))
            if report.other:
                parts.append(_("{report_other} sin número entero").format(report_other=report.other))
            parts.append(_("metadatos {report_tagged}/{report_files}").format(report_tagged=report.tagged, report_files=report.files))
            if report.category:
                parts.append(report.category)
            line = Gtk.Box(spacing=8, margin_top=4, margin_bottom=4, margin_start=6, margin_end=6)
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
            name = Gtk.Label(xalign=0, wrap=True, tooltip_text=report.folder)
            name.set_markup(f"<b>{GLib.markup_escape_text(report.name)}</b>")
            detail = Gtk.Label(label=" · ".join(parts), xalign=0, wrap=True)
            detail.add_css_class({"complete": "success", "incomplete": "warning"}.get(report.status_key, "dim-label"))
            text.append(name)
            text.append(detail)
            open_folder = icon_button(("folder-open-symbolic",), _("Abrir carpeta"), valign=Gtk.Align.CENTER)
            open_folder.connect("clicked", lambda _b, f=report.folder: Gtk.FileLauncher.new(
                Gio.File.new_for_path(f)).launch(None, None, lambda *_args: None))
            line.append(text)
            line.append(open_folder)
            self.series_list.append(line)
        incomplete = sum(1 for r in self.series_reports if r.missing)
        self.series_info.set_text(
            _("{series_reports_count} serie(s) reconocidas, {incomplete} con huecos").format(series_reports_count=len(self.series_reports), incomplete=incomplete)
            + (_(" · se muestran las primeras {SERIES_SHOWN} de {shown_count}: afina el filtro").format(SERIES_SHOWN=SERIES_SHOWN, shown_count=len(shown)) if len(shown) > SERIES_SHOWN
               else _(" · {shown_count} en la lista").format(shown_count=len(shown)))
            + _(". Una carpeta suelta sin metadatos ni nombre normalizado no cuenta como serie.")
            if self.series_reports else
            _("Todavía no hay series: indexa la colección y escribe metadatos o normaliza los nombres de las carpetas."))

    def _refresh_library(self):
        while (row := self.folders.get_first_child()) is not None:
            self.folders.remove(row)
        for folder in self.settings.folders:
            line = Gtk.Box(spacing=8, margin_top=4, margin_bottom=4, margin_start=6, margin_end=6)
            line.append(Gtk.Label(label=folder, xalign=0, hexpand=True))
            remove = icon_button(("list-remove-symbolic",), _("Quitar"))
            remove.connect("clicked", lambda _b, f=folder: self._remove_folder(f))
            line.append(remove)
            self.folders.append(line)
        total = Library(LIBRARY_DB).count() if LIBRARY_DB.exists() else 0
        self.index_info.set_text(_("{total} portada(s) indexada(s). Las carpetas se recorren con subcarpetas; los archivos ya indexados no se releen.").format(total=total))
        self._refresh_series()

    def _add_folder(self, _button):
        Gtk.FileDialog(title=_("Carpeta de cómics")).select_folder(self, None, self._folder_chosen)

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
            self.index_info.set_text(_("Espera a que termine la indexación (o cancélala) para quitar carpetas."))
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
            self.index_info.set_text(_("Añade primero alguna carpeta."))
            return
        self.cancel.clear()
        self.indexing = True
        set_icon_button(self.index_button, STOP_ICON, _("Cancelar"))
        Thread(target=self._index, args=([Path(f) for f in self.settings.folders],), daemon=True).start()

    def _index(self, folders):
        def progress(done, total):
            later(self.index_progress.set_fraction, done / total)
            later(self.index_progress.set_text, f"{done}/{total}")
        try:
            stats = Library(LIBRARY_DB).index(folders, progress, self.cancel)
            message = (_("Nuevas: {stats_indexed} · sin cambios: {stats_unchanged} · ilegibles: {stats_failed} · eliminadas: {stats_removed} · metadatos leídos en archivos ya indexados: {stats_refreshed}").format(stats_indexed=stats.indexed, stats_unchanged=stats.unchanged, stats_failed=stats.failed, stats_removed=stats.removed, stats_refreshed=stats.refreshed))
            if stats.failed_files:
                shown = stats.failed_files[:5]
                more = _(" (y {stats_failed} más)").format(stats_failed=stats.failed - len(shown)) if stats.failed > len(shown) else ""
                message += (_("\nIlegibles: ") + ", ".join(f"{Path(f).name} ({reason})" for f, reason in shown)
                            + more)
            if stats.unavailable:
                message += (_("\nSin acceso o vacías (su índice se conserva): ")
                            + ", ".join(stats.unavailable))
        except Exception as error:  # noqa: BLE001
            message = _("Error al indexar: {error}").format(error=error)
        later(self._index_done, message)

    def _index_done(self, message):
        self.indexing = False
        set_icon_button(self.index_button, INDEX_ICON, _("Indexar / actualizar"))
        self._refresh_library()
        self.index_info.set_text(self.index_info.get_text() + "\n" + message)

    # ---- Ajustes -----------------------------------------------------------------------
