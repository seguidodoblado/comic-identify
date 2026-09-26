import sqlite3
import time
import zipfile
from pathlib import Path

from conftest import jpeg, make_cover

from comic_identify.library import Library, orphans


def _cbz(path: Path, seed: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("01.jpg", jpeg(make_cover(seed)))
    return path


def _rows(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as db:
        return {r[0] for r in db.execute("SELECT path FROM covers")}


def test_orphans_is_linear_not_quadratic():
    known = [f"/comics/{i}.cbz" for i in range(200_000)]
    seen = set(known[:-10])
    start = time.time()
    gone = orphans(known, seen, [Path("/comics")], [Path("/comics")])
    assert len(gone) == 10
    assert time.time() - start < 2   # el bucle anterior habría tardado horas con este tamaño


def test_orphans_rules():
    known = ["/a/1.cbz", "/a/sub/2.cbz", "/b/3.cbz", "/c/4.cbz", "/ab/5.cbz"]
    gone = orphans(known, seen={"/a/1.cbz"}, available=[Path("/a")], configured=[Path("/a"), Path("/b")])
    # /a/sub/2 falta en una carpeta accesible -> se olvida; /b está configurada pero sin acceso -> se conserva;
    # /c y /ab no pertenecen a ninguna carpeta configurada (y /ab no es /a) -> huérfanas
    assert set(gone) == {"/a/sub/2.cbz", "/c/4.cbz", "/ab/5.cbz"}


def test_missing_or_empty_folder_keeps_its_index(tmp_path):
    disk = tmp_path / "disco"
    _cbz(disk / "x.cbz", 1)
    _cbz(tmp_path / "local" / "y.cbz", 2)
    library = Library(tmp_path / "lib.db")
    assert library.index([disk, tmp_path / "local"]).indexed == 2

    (disk / "x.cbz").rename(tmp_path / "x_movido.cbz")     # el disco «desaparece»: carpeta vacía
    (tmp_path / "x_movido.cbz").unlink()
    stats = library.index([disk, tmp_path / "local"])
    assert stats.removed == 0 and stats.unavailable == [str(disk)]
    assert library.count() == 2

    disk.rmdir()                                            # y ahora ni siquiera existe
    assert library.index([disk, tmp_path / "local"]).removed == 0 and library.count() == 2


def test_deleted_file_in_available_folder_is_forgotten(tmp_path):
    _cbz(tmp_path / "a.cbz", 1)
    _cbz(tmp_path / "b.cbz", 2)
    library = Library(tmp_path / "lib.db")
    library.index([tmp_path])
    (tmp_path / "b.cbz").unlink()
    stats = library.index([tmp_path])
    assert stats.removed == 1 and stats.unavailable == []
    assert _rows(tmp_path / "lib.db") == {str(tmp_path / "a.cbz")}


def test_folder_no_longer_configured_is_pruned_on_next_index(tmp_path):
    _cbz(tmp_path / "uno" / "a.cbz", 1)
    _cbz(tmp_path / "dos" / "b.cbz", 2)
    library = Library(tmp_path / "lib.db")
    library.index([tmp_path / "uno", tmp_path / "dos"])
    assert library.index([tmp_path / "uno"]).removed == 1     # «dos» ya no está configurada
    assert _rows(tmp_path / "lib.db") == {str(tmp_path / "uno" / "a.cbz")}


def test_forget_folder_removes_only_that_folder(tmp_path):
    for name, seed in (("comics", 1), ("comics2", 2), ("otro", 3)):
        _cbz(tmp_path / name / "c.cbz", seed)
    library = Library(tmp_path / "lib.db")
    library.index([tmp_path / "comics", tmp_path / "comics2", tmp_path / "otro"])
    assert library.forget_folder(tmp_path / "comics") == 1     # no arrastra a «comics2»
    assert _rows(tmp_path / "lib.db") == {str(tmp_path / "comics2" / "c.cbz"), str(tmp_path / "otro" / "c.cbz")}
    assert library.forget_folder(tmp_path / "no_existe") == 0


def test_one_unreadable_file_does_not_abort_the_batch(tmp_path, monkeypatch):
    from PIL import Image

    from comic_identify import library as library_module
    for name, seed in (("a.cbz", 1), ("b.cbz", 2), ("c.cbz", 3)):
        _cbz(tmp_path / name, seed)
    real = library_module.read_cover

    def flaky(path):
        if path.name == "b.cbz":   # Pillow lanza esta excepción, que no es OSError ni ValueError
            raise Image.DecompressionBombError("Image size exceeds limit")
        return real(path)
    monkeypatch.setattr(library_module, "read_cover", flaky)

    stats = Library(tmp_path / "lib.db").index([tmp_path])

    assert (stats.indexed, stats.failed) == (2, 1)
    assert [(Path(f).name, reason) for f, reason in stats.failed_files] == [("b.cbz", "imagen enorme")]
    assert _rows(tmp_path / "lib.db") == {str(tmp_path / "a.cbz"), str(tmp_path / "c.cbz")}


def test_failure_reasons_tell_the_cases_apart(tmp_path):
    _cbz(tmp_path / "ok.cbz", 1)
    with zipfile.ZipFile(tmp_path / "vacio.cbz", "w") as archive:
        archive.writestr("notas.txt", "sin imágenes")
    with zipfile.ZipFile(tmp_path / "rota.cbz", "w") as archive:
        archive.writestr("01.jpg", b"esto no es una imagen")

    stats = Library(tmp_path / "lib.db").index([tmp_path])

    assert stats.indexed == 1
    reasons = {Path(f).name: reason for f, reason in stats.failed_files}
    assert reasons == {"vacio.cbz": "sin imágenes o archivo dañado", "rota.cbz": "imagen no válida"}


def _tag(path: Path, **info) -> None:
    from comic_identify.comicinfo import build_xml, write_xml
    write_xml(path, build_xml(None, info))


def test_index_records_the_comicinfo_summary_and_does_not_reread_unchanged_files(tmp_path):
    plain = _cbz(tmp_path / "plain.cbz", 1)
    tagged = _cbz(tmp_path / "tagged.cbz", 2)
    _tag(tagged, Series="Capitán Marvel", Volume="2", Number="5", Count="36", Tags="Otra, Categoría: Series")
    library = Library(tmp_path / "lib.db")
    stats = library.index([tmp_path])
    assert stats.indexed == 2 and stats.refreshed == 0
    rows = {Path(r[0]).name: r[1:] for r in library.series_rows()}
    assert rows["tagged.cbz"] == ("Capitán Marvel", "2", "5", 36, "Series", 1)
    assert rows["plain.cbz"] == ("", "", "", None, "", 0)
    again = library.index([tmp_path])
    assert again.unchanged == 2 and again.indexed == 0 and again.refreshed == 0
    assert plain.exists()


def test_a_legacy_index_is_extended_and_only_the_metadata_is_read(tmp_path):
    a = _cbz(tmp_path / "a.cbz", 1)
    _tag(a, Series="Vieja", Number="1")
    stat = a.stat()
    with sqlite3.connect(tmp_path / "lib.db") as db:      # índice de una versión anterior: sin columnas de metadatos
        db.execute("CREATE TABLE covers (path TEXT PRIMARY KEY, mtime REAL, size INTEGER, hash BLOB)")
        db.execute("INSERT INTO covers VALUES (?, ?, ?, ?)", (str(a), stat.st_mtime, stat.st_size, b"\x07" * 32))
    library = Library(tmp_path / "lib.db")                # abrirlo lo amplía
    assert library.series_rows()[0][1:] == ("", "", "", None, "", 0)      # aún sin leer: sin NULL que rompan al agrupar
    stats = library.index([tmp_path])
    assert stats.refreshed == 1 and stats.indexed == 0 and stats.unchanged == 0
    assert library.series_rows()[0][1:] == ("Vieja", "", "1", None, "", 1)
    with sqlite3.connect(tmp_path / "lib.db") as db:
        assert db.execute("SELECT hash FROM covers").fetchone() == (b"\x07" * 32,)      # la huella no se tocó
    assert library.index([tmp_path]).unchanged == 1


def test_files_with_unreadable_metadata_are_indexed_as_untagged(tmp_path):
    bad = tmp_path / "bad.cbz"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("01.jpg", jpeg(make_cover(3)))
        archive.writestr("ComicInfo.xml", b"<no es xml")
    library = Library(tmp_path / "lib.db")
    assert library.index([tmp_path]).indexed == 1
    assert library.series_rows()[0][1:] == ("", "", "", None, "", 0)
