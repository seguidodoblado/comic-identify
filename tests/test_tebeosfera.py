import gzip
import io
import sqlite3
import types
from contextlib import closing

import pytest
from PIL import Image
from test_tbficha import URL, page

from comic_identify import tebeosfera as tb
from comic_identify.identify import (
    search_tebeosfera,
    tebeosfera_alternative,
    tebeosfera_entry,
    tebeosfera_issue_candidate,
    tebeosfera_page_candidate,
)
from comic_identify.naming import suggest_values

BASE = tb.BASE
ROBOTS = f"User-agent: *\nDisallow: /adminpanel/$\nSitemap: {BASE}sitemap1.xml\nSitemap: {BASE}sitemap2.xml\nSitemap: {BASE}sitemap3.xml\n"


def sitemap(kind, *slugs):
    return "<urlset>" + "".join(f"<url><loc>{BASE}{kind}/{s}.html</loc></url>" for s in slugs) + "</urlset>"


PAGES = {
    "sitemap1.xml": sitemap("publicaciones", "universo_dc_1989_zinco", "daredevil_2019_panini", "spiderman_1983_forum_planeta-deagostini",
                            "batman_2019_ovni_press_-coleccion_80_aniversario-", "el_gran_libro_2020_norma", "sin_numeros_2020_norma"),
    "sitemap2.xml": sitemap("numeros", "universo_dc_1989_zinco_10", "universo_dc_1989_zinco_2", "universo_dc_1989_zinco_37",
                            "universo_dc_1989_zinco_variante_2", "daredevil_2019_panini_67", "daredevil_2019_panini_68",
                            "spiderman_1983_forum_planeta-deagostini_95", "el_gran_libro_2020_norma",
                            "batman_2019_ovni_press_-coleccion_80_aniversario-_7", "huerfano_2000_x_1"),
    "sitemap3.xml": sitemap("autores", "newell_mindy"),
}


def fetcher(log=None):
    def fetch(url):
        if log is not None:
            log.append(url)
        name = url.removeprefix(BASE)
        if name == "robots.txt":
            return ROBOTS.encode()
        if name in PAGES:
            return PAGES[name].encode()
        raise tb.TebeosferaError(f"sin red en la prueba: {url}")
    return fetch


@pytest.fixture
def index(tmp_path):
    target = tmp_path / "tebeosfera.db"
    tb.build_index(target, fetcher())
    return tb.TebeosferaIndex(target)


def test_build_index_reads_collections_and_their_numbers_from_the_sitemaps(tmp_path):
    log = []
    target = tmp_path / "t.db"
    assert tb.build_index(target, fetcher(log)) == 6
    assert log == [BASE + "robots.txt", BASE + "sitemap1.xml", BASE + "sitemap2.xml", BASE + "sitemap3.xml"]   # para al llegar a los autores
    index = tb.TebeosferaIndex(target)
    assert index.is_ready() and index.counts() == {"colecciones": 6, "números": 9}
    assert index.numbers_of("universo_dc_1989_zinco") == ["2", "10", "37", "variante_2"]   # numéricos primero, en orden
    assert index.numbers_of("sin_numeros_2020_norma") == []
    assert index.get_entry("el_gran_libro_2020_norma").single                             # un número único: es su propia ficha
    assert index.get_entry("universo_dc_1989_zinco") == tb.Entry("universo_dc_1989_zinco", "Universo DC (1989, Zinco)", "1989", "Zinco", False)


def test_build_index_keeps_the_old_index_when_the_web_fails_or_changes(tmp_path):
    target = tmp_path / "t.db"
    tb.build_index(target, fetcher())
    with pytest.raises(tb.TebeosferaError):
        tb.build_index(target, lambda url: b"" if url.endswith("robots.txt") else b"<urlset></urlset>")
    assert tb.TebeosferaIndex(target).counts()["colecciones"] == 6
    with pytest.raises(tb.TebeosferaError):
        tb.build_index(target, lambda url: (_ for _ in ()).throw(tb.TebeosferaError("caída")))
    assert tb.TebeosferaIndex(target).counts()["colecciones"] == 6


