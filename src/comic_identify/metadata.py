"""Escritura de metadatos en lote con registro, para poder deshacer cada lote entero.

Cada archivo se escribe con `comicinfo.write_xml` (todo o nada por archivo). El registro guarda el ComicInfo.xml
anterior y el nuevo, byte a byte; deshacer restaura el anterior, o quita el ComicInfo.xml si el archivo no lo tenía.
"""
import base64
import json
import uuid
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .comicinfo import MetadataError, build_xml, parse_info, read_xml, write_xml
from .i18n import _
from .library import Library


@dataclass
class BatchResult:
    batch: str = ""
    written: list[Path] = field(default_factory=list)
    unchanged: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)


@dataclass
class UndoResult:
    restored: list[Path] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)


def _encode(data: bytes | None) -> str | None:
    return None if data is None else base64.b64encode(data).decode("ascii")


def _decode(text: str | None) -> bytes | None:
    return None if text is None else base64.b64decode(text)


def _append(log: Path, entry: dict) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"time": stamp, **entry}, ensure_ascii=False) + "\n")


def differs(current: Mapping[str, str], changes: Mapping[str, str | None]) -> bool:
    """¿Cambiaría algo? Falso si todos los campos pedidos ya valen eso (un campo vacío equivale a no tenerlo)."""
    return any(current.get(key, "") != (value or "").strip() for key, value in changes.items())


def write_batch(items: Iterable[tuple[Path, Mapping[str, str | None]]], log: Path, library: Library | None = None,
                progress: Callable[[int, int], None] | None = None) -> BatchResult:
    """Aplica los cambios de cada archivo. Un archivo que falla no impide los demás: queda en `failed` con el motivo.

    Lo escrito se anota en el registro en cuanto se escribe, así que un corte a medias sigue siendo deshacible.
    `progress(hechos, total)` se llama tras cada archivo escrito.
    """
    result = BatchResult(batch=uuid.uuid4().hex[:12])
    prepared: list[tuple[Path, bytes | None, bytes]] = []
    for path, changes in items:       # primero se prepara todo: lo que no se pueda leer o validar se descarta ya
        try:
            existing = read_xml(path)
            if not differs(parse_info(existing) if existing else {}, changes):
                result.unchanged.append(path)
                continue
            prepared.append((path, existing, build_xml(existing, changes)))
        except MetadataError as error:
            result.failed.append((path, str(error)))
    for done, (path, before, after) in enumerate(prepared, 1):
        if progress is not None:
            progress(done - 1, len(prepared))
        try:
            write_xml(path, after)
        except MetadataError as error:
            result.failed.append((path, str(error)))
            continue
        _append(log, {"batch": result.batch, "path": str(path), "before": _encode(before), "after": _encode(after)})
        if library is not None:
            library.refresh_stat(path, parse_info(after))
        result.written.append(path)
    if progress is not None:
        progress(len(prepared), len(prepared))
    return result


def delete_info(path: Path, log: Path, library: Library | None = None) -> bool:
    """Quita el ComicInfo.xml entero del archivo (no campo a campo, para empezar de cero); False si no tenía ninguno.
    Se anota en el mismo registro que escribir metadatos, así que se deshace igual (el botón «Deshacer» de Ajustes)."""
    existing = read_xml(path)
    if existing is None:
        return False
    write_xml(path, None)
    _append(log, {"batch": uuid.uuid4().hex[:12], "path": str(path), "before": _encode(existing), "after": None})
    if library is not None:
        library.refresh_stat(path, {})
    return True


def undo_last(log: Path, library: Library | None = None) -> UndoResult:
    """Deshace el último lote. Un archivo que ya no está, o que se ha vuelto a modificar desde entonces, se deja como
    está (no se pisan cambios posteriores) y se cuenta en `skipped`; un fallo al escribir lo deja en el registro."""
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    if not lines:
        raise LookupError(_("No hay metadatos que deshacer."))
    batch = json.loads(lines[-1])["batch"]
    start = len(lines)
    while start > 0 and json.loads(lines[start - 1])["batch"] == batch:
        start -= 1
    result, keep = UndoResult(), []
    for line in reversed(lines[start:]):
        entry = json.loads(line)
        path = Path(entry["path"])
        try:
            if not path.is_file():
                result.skipped.append((path, _("el archivo ya no está en esa ruta")))
                continue
            if read_xml(path) != _decode(entry["after"]):
                result.skipped.append((path, _("se ha modificado desde entonces")))
                continue
            write_xml(path, _decode(entry["before"]))
        except MetadataError as error:
            result.skipped.append((path, str(error)))
            keep.append(line)
            continue
        if library is not None:
            previous = _decode(entry["before"])
            library.refresh_stat(path, parse_info(previous) if previous else {})
        result.restored.append(path)
    with suppress(OSError):
        log.write_text("".join(line + "\n" for line in [*lines[:start], *reversed(keep)]), encoding="utf-8")
    return result
