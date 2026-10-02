import pytest

from comic_identify.gcd_api import API, GcdApiClient, GcdApiError

ISSUE = {
    "series": f"{API}series/1/?format=json",
    "number": "100",
    "title": "Casa Tomada",
    "key_date": "2006-12-00",
    "on_sale_date": "2006-12-21",
    "price": "3.50 EUR; 4.00 USD",
    "barcode": "977060120000000012",
    "isbn": "",
    "brand_emblem": "Marvel Knights",
    "story_set": [
        {"type": "cover", "title": "", "genre": "crime; superhero", "characters": "Punisher [Frank Castle]",
         "synopsis": "", "script": "", "pencils": "Tim Bradstreet", "inks": "Tim Bradstreet", "colors": "Grant Goleash",
         "letters": "", "editing": ""},
        {"type": "comic story", "title": "Uno", "genre": "crime; superhero; noir",
         "characters": "Punisher [Frank Castle]; Micro; ?", "synopsis": "Micro se une a la operación.",
         "script": "Garth Ennis; Sofía Traductora (translation)", "pencils": "Lewis LaRosa", "inks": "Lewis LaRosa",
         "colors": "Dean White", "letters": "Randolph Gentile", "editing": "Axel Alonso (editor original)"},
        {"type": "comic story", "title": "Dos", "genre": "crime", "characters": "Micro; Roth", "synopsis": "",
         "script": "Garth Ennis", "pencils": "Tom Palmer", "inks": "Otro Guionista", "colors": "", "letters": "",
         "editing": ""},
        {"type": "advertisement", "title": "Anuncio", "genre": "", "characters": "", "synopsis": "",
         "script": "", "pencils": "", "inks": "", "colors": "", "letters": "", "editing": ""},
    ],
}
SERIES = {"name": "Punisher MAX", "country": "us", "year_began": 2004, "year_ended": 2008,
         "publisher": f"{API}publisher/12/?format=json"}
PUBLISHER = {"name": "Marvel"}

URLS = {ISSUE["series"]: SERIES, SERIES["publisher"]: PUBLISHER}


def fetcher(log=None):
    def fetch(url):
        if log is not None:
            log.append(url)
        if url == f"{API}issue/100/?format=json":
            return ISSUE
        if url in URLS:
            return URLS[url]
        raise GcdApiError(f"sin red en la prueba: {url}")
    return fetch


def test_issue_combines_three_requests_into_a_hit_and_its_details():
    log = []
    hit, _ = GcdApiClient(fetcher(log)).issue(100)
    assert log == [f"{API}issue/100/?format=json", ISSUE["series"], SERIES["publisher"]]
    assert (hit.series, hit.publisher, hit.years, hit.number, hit.title) == (
        "Punisher MAX", "Marvel", "2004–2008", "100", "Casa Tomada")
    assert (hit.issue_id, hit.series_id, hit.country, hit.brand) == (100, 1, "us", "Marvel Knights")


def test_classic_credit_fields_are_split_and_the_cover_only_gives_the_cover_artist():
    _, details = GcdApiClient(fetcher()).issue(100)
    # la traductora (guion anotado «translation») va a Translator, no a Writer; la nota de edición no cambia el papel
    assert details.credits == {"Writer": "Garth Ennis", "Penciller": "Lewis LaRosa, Tom Palmer",
                               "Inker": "Lewis LaRosa, Otro Guionista", "Colorist": "Dean White",
                               "Letterer": "Randolph Gentile", "Editor": "Axel Alonso",
                               "Translator": "Sofía Traductora", "CoverArtist": "Tim Bradstreet"}
    assert "Grant Goleash" not in details.credits["Colorist"] and "Grant Goleash" not in details.credits["CoverArtist"]


def test_genre_characters_and_summary_match_the_local_index_rules():
    _, details = GcdApiClient(fetcher()).issue(100)
    assert details.genre == "crimen, superhéroes, noir"
    assert details.characters == "Punisher, Micro, Roth"
    assert details.summary == "Micro se une a la operación."


def test_several_stories_get_a_line_each_with_who_did_what():
    _, details = GcdApiClient(fetcher()).issue(100)
    assert details.story_lines == [
        "- «Uno»: Guion Garth Ennis · Lápiz Lewis LaRosa · Tinta Lewis LaRosa · Color Dean White",
        "- «Dos»: Guion Garth Ennis · Lápiz Tom Palmer · Tinta Otro Guionista"]


def test_price_barcode_and_dates_pass_through_for_the_shared_issuedetails_helpers():
    _, details = GcdApiClient(fetcher()).issue(100)
    assert (details.cost, details.on_sale, details.barcode) == ("3.50", "2006-12-21", "977060120000000012")
    assert details.date == ("2006", "12", "")
    assert not details.inherited   # la API no da créditos heredados de la historia original reimpresa


def test_an_issue_the_api_does_not_know_raises():
    def fetch(url):
        return {"api_url": url}   # sin "series": la API no tiene ese número
    with pytest.raises(GcdApiError):
        GcdApiClient(fetch).issue(424242)


def test_a_series_without_a_publisher_link_leaves_it_empty():
    def fetch(url):
        if url == f"{API}issue/1/?format=json":
            return {"series": f"{API}series/1/?format=json", "number": "1", "story_set": []}
        return {"name": "Serie sin editorial", "country": "es", "year_began": 1980, "year_ended": None,
               "publisher": None}
    hit, _ = GcdApiClient(fetch).issue(1)
    assert hit.publisher == "" and hit.years == "1980"