def test_search_ignores_accents_case_and_spaces_and_can_filter_by_publisher(index):
    assert [e.slug for e in index.search("universo dc")] == ["universo_dc_1989_zinco"]
    assert [e.slug for e in index.search("spider man")] == ["spiderman_1983_forum_planeta-deagostini"]   # «spider man» = «Spiderman»
    assert [e.slug for e in index.search("batman", publisher="ovni")] == ["batman_2019_ovni_press_-coleccion_80_aniversario-"]
    assert index.search("batman", publisher="panini") == [] and index.search("") == []
    assert {e.slug for e in index.search("norma")} == {"el_gran_libro_2020_norma", "sin_numeros_2020_norma"}


def test_a_real_title_read_from_a_ficha_replaces_the_one_from_the_address_and_is_searchable(index):
    index.set_real_title("universo_dc_1989_zinco", "Universo DC (1989, Zinco) -Ñoño-")
    assert index.search("universo")[0].title == "Universo DC (1989, Zinco) -Ñoño-"
    assert index.search("nono")[0].slug == "universo_dc_1989_zinco"                # sin tildes
    tb.build_index(index.path, fetcher())                                           # al rehacer el índice no se pierde
    assert index.search("universo")[0].title.endswith("-Ñoño-")


def test_find_issue_matches_numbers_ignoring_zeros_and_guesses_when_the_index_has_none(index):
    client = tb.TebeosferaClient(index, fetch=fetcher())
    entry = index.search("universo dc")[0]
    assert client.find_issue(entry, "10") == tb.Issue("10", "numeros/universo_dc_1989_zinco_10.html")
    assert client.find_issue(entry, "010").label == "10" and client.find_issue(entry, "variante_2").label == "variante_2"
    assert client.find_issue(entry, "11") is None and client.find_issue(entry, "") is None
    empty = index.get_entry("sin_numeros_2020_norma")        # sin números en el índice: se prueba «colección_número»
    assert client.find_issue(empty, "3").page == "numeros/sin_numeros_2020_norma_3.html"
    single = index.get_entry("el_gran_libro_2020_norma")
    assert client.find_issue(single, "cualquiera").page == "numeros/el_gran_libro_2020_norma.html"
    assert (single.page, entry.page) == ("numeros/el_gran_libro_2020_norma.html", "colecciones/universo_dc_1989_zinco.html")


def test_nearest_offers_the_numbers_closest_to_the_typed_one(index):
    client = tb.TebeosferaClient(index, fetch=fetcher())
    entry = index.search("universo dc")[0]
    assert [i.label for i in client.nearest(entry, "11", 2)] == ["10", "37"] or [i.label for i in client.nearest(entry, "11", 2)] == ["2", "10"]
    assert [i.label for i in client.nearest(entry, "11", 3)] == ["2", "10", "37"]
    assert [i.label for i in client.nearest(entry, "x", 10)] == ["2", "10", "37", "variante_2"]


def test_ficha_is_downloaded_once_and_kept_with_its_real_title(index):
    html = page().encode()
    calls = []

    def fetch_page(url):
        calls.append(url)
        return html
    client = tb.TebeosferaClient(index, fetch=fetch_page)
    first = client.ficha("numeros/daredevil_2019_panini_67.html")
    again = client.ficha("numeros/daredevil_2019_panini_67.html")
    assert first == again and calls == [BASE + "numeros/daredevil_2019_panini_67.html"]          # una sola petición
    assert index.get_entry("daredevil_2019_panini").title == "Daredevil (2019, Panini)"
    assert index.by_barcode("977-2938548-00800020") == ["numeros/daredevil_2019_panini_67.html"]
    with pytest.raises(tb.TebeosferaError):
        tb.TebeosferaClient(index, fetch=lambda url: b"<html>404</html>").ficha("numeros/no_existe.html")


def test_a_ficha_read_by_an_older_parser_is_read_again_from_the_saved_html(index):
    client = tb.TebeosferaClient(index, fetch=lambda url: page().encode())
    client.ficha("numeros/daredevil_2019_panini_67.html")
    with closing(sqlite3.connect(index.path)) as db, db:
        db.execute("UPDATE fichas SET parser_version = 0, data = '{}'")
    assert index.get_ficha("numeros/daredevil_2019_panini_67.html").number == "67"


