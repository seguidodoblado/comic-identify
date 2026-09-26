import zipfile
from pathlib import Path

import pytest
from conftest import jpeg, make_cover

from comic_identify.gcd import SeriesInfo
from comic_identify.library import Library
from comic_identify.naming import (
    detect_number,
    number_width,
    pad_number,
    render,
    series_values,
    years_text,
)
from comic_identify.renamer import rename_series, undo_last


def _series(tmp_path: Path, names: list[str], folder: str = "serie") -> Path:
    root = tmp_path / folder
    root.mkdir()
    for seed, name in enumerate(names):
        with zipfile.ZipFile(root / name, "w") as archive:
            archive.writestr("01.jpg", jpeg(make_cover(seed)))
    return root


def _names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def test_detect_number_from_file_names():
    assert detect_number("Batman 06") == ("06", False)
    assert detect_number("Hawkeye - Kate Bishop 02") == ("02", False)
    assert detect_number("IJUSTICE GAU-Año 04 (03)") == ("04", False)           # lo de los paréntesis se ignora
    assert detect_number("Batman 2011 05") == ("05", False)                     # un año no es un número
    assert detect_number("Batman (2011)") == ("", False)                        # solo hay un año
    assert detect_number("11") == ("11", False)
    assert detect_number("Vol 2 Nº 05") == ("05", True)                         # dos candidatos: el último, dudoso
    assert detect_number("Especial sin número") == ("", False)
    assert detect_number("Titulo [Extra 3]") == ("3", False)                    # si solo hay dentro, se usa


def test_number_width_is_at_least_two_digits_and_grows_with_the_highest_number():
    assert number_width([]) == 2 and number_width([1, 2, 9]) == 2                # 01, 02… aunque la serie sea corta
    assert number_width(list(range(1, 27))) == 2 and number_width([5, 10]) == 2
    assert number_width([1, 99]) == 2 and number_width([1, 100]) == 3 and number_width([3, 301]) == 3
    assert [pad_number(n, number_width([1, 9])) for n in (1, 9)] == ["01", "09"]
    assert [pad_number(n, number_width([1, 26])) for n in (1, 26)] == ["01", "26"]
    assert [pad_number(n, number_width([1, 301])) for n in (1, 301)] == ["001", "301"]


def test_years_pad_and_series_values():
    assert (years_text(2000, 2002), years_text(2006, 2006), years_text(2011, None), years_text(None, 2000)) == \
        ("2000-2002", "2006", "2011-", "")
    assert pad_number(7, 2) == "07" and pad_number(7, 3) == "007" and pad_number(301, 2) == "301"
    info = SeriesInfo(1, "Capitán Marvel", "Planeta DeAgostini", "es", 2000, 2002, 26, "Forum; Marvel Comics")
    values = series_values(info)
    assert render("{nombre} {volumen} {bandera} [{contenido}] ({edicion}) - {sello}", values) == \
        "Capitán Marvel 🇪🇸 (2000-2002) - Forum"
    ongoing = series_values(SeriesInfo(2, "Los Vengadores", "Panini España", "es", 2011, None, 137))
    assert (ongoing.edicion, ongoing.sello) == ("2011-", "")
    assert series_values(SeriesInfo(3, "X", "Novaro", "mx", 1980, 1990, 5)).bandera == ""


def test_series_info_from_the_gcd_index(index):
    info = index.series_info(10)
    assert (info.name, info.publisher, info.country, info.year_began, info.year_ended, info.issue_count) == \
        ("Spiderman", "Panini España", "es", 2006, None, 189)
    assert series_values(info).sello == "Forum"                                # el sello más frecuente de sus números
    assert series_values(index.series_info(11)).sello == "Panini Comics"
    assert index.series_info(9999) is None


def test_library_rename_folder_updates_only_that_prefix(tmp_path):
    root = _series(tmp_path, ["a.cbz"], "comics")
    other = _series(tmp_path, ["b.cbz"], "comics2")
    library = Library(tmp_path / "lib.db")
    library.index([root, other])
    library.rename_folder(root, tmp_path / "nueva")
    import sqlite3
    with sqlite3.connect(tmp_path / "lib.db") as db:
        assert {r[0] for r in db.execute("SELECT path FROM covers")} == {str(tmp_path / "nueva" / "a.cbz"), str(other / "b.cbz")}


