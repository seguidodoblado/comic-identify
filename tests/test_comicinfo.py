import shutil
import struct
import subprocess
import zipfile
import zlib
from pathlib import Path

import pytest

from comic_identify import comicinfo
from comic_identify.comicinfo import (
    MetadataError,
    archive_kind,
    build_xml,
    category_of,
    parse_info,
    read_info,
    read_xml,
    with_category,
    write_xml,
)

PAGES = {"01.jpg": b"\xff\xd8page-one" * 50, "02.jpg": b"\xff\xd8page-two" * 70, "sub/03.jpg": b"\xff\xd8page-3" * 30}


def make_zip(path: Path, extra: dict[str, bytes] | None = None, comment: bytes = b"") -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.comment = comment
        for name, data in {**PAGES, **(extra or {})}.items():
            archive.writestr(name, data, compress_type=zipfile.ZIP_STORED if name.endswith("01.jpg") else zipfile.ZIP_DEFLATED)
    return path


def make_with_tool(command: list[str], tmp_path: Path, name: str, extra: dict[str, bytes] | None = None) -> Path:
    source = tmp_path / f"src-{name}"
    source.mkdir()
    for page, data in {**PAGES, **(extra or {})}.items():
        (source / page).parent.mkdir(parents=True, exist_ok=True)
        (source / page).write_bytes(data)
    target = tmp_path / name
    subprocess.run([*command, str(target), "."], cwd=source, check=True, capture_output=True)
    return target


def make_rar4(path: Path, files: dict[str, bytes]) -> Path:
    """RAR 2.9 (el formato de tantos «.cbr» antiguos) con los archivos sin comprimir: rar 7 ya no sabe crearlos."""
    def block(kind: int, flags: int, body: bytes) -> bytes:
        rest = struct.pack("<BHH", kind, flags, 7 + len(body)) + body
        return struct.pack("<H", zlib.crc32(rest) & 0xFFFF) + rest
    out = b"Rar!\x1a\x07\x00" + block(0x73, 0, b"\x00" * 6)
    for name, data in files.items():
        raw = name.encode()
        body = struct.pack("<IIBIIBBHI", len(data), len(data), 3, zlib.crc32(data), 0x5A3C2100, 29, 0x30, len(raw),
                           0x81A4) + raw
        header = block(0x74, 0x8000, body)
        out += header + data
    path.write_bytes(out + bytes.fromhex("c43d7b00400700"))
    return path


def pages_of(path: Path) -> dict[str, bytes]:
    """Contenido de las páginas extraído con una herramienta ajena al módulo (unrar para RAR: este 7z no lee los
    RAR que crea rar 7.00)."""
    folder = path.parent / f"out-{path.name}"
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir()
    if archive_kind(path) == "rar":
        subprocess.run(["unrar", "x", "-y", "-inul", str(path), f"{folder}/"], check=True, capture_output=True)
    else:
        subprocess.run(["7z", "x", "-y", f"-o{folder}", str(path)], check=True, capture_output=True)
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*")
            if p.is_file() and p.name != "ComicInfo.xml"}


# ---- XML ------------------------------------------------------------------------------------------------------

def test_build_xml_new_file_uses_schema_order():
    xml = build_xml(None, {"Web": "http://x", "Series": "Capitán Marvel", "Number": "1", "Year": "2000",
                           "Publisher": "Planeta", "Title": ""})
    assert xml.startswith(b'<?xml version="1.0" encoding="utf-8"?>')
    assert list(parse_info(xml)) == ["Series", "Number", "Year", "Publisher", "Web"]     # orden del esquema, sin campos vacíos
    assert parse_info(xml)["Series"] == "Capitán Marvel"


def test_build_xml_keeps_what_it_does_not_touch_and_removes_blanked_fields():
    existing = (b'<?xml version="1.0"?><ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                b"<Writer>Alan Moore</Writer><Series>Viejo</Series><Summary>Resumen</Summary>"
                b'<Pages><Page Image="0" Type="FrontCover"/></Pages><Extra>x</Extra></ComicInfo>')
    xml = build_xml(existing, {"Series": "Nuevo", "Summary": "", "Year": "1999"})
    info = parse_info(xml)
    assert info["Series"] == "Nuevo" and info["Writer"] == "Alan Moore" and info["Year"] == "1999"
    assert "Summary" not in info and info["Extra"] == "x"
    assert b'<Page Image="0" Type="FrontCover"' in xml                         # las páginas se conservan
    assert list(parse_info(xml)).index("Series") < list(parse_info(xml)).index("Writer") < list(parse_info(xml)).index("Extra")


def test_build_xml_validates_values_and_input():
    for bad in ({"Year": "20x0"}, {"Month": "13"}, {"Day": "0"}, {"Count": "-1"}, {"Inventado": "x"}):
        with pytest.raises(MetadataError):
            build_xml(None, bad)
    with pytest.raises(MetadataError):
        build_xml(b"<no es xml", {"Series": "x"})
    with pytest.raises(MetadataError):
        build_xml(b"<Otra/>", {"Series": "x"})
    assert parse_info(build_xml(None, {"Month": "12", "Day": "31", "Volume": "8"}))["Volume"] == "8"


