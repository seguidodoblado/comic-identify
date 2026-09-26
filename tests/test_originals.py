import json
from urllib.parse import parse_qs, urlparse

import pytest

from comic_identify.comicvine import ComicVineClient, ComicVineError
from comic_identify.originals import content_years, find_volumes

# Fechas de portada por (serie, número); el 9 no tiene fecha y el resto de números no existe.
DATES = {(6458, "1"): "1999-11-01", (6458, "26"): "2001-12-01", (6458, "5"): "2000-03-01",
         (6458, "9"): None, (7000, "1"): "2008-06-01"}


class FakeComicVine:
    """Dos series americanas con esas fechas."""

    def __init__(self):
        self.calls = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        query = parse_qs(urlparse(url).query)
        if "/search/" in url:
            volumes = [{"id": 6458, "name": "Captain Marvel", "start_year": "1999", "publisher": {"name": "Marvel"},
                        "count_of_issues": 35},
                       {"id": 7000, "name": "Captain Marvel", "start_year": "2008", "publisher": None}]
            return json.dumps({"status_code": 1, "results": volumes}).encode()
        volume, number = (part.split(":")[1] for part in query["filter"][0].split(","))
        date = DATES.get((int(volume), number), "no")
        results = [] if date == "no" else [{"issue_number": number, "cover_date": date}]
        return json.dumps({"status_code": 1, "results": results}).encode()


@pytest.fixture
def client():
    return ComicVineClient("clave", FakeComicVine())


def test_find_volumes_lists_series_with_their_details(client):
    volumes = find_volumes(client, "  Captain Marvel ")
    assert [(v.id, v.start_year, v.publisher, v.issues) for v in volumes] == [(6458, "1999", "Marvel", "35"), (7000, "2008", "", "")]
    assert volumes[0].label == "Captain Marvel (1999) · Marvel · 35 números"
    assert volumes[1].label == "Captain Marvel (2008)"
    with pytest.raises(ValueError):
        find_volumes(client, "   ")


def test_content_years_from_first_and_last_issue(client):
    assert content_years(client, 6458, "1", "26") == "1999-2001"
    assert content_years(client, 6458, "1") == "1999"                # un solo número
    assert content_years(client, 6458, "26", "1") == "1999-2001"     # da igual el orden
    assert content_years(client, 6458, "5", "5") == "2000"           # mismo año: un solo valor


def test_content_years_is_lenient_with_missing_dates_but_fails_when_there_is_none(client):
    assert content_years(client, 6458, "1", "9") == "1999"           # el 9 no tiene fecha: se usa el que sí
    with pytest.raises(LookupError, match="fecha de portada"):
        content_years(client, 6458, "9")                             # sin fecha
    with pytest.raises(LookupError):
        content_years(client, 6458, "99")                            # el número no existe
    with pytest.raises(ValueError):
        content_years(client, 6458, "  ", "")


def test_api_errors_reach_the_caller():
    bad = ComicVineClient("mala", lambda _url: b'{"status_code": 100, "error": "Invalid API Key", "results": []}')
    with pytest.raises(ComicVineError, match="Invalid API Key"):
        find_volumes(bad, "Batman")
