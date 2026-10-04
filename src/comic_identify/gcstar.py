"""Transferir un cómic a una colección de GCstar (gcstar.gitlab.io): añade un `<item>` a su archivo `.gcs` sin
tocar el resto (no se reescribe ni se reordena nada de lo que ya había) y copia la portada y la contraportada a la
carpeta de imágenes de esa colección, con la misma convención de nombres que el propio GCstar entiende.

Verificado leyendo el código fuente de GCstar (no solo su formato de archivo): las rutas de `image`/`backpic` se
resuelven relativas a la carpeta donde vive el `.gcs` (`GCUtils::getDisplayedImage`), y si `<maxId>`/`items=` no
coinciden con el contenido real, GCstar los recalcula solo al abrir (`GCData.pm`, `findMaxId`), así que no hace
falta acertarlos con precisión.
"""
import json
import os
import re
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from .covers import extract_page, list_pages
from .i18n import _

COVER_SUFFIX = " - Portada"
BACK_SUFFIX = " - Trasera"
IMAGES_SUBFOLDER = "comics"   # carpeta propia bajo la de tu .gcs: ahí conviven las imágenes de varias colecciones
VOCABULARY_FIELDS = ("type", "category", "format", "collection")   # texto libre del usuario: se sugiere, no se adivina

# «Tipo» de GCstar: origen de la serie, según la primera carpeta de tu colección (tu propia convención en
# «Mi colección»: …/comics/EUROPA/…, …/comics/USA/…, …/comics/JAPÓN/…). Solo mira el nombre de esa carpeta, nunca
# la ruta absoluta, así que sobrevive a cambiar de disco.
ORIGIN_BY_FOLDER = {"europa": "Europeo", "usa": "Americano", "japón": "Manga"}

# Nuestros campos (del ComicInfo/formulario) -> atributos de un <item> de GCcomics. El «número» del cómic (Nº de
# ComicInfo) se corresponde con el campo `volume` de GCstar, no con nuestro «Volumen»: así es como ya lo usas tú
# (Blake y Mortimer #1, #2… con volume="1", volume="2"); nuestro Volumen (reinicio de numeración) no tiene hueco
# propio en GCstar, así que se incluye como texto dentro de `series`.
FIELD_MAP = {"Writer": "writer", "Penciller": "illustrator", "Inker": "inker", "Colorist": "colourist",
            "Letterer": "letterer", "CoverArtist": "artist", "Web": "webPage"}   # «artist» es su «Cover Artist»

# `BlackAndWhite` de ComicInfo -> etiqueta de GCstar (las palabras de la colección del usuario: «Color» y «B&N»)
COLOR_TAGS = {"No": "Color", "Yes": "B&N"}
COMMENT_CREDITS = (("Translator", "Traducción"), ("Editor", "Edición"))   # sin campo en GCstar: al final del comentario


class GCstarError(Exception):
    """No se pudo transferir el cómic a GCstar; el .gcs y las imágenes quedan como estaban."""


@dataclass
class TransferResult:
    item_id: int
    image: Path | None = None
    backpic: Path | None = None


@dataclass
class UndoResult:
    removed: bool = False
    images: list[Path] = field(default_factory=list)
    skipped_images: list[Path] = field(default_factory=list)   # ya no coinciden con lo que pusimos: no se tocan


# ---- GCstar en marcha -------------------------------------------------------------------------------------------

def is_running(proc_dir: Path = Path("/proc")) -> bool:
    """GCstar está abierto (con `autosave`, cerrarlo después podría sobrescribir lo que acabemos de añadir).

    Compara por el nombre exacto de cada argumento (no si «gcstar» aparece en cualquier parte de la línea de
    comandos: si no, esta misma comprobación se detectaría a sí misma al ejecutarse dentro de sus propias pruebas,
    cuyo archivo se llama `test_gcstar.py`). Si no se puede saber (no hay `/proc`, sin permiso…), False: es una
    red de seguridad, no un bloqueo estricto.
    """
    try:
        pids = [entry for entry in os.listdir(proc_dir) if entry.isdigit()]
    except OSError:
        return False
    for pid in pids:
        with suppress(OSError):
            args = (proc_dir / pid / "cmdline").read_bytes().split(b"\x00")
            if any(Path(arg.decode(errors="replace")).name.lower() == "gcstar" for arg in args if arg):
                return True
    return False


# ---- Lectura del .gcs (sin tocarlo) -----------------------------------------------------------------------------

def _items(text: str) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    return [dict(item.attrib) for item in root.findall("item")]


