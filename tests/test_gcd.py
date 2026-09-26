import sqlite3

import pytest
from conftest import jpeg, make_cover

from comic_identify import identify as pipeline
from comic_identify.barcode import Barcode
from comic_identify.gcd import GcdIndex, build_index


def test_build_keeps_only_spanish_and_not_deleted(dump, tmp_path):
    target = tmp_path / "gcd_es.db"
    assert build_index(dump, target) == (3, 5)   # series 10-12; números 100-104 (sin borrados)
    assert GcdIndex(target).counts() == (3, 5)
    assert not target.with_suffix(".tmp").exists()


def test_brand_is_imported_and_shown(index):
    hit = index.search("spiderman", "12")[0]
    assert set(hit.brand.split(",")) == {"Forum; Marvel Comics", "Panini Comics"}   # sin la marca borrada
    assert index.by_barcode("977060120000000012")[0].brand == hit.brand
    assert index.search("cuatro fantasticos", "7")[0].brand == "Panini Comics"
    assert index.search("spiderman", "100")[0].brand == ""


def test_old_schema_index_is_not_ready(index, tmp_path):
    assert index.is_ready()
    old = tmp_path / "old.db"
    sqlite3.connect(old).execute("CREATE TABLE issues (id)").connection.commit()   # user_version = 0
    assert not GcdIndex(old).is_ready() and not GcdIndex(tmp_path / "missing.db").is_ready()
    (tmp_path / "junk.db").write_bytes(b"esto no es sqlite" * 100)
    assert not GcdIndex(tmp_path / "junk.db").is_ready()


def test_build_rejects_other_databases(tmp_path):
    other = tmp_path / "other.db"
    sqlite3.connect(other).execute("CREATE TABLE x (a)").connection.commit()
    target = tmp_path / "out.db"
    with pytest.raises(ValueError, match="GCD"):
        build_index(other, target)
    assert not target.exists() and not target.with_suffix(".tmp").exists()


def test_search_ignores_accents_and_finds_issue(index):
    hits = index.search("cuatro fantasticos", "7")
    assert [(h.series, h.number, h.issue_id) for h in hits] == [("Los Cuatro Fantásticos", "7", 103)]
    assert hits[0].url == "https://www.comics.org/issue/103/"


def test_search_bridges_spiderman_spelling_and_truncated_queries(index):
    for text in ("spider man", "spider-ma", "spiderman"):
        assert {h.issue_id for h in index.search(text, "12")} >= {100, 104}, text


def test_search_puts_spain_first_and_skips_variants(index):
    hits = index.search("spiderman", "12")
    assert hits[0].country == "es" and hits[0].issue_id == 100
    assert 102 not in {h.issue_id for h in hits}


def test_search_without_number_lists_series_and_unknown_is_empty(index):
    assert {h.series for h in index.search("spiderman")} == {"Spiderman"}
    assert all(h.url.startswith("https://www.comics.org/series/") and h.url.endswith("/covers/")
               for h in index.search("spiderman"))   # galería de portadas de la serie
    assert index.search("xyzzy", "1") == [] and index.search("!!!") == []
    assert index.search("spiderman", "9999") == []


def test_by_barcode_matches_digits_only(index):
    assert [h.issue_id for h in index.by_barcode("9770601200 00000012")] == [100]
    assert index.by_barcode("123") == [] and index.by_barcode("") == []


def _photo(tmp_path, monkeypatch, barcode=None):
    monkeypatch.setattr(pipeline, "read_barcode", lambda _: barcode)
    photo = tmp_path / "u.jpg"
    photo.write_bytes(jpeg(make_cover(1)))
    return photo


def test_identify_with_gcd_only_needs_no_comicvine_key(index, tmp_path, monkeypatch):
    outcome = pipeline.identify(_photo(tmp_path, monkeypatch), None, None, "spiderman", "12", gcd=index)
    assert outcome.notes == []
    assert outcome.candidates[0].source == "GCD" and outcome.candidates[0].title == "Spiderman #12"
    assert outcome.candidates[0].subtitle.startswith("Panini España · Sello: ")
    assert outcome.candidates[0].subtitle.endswith(" · Sombras · 2006-12")
    assert "Forum; Marvel Comics" in outcome.candidates[0].subtitle


