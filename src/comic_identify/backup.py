"""Copias de seguridad de los datos de la aplicación (índices, ajustes y registros de deshacer) y su restauración.

Cada copia es un único `.zip` con un `manifest.json` (versión, fecha, tamaño y SHA-256 de cada archivo). Las bases
SQLite se copian con la API de copia de SQLite (coherente aunque otro proceso las esté usando), no a pie de archivo.
Nada se da por bueno sin comprobarlo: al crear una copia se verifica el zip y las bases; al restaurar se verifican
los SHA-256 y las bases ANTES de tocar nada, y se guarda una copia del estado actual por si hay que volver atrás.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from collections.abc import Mapping
from contextlib import closing, suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import settings

MANIFEST = "manifest.json"
PREFIX = "comic-identify-"
AUTO, MANUAL, RESTORE = "auto", "manual", "restaurar"
KIND_LABELS = {AUTO: "automática", MANUAL: "manual", RESTORE: "antes de restaurar"}
DEFAULT_KEEP = 10
_STAMP = "%Y-%m-%d_%H-%M-%S"


class BackupError(Exception):
    """No se pudo crear, leer o restaurar una copia; lo que había antes queda como estaba."""


@dataclass
class BackupInfo:
    path: Path
    created: datetime
    kind: str
    size: int
    names: list[str] = field(default_factory=list)


@dataclass
class RestoreResult:
    restored: list[str]
    safety: Path | None   # copia del estado anterior a restaurar


def default_sources() -> dict[str, Path]:
    """Qué se copia (nombre dentro del zip -> dónde vive). La caché de WebKit no: es desechable."""
    return {"config.json": settings.CONFIG_FILE, "library.db": settings.LIBRARY_DB, "gcd_es.db": settings.GCD_DB,
            "universomarvel.db": settings.UNIVERSOMARVEL_DB, "tebeosfera.db": settings.TEBEOSFERA_DB,
            "renames.log": settings.RENAME_LOG, "metadata.log": settings.METADATA_LOG,
            "gcstar.log": settings.GCSTAR_LOG}


def _is_db(name: str) -> bool:
    return name.endswith(".db")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _integrity(path: Path) -> None:
    try:
        with closing(sqlite3.connect(path)) as db:
            answer = db.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.Error as error:
        raise BackupError(f"«{path.name}» no es una base de datos válida: {error}") from error
    if not answer or answer[0] != "ok":
        raise BackupError(f"La base de datos «{path.name}» está dañada.")


def _snapshot(source: Path, target: Path, name: str) -> None:
    if _is_db(name):
        try:
            with closing(sqlite3.connect(source)) as origin, \
                    closing(sqlite3.connect(target)) as copy:
                origin.backup(copy)
        except sqlite3.Error as error:
            raise BackupError(f"No se pudo copiar «{name}»: {error}") from error
        _integrity(target)
    else:
        shutil.copyfile(source, target)


def _stamp_name(when: datetime, kind: str) -> str:
    return f"{PREFIX}{when.strftime(_STAMP)}-{kind}.zip"


def read_manifest(archive: Path) -> dict:
    try:
        with zipfile.ZipFile(archive) as zipped:
            manifest = json.loads(zipped.read(MANIFEST))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
        raise BackupError(f"«{archive.name}» no es una copia válida: {error}") from error
    if not isinstance(manifest.get("files"), dict):
        raise BackupError(f"«{archive.name}» no es una copia válida: manifiesto incompleto.")
    return manifest


def _verify_archive(archive: Path) -> None:
    manifest = read_manifest(archive)
    try:
        with zipfile.ZipFile(archive) as zipped:
            if (bad := zipped.testzip()) is not None:
                raise BackupError(f"La copia está dañada ({bad}).")
            for name, meta in manifest["files"].items():
                digest = hashlib.sha256(zipped.read(name)).hexdigest()
                if digest != meta.get("sha256"):
                    raise BackupError(f"«{name}» no coincide con su SHA-256 en la copia.")
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise BackupError(f"La copia no se puede leer: {error}") from error


def create(dest_dir: Path, kind: str, sources: Mapping[str, Path] | None = None, version: str = "") -> Path:
    """Crea una copia en `dest_dir` y devuelve su ruta; se escribe en un archivo temporal y solo se da por buena
    (se renombra) cuando ha pasado la verificación."""
    sources = default_sources() if sources is None else sources
    present = {name: path for name, path in sources.items() if path.is_file()}
    if not present:
        raise BackupError("Todavía no hay datos que copiar.")
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=dest_dir, prefix=".copia-") as tmp:
            files, staged = {}, {}
            for name, path in present.items():
                before = path.stat()   # antes de copiar: si cambia durante la copia, la próxima vez cuenta como cambiada
                staged[name] = Path(tmp) / name
                _snapshot(path, staged[name], name)
                files[name] = {"size": staged[name].stat().st_size, "sha256": _sha256(staged[name]),
                               "source_size": before.st_size, "source_mtime_ns": before.st_mtime_ns}
            now = datetime.now().astimezone()
            final = dest_dir / _stamp_name(now, kind)
            for extra in range(2, 100):   # dos copias en el mismo segundo no se pisan
                if not final.exists():
                    break
                final = dest_dir / _stamp_name(now, f"{kind}-{extra}")
            manifest = {"app_version": version, "created": now.isoformat(timespec="seconds"), "kind": kind,
                        "files": files}
            part = final.with_name(final.name + ".part")
            descriptor = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # lleva la clave de ComicVine
            with os.fdopen(descriptor, "wb") as handle, zipfile.ZipFile(handle, "w", zipfile.ZIP_DEFLATED) as zipped:
                for name, path in staged.items():
                    zipped.write(path, name)
                zipped.writestr(MANIFEST, json.dumps(manifest, indent=2, ensure_ascii=False))
            try:
                _verify_archive(part)
                os.replace(part, final)
            except BaseException:
                with suppress(OSError):
                    part.unlink()
                raise
    except OSError as error:
        raise BackupError(f"No se pudo escribir la copia en «{dest_dir}»: {error}") from error
    return final


def list_backups(dest_dir: Path) -> list[BackupInfo]:
    """Las copias de la carpeta, de la más reciente a la más antigua; se ignora lo que no sea una copia legible."""
    found = []
    for archive in dest_dir.glob(f"{PREFIX}*.zip"):
        try:
            manifest = read_manifest(archive)
            created = datetime.fromisoformat(manifest["created"])
            found.append((archive.stat().st_mtime_ns, BackupInfo(archive, created, str(manifest.get("kind", "")),
                                                                  archive.stat().st_size, sorted(manifest["files"]))))
        except (BackupError, KeyError, ValueError, OSError):
            continue
    # la fecha del manifiesto tiene precisión de segundos: a igualdad, manda la del archivo
    return [info for _mtime, info in sorted(found, key=lambda item: (item[1].created, item[0]), reverse=True)]


def unchanged_since_last(dest_dir: Path, sources: Mapping[str, Path] | None = None) -> bool:
    """¿Los datos son los mismos (tamaño y fecha de modificación) que cuando se hizo la última copia? Sirve para no
    llenar la carpeta de copias idénticas cada vez que se cierra la aplicación."""
    sources = default_sources() if sources is None else sources
    backups = list_backups(dest_dir)
    if not backups:
        return False
    files = read_manifest(backups[0].path)["files"]
    present = {name: path.stat() for name, path in sources.items() if path.is_file()}
    if set(present) != set(files):
        return False
    return all(files[name].get("source_size") == stat.st_size and files[name].get("source_mtime_ns") == stat.st_mtime_ns
               for name, stat in present.items())


def prune(dest_dir: Path, keep: int) -> list[Path]:
    """Borra las copias automáticas más antiguas y deja las `keep` últimas. Las manuales y las de antes de
    restaurar nunca se borran solas."""
    automatic = [info for info in list_backups(dest_dir) if info.kind == AUTO]
    removed = []
    for info in automatic[max(keep, 1):]:
        with suppress(OSError):
            info.path.unlink()
            removed.append(info.path)
    return removed


def restore(archive: Path, targets: Mapping[str, Path] | None = None, version: str = "") -> RestoreResult:
    """Devuelve los datos de la copia a su sitio. Primero se extrae y se comprueba todo (SHA-256 y bases de datos)
    junto al destino; solo entonces se guarda una copia del estado actual y se sustituyen los archivos. Si algo
    falla antes de sustituir, no se ha tocado nada. Los nombres del zip que no conocemos se ignoran (nunca se usan
    como ruta)."""
    targets = default_sources() if targets is None else targets
    manifest = read_manifest(archive)
    names = [name for name in manifest["files"] if name in targets]
    if not names:
        raise BackupError("La copia no contiene ningún dato que restaurar.")
    staged: dict[str, Path] = {}
    try:
        with zipfile.ZipFile(archive) as zipped:
            for name in names:
                targets[name].parent.mkdir(parents=True, exist_ok=True)
                descriptor, temp = tempfile.mkstemp(dir=targets[name].parent, prefix=f".{name}.", suffix=".restaurando")
                staged[name] = Path(temp)
                with os.fdopen(descriptor, "wb") as out, zipped.open(name) as source:
                    shutil.copyfileobj(source, out)
                if _sha256(staged[name]) != manifest["files"][name].get("sha256"):
                    raise BackupError(f"«{name}» está dañado en la copia (no coincide su SHA-256).")
                if _is_db(name):
                    _integrity(staged[name])
        safety = None
        if any(targets[name].is_file() for name in targets):
            safety = create(archive.parent, RESTORE, targets, version)
        for name, temp in staged.items():
            os.replace(temp, targets[name])
            if _is_db(name):   # restos de una sesión anterior que corromperían la base restaurada
                for suffix in ("-journal", "-wal", "-shm"):
                    with suppress(OSError):
                        Path(str(targets[name]) + suffix).unlink()
        staged.clear()
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise BackupError(f"No se pudo restaurar: {error}") from error
    finally:
        for temp in staged.values():
            with suppress(OSError):
                temp.unlink()
    return RestoreResult(names, safety)