def test_cover_is_shrunk_stored_and_downloaded_once(index):
    buffer = io.BytesIO()
    Image.new("RGB", (1200, 1800), (200, 30, 30)).save(buffer, "JPEG")
    calls = []

    def fetch(url):
        calls.append(url)
        return buffer.getvalue()
    client = tb.TebeosferaClient(index, fetch=fetch)
    url = BASE + "T3content/img/x.jpg"
    small = client.cover(url)
    assert max(Image.open(io.BytesIO(small)).size) <= tb.COVER_SIDE and client.cover(url) == small and len(calls) == 1
    with pytest.raises(tb.TebeosferaError):
        tb.TebeosferaClient(index, fetch=lambda u: b"no es una imagen").cover(BASE + "otra.jpg")


def test_fetcher_only_talks_to_tebeosfera_and_understands_gzip(monkeypatch):
    with pytest.raises(tb.TebeosferaError):
        tb.Fetcher().get("https://example.com/")

    class Response:
        def __init__(self, body, encoding):
            self._body, self.headers = body, {"Content-Encoding": encoding}

        def read(self, limit):
            return self._body[:limit]

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False
    seen = []
    monkeypatch.setattr(tb.urllib.request, "urlopen", lambda request, timeout: (seen.append(request), Response(
        gzip.compress(b"<urlset/>"), "gzip"))[1])
    assert tb.Fetcher(min_interval=0).get(BASE + "sitemap1.xml") == b"<urlset/>"
    assert seen[0].get_header("Accept-encoding") == "gzip" and "comic-identify" in seen[0].get_header("User-agent")
    monkeypatch.setattr(tb.urllib.request, "urlopen", lambda request, timeout: Response(b"not gzip", "gzip"))
    with pytest.raises(tb.TebeosferaError):
        tb.Fetcher(min_interval=0).get(BASE + "sitemap1.xml")


def test_fetcher_does_not_wait_before_the_first_request_on_a_freshly_booted_machine(monkeypatch):
    slept = []

    class Response:
        def __init__(self):
            self.headers = {}

        def read(self, limit):
            return b"ok"

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False
    # equipo recién arrancado: monotonic() vale menos que el intervalo y no debe provocar una espera
    monkeypatch.setattr(tb, "time", types.SimpleNamespace(monotonic=lambda: 5.0, sleep=slept.append))
    monkeypatch.setattr(tb.urllib.request, "urlopen", lambda request, timeout: Response())
    fetcher = tb.Fetcher(min_interval=100)
    fetcher.get(BASE + "sitemap1.xml")
    assert slept == []
    fetcher.get(BASE + "sitemap2.xml")
    assert slept == [100]


def test_ficha_page_only_accepts_numbers_of_the_site():
    assert tb.ficha_page(BASE + "numeros/x_10.html") == "numeros/x_10.html"
    for url in (BASE + "colecciones/x.html", BASE + "numeros/", "https://example.com/numeros/x.html", "", None):
        assert tb.ficha_page(url) == ""