def next_id(text: str) -> int:
    """Un id que no esté ya usado (uno más que el mayor que haya, o 1 si no hay ninguno)."""
    ids = [int(item["id"]) for item in _items(text) if item.get("id", "").isdigit()]
    return max(ids, default=0) + 1


def vocabulary(text: str, field_name: str) -> list[str]:
    """Los valores que ya se han usado en ese campo (para sugerirlos: `type`, `category`, `format`, `collection`),
    sin repetir, en el orden en que aparecen la primera vez."""
    seen: dict[str, None] = {}
    for item in _items(text):
        value = item.get(field_name, "").strip()
        if value:
            seen.setdefault(value, None)
    return list(seen)


# ---- Componer los campos del <item> ------------------------------------------------------------------------------

def format_name(series: str, number: str, title: str) -> str:
    """Como compone GCstar su propio campo `name` (columna «Título» de su lista): `%series% #%volume[%03d]% %title%`."""
    parts = [series.strip()]
    if number.strip().isdigit():
        parts.append(f"#{int(number):03d}")
    if title.strip():
        parts.append(title.strip())
    return " ".join(part for part in parts if part)


def format_date(year: str, month: str, day: str, pattern: str = "%d/%m/%Y") -> str:
    """La fecha en el formato de fecha de GCstar (el que tenga configurado); «» si ni el año se sabe. Sin mes ni
    día se usa enero y el día 1, para que al menos el año salga bien; se puede afinar luego a mano en GCstar."""
    if not year.strip().isdigit():
        return ""
    try:
        return date(int(year), int(month) if month.strip().isdigit() else 1,
                   int(day) if day.strip().isdigit() else 1).strftime(pattern)
    except ValueError:
        return ""


def publisher_text(publisher: str, imprint: str) -> str:
    """«Publicado por» de GCstar: «Editorial - Sello». GCstar no tiene campo de sello, así que va aquí para no
    perderlo; si falta uno de los dos, se queda solo el otro."""
    return " - ".join(part for part in (publisher.strip(), imprint.strip()) if part)


def is_isbn(code: str) -> bool:
    """¿Parece un ISBN (13 cifras que empiezan por 978/979, o 10 con dígito de control opcional X)? El código de barras
    de una revista (977…) o cualquier otro no lo es: no debe ir en el campo ISBN."""
    digits = re.sub(r"[\s-]", "", code).upper()
    return bool(re.fullmatch(r"97[89]\d{10}", digits) or re.fullmatch(r"\d{9}[\dX]", digits))


def isbn_text(explicit: str, gtin: str) -> str:
    """Lo escrito a mano en el diálogo, si hay algo; si no, el GTIN del archivo solo si es de verdad un ISBN."""
    return explicit.strip() or (re.sub(r"[\s-]", "", gtin) if is_isbn(gtin) else "")


def cost_text(value: str) -> str:
    """El «Coste» de GCstar es un número: «3,90 €» -> «3.90»; algo que no lo sea se descarta en vez de romper el campo."""
    cleaned = re.sub(r"[^\d.,]", "", value.replace(",", "."))
    return cleaned if re.fullmatch(r"\d+(\.\d+)?", cleaned) else ""


def series_text(series: str, volume: str) -> str:
    """El nombre de serie que se manda a GCstar: el nuestro, más «Volumen N» si hay un reinicio de numeración."""
    series, volume = series.strip(), volume.strip()
    return f"{series} Volumen {volume}" if volume and volume != "1" else series


def comment_text(fields: Mapping[str, str]) -> str:
    """El comentario de GCstar: las Notas y, al final, «Traducción» y «Edición» (que GCstar no tiene como campos), solo si hay dato."""
    lines = [f"{label}: {fields[key].strip()}" for key, label in COMMENT_CREDITS if fields.get(key, "").strip()]
    return "\n\n".join(part for part in (fields.get("Notes", "").strip(), "\n".join(lines)) if part)


