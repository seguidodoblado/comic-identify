"""Metadatos ComicInfo.xml de archivos y carpetas."""
import json
from pathlib import Path
from threading import Thread

from ..comicinfo import CATEGORIES, MetadataError, build_xml, read_info
from ..covers import (
    COMIC_EXTENSIONS,
    list_pages,
)
from ..gcd import IssueDetails
from ..i18n import _, ngettext
from ..identify import (
    CATALOG_SOURCES,
    MARVEL_METADATA,
    MARVEL_PER_ISSUE,
)
from ..library import Library
from ..metadata import differs, write_batch
from ..metadata import undo_last as undo_metadata
from ..metaform import (
    append_block,
    common_value,
    file_changes,
    initial_category,
    initial_form,
    merge_values,
    series_changes,
    suggest_fields,
)
from ..naming import (
    Values,
    detect_number,
    natural_key,
    parse_name,
    series_values,
    suggest_values,
)
from ..settings import (
    LIBRARY_DB,
    METADATA_LOG,
    UNIVERSOMARVEL_DB,
)
from ..umficha import GCD_CREDITS_HEADING, compose_notes
from ..universomarvel import (
    UniversoMarvelClient,
    UniversoMarvelIndex,
)
from .constants import (
    STOP_ICON,
)
from .widgets import (
    GLib,
    Gtk,
    NotesBox,
    Pango,
    icon_button,
    later,
)