def test_special_characters_survive_a_round_trip():
    xml = build_xml(None, {"Series": "Punisher: P.O.V. <&> «ñ» 🇪🇸", "Notes": "línea 1\nlínea 2"})
    assert parse_info(xml) == {"Series": "Punisher: P.O.V. <&> «ñ» 🇪🇸", "Notes": "línea 1\nlínea 2"}


def test_category_lives_in_tags_and_keeps_other_tags():
    assert with_category("", "Series") == "Categoría: Series"
    assert with_category("Superhéroes, Categoría: Series", "Recopilatorios y clásicos") == \
        "Superhéroes, Categoría: Recopilatorios y clásicos"
    assert with_category("Superhéroes, Categoría: Series", "") == "Superhéroes"
    assert category_of("Superhéroes, Categoría: Eventos y crossovers") == "Eventos y crossovers"
    assert category_of("solo etiquetas") == ""
    assert "Series" in comicinfo.CATEGORIES and len(comicinfo.CATEGORIES) == 7


# ---- ZIP ------------------------------------------------------------------------------------------------------

def test_kind_is_decided_by_content_not_extension(tmp_path):
    zipped = make_zip(tmp_path / "es-zip.cbr")
    assert archive_kind(zipped) == "zip"
    (tmp_path / "vacio.cbz").write_bytes(b"\x00" * 4096)          # cabecera a ceros: dañado
    assert archive_kind(tmp_path / "vacio.cbz") is None
    with pytest.raises(MetadataError, match="dañado"):
        read_xml(tmp_path / "vacio.cbz")
    with pytest.raises(MetadataError, match="dañado"):
        write_xml(tmp_path / "vacio.cbz", b"<ComicInfo/>")
    assert (tmp_path / "vacio.cbz").read_bytes() == b"\x00" * 4096


def test_zip_write_read_replace_and_delete(tmp_path):
    comic = make_zip(tmp_path / "a.cbz", comment=b"nota")
    assert read_xml(comic) is None and read_info(comic) == {}
    write_xml(comic, build_xml(None, {"Series": "Uno", "Number": "1"}))
    assert read_info(comic) == {"Series": "Uno", "Number": "1"}
    with zipfile.ZipFile(comic) as archive:
        assert archive.comment == b"nota" and archive.testzip() is None
        assert {n: archive.read(n) for n in archive.namelist() if n != "ComicInfo.xml"} == PAGES
    write_xml(comic, build_xml(read_xml(comic), {"Series": "Dos", "Year": "2001"}))
    assert read_info(comic) == {"Series": "Dos", "Number": "1", "Year": "2001"}
    with zipfile.ZipFile(comic) as archive:
        assert archive.namelist().count("ComicInfo.xml") == 1                # sustituido, no duplicado
    write_xml(comic, None)
    assert read_xml(comic) is None
    with zipfile.ZipFile(comic) as archive:
        assert {n: archive.read(n) for n in archive.namelist()} == PAGES
    assert [p.name for p in tmp_path.iterdir()] == ["a.cbz"]                    # ni rastro de temporales


def test_zip_replaces_an_existing_differently_cased_entry(tmp_path):
    comic = make_zip(tmp_path / "a.cbz", extra={"comicinfo.XML": b"<ComicInfo><Series>Viejo</Series></ComicInfo>"})
    assert read_info(comic) == {"Series": "Viejo"}
    write_xml(comic, build_xml(read_xml(comic), {"Series": "Nuevo"}))
    with zipfile.ZipFile(comic) as archive:
        assert [n for n in archive.namelist() if n.lower() == "comicinfo.xml"] == ["ComicInfo.xml"]
    assert read_info(comic) == {"Series": "Nuevo"}


def test_a_failed_write_leaves_the_original_untouched(tmp_path, monkeypatch):
    comic = make_zip(tmp_path / "a.cbz")
    before = comic.read_bytes()
    with pytest.raises(MetadataError):
        write_xml(comic, b"<esto no es xml")
    monkeypatch.setattr(comicinfo, "_verify", lambda *args: (_ for _ in ()).throw(MetadataError("simulado")))
    with pytest.raises(MetadataError, match="simulado"):
        write_xml(comic, build_xml(None, {"Series": "X"}))
    assert comic.read_bytes() == before and [p.name for p in tmp_path.iterdir()] == ["a.cbz"]


def test_not_enough_disk_space_is_reported_before_touching_anything(tmp_path, monkeypatch):
    comic = make_zip(tmp_path / "a.cbz")
    monkeypatch.setattr(comicinfo.shutil, "disk_usage", lambda _p: shutil._ntuple_diskusage(10, 10, 0))
    with pytest.raises(MetadataError, match="espacio"):
        write_xml(comic, build_xml(None, {"Series": "X"}))


