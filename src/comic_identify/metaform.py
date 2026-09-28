"""Lógica (sin interfaz) del formulario de metadatos: qué se propone y qué se escribe en cada archivo.

Cada campo de serie se rellena, por orden, con: lo que ya tienen todos los archivos → la serie de GCD elegida →
el nombre de la carpeta o del archivo → lo tecleado en la pantalla principal. Un campo que los archivos ya tienen
con el mismo valor en todos se muestra tal cual; si difieren, queda vacío y no se toca salvo que se escriba algo.
"""
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace

from .comicinfo import CATEGORY_PREFIX as CATEGORY_LABEL
from .comicinfo import FIELD_ORDER, category_of, with_category
from .naming import Values, looks_normalized
from .umficha import NOTE_HEADINGS

SERIES_FIELDS = ("Series", "Volume", "Year", "Month", "Day", "Count", "Publisher", "Imprint", "LanguageISO", "Web",
                 "Notes", "Writer", "Penciller", "Inker", "Colorist", "Letterer", "CoverArtist", "Translator", "Format", "Editor",
                 "Genre", "Characters")   # créditos: por lote, no por número
LANGUAGES = {"🇪🇸": "es", "🇺🇸": "en"}
GCD_SERIES_URL = "https://www.comics.org/series/{}/"
NO_CATEGORY = ""        # «no cambiar»


def merge_values(parsed: Values, gcd: Values | None = None, title: str = "") -> Values:
    """Valores de partida: el nombre normalizado de la carpeta o archivo manda y GCD rellena lo que falta; si el nombre
    no está normalizado (sin bandera, años ni sello), manda GCD y, sin GCD, lo tecleado como título."""
    normalized = looks_normalized(parsed)
    if gcd is None:
        return parsed if normalized or not title.strip() else replace(parsed, nombre=title.strip())
    if not normalized:
        return replace(gcd, contenido=parsed.contenido)
    filled = {field: getattr(gcd, field) for field in ("nombre", "bandera", "edicion", "sello")
              if not getattr(parsed, field)}
    return replace(parsed, **filled)


def suggest_fields(values: Values, publisher: str = "", info=None) -> dict[str, str]:
    """Campos de ComicInfo a partir de los valores del nombre (y de la serie de GCD, si se eligió una)."""
    volume = values.volumen.strip()
    series = values.nombre.strip() if volume.isdigit() or not volume else f"{values.nombre.strip()} {volume}"
    years = values.edicion.strip() or values.contenido.strip()
    year = re.match(r"\d{4}", years.replace(" ", ""))
    content = values.contenido.strip()
    fields = {"Series": series, "Volume": volume if volume.isdigit() else "", "Year": year.group() if year else "",
              "Publisher": publisher.strip(), "Imprint": values.sello.strip(),
              "LanguageISO": LANGUAGES.get(values.bandera, ""),
              "Notes": f"Contenido original: {content}" if content else ""}
    if info is not None:
        fields["Web"] = GCD_SERIES_URL.format(info.id)
        fields["Publisher"] = fields["Publisher"] or info.publisher
        if info.issue_count:
            fields["Count"] = str(info.issue_count)
    return {key: value for key, value in fields.items() if value}


def append_block(existing: str, block: str) -> str:
    """`block` debajo de lo que ya haya en las notas. Si las notas ya llevan un bloque de este tipo (empieza por
    «Contenido USA:», «Créditos por historia (USA):» o «Comentarios de la edición:» y llega hasta el final), se
    refresca en vez de repetirlo; si detrás hay algo escrito a mano, no se toca nada."""
    block, existing = block.strip(), existing.strip()
    if not block:
        return existing
    lines = existing.splitlines()
    first = next((n for n, line in enumerate(lines) if line.strip() in NOTE_HEADINGS), None)
    if first is None:
        return f"{existing}\n{block}" if existing else block
    if all(line.strip() in NOTE_HEADINGS or line.startswith("- ") for line in lines[first:]):
        return "\n".join([*lines[:first], block]).strip()
    return existing


def common_value(infos: Sequence[Mapping[str, str]], key: str) -> tuple[str, bool]:
    """(valor común, ninguno lo tiene): «» y False si difieren o solo algunos lo tienen."""
    values = {info.get(key, "") for info in infos}
    if values == {""}:
        return "", True
    return (values.pop(), False) if len(values) == 1 else ("", False)


