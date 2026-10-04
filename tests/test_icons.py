import io
import os
import time

from PIL import Image

from comic_identify.ui.icons import (
    FALLBACK_URL,
    MARKER,
    RETRY_AFTER,
    _declared_icons,
    ensure_icons,
    fetch_icon,
    icon_file,
)


def _img(size: int, fmt: str, color="red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (size, size), color).save(buffer, fmt)
    return buffer.getvalue()


class FakeWeb:
    def __init__(self, files: dict[str, bytes]):
        self.files, self.calls = files, []

    def __call__(self, url: str):
        self.calls.append(url)
        return self.files.get(url)


def test_favicon_is_converted_to_png_and_cached(tmp_path):
    web = FakeWeb({"https://www.ejemplo.es/favicon.ico": _img(16, "ICO")})
    ready = []
    ensure_icons([("www.ejemplo.es", False)], tmp_path, lambda h, p: ready.append((h, p)), web)
    assert ready == [("www.ejemplo.es", tmp_path / "www.ejemplo.es.png")]
    with Image.open(ready[0][1]) as png:
        assert png.format == "PNG" and png.size == (16, 16)

    ensure_icons([("www.ejemplo.es", False)], tmp_path, lambda h, p: ready.append((h, p)), web)
    assert len(ready) == 2 and len(web.calls) == 1      # la segunda vez sale de la caché, sin red


def test_larger_picks_the_biggest_declared_icon(tmp_path):
    html = (b'<link rel="shortcut icon" href="/favicon.ico">'
            b'<link rel="apple-touch-icon" sizes="120x120" href="/img/touch-120.png">'
            b'<link rel="icon" href="/img/logo-32x32.png"><link rel="stylesheet" href="/x.css">')
    web = FakeWeb({"https://web.es/": html, "https://web.es/favicon.ico": _img(16, "ICO"),
                   "https://web.es/img/touch-120.png": _img(120, "PNG"), "https://web.es/img/logo-32x32.png": _img(32, "PNG")})
    path = fetch_icon("web.es", tmp_path, larger=True, fetch=web)
    with Image.open(path) as png:
        assert png.size == (64, 64)                    # la de 120 px, reducida al máximo de 64
    assert "https://web.es/x.css" not in web.calls


def test_declared_icons_sorted_by_announced_size():
    html = b'<link rel="icon" href="a-16x16.png"><link rel="apple-touch-icon" sizes="180x180" href="b.png">'
    assert _declared_icons(html, "https://x.es/") == ["https://x.es/b.png", "https://x.es/a-16x16.png"]
    assert _declared_icons(None, "https://x.es/") == []


def test_failed_hosts_are_not_retried_for_a_week(tmp_path):
    web = FakeWeb({"https://roto.es/favicon.ico": b"esto no es una imagen"})
    ready = []
    ensure_icons([("roto.es", False)], tmp_path, lambda h, p: ready.append(h), web)
    assert ready == [] and icon_file("roto.es", tmp_path) is None
    assert len(web.calls) == 2                          # su icono y el respaldo del servicio de favicons

    ensure_icons([("roto.es", False)], tmp_path, lambda h, p: ready.append(h), web)
    assert len(web.calls) == 2                          # no reintenta

    old = time.time() - RETRY_AFTER - 10
    os.utime(tmp_path / "roto.es.none", (old, old))
    web.files["https://roto.es/favicon.ico"] = _img(16, "PNG")
    ensure_icons([("roto.es", False)], tmp_path, lambda h, p: ready.append(h), web)
    assert ready == ["roto.es"] and not (tmp_path / "roto.es.none").exists()


def test_a_site_that_blocks_bots_gets_its_icon_from_the_favicon_service(tmp_path):
    web = FakeWeb({FALLBACK_URL.format(host="wiki.es"): _img(64, "PNG", "blue")})       # la propia web no responde
    ready = []
    ensure_icons([("wiki.es", False)], tmp_path, lambda h, p: ready.append(h), web)
    assert ready == ["wiki.es"] and icon_file("wiki.es", tmp_path) is not None
    assert web.calls == ["https://wiki.es/favicon.ico", "https://www.google.com/s2/favicons?domain=wiki.es&sz=64"]
    assert not (tmp_path / "wiki.es.none").exists()


def test_the_favicon_service_is_not_asked_when_the_site_gives_its_own_icon(tmp_path):
    web = FakeWeb({"https://web.es/favicon.ico": _img(16, "ICO")})
    ensure_icons([("web.es", False)], tmp_path, lambda h, p: None, web)
    assert all("google" not in call for call in web.calls)


def test_a_failure_before_the_fallback_existed_is_retried_but_a_new_one_is_not(tmp_path):
    web = FakeWeb({FALLBACK_URL.format(host="wiki.es"): _img(64, "PNG")})
    (tmp_path / "wiki.es.none").touch()                              # marcador antiguo, vacío: no vale
    ensure_icons([("wiki.es", False)], tmp_path, lambda h, p: None, web)
    assert icon_file("wiki.es", tmp_path) is not None
    nothing = FakeWeb({})
    ensure_icons([("nada.es", False)], tmp_path, lambda h, p: None, nothing)      # ni la web ni el servicio
    assert (tmp_path / "nada.es.none").read_text() == MARKER and len(nothing.calls) == 2
    ensure_icons([("nada.es", False)], tmp_path, lambda h, p: None, nothing)
    assert len(nothing.calls) == 2                                    # no se insiste durante una semana