def build_attrs(fields: Mapping[str, str], gcstar_fields: Mapping[str, str], comic: Path, pages: int,
                image: Path | None, backpic: Path | None, gcs_dir: Path) -> dict[str, str]:
    """Los atributos del `<item>`: `fields` son los del ComicInfo (Series, Number, Title, Writer…) y `gcstar_fields`
    los propios de GCstar que no salen de ahí (type, category, format, collection, cost, isbn)."""
    series = series_text(fields.get("Series", ""), fields.get("Volume", ""))
    attrs = {"name": format_name(series, fields.get("Number", ""), fields.get("Title", "")), "series": series,
            "volume": fields.get("Number", "").strip(), "title": fields.get("Title", "").strip(),
            **{gcstar_key: fields.get(our_key, "").strip() for our_key, gcstar_key in FIELD_MAP.items()},
            "publisher": publisher_text(fields.get("Publisher", ""), fields.get("Imprint", "")),
            "synopsis": fields.get("Summary", "").strip(), "collection": gcstar_fields.get("collection", "").strip(),
            "publishdate": format_date(fields.get("Year", ""), fields.get("Month", ""), fields.get("Day", "")),
            "image": str(image.relative_to(gcs_dir)) if image else "",
            "backpic": str(backpic.relative_to(gcs_dir)) if backpic else "",
            "added": datetime.now().astimezone().strftime("%d/%m/%Y"), "isbn": isbn_text(gcstar_fields.get("isbn", ""), fields.get("GTIN", "")),
            "cost": cost_text(gcstar_fields.get("cost", "")),
            "type": gcstar_fields.get("type", "").strip(), "category": gcstar_fields.get("category", "").strip(),
            "format": gcstar_fields.get("format", "").strip(), "numberboards": str(pages) if pages else "",
            "comment": comment_text(fields), "tags": COLOR_TAGS.get(fields.get("BlackAndWhite", "").strip(), ""), "file": str(comic), "borrower": "none"}
    return {key: value for key, value in attrs.items() if value}


def build_item(attrs: Mapping[str, str], item_id: int) -> str:
    """El bloque `<item id="…" …>…</item>`, indentado como una línea más del archivo (no como un documento aparte)."""
    element = ET.Element("item", {"id": str(item_id), **{k: v for k, v in attrs.items()
                                                         if k not in ("synopsis", "comment", "tags")}})
    for key in ("synopsis", "comment"):
        if attrs.get(key):
            ET.SubElement(element, key).text = attrs[key]
    if attrs.get("tags"):   # una lista: <tags><line><col>etiqueta</col></line>…</tags>, como la escribe el propio GCstar
        tags = ET.SubElement(element, "tags")
        for tag in attrs["tags"].split("\n"):
            ET.SubElement(ET.SubElement(tags, "line"), "col").text = tag
    ET.indent(element, space=" ")
    return " " + ET.tostring(element, encoding="unicode") + "\n"


def insert_item(text: str, item_xml: str) -> str:
    """`text` con `item_xml` añadido justo antes de `</collection>`; nada más del archivo se toca."""
    marker = "</collection>"
    index = text.rfind(marker)
    if index == -1:
        raise GCstarError(_("El archivo no parece un .gcs de GCstar (no se encontró «</collection>»)."))
    return text[:index] + item_xml + text[index:]


# ---- Dónde poner la portada y la contraportada -------------------------------------------------------------------

def relative_path(comic: Path, library_folders: Sequence[Path]) -> Path | None:
    """La ruta del cómic bajo la carpeta de «Mi colección» en la que esté (probadas en orden); None si no está bajo
    ninguna de las configuradas. Solo se usa el nombre de las carpetas, nunca dónde esté montado el disco."""
    comic = comic.resolve()
    for folder in library_folders:
        try:
            return comic.relative_to(Path(folder).resolve())
        except (ValueError, OSError):
            continue
    return None


def mirror_stems(comic: Path, library_folders: Sequence[Path], gcs_path: Path) -> tuple[Path, Path] | None:
    """Los nombres (sin extensión) de la portada y la contraportada, con la misma estructura de carpetas que el
    cómic tiene bajo la carpeta de «Mi colección» en la que esté, replicada bajo `IMAGES_SUBFOLDER` en la carpeta
    del `.gcs` (para poder compartir esa carpeta con otras colecciones de GCstar).

    None si el cómic no está bajo ninguna carpeta configurada: no se adivina dónde ponerlas.
    """
    relative = relative_path(comic, library_folders)
    if relative is None:
        return None
    target_dir = gcs_path.resolve().parent / IMAGES_SUBFOLDER / relative.parent
    return target_dir / f"{comic.stem}{COVER_SUFFIX}", target_dir / f"{comic.stem}{BACK_SUFFIX}"


def suggest_type(comic: Path, library_folders: Sequence[Path]) -> str:
    """El «Tipo» de GCstar sugerido a partir de la primera carpeta bajo «Mi colección» (ver `ORIGIN_BY_FOLDER`);
    «» si el cómic no está bajo ninguna carpeta configurada o su primer tramo no es de los conocidos."""
    relative = relative_path(comic, library_folders)
    if relative is None or not relative.parts:
        return ""
    return ORIGIN_BY_FOLDER.get(relative.parts[0].lower(), "")


# ---- Leer y escribir el .gcs con seguridad ------------------------------------------------------------------------

