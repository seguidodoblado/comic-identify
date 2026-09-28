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
    assert logo_key("Planeta DeAgostini") is None                       # Planeta a secas no es Forum
    assert logo_key("Norma Editorial", "") is None and logo_key("", "") is None and logo_key() is None


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
