from urllib.parse import parse_qs, urlparse

import pytest

from comic_identify.sources import NAMES, search_url


def _query(url: str) -> dict:
    return parse_qs(urlparse(url).query)


def test_sites_with_their_own_search_use_it():
    panini = search_url("Panini", "Capitán Marvel", "1")
    assert panini.startswith("https://www.panini.es/shp_esp_es/catalogsearch/result/") and _query(panini) == {"q": ["Capitán Marvel 1"]}
    zona = search_url("Zona Negativa", "Los Vengadores")
    assert urlparse(zona).netloc == "www.zonanegativa.com" and _query(zona) == {"s": ["Los Vengadores"]}


def test_the_rest_use_a_site_restricted_google_search():
    for name, domain in (("Tebeosfera", "tebeosfera.com"), ("Whakoom", "whakoom.com"), ("Norma", "normaeditorial.com"),
                         ("Universo Marvel", "fichas.universomarvel.com")):
        url = search_url(name, "Capitán Marvel", "1")
        assert urlparse(url).netloc == "www.google.com"
        assert _query(url) == {"q": [f"site:{domain} Capitán Marvel 1"]}


def test_query_is_url_encoded_and_the_number_is_optional():
    assert search_url("Panini", "Patrulla-X años").endswith("q=Patrulla-X+a%C3%B1os")   # ñ codificada
    assert _query(search_url("Zona Negativa", "  Batman  ", "  "))["s"] == ["Batman"]


def test_errors():
    with pytest.raises(ValueError):
        search_url("Panini", "   ")
    with pytest.raises(ValueError):
        search_url("Inventada", "Batman")
    assert len(NAMES) == 6


def test_every_source_has_a_host_for_its_icon():
    from comic_identify.sources import SOURCES
    assert all(source.host and "/" not in source.host for source in SOURCES)


def test_publisher_and_year_narrow_the_search_when_given():
    google = search_url("Tebeosfera", "Capitán Marvel", "1", "Forum", "2000")
    assert _query(google) == {"q": ["site:tebeosfera.com Capitán Marvel 1 Forum 2000"]}
    assert _query(search_url("Zona Negativa", "Batman", "", "Zinco", "1987"))["s"] == ["Batman Zinco 1987"]
    assert _query(search_url("Panini", "Batman", "5", "", "2012"))["q"] == ["Batman 5 2012"]      # los que faltan se omiten
    assert search_url("Panini", "Batman", "5") == search_url("Panini", "Batman", "5", "", "")     # y son opcionales
