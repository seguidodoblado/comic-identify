import json
import zipfile
from pathlib import Path

import pytest
from test_comicinfo import needs_rar, rar_fixture

from comic_identify import metadata
from comic_identify.comicinfo import MetadataError, build_xml, read_info, read_xml, write_xml
from comic_identify.library import Library
from comic_identify.metadata import delete_info, undo_last, write_batch


def make_zip(path: Path, info: dict[str, str] | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("01.jpg", b"\xff\xd8uno" * 20)
        archive.writestr("02.jpg", b"\xff\xd8dos" * 20)
        if info is not None:
            archive.writestr("ComicInfo.xml", build_xml(None, info))
    return path


def pages(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return [n for n in archive.namelist() if n != "ComicInfo.xml"]


def test_batch_writes_every_file_and_logs_before_and_after(tmp_path):
    log = tmp_path / "metadata.log"
    a, b = make_zip(tmp_path / "a.cbz"), make_zip(tmp_path / "b.cbz", {"Series": "Viejo", "Writer": "Moore"})
    result = write_batch([(a, {"Series": "Nueva", "Number": "1"}), (b, {"Series": "Nueva", "Number": "2"})], log)
    assert result.written == [a, b] and not result.failed and not result.unchanged
    assert read_info(a) == {"Series": "Nueva", "Number": "1"}
    assert read_info(b) == {"Series": "Nueva", "Number": "2", "Writer": "Moore"}     # lo que no se toca, se conserva
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [e["path"] for e in entries] == [str(a), str(b)] and {e["batch"] for e in entries} == {result.batch}
    assert entries[0]["before"] is None and entries[1]["before"] is not None


def test_files_that_already_have_those_values_are_not_rewritten(tmp_path):
    log = tmp_path / "metadata.log"
    a = make_zip(tmp_path / "a.cbz", {"Series": "Igual", "Number": "1"})
    stamp = a.stat().st_mtime_ns
    result = write_batch([(a, {"Series": "Igual", "Number": "1", "Title": ""})], log)   # «Title» vacío y ya inexistente
    assert result.unchanged == [a] and not result.written and a.stat().st_mtime_ns == stamp
    assert not log.exists()


def test_a_bad_file_does_not_stop_the_others(tmp_path):
    log = tmp_path / "metadata.log"
    good, damaged = make_zip(tmp_path / "good.cbz"), tmp_path / "damaged.cbz"
    damaged.write_bytes(b"\x00" * 2048)
    result = write_batch([(damaged, {"Series": "X"}), (good, {"Series": "X"}), (good, {"Year": "20x0"})], log)
    assert result.written == [good]
    assert [p for p, _ in result.failed] == [damaged, good] and "dañado" in result.failed[0][1]
    assert read_info(good) == {"Series": "X"}
    assert len(log.read_text(encoding="utf-8").splitlines()) == 1        # solo lo escrito se registra


def test_undo_restores_the_previous_metadata_or_removes_it(tmp_path):
    log = tmp_path / "metadata.log"
    fresh, had = make_zip(tmp_path / "fresh.cbz"), make_zip(tmp_path / "had.cbz", {"Series": "Antes", "Writer": "Moore"})
    original = read_xml(had)
    write_batch([(fresh, {"Series": "Nuevo"}), (had, {"Series": "Nuevo"})], log)
    result = undo_last(log)
    assert sorted(result.restored) == sorted([fresh, had]) and not result.skipped
    assert read_xml(fresh) is None and read_xml(had) == original         # byte a byte
    assert pages(fresh) == ["01.jpg", "02.jpg"]
    assert not log.read_text(encoding="utf-8")
    with pytest.raises(LookupError):
        undo_last(log)


def test_delete_info_removes_the_whole_comicinfo_and_can_be_undone(tmp_path):
    log = tmp_path / "metadata.log"
    had = make_zip(tmp_path / "had.cbz", {"Series": "Antes", "Writer": "Moore"})
    original = read_xml(had)
    assert delete_info(had, log) is True
    assert read_xml(had) is None and pages(had) == ["01.jpg", "02.jpg"]      # el resto del archivo, intacto
    result = undo_last(log)
    assert result.restored == [had] and read_xml(had) == original           # byte a byte


def test_delete_info_on_a_file_with_no_comicinfo_does_nothing_and_is_not_logged(tmp_path):
    log = tmp_path / "metadata.log"
    fresh = make_zip(tmp_path / "fresh.cbz")
    assert delete_info(fresh, log) is False
    assert not log.exists()


def test_delete_info_updates_the_library_index(tmp_path):
    import sqlite3
    log, library = tmp_path / "metadata.log", Library(tmp_path / "lib.db")
    had = make_zip(tmp_path / "had.cbz", {"Series": "Antes"})
    stat = had.stat()
    with sqlite3.connect(tmp_path / "lib.db") as db:
        db.execute("INSERT INTO covers (path, mtime, size, hash) VALUES (?, ?, ?, ?)",
                   (str(had), stat.st_mtime, stat.st_size, b"\x00" * 32))
    delete_info(had, log, library)
    with sqlite3.connect(tmp_path / "lib.db") as db:
        assert db.execute("SELECT size FROM covers WHERE path = ?", (str(had),)).fetchone() == (had.stat().st_size,)


def test_undo_only_reverts_the_last_batch(tmp_path):
    log = tmp_path / "metadata.log"
    a = make_zip(tmp_path / "a.cbz")
    write_batch([(a, {"Series": "Primero"})], log)
    write_batch([(a, {"Series": "Segundo"})], log)
    undo_last(log)
    assert read_info(a) == {"Series": "Primero"}
    undo_last(log)
    assert read_xml(a) is None


def test_undo_does_not_overwrite_later_edits_or_missing_files(tmp_path):
    log = tmp_path / "metadata.log"
    edited, moved, fine = (make_zip(tmp_path / f"{n}.cbz") for n in ("edited", "moved", "fine"))
    write_batch([(edited, {"Series": "X"}), (moved, {"Series": "X"}), (fine, {"Series": "X"})], log)
    write_xml(edited, build_xml(read_xml(edited), {"Series": "Editado a mano"}))     # otro programa lo cambia después
    moved.rename(tmp_path / "otro-nombre.cbz")
    result = undo_last(log)
    assert result.restored == [fine]
    assert dict(result.skipped) == {edited: "se ha modificado desde entonces", moved: "el archivo ya no está en esa ruta"}
    assert read_info(edited) == {"Series": "Editado a mano"} and read_xml(fine) is None


def test_a_failed_restore_stays_in_the_log_for_a_retry(tmp_path, monkeypatch):
    log = tmp_path / "metadata.log"
    a = make_zip(tmp_path / "a.cbz")
    write_batch([(a, {"Series": "X"})], log)
    monkeypatch.setattr(metadata, "write_xml", lambda *args: (_ for _ in ()).throw(MetadataError("disco lleno")))
    result = undo_last(log)
    assert result.restored == [] and result.skipped == [(a, "disco lleno")]
    monkeypatch.undo()
    assert read_info(a) == {"Series": "X"} and len(log.read_text(encoding="utf-8").splitlines()) == 1
    assert undo_last(log).restored == [a] and read_xml(a) is None


def test_library_index_keeps_up_with_the_new_size(tmp_path):
    log, library = tmp_path / "metadata.log", Library(tmp_path / "lib.db")
    a = make_zip(tmp_path / "a.cbz")
    stat = a.stat()
    import sqlite3
    with sqlite3.connect(tmp_path / "lib.db") as db:
        db.execute("INSERT INTO covers (path, mtime, size, hash) VALUES (?, ?, ?, ?)",
                   (str(a), stat.st_mtime, stat.st_size, b"\x00" * 32))
    write_batch([(a, {"Series": "X"})], log, library)
    with sqlite3.connect(tmp_path / "lib.db") as db:
        assert db.execute("SELECT mtime, size FROM covers WHERE path = ?", (str(a),)).fetchone() == \
            (a.stat().st_mtime, a.stat().st_size)
    undo_last(log, library)
    with sqlite3.connect(tmp_path / "lib.db") as db:
        assert db.execute("SELECT size FROM covers WHERE path = ?", (str(a),)).fetchone() == (a.stat().st_size,)


@needs_rar
def test_batch_and_undo_work_on_rar4_and_rar5(tmp_path):
    log = tmp_path / "metadata.log"
    comics = []
    for flavour in ("rar4", "rar5"):
        (tmp_path / flavour).mkdir()
        comics.append(rar_fixture(tmp_path / flavour, flavour))
    result = write_batch([(c, {"Series": "Serie RAR", "Number": "3"}) for c in comics], log)
    assert result.written == comics and all(read_info(c) == {"Series": "Serie RAR", "Number": "3"} for c in comics)
    assert len(undo_last(log).restored) == 2 and all(read_xml(c) is None for c in comics)
