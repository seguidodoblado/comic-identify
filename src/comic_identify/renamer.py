"""Renombrado seguro de archivos y carpetas de la colección, con registro para deshacerlo."""
import json
import os
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from .library import Library
from .naming import MAX_NAME_BYTES

TEMP_SUFFIX = ".renombrando-"


def _append(log: Path, entries: list[dict]) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with log.open("a", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps({"time": stamp, **entry}, ensure_ascii=False) + "\n")


def check_moves(moves: list[tuple[Path, Path]]) -> None:
    """Valida un lote antes de tocar nada. Un destino puede ser el nombre actual de otro archivo del lote."""
    sources = {src for src, _ in moves}
    targets = [dst for _, dst in moves]
    if len(set(targets)) != len(targets):
        raise FileExistsError("Dos archivos acabarían con el mismo nombre.")
    for src, dst in moves:
        if not src.is_file():
            raise FileNotFoundError(f"No existe el archivo: {src}")
        if len(dst.name.encode()) > MAX_NAME_BYTES or len(src.name.encode()) + 24 > MAX_NAME_BYTES:
            raise ValueError("El nombre resultante es demasiado largo para el sistema de archivos.")
        if dst.exists() and dst not in sources:
            raise FileExistsError(f"Ya existe un archivo con ese nombre: {dst.name}")


def move_all(moves: list[tuple[Path, Path]]) -> None:
    """Renombra un lote en dos fases (origen → temporal → destino): todo o nada.

    Así un nombre puede ser el destino de otro archivo del mismo lote (por ejemplo, al desplazar números) sin
    pisar nada. Si algo falla, lo ya hecho se revierte.
    """
    moves = [(src, dst) for src, dst in moves if src != dst]
    check_moves(moves)
    marker = uuid.uuid4().hex[:8]
    parked: list[tuple[Path, Path, Path]] = []     # (origen, destino, temporal)
    placed: list[tuple[Path, Path, Path]] = []
    try:
        for src, dst in moves:
            temp = src.with_name(f"{src.name}{TEMP_SUFFIX}{marker}")
            os.rename(src, temp)
            parked.append((src, dst, temp))
        for src, dst, temp in parked:
            os.rename(temp, dst)
            placed.append((src, dst, temp))
    except OSError:
        for _src, dst, temp in reversed(placed):
            with suppress(OSError):
                os.rename(dst, temp)
        for src, _dst, temp in reversed(parked):
            with suppress(OSError):
                os.rename(temp, src)
        raise


def rename_file(path: Path, stem: str, log: Path, library: Library | None = None) -> Path:
    """Renombra `path` a `stem` (conserva la extensión) en su misma carpeta. No sobrescribe nunca."""
    target = path.with_name(stem + path.suffix)
    if not path.is_file():
        raise FileNotFoundError(f"No existe el archivo: {path}")
    if target == path:
        return path
    move_all([(path, target)])
    if library is not None:
        library.rename(path, target)
    _append(log, [{"old": str(path), "new": str(target)}])
    return target


def rename_series(folder: Path, folder_name: str | None, moves: list[tuple[Path, Path]], log: Path,
                  library: Library | None = None) -> Path:
    """Renombra los archivos de `moves` y luego la carpeta, como un solo lote que se deshace de una vez.

    Devuelve la carpeta final. Si la carpeta no se puede renombrar, los archivos vuelven a su nombre.
    """
    moves = [(src, dst) for src, dst in moves if src != dst]
    new_folder = folder.with_name(folder_name) if folder_name and folder_name != folder.name else folder
    if new_folder != folder:
        if len(new_folder.name.encode()) > MAX_NAME_BYTES:
            raise ValueError("El nombre de la carpeta es demasiado largo para el sistema de archivos.")
        if new_folder.exists():
            raise FileExistsError(f"Ya existe una carpeta con ese nombre: {new_folder.name}")
    move_all(moves)
    try:
        if new_folder != folder:
            os.rename(folder, new_folder)
    except OSError:
        move_all([(dst, src) for src, dst in moves])
        raise
    if library is not None:
        for src, dst in moves:
            library.rename(src, dst)
        if new_folder != folder:
            library.rename_folder(folder, new_folder)
    batch = uuid.uuid4().hex[:12]
    entries = [{"batch": batch, "old": str(src), "new": str(dst)} for src, dst in moves]
    if new_folder != folder:
        entries.append({"batch": batch, "kind": "folder", "old": str(folder), "new": str(new_folder)})
    _append(log, entries)
    return new_folder


def undo_last(log: Path, library: Library | None = None) -> list[tuple[Path, Path]]:
    """Deshace el último renombrado (o el último lote entero). Devuelve los pares (antes, después de deshacer)."""
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    if not lines:
        raise LookupError("No hay renombrados que deshacer.")
    group = [json.loads(lines[-1])]
    batch = group[0].get("batch")
    while batch and len(group) < len(lines) and json.loads(lines[-1 - len(group)]).get("batch") == batch:
        group.append(json.loads(lines[-len(group) - 1]))
    folder = next((e for e in group if e.get("kind") == "folder"), None)
    where = Path(folder["new"]) if folder else None   # los archivos están ahora dentro de la carpeta nueva

    def here(path: Path) -> Path:
        return where / path.name if where else path

    moves = [(here(Path(e["new"])), here(Path(e["old"]))) for e in group if e.get("kind") != "folder"]
    if folder and (not where.is_dir() or Path(folder["old"]).exists()):
        raise FileExistsError("La carpeta ya no está o su nombre original está ocupado.")
    move_all(moves)
    if library is not None:
        for src, dst in moves:
            library.rename(src, dst)
    pairs = list(moves)
    if folder:
        try:
            os.rename(where, Path(folder["old"]))
        except OSError:
            move_all([(dst, src) for src, dst in moves])
            if library is not None:
                for src, dst in moves:
                    library.rename(dst, src)
            raise
        if library is not None:
            library.rename_folder(where, Path(folder["old"]))
        pairs.append((where, Path(folder["old"])))
    with suppress(OSError):
        log.write_text("".join(line + "\n" for line in lines[:len(lines) - len(group)]), encoding="utf-8")
    return pairs
