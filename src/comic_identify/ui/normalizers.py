"""Normalizar nombres de archivos y carpetas."""
from pathlib import Path
from threading import Thread

from ..comicvine import ComicVineClient, ComicVineError
from ..covers import (
    COMIC_EXTENSIONS,
)
from ..i18n import _
from ..library import Library
from ..naming import (
    FLAGS,
    MAX_NAME_BYTES,
    VARIABLES,
    Values,
    check_pattern,
    detect_number,
    missing_content_years,
    natural_key,
    number_width,
    pad_number,
    render,
    series_values,
    suggest_values,
)
from ..originals import content_years, find_volumes
from ..renamer import rename_file, rename_series, undo_last
from ..settings import (
    LIBRARY_DB,
    RENAME_LOG,
)
from .constants import (
    COMICVINE_HOST,
    DEFAULT_PATTERN,
)
from .widgets import (
    GLib,
    Gtk,
    Pango,
    icon_button,
    later,
)


class NormalizersMixin:
    def _normalize_target(self) -> Path | None:
        """El CBR/CBZ abierto o, si no, el archivo de la coincidencia de «Mi colección» elegida."""
        if self.source_file is not None and self.source_file.is_file():
            return self.source_file
        if self.selected is not None and self.selected.path is not None and self.selected.path.is_file():
            return self.selected.path
        return None

    def _update_normalize(self):
        target = self._normalize_target()
        self.normalize_button.set_sensitive(target is not None)
        self.metadata_button.set_sensitive(target is not None)
        self.export_cover_button.set_sensitive(target is not None)
        self.gcstar_button.set_sensitive(target is not None and bool(self.settings.gcstar_path.strip()))

    # ---- Extraer la portada como imagen (para catalogadores externos como GCstar) -----------
    def _normalize(self, _button):
        target = self._normalize_target()
        if target is None:
            return
        if self.selected is not None:
            values, from_gcd = suggest_values(self.selected), self.selected.source == "GCD"
        else:   # sin sugerencia elegida: lo que haya en los campos de búsqueda
            title, number, _publisher, year = self._fields()
            values, from_gcd = Values(nombre=title, numero=number, edicion=year), False
        self._open_normalizer(target, values, from_gcd)

    def _open_normalizer(self, target: Path, values: Values, from_gcd: bool):
        window = Gtk.Window(title=_("Normalizar nombre"), transient_for=self, modal=True, default_width=720)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=14, margin_bottom=14,
                      margin_start=16, margin_end=16)
        window.set_child(box)
        current = Gtk.Label(xalign=0, wrap=True, selectable=False)
        current.set_markup(_("<b>Archivo:</b> {markup_escape_text}").format(markup_escape_text=GLib.markup_escape_text(target.name)))
        box.append(current)
        where = Gtk.Label(xalign=0, wrap=True, label=(
            _("En {target_parent}. Se renombra este mismo archivo, no una copia; se puede deshacer desde Ajustes.").format(target_parent=target.parent)))
        where.add_css_class("dim-label")
        box.append(where)

        grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        entries: dict[str, Gtk.Editable] = {}
        fields = (("nombre", _("Nombre"), _("serie u OneShot")), ("volumen", _("Volumen"), _("8 → «Volumen 8»")),
                  ("contenido", _("Contenido [años]"), _("años del material original: 1991 o 1991-1993")),
                  ("edicion", _("Edición (años)"), _("años de la edición que tienes")),
                  ("editorial", _("Editorial"), _("quién la publica: Planeta DeAgostini, Panini…")),
                  ("sello", _("Sello"), _("solo el que ves impreso en el ejemplar")), ("numero", _("Nº"), _("opcional")))
        flag = Gtk.DropDown.new_from_strings([_("(ninguna)"), *FLAGS.values()])
        flag.set_selected(([""] + list(FLAGS.values())).index(values.bandera) if values.bandera in FLAGS.values() else 0)
        for row, (key, label, hint) in enumerate(fields[:2] + (("bandera", _("Bandera"), ""),) + fields[2:]):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
            widget = flag if key == "bandera" else Gtk.Entry(text=getattr(values, key), hexpand=True,
                                                              placeholder_text=hint)
            if key != "bandera":
                entries[key] = widget
            grid.attach(widget, 1, row, 1, 1)
            if key == "contenido":   # el dato que no se sabe solo: ayuda para averiguarlo en ComicVine
                find = Gtk.Button(child=self._button_content(_("Buscar en ComicVine…")), tooltip_text=(
                    _("Busca los años originales en ComicVine a partir del título original y los números")))
                find.connect("clicked", lambda _b: self._open_original_lookup(window, entries))
                grid.attach(find, 2, row, 1, 1)
        box.append(grid)
        if from_gcd:
            note = Gtk.Label(xalign=0, wrap=True, label=(
                _("El sello y los años vienen de GCD, transcritos por otro colaborador: compruébalos con el "
                "ejemplar. El año real del contenido en ediciones españolas no se sabe solo: ponlo tú o "
                "búscalo con el botón de ComicVine.")))
            note.add_css_class("dim-label")
            box.append(note)

        box.append(Gtk.Label(label=_("Patrón (variables: ") + ", ".join("{" + v + "}" for v in VARIABLES) + "):",
                             xalign=0, wrap=True))
        pattern_row = Gtk.Box(spacing=8)
        pattern = Gtk.Entry(text=self.settings.pattern, hexpand=True)
        reset = icon_button(("edit-undo-symbolic", "view-refresh-symbolic"), _("Restablecer"))
        reset.connect("clicked", lambda _b: pattern.set_text(DEFAULT_PATTERN))
        pattern_row.append(pattern)
        pattern_row.append(reset)
        box.append(pattern_row)

        preview = Gtk.Label(xalign=0, wrap=True)
        problem = Gtk.Label(xalign=0, wrap=True)
        problem.add_css_class("error")
        hint = Gtk.Label(xalign=0, wrap=True)
        hint.add_css_class("dim-label")
        box.append(Gtk.Label(label=_("Nombre resultante:"), xalign=0))
        box.append(preview)
        box.append(hint)
        box.append(problem)

        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = icon_button(("process-stop-symbolic", "window-close-symbolic"), _("Cancelar"))
        apply = icon_button(("emblem-ok-symbolic", "object-select-symbolic"), _("Renombrar"))
        apply.add_css_class("suggested-action")
        buttons.append(cancel)
        buttons.append(apply)
        box.append(buttons)

        def current_values() -> Values:
            chosen = flag.get_selected()
            return Values(bandera=list(FLAGS.values())[chosen - 1] if chosen else "",
                          **{key: entry.get_text() for key, entry in entries.items()})

        state = {"stem": None}

        def refresh(*_args):
            state["stem"] = None
            try:
                stem = render(pattern.get_text(), current_values())
            except ValueError as error:
                preview.set_text("")
                problem.set_text(str(error))
                apply.set_sensitive(False)
                return
            new = target.with_name(stem + target.suffix)
            preview.set_markup(f"<big><b>{GLib.markup_escape_text(new.name)}</b></big>")
            hint.set_text(_("Sin años del contenido: el nombre llevará solo (años de la edición). Si más adelante "
                          "los averiguas, se completa volviendo a normalizar.")
                          if missing_content_years(pattern.get_text(), current_values()) else "")
            if not stem:
                problem.set_text(_("El nombre resultante está vacío."))
            elif new == target:
                problem.set_text(_("Es el nombre que ya tiene."))
            elif new.exists():
                problem.set_text(_("Ya existe un archivo con ese nombre en la carpeta; no se sobrescribe."))
            else:
                problem.set_text("")
                state["stem"] = stem
            apply.set_sensitive(state["stem"] is not None)

        def do_rename(_button):
            library = Library(LIBRARY_DB) if LIBRARY_DB.exists() else None
            try:
                check_pattern(pattern.get_text())
                new = rename_file(target, state["stem"], RENAME_LOG, library)
            except (OSError, ValueError) as error:
                problem.set_text(_("No se pudo renombrar: {error}").format(error=error))
                return
            self.settings.pattern = pattern.get_text()
            self.settings.save()
            if self.source_file == target:
                self.source_file = new
            if self.selected is not None and self.selected.path == target:
                self.selected.path = new
            self.status.set_text(_("Renombrado: {target_name} → {new_name}").format(target_name=target.name, new_name=new.name))
            self._update_normalize()
            window.close()

        for entry in (*entries.values(), pattern):
            entry.connect("changed", refresh)
        flag.connect("notify::selected", refresh)
        cancel.connect("clicked", lambda _b: window.close())
        apply.connect("clicked", do_rename)
        self.normalizer = {"window": window, "entries": entries, "flag": flag, "pattern": pattern,
                           "preview": preview, "problem": problem, "apply": apply, "hint": hint}   # para las pruebas
        refresh()
        window.present()
        for entry in entries.values():   # sin texto resaltado al abrir
            entry.select_region(0, 0)
        entries["contenido"].grab_focus()   # es el dato que casi siempre hay que poner a mano

    def _button_content(self, text: str):
        content = Gtk.Box(spacing=6)
        content.append(self._icon(COMICVINE_HOST, 16))
        content.append(Gtk.Label(label=text))
        return content

    def _open_original_lookup(self, parent, entries, first_default: str = "", last_default: str = ""):
        """Averigua los años del material original con ComicVine: título original → serie → años."""
        window = Gtk.Window(title=_("Años del material original"), transient_for=parent, modal=True,
                            default_width=560, default_height=460)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12,
                      margin_start=14, margin_end=14)
        window.set_child(box)
        box.append(Gtk.Label(xalign=0, wrap=True, label=(
            _("Escribe el título original (en inglés) y los números americanos que recoge la edición; "
            "los años salen de las fechas de portada de ComicVine."))))
        title = Gtk.Entry(placeholder_text=_("Título original, p. ej. Captain Marvel"), hexpand=True)
        first = Gtk.Entry(placeholder_text=_("Nº inicial"), width_chars=9, text=first_default or (
            entries["numero"].get_text() if "numero" in entries else ""))
        last = Gtk.Entry(placeholder_text=_("Nº final (opcional)"), width_chars=16, text=last_default)
        search = Gtk.Button(child=self._button_content(_("Buscar series")))
        line = Gtk.Box(spacing=8)
        for widget in (first, last, search):
            line.append(widget)
        listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(listing)
        info = Gtk.Label(xalign=0, wrap=True)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = icon_button(("process-stop-symbolic", "window-close-symbolic"), _("Cancelar"))
        use = icon_button(("emblem-ok-symbolic", "object-select-symbolic"), _("Usar estos años"), sensitive=False)
        use.add_css_class("suggested-action")
        buttons.append(cancel)
        buttons.append(use)
        for widget in (title, line, scroll, info, buttons):
            box.append(widget)

        volumes: list = []
        key = self.settings.api_key.strip()
        if not key:
            info.set_text(_("Necesitas la clave gratuita de ComicVine (pestaña Ajustes) para esta búsqueda."))
            search.set_sensitive(False)

        def fail(error):
            info.set_text(str(error))
            search.set_sensitive(True)

        def search_done(found):
            volumes[:] = found
            while (row := listing.get_first_child()) is not None:
                listing.remove(row)
            for volume in found:
                listing.append(Gtk.Label(label=volume.label, xalign=0, margin_top=4, margin_bottom=4,
                                         margin_start=6))
            info.set_text(_("{found_count} serie(s). Elige la que recoge tu edición.").format(found_count=len(found)) if found
                          else _("ComicVine no encuentra esa serie: prueba con el título original en inglés."))
            search.set_sensitive(True)

        def do_search(_widget):
            search.set_sensitive(False)
            info.set_text(_("Buscando en ComicVine…"))

            def work():
                try:
                    found = find_volumes(ComicVineClient(key), title.get_text())
                except (ComicVineError, ValueError) as error:
                    later(fail, error)
                else:
                    later(search_done, found)
            Thread(target=work, daemon=True).start()

        def do_use(_widget):
            row = listing.get_selected_row()
            if row is None:
                return
            volume = volumes[row.get_index()]
            use.set_sensitive(False)
            info.set_text(_("Consultando las fechas de portada…"))

            def work():
                try:
                    years = content_years(ComicVineClient(key), volume.id, first.get_text(), last.get_text())
                except (ComicVineError, LookupError, ValueError) as error:
                    later(lambda e=error: (info.set_text(str(e)), use.set_sensitive(True)))
                else:
                    later(finish, years, volume)
            Thread(target=work, daemon=True).start()

        def finish(years, volume):
            entries["contenido"].set_text(years)
            self.status.set_text(_("Años del contenido: {years} (portadas de {volume_name} {volume_start_year} en ComicVine).").format(years=years, volume_name=volume.name, volume_start_year=volume.start_year))
            window.close()

        search.connect("clicked", do_search)
        title.connect("activate", do_search)
        listing.connect("row-selected", lambda _l, row: use.set_sensitive(row is not None))
        cancel.connect("clicked", lambda _b: window.close())
        use.connect("clicked", do_use)
        self.lookup = {"window": window, "title": title, "first": first, "last": last, "search": search,
                       "listing": listing, "use": use, "info": info}   # para las pruebas
        window.present()
        title.grab_focus()

    # ---- Normalizar una carpeta-serie y renumerar su contenido --------------------------------
    def _choose_series_folder(self, _button):
        Gtk.FileDialog(title=_("Carpeta de la serie")).select_folder(self, None, self._series_folder_chosen)

    def _series_folder_chosen(self, dialog, result):
        try:
            folder = Path(dialog.select_folder_finish(result).get_path())
        except GLib.Error:
            return
        self._start_series_normalizer(folder)

    def _start_series_normalizer(self, folder: Path):
        files = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in COMIC_EXTENSIONS),
                       key=lambda p: natural_key(p.name))
        if not files:
            self.status.set_text(_("No hay archivos CBR/CBZ directamente en {folder_name}.").format(folder_name=folder.name))
            return
        info, gcd = None, self._gcd()
        if gcd is not None and self.selected is not None and self.selected.series_id:
            info = gcd.series_info(self.selected.series_id)
        if info is not None:
            values, from_gcd = series_values(info), True
        else:   # sin serie de GCD elegida: lo tecleado, o el nombre de la carpeta
            title, _number, _publisher, year = self._fields()
            values, from_gcd = Values(nombre=title or folder.name, edicion=year), False
        self._open_series_normalizer(folder, files, values, from_gcd)

    def _open_series_normalizer(self, folder: Path, files: list[Path], values: Values, from_gcd: bool):
        window = Gtk.Window(title=_("Normalizar carpeta"), transient_for=self, modal=True, default_width=900,
                            default_height=760)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12,
                      margin_start=14, margin_end=14)
        window.set_child(box)
        head = Gtk.Label(xalign=0, wrap=True)
        head.set_markup(_("<b>Carpeta:</b> {markup_escape_text}  ({files_count} archivos)").format(markup_escape_text=GLib.markup_escape_text(str(folder)), files_count=len(files)))
        box.append(head)

        detected = [(path, *detect_number(path.stem)) for path in files]
        numbers = [int(n) for _p, n, _d in detected if n]
        grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        entries: dict[str, Gtk.Entry] = {}
        flag = Gtk.DropDown.new_from_strings([_("(ninguna)"), *FLAGS.values()])
        flag.set_selected(([""] + list(FLAGS.values())).index(values.bandera)
                          if values.bandera in FLAGS.values() else 0)
        fields = (("nombre", _("Nombre (serie)"), ""), ("volumen", _("Volumen"), _("8 → «Volumen 8»")), ("bandera", _("Bandera"), ""),
                  ("contenido", _("Contenido [años]"), _("años del material original: 1999-2001")),
                  ("edicion", _("Edición (años)"), _("2000-2002; 2011- si sigue publicándose")),
                  ("editorial", _("Editorial"), _("quién la publica: Planeta DeAgostini, Panini…")),
                  ("sello", _("Sello"), _("solo el que ves impreso en los ejemplares")))
        for row, (key, label, hint) in enumerate(fields):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
            widget = flag if key == "bandera" else Gtk.Entry(text=getattr(values, key), hexpand=True,
                                                              placeholder_text=hint)
            if key != "bandera":
                entries[key] = widget
            grid.attach(widget, 1, row, 1, 1)
            if key == "contenido":
                find = icon_button(("system-search-symbolic",), _("Buscar en ComicVine…"), tooltip_text=(
                    _("Averigua los años del material original a partir del título original y los números")))
                find.connect("clicked", lambda _b: self._open_original_lookup(
                    window, entries, str(min(numbers)) if numbers else "",
                    str(max(numbers)) if len(numbers) > 1 else ""))
                grid.attach(find, 2, row, 1, 1)
        box.append(grid)
        if from_gcd:
            note = Gtk.Label(xalign=0, wrap=True, label=(
                _("Nombre, país, años de la serie y sello vienen de GCD (transcritos por otro colaborador): "
                "compruébalos. Los años del contenido original no se saben solos: ponlos tú o búscalos en ComicVine.")))
            note.add_css_class("dim-label")
            box.append(note)

        box.append(Gtk.Label(label=_("Patrón de la carpeta:"), xalign=0))
        folder_pattern = Gtk.Entry(text=self.settings.pattern, hexpand=True)
        box.append(folder_pattern)
        box.append(Gtk.Label(xalign=0, wrap=True, label=(
            _("Cada archivo se llamará como la carpeta resultante más « #01», « #02»… Se usa el número que ya trae "
            "cada nombre, así que los huecos se respetan."))))

        result = Gtk.Label(xalign=0, wrap=True)
        box.append(Gtk.Label(label=_("Carpeta resultante:"), xalign=0))
        box.append(result)

        listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        rows = []
        for path, number, doubtful in detected:
            line = Gtk.Box(spacing=8, margin_top=3, margin_bottom=3, margin_start=6, margin_end=6)
            include = Gtk.CheckButton(active=True, tooltip_text=_("Renombrar este archivo"))
            old = Gtk.Label(label=path.name, xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.MIDDLE,
                            width_chars=28, max_width_chars=40)
            entry = Gtk.Entry(text=str(int(number)) if number else "", width_chars=5, placeholder_text=_("Nº"),
                              tooltip_text=_("Número de ejemplar de este archivo"))
            new = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.MIDDLE, width_chars=28,
                            max_width_chars=44)
            note = Gtk.Label(xalign=0, width_chars=22)
            for widget in (include, old, entry, Gtk.Label(label="→"), new, note):
                line.append(widget)
            listing.append(line)
            rows.append({"path": path, "include": include, "entry": entry, "new": new, "note": note,
                         "doubtful": doubtful, "name": None, "number": None})
        scroll = Gtk.ScrolledWindow(vexpand=True, min_content_height=240)
        scroll.set_child(listing)
        box.append(scroll)
        summary = Gtk.Label(xalign=0, wrap=True)
        problem = Gtk.Label(xalign=0, wrap=True)
        problem.add_css_class("error")
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = icon_button(("process-stop-symbolic", "window-close-symbolic"), _("Cancelar"))
        apply = icon_button(("emblem-ok-symbolic", "object-select-symbolic"), _("Renombrar carpeta y archivos"))
        apply.add_css_class("suggested-action")
        for widget in (cancel, apply):
            buttons.append(widget)
        for widget in (summary, problem, buttons):
            box.append(widget)

        state = {"folder_stem": None}

        def current_values() -> Values:
            chosen = flag.get_selected()
            return Values(bandera=list(FLAGS.values())[chosen - 1] if chosen else "",
                          **{key: entry.get_text() for key, entry in entries.items()})

        def refresh(*_args):
            blocking, state["folder_stem"] = [], None
            try:
                folder_stem = render(folder_pattern.get_text(), current_values())
            except ValueError as error:
                result.set_text("")
                problem.set_text(str(error))
                apply.set_sensitive(False)
                return
            new_folder = folder.with_name(folder_stem) if folder_stem else folder
            result.set_markup(f"<big><b>{GLib.markup_escape_text(new_folder.name)}</b></big>")
            if not folder_stem:
                blocking.append(_("El nombre de la carpeta resultante está vacío."))
            elif new_folder != folder and new_folder.exists():
                blocking.append(_("Ya existe una carpeta llamada «{new_folder_name}».").format(new_folder_name=new_folder.name))
            included = [r for r in rows if r["include"].get_active()]
            for r in rows:
                text = r["entry"].get_text().strip()
                r["number"] = int(text) if text.isdigit() else None
            width = number_width([r["number"] for r in included if r["number"] is not None])
            moving = {r["path"].name for r in included}
            taken: dict[str, int] = {}
            for r in rows:
                r["name"], message = None, ""
                if not r["include"].get_active():
                    r["new"].set_text(_("(no se renombra)"))
                elif r["number"] is None:
                    r["new"].set_text("—")
                    message = _("Sin número")
                    blocking.append(_("{name}: escribe su número o exclúyelo.").format(name=r['path'].name))
                else:
                    if not folder_stem:
                        message = _("Nombre vacío")
                    else:
                        r["name"] = f"{folder_stem} #{pad_number(r['number'], width)}{r['path'].suffix}"
                        if len(r["name"].encode()) > MAX_NAME_BYTES:
                            message = _("Nombre demasiado largo")
                            blocking.append(_("El nombre de los archivos es demasiado largo para el sistema de archivos."))
                        r["new"].set_text(r["name"])
                        taken[r["name"]] = taken.get(r["name"], 0) + 1
                        message = _("revisa el número") if r["doubtful"] else ""
                r["note"].set_text(message)
            existing = {p.name for p in folder.iterdir()}
            for r in rows:
                if r["name"] is None:
                    continue
                if taken[r["name"]] > 1:
                    r["note"].set_text(_("Repetido"))
                    blocking.append(_("Hay varios archivos con el número de «{r}».").format(r=r['name']))
                elif r["name"] in existing and r["name"] not in moving:
                    r["note"].set_text(_("Ya existe"))
                    blocking.append(_("«{r}» ya existe y no forma parte del lote.").format(r=r['name']))
            changes = [r for r in rows if r["name"] and r["name"] != r["path"].name]
            summary.set_text(_("{changes_count} archivo(s) se renombran · {sum} ya tienen ese nombre · {sum_2} sin tocar").format(changes_count=len(changes), sum=sum(1 for r in rows if r['name'] == r['path'].name), sum_2=sum(1 for r in rows if not r['include'].get_active())))
            extra = _(" (y {blocking_count} problema(s) más)").format(blocking_count=len(blocking) - 1) if len(blocking) > 1 else ""
            problem.set_text(blocking[0] + extra if blocking else "")
            apply.set_sensitive(not blocking and (bool(changes) or new_folder != folder))
            state["folder_stem"] = folder_stem

        def do_apply(_button):
            library = Library(LIBRARY_DB) if LIBRARY_DB.exists() else None
            moves = [(r["path"], folder / r["name"]) for r in rows if r["name"] and r["name"] != r["path"].name]
            try:
                new_folder = rename_series(folder, state["folder_stem"], moves, RENAME_LOG, library)
            except (OSError, ValueError) as error:
                problem.set_text(_("No se pudo renombrar (no se ha cambiado nada): {error}").format(error=error))
                return
            self.settings.pattern = folder_pattern.get_text()
            self.settings.save()
            if self.source_file is not None and folder in self.source_file.parents:
                renamed = dict(moves).get(self.source_file, self.source_file)
                self.source_file = new_folder / renamed.name
            self.status.set_text(_("Carpeta renombrada a «{new_folder_name}» y {moves_count} archivo(s) renumerados.").format(new_folder_name=new_folder.name, moves_count=len(moves)))
            self._update_normalize()
            window.close()

        for entry in (*entries.values(), folder_pattern, *(r["entry"] for r in rows)):
            entry.connect("changed", refresh)
        for r in rows:
            r["include"].connect("toggled", refresh)
        flag.connect("notify::selected", refresh)
        cancel.connect("clicked", lambda _b: window.close())
        apply.connect("clicked", do_apply)
        self.series_normalizer = {"window": window, "entries": entries, "flag": flag, "rows": rows, "result": result,
                                  "summary": summary, "problem": problem, "apply": apply,
                                  "folder_pattern": folder_pattern}   # para las pruebas
        refresh()
        window.present()
        for entry in entries.values():   # sin texto resaltado al abrir
            entry.select_region(0, 0)
        entries["contenido"].grab_focus()

    # ---- Metadatos (ComicInfo.xml) de una carpeta o de un archivo ----------------------------
    def _undo_rename(self, _button):
        library = Library(LIBRARY_DB) if LIBRARY_DB.exists() else None
        try:
            pairs = undo_last(RENAME_LOG, library)
        except (OSError, LookupError, ValueError) as error:
            self.undo_info.set_text(_("No se pudo deshacer: {error}").format(error=error))
            return
        for current, original in pairs:
            if self.source_file == current:
                self.source_file = original
        first, last = pairs[0], pairs[-1]
        self.undo_info.set_text(_("Deshecho: {name} → {name_2}").format(name=first[0].name, name_2=first[1].name) if len(pairs) == 1 else
                                _("Deshecho un lote de {pairs_count} renombrado(s), el último: {name} → {name_2}").format(pairs_count=len(pairs), name=last[0].name, name_2=last[1].name))
        self._update_normalize()

    # ---- Asistente de IA: terminal embebido con la CLI del usuario, en el panel --------------
