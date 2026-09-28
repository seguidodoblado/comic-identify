import json
import sqlite3
import zipfile
from contextlib import closing

import pytest

from comic_identify import backup
from comic_identify.backup import (
    AUTO,
    MANUAL,
    BackupError,
    create,
    list_backups,
    prune,
    restore,
    unchanged_since_last,
)
from comic_identify.settings import Settings


def _db(path, rows):
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
        db.execute("DELETE FROM t")
        db.executemany("INSERT INTO t VALUES (?)", [(row,) for row in rows])
        db.commit()


def _rows(path):
    with closing(sqlite3.connect(path)) as db:
        return [row[0] for row in db.execute("SELECT v FROM t ORDER BY v")]


@pytest.fixture
def data(tmp_path):
    folder = tmp_path / "datos"
    folder.mkdir()
    sources = {"config.json": folder / "config.json", "library.db": folder / "library.db",
               "renames.log": folder / "renames.log", "gcstar.log": folder / "gcstar.log"}
    sources["config.json"].write_text('{"api_key": "secreta"}')
    _db(sources["library.db"], ["a", "b"])
    sources["renames.log"].write_text("uno\n")
    return sources, tmp_path / "copias"


def test_create_makes_a_verified_zip_with_a_manifest_and_skips_missing_files(data):
    sources, dest = data
    archive = create(dest, MANUAL, sources, "1.2.3")
    assert archive.parent == dest and archive.name.endswith("-manual.zip")
    manifest = backup.read_manifest(archive)
    assert set(manifest["files"]) == {"config.json", "library.db", "renames.log"}   # gcstar.log no existe
    assert manifest["app_version"] == "1.2.3" and manifest["kind"] == MANUAL
    assert not list(dest.glob("*.part")) and not list(dest.glob(".copia-*"))       # sin restos temporales
    assert archive.stat().st_mode & 0o777 == 0o600                                   # lleva la clave de ComicVine


def test_create_with_nothing_to_copy_fails_cleanly(tmp_path):
    with pytest.raises(BackupError):
        create(tmp_path / "copias", MANUAL, {"library.db": tmp_path / "no-existe.db"})


def test_the_database_copy_is_a_real_readable_database(data, tmp_path):
    sources, dest = data
    archive = create(dest, MANUAL, sources)
    with zipfile.ZipFile(archive) as zipped:
        zipped.extract("library.db", tmp_path / "fuera")
    assert _rows(tmp_path / "fuera" / "library.db") == ["a", "b"]


def test_two_backups_in_the_same_second_do_not_overwrite_each_other(data):
    sources, dest = data
    first, second = create(dest, MANUAL, sources), create(dest, MANUAL, sources)
    assert first != second and first.exists() and second.exists()


def test_list_backups_newest_first_ignoring_what_is_not_a_backup(data):
    sources, dest = data
    old, new = create(dest, AUTO, sources), create(dest, MANUAL, sources)
    (dest / "comic-identify-basura.zip").write_text("no es un zip")
    (dest / "otra-cosa.zip").write_bytes(b"")
    found = list_backups(dest)
    assert [info.path for info in found] == [new, old]
    assert found[0].kind == MANUAL and "library.db" in found[0].names and found[0].size > 0


def test_unchanged_since_last_detects_any_change_and_new_or_missing_files(data):
    sources, dest = data
    assert not unchanged_since_last(dest, sources)                  # aún no hay copias
    create(dest, AUTO, sources)
    assert unchanged_since_last(dest, sources)
    sources["renames.log"].write_text("uno\ndos\n")
    assert not unchanged_since_last(dest, sources)                  # cambió un archivo
    create(dest, AUTO, sources)
    assert unchanged_since_last(dest, sources)
    sources["gcstar.log"].write_text("nuevo")
    assert not unchanged_since_last(dest, sources)                  # apareció un archivo que la copia no tiene


def test_prune_only_removes_old_automatic_backups(data):
    sources, dest = data
    manual = create(dest, MANUAL, sources)
    autos = [create(dest, AUTO, sources) for _ in range(4)]
    assert set(prune(dest, keep=2)) == set(autos[:2])             # las 2 más antiguas
    remaining = {info.path for info in list_backups(dest)}
    assert remaining == {manual, *autos[2:]}                       # la manual + las 2 automáticas más nuevas
    prune(dest, keep=0)                                            # keep < 1 se trata como 1: nunca vacía todo
    assert {info.path for info in list_backups(dest)} == {manual, autos[3]}