def test_identify_ranks_exact_barcode_first(index, tmp_path, monkeypatch):
    barcode = Barcode("9770601200000", "00012")
    photo = _photo(tmp_path, monkeypatch, barcode)
    outcome = pipeline.identify(photo, None, None, "cuatro fantasticos", gcd=index)
    assert outcome.candidates[0].exact and outcome.candidates[0].title == "Spiderman #12"
    assert outcome.issue_number == "12"   # sale del complemento del código de barras


def test_identify_without_title_asks_for_it(index, tmp_path, monkeypatch):
    outcome = pipeline.identify(_photo(tmp_path, monkeypatch), None, None, gcd=index)
    assert outcome.candidates == [] and "Escribe el título" in outcome.notes[0]


def test_identify_without_any_source_explains_what_to_do(tmp_path, monkeypatch):
    outcome = pipeline.identify(_photo(tmp_path, monkeypatch), None, None, "spiderman")
    assert "GCD" in outcome.notes[0] and "ComicVine" in outcome.notes[0]


def test_live_search_returns_gcd_candidates(index):
    found = pipeline.search_gcd(index, "spider", "12")
    assert found and all(c.source == "GCD" and c.url for c in found)
    assert pipeline.search_gcd(index, "xyzzy") == []


def test_partial_dates_drop_the_zero_parts():
    hit = pipeline.GcdHit("Serie", "Editorial", "1969", "1", date="1969-00-00")
    assert pipeline._gcd_candidate(hit).subtitle == "Editorial · 1969"
    assert pipeline._gcd_candidate(pipeline.GcdHit("S", "E", "", "1", date="2003-04-00")).subtitle == "E · 2003-04"


def test_year_filter_uses_the_issue_date_or_the_series_range(index):
    # Con número, el año es el del ejemplar (fecha 1981 en la mexicana, 2006 en la de Panini).
    assert {h.issue_id for h in index.search("spiderman", "12", year="1981")} == {104}
    assert {h.issue_id for h in index.search("spiderman", "12", year="2006")} == {100}
    assert index.search("spiderman", "12", year="1985") == []       # la serie existía, pero el nº 12 es de 1981
    assert index.search("spiderman", "12", year="1950") == []       # ninguna serie existía
    assert index.search("spiderman", "12", year="año raro") != []   # un año no numérico se ignora
    # Sin número, basta con que la serie estuviera publicándose ese año.
    assert {h.series_id for h in index.search("spiderman", year="1985")} == {12}
    assert {h.series_id for h in index.search("spiderman", year="2010")} == {10}       # la de Panini sigue en curso


def test_publisher_filter_matches_publisher_or_brand_ignoring_accents(index):
    assert {h.issue_id for h in index.search("spiderman", "12", publisher="panini")} == {100}
    assert {h.issue_id for h in index.search("spiderman", "12", publisher="NOVEDADES")} == {104}
    assert {h.issue_id for h in index.search("spiderman", "12", publisher="forum")} == {100}   # es un sello de la 100
    assert index.search("spiderman", "12", publisher="inexistente") == []
    assert {h.series_id for h in index.search("spiderman", publisher="forum")} == {10}         # sello, a nivel de serie
    assert {h.series_id for h in index.search("cuatro fantasticos", publisher="Panini España")} == {11}


def test_filters_combine_and_live_search_passes_them(index):
    assert {h.issue_id for h in index.search("spiderman", "12", publisher="panini", year="2006")} == {100}
    assert index.search("spiderman", "12", publisher="panini", year="1985") == []
    found = pipeline.search_gcd(index, "spiderman", "12", "novedades", "1981")
    assert [c.url for c in found] == ["https://www.comics.org/issue/104/"]


def test_filters_never_fall_back_to_any_word_of_the_title(index):
    assert {h.issue_id for h in index.search("cuatro spiderman", "7")} == {103}                  # sin filtros: cualquier palabra
    assert index.search("cuatro spiderman", "7", publisher="panini") == []                        # con filtros: nada, no ruido
    assert index.search("cuatro spiderman", "7", year="2007") == []
