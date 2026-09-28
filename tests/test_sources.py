from urllib.parse import parse_qs, urlparse

import pytest

from comic_identify.sources import NAMES, search_url


def _query(url: str) -> dict:
    return parse_qs(urlparse(url).query)


def test_sites_with_their_own_search_use_it():
    panini = search_url("Panini", "Capitán Marvel", "1")
    assert panini.startswith("https://www.panini.es/shp_esp_es/catalogsearch/result/") and _query(panini) == {"q": ["Capitán Marvel 1"]}


def test_the_rest_use_a_site_restricted_google_search():
    for name, domain in (("Tebeosfera", "tebeosfera.com"), ("Whakoom", "whakoom.com"), ("Norma", "normaeditorial.com"),
                         ("Universo Marvel", "fichas.universomarvel.com"), ("Norma Comics", "normacomics.com"),
                         ("DC Comics", "dc.com"), ("DC Database", "dc.fandom.com")):
        url = search_url(name, "Capitán Marvel", "1")
        assert urlparse(url).netloc == "www.google.com"
        assert _query(url) == {"q": [f"site:{domain} Capitán Marvel 1"]}


def test_query_is_url_encoded_and_the_number_is_optional():
    assert search_url("Panini", "Patrulla-X años").endswith("q=Patrulla-X+a%C3%B1os")   # ñ codificada


def test_errors():
    with pytest.raises(ValueError):
        search_url("Panini", "   ")
    with pytest.raises(ValueError):
        search_url("Inventada", "Batman")
    assert len(NAMES) == 8


def test_every_source_has_a_host_for_its_icon():
    from comic_identify.sources import SOURCES
    assert all(source.host and "/" not in source.host for source in SOURCES)


def test_every_source_belongs_to_a_known_category_and_none_is_left_empty():
    from comic_identify.sources import GROUPS, SOURCES
    assert all(source.category in GROUPS for source in SOURCES)
    assert all(any(source.category == category for source in SOURCES) for category in GROUPS)
    assert {s.name: s.category for s in SOURCES if s.category != "Generalistas"} == {
        "Universo Marvel": "Marvel", "DC Comics": "DC", "DC Database": "DC"}


def test_publisher_and_year_narrow_the_search_when_given():
    google = search_url("Tebeosfera", "Capitán Marvel", "1", "Forum", "2000")
    assert _query(google) == {"q": ["site:tebeosfera.com Capitán Marvel 1 Forum 2000"]}
    assert _query(search_url("Panini", "Batman", "5", "", "2012"))["q"] == ["Batman 5 2012"]      # los que faltan se omiten
    assert search_url("Panini", "Batman", "5") == search_url("Panini", "Batman", "5", "", "")     # y son opcionales


def test_shops_build_search_urls_for_the_title_number_publisher_and_year():
    from comic_identify.sources import SHOP_GROUPS, SHOPS, shop_url
    assert _query(shop_url("Editorial Ivrea", "Darwin's Game", "1"))["buscar"] == ["Darwin's Game 1"]
    assert _query(shop_url("Todocolección", "Spiderman", "34", "Panini", "2005")) == {"bu": ["Spiderman 34 Panini 2005"]}
    assert _query(shop_url("eBay.es", "Capitán Marvel", "1"))["_nkw"] == ["Capitán Marvel 1"]
    assert _query(shop_url("Wallapop", "Alpha Flight"))["keywords"] == ["Alpha Flight"]
    assert _query(shop_url("Milanuncios", "Conan"))["s"] == ["Conan"]
    assert _query(shop_url("Iberlibro", "Conan", "3"))["kn"] == ["Conan 3"]
    assert _query(shop_url("Amazon.es", "Conan"))["k"] == ["Conan"]
    assert _query(shop_url("Casa del Libro", "Conan"))["q"] == ["Conan"]
    assert _query(shop_url("Panini", "Batman", "5", "", "2012"))["q"] == ["Batman 5 2012"]   # los que faltan se omiten
    assert {shop.category for shop in SHOPS} == set(SHOP_GROUPS) and len(SHOPS) == 9
    assert all(shop.host and "/" not in shop.host and "{q}" in shop.template for shop in SHOPS)


def test_shop_url_needs_a_title_and_a_known_shop_and_encodes_special_characters():
    from comic_identify.sources import shop_url
    with pytest.raises(ValueError):
        shop_url("Wallapop", "   ", "34")
    with pytest.raises(ValueError):
        shop_url("Inventada", "Batman")
    assert "%26" in shop_url("Todocolecci\xf3n", "Alpha Flight & La Masa") and "+" in shop_url("Wallapop", "Alpha Flight")
