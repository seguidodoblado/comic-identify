import io
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from conftest import jpeg, make_cover
from PIL import Image
from test_comicinfo import PAGES, needs_rar, rar_fixture

from comic_identify import identify as pipeline
from comic_identify.barcode import Barcode, parse_barcode
from comic_identify.comicvine import ComicVineClient, ComicVineError
from comic_identify.covers import cover_to_png, extract_cover, read_cover, thumbnail_bytes
from comic_identify.hashing import dhash, dhash_variants, similarity
from comic_identify.library import Library
from comic_identify.settings import Settings


def test_same_cover_survives_rescale_and_compression():
    original = make_cover(1)
    scan = Image.open(io.BytesIO(jpeg(original.resize((300, 450)), quality=40)))
    assert similarity(dhash_variants(scan), dhash(original)) > 0.9


def test_scan_with_border_still_matches():
    original = make_cover(1)
    bordered = Image.new("RGB", (660, 990), "white")
    bordered.paste(original, (30, 45))
    assert similarity(dhash_variants(bordered), dhash(original)) > pipeline.MATCH_THRESHOLD


def test_different_covers_are_not_similar():
    scores = [similarity(dhash_variants(make_cover(1)), dhash(make_cover(seed))) for seed in range(2, 12)]
    assert max(scores) < pipeline.MATCH_THRESHOLD


def test_parse_barcode_variants():
    assert parse_barcode(["75960608563000111"]) == Barcode("759606085630", "00111")
    assert parse_barcode(["9780143007234", "12345"]) == Barcode("9780143007234", "12345")
    assert parse_barcode(["759606085630"]) == Barcode("759606085630")
    assert parse_barcode(["hola", ""]) is None
    assert Barcode("759606085630", "00111").issue_number == "1"        # UPC-A: 3 primeros dígitos
    assert Barcode("759606085630", "30011").issue_number == "300"
    assert Barcode("9770601200000", "00024").issue_number == "24"     # EAN-13: complemento completo
    assert Barcode("9770601200000", "00000").issue_number is None
    assert Barcode("9780143007234").issue_number is None


