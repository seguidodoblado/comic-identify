import json
import zipfile
from pathlib import Path

import pytest
from conftest import jpeg, make_cover

from comic_identify.library import Library
from comic_identify.renamer import rename_file, undo_last


def _cbz(path: Path, seed: int = 1) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("01.jpg", jpeg(make_cover(seed)))
    return path


def _paths(db: Path) -> set[str]:
    import sqlite3
    with sqlite3.connect(db) as connection:
        return {row[0] for row in connection.execute("SELECT path FROM covers")}


def test_rename_keeps_extension_updates_index_and_logs(tmp_path):
    comic = _cbz(tmp_path / "viejo.CBR")
    library = Library(tmp_path / "lib.db")
    library.index([tmp_path])
    log = tmp_path / "data" / "renames.log"

    new = rename_file(comic, "Punisher 🇪🇸 [1991] (1993) - Forum", log, library)

    assert new == tmp_path / "Punisher 🇪🇸 [1991] (1993) - Forum.CBR" and new.exists() and not comic.exists()
    assert _paths(tmp_path / "lib.db") == {str(new)}                         # el índice no pierde el archivo
    entry = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert entry["old"] == str(comic) and entry["new"] == str(new) and "T" in entry["time"]


def test_rename_never_overwrites_and_rejects_bad_targets(tmp_path):
    first, second = _cbz(tmp_path / "a.cbz", 1), _cbz(tmp_path / "b.cbz", 2)
    log = tmp_path / "renames.log"
    with pytest.raises(FileExistsError):
        rename_file(first, "b", log)
    assert first.exists() and second.read_bytes() != first.read_bytes()      # nada se ha tocado
    assert rename_file(first, "a", log) == first and not log.exists()         # mismo nombre: no hace nada
    with pytest.raises(ValueError, match="largo"):
        rename_file(first, "x" * 300, log)
    with pytest.raises(FileNotFoundError):
        rename_file(tmp_path / "no_existe.cbz", "z", log)


def test_undo_restores_name_index_and_pops_the_log(tmp_path):
    comic = _cbz(tmp_path / "original.cbz")
    library = Library(tmp_path / "lib.db")
    library.index([tmp_path])
    log = tmp_path / "renames.log"
    step1 = rename_file(comic, "paso1", log, library)
    step2 = rename_file(step1, "paso2", log, library)

    assert undo_last(log, library) == [(step2, step1)] and step1.exists() and not step2.exists()
    assert _paths(tmp_path / "lib.db") == {str(step1)}
    assert undo_last(log, library) == [(step1, comic)] and comic.exists()
    with pytest.raises(LookupError):
        undo_last(log, library)


def test_undo_refuses_when_it_would_clobber_or_the_file_is_gone(tmp_path):
    comic = _cbz(tmp_path / "a.cbz")
    log = tmp_path / "renames.log"
    new = rename_file(comic, "b", log)
    _cbz(tmp_path / "a.cbz", 2)                          # el nombre original vuelve a estar ocupado
    with pytest.raises(FileExistsError):
        undo_last(log)
    (tmp_path / "a.cbz").unlink()
    new.unlink()
    with pytest.raises(FileNotFoundError):
        undo_last(log)