def test_rename_series_respects_gaps_renames_folder_updates_index_and_undoes_as_one_batch(tmp_path):
    folder = _series(tmp_path, ["Batman 1.cbz", "Batman 2.cbz", "Batman 4.cbz", "Batman 10.cbz"])
    library = Library(tmp_path / "lib.db")
    library.index([folder])
    log = tmp_path / "log" / "renames.log"
    moves = [(folder / "Batman 1.cbz", folder / "Batman 01.cbz"), (folder / "Batman 2.cbz", folder / "Batman 02.cbz"),
             (folder / "Batman 4.cbz", folder / "Batman 04.cbz"), (folder / "Batman 10.cbz", folder / "Batman 10.cbz")]

    new = rename_series(folder, "Batman 🇺🇸 [1940] - DC", moves, log, library)

    assert new == tmp_path / "Batman 🇺🇸 [1940] - DC" and not folder.exists()
    assert _names(new) == ["Batman 01.cbz", "Batman 02.cbz", "Batman 04.cbz", "Batman 10.cbz"]   # el hueco (3) se respeta
    import sqlite3
    with sqlite3.connect(tmp_path / "lib.db") as db:
        assert {r[0] for r in db.execute("SELECT path FROM covers")} == {str(new / n) for n in _names(new)}

    pairs = undo_last(log, library)                                          # un solo paso deshace carpeta y archivos
    assert len(pairs) == 4 and pairs[-1] == (new, folder)
    assert _names(folder) == ["Batman 1.cbz", "Batman 10.cbz", "Batman 2.cbz", "Batman 4.cbz"] and not new.exists()
    with sqlite3.connect(tmp_path / "lib.db") as db:
        assert {r[0] for r in db.execute("SELECT path FROM covers")} == {str(folder / n) for n in _names(folder)}
    with pytest.raises(LookupError):
        undo_last(log, library)


def test_rename_series_can_shift_names_within_the_batch(tmp_path):
    """Un nombre puede ser el destino de otro archivo del mismo lote (desplazar números) sin pisarse."""
    folder = _series(tmp_path, ["S 1.cbz", "S 2.cbz", "S 3.cbz"])
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    moves = [(folder / "S 1.cbz", folder / "S 2.cbz"), (folder / "S 2.cbz", folder / "S 3.cbz"),
             (folder / "S 3.cbz", folder / "S 4.cbz")]
    rename_series(folder, None, moves, tmp_path / "renames.log")
    after = {p.name: p.read_bytes() for p in folder.iterdir()}
    assert sorted(after) == ["S 2.cbz", "S 3.cbz", "S 4.cbz"]
    assert (after["S 2.cbz"], after["S 3.cbz"], after["S 4.cbz"]) == (before["S 1.cbz"], before["S 2.cbz"], before["S 3.cbz"])


def test_rename_series_validates_everything_before_touching_anything(tmp_path):
    folder = _series(tmp_path, ["A 1.cbz", "A 2.cbz", "Otro.cbz"])
    log = tmp_path / "renames.log"
    with pytest.raises(FileExistsError, match="mismo nombre"):                  # dos archivos → mismo destino
        rename_series(folder, None, [(folder / "A 1.cbz", folder / "X.cbz"), (folder / "A 2.cbz", folder / "X.cbz")], log)
    with pytest.raises(FileExistsError, match="Ya existe"):                     # destino ocupado por un archivo ajeno al lote
        rename_series(folder, None, [(folder / "A 1.cbz", folder / "Otro.cbz")], log)
    (tmp_path / "ocupada").mkdir()
    with pytest.raises(FileExistsError, match="carpeta"):                       # la carpeta destino ya existe
        rename_series(folder, "ocupada", [(folder / "A 1.cbz", folder / "B 1.cbz")], log)
    with pytest.raises(FileNotFoundError):
        rename_series(folder, None, [(folder / "no_existe.cbz", folder / "Z.cbz")], log)
    assert _names(folder) == ["A 1.cbz", "A 2.cbz", "Otro.cbz"] and not log.exists()   # no se tocó nada


def test_rename_series_rolls_back_the_files_if_the_folder_cannot_be_renamed(tmp_path, monkeypatch):
    import os

    from comic_identify import renamer
    folder = _series(tmp_path, ["A 1.cbz", "A 2.cbz"])
    real = os.rename

    def flaky(src, dst):
        if Path(src) == folder:
            raise PermissionError("sin permiso para renombrar la carpeta")
        return real(src, dst)
    monkeypatch.setattr(renamer.os, "rename", flaky)
    with pytest.raises(PermissionError):
        rename_series(folder, "nueva", [(folder / "A 1.cbz", folder / "A 01.cbz"), (folder / "A 2.cbz", folder / "A 02.cbz")],
                      tmp_path / "renames.log")
    assert _names(folder) == ["A 1.cbz", "A 2.cbz"]                              # los archivos volvieron a su nombre
    assert not (tmp_path / "renames.log").exists()
