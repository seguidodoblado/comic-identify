"""Filas de resultados y logotipos de editoriales."""
from pathlib import Path
from threading import Thread

from ..i18n import _
from ..identify import (
    CATALOG_SOURCES,
    Candidate,
)
from ..settings import (
    LOGO_DIR,
)
from .constants import (
    SOURCE_STYLES,
)
from .logos import LOGO_BOX, fetch_logo, logo_file, logo_key, publisher_slug, short_name, user_logo
from .logos import NAMES as LOGO_NAMES
from .widgets import (
    Gdk,
    GdkPixbuf,
    Gio,
    GLib,
    Gtk,
    Pango,
    icon_button,
    later,
)


class ResultsMixin:
    def _logo_ready(self, key: str, path: Path):
        for picture in self.logo_widgets.pop(key, []):
            picture.set_filename(str(path))

    def _request_logo(self, key: str):
        """Descarga (una sola vez; luego, caché) el logotipo de esa editorial, en segundo plano."""
        if key in self._logo_requested:
            return
        self._logo_requested.add(key)

        def run():
            if (path := fetch_logo(key, self.logo_dir)) is not None:
                later(self._logo_ready, key, path)
        Thread(target=run, daemon=True).start()

    @staticmethod
    def _scaled_logo(path: Path):
        """El logotipo del usuario, reducido para que quepa en el hueco (conservando la proporción) y hecho textura: GTK
        no escala bien una imagen grande dentro de un hueco pequeño (se ve enorme y descentrada). Vale PNG, JPG y SVG.
        None si no se puede leer."""
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), LOGO_BOX[0], LOGO_BOX[1], True)
        except GLib.Error:
            return None
        return Gdk.Texture.new_for_pixbuf(pixbuf)

    def _publisher_logo(self, candidate: Candidate):
        """La marca de la editorial de la fila, en un hueco fijo a la derecha: su logotipo (uno que haya puesto el
        usuario, o el descargado de la web de fichas) o, si no hay ninguno, una etiqueta con su nombre. Solo en las
        filas de GCD y Universo Marvel; las demás no tienen editorial."""
        if candidate.source not in ("GCD", *CATALOG_SOURCES):
            return None
        name = candidate.publisher.strip()
        key = logo_key(candidate.publisher, candidate.brand, candidate.extra.get("index_publisher", ""))
        if key is None and not name:
            return None
        slot = Gtk.Box(halign=Gtk.Align.END, valign=Gtk.Align.CENTER)
        slot.set_size_request(*LOGO_BOX)
        slug = key or publisher_slug(name)
        # la búsqueda por palabras es solo para las editoriales sin logotipo automático (Tebeosfera, antes de
        # consultar una ficha, solo trae un trozo del nombre); con una de las 8 automáticas, «planeta» encontraría
        # por error el archivo de una editorial distinta con esa palabra en su nombre, como «planeta-comic.png»
        custom = user_logo((slug,), LOGO_DIR, fuzzy=key is None)
        texture = self._scaled_logo(custom) if custom is not None else None
        if texture is not None:   # el del usuario manda sobre el descargado
            slot.set_tooltip_text(LOGO_NAMES.get(key, name))
            slot.append(Gtk.Picture(paintable=texture, can_shrink=False, hexpand=True, halign=Gtk.Align.END,
                                    valign=Gtk.Align.CENTER))
            return slot
        path = logo_file(key, self.logo_dir) if key is not None else None
        if key is None:   # editorial sin logotipo: su nombre, para que ninguna fila quede sin marca
            slot.append(Gtk.Label(label=short_name(name), hexpand=True, halign=Gtk.Align.END,
                                  ellipsize=Pango.EllipsizeMode.END, max_width_chars=16,
                                  css_classes=["publisher-badge"], tooltip_text=(
                _("{name}\nPara poner su logotipo, guarda «{slug}.png» en {LOGO_DIR}").format(name=name, slug=slug, LOGO_DIR=LOGO_DIR))))
            return slot
        slot.set_tooltip_text(LOGO_NAMES[key])
        # los descargados van ya reducidos: sin can_shrink se ven del tamaño exacto (GTK no los reescala a su gusto)
        logo = Gtk.Picture(can_shrink=False, hexpand=True, halign=Gtk.Align.END, valign=Gtk.Align.CENTER)
        slot.append(logo)
        if path is not None:
            logo.set_filename(str(path))
        else:
            self.logo_widgets.setdefault(key, []).append(logo)
            self._request_logo(key)
        return slot

    def _row(self, candidate: Candidate):
        row = Gtk.Box(spacing=12, margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
        thumb = Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.CONTAIN)
        thumb.set_size_request(70, 105)
        thumb.set_visible(bool(candidate.cover))   # GCD no tiene imagen: no reservar el hueco
        if candidate.cover:
            try:
                thumb.set_paintable(Gdk.Texture.new_from_bytes(GLib.Bytes.new(candidate.cover)))
            except GLib.Error:
                pass
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True, valign=Gtk.Align.CENTER)
        title = Gtk.Label(xalign=0, wrap=True)
        title.set_markup(f"<b>{GLib.markup_escape_text(candidate.title)}</b>")
        head = Gtk.Box(spacing=8)
        head.append(title)
        if (style := SOURCE_STYLES.get(candidate.source)) is not None:   # icono de la web y etiqueta de su color
            host, css_class = style
            head.append(self._icon(host, 16))
            head.append(Gtk.Label(label=candidate.source, valign=Gtk.Align.CENTER,
                                  css_classes=["source-chip", css_class]))
        else:
            head.append(Gtk.Label(label=candidate.source, valign=Gtk.Align.CENTER, css_classes=["dim-label"]))
        text.append(head)
        if candidate.subtitle:
            text.append(Gtk.Label(label=candidate.subtitle, xalign=0, wrap=True))
        if candidate.similarity is not None:
            verdict = _("Coincidencia probable") if candidate.is_match else _("Poco parecida")
            score = Gtk.Label(label=_("{verdict} · {candidate_similarity:.0%} de parecido").format(verdict=verdict, candidate_similarity=candidate.similarity), xalign=0)
            score.add_css_class("success" if candidate.is_match else "dim-label")
            text.append(score)
        elif candidate.source in CATALOG_SOURCES:
            if candidate.extra.get("level") != "series":
                how = _("Datos de la ficha de {candidate_source}").format(candidate_source=candidate.source)
            elif self._is_single_issue(candidate):
                how = _("Número suelto del catálogo: elígelo para ver su ficha")
            else:
                how = _("Serie del catálogo: escribe el número y elígela para consultar su ficha")
            score = Gtk.Label(label=how, xalign=0, wrap=True)
            score.add_css_class("dim-label")
            text.append(score)
        elif candidate.source == "GCD":
            how = _("Coincide el código de barras") if candidate.exact else _("Por título; portada sin comparar")
            score = Gtk.Label(label=how, xalign=0)
            score.add_css_class("success" if candidate.exact else "dim-label")
            text.append(score)
        row.append(thumb)
        row.append(text)
        if (logo := self._publisher_logo(candidate)) is not None:
            row.append(logo)
        if candidate.path:
            open_folder = icon_button(("folder-open-symbolic",), _("Abrir carpeta"), valign=Gtk.Align.CENTER)
            open_folder.connect("clicked", lambda _b, p=candidate.path: Gtk.FileLauncher.new(
                Gio.File.new_for_path(str(p))).open_containing_folder(None, None, lambda *_args: None))
            row.append(open_folder)
        return row

    # ---- Mi colección ------------------------------------------------------------------
