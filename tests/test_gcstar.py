import json
import zipfile
from pathlib import Path

import pytest
from conftest import jpeg, make_cover

import comic_identify.gcstar as gcstar_module
from comic_identify.gcstar import (
    GCstarError,
    TransferResult,
    build_attrs,
    build_item,
    cost_text,
    format_date,
    format_name,
    insert_item,
    is_isbn,
    is_running,
    isbn_text,
    mirror_stems,
    next_id,
    publisher_text,
    relative_path,
    series_text,
    suggest_type,
    transfer,
    undo_last,
    vocabulary,
)

TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<collection type="GCcomics" items="1" version="1.8.0">
 <information>
  <description>Colección de prueba</description>
  <images>/tmp/Colecciones/Comics/</images>
  <maxId>3</maxId>
  <name>Comics</name>
 </information>

 <item
  id="3"
  name="Serie #001"
  series="Serie"
  volume="1"
  type="Serie"
  category="USA"
  format="Grapa"
  collection="Universo"
 >
 </item>
</collection>
"""


@pytest.fixture(autouse=True)
def _gcstar_not_running(monkeypatch):
    """`is_running()` mira el `/proc` real de la máquina; en esta sesión de desarrollo hay procesos que mencionan
    «gcstar» (este mismo archivo de pruebas, el editor, …), así que sin esto las pruebas serían intermitentes. Las
    que quieren probar el caso «sí está abierto» lo pisan ellas mismas con su propio monkeypatch."""
    monkeypatch.setattr(gcstar_module, "is_running", lambda *a, **k: False)


def _comic(path: Path, pages: int = 2) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for n in range(1, pages + 1):
            archive.writestr(f"{n:02d}.jpg", jpeg(make_cover(n)))
    return path


# ---- Funciones puras -----------------------------------------------------------------------------------------

def test_next_id_ignores_the_stale_maxid_and_uses_the_real_items():
    assert next_id(TEMPLATE) == 4
    assert next_id('<collection><item id="1"/><item id="9"/></collection>') == 10
    assert next_id("<collection></collection>") == 1
    assert next_id("esto no es xml") == 1


def test_vocabulary_deduplicates_and_keeps_first_seen_order():
    text = ('<collection><item id="1" category="USA"/><item id="2" category="Europa"/>'
           '<item id="3" category="USA"/><item id="4"/></collection>')
    assert vocabulary(text, "category") == ["USA", "Europa"]
    assert vocabulary(text, "format") == []


def test_format_name_matches_gcstars_own_formula():
    assert format_name("Blake y Mortimer", "1", "El secreto del espadón I") == "Blake y Mortimer #001 El secreto del espadón I"
    assert format_name("Serie", "12", "") == "Serie #012"
    assert format_name("Serie", "", "Sin número") == "Serie Sin número"
    assert format_name("Serie", "no-numerico", "") == "Serie"


def test_format_date_defaults_to_january_first_and_rejects_nonsense():
    assert format_date("2000", "3", "7") == "07/03/2000"
    assert format_date("2000", "", "") == "01/01/2000"
    assert format_date("", "3", "7") == ""
    assert format_date("2000", "2", "30") == ""          # 30 de febrero no existe: se deja vacío, no se inventa


def test_series_text_adds_volumen_only_when_it_is_a_real_restart():
    assert series_text("Capitán Marvel", "") == "Capitán Marvel"
    assert series_text("Capitán Marvel", "1") == "Capitán Marvel"
    assert series_text("Capitán Marvel", "3") == "Capitán Marvel Volumen 3"


def test_publisher_text_combines_editorial_and_sello_without_stray_dashes():
    assert publisher_text("Planeta DeAgostini", "Forum") == "Planeta DeAgostini - Forum"
    assert publisher_text("Panini", "") == "Panini"
    assert publisher_text("", "Forum") == "Forum"
    assert publisher_text("  ", "  ") == ""


def test_build_attrs_puts_editorial_and_sello_together_in_publicado_por():
    fields = {"Series": "Alpha Flight", "Publisher": "Planeta DeAgostini", "Imprint": "Forum"}
    attrs = build_attrs(fields, {}, Path("/c/01.cbr"), 0, None, None, Path("/gcs"))
    assert attrs["publisher"] == "Planeta DeAgostini - Forum"
    assert "publisher" not in build_attrs({"Series": "X"}, {}, Path("/c/01.cbr"), 0, None, None, Path("/gcs"))


def test_build_attrs_maps_our_fields_to_gcstars_and_number_becomes_volume():
    fields = {"Series": "Blake y Mortimer", "Number": "1", "Title": "El secreto del espadón I",
              "Writer": "Edgar P. Jacobs", "Penciller": "Edgar P. Jacobs", "Publisher": "Norma Editorial",
              "Year": "1946", "Summary": "Resumen", "Notes": "Nota personal", "Volume": "",
              "Web": "https://www.comics.org/series/1234/", "CoverArtist": "Rafael L\xf3pez Esp\xed"}
    attrs = build_attrs(fields, {"type": "Serie", "category": "Franco-Belga"}, Path("/c/01.cbr"), 64, None, None,
                        Path("/gcs"))
    assert attrs["series"] == "Blake y Mortimer" and attrs["volume"] == "1"           # el Nº, no nuestro Volumen
    assert attrs["writer"] == attrs["illustrator"] == "Edgar P. Jacobs"
    assert attrs["publisher"] == "Norma Editorial" and attrs["publishdate"] == "01/01/1946"
    assert attrs["webPage"] == "https://www.comics.org/series/1234/"
    assert attrs["artist"] == "Rafael L\xf3pez Esp\xed"                  # el autor de la portada va a su «Cover Artist»
    assert attrs["synopsis"] == "Resumen" and attrs["comment"] == "Nota personal"
    assert attrs["type"] == "Serie" and attrs["category"] == "Franco-Belga"
    assert attrs["numberboards"] == "64" and attrs["file"] == "/c/01.cbr" and attrs["borrower"] == "none"
    assert "image" not in attrs and "backpic" not in attrs           # sin portada: no se escribe el atributo vacío


def test_build_item_and_insert_item_produce_valid_escaped_xml():
    import xml.etree.ElementTree as ET
    attrs = {"series": "Punisher: P.O.V. <&> «ñ» 🇪🇸", "volume": "1", "synopsis": "línea 1\nlínea 2"}
    item_xml = build_item(attrs, 42)
    assert 'id="42"' in item_xml
    full = insert_item(TEMPLATE, item_xml)
    root = ET.fromstring(full)
    items = root.findall("item")
    assert len(items) == 2 and items[-1].get("id") == "42"
    assert items[-1].get("series") == "Punisher: P.O.V. <&> «ñ» 🇪🇸"
    assert items[-1].find("synopsis").text == "línea 1\nlínea 2"
    # nada más del archivo cambia: solo se ha insertado el bloque nuevo justo antes de </collection>
    marker = TEMPLATE.rindex("</collection>")
    assert full == TEMPLATE[:marker] + item_xml + TEMPLATE[marker:]


def test_insert_item_refuses_a_file_without_a_collection_tag():
    with pytest.raises(GCstarError, match="collection"):
        insert_item("<algo/>", "<item/>")


def test_mirror_stems_only_when_the_comic_is_under_a_configured_folder(tmp_path):
    library = tmp_path / "Games" / "comics"
    comic = library / "EUROPA" / "Serie" / "Serie #01.cbz"
    comic.parent.mkdir(parents=True)
    comic.touch()
    gcs = tmp_path / "Colecciones" / "comics.gcs"
    cover, back = mirror_stems(comic, [library], gcs)
    # bajo IMAGES_SUBFOLDER ("comics"): así conviven varias colecciones de GCstar bajo la misma carpeta de imágenes
    assert cover == tmp_path / "Colecciones" / "comics" / "EUROPA" / "Serie" / "Serie #01 - Portada"
    assert back == tmp_path / "Colecciones" / "comics" / "EUROPA" / "Serie" / "Serie #01 - Trasera"
    assert mirror_stems(comic, [tmp_path / "otra"], gcs) is None


def test_relative_path_and_suggested_type_do_not_depend_on_the_absolute_disk(tmp_path):
    for root_name in ("disco_A", "disco_B"):   # simula que la colección se muda a otro disco/punto de montaje
        library = tmp_path / root_name / "comics"
        comic = library / "EUROPA" / "Serie" / "Serie #01.cbz"
        comic.parent.mkdir(parents=True)
        comic.touch()
        assert relative_path(comic, [library]) == Path("EUROPA/Serie/Serie #01.cbz")
        assert suggest_type(comic, [library]) == "Europeo"
    usa = tmp_path / "disco_A" / "comics" / "USA" / "Marvel" / "X #01.cbz"
    usa.parent.mkdir(parents=True); usa.touch()
    assert suggest_type(usa, [tmp_path / "disco_A" / "comics"]) == "Americano"
    japon = tmp_path / "disco_A" / "comics" / "JAPÓN" / "Serie" / "X #01.cbz"
    japon.parent.mkdir(parents=True); japon.touch()
    assert suggest_type(japon, [tmp_path / "disco_A" / "comics"]) == "Manga"
    assert relative_path(tmp_path / "suelto.cbz", [tmp_path / "disco_A" / "comics"]) is None
    assert suggest_type(tmp_path / "suelto.cbz", [tmp_path / "disco_A" / "comics"]) == ""
    otra_carpeta = tmp_path / "disco_A" / "comics" / "SIN_MAPEAR" / "X.cbz"
    otra_carpeta.parent.mkdir(parents=True); otra_carpeta.touch()
    assert suggest_type(otra_carpeta, [tmp_path / "disco_A" / "comics"]) == ""   # carpeta que no reconocemos: no se inventa


def test_is_running_reads_proc_cmdline(tmp_path):
    proc = tmp_path / "proc"
    (proc / "123").mkdir(parents=True)
    (proc / "123" / "cmdline").write_bytes(b"/usr/bin/perl\x00/usr/bin/gcstar\x00")
    (proc / "456").mkdir(parents=True)
    (proc / "456" / "cmdline").write_bytes(b"/usr/bin/firefox\x00")
    (proc / "not-a-pid").mkdir(parents=True)
    assert is_running(proc) is True
    (proc / "123" / "cmdline").write_bytes(b"/usr/bin/firefox\x00")
    assert is_running(proc) is False
    assert is_running(tmp_path / "no-existe") is False
    # una subcadena no basta: si no, esta prueba se detectaría a sí misma (vive en test_gcstar.py)
    (proc / "789").mkdir(parents=True)
    (proc / "789" / "cmdline").write_bytes(b"/usr/bin/python\x00-m\x00pytest\x00tests/test_gcstar.py\x00")
    assert is_running(proc) is False


# ---- Transferencia de principio a fin -----------------------------------------------------------------------

@pytest.fixture
def scenario(tmp_path):
    library = tmp_path / "Games" / "comics"
    (library / "USA" / "Serie").mkdir(parents=True)
    comic = _comic(library / "USA" / "Serie" / "Serie #01.cbz")
    gcs = tmp_path / "Colecciones" / "comics.gcs"
    gcs.parent.mkdir(parents=True)
    gcs.write_text(TEMPLATE, encoding="utf-8")
    return comic, gcs, [library], tmp_path / "gcstar.log"


def test_transfer_adds_the_item_and_mirrors_the_cover_and_back_cover(scenario):
    comic, gcs, folders, log = scenario
    fields = {"Series": "Serie", "Number": "1", "Title": "Uno", "Writer": "Autor", "Year": "2001"}
    result = transfer(comic, fields, {"category": "USA"}, gcs, folders, log)
    assert isinstance(result, TransferResult) and result.item_id == 4
    assert result.image == gcs.parent / "comics" / "USA" / "Serie" / "Serie #01 - Portada.jpg"
    assert result.image.read_bytes() == jpeg(make_cover(1))
    assert result.backpic.read_bytes() == jpeg(make_cover(2))

    import xml.etree.ElementTree as ET
    root = ET.fromstring(gcs.read_text(encoding="utf-8"))
    added = root.findall("item")[-1]
    assert added.get("id") == "4" and added.get("series") == "Serie" and added.get("volume") == "1"
    assert added.get("category") == "USA" and added.get("file") == str(comic)
    assert added.get("image") == "comics/USA/Serie/Serie #01 - Portada.jpg"
    assert added.get("backpic") == "comics/USA/Serie/Serie #01 - Trasera.jpg"

    log_entry = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert log_entry["item_id"] == 4 and Path(log_entry["image"]) == result.image


def test_transfer_without_back_cover_and_without_a_matching_library_folder(scenario):
    comic, gcs, folders, log = scenario
    fields = {"Series": "Serie", "Number": "1"}
    result = transfer(comic, fields, {}, gcs, folders, log, include_back=False)
    assert result.image is not None and result.backpic is None

    lone = comic.parent / "Suelto.cbz"
    _comic(lone)
    result2 = transfer(lone, {"Series": "Suelto"}, {}, gcs, [], log)   # sin ninguna carpeta configurada
    assert result2.image is None and result2.backpic is None
    root_text = gcs.read_text(encoding="utf-8")
    assert 'file="' + str(lone) + '"' in root_text and "image=" not in root_text.splitlines()[-2]


def test_transfer_refuses_and_writes_nothing_if_gcstar_is_running(scenario, monkeypatch):
    comic, gcs, folders, log = scenario
    import comic_identify.gcstar as gcstar_module
    monkeypatch.setattr(gcstar_module, "is_running", lambda *a, **k: True)
    before = gcs.read_text(encoding="utf-8")
    with pytest.raises(GCstarError, match="abierto"):
        transfer(comic, {"Series": "Serie"}, {}, gcs, folders, log)
    assert gcs.read_text(encoding="utf-8") == before
    assert not log.exists()
    assert list((gcs.parent).rglob("*.jpg")) == []           # tampoco se creó ninguna portada


def test_transfer_rolls_back_the_cover_if_something_fails_afterwards(scenario, monkeypatch):
    comic, gcs, folders, log = scenario
    import comic_identify.gcstar as gcstar_module
    monkeypatch.setattr(gcstar_module, "build_item", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    before = gcs.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="boom"):
        transfer(comic, {"Series": "Serie"}, {}, gcs, folders, log)
    assert gcs.read_text(encoding="utf-8") == before
    assert list(gcs.parent.rglob("*.jpg")) == []


def test_undo_removes_the_item_and_the_images(scenario):
    comic, gcs, folders, log = scenario
    result = transfer(comic, {"Series": "Serie", "Number": "1"}, {}, gcs, folders, log)
    undo = undo_last(log)
    assert undo.removed is True and sorted(undo.images) == sorted(p for p in (result.image, result.backpic))
    assert not result.image.exists() and not result.backpic.exists()
    assert gcs.read_text(encoding="utf-8") == TEMPLATE
    with pytest.raises(LookupError):
        undo_last(log)


def test_undo_does_not_touch_an_image_that_changed_since_or_an_item_edited_by_hand(scenario):
    comic, gcs, folders, log = scenario
    result = transfer(comic, {"Series": "Serie", "Number": "1"}, {}, gcs, folders, log)
    result.image.write_bytes(b"otra cosa completamente distinta")
    edited = gcs.read_text(encoding="utf-8").replace('series="Serie"', 'series="Serie (editado a mano)"', 1)
    # solo se cambia la ÚLTIMA aparición (el item que acabamos de añadir), simulando una edición manual posterior
    last = gcs.read_text(encoding="utf-8").rindex('series="Serie"')
    edited = gcs.read_text(encoding="utf-8")[:last] + 'series="Serie (editado a mano)"' + \
        gcs.read_text(encoding="utf-8")[last + len('series="Serie"'):]
    gcs.write_text(edited, encoding="utf-8")

    undo = undo_last(log)
    assert undo.removed is False                          # el texto del item ya no coincide: no se toca
    assert result.image.read_bytes() == b"otra cosa completamente distinta"   # tampoco la portada modificada
    assert undo.skipped_images == [result.image]
    assert result.backpic in undo.images and not result.backpic.exists()     # esta sí seguía intacta
    assert gcs.read_text(encoding="utf-8") == edited


def test_is_isbn_accepts_isbns_and_rejects_magazine_barcodes():
    assert is_isbn("9788413346120") and is_isbn("978-84-1334-612-0") and is_isbn("8413346126") and is_isbn("843346120X")
    assert not is_isbn("977000559000400001")       # código de barras de una revista (ISSN), no un ISBN
    assert not is_isbn("") and not is_isbn("1234") and not is_isbn("9770005590004")


def test_isbn_and_cost_go_to_their_gcstar_fields_and_a_barcode_is_not_taken_for_an_isbn():
    base = {"Series": "X", "GTIN": "978-84-1334-612-0"}
    attrs = build_attrs(base, {"cost": "3,90 \u20ac"}, Path("/c/01.cbr"), 0, None, None, Path("/gcs"))
    assert attrs["isbn"] == "9788413346120" and attrs["cost"] == "3.90"
    magazine = build_attrs({"Series": "X", "GTIN": "977000559000400001"}, {}, Path("/c/01.cbr"), 0, None, None, Path("/gcs"))
    assert "isbn" not in magazine and "cost" not in magazine        # nada de meter ahí un código que no es un ISBN
    typed = build_attrs(base, {"isbn": " 1234567890 "}, Path("/c/01.cbr"), 0, None, None, Path("/gcs"))
    assert typed["isbn"] == "1234567890"                             # lo escrito a mano manda


def test_cost_text_keeps_only_a_real_number():
    assert cost_text("0.60") == "0.60" and cost_text("8") == "8" and cost_text(" 275,5 ptas ") == "275.5"
    assert cost_text("") == "" and cost_text("gratis") == "" and cost_text("1.2.3") == "" and isbn_text("", "") == ""


def test_format_from_comicinfo_reaches_the_gcstar_formato_field_via_the_dialog_value():
    attrs = build_attrs({"Series": "X", "Format": "Tomo tapa blanda"}, {"format": "Tomo tapa blanda"},
                        Path("/c/01.cbr"), 0, None, None, Path("/gcs"))
    assert attrs["format"] == "Tomo tapa blanda"
    assert "format" not in build_attrs({"Series": "X"}, {"format": ""}, Path("/c/01.cbr"), 0, None, None, Path("/gcs"))
