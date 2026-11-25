"""Pestaña «Ajustes»: claves, fuentes, tema, idioma, acerca de."""
import json
import os
import sys
from pathlib import Path
from threading import Thread

from .. import __version__
from ..assistant import PROMPT
from ..gcd import GcdIndex, build_index
from ..i18n import _
from ..settings import (
    GCD_DB,
    TEBEOSFERA_DB,
    UNIVERSOMARVEL_DB,
    Settings,
)
from ..tebeosfera import TebeosferaError, TebeosferaIndex
from ..tebeosfera import build_index as build_tebeosfera_index
from ..universomarvel import (
    UniversoMarvelError,
    UniversoMarvelIndex,
)
from ..universomarvel import build_index as build_marvel_index
from .constants import (
    AUTHOR,
    AUTHOR_EMAIL,
    COMICVINE_API_URL,
    COMICVINE_HOST,
    GCD_DOWNLOAD_URL,
    GCD_HOST,
    GCD_SITE,
    REPO_URL,
    RESTORE_VARIABLE,
)
from .widgets import (
    GLib,
    Gtk,
    icon_button,
    later,
    theme_state,
)


class SettingsMixin:
    def _about(self, _button):
        about = Gtk.AboutDialog(
            transient_for=self, modal=True, program_name="Comic Identify", version=__version__,
            logo_icon_name="comic-identify", authors=[f"{AUTHOR} <{AUTHOR_EMAIL}>"], copyright=f"© 2026 {AUTHOR}",
            comments=(_("Identifica un cómic a partir de su portada, normaliza los nombres de archivos y carpetas y "
                      "escribe metadatos ComicInfo.xml.")),
            website=REPO_URL, website_label=REPO_URL.removeprefix("https://"),
            license_type=Gtk.License.GPL_3_0, translator_credits=_("translator-credits"))
        about.add_credit_section(_("Datos de terceros"), [
            "Grand Comics Database (CC BY-SA 4.0) https://www.comics.org/",
            "Comic Vine https://comicvine.gamespot.com/",
            "Universo Marvel https://fichas.universomarvel.com/",
            "Tebeosfera (textos CC BY-SA 4.0) https://www.tebeosfera.com/"])
        about.present()

    def _credit(self, host: str, title: str, text: str, url: str):
        """Logo, nombre, qué aporta y enlace de una de las fuentes de datos."""
        row = Gtk.Box(spacing=12)
        row.append(self._icon(host, 32))
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        heading = Gtk.Label(xalign=0)
        heading.set_markup(f"<b>{GLib.markup_escape_text(title)}</b>")
        body = Gtk.Label(label=text, xalign=0, wrap=True)
        link = Gtk.LinkButton(uri=url, label=url.removeprefix("https://").rstrip("/"), halign=Gtk.Align.START)
        for widget in (heading, body, link):
            column.append(widget)
        row.append(column)
        return row

    def _settings_page(self):
        page = self._box()
        self._settings_credits(page)
        self._settings_comicvine(page)
        self._settings_gcd(page)
        self._settings_theme(page)
        self._settings_language(page)
        self._settings_marvel(page)
        self._settings_tebeosfera(page)
        self._settings_assistant(page)
        self._settings_undo(page)
        self._settings_gcstar(page)
        self._settings_backup(page)
        scroll = Gtk.ScrolledWindow()   # la página es más alta que la ventana
        scroll.set_child(page)
        return scroll

    def _settings_credits(self, page):
        """Cabecera de Ajustes: «Acerca de» y los créditos de las fuentes."""
        about = icon_button(("help-about-symbolic", "dialog-information-symbolic"), _("Acerca de…"),
                            halign=Gtk.Align.END, tooltip_text=_("Versión, autor, licencia y datos de terceros"))
        about.connect("clicked", self._about)
        page.append(about)   # arriba: la página es larga y así se ve al entrar
        page.append(Gtk.Label(xalign=0, wrap=True, label=(
            _("Esta aplicación se apoya en el trabajo de cuatro comunidades de colaboradores, que son las que "
            "han hecho el trabajo duro:"))))
        page.append(self._credit(COMICVINE_HOST, "Comic Vine", (
            _("Enciclopedia colaborativa de cómics con una API gratuita. Aporta series, números y portadas, "
            "que la aplicación compara visualmente con la tuya; es más fuerte en ediciones americanas.")),
            "https://comicvine.gamespot.com/"))
        page.append(self._credit(GCD_HOST, "Grand Comics Database (GCD)", (
            _("Base de datos abierta y colaborativa de cómics de todo el mundo, mantenida por voluntarios. "
            "De ella sale el índice de ediciones en español (España y Latinoamérica): títulos, números, "
            "editoriales y sellos. Datos con licencia CC BY-SA 4.0.")), GCD_SITE))
        page.append(self._credit("fichas.universomarvel.com", "Universo Marvel", (
            _("Catálogo, mantenido por sus autores, de las ediciones españolas de Marvel de 31 editoriales (Forum/"
            "Planeta, Panini, Vértice, Bruguera, Zinco…): fecha, precio, páginas, créditos, comentarios y el "
            "ejemplar USA original de cada número. De él salen las fichas que consultas, una a una, y los "
            "logotipos de algunas editoriales.")), "https://fichas.universomarvel.com/"))
        page.append(self._credit("www.tebeosfera.com", "Tebeosfera", (
            _("El gran catálogo de la historieta editada en España, de todas las editoriales y épocas, hecho por "
            "la Asociación Cultural Tebeosfera y sus colaboradores. De él salen las colecciones y las fichas de "
            "cada ejemplar: fecha, precio, créditos, géneros, ISBN y portada. Sus textos tienen licencia "
            "CC BY-SA 4.0 y las imágenes son de sus titulares.")), "https://www.tebeosfera.com/"))

    def _settings_comicvine(self, page):
        """Clave de la API de ComicVine."""
        page.append(Gtk.Separator(margin_top=6, margin_bottom=6))
        page.append(Gtk.Label(label=_("Clave de la API de ComicVine (gratuita):"), xalign=0))
        self.key = Gtk.PasswordEntry(show_peek_icon=True, text=self.settings.api_key)
        save = icon_button(("document-save-symbolic",), _("Guardar"), halign=Gtk.Align.START)
        save.connect("clicked", self._save_key)
        self.key_info = Gtk.Label(xalign=0)
        for widget in (self.key, save, Gtk.LinkButton(uri=COMICVINE_API_URL, label=_("Obtener una clave"),
                                                      halign=Gtk.Align.START), self.key_info):
            page.append(widget)

    def _settings_gcd(self, page):
        """Volcado de GCD."""
        page.append(Gtk.Separator(margin_top=6, margin_bottom=6))
        page.append(Gtk.Label(xalign=0, wrap=True, label=(
            _("Grand Comics Database (ediciones en español, sin límites ni conexión). Descarga el volcado "
            "SQLite desde comics.org (requiere cuenta gratuita), descomprímelo e impórtalo aquí una vez."))))
        self.gcd_button = icon_button(("document-open-symbolic", "folder-download-symbolic"),
                                      _("Importar volcado de GCD…"), halign=Gtk.Align.START)
        self.gcd_button.connect("clicked", self._choose_gcd)
        self.gcd_info = Gtk.Label(xalign=0, wrap=True)
        attribution = Gtk.LinkButton(uri="https://www.comics.org/", halign=Gtk.Align.START,
                                     label=_("Datos de Grand Comics Database (CC BY-SA 4.0)"))
        for widget in (Gtk.LinkButton(uri=GCD_DOWNLOAD_URL, label=_("Descargar el volcado"),
                                      halign=Gtk.Align.START), self.gcd_button, self.gcd_info, attribution):
            page.append(widget)
        self._refresh_gcd()

    def _settings_theme(self, page):
        """Tema Sistema/Claro/Oscuro."""
        page.append(Gtk.Separator(margin_top=6, margin_bottom=6))
        page.append(Gtk.Label(xalign=0, wrap=True, label=(
            _("Tema: claro (iconos de color de tu tema), oscuro (iconos simbólicos) o el del sistema. Se recuerda al "
            "reiniciar; cambiarlo reinicia la aplicación conservando el cómic abierto y los campos."))))
        theme_buttons = Gtk.Box(spacing=8, halign=Gtk.Align.START)
        self.theme_buttons = {}
        for dark, text, icons in ((False, _("Claro"), ("weather-clear",)), (True, _("Oscuro"), ("weather-clear-night",)),
                                   (None, _("Sistema"), ("preferences-desktop-theme",))):
            button = icon_button(icons, text)
            button.connect("clicked", lambda _b, d=dark: self._set_theme(d))
            self.theme_buttons[dark] = button
            theme_buttons.append(button)
        self.theme_info = Gtk.Label(xalign=0, wrap=True)
        for widget in (theme_buttons, self.theme_info):
            page.append(widget)
        self._refresh_theme_info()

    def _settings_language(self, page):
        """Selector de idioma."""
        page.append(Gtk.Separator(margin_top=6, margin_bottom=6))
        page.append(Gtk.Label(xalign=0, wrap=True, label=_(
            "Idioma: el del sistema o uno fijo. Cambiarlo reinicia la aplicación conservando el cómic abierto y los campos.")))
        language_buttons = Gtk.Box(spacing=8, halign=Gtk.Align.START)
        self.language_buttons = {}
        for code, text in ((None, _("Sistema")), ("es", "Español"), ("en", "English")):
            button = icon_button(("preferences-desktop-locale", "preferences-desktop-language"), text)
            button.connect("clicked", lambda _b, c=code: self._set_language(c))
            self.language_buttons[code] = button
            language_buttons.append(button)
        self.language_info = Gtk.Label(xalign=0, wrap=True)
        for widget in (language_buttons, self.language_info):
            page.append(widget)
        self._refresh_language_info()

    def _settings_marvel(self, page):
        """Índice de Universo Marvel."""
        page.append(Gtk.Separator(margin_top=6, margin_bottom=6))
        page.append(Gtk.Label(xalign=0, wrap=True, label=(
            _("Universo Marvel (fichas.universomarvel.com): catálogo de las ediciones españolas de Marvel (Forum/"
            "Planeta, Panini, Vértice, Bruguera y otras 27 editoriales). Es una web personal, así que no se rastrea: "
            "se descarga el índice de series (una petición por editorial, espaciadas: casi un minuto) para buscar al escribir y, al elegir una serie con su número "
            "escrito, solo la ficha de ese ejemplar, una vez; queda guardada en la base local."))))
        self.marvel_button = icon_button(("folder-download-symbolic", "document-save-symbolic"),
                                         _("Descargar el índice de Universo Marvel"), halign=Gtk.Align.START)
        self.marvel_button.connect("clicked", self._download_marvel)
        self.marvel_info = Gtk.Label(xalign=0, wrap=True)
        self.marvel_progress = Gtk.ProgressBar(visible=False)   # pulsa mientras se descarga el índice
        self._marvel_pulse_id = 0
        for widget in (self.marvel_button, self.marvel_progress, self.marvel_info):
            page.append(widget)
        self._refresh_marvel()

    def _settings_tebeosfera(self, page):
        """Índice de Tebeosfera."""
        page.append(Gtk.Separator(margin_top=6, margin_bottom=6))
        page.append(Gtk.Label(xalign=0, wrap=True, label=(
            _("Tebeosfera (www.tebeosfera.com): el catálogo de la historieta editada en España, de todas las editoriales "
            "(Panini, ECC, Norma, Planeta, Zinco, Forum, Vértice…). Es el proyecto de una asociación cultural, así "
            "que no se rastrea: el índice sale de sus sitemaps públicos (unas 13 peticiones espaciadas, unos 20 "
            "segundos) para buscar al escribir y, al elegir una colección con su número escrito, solo la ficha "
            "de ese ejemplar, una vez; queda guardada en la base local. Las imágenes son de sus titulares."))))
        self.tebeosfera_button = icon_button(("folder-download-symbolic", "document-save-symbolic"),
                                             _("Descargar el índice de Tebeosfera"), halign=Gtk.Align.START)
        self.tebeosfera_button.connect("clicked", self._download_tebeosfera)
        self.tebeosfera_info = Gtk.Label(xalign=0, wrap=True)
        self.tebeosfera_progress = Gtk.ProgressBar(visible=False)
        self._tebeosfera_pulse_id = 0
        for widget in (self.tebeosfera_button, self.tebeosfera_progress, self.tebeosfera_info):
            page.append(widget)
        self._refresh_tebeosfera()

    def _settings_assistant(self, page):
        """Comando y mensaje del asistente de IA."""
        page.append(Gtk.Separator(margin_top=6, margin_bottom=6))
        page.append(Gtk.Label(xalign=0, wrap=True, label=(
            _("Asistente de IA (botón «Preguntar a la IA»): comando que se abre en un terminal con tu propia "
            "sesión. {{prompt}} se sustituye por el mensaje. Ejemplos: «claude {{prompt}}», «codex {{prompt}}», "
            "«opencode --prompt {{prompt}}».").format())))
        self.assistant_entry = Gtk.Entry(text=self.settings.assistant)
        page.append(self.assistant_entry)
        page.append(Gtk.Label(xalign=0, wrap=True, label=(
            _("Mensaje que sustituye a {{prompt}} ({{image}} es la portada que se le pasa). Se puede cambiar para "
            "pedirle otras cosas o usar otras webs:").format())))
        self.prompt_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD, top_margin=6, bottom_margin=6, left_margin=8,
                                        right_margin=8)
        self.prompt_view.get_buffer().set_text(self.settings.prompt)
        prompt_scroll = Gtk.ScrolledWindow(min_content_height=130, max_content_height=220,
                                           propagate_natural_height=True, has_frame=True)
        prompt_scroll.set_child(self.prompt_view)
        save_command = icon_button(("document-save-symbolic",), _("Guardar comando y mensaje"))
        save_command.connect("clicked", self._save_assistant)
        reset_prompt = icon_button(("edit-undo-symbolic", "view-refresh-symbolic"), _("Restablecer el mensaje"),
                                   tooltip_text=_("Vuelve al mensaje que trae la aplicación"))
        reset_prompt.connect("clicked", lambda _b: self.prompt_view.get_buffer().set_text(PROMPT))
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.START)
        buttons.append(save_command)
        buttons.append(reset_prompt)
        self.assistant_info = Gtk.Label(xalign=0, wrap=True)
        for widget in (prompt_scroll, buttons, self.assistant_info):
            page.append(widget)

    def _settings_undo(self, page):
        """Deshacer renombrados y metadatos."""
        page.append(Gtk.Separator(margin_top=6, margin_bottom=6))
        page.append(Gtk.Label(xalign=0, wrap=True, label=(
            _("Normalización de nombres: cada renombrado queda registrado y se puede deshacer, de uno en uno, "
            "del último al primero."))))
        undo = icon_button(("edit-undo-symbolic", "view-refresh-symbolic"), _("Deshacer el último renombrado"),
                           halign=Gtk.Align.START)
        undo.connect("clicked", self._undo_rename)
        self.undo_info = Gtk.Label(xalign=0, wrap=True)
        for widget in (undo, self.undo_info):
            page.append(widget)
        page.append(Gtk.Label(xalign=0, wrap=True, label=(
            _("Metadatos: cada escritura queda registrada con el ComicInfo.xml anterior. Deshacer revierte el último "
            "lote entero, sin pisar archivos que se hayan modificado o movido después."))))
        self.metadata_undo_button = icon_button(("edit-undo-symbolic", "view-refresh-symbolic"),
                                                _("Deshacer el último lote de metadatos"), halign=Gtk.Align.START)
        self.metadata_undo_button.connect("clicked", self._undo_metadata)
        self.metadata_undo_info = Gtk.Label(xalign=0, wrap=True)
        for widget in (self.metadata_undo_button, self.metadata_undo_info):
            page.append(widget)

    def _settings_gcstar(self, page):
        """Ruta de la colección de GCstar."""
        page.append(Gtk.Separator(margin_top=6, margin_bottom=6))
        page.append(Gtk.Label(xalign=0, wrap=True, label=(
            _("Transferir a GCstar (botón «Transferir a GCstar…»): añade el cómic a una colección de GCstar sin "
            "tocar el resto de su archivo .gcs, con su portada y contraportada junto a él, con la misma "
            "convención de nombres que ya uses. Necesita que la carpeta del cómic esté en «Mi colección», "
            "arriba, para saber dónde ponerlas."))))
        self.gcstar_entry = Gtk.Entry(text=self.settings.gcstar_path, hexpand=True,
                                      placeholder_text=_("Archivo .gcs de tu colección"))
        choose_gcstar = icon_button(("document-open-symbolic", "folder-open-symbolic"), _("Elegir archivo .gcs…"))
        choose_gcstar.connect("clicked", self._choose_gcstar)
        gcstar_line = Gtk.Box(spacing=8)
        gcstar_line.append(self.gcstar_entry)
        gcstar_line.append(choose_gcstar)
        save_gcstar = icon_button(("document-save-symbolic",), _("Guardar"), halign=Gtk.Align.START)
        save_gcstar.connect("clicked", self._save_gcstar_path)
        self.gcstar_undo_button = icon_button(("edit-undo-symbolic", "view-refresh-symbolic"),
                                              _("Deshacer la última transferencia a GCstar"), halign=Gtk.Align.START)
        self.gcstar_undo_button.connect("clicked", self._undo_gcstar)
        self.gcstar_info = Gtk.Label(xalign=0, wrap=True)
        for widget in (gcstar_line, save_gcstar, self.gcstar_undo_button, self.gcstar_info):
            page.append(widget)

    def _settings_backup(self, page):
        """Copias de seguridad."""
        page.append(Gtk.Separator(margin_top=6, margin_bottom=6))
        page.append(Gtk.Label(xalign=0, wrap=True, label=(
            _("Copias de seguridad: guardan tus índices (colección y GCD), los ajustes y los registros de deshacer "
            "en un .zip verificado. Se hace una automática al cerrar la aplicación (solo si algo ha cambiado) y "
            "las que quieras a mano. Las automáticas más antiguas se borran; las manuales, nunca. Ojo: el zip "
            "incluye tu clave de ComicVine."))))
        self.backup_entry = Gtk.Entry(text=self.settings.backup_dir, hexpand=True,
                                      placeholder_text=_("Carpeta donde guardar las copias"))
        choose_backup = icon_button(("folder-open-symbolic", "document-open-symbolic"), _("Elegir carpeta…"))
        choose_backup.connect("clicked", self._choose_backup_dir)
        backup_line = Gtk.Box(spacing=8)
        backup_line.append(self.backup_entry)
        backup_line.append(choose_backup)
        self.backup_keep = Gtk.SpinButton.new_with_range(1, 99, 1)
        self.backup_keep.set_value(self.settings.backup_keep)
        keep_line = Gtk.Box(spacing=8)
        keep_line.append(Gtk.Label(label=_("Copias automáticas que se conservan:")))
        keep_line.append(self.backup_keep)
        save_backup = icon_button(("document-save-symbolic",), _("Guardar"), halign=Gtk.Align.START)
        save_backup.connect("clicked", self._save_backup_settings)
        self.backup_now_button = icon_button(("document-save-as-symbolic", "document-save-symbolic"),
                                             _("Copiar ahora"))
        self.backup_now_button.connect("clicked", self._backup_now)
        self.backup_restore_button = icon_button(("document-revert-symbolic", "edit-undo-symbolic"),
                                                 _("Restaurar una copia…"))
        self.backup_restore_button.connect("clicked", self._open_restore)
        backup_buttons = Gtk.Box(spacing=8, halign=Gtk.Align.START)
        backup_buttons.append(save_backup)
        backup_buttons.append(self.backup_now_button)
        backup_buttons.append(self.backup_restore_button)
        self.backup_info = Gtk.Label(xalign=0, wrap=True)
        for widget in (backup_line, keep_line, backup_buttons, self.backup_info):
            page.append(widget)
        self._refresh_backup_info()


    # ---- Copias de seguridad ------------------------------------------------------------------
    def _reload_settings(self):
        """Tras restaurar: los ajustes vuelven a leerse del archivo y los campos de Ajustes los reflejan (si no,
        el siguiente «Guardar» escribiría encima lo que había antes de restaurar)."""
        self.settings = Settings.load()
        self.key.set_text(self.settings.api_key)
        self.assistant_entry.set_text(self.settings.assistant)
        self.prompt_view.get_buffer().set_text(self.settings.prompt)
        self.gcstar_entry.set_text(self.settings.gcstar_path)
        self.backup_entry.set_text(self.settings.backup_dir)
        self.backup_keep.set_value(self.settings.backup_keep)
        self._update_normalize()

    def _refresh_gcd(self):
        index = GcdIndex(GCD_DB)
        if index.is_ready():
            series, issues = index.counts()
            self.gcd_info.set_text(_("Índice de GCD: {series} series y {issues} números.").format(series=series, issues=issues) + (
                "" if index.has_details() else _(" Es de una versión anterior y no trae los créditos, el género ni los "
                "personajes de cada número: vuelve a importar el volcado para tenerlos (tarda unos segundos).")))
        elif GCD_DB.exists():
            self.gcd_info.set_text(_("El índice de GCD es de una versión anterior: vuelve a importar el "
                                   "volcado para actualizarlo (tarda unos segundos)."))
        else:
            self.gcd_info.set_text(_("Todavía no has importado el volcado de GCD."))

    def _refresh_theme_info(self):
        mode = _("oscuro") if theme_state["dark"] else _("claro")
        origin = _("elegido") if self.settings.dark_mode is not None else _("el del sistema")
        self.theme_info.set_text(_("Tema actual: {mode} ({origin}).").format(mode=mode, origin=origin))
        for dark, button in self.theme_buttons.items():
            button.set_sensitive(dark != self.settings.dark_mode)

    def _refresh_language_info(self):
        names = {"es": "Español", "en": "English"}
        current = names.get(self.settings.language, _("Sistema"))
        self.language_info.set_text(_("Idioma actual: {language}.").format(language=current))
        for code, button in self.language_buttons.items():
            button.set_sensitive(code != self.settings.language)

    def _set_language(self, code: str | None):
        """Guarda el idioma y reinicia el proceso para aplicarlo, con el mismo cómic abierto y los mismos campos."""
        if self.indexing:
            self.language_info.set_text(_("Hay una indexación en marcha: espera a que termine para cambiar el idioma."))
            return
        self.settings.language = code
        self.settings.save()
        self._restart()

    def _set_theme(self, dark: bool | None):
        """Guarda el tema y reinicia el proceso para aplicarlo (Cinnamon/Mint no repinta una ventana ya presentada),
        con el mismo cómic abierto y los mismos campos."""
        if self.indexing:
            self.theme_info.set_text(_("Hay una indexación en marcha: espera a que termine para cambiar el tema."))
            return
        self.settings.dark_mode = dark
        self.settings.save()
        self._restart()

    def _restart(self):
        state = {"fields": list(self._fields()), "file": str(self.source_file) if self.source_file else "",
                 "page": self.notebook.get_current_page()}
        os.execve("/proc/self/exe", sys.orig_argv, {**os.environ, RESTORE_VARIABLE: json.dumps(state)})

    def _restore_session(self):
        """Tras reiniciar por un cambio de tema: el cómic y los campos que había."""
        raw = os.environ.pop(RESTORE_VARIABLE, "")
        if not raw:
            return
        try:
            state = json.loads(raw)
        except ValueError:
            return
        title, number, publisher, year = (list(state.get("fields", [])) + ["", "", "", ""])[:4]
        self._set_fields(str(title), str(number), str(publisher), str(year))
        if state.get("file") and Path(state["file"]).exists():
            self._load(Path(state["file"]))
        self.notebook.set_current_page(int(state.get("page", 0)))

    def _refresh_marvel(self):
        index = UniversoMarvelIndex(UNIVERSOMARVEL_DB)
        if index.is_ready():
            counts = index.counts()
            self.marvel_info.set_text(_("Índice de Universo Marvel: {sum} series (").format(sum=sum(counts.values()))
                                      + ", ".join(f"{name}: {number}" for name, number in counts.items()) + ").")
        else:
            self.marvel_info.set_text(_("Todavía no has descargado el índice de Universo Marvel."))

    def _download_marvel(self, _button):
        self.marvel_button.set_sensitive(False)
        self.marvel_progress.set_visible(True)
        self.marvel_progress.pulse()
        self._marvel_pulse_id = GLib.timeout_add(150, lambda: (self.marvel_progress.pulse(), True)[1])

        def run():
            try:
                build_marvel_index(UNIVERSOMARVEL_DB, progress=lambda message: later(self.marvel_info.set_text, message))
            except (UniversoMarvelError, OSError) as error:
                later(self.marvel_info.set_text, _("No se pudo descargar: {error}").format(error=error))
            else:
                later(self._refresh_marvel)
            later(self._marvel_download_finished)
        Thread(target=run, daemon=True).start()

    def _marvel_download_finished(self):
        if self._marvel_pulse_id:
            GLib.source_remove(self._marvel_pulse_id)
            self._marvel_pulse_id = 0
        self.marvel_progress.set_visible(False)
        self.marvel_button.set_sensitive(True)

    def _refresh_tebeosfera(self):
        index = TebeosferaIndex(TEBEOSFERA_DB)
        if index.is_ready():
            counts = index.counts()
            self.tebeosfera_info.set_text(_("Índice de Tebeosfera: {counts} colecciones y {counts_2} números.").format(counts=counts['colecciones'], counts_2=counts['números']))
        else:
            self.tebeosfera_info.set_text(_("Todavía no has descargado el índice de Tebeosfera."))

    def _download_tebeosfera(self, _button):
        self.tebeosfera_button.set_sensitive(False)
        self.tebeosfera_progress.set_visible(True)
        self.tebeosfera_progress.pulse()
        self._tebeosfera_pulse_id = GLib.timeout_add(150, lambda: (self.tebeosfera_progress.pulse(), True)[1])

        def run():
            try:
                build_tebeosfera_index(TEBEOSFERA_DB,
                                       progress=lambda message: later(self.tebeosfera_info.set_text, message))
            except (TebeosferaError, OSError) as error:
                later(self.tebeosfera_info.set_text, _("No se pudo descargar: {error}").format(error=error))
            else:
                later(self._refresh_tebeosfera)
            later(self._tebeosfera_download_finished)
        Thread(target=run, daemon=True).start()

    def _tebeosfera_download_finished(self):
        if self._tebeosfera_pulse_id:
            GLib.source_remove(self._tebeosfera_pulse_id)
            self._tebeosfera_pulse_id = 0
        self.tebeosfera_progress.set_visible(False)
        self.tebeosfera_button.set_sensitive(True)

    def _choose_gcd(self, _button):
        dump = Gtk.FileFilter(name=_("Volcado SQLite de GCD"))
        for pattern in ("*.db", "*.sqlite", "*.sqlite3"):
            dump.add_pattern(pattern)
        Gtk.FileDialog(title=_("Volcado de GCD"), default_filter=dump).open(self, None, self._gcd_chosen)

    def _gcd_chosen(self, dialog, result):
        try:
            source = Path(dialog.open_finish(result).get_path())
        except GLib.Error:
            return
        self.gcd_button.set_sensitive(False)
        Thread(target=self._import_gcd, args=(source,), daemon=True).start()

    def _import_gcd(self, source: Path):
        try:
            build_index(source, GCD_DB, lambda message: later(self.gcd_info.set_text, message))
        except Exception as error:  # noqa: BLE001 - se muestra al usuario
            later(self.gcd_info.set_text, _("No se pudo importar: {error}").format(error=error))
        else:
            later(self._refresh_gcd)
        later(self.gcd_button.set_sensitive, True)

    def _save_key(self, _button):
        self.settings.api_key = self.key.get_text().strip()
        self.settings.save()
        self.key_info.set_text(_("Clave guardada."))

    def _choose_gcstar(self, _button):
        gcs_filter = Gtk.FileFilter(name=_("Colección de GCstar"))
        gcs_filter.add_pattern("*.gcs")
        Gtk.FileDialog(title=_("Archivo .gcs de GCstar"), default_filter=gcs_filter).open(self, None,
                                                                                      self._gcstar_path_chosen)

    def _gcstar_path_chosen(self, dialog, result):
        try:
            self.gcstar_entry.set_text(dialog.open_finish(result).get_path())
        except GLib.Error:
            pass  # Selección cancelada.

    def _save_gcstar_path(self, _button):
        self.settings.gcstar_path = self.gcstar_entry.get_text().strip()
        self.settings.save()
        self._update_normalize()
        self.gcstar_info.set_text(_("Ruta guardada.") if self.settings.gcstar_path else
                                  _("Ruta guardada (vacía): el botón «Transferir a GCstar…» queda desactivado."))
