"""Índice local de portadas de la colección del usuario (SQLite + hash perceptual)."""
import os
import sqlite3
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event

import numpy as np
from PIL import Image

from .comicinfo import MetadataError, category_of, read_info
from .covers import COMIC_EXTENSIONS, read_cover
from .hashing import HASH_BYTES, dhash_bytes, distances
from .i18n import _

Progress = Callable[[int, int], None]
MAX_FAILED_LISTED = 20


@dataclass
class IndexStats:
    indexed: int = 0
    unchanged: int = 0
    failed: int = 0
    removed: int = 0
    refreshed: int = 0    # archivos sin cambios a los que solo se les han leído los metadatos
    unavailable: list[str] = field(default_factory=list)   # carpetas sin acceso o vacías: no se limpian
    failed_files: list[tuple[str, str]] = field(default_factory=list)   # (ruta, motivo) de los primeros


def find_comics(folders: Iterable[Path]) -> list[Path]:
    found: set[Path] = set()
    for folder in folders:
        found.update(p for p in Path(folder).rglob("*")
                     if p.suffix.lower() in COMIC_EXTENSIONS and p.is_file())
    return sorted(found)


def _prefixes(folders: list[Path]) -> list[str]:
    """Rutas con barra final: `/a/comics/` no debe confundirse con `/a/comics2/`."""
    return [os.path.join(str(folder), "") for folder in folders]


def _under(path: str, prefixes: list[str]) -> bool:
    return any(path.startswith(prefix) for prefix in prefixes)


def orphans(known: Iterable[str], seen: set[str], available: list[Path], configured: list[Path]) -> list[str]:
    """Rutas del índice que se pueden olvidar.

    Se olvida lo que ya no está en una carpeta accesible y lo que no pertenece a ninguna carpeta
    configurada. Lo de una carpeta configurada pero sin acceso (disco desmontado, punto de montaje
    vacío) se conserva: perder el índice de un disco externo por no tenerlo conectado sale muy caro.
    """
    available, configured = _prefixes(available), _prefixes(configured)
    return [p for p in known
            if p not in seen and (_under(p, available) or not _under(p, configured))]


META_COLUMNS = (("series", "TEXT"), ("volume", "TEXT"), ("number", "TEXT"), ("count", "INTEGER"),
                ("category", "TEXT"), ("tagged", "INTEGER"), ("meta_state", "TEXT"))   # resumen del ComicInfo.xml


def _state(info: os.stat_result) -> str:
    """Versión del archivo con la que se leyeron sus metadatos: si cambia, hay que volver a leerlos."""
    return f"{info.st_mtime}:{info.st_size}"


def _meta_values(info: Mapping[str, str]) -> tuple:
    """(serie, volumen, número, total, categoría, ¿tiene ComicInfo?) de los campos de un ComicInfo.xml."""
    count = info.get("Count", "")
    return (info.get("Series", ""), info.get("Volume", ""), info.get("Number", ""),
            int(count) if count.isdigit() else None, category_of(info.get("Tags", "")), 1 if info else 0)


def read_meta(path: Path) -> dict[str, str]:
    """Campos del ComicInfo.xml del archivo; {} si no lo tiene o no se puede leer (no debe abortar el índice)."""
    try:
        return read_info(path)
    except (MetadataError, OSError):
        return {}