def _cbz(path: Path, pages: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in pages.items():
            archive.writestr(name, data)
    return path


def test_read_cover_natural_order_and_mislabelled_zip(tmp_path):
    pages = {"10.jpg": b"ten", "2.jpg": b"two", "notes.txt": b"x"}
    assert read_cover(_cbz(tmp_path / "a.cbr", pages)) == b"two"  # ZIP con extensión .cbr
    assert read_cover(tmp_path / "missing.cbz") is None


def test_cover_to_png_from_comic_archive(tmp_path):
    comic = _cbz(tmp_path / "x.cbz", {"02.jpg": b"no", "01.jpg": jpeg(make_cover(3))})
    target = tmp_path / "portada.png"
    cover_to_png(comic, target)
    with Image.open(target) as png:
        assert png.format == "PNG" and png.size == (600, 900)
    empty = _cbz(tmp_path / "e.cbz", {"notes.txt": b"x"})
    with pytest.raises(ValueError):
        cover_to_png(empty, target)


def test_library_index_incremental_and_find(tmp_path):
    for seed in (1, 2, 3):
        _cbz(tmp_path / f"comic{seed}.cbz", {"01.jpg": jpeg(make_cover(seed))})
    _cbz(tmp_path / "broken.cbz", {"01.jpg": b"not an image"})
    library = Library(tmp_path / "db" / "library.db")

    stats = library.index([tmp_path])
    assert (stats.indexed, stats.failed, library.count()) == (3, 1, 3)

    query = dhash_variants(make_cover(2).resize((250, 375)))
    path, score = library.find(query)[0]
    assert path.name == "comic2.cbz" and score > 0.9

    assert library.index([tmp_path]).unchanged == 3
    (tmp_path / "comic3.cbz").unlink()
    assert library.index([tmp_path]).removed == 1 and library.count() == 2


def test_settings_roundtrip_is_private(tmp_path):
    file = tmp_path / "cfg" / "config.json"
    Settings("abc", ["/tmp/x"]).save(file)
    assert Settings.load(file) == Settings("abc", ["/tmp/x"])
    assert file.stat().st_mode & 0o777 == 0o600
    assert Settings.load(tmp_path / "nope.json") == Settings()


class FakeComicVine:
    """Sustituye a la red: dos series, y solo el ejemplar 7 de la primera existe."""

    def __init__(self, cover_bytes: bytes, other_bytes: bytes):
        self.covers = {"http://img/right.jpg": cover_bytes, "http://img/wrong.jpg": other_bytes}
        self.urls: list[str] = []

    def __call__(self, url: str) -> bytes:
        import json
        self.urls.append(url)
        if url in self.covers:
            return self.covers[url]
        if "/search/" in url:
            volumes = [{"id": 1, "name": "Right Series", "start_year": "1990",
                        "publisher": {"name": "Acme"}}, {"id": 2, "name": "Wrong Series"}]
            return json.dumps({"status_code": 1, "results": volumes}).encode()
        image = "right" if "volume%3A1" in url else "wrong"
        issue = {"issue_number": "7", "name": "The Return", "cover_date": "1991-07-01",
                 "volume": {"name": image.title() + " Series"}, "site_detail_url": "http://cv/" + image,
                 "image": {"medium_url": f"http://img/{image}.jpg", "super_url": f"http://img/{image}_big.jpg"}}
        return json.dumps({"status_code": 1, "results": [issue]}).encode()


def test_identify_ranks_by_cover_similarity(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "read_barcode", lambda _: None)
    photo = tmp_path / "upload.jpg"
    photo.write_bytes(jpeg(make_cover(5), quality=50))
    fake = FakeComicVine(jpeg(make_cover(5).resize((300, 450))), jpeg(make_cover(6)))

    outcome = pipeline.identify(photo, None, ComicVineClient("key", fake), "right series", "7")

    assert [c.title for c in outcome.candidates] == ["Right Series #7", "Wrong Series #7"]
    assert outcome.candidates[0].is_match and not outcome.candidates[1].is_match
    assert outcome.candidates[0].subtitle == "The Return · 1991-07-01"
    assert outcome.candidates[0].image_url == "http://img/right_big.jpg"   # portada grande para el panel
    assert outcome.issue_number == "7"


def test_identify_reports_missing_key_and_api_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "read_barcode", lambda _: None)
    photo = tmp_path / "u.jpg"
    photo.write_bytes(jpeg(make_cover(1)))
    assert "clave" in pipeline.identify(photo, None, None, "x").notes[0]

    def bad_key(_url):
        return b'{"status_code": 100, "error": "Invalid API Key", "results": []}'
    note = pipeline.identify(photo, None, ComicVineClient("bad", bad_key), "x").notes[0]
    assert "Invalid API Key" in note


def test_comicvine_non_json_raises():
    client = ComicVineClient("k", lambda _url: b"<html>")
    try:
        client.search_volumes("x")
    except ComicVineError:
        return
    raise AssertionError("debía fallar")


def test_thumbnail_is_small_jpeg_and_rejects_garbage():
    thumb = thumbnail_bytes(jpeg(make_cover(1)))
    with Image.open(io.BytesIO(thumb)) as image:
        assert image.format == "JPEG" and max(image.size) == 300 and image.size == (200, 300)
    assert thumbnail_bytes(b"no soy una imagen") is None


def test_identify_shows_thumbnail_for_library_matches(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "read_barcode", lambda _: None)
    _cbz(tmp_path / "Mi Cómic 001.cbz", {"01.jpg": jpeg(make_cover(4))})
    library = Library(tmp_path / "lib.db")
    library.index([tmp_path])
    photo = tmp_path / "u.jpg"
    photo.write_bytes(jpeg(make_cover(4).resize((300, 450)), quality=50))

    outcome = pipeline.identify(photo, library, None)

    match = outcome.candidates[0]
    assert match.source == "Mi colección" and match.title == "Mi Cómic 001"
    assert match.cover and thumbnail_bytes(match.cover)   # miniatura JPEG válida


def test_comicvine_candidate_carries_structured_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "read_barcode", lambda _: None)
    photo = tmp_path / "u.jpg"
    photo.write_bytes(jpeg(make_cover(5)))
    fake = FakeComicVine(jpeg(make_cover(5).resize((300, 450))), jpeg(make_cover(6)))
    candidate = pipeline.identify(photo, None, ComicVineClient("k", fake), "right series", "7").candidates[0]
    assert (candidate.series, candidate.number, candidate.year, candidate.issue_name) == \
        ("Right Series", "7", "1991", "The Return")


