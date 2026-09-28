import sqlite3

import pytest

from comic_identify import universomarvel as um
from comic_identify.identify import Candidate, search_marvel
from comic_identify.universomarvel import (
    Entry,
    Fetcher,
    UniversoMarvelError,
    UniversoMarvelIndex,
    build_index,
    parse_index,
)

FORUM = """<HTML><body><CENTER>
<H2>Series Regulares y Limitadas</H2>
<form name="jump"><select name="menu">
<option value="aphff_v1.html">Alpha Flight vol.1</option>
<option value="aphff_v1.html">Marvel Two-In-One: Alpha Flight &amp; La Masa vol.1</option>
<option value="spf_v1.html">Spiderman vol.1</option>
<option value="spf_v1.html">Spiderman vol.1</option>
<option value="">Elige una serie</option>
<option value="leeme.txt">No es una página</option>
<option value="bustarwarsf_v1.html">\xa1Bienvenido al universo de Star Wars! vol.1</option>
</select></form>
<H2>Especiales</H2>
<select><option value="esp/alertaf.html">\xa1Alerta!</option>
<option VALUE='conanf_v1.html'>Conan\n   vol.1</option></select>
</body></HTML>""".encode("iso-8859-1")
VERTICE = b"""<html><body><h2>Formato Bolsillo</h2><select>
<option value="2piskidv_v1.html">2 Pistolas Kid vol.1</option></select></body></html>"""


def test_parse_index_reads_titles_sections_and_skips_what_is_not_a_series_page():
    entries = parse_index(FORUM, "Forum/Planeta")
    assert [(e.section, e.title, e.page) for e in entries] == [
        ("Series Regulares y Limitadas", "Alpha Flight vol.1", "aphff_v1.html"),
        ("Series Regulares y Limitadas", "Marvel Two-In-One: Alpha Flight & La Masa vol.1", "aphff_v1.html"),
        ("Series Regulares y Limitadas", "Spiderman vol.1", "spf_v1.html"),      # el duplicado exacto solo una vez
        ("Series Regulares y Limitadas", "\xa1Bienvenido al universo de Star Wars! vol.1", "bustarwarsf_v1.html"),
        ("Especiales", "\xa1Alerta!", "esp/alertaf.html"),
        ("Especiales", "Conan vol.1", "conanf_v1.html"),                          # espacios y saltos de línea colapsados
    ]
    assert all(e.publisher == "Forum/Planeta" for e in entries)


def test_entry_url_and_single_issue_detection():
    assert Entry("P", "S", "T", "aphff_v1.html").url == "https://fichas.universomarvel.com/aphff_v1.html"
    assert Entry("P", "S", "T", "esp/alertap.html").url == "https://fichas.universomarvel.com/esp/alertap.html"
    assert Entry("P", "S", "T", "esp/alertap.html").is_single_issue
    assert not Entry("P", "S", "T", "aphff_v1.html").is_single_issue


def test_decode_uses_the_declared_charset_or_falls_back_to_latin1():
    assert um.decode("<p>Cañón</p>".encode("iso-8859-1")) == "<p>Cañón</p>"
    assert "Cañón" in um.decode('<meta charset="utf-8"><p>Cañón</p>'.encode())
    assert "Cañón" in um.decode('<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">'
                                "<p>Cañón</p>".encode("iso-8859-1"))
    assert um.decode(b'<meta charset="inventado-9"><p>ok</p>')   # una codificación desconocida no rompe nada


@pytest.fixture
def index(tmp_path):
    pages = {"forum.html": FORUM, "vertice.html": VERTICE}
    calls = []

    def fetch(url):
        calls.append(url)
        return pages[url.rsplit("/", 1)[1]]
    target = tmp_path / "um.db"
    progress = []
    total = build_index(target, {"Forum/Planeta": "forum.html", "Vértice": "vertice.html"}, fetch, progress.append)
    assert total == 7 and len(calls) == 2 and len(progress) == 2
    return UniversoMarvelIndex(target)