class MetadataMixin:
    def _choose_metadata_folder(self, _button):
        Gtk.FileDialog(title=_("Carpeta con los cómics")).select_folder(self, None, self._metadata_folder_chosen)

    def _metadata_folder_chosen(self, dialog, result):
        try:
            folder = Path(dialog.select_folder_finish(result).get_path())
        except GLib.Error:
            return
        files = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in COMIC_EXTENSIONS),
                       key=lambda p: natural_key(p.name))
        if not files:
            self.status.set_text(_("No hay archivos de cómic directamente en {folder_name}.").format(folder_name=folder.name))
            return
        self._start_metadata(folder, files)

    def _metadata_file(self, _button):
        target = self._normalize_target()
        if target is not None:
            self._start_metadata(target, [target])

    def _start_metadata(self, where: Path, files: list[Path]):
        self.status.set_text(_("Leyendo los metadatos de {files_count} archivo(s)…").format(files_count=len(files)))
        chosen = self.selected   # con una ficha de Universo Marvel y un solo archivo, también las fichas USA
        wants_usa = (len(files) == 1 and chosen is not None and chosen.source == "Universo Marvel"
                     and chosen.extra.get("level") == "issue")
        if wants_usa:
            self._start_search_progress("usa")

        def read():   # en otro hilo: un RAR se lee lanzando `unrar`
            infos, counts = [], {}
            for path in files:
                try:
                    infos.append((read_info(path), ""))
                except MetadataError as error:
                    infos.append((None, str(error)))
                counts[path] = len(list_pages(path))   # las páginas del archivo real, no las de ninguna ficha
            usa, usa_error = None, ""
            if wants_usa:   # guion, lápiz, tinta y color están en la ficha del original USA de cada historia
                try:
                    refs = [tuple(ref) for ref in json.loads(chosen.extra.get("UsaRefs", "[]"))]
                    if refs:
                        client = UniversoMarvelClient(UniversoMarvelIndex(UNIVERSOMARVEL_DB))
                        usa = client.usa_info(refs, chosen.extra.get("SpanishPage", ""),
                                              lambda message: later(self.status.set_text, message))
                except Exception as error:  # noqa: BLE001 - los créditos USA son un extra: el diálogo se abre igualmente
                    usa_error = str(error)
            later(self._metadata_loaded, where, files, infos, counts, usa, usa_error)
        Thread(target=read, daemon=True).start()

    def _metadata_loaded(self, where: Path, files: list[Path], infos: list, counts: dict, usa=None,
                         usa_error: str = ""):
        self._stop_search_progress("usa")
        self.status.set_text(_("Metadatos leídos de {files_count} archivo(s).").format(files_count=len(files)))
        gcd = self._gcd()
        info = None
        if gcd is not None and self.selected is not None and self.selected.series_id:
            info = gcd.series_info(self.selected.series_id)
        title, _number, publisher, _year = self._fields()
        catalog = self.selected is not None and self.selected.source in CATALOG_SOURCES
        values = merge_values(parse_name(where.stem if where.is_file() else where.name),
                              suggest_values(self.selected) if catalog else
                              series_values(info) if info is not None else None, title)
        extra, per_issue = {}, {}
        if catalog:
            publisher = publisher or self.selected.publisher
            # Mes, traducción, rotulación… son de UN ejemplar: solo se ofrecen si se etiqueta un único archivo
            extra = {key: self.selected.extra[key] for key in MARVEL_METADATA
                     if len(files) == 1 and self.selected.extra.get(key)}
            per_issue = {key: self.selected.extra[key] for key in MARVEL_PER_ISSUE
                         if len(files) == 1 and self.selected.extra.get(key)}
            if self.selected.brand:
                extra["Imprint"] = self.selected.brand
        notice = ""
        notice_warning = False   # el aviso se pinta como advertencia (no por su texto, que se traduce)
        details = self._gcd_issue_details(gcd) if len(files) == 1 else None
        if details is not None:   # créditos, género y personajes del número de GCD elegido
            extra.update({key: value for key, value in details.credits.items() if value})
            extra.update({"Genre": details.genre, "Characters": details.characters,
                          "Year": details.date[0], "Month": details.date[1], "Day": details.date[2],
                          "Web": self.selected.url})
            per_issue.update({"GTIN": details.barcode or details.isbn, "Summary": details.summary})
            if details.story_lines:   # varias historias: quién hizo qué en cada una, en las Notas
                per_issue["NotesBlock"] = "\n".join([GCD_CREDITS_HEADING, *details.story_lines])
            notice = (_("Créditos, género y personajes: de la ficha del número en GCD (los de alguna historia, de la "
                        "original reimpresa).") if details.inherited else
                      _("Créditos, género y personajes: de la ficha del número en GCD."))
        if usa is not None:
            extra.update({key: value for key, value in usa.credits.items() if value})
            if usa.summary:   # la sinopsis de las historias, para el Resumen (solo si el archivo no lo tiene ya)
                per_issue["Summary"] = usa.summary
            if usa.story_lines:   # además de los campos (unión), el desglose de quién hizo qué en cada historia
                per_issue["NotesBlock"] = compose_notes(self.selected.extra.get("NotesUsa", ""), usa.story_lines,
                                                        self.selected.extra.get("NotesComments", ""))
            if any(usa.credits.values()):
                years = f" ({', '.join(str(year) for year in usa.years)})" if usa.years else ""
                notice = _("Guion, lápiz, tinta y color: de las fichas USA de los originales que recoge este "
                           "ejemplar{years}.").format(years=years)
                if usa.approximate:
                    notice += " " + _("Revisa: de {titles} no se pudo saber qué historias son las de este ejemplar, "
                                      "y se han incluido todas.").format(titles=", ".join(usa.approximate))
                    notice_warning = True
            if usa.missing:
                unread = _("No se pudo leer la ficha USA de: {titles}.").format(titles=", ".join(usa.missing))
                notice = f"{notice} {unread}" if notice else unread
                notice_warning = True
        elif usa_error:
            notice = _("No se pudieron consultar las fichas USA (guion, lápiz, tinta y color): {usa_error}").format(usa_error=usa_error)
            notice_warning = True
        self._open_metadata_dialog(where, files, infos, values, publisher, info, extra, counts, per_issue, notice,
                                   notice_warning)

    def _gcd_issue_details(self, gcd):
        """Los datos que GCD tiene del número elegido (no de la serie): del índice local si los trae, o los ya
        consultados a su API pública al usar la ficha de un número que no estaba en el índice."""
        chosen = self.selected
        if chosen is None or chosen.source != "GCD" or not chosen.extra.get("issue_id"):
            return None
        if api_details := chosen.extra.get("ApiIssueDetails"):
            return IssueDetails(**json.loads(api_details))
        if gcd is None:
            return None
        return gcd.issue_details(int(chosen.extra["issue_id"]))

    def _open_metadata_dialog(self, where: Path, files: list[Path], infos: list, values: Values, publisher: str,
                              gcd_info, extra=None, counts=None, per_issue=None, notice: str = "",
                              notice_warning: bool = False):
        good = [i for i, _error in infos if i is not None]
        suggested = suggest_fields(values, publisher, gcd_info)
        suggested.update({key: value for key, value in (extra or {}).items() if value})   # la ficha manda
        texts, baseline = initial_form(good, suggested)
        if (per_issue or {}).get("NotesBlock"):   # ejemplares USA y comentarios de la ficha, bajo lo que ya haya
            texts["Notes"] = append_block(texts.get("Notes", ""), per_issue["NotesBlock"])
        window = Gtk.Window(title=_("Metadatos"), transient_for=self, modal=True, default_width=960, default_height=780)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12,
                        margin_start=14, margin_end=14)
        window.set_child(outer)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)   # todo lo que puede crecer va aquí dentro,
        content = Gtk.ScrolledWindow(vexpand=True, margin_end=4)         # con desplazamiento propio: los botones de
        content.set_child(box)                                          # abajo siempre quedan a la vista
        outer.append(content)
        head = Gtk.Label(xalign=0, wrap=True)
        head.set_markup(_("<b>{kind}:</b> {path}  ({files})").format(
            kind=_("Carpeta") if where.is_dir() else _("Archivo"), path=GLib.markup_escape_text(str(where)),
            files=ngettext("{count} archivo", "{count} archivos", len(files)).format(count=len(files))))
        box.append(head)
        original = Gtk.Label(xalign=0, wrap=True, label=(
            _("Los metadatos se escriben en los propios archivos, no en copias (antes se verifica una copia de cada "
            "uno); cada lote se puede deshacer desde Ajustes.")))
        original.add_css_class("dim-label")
        box.append(original)
        if notice:
            note_label = Gtk.Label(xalign=0, wrap=True, label=notice)
            note_label.add_css_class("warning" if notice_warning else "dim-label")
            box.append(note_label)

        labels = {"Series": (_("Serie"), _("nombre de la serie")), "Volume": (_("Volumen"), "8"),
                  "Publisher": (_("Editorial"), _("Panini, Planeta…")), "Imprint": (_("Sello"), _("el impreso en el ejemplar")),
                  "Year": (_("Año"), "2000"), "Month": (_("Mes"), _("opcional, 01-12")), "Day": (_("Día"), _("opcional, 01-31")),
                  "Count": (_("Total de números"), _("los que tiene la serie")),
                  "LanguageISO": (_("Idioma"), _("es, en…")), "Format": (_("Formato"), _("Tomo tapa blanda, Grapa…")),
                  "Genre": (_("Género"), _("crimen, superhéroes…")), "Characters": (_("Personajes"), _("Punisher, Micro…")),
                  "Web": ("Web", _("ficha de GCD u otra")),
                  "Notes": (_("Notas"), _("años del contenido original…"))}
        layout = (("Series", "Volume"), ("Publisher", "Imprint"), ("Year", "Month", "Day", "Count"),
                  ("LanguageISO", "Format"), ("Genre", "Characters"), ("Web",), ("Notes",))
        grid = Gtk.Grid(column_spacing=10, row_spacing=6)
        entries: dict[str, Gtk.Entry] = {}
        for row, keys in enumerate(layout):
            for index, key in enumerate(keys):
                label, hint = labels[key]
                value, absent = common_value(good, key)
                varied = not value and not absent
                narrow = key in ("Month", "Day")
                shown = _("(distinto en cada archivo: se deja como está)") if varied else hint
                if key == "Notes":   # varias líneas: contenido original, ejemplares USA y comentarios de la edición
                    entry = NotesBox(texts[key], shown)
                else:
                    entry = Gtk.Entry(text=texts[key], hexpand=not narrow, width_chars=4 if narrow else -1,
                                      placeholder_text=shown)
                entries[key] = entry
                grid.attach(Gtk.Label(label=label, xalign=0, yalign=0 if key == "Notes" else 0.5),
                            index * 2, row, 1, 1)
                span = 7 if key == "Notes" else 3 if len(keys) == 1 and key == "Web" else 1
                grid.attach(entry, index * 2 + 1, row, span, 1)
        box.append(grid)
        note = Gtk.Label(xalign=0, wrap=True, label=(
            _("Se rellena con lo que ya tienen los archivos y, en lo demás, con la serie de GCD y el nombre. Un campo "
            "vacío no se toca; si quitas un valor que todos tenían, se borra. Revisa lo que viene de GCD.")))
        note.add_css_class("dim-label")
        box.append(note)

        box.append(Gtk.Label(label=_("Créditos (se aplican a todos los archivos del lote):"), xalign=0))
        credit_labels = {"Writer": (_("Guion"), _("quien escribe")), "Penciller": (_("Lápiz"), _("quien dibuja")),
                         "Inker": (_("Tinta"), _("quien entinta")), "Colorist": (_("Color"), _("quien colorea")),
                         "Letterer": (_("Rotulación"), _("quien rotula")), "CoverArtist": (_("Portada"), _("quien dibuja la portada")),
                         "Translator": (_("Traducción"), _("quien traduce")), "Editor": (_("Edición"), _("quien edita"))}
        credit_layout = (("Writer", "Penciller", "Inker"), ("Colorist", "Letterer", "CoverArtist"),
                         ("Translator", "Editor"))
        credit_grid = Gtk.Grid(column_spacing=10, row_spacing=6)
        for row, keys in enumerate(credit_layout):
            for index, key in enumerate(keys):
                label, hint = credit_labels[key]
                value, absent = common_value(good, key)
                varied = not value and not absent
                entry = Gtk.Entry(text=texts[key], hexpand=True, placeholder_text=(
                    _("(distinto en cada archivo: se deja como está)") if varied else hint))
                entries[key] = entry
                credit_grid.attach(Gtk.Label(label=label, xalign=0), index * 2, row, 1, 1)
                credit_grid.attach(entry, index * 2 + 1, row, 1, 1)
        box.append(credit_grid)

        box.append(Gtk.Label(label=_("Categoría (la eliges tú; se guarda en las etiquetas):"), xalign=0))
        radios = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4, column_spacing=12,
                             row_spacing=4, homogeneous=False)
        first, wanted = None, initial_category(good)
        options = {}
        for name in ("", *CATEGORIES):
            radio = Gtk.CheckButton(label=name or _("(no cambiar)"), active=(name == wanted))
            if first is None:
                first = radio
            else:
                radio.set_group(first)
            options[name] = radio
            radios.append(radio)
        box.append(radios)

        listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        rows = []
        for path, (info, error) in zip(files, infos, strict=True):
            number = detect_number(path.stem)[0] or (info or {}).get("Number", "")
            line = Gtk.Box(spacing=8, margin_top=3, margin_bottom=3, margin_start=6, margin_end=6)
            include = Gtk.CheckButton(active=info is not None, sensitive=info is not None,
                                      tooltip_text=_("Escribir los metadatos de este archivo"))
            name = Gtk.Label(label=path.name, xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE,
                             width_chars=20, max_width_chars=28, tooltip_text=error or str(path))
            number_entry = Gtk.Entry(text=number, width_chars=5, placeholder_text=_("Nº"),
                                     tooltip_text=_("Número de ejemplar (se toma del nombre del archivo)"))
            title_entry = Gtk.Entry(text=(info or {}).get("Title", "") or (per_issue or {}).get("Title", ""),
                                    width_chars=16, hexpand=True,
                                    placeholder_text=_("Título del ejemplar (opcional)"))
            summary_entry = Gtk.Entry(text=(info or {}).get("Summary", "") or (per_issue or {}).get("Summary", ""),
                                      width_chars=16, hexpand=True,
                                      placeholder_text=_("Resumen del ejemplar (opcional)"))
            state_label = Gtk.Label(xalign=0, width_chars=14, ellipsize=Pango.EllipsizeMode.END, tooltip_text=error)
            for widget in (include, name, number_entry, title_entry, summary_entry, state_label):
                line.append(widget)
            listing.append(line)
            rows.append({"path": path, "info": info, "error": error, "include": include, "number": number_entry,
                         "title": title_entry, "summary": summary_entry, "state": state_label, "changes": None,
                         "pages": (counts or {}).get(path, 0)})
        scroll = Gtk.ScrolledWindow(min_content_height=140, max_content_height=320, propagate_natural_height=True)
        scroll.set_child(listing)
        box.append(scroll)
        summary = Gtk.Label(xalign=0, wrap=True)
        problem = Gtk.Label(xalign=0, wrap=True)
        problem.add_css_class("error")
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = icon_button(STOP_ICON, _("Cancelar"))
        apply = icon_button(("emblem-ok-symbolic", "object-select-symbolic"), _("Escribir metadatos"))
        apply.add_css_class("suggested-action")
        for widget in (cancel, apply):
            buttons.append(widget)
        for widget in (summary, problem, buttons):   # fuera del área que se desplaza: siempre a la vista
            outer.append(widget)
        state = {"busy": False}

        def chosen_category() -> str:
            return next((name for name, radio in options.items() if radio.get_active()), "")

        def refresh(*_args):
            if state["busy"]:
                return
            series = series_changes({key: entry.get_text() for key, entry in entries.items()}, baseline)
            blocking = ""
            try:
                build_xml(None, series)   # valida números y fechas antes de tocar nada
            except MetadataError as error:
                blocking = str(error)
            category = chosen_category()
            pending = same = 0
            for r in rows:
                r["changes"] = None
                if r["error"]:
                    r["state"].set_text(_("no se puede leer"))
                elif not r["include"].get_active():
                    r["state"].set_text(_("sin tocar"))
                elif blocking:
                    r["state"].set_text("—")
                else:
                    changes = file_changes(series, category, r["number"].get_text(), r["title"].get_text(),
                                           r["summary"].get_text(), r["info"], r["pages"],
                                           {key: (per_issue or {}).get(key, "") for key in ("GTIN", "BlackAndWhite")})
                    if differs(r["info"], changes):
                        r["changes"] = changes
                        r["state"].set_text(_("se modifica") if r["info"] else _("se crea"))
                        pending += 1
                    else:
                        r["state"].set_text(_("ya está igual"))
                        same += 1
            skipped = sum(1 for r in rows if not r["include"].get_active() or r["error"])
            summary.set_text(_("{pending} archivo(s) se modifican · {same} ya están igual · {skipped} sin tocar").format(pending=pending, same=same, skipped=skipped))
            problem.set_text(blocking)
            apply.set_sensitive(bool(pending) and not blocking)

        def finished(result):
            state["busy"] = False
            self._refresh_series()
            if self.source_file in result.written:
                self._refresh_meta()
            self.status.set_text(
                _("Metadatos escritos en {result_written_count} archivo(s)").format(result_written_count=len(result.written))
                + (_("; {result_unchanged_count} ya estaban igual").format(result_unchanged_count=len(result.unchanged)) if result.unchanged else "")
                + (_(". {result_failed_count} fallaron: ").format(result_failed_count=len(result.failed)) + "; ".join(f"{p.name}: {e}" for p, e in result.failed[:3])
                   if result.failed else "."))
            if result.failed and not result.written:
                problem.set_text(_("No se ha escrito nada: ") + "; ".join(f"{p.name}: {e}" for p, e in result.failed[:3]))
                for widget in (cancel, apply):
                    widget.set_sensitive(True)
                return
            window.close()

        def do_apply(_button):
            items = [(r["path"], r["changes"]) for r in rows if r["changes"]]
            state["busy"] = True
            for widget in (cancel, apply):
                widget.set_sensitive(False)
            library = Library(LIBRARY_DB) if LIBRARY_DB.exists() else None

            def progress(done, total):
                later(summary.set_text, _("Escribiendo… {done}/{total}").format(done=done, total=total))

            def run():
                later(finished, write_batch(items, METADATA_LOG, library, progress))
            Thread(target=run, daemon=True).start()

        for entry in (*entries.values(), *(r["number"] for r in rows), *(r["title"] for r in rows),
                     *(r["summary"] for r in rows)):
            entry.connect("changed", refresh)
        for radio in options.values():
            radio.connect("toggled", refresh)
        for r in rows:
            r["include"].connect("toggled", refresh)
        cancel.connect("clicked", lambda _b: window.close())
        apply.connect("clicked", do_apply)
        self.metadata_dialog = {"window": window, "entries": entries, "options": options, "rows": rows,
                                "summary": summary, "problem": problem, "apply": apply}   # para las pruebas
        refresh()
        window.present()
        entries["Series"].grab_focus()

    def _undo_metadata(self, _button):
        library = Library(LIBRARY_DB) if LIBRARY_DB.exists() else None
        self.metadata_undo_button.set_sensitive(False)
        self.metadata_undo_info.set_text(_("Deshaciendo…"))

        def run():
            try:
                later(self._metadata_undone, undo_metadata(METADATA_LOG, library), None)
            except (OSError, LookupError, ValueError) as error:
                later(self._metadata_undone, None, error)
        Thread(target=run, daemon=True).start()

    def _metadata_undone(self, result, error):
        self.metadata_undo_button.set_sensitive(True)
        self._refresh_series()
        self._refresh_meta()
        if error is not None:
            self.metadata_undo_info.set_text(_("No se pudo deshacer: {error}").format(error=error))
            return
        text = _("Deshecho el último lote: {result_restored_count} archivo(s) restaurados.").format(result_restored_count=len(result.restored))
        if result.skipped:
            text += _(" {result_skipped_count} omitidos: ").format(result_skipped_count=len(result.skipped)) + "; ".join(f"{p.name} ({why})" for p, why in result.skipped[:3])
        self.metadata_undo_info.set_text(text)