class Library:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS covers "
                       "(path TEXT PRIMARY KEY, mtime REAL, size INTEGER, hash BLOB)")
            present = {row[1] for row in db.execute("PRAGMA table_info(covers)")}
            for name, kind in META_COLUMNS:   # un índice anterior se amplía; sus metadatos se leen en el siguiente índice
                if name not in present:
                    db.execute(f"ALTER TABLE covers ADD COLUMN {name} {kind}")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def count(self) -> int:
        with closing(self._connect()) as db:
            return db.execute("SELECT COUNT(*) FROM covers").fetchone()[0]

    def index(self, folders: Iterable[Path], progress: Progress | None = None,
              cancel: Event | None = None, workers: int = 4) -> IndexStats:
        """Añade o actualiza las portadas nuevas o modificadas; olvida las que ya no existen."""
        stats = IndexStats()
        folders = [Path(f) for f in folders]
        found = {folder: find_comics([folder]) for folder in folders}
        files = sorted({f for comics in found.values() for f in comics})
        with closing(self._connect()) as db:
            known = {p: (m, s, state) for p, m, s, state in
                     db.execute("SELECT path, mtime, size, meta_state FROM covers")}
            pending = []   # (ruta, mtime, tamaño, ¿cambió el archivo?, versión): si no cambió, solo faltan sus metadatos
            for path in files:
                info = path.stat()
                row = known.get(str(path))
                changed = row is None or row[:2] != (info.st_mtime, info.st_size)
                if changed or row[2] != _state(info):
                    pending.append((path, info.st_mtime, info.st_size, changed, _state(info)))
                else:
                    stats.unchanged += 1

            def hash_cover(entry):
                """Devuelve (entrada, huella, motivo del fallo, metadatos). Un archivo raro no debe abortar el lote."""
                path, changed = entry[0], entry[3]
                meta = read_meta(path)
                if not changed:
                    return entry, None, "", meta
                try:
                    data = read_cover(path)
                    if not data:
                        return entry, None, _("sin imágenes o archivo dañado"), meta
                    digest = dhash_bytes(data)
                    return entry, digest, "" if digest else _("imagen no válida"), meta
                except Image.DecompressionBombError:   # escaneo enorme que Pillow rechaza por seguridad
                    return entry, None, _("imagen enorme"), meta
                except Exception as error:  # noqa: BLE001
                    return entry, None, type(error).__name__, meta

            with ThreadPoolExecutor(workers) as pool:
                for done, (entry, digest, reason, meta) in enumerate(pool.map(hash_cover, pending), 1):
                    if cancel is not None and cancel.is_set():
                        break
                    if not entry[3]:   # sin cambios en el archivo: la huella ya está, solo se anotan los metadatos
                        db.execute("UPDATE covers SET series = ?, volume = ?, number = ?, count = ?, category = ?, "
                                   "tagged = ?, meta_state = ? WHERE path = ?",
                                   (*_meta_values(meta), entry[4], str(entry[0])))
                        stats.refreshed += 1
                    elif digest is None:
                        stats.failed += 1
                        if len(stats.failed_files) < MAX_FAILED_LISTED:
                            stats.failed_files.append((str(entry[0]), reason))
                    else:
                        db.execute("INSERT OR REPLACE INTO covers (path, mtime, size, hash, series, volume, number, "
                                   "count, category, tagged, meta_state) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                   (str(entry[0]), entry[1], entry[2], digest, *_meta_values(meta), entry[4]))
                        stats.indexed += 1
                    if done % 50 == 0:
                        db.commit()
                    if progress:
                        progress(done, len(pending))
            if cancel is None or not cancel.is_set():
                available = [folder for folder, comics in found.items() if comics]
                stats.unavailable = [str(f) for f in found if f not in available]
                gone = orphans(known, {str(f) for f in files}, available, folders)
                db.executemany("DELETE FROM covers WHERE path = ?", [(p,) for p in gone])
                stats.removed = len(gone)
            db.commit()
        return stats

    def rename(self, old: Path, new: Path) -> None:
        """Actualiza la ruta de un archivo ya indexado (al renombrarlo), sin volver a leerlo."""
        with closing(self._connect()) as db, db:
            db.execute("UPDATE covers SET path = ? WHERE path = ?", (str(new), str(old)))

    def refresh_stat(self, path: Path, meta: Mapping[str, str]) -> None:
        """Anota el tamaño, la fecha y los metadatos de un archivo indexado cuyo contenido se ha reescrito sin cambiar
        su portada, para que el próximo índice no lo vuelva a leer."""
        try:
            info = path.stat()
        except OSError:
            return
        with closing(self._connect()) as db, db:
            db.execute("UPDATE covers SET mtime = ?, size = ?, series = ?, volume = ?, number = ?, count = ?, "
                       "category = ?, tagged = ?, meta_state = ? WHERE path = ?",
                       (info.st_mtime, info.st_size, *_meta_values(meta), _state(info), str(path)))

    def series_rows(self) -> list[tuple]:
        """(ruta, serie, volumen, número, total, categoría, ¿con metadatos?) de todos los archivos indexados."""
        with closing(self._connect()) as db:
            return db.execute("SELECT path, COALESCE(series, ''), COALESCE(volume, ''), COALESCE(number, ''), count, "
                              "COALESCE(category, ''), COALESCE(tagged, 0) FROM covers").fetchall()

    def rename_folder(self, old: Path, new: Path) -> None:
        """Cambia el prefijo de todas las rutas indexadas de una carpeta que se ha renombrado."""
        old_prefix, new_prefix = _prefixes([old])[0], _prefixes([new])[0]
        with closing(self._connect()) as db, db:
            db.execute("UPDATE covers SET path = ? || substr(path, ?) WHERE substr(path, 1, ?) = ?",
                       (new_prefix, len(old_prefix) + 1, len(old_prefix), old_prefix))

    def forget_folder(self, folder: Path) -> int:
        """Olvida las portadas de una carpeta (al quitarla de la lista). Devuelve cuántas."""
        prefix = _prefixes([folder])[0]
        with closing(self._connect()) as db, db:
            return db.execute("DELETE FROM covers WHERE substr(path, 1, ?) = ?",
                              (len(prefix), prefix)).rowcount

    def find(self, variants: list[bytes], limit: int = 5) -> list[tuple[Path, float]]:
        """Las portadas más parecidas del índice, de mayor a menor similitud."""
        with closing(self._connect()) as db:
            rows = db.execute("SELECT path, hash FROM covers").fetchall()
        if not rows:
            return []
        matrix = np.frombuffer(b"".join(r[1] for r in rows), dtype=np.uint8).reshape(-1, HASH_BYTES)
        nearest = np.min([distances(v, matrix) for v in variants], axis=0)
        best = np.argsort(nearest)[:limit]
        scores = 1 - nearest[best] / (HASH_BYTES * 8)
        return [(Path(rows[i][0]), float(s)) for i, s in zip(best, scores)]