def test_build_index_creates_a_ready_index_with_counts_per_publisher(index):
    assert index.is_ready()
    assert index.counts() == {"Forum/Planeta": 6, "Vértice": 1}


def test_search_ignores_accents_case_and_spacing_and_ranks_prefix_matches_first(index):
    assert [e.title for e in index.search("alpha flight")] == [
        "Alpha Flight vol.1", "Marvel Two-In-One: Alpha Flight & La Masa vol.1"]
    assert [e.title for e in index.search("SPIDER MAN")] == ["Spiderman vol.1"]     # «spider man» ~ «Spiderman»
    assert [e.title for e in index.search("alerta")] == ["\xa1Alerta!"]             # sin signos ni tildes
    assert index.search("2 pistolas")[0].publisher == "Vértice"
    assert index.search("") == [] and index.search("   ") == [] and index.search("inexistente") == []


def test_search_can_be_narrowed_by_publisher_and_never_treats_input_as_sql_or_wildcards(index):
    assert index.search("vol", publisher="vertice")[0].title == "2 Pistolas Kid vol.1"
    assert index.search("vol", publisher="panini") == []
    assert index.search("100%") == [] and index.search("_") == [] and index.search("'; DROP TABLE series;--") == []
    assert index.counts()   # la tabla sigue ahí


def test_a_failed_download_or_an_empty_page_keeps_the_previous_index(tmp_path, index):
    before = index.path.read_bytes()
    with pytest.raises(UniversoMarvelError):
        build_index(index.path, {"Forum/Planeta": "forum.html"}, lambda url: b"<html>cambiado</html>")
    def broken(url):
        raise UniversoMarvelError("sin red")
    with pytest.raises(UniversoMarvelError):
        build_index(index.path, {"Forum/Planeta": "forum.html"}, broken)
    assert index.path.read_bytes() == before and not index.path.with_suffix(".tmp").exists()


def test_a_missing_or_foreign_database_is_not_ready(tmp_path):
    assert not UniversoMarvelIndex(tmp_path / "no-existe.db").is_ready()
    other = tmp_path / "otra.db"
    sqlite3.connect(other).close()
    assert not UniversoMarvelIndex(other).is_ready()
    junk = tmp_path / "basura.db"
    junk.write_bytes(b"no soy sqlite" * 50)
    assert not UniversoMarvelIndex(junk).is_ready()


def test_fetcher_only_talks_to_the_universo_marvel_server_and_never_reaches_the_network_otherwise():
    with pytest.raises(UniversoMarvelError, match="Solo se consulta"):
        Fetcher().get("https://example.com/forum.html")
    with pytest.raises(UniversoMarvelError, match="Solo se consulta"):
        Fetcher().get("https://fichas.universomarvel.com.evil.example/x.html")


def test_fetcher_waits_between_requests_and_identifies_itself(monkeypatch):
    sent, slept = [], []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return b"ok"
    monkeypatch.setattr(um.urllib.request, "urlopen", lambda request, timeout: sent.append(request) or Response())
    monkeypatch.setattr(um.time, "sleep", slept.append)
    fetcher = Fetcher(min_interval=100)
    assert fetcher.get("https://fichas.universomarvel.com/forum.html") == b"ok"
    fetcher.get("https://fichas.universomarvel.com/panini.html")
    assert len(slept) == 1 and 0 < slept[0] <= 100                        # la segunda petición esperó
    assert sent[0].get_header("User-agent").startswith("comic-identify/")


def test_search_marvel_gives_candidates_that_open_the_series_page(index):
    found = search_marvel(index, "alpha flight")
    assert found[0].source == "Universo Marvel" and found[0].title == "Alpha Flight vol.1"
    assert found[0].url == "https://fichas.universomarvel.com/aphff_v1.html"
    assert found[0].subtitle == "Forum/Planeta · Series Regulares y Limitadas"
    assert (found[0].publisher, found[0].brand) == ("Planeta DeAgostini", "Forum")   # editorial y sello, distintos
    assert found[0].series == "Alpha Flight" and found[0].extra["Volume"] == ""        # el volumen 1 no se escribe
    assert found[0].extra["index_publisher"] == "Forum/Planeta" and found[0].rank[0] == 2   # como GCD: por título
    assert Candidate("x", "ComicVine").rank[0] == 3 > found[0].rank[0]


