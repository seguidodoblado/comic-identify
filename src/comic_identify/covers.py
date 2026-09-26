"""Extracción de la primera página (la portada) de archivos CBZ/CBR."""
import io
import shutil
import subprocess
import zipfile
from pathlib import Path

from PIL import Image

from .naming import natural_key

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
COMIC_EXTENSIONS = (".cbz", ".cbr", ".cb7", ".zip", ".rar", ".7z")


def _images(names: list[str]) -> list[str]:
    """Las páginas (imágenes) de una lista de nombres, en orden natural."""
    return sorted((n for n in names if n.lower().endswith(IMAGE_EXTENSIONS) and "__MACOSX" not in n), key=natural_key)


def _first_image(names: list[str]) -> str | None:
    images = _images(names)
    return images[0] if images else None


def _from_zip(path: Path) -> bytes | None:
    with zipfile.ZipFile(path) as archive:
        name = _first_image(archive.namelist())
        return archive.read(name) if name else None


def _run(command: list[str]) -> bytes | None:
    try:
        done = subprocess.run(command, capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 else None


def _names_unrar(path: Path) -> list[str]:
    listing = _run(["unrar", "lb", "--", str(path)])
    return listing.decode(errors="replace").splitlines() if listing else []


def _names_7z(path: Path) -> list[str]:
    listing = _run(["7z", "l", "-slt", "-ba", "--", str(path)])
    return [line[7:] for line in listing.decode(errors="replace").splitlines()
            if line.startswith("Path = ")] if listing else []


def _from_unrar(path: Path) -> bytes | None:
    name = _first_image(_names_unrar(path))
    return _run(["unrar", "p", "-inul", "--", str(path), name]) if name else None


def _from_7z(path: Path) -> bytes | None:
    name = _first_image(_names_7z(path))
    return _run(["7z", "x", "-so", "--", str(path), name]) if name else None


def _from_rar(path: Path) -> bytes | None:
    """RAR con `unrar` y, si no lo lee o no está, con `7z`: un «.cbr» a veces es en realidad un 7-Zip."""
    for tool, reader in (("unrar", _from_unrar), ("7z", _from_7z)):
        if shutil.which(tool) and (data := reader(path)):
            return data
    return None


def read_cover(path: Path) -> bytes | None:
    """Devuelve los bytes de la portada, o None si no se pudo leer.

    Se decide por el contenido, no por la extensión: hay muchos .cbr que en realidad son ZIP.
    """
    try:
        return _from_zip(path) if zipfile.is_zipfile(path) else _from_rar(path)
    except (OSError, zipfile.BadZipFile, KeyError):
        return None


def list_pages(path: Path) -> list[str]:
    """Nombres de las páginas del archivo en orden de lectura (la primera es la portada); [] si no se puede leer."""
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                return _images(archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return []
    for tool, lister in (("unrar", _names_unrar), ("7z", _names_7z)):
        if shutil.which(tool) and (pages := _images(lister(path))):
            return pages
    return []


def read_page(path: Path, name: str) -> bytes | None:
    """Los bytes de una página de `list_pages`, o None si no se pudo leer."""
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                return archive.read(name)
    except (OSError, zipfile.BadZipFile, KeyError):
        return None
    for tool, command in (("unrar", ["unrar", "p", "-inul", "--", str(path), name]),
                          ("7z", ["7z", "x", "-so", "--", str(path), name])):
        if shutil.which(tool) and (data := _run(command)):
            return data
    return None


def cover_to_png(comic: Path, target: Path) -> None:
    """Guarda la portada de un CBR/CBZ como PNG. Lanza ValueError si no tiene imágenes."""
    data = read_cover(comic)
    if data is None:
        raise ValueError("no se encontró ninguna imagen en el archivo")
    with Image.open(io.BytesIO(data)) as image:
        image.convert("RGB").save(target, "PNG")


def thumbnail_bytes(data: bytes, max_side: int = 300) -> bytes | None:
    """Reduce una imagen a una miniatura JPEG para mostrarla; None si no es una imagen válida."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = image.convert("RGB")
            image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=85)
            return buffer.getvalue()
    except (OSError, ValueError):
        return None