def test_candidates_carry_the_series_then_the_issue_with_every_metadata_field(index):
    [series] = search_tebeosfera(index, "daredevil")
    assert (series.source, series.extra["level"], series.extra["slug"]) == ("Tebeosfera", "series", "daredevil_2019_panini")
    assert series.subtitle == "Panini · 2019" and series.url == BASE + "colecciones/daredevil_2019_panini.html"
    entry = tebeosfera_entry(series)
    assert entry == index.get_entry("daredevil_2019_panini")
    ficha = tb.parse_ficha(page(), URL)
    issue = tebeosfera_issue_candidate(entry, tb.Issue("67", "numeros/daredevil_2019_panini_67.html"), ficha)
    assert (issue.title, issue.number, issue.year, issue.publisher, issue.brand) == ("Daredevil #67", "67", "2025", "Planeta DeAgostini", "Forum")
    assert issue.subtitle == "14 de agosto de 2025 (aprox.) · 28 págs. · 3.30 € · Cuaderno, Grapa · El Hombre Sin Miedo - Ritos de Reconciliación"
    extra = issue.extra
    assert (extra["Year"], extra["Month"], extra["Day"], extra["Count"], extra["LanguageISO"]) == ("2025", "8", "14", "74", "es")
    assert (extra["Writer"], extra["Penciller"], extra["Translator"], extra["CoverArtist"]) == (
        "Saladin Ahmed", "Chris Giarrusso, Todd Nauck", "Gonzalo Quesada", "John Romita Jr., Scott Hanna")
    assert (extra["Genre"], extra["Characters"], extra["Format"], extra["BlackAndWhite"]) == ("Acción, Superhéroes", "Daredevil", "Cuaderno, Grapa", "No")
    assert (extra["GTIN"], extra["ISBN"], extra["Cost"], extra["level"], extra["SpanishPage"]) == (
        "977293854800800020", "", "3.30", "issue", "numeros/daredevil_2019_panini_67.html")
    assert extra["Web"] == BASE + "numeros/daredevil_2019_panini_67.html" and "Datos de la edición (Tebeosfera):" in extra["NotesBlock"]
    assert extra["Title"] == "El Hombre Sin Miedo - Ritos de Reconciliación"


def test_alternatives_and_pages_reached_by_browsing_resolve_like_any_single_issue(index):
    entry = index.get_entry("universo_dc_1989_zinco")
    alternative = tebeosfera_alternative(entry, tb.Issue("10", "numeros/universo_dc_1989_zinco_10.html"))
    assert alternative.title == "Universo DC (1989, Zinco) \xb7 n\xba 10" and alternative.extra["single"] == "1"
    assert tebeosfera_entry(alternative).page == "numeros/universo_dc_1989_zinco_10.html"
    stub = tebeosfera_page_candidate("UNIVERSO DC", "numeros/universo_dc_1989_zinco_10.html")
    assert tebeosfera_entry(stub).page == "numeros/universo_dc_1989_zinco_10.html" and stub.extra["level"] == "series"


def test_naming_suggests_a_spanish_edition_from_a_tebeosfera_candidate(index):
    entry = index.get_entry("daredevil_2019_panini")
    ficha = tb.parse_ficha(page(), URL)
    values = suggest_values(tebeosfera_issue_candidate(entry, tb.Issue("67", "numeros/x.html"), ficha))
    assert (values.nombre, values.bandera, values.edicion, values.editorial, values.sello, values.numero) == (
        "Daredevil", "\U0001f1ea\U0001f1f8", "2025", "Planeta DeAgostini", "Forum", "67")


def test_the_index_is_part_of_the_backups():
    from comic_identify import backup
    assert "tebeosfera.db" in backup.default_sources()


def test_sitemap_numbers_with_no_collection_are_ignored():
    collections, numbers = tb.parse_sitemaps([PAGES["sitemap1.xml"], PAGES["sitemap2.xml"]])
    assert len(collections) == 6 and "huerfano_2000_x" not in numbers
    assert sorted(numbers["daredevil_2019_panini"]) == ["67", "68"]


def test_results_are_ordered_collection_then_tebeosfera_then_universo_marvel_then_gcd():
    from comic_identify.identify import Candidate
    mixed = [Candidate("g", "GCD"), Candidate("m", "Universo Marvel"), Candidate("t", "Tebeosfera"),
             Candidate("c", "ComicVine"), Candidate("l", "Mi colección"), Candidate("t2", "Tebeosfera")]
    assert [c.title for c in sorted(mixed, key=lambda c: c.rank)] == ["l", "t", "t2", "m", "g", "c"]   # ComicVine, tras los catálogos
    parecida = Candidate("g2", "GCD", similarity=0.95)
    exacta = Candidate("g3", "GCD", exact=True)
    ordered = [c.title for c in sorted([*mixed, parecida, exacta], key=lambda c: c.rank)]
    assert ordered[:3] == ["l", "g3", "g2"]   # tu colección siempre primero; luego el código de barras y la portada parecida