def test_restore_brings_data_back_and_keeps_a_safety_copy_of_the_current_state(data):
    sources, dest = data
    archive = create(dest, MANUAL, sources)
    _db(sources["library.db"], ["cambiado"])
    sources["config.json"].write_text('{"api_key": "otra"}')
    result = restore(archive, sources)
    assert sorted(result.restored) == ["config.json", "library.db", "renames.log"]
    assert _rows(sources["library.db"]) == ["a", "b"]
    assert sources["config.json"].read_text() == '{"api_key": "secreta"}'
    assert result.safety is not None and result.safety.name.endswith("-restaurar.zip")
    with zipfile.ZipFile(result.safety) as zipped:                    # el estado de antes de restaurar se guardó
        assert b"otra" in zipped.read("config.json")
    assert not list(sources["library.db"].parent.glob(".*.restaurando"))


def test_restore_of_a_corrupt_backup_touches_nothing(data):
    sources, dest = data
    archive = create(dest, MANUAL, sources)
    _db(sources["library.db"], ["actual"])
    corrupt = dest / "comic-identify-2000-01-01_00-00-00-manual.zip"
    with zipfile.ZipFile(archive) as zipped, zipfile.ZipFile(corrupt, "w") as out:
        for name in zipped.namelist():
            out.writestr(name, b"MANIPULADO" if name == "renames.log" else zipped.read(name))
    before = {name: path.read_bytes() for name, path in sources.items() if path.exists()}
    with pytest.raises(BackupError, match="SHA-256"):
        restore(corrupt, sources)
    assert {name: path.read_bytes() for name, path in sources.items() if path.exists()} == before
    assert not list(sources["library.db"].parent.glob(".*.restaurando"))
    assert len(list(dest.glob("*-restaurar.zip"))) == 0              # ni siquiera llegó a guardar la copia de seguridad


def test_restore_ignores_unknown_names_in_the_zip_and_never_uses_them_as_paths(data, tmp_path):
    sources, dest = data
    archive = create(dest, MANUAL, sources)
    sneaky = dest / "comic-identify-2001-01-01_00-00-00-manual.zip"
    manifest = backup.read_manifest(archive)
    manifest["files"]["../../fuera.txt"] = {"sha256": "x"}
    with zipfile.ZipFile(archive) as zipped, zipfile.ZipFile(sneaky, "w") as out:
        for name in zipped.namelist():
            if name != backup.MANIFEST:
                out.writestr(name, zipped.read(name))
        out.writestr("../../fuera.txt", "dentro")
        out.writestr(backup.MANIFEST, json.dumps(manifest))
    result = restore(sneaky, sources)
    assert "../../fuera.txt" not in result.restored
    assert not (tmp_path / "fuera.txt").exists() and not (tmp_path.parent / "fuera.txt").exists()


def test_restore_into_a_fresh_machine_without_current_data_makes_no_safety_copy(data, tmp_path):
    sources, dest = data
    archive = create(dest, MANUAL, sources)
    fresh = {name: tmp_path / "nuevo" / path.name for name, path in sources.items()}
    result = restore(archive, fresh)
    assert result.safety is None and _rows(fresh["library.db"]) == ["a", "b"]


def test_restore_removes_leftover_journal_files_next_to_restored_databases(data):
    sources, dest = data
    archive = create(dest, MANUAL, sources)
    leftover = sources["library.db"].with_name("library.db-journal")
    leftover.write_bytes(b"basura")
    restore(archive, sources)
    assert not leftover.exists()


def test_not_a_backup_is_refused(tmp_path):
    bad = tmp_path / "comic-identify-x.zip"
    bad.write_text("no es un zip")
    with pytest.raises(BackupError):
        restore(bad, {"config.json": tmp_path / "c.json"})


def test_settings_keep_the_backup_options_and_fall_back_when_invalid(tmp_path):
    path = tmp_path / "config.json"
    Settings(backup_dir="/copias", backup_keep=4).save(path)
    loaded = Settings.load(path)
    assert loaded.backup_dir == "/copias" and loaded.backup_keep == 4
    path.write_text('{"backup_keep": 0}')
    assert Settings.load(path).backup_keep == 10
    path.write_text('{"backup_keep": "mucho"}')
    assert Settings.load(path).backup_keep == 10