def test_split_volume_and_ficha_title():
    assert um.split_volume("Spiderman vol.2") == ("Spiderman", "2")
    assert um.split_volume("Spiderman vol.1") == ("Spiderman", "")                # solo importa si hay reinicio
    assert um.split_volume("Capit\xe1n Am\xe9rica Vol. 3") == ("Capit\xe1n Am\xe9rica", "3")
    assert um.split_volume("Dan Defensor vol.1 (2\xaa Edici\xf3n)") == ("Dan Defensor vol.1 (2\xaa Edici\xf3n)", "")
    assert um.split_volume("\xa1Alerta!") == ("\xa1Alerta!", "")
    assert um.split_ficha_title("Alpha Flight vol.1 n\xba 45") == ("Alpha Flight vol.1", "45")
    assert um.split_ficha_title("Spiderman vol.2 n\xba 12.5") == ("Spiderman vol.2", "12.5")
    assert um.split_ficha_title("\xa1Alerta!") == ("\xa1Alerta!", "")


def test_series_and_issue_candidates_are_told_apart_so_selecting_an_issue_never_reloads_it(index):
    from comic_identify.identify import marvel_issue_candidate
    from comic_identify.umficha import Ficha, SeriesIssue
    series = search_marvel(index, "alerta")[0]
    assert series.extra["level"] == "series" and series.extra["page"] == "esp/alertaf.html"
    issue = marvel_issue_candidate(Entry("Forum/Planeta", "Especiales", "\xa1Alerta!", "esp/alertaf.html"),
                                   SeriesIssue("g", "", "esp/alertaf.html"), Ficha(title="\xa1Alerta!"))
    assert issue.extra["level"] == "issue" and issue.number == ""     # un especial suelto: mismo aspecto, otro nivel


def test_ficha_page_recognises_only_spanish_issue_pages_of_the_site():
    assert um.ficha_page("https://fichas.universomarvel.com/esp/amalgambwagshif11.html") == "esp/amalgambwagshif11.html"
    for url in ("https://fichas.universomarvel.com/amalgamf_v1.html", "https://fichas.universomarvel.com/usa/aphf1001.html",
                "https://fichas.universomarvel.com/esp/", "https://example.com/esp/a.html", "", None):
        assert um.ficha_page(url) == ""


def test_series_listing_its_fichas_by_title_offers_them_as_candidates():
    from comic_identify.identify import alternative_candidate
    from comic_identify.umficha import SeriesIssue
    entry = Entry("Forum/Planeta", "Series Regulares y Limitadas", "Amalgam vol.1", "amalgamf_v1.html")
    candidate = alternative_candidate(entry, SeriesIssue("AMALGAM VOL.1 - FORUM", "JLX", "esp/jlx1.html"))
    assert (candidate.title, candidate.extra["level"], candidate.extra["page"]) == (
        "Amalgam vol.1 \xb7 JLX", "series", "esp/jlx1.html")     # una ficha suelta: al elegirla se consulta sola


def test_ficha_reached_by_browsing_takes_its_publisher_from_the_ficha_itself():
    from comic_identify.identify import marvel_issue_candidate, page_candidate
    from comic_identify.umficha import Ficha, SeriesIssue
    stub = page_candidate("AMALGAM", "esp/amalgambwagshif11.html")
    entry = Entry(stub.extra["index_publisher"], "", stub.title, stub.extra["page"])
    candidate = marvel_issue_candidate(entry, SeriesIssue("", "", entry.page), Ficha(title="Amalgam vol.1 n\xba 1", publisher="Forum"))
    assert (candidate.publisher, candidate.brand, candidate.extra["index_publisher"]) == ("Planeta DeAgostini", "Forum", "Forum/Planeta")