def initial_form(infos: Sequence[Mapping[str, str]], suggested: Mapping[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """(textos iniciales, valor uniforme que ya tienen los archivos). Sirve para saber si el usuario vació un campo."""
    texts, baseline = {}, {}
    for key in SERIES_FIELDS:
        value, absent = common_value(infos, key)
        texts[key] = suggested.get(key, "") if absent else value
        baseline[key] = value
    return texts, baseline


def series_changes(texts: Mapping[str, str], baseline: Mapping[str, str]) -> dict[str, str]:
    """Campos de serie a escribir: lo tecleado, y «» (borrar) si el usuario vació un valor que todos tenían."""
    changes = {}
    for key in SERIES_FIELDS:
        text = texts.get(key, "").strip()
        if text:
            changes[key] = text
        elif baseline.get(key):
            changes[key] = ""
    return changes


def initial_category(infos: Sequence[Mapping[str, str]]) -> str:
    """La categoría que ya tienen todos los archivos (si coinciden); si no, «no cambiar»."""
    found = {category_of(info.get("Tags", "")) for info in infos}
    return found.pop() if len(found) == 1 else NO_CATEGORY


def file_changes(series: Mapping[str, str], category: str, number: str, title: str, summary: str,
                 current: Mapping[str, str], pages: int = 0, extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Todo lo que hay que dejar en un archivo: campos de serie + Nº + título + resumen + (si se eligió) categoría
    en `Tags` + `PageCount` (las páginas contadas en el propio archivo, que es la fuente fiable) + `extra` (datos de
    un solo ejemplar, como el código de barras, que no pisan lo demás)."""
    changes = dict(series)
    if number.strip():
        changes["Number"] = str(int(number)) if number.strip().isdigit() else number.strip()
    changes["Title"] = title.strip()
    changes["Summary"] = summary.strip()
    if category != NO_CATEGORY:
        changes["Tags"] = with_category(current.get("Tags", ""), category)
    if pages > 0:
        changes["PageCount"] = str(pages)
    for key, value in (extra or {}).items():
        if value.strip() and key not in changes:
            changes[key] = value.strip()
    return changes


LABELS = {"Title": "Título", "Series": "Serie", "Volume": "Volumen", "Number": "Nº", "Count": "Total",
          "AlternateSeries": "Serie alternativa", "AlternateNumber": "Nº alternativo", "AlternateCount": "Total alternativo",
          "Summary": "Resumen", "Notes": "Notas", "Writer": "Guion", "Penciller": "Lápiz", "Inker": "Tinta",
          "Colorist": "Color", "Letterer": "Rotulación", "CoverArtist": "Portada", "Editor": "Edición",
          "Translator": "Traducción", "Publisher": "Editorial", "Imprint": "Sello", "Genre": "Género", "Web": "Web",
          "PageCount": "Páginas", "LanguageISO": "Idioma", "Format": "Formato", "BlackAndWhite": "Blanco y negro",
          "Manga": "Manga", "Characters": "Personajes", "Teams": "Equipos", "Locations": "Lugares",
          "ScanInformation": "Escaneo", "StoryArc": "Arco", "StoryArcNumber": "Nº del arco", "SeriesGroup": "Grupo",
          "AgeRating": "Edad", "CommunityRating": "Valoración", "MainCharacterOrTeam": "Protagonista",
          "Review": "Reseña", "GTIN": "Código de barras"}


def describe_info(info: Mapping[str, str]) -> list[tuple[str, str]]:
    """Filas (etiqueta, valor) para mostrar un ComicInfo.xml: en el orden del esquema, con la fecha en una sola fila y
    la categoría aparte del resto de etiquetas. Los campos vacíos no salen."""
    rows: list[tuple[str, str]] = []
    year, month, day = (info.get(key, "").strip() for key in ("Year", "Month", "Day"))
    date = "-".join([year.zfill(4), *([month.zfill(2)] + ([day.zfill(2)] if day else []) if month else [])]) if year else ""
    for key in FIELD_ORDER:
        value = info.get(key, "").strip()
        if key in ("Year", "Month", "Day"):
            if key == "Year" and date:
                rows.append(("Fecha", date))
        elif key == "Tags":
            category = category_of(value)
            rest = ", ".join(t for t in (t.strip() for t in value.split(",")) if t and not t.startswith(CATEGORY_LABEL))
            if category:
                rows.append(("Categoría", category))
            if rest:
                rows.append(("Etiquetas", rest))
        elif value:
            rows.append((LABELS.get(key, key), value))
    rows.extend((key, value.strip()) for key, value in info.items() if key not in FIELD_ORDER and value.strip())
    return rows
