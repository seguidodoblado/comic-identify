import io
import os
import time

from PIL import Image

from comic_identify import logos
from comic_identify.logos import fetch_logo, logo_file, logo_key
from comic_identify.universomarvel import UniversoMarvelError


def _png_bytes(size=(56, 32)):
    buffer = io.BytesIO()
    Image.new("RGB", size, (250, 250, 250)).save(buffer, "JPEG")
    return buffer.getvalue()


def test_logo_key_recognizes_the_publisher_in_any_of_the_texts_ignoring_accents_and_case():
    assert logo_key("Planeta DeAgostini", "Forum") == "forum"
    assert logo_key("Forum/Planeta", "") == "forum"
    assert logo_key("Panini Comics", "") == "panini" and logo_key("PANINI España") == "panini"
    assert logo_key("Ediciones V\xe9rtice") == "vertice" and logo_key("Vertice") == "vertice"
    assert logo_key("Planeta DeAgostini") == "planeta" and logo_key("Planeta De Agostini Comics") == "planeta"
    assert logo_key("Planeta DeAgostini", "Planeta DeAgostini; DC [swirl]") == "planeta"   # sin sello Forum, la editorial
    assert logo_key("Planeta DeAgostini", "Forum; Marvel Comics") == "forum"               # el sello Forum manda
    assert logo_key("ECC Ediciones") == "ecc" and logo_key("Ecc") == "ecc" and logo_key("Ecclesia") is None   # solo la palabra
    assert logo_key("Zinco") == "zinco" and logo_key("Norma Editorial") == "norma" and logo_key("Norma Comics") == "norma"
    assert logo_key("Editorial Bruguera") == "bruguera" and logo_key("Normalizados S.A.") is None      # Norma, solo la palabra
    assert logo_key("Planeta C\xf3mic") is None and logo_key("Editorial Planeta") is None   # otras Planeta no son DeAgostini
    assert logo_key("Ediciones B", "") is None and logo_key("", "") is None and logo_key() is None


def test_fetch_logo_downloads_once_stores_a_png_and_then_serves_the_cache(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        return _png_bytes()
    path = fetch_logo("forum", tmp_path, fetch)
    assert path == tmp_path / "forum.png" and Image.open(path).format == "PNG"
    big = fetch_logo("panini", tmp_path, lambda url: _png_bytes((310, 64)))        # un logotipo grande se reduce al hueco
    assert Image.open(big).size == (116, 24)
    assert Image.open(path).size == (42, 24)                                       # y el peque\xf1o (56x32) tambi\xe9n, con su proporci\xf3n
    assert calls == ["https://fichas.universomarvel.com/ima_gen/logoforum.jpg"]
    assert fetch_logo("forum", tmp_path, fetch) == path and len(calls) == 1      # la segunda vez, de la cach\xe9
    assert logo_file("forum", tmp_path) == path and logo_file("vertice", tmp_path) is None


def test_a_failed_or_invalid_download_leaves_no_logo_and_is_not_retried_for_a_week(tmp_path):
    def broken(url):
        raise UniversoMarvelError("sin red")
    assert fetch_logo("panini", tmp_path, broken) is None and (tmp_path / "panini.none").exists()
    called = []
    assert fetch_logo("panini", tmp_path, lambda url: called.append(url) or _png_bytes()) is None
    assert called == []                                                           # no insiste todav\xeda
    old = time.time() - logos.RETRY_AFTER - 10
    os.utime(tmp_path / "panini.none", (old, old))
    assert fetch_logo("panini", tmp_path, lambda url: _png_bytes((155, 32))) == tmp_path / "panini.png"
    assert not (tmp_path / "panini.none").exists()                               # y con \xe9xito se borra la marca
    assert fetch_logo("vertice", tmp_path, lambda url: b"<html>no soy una imagen</html>") is None
    assert fetch_logo("desconocida", tmp_path, lambda url: _png_bytes()) is None and not (tmp_path / "desconocida.png").exists()


def test_every_logo_has_a_name_a_term_and_a_relative_url_on_the_fichas_site():
    assert set(logos.LOGOS) == set(logos._TERMS) == set(logos.NAMES)
    assert all(path.endswith(".jpg") and not path.startswith("/") for path in logos.LOGOS.values())
    for key, name in logos.NAMES.items():
        assert logo_key(name) == key or key == "forum", (key, name)        # el nombre visible se reconoce a s\xed mismo


def test_publisher_slug_and_short_name():
    from comic_identify.logos import publisher_slug, short_name
    assert publisher_slug("Editorial Novaro") == "editorial-novaro" and publisher_slug("Ediciones B") == "ediciones-b"
    assert publisher_slug("Grupo Editorial Vid, S.A.") == "grupo-editorial-vid-s-a" and publisher_slug("") == ""
    assert publisher_slug("Editorial Zig-Zag") == "editorial-zig-zag" and publisher_slug("Cr\xe1neo \xd1a\xf1a") == "craneo-nana"
    assert short_name('Ediciones B') == "Ediciones B"                             # no se recorta lo que no es forma societaria
    assert short_name("Editorial Ejea S.A. de C.V.") == "Editorial Ejea" and short_name("Editorial Juventud, S.A.") == "Editorial Juventud"
    assert short_name('Editora "La Prensa" Ltda.') == "Editora La Prensa" and short_name("S.A.") == "S.A."


def test_a_logo_put_by_the_user_wins_over_the_downloaded_one_and_covers_unknown_publishers(tmp_path):
    from comic_identify.logos import user_logo
    cache, mine = tmp_path / "cache", tmp_path / "mios"
    mine.mkdir()
    fetch_logo("forum", cache, lambda url: _png_bytes())
    assert logo_file("forum", cache, mine) == cache / "forum.png"                  # nada suyo: el descargado
    (mine / "forum.svg").write_text("<svg/>")
    assert logo_file("forum", cache, mine) == mine / "forum.svg"                  # lo suyo manda
    (mine / "editorial-novaro.jpg").write_bytes(_png_bytes())
    assert user_logo(("editorial-novaro",), mine) == mine / "editorial-novaro.jpg"
    assert user_logo(("otra", "editorial-novaro"), mine) == mine / "editorial-novaro.jpg"
    assert user_logo(("otra",), mine) is None and user_logo(("x",), None) is None and user_logo(("",), mine) is None
