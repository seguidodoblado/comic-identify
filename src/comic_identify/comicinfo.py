"""Lectura y escritura de `ComicInfo.xml` dentro de CBZ/CBR/CB7 (el formato que entienden Kavita, Komga y ComicTagger).

El tipo de archivo se decide por el contenido, no por la extensión (hay muchos «.cbr» que son ZIP). Escribir nunca toca
el original hasta que una copia, ya modificada, ha pasado la verificación: entonces se sustituye de forma atómica.
"""
import copy
import os
import shutil
import subprocess
import tempfile
import uuid
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

ENTRY_NAME = "ComicInfo.xml"
MAX_XML_BYTES = 2 * 1024 * 1024          # un ComicInfo.xml real pesa unos pocos KB
TOOL_TIMEOUT = 1800                      # segundos: reescribir un archivo de cientos de MB en un disco lento
SPACE_MARGIN = 64 * 1024 * 1024

# Orden de los elementos en ComicInfo.xsd (v2.1): el esquema los define como secuencia.
FIELD_ORDER = (
    "Title", "Series", "Number", "Count", "Volume", "AlternateSeries", "AlternateNumber", "AlternateCount", "Summary",
    "Notes", "Year", "Month", "Day", "Writer", "Penciller", "Inker", "Colorist", "Letterer", "CoverArtist", "Editor",
    "Translator", "Publisher", "Imprint", "Genre", "Tags", "Web", "PageCount", "LanguageISO", "Format",
    "BlackAndWhite", "Manga", "Characters", "Teams", "Locations", "ScanInformation", "StoryArc", "StoryArcNumber",
    "SeriesGroup", "AgeRating", "Pages", "CommunityRating", "MainCharacterOrTeam", "Review", "GTIN")
INTEGER_FIELDS = {"Count": (0, None), "Volume": (0, None), "Year": (0, 9999), "Month": (1, 12), "Day": (1, 31),
                  "AlternateCount": (0, None), "PageCount": (0, None)}

CATEGORIES = ("Series", "Etapas y autores", "Recopilatorios y clásicos", "Eventos y crossovers", "OGN y OneShots",
              "Universos alternativos", "Extras y Documentación")
CATEGORY_PREFIX = "Categoría: "


class MetadataError(Exception):
    """No se pudieron leer o escribir los metadatos; el archivo original queda como estaba."""


# ---- XML ------------------------------------------------------------------------------------------------------