def test_encrypted_zip_is_refused(tmp_path):
    comic = make_zip(tmp_path / "a.cbz")
    data = bytearray(comic.read_bytes())
    for marker in (b"PK\x03\x04", b"PK\x01\x02"):        # marca el bit de cifrado en las cabeceras
        offset = 0
        while (offset := data.find(marker, offset)) != -1:
            data[offset + (6 if marker == b"PK\x03\x04" else 8)] |= 1
            offset += 4
    comic.write_bytes(bytes(data))
    with pytest.raises(MetadataError, match="cifrado"):
        write_xml(comic, build_xml(None, {"Series": "X"}))


# ---- RAR y 7z (necesitan los programas instalados) --------------------------------------------------------------

needs_rar = pytest.mark.skipif(not (shutil.which("rar") and shutil.which("7z")), reason="faltan rar y 7z")
needs_7z = pytest.mark.skipif(not shutil.which("7z"), reason="falta 7z")


def rar_fixture(tmp_path: Path, flavour: str) -> Path:
    if flavour == "rar4":
        return make_rar4(tmp_path / "a.cbr", {name.replace("/", "_"): data for name, data in PAGES.items()})
    return make_with_tool(["rar", "a", "-r", "-idq", "-ma5", *(["-s"] if flavour == "rar5-solido" else [])], tmp_path, "a.cbr")


@needs_rar
@pytest.mark.parametrize("flavour", ["rar5", "rar4", "rar5-solido"])
def test_rar_write_read_replace_and_delete(tmp_path, flavour):
    comic = rar_fixture(tmp_path, flavour)
    expected = {name.replace("/", "_"): data for name, data in PAGES.items()} if flavour == "rar4" else PAGES
    assert archive_kind(comic) == "rar" and read_xml(comic) is None
    write_xml(comic, build_xml(None, {"Series": "Uno", "Number": "1"}))
    assert archive_kind(comic) == "rar" and read_info(comic) == {"Series": "Uno", "Number": "1"}
    assert pages_of(comic) == expected
    write_xml(comic, build_xml(read_xml(comic), {"Series": "Dos", "Publisher": "Forum"}))
    assert read_info(comic) == {"Series": "Dos", "Number": "1", "Publisher": "Forum"}
    assert pages_of(comic) == expected
    listing = subprocess.run(["unrar", "lb", str(comic)], capture_output=True, text=True, check=True).stdout.splitlines()
    assert listing.count("ComicInfo.xml") == 1
    write_xml(comic, None)
    assert read_xml(comic) is None and pages_of(comic) == expected
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".")]


@needs_rar
def test_rar_keeps_its_format_version(tmp_path):
    for flavour, magic in (("rar4", b"Rar!\x1a\x07\x00"), ("rar5", b"Rar!\x1a\x07\x01\x00")):
        (tmp_path / flavour).mkdir()
        comic = rar_fixture(tmp_path / flavour, flavour)
        assert comic.read_bytes().startswith(magic)
        write_xml(comic, build_xml(None, {"Series": "X"}))
        assert comic.read_bytes().startswith(magic)         # rar no «actualiza» un RAR4 a RAR5 ni al revés


@needs_rar
def test_rar_with_a_zip_or_7z_inside_a_cbr_name_is_handled_by_real_type(tmp_path):
    comic = make_zip(tmp_path / "es-zip.cbr")                     # extensión de RAR, contenido ZIP
    write_xml(comic, build_xml(None, {"Series": "X"}))
    assert archive_kind(comic) == "zip" and read_info(comic) == {"Series": "X"}


@needs_7z
def test_7z_write_read_replace_and_delete(tmp_path):
    comic = make_with_tool(["7z", "a", "-bd", "-bso0"], tmp_path, "a.cb7")
    assert archive_kind(comic) == "7z" and read_xml(comic) is None
    write_xml(comic, build_xml(None, {"Series": "Uno"}))
    assert read_info(comic) == {"Series": "Uno"} and pages_of(comic) == PAGES
    write_xml(comic, build_xml(read_xml(comic), {"Series": "Dos"}))
    assert read_info(comic) == {"Series": "Dos"} and pages_of(comic) == PAGES
    write_xml(comic, None)
    assert read_xml(comic) is None and pages_of(comic) == PAGES


@needs_rar
def test_rar_without_the_rar_program_gives_a_clear_error(tmp_path, monkeypatch):
    comic = make_with_tool(["rar", "a", "-r", "-idq"], tmp_path, "a.cbr")
    before = comic.read_bytes()
    real_which = shutil.which
    monkeypatch.setattr(comicinfo.shutil, "which", lambda name: None if name == "rar" else real_which(name))
    with pytest.raises(MetadataError, match="rar"):
        write_xml(comic, build_xml(None, {"Series": "X"}))
    assert comic.read_bytes() == before


@needs_rar
@pytest.mark.parametrize("flavour", ["rar5", "rar4"])
def test_pages_of_a_rar_can_be_listed_and_read_one_by_one(tmp_path, flavour):
    from comic_identify.covers import list_pages, read_page
    comic = rar_fixture(tmp_path, flavour)
    pages = list_pages(comic)
    assert pages[:2] == ["01.jpg", "02.jpg"] and len(pages) == 3
    assert read_page(comic, "02.jpg") == PAGES["02.jpg"] and read_page(comic, pages[2]) is not None