def _read_text(gcs_path: Path) -> str:
    try:
        return gcs_path.read_text(encoding="utf-8")
    except OSError as error:
        raise GCstarError(_("No se pudo leer «{name}»: {error}").format(name=gcs_path.name, error=error)) from error


def _write_text(gcs_path: Path, text: str) -> None:
    """Todo o nada: escribe en una copia, comprueba que sigue siendo un XML válido y solo entonces la sustituye."""
    temp = gcs_path.with_name(f".{uuid.uuid4().hex[:10]}.tmp.gcs")
    try:
        temp.write_text(text, encoding="utf-8")
        try:
            ET.fromstring(temp.read_text(encoding="utf-8"))
        except ET.ParseError as error:
            raise GCstarError(_("El resultado no sería un XML válido: {error}").format(error=error)) from error
        os.replace(temp, gcs_path)
    except OSError as error:
        raise GCstarError(_("No se pudo escribir «{name}»: {error}").format(name=gcs_path.name, error=error)) from error
    finally:
        with suppress(OSError):
            temp.unlink()


# ---- La transferencia en sí ----------------------------------------------------------------------------------------

def transfer(comic: Path, fields: Mapping[str, str], gcstar_fields: Mapping[str, str], gcs_path: Path,
            library_folders: Sequence[Path], log: Path, include_back: bool = True) -> TransferResult:
    """Añade `comic` a la colección de GCstar en `gcs_path`. Todo o nada: si algo falla a mitad, el `.gcs` y las
    imágenes que se hubieran empezado a crear quedan como si no se hubiera hecho nada.
    """
    if is_running():
        raise GCstarError(_("GCstar parece estar abierto: ciérralo antes de transferir, para que no sobrescriba "
                          "esto al guardar."))
    if not gcs_path.is_file():
        raise GCstarError(_("No existe el archivo «{gcs_path}».").format(gcs_path=gcs_path))
    text = _read_text(gcs_path)
    item_id = next_id(text)
    pages = list_pages(comic)
    image = backpic = None
    try:
        mirrors = mirror_stems(comic, library_folders, gcs_path)
        if mirrors is not None and pages:
            cover_stem, back_stem = mirrors
            cover_stem.parent.mkdir(parents=True, exist_ok=True)
            image = extract_page(comic, pages[0], cover_stem)
            if include_back and len(pages) > 1:
                backpic = extract_page(comic, pages[-1], back_stem)
        attrs = build_attrs(fields, gcstar_fields, comic, len(pages), image, backpic, gcs_path.resolve().parent)
        item_xml = build_item(attrs, item_id)
        _write_text(gcs_path, insert_item(text, item_xml))
    except (OSError, ValueError, GCstarError):
        for path in (image, backpic):
            if path is not None:
                with suppress(OSError):
                    path.unlink()
        raise

    def stat(path: Path | None) -> list[float] | None:
        return [path.stat().st_mtime, path.stat().st_size] if path is not None else None

    _append_log(log, {"gcs": str(gcs_path), "item_id": item_id, "item_xml": item_xml,
                      "image": str(image) if image else None, "image_stat": stat(image),
                      "backpic": str(backpic) if backpic else None, "backpic_stat": stat(backpic)})
    return TransferResult(item_id, image, backpic)


def _append_log(log: Path, entry: dict) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"time": stamp, **entry}, ensure_ascii=False) + "\n")


def undo_last(log: Path) -> UndoResult:
    """Deshace la última transferencia: quita el `<item>` (si el .gcs sigue teniendo exactamente ese texto; si se ha
    editado desde entonces a mano, no se toca) y borra la portada/contraportada que se crearon, solo si nadie las
    ha cambiado desde entonces (misma fecha y tamaño que al crearlas).
    """
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    if not lines:
        raise LookupError(_("No hay transferencias a GCstar que deshacer."))
    entry = json.loads(lines[-1])
    gcs_path = Path(entry["gcs"])
    result = UndoResult()
    if gcs_path.is_file():
        text = _read_text(gcs_path)
        if entry["item_xml"] in text:
            _write_text(gcs_path, text.replace(entry["item_xml"], "", 1))
            result.removed = True
    for key in ("image", "backpic"):
        path_text = entry.get(key)
        if not path_text:
            continue
        path = Path(path_text)
        unchanged = path.is_file() and [path.stat().st_mtime, path.stat().st_size] == entry.get(f"{key}_stat")
        if unchanged and _try_remove(path):
            result.images.append(path)
        elif path.is_file():
            result.skipped_images.append(path)
    with suppress(OSError):
        log.write_text("".join(line + "\n" for line in lines[:-1]), encoding="utf-8")
    return result


def _try_remove(path: Path) -> bool:
    try:
        path.unlink()
    except OSError:
        return False
    return True