def parse_info(xml: bytes) -> dict[str, str]:
    """Campos de primer nivel de un ComicInfo.xml como {nombre: texto}. Ignora `Pages` y lo que no es texto plano."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as error:
        raise MetadataError(f"El ComicInfo.xml no es un XML válido: {error}") from error
    return {_local(child.tag): (child.text or "").strip() for child in root if _local(child.tag) != "Pages"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def build_xml(existing: bytes | None, changes: Mapping[str, str | None]) -> bytes:
    """Aplica `changes` sobre el XML existente (o uno nuevo): «» o None borran el campo, lo demás se respeta tal cual.

    Se conservan los elementos que no se tocan (autores, `Pages`…) y se dejan en el orden del esquema.
    """
    for key, value in changes.items():
        if key not in FIELD_ORDER:
            raise MetadataError(f"Campo desconocido de ComicInfo: {key}")
        if key in INTEGER_FIELDS and value:
            low, high = INTEGER_FIELDS[key]
            if not str(value).isdigit() or int(value) < low or (high is not None and int(value) > high):
                raise MetadataError(f"«{key}» debe ser un número entero válido, no «{value}».")
    if existing:
        try:
            root = ET.fromstring(existing)
        except ET.ParseError as error:
            raise MetadataError(f"El ComicInfo.xml existente no es un XML válido: {error}") from error
        if _local(root.tag) != "ComicInfo":
            raise MetadataError("El XML existente no es un ComicInfo.")
    else:
        root = ET.Element("ComicInfo")
    for child in list(root):
        if _local(child.tag) in changes:
            root.remove(child)
    for key, value in changes.items():
        if value is not None and str(value).strip():
            ET.SubElement(root, key).text = str(value).strip()
    rank = {name: index for index, name in enumerate(FIELD_ORDER)}
    root[:] = sorted(root, key=lambda child: rank.get(_local(child.tag), len(rank)))   # estable: lo desconocido, al final
    ET.indent(root, space="  ")
    return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="utf-8") + b"\n"


def category_of(tags: str) -> str:
    """La categoría guardada en `Tags` («Categoría: Series»), o «» si no hay."""
    for tag in (t.strip() for t in tags.split(",")):
        if tag.startswith(CATEGORY_PREFIX):
            return tag[len(CATEGORY_PREFIX):].strip()
    return ""


def with_category(tags: str, category: str) -> str:
    """`Tags` con la categoría puesta (o quitada si `category` está vacía); el resto de etiquetas se conserva."""
    kept = [t.strip() for t in tags.split(",") if t.strip() and not t.strip().startswith(CATEGORY_PREFIX)]
    return ", ".join([*kept, CATEGORY_PREFIX + category] if category else kept)


# ---- Tipo de archivo y herramientas externas ------------------------------------------------------------------

def archive_kind(path: Path) -> str | None:
    """«zip», «rar» o «7z» según el contenido; None si no es ninguno (o está dañado y sin cabecera)."""
    try:
        if zipfile.is_zipfile(path):
            return "zip"
        with path.open("rb") as handle:
            head = handle.read(8)
    except OSError:
        return None
    if head.startswith(b"Rar!\x1a\x07"):
        return "rar"
    if head.startswith(b"7z\xbc\xaf\x27\x1c"):
        return "7z"
    return None


def _run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, capture_output=True, cwd=cwd, timeout=TOOL_TIMEOUT, check=False)
    except FileNotFoundError as error:
        raise MetadataError(f"Falta el programa «{command[0]}».") from error
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MetadataError(f"Falló «{command[0]}»: {error}") from error


def _tool_error(done: subprocess.CompletedProcess, what: str) -> MetadataError:
    detail = (done.stderr or done.stdout).decode(errors="replace").strip().splitlines()
    return MetadataError(f"{what}: {detail[-1] if detail else 'código ' + str(done.returncode)}")


def _names_7z(path: Path) -> list[str]:
    done = _run(["7z", "l", "-slt", "-ba", "--", str(path)])
    if done.returncode != 0:
        raise _tool_error(done, "No se pudo listar el archivo")
    return [line[7:] for line in done.stdout.decode(errors="replace").splitlines() if line.startswith("Path = ")]


def _names_rar(path: Path) -> list[str]:
    for tool in ("unrar", "rar"):
        if shutil.which(tool):
            done = _run([tool, "lb", "--", str(path)])
            if done.returncode == 0:
                return done.stdout.decode(errors="replace").splitlines()
    if shutil.which("7z"):
        return _names_7z(path)
    raise MetadataError("Para leer RAR hace falta «unrar» o «7z».")


def _extract_rar(path: Path, name: str) -> bytes:
    for tool in ("unrar", "rar"):
        if shutil.which(tool):
            done = _run([tool, "p", "-inul", "--", str(path), name])
            if done.returncode == 0:
                return done.stdout
    done = _run(["7z", "x", "-so", "--", str(path), name])
    if done.returncode != 0:
        raise _tool_error(done, "No se pudo leer el ComicInfo.xml")
    return done.stdout


def _find(names: list[str]) -> str | None:
    """El nombre real de ComicInfo.xml en la raíz del archivo (sin distinguir mayúsculas)."""
    return next((n for n in names if n.replace("\\", "/").lower() == ENTRY_NAME.lower()), None)


# ---- Lectura --------------------------------------------------------------------------------------------------

def read_xml(path: Path) -> bytes | None:
    """El ComicInfo.xml del archivo tal cual está, o None si no lo tiene."""
    kind = archive_kind(path)
    if kind is None:
        raise MetadataError("No es un archivo ZIP, RAR ni 7-Zip (¿está dañado?).")
    try:
        if kind == "zip":
            with zipfile.ZipFile(path) as archive:
                name = _find(archive.namelist())
                if name is None:
                    return None
                if archive.getinfo(name).file_size > MAX_XML_BYTES:
                    raise MetadataError("El ComicInfo.xml es sospechosamente grande.")
                return archive.read(name)
        names = _names_7z(path) if kind == "7z" else _names_rar(path)
        name = _find(names)
        if name is None:
            return None
        data = _extract_rar(path, name) if kind == "rar" else _extract_7z(path, name)
    except (OSError, zipfile.BadZipFile) as error:
        raise MetadataError(f"No se pudo leer el archivo: {error}") from error
    if len(data) > MAX_XML_BYTES:
        raise MetadataError("El ComicInfo.xml es sospechosamente grande.")
    return data


def _extract_7z(path: Path, name: str) -> bytes:
    done = _run(["7z", "x", "-so", "--", str(path), name])
    if done.returncode != 0:
        raise _tool_error(done, "No se pudo leer el ComicInfo.xml")
    return done.stdout


def read_info(path: Path) -> dict[str, str]:
    """Campos del ComicInfo.xml del archivo ({} si no tiene)."""
    xml = read_xml(path)
    return parse_info(xml) if xml else {}


# ---- Escritura ------------------------------------------------------------------------------------------------

def write_xml(path: Path, xml: bytes | None) -> None:
    """Deja `xml` como ComicInfo.xml del archivo (None lo elimina). Todo o nada: ante cualquier fallo, el original
    no cambia. Trabaja sobre una copia junto al original y solo la sustituye si la verificación pasa."""
    kind = archive_kind(path)
    if kind is None:
        raise MetadataError("No es un archivo ZIP, RAR ni 7-Zip (¿está dañado?).")
    if xml is not None:
        if len(xml) > MAX_XML_BYTES:
            raise MetadataError("El ComicInfo.xml es demasiado grande.")
        parse_info(xml)   # que sea XML bien formado
    size = path.stat().st_size
    if shutil.disk_usage(path.parent).free < size + SPACE_MARGIN:
        raise MetadataError("No hay espacio libre suficiente en el disco para reescribir el archivo.")
    temp = path.with_name(f".{uuid.uuid4().hex[:10]}.tmp.{kind}")
    try:
        {"zip": _write_zip, "rar": _write_rar, "7z": _write_7z}[kind](path, temp, xml)
        _verify(kind, path, temp, xml)
        shutil.copymode(path, temp)
        os.replace(temp, path)
    except OSError as error:
        raise MetadataError(f"No se pudo escribir el archivo: {error}") from error
    finally:
        with suppress(OSError):
            temp.unlink()


def _write_zip(source_path: Path, target_path: Path, xml: bytes | None) -> None:
    try:
        with zipfile.ZipFile(source_path) as source, zipfile.ZipFile(target_path, "w", allowZip64=True) as target:
            target.comment = source.comment
            for info in source.infolist():
                if info.flag_bits & 0x1:
                    raise MetadataError("El archivo está cifrado.")
                if info.filename.replace("\\", "/").lower() == ENTRY_NAME.lower():
                    continue
                with source.open(info) as reader, target.open(copy.copy(info), "w") as writer:
                    shutil.copyfileobj(reader, writer, 1024 * 1024)
            if xml is not None:
                target.writestr(ENTRY_NAME, xml, compress_type=zipfile.ZIP_DEFLATED)
    except zipfile.BadZipFile as error:
        raise MetadataError(f"ZIP dañado: {error}") from error


def _with_workfile(xml: bytes, action) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory(prefix="comic-identify-") as folder:
        (Path(folder) / ENTRY_NAME).write_bytes(xml)
        return action(Path(folder))


def _existing_name(kind: str, path: Path) -> str | None:
    return _find(_names_rar(path) if kind == "rar" else _names_7z(path))


def _write_rar(source_path: Path, target_path: Path, xml: bytes | None) -> None:
    if not shutil.which("rar"):
        raise MetadataError("Para escribir en un RAR hace falta el programa «rar» (paquete no libre «rar»).")
    shutil.copy2(source_path, target_path)
    existing = _existing_name("rar", target_path)
    if xml is None:
        if existing is None:
            return
        done = _run(["rar", "d", "-idq", "-y", "--", str(target_path), existing])
    else:
        # `rar a` sustituye la entrada si ya existe (con el nombre que tuviera, sin distinguir mayúsculas).
        done = _with_workfile(xml, lambda cwd: _run(["rar", "a", "-ep", "-idq", "-y", "--", str(target_path),
                                                    ENTRY_NAME], cwd))
    if done.returncode != 0:
        raise _tool_error(done, "«rar» no pudo modificar el archivo")


def _write_7z(source_path: Path, target_path: Path, xml: bytes | None) -> None:
    if not shutil.which("7z"):
        raise MetadataError("Para escribir en un 7-Zip hace falta el programa «7z».")
    shutil.copy2(source_path, target_path)
    existing = _existing_name("7z", target_path)
    if xml is None:
        if existing is None:
            return
        done = _run(["7z", "d", "-y", "-bd", "--", str(target_path), existing])
    else:
        done = _with_workfile(xml, lambda cwd: _run(["7z", "a", "-y", "-bd", "--", str(target_path), ENTRY_NAME], cwd))
    if done.returncode != 0:
        raise _tool_error(done, "«7z» no pudo modificar el archivo")


def _others(names: list[str]) -> list[str]:
    return sorted(n for n in names if n.replace("\\", "/").lower() != ENTRY_NAME.lower() and not n.endswith(("/", "\\")))


def _verify(kind: str, original: Path, result: Path, xml: bytes | None) -> None:
    """La copia debe abrirse, pasar la prueba de integridad y tener las mismas páginas más el ComicInfo esperado."""
    try:
        if kind == "zip":
            with zipfile.ZipFile(original) as before, zipfile.ZipFile(result) as after:
                if after.testzip() is not None:
                    raise MetadataError("La copia reescrita no pasa la prueba de integridad.")
                crc = {i.filename: i.CRC for i in before.infolist() if i.filename.lower() != ENTRY_NAME.lower()}
                crc_after = {i.filename: i.CRC for i in after.infolist() if i.filename.lower() != ENTRY_NAME.lower()}
                if crc != crc_after:
                    raise MetadataError("La copia reescrita no contiene exactamente los mismos archivos.")
            names_before, names_after = None, None
        else:
            listing = _names_rar if kind == "rar" else _names_7z
            names_before, names_after = _others(listing(original)), _others(listing(result))
            tester = ["rar", "t", "-idq", "--", str(result)] if kind == "rar" else ["7z", "t", "-bd", "--", str(result)]
            done = _run(tester)
            if done.returncode != 0:
                raise _tool_error(done, "La copia reescrita no pasa la prueba de integridad")
        if names_before != names_after:
            raise MetadataError("La copia reescrita no contiene exactamente los mismos archivos.")
    except (OSError, zipfile.BadZipFile) as error:
        raise MetadataError(f"La copia reescrita no se puede abrir: {error}") from error
    if read_xml(result) != xml:
        raise MetadataError("El ComicInfo.xml de la copia no es el esperado.")