def test_comicvine_filters_by_publisher_and_year(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "read_barcode", lambda _: None)
    photo = tmp_path / "u.jpg"
    photo.write_bytes(jpeg(make_cover(5)))
    fake = FakeComicVine(jpeg(make_cover(5).resize((300, 450))), jpeg(make_cover(6)))
    client = ComicVineClient("k", fake)

    assert [c.series for c in pipeline.identify(photo, None, client, "series", "7", publisher="acme").candidates] == \
        ["Right Series"]                                                # solo la serie 1 tiene editorial «Acme»
    assert pipeline.identify(photo, None, client, "series", "7", publisher="Panini").candidates == []
    assert [c.series for c in pipeline.identify(photo, None, client, "series", "7", year="1991").candidates] \
        and pipeline.identify(photo, None, client, "series", "7", year="1985").candidates == []   # el número es de 1991


@pytest.mark.skipif(shutil.which("7z") is None, reason="necesita 7z")
def test_read_cover_from_a_7z_archive_named_cbr(tmp_path):
    """Un «.cbr» puede ser en realidad un 7-Zip: unrar no lo lee, así que se prueba con 7z."""
    image = tmp_path / "01.jpg"
    image.write_bytes(jpeg(make_cover(2)))
    archive = tmp_path / "engañoso.cbr"
    subprocess.run(["7z", "a", "-t7z", "-bd", "-y", str(archive), str(image)], capture_output=True, check=True)
    assert archive.read_bytes()[:6] == b"7z\xbc\xaf'\x1c"
    assert read_cover(archive) == image.read_bytes()


def test_list_and_read_pages_of_a_zip_in_natural_order(tmp_path):
    import zipfile

    from comic_identify.covers import list_pages, read_page
    comic = tmp_path / "a.cbr"                          # extensión de RAR, contenido ZIP
    with zipfile.ZipFile(comic, "w") as archive:
        for name in ("p10.jpg", "p2.jpg", "p1.jpg", "__MACOSX/p1.jpg", "notas.txt", "ComicInfo.xml"):
            archive.writestr(name, name.encode())
    assert list_pages(comic) == ["p1.jpg", "p2.jpg", "p10.jpg"]
    assert read_page(comic, "p2.jpg") == b"p2.jpg" and read_page(comic, "no-existe.jpg") is None
    assert read_cover(comic) == b"p1.jpg"               # la portada sigue siendo la primera página
    (tmp_path / "roto.cbz").write_bytes(b"\x00" * 100)
    assert list_pages(tmp_path / "roto.cbz") == [] and read_page(tmp_path / "roto.cbz", "x.jpg") is None


def test_extract_cover_saves_the_raw_bytes_with_the_original_extension(tmp_path):
    import zipfile

    comic = tmp_path / "a.cbz"
    cover_bytes, other_bytes = b"\xff\xd8" + b"portada" * 20, b"\x89PNG" + b"pagina2" * 20
    with zipfile.ZipFile(comic, "w") as archive:
        archive.writestr("01.jpg", cover_bytes)
        archive.writestr("02.png", other_bytes)
    saved = extract_cover(comic, tmp_path / "Serie 01")
    assert saved == tmp_path / "Serie 01.jpg" and saved.read_bytes() == cover_bytes   # tal cual, sin recodificar

    with pytest.raises(FileExistsError, match="Serie 01.jpg"):
        extract_cover(comic, tmp_path / "Serie 01")           # no se sobrescribe
    assert saved.read_bytes() == cover_bytes

    empty = tmp_path / "vacio.cbz"
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("notas.txt", "x")
    with pytest.raises(ValueError, match="ninguna imagen"):
        extract_cover(empty, tmp_path / "vacio")


@needs_rar
def test_extract_cover_from_a_real_rar(tmp_path):
    comic = rar_fixture(tmp_path, "rar5")
    saved = extract_cover(comic, tmp_path / "portada")
    assert saved == tmp_path / "portada.jpg" and saved.read_bytes() == PAGES["01.jpg"]
