import pytest

from comic_identify import tbficha
from comic_identify.metaform import append_block
from comic_identify.tbficha import (
    TbFicha,
    parse_date,
    parse_ficha,
    role_fields,
    slug_title,
    smart_title,
)

URL = "https://www.tebeosfera.com/numeros/daredevil_2019_panini_67.html"


def page(price='<span title="EURO (EUR)" class="flecha">3.30<strong>&nbsp;€</strong></span>', color="COLOR (portada, interior)",
         registros="ISBN: 977293854800800020 ISSN: 2938-5482 Dep. Legal: GI 1263-2023", lengua="Traducción del inglés",
         title='<span>DAREDEVIL</span><br><span>EL HOMBRE SIN MIEDO</span><br>RITOS DE RECONCILIACIÓN',
         line=('<a href="/entidades/grupo_planeta.html">Grupo Planeta</a> : <a href="/entidades/planeta_deagostini.html">'
               'Planeta DeAgostini</a> <strong> · </strong> <a href="/entidades/forum.html">forum</a> '
               '<strong> · </strong> <span>Barcelona</span> <strong> · </strong> <img title="España" src="x.png" />')):
    """Una ficha con la estructura de las reales (etiqueta/dato, autores por rol, pestañas, texto libre), inventada."""
    return f"""<html><head>
<meta property="og:title" content="DAREDEVIL (2019, PANINI) 67" />
<meta property="og:image" content="https://www.tebeosfera.com/T3content/img/T3_numeros/x/y/portada.jpeg" />
</head><body>
<div id="titulo_ficha"><div class="titulo">{title}</div><div class="subtitulo"></div></div>
<input type="hidden" id="NUMERO_RUTA" name="NUMERO_RUTA" value = "daredevil_2019_panini_67" />
<div id="cuerpo2_ficha" class="row-fluid">
<div class="row-fluid dato"><strong><span>Nº</span></strong> 67 <strong>de</strong> <span><a href="/colecciones/daredevil_2019_panini.html">DAREDEVIL</a></span>&nbsp;<span>[de 74]</span></div>
<div class="row-fluid">{line}</div>
<div class="row-fluid"><div class="span3 etiqueta">Distribución:</div><div class="span9 dato"><span>SD DISTRIBUCIONES</span><strong> · </strong><span>14-VIII-2025 <i class="t3icon-pregunta ttip_t" title="Esta fecha ha sido aproximada."></i></span> <strong> · </strong> {price}</div></div>
<div class="row-fluid"><div class="span3 etiqueta">Edición:</div><div class="span9 dato"><a>NUEVA</a>&nbsp;·&nbsp;<a>TEBEO</a></div></div>
<div class="row-fluid"><div class="span3 etiqueta">Origen:</div><div class="span9 dato">Daredevil Vol 8 : Marvel</div></div>
<div class="row-fluid"><div class="span3 etiqueta">Lengua:</div><div class="span9 dato">{lengua}</div></div>
<div class="row-fluid"><div class="span3 etiqueta">Formato:</div><div class="span9 dato"><a>CUADERNO</a> <strong> · </strong> <a>GRAPA</a></div></div>
<div class="row-fluid"><div class="span3 etiqueta">Tamaño:</div><div class="span9 dato">25,8 x 16,8 cm</div></div>
<div class="row-fluid"><div class="span3 etiqueta">Paginación:</div><div class="span9 dato">28 págs. más cubiertas</div></div>
<div class="row-fluid"><div class="span3 etiqueta">Color:</div><div class="span9 dato">{color}</div></div>
<div class="row-fluid"><div class="span3 etiqueta">Registros:</div><div class="span9 dato">{registros}</div></div>
<div class="row-fluid"><div class="span3 etiqueta">Ediciones:</div><div class="span9 dato">Antes, en <a>DAREDEVIL (2011, PANINI) 5</a> <a>DAREDEVIL (2011, PANINI) 6</a> Luego, en <a>DAREDEVIL (2019, PANINI) -TOMO- 1</a></div></div>
<div class="row-fluid"><div class="span3 etiqueta">Autores:</div><div class="span9 dato">
<div class="row-fluid tab_datos"><span class="tab_subtitulo">Guionista <span class="peque">1</span></span>: <a>SALADIN AHMED</a></div>
<div class="row-fluid tab_datos"><span class="tab_subtitulo">Dibujantes <span class="peque">2</span></span>: <a>CHRIS GIARRUSSO</a><strong>, </strong><a>TODD NAUCK</a></div>
<div class="row-fluid tab_datos"><span class="tab_subtitulo">Entintador <span class="peque">1</span></span>: <a>OREN JUNIOR</a></div>
<div class="row-fluid tab_datos"><span class="tab_subtitulo">Colorista <span class="peque">1</span></span>: <a>JESÚS ABURTOV</a></div>
<div class="row-fluid tab_datos"><span class="tab_subtitulo">Rotulista <span class="peque">1</span></span>: <a>NORMA CUADRAT</a></div>
<div class="row-fluid tab_datos"><span class="tab_subtitulo">Traductor <span class="peque">1</span></span>: <a>GONZALO QUESADA</a></div>
<div class="row-fluid tab_datos"><span class="tab_subtitulo">Portadistas <span class="peque">2</span></span>: <a>JOHN ROMITA JR.</a><strong>, </strong><a>SCOTT HANNA</a></div>
<div class="row-fluid tab_datos"><span class="tab_subtitulo">Editor <span class="peque">1</span></span>: <a>JULIÁN M. CLEMENTE</a></div>
<div class="row-fluid tab_datos"><span class="tab_subtitulo">Correctores <span class="peque">1</span></span>: <a>BRUNO ORIVE</a></div>
</div></div></div>
<div class="tabbable clearfix"><ul class="nav nav-tabs"><li><a href="#tab1" data-toggle="tab">SAGAS&nbsp;<span class="peque">1</span></a></li><li><a href="#tab2" data-toggle="tab">GÉNEROS&nbsp;<span class="peque">2</span></a></li></ul>
<div class="tab-content"><div class="tab-pane active" id="tab1"><p><div><a href="/sagas/daredevil.html">Daredevil</a></div></p></div>
<div class="tab-pane" id="tab2"><p><a>Acción</a>, <a>Superhéroes</a></p></div></div></div>
<div class="row-fluid T3WISIWISI"><p>Cuaderno grapado de 24 páginas en color más cubiertas.</p><p>- Contiene el número 20 original.</p></div>
</body></html>"""


def test_smart_title_only_touches_all_caps_text():
    assert smart_title("UNIVERSO DC") == "Universo DC"
    assert smart_title("MARVEL SAGA: EL ASOMBROSO SPIDERMAN") == "Marvel Saga: El Asombroso Spiderman"
    assert smart_title("J. J. BIRCH") == "J. J. Birch"
    assert smart_title("MCFARLANE") == "McFarlane" and smart_title("TOM DEFALCO") == "Tom Defalco"
    assert smart_title("TOMO II") == "Tomo II"                       # cifras romanas
    assert smart_title("La Guerra Màgica") == "La Guerra Màgica"     # ya trae minúsculas: se respeta
    assert smart_title("") == "" and smart_title("2019") == "2019"


@pytest.mark.parametrize("text, expected", [
    ("XII-1989", (1989, 12, None)), ("14-VIII-2025", (2025, 8, 14)), ("6-III-2026", (2026, 3, 6)), ("2019", (2019, None, None)),
    ("VII-VIII-1990", (1990, 7, None)), ("", (None, None, None)), ("sin fecha", (None, None, None))])
def test_parse_date_reads_roman_months(text, expected):
    assert parse_date(text) == expected


def test_roles_map_to_comicinfo_fields_in_any_number_and_gender():
    assert role_fields("Guionistas") == ("Writer",) and role_fields("Historietista") == ("Writer", "Penciller")
    assert role_fields("Entintadora") == ("Inker",) and role_fields("Portadistas") == ("CoverArtist",)
    assert role_fields("Rotulista") == ("Letterer",) and role_fields("Traductores") == ("Translator",)
    assert role_fields("Corrector") == ()


def test_slug_title_reads_year_publisher_and_subtitle_from_the_address():
    assert slug_title("universo_dc_1989_zinco") == ("Universo DC", "1989", "Zinco", "")
    assert slug_title("batman_2019_ovni_press_-coleccion_80_aniversario-") == (
        "Batman", "2019", "Ovni Press", "Coleccion 80 Aniversario")
    assert slug_title("spiderman_1983_forum_planeta-deagostini") == ("Spiderman", "1983", "Forum Planeta-Deagostini", "")
    assert slug_title("el_hombre_de_acero") == ("El Hombre de Acero", "", "", "")


def test_a_ficha_is_read_completely():
    ficha = parse_ficha(page(), URL)
    assert (ficha.series, ficha.issue_title) == ("Daredevil", "El Hombre Sin Miedo - Ritos de Reconciliación")
    assert (ficha.number, ficha.count, ficha.collection_slug, ficha.slug) == ("67", 74, "daredevil_2019_panini",
                                                                              "daredevil_2019_panini_67")
    assert ficha.collection_title == "DAREDEVIL (2019, PANINI)"
    assert (ficha.group, ficha.publisher, ficha.imprint, ficha.city) == ("Grupo Planeta", "Planeta DeAgostini", "Forum", "Barcelona")
    assert (ficha.year, ficha.month, ficha.day, ficha.approximate_date) == (2025, 8, 14, True)
    assert ficha.date_label == "14 de agosto de 2025 (aprox.)" and ficha.distributor == "Sd Distribuciones"
    assert (ficha.price, ficha.price_label, ficha.price_euros) == (("3.30", "€"), "3.30 €", "3.30")
    assert (ficha.language, ficha.format, ficha.pages, ficha.size) == ("es", "Cuaderno, Grapa", 28, "25,8 x 16,8 cm")
    assert ficha.origin == "Daredevil Vol 8 : Marvel" and ficha.edition == "NUEVA · TEBEO"
    assert (ficha.isbn, ficha.gtin, ficha.issn, ficha.legal_deposit) == ("", "977293854800800020", "2938-5482", "GI 1263-2023")
    assert ficha.credits == {"Writer": "Saladin Ahmed", "Penciller": "Chris Giarrusso, Todd Nauck", "Inker": "Oren Junior",
                             "Colorist": "Jesús Aburtov", "Letterer": "Norma Cuadrat", "Translator": "Gonzalo Quesada",
                             "CoverArtist": "John Romita Jr., Scott Hanna", "Editor": "Julián M. Clemente"}
    assert ficha.other_credits == {"Correctores": "Bruno Orive"}
    assert (ficha.genres, ficha.sagas) == (["Acción", "Superhéroes"], ["Daredevil"])
    assert ficha.comments == ["Cuaderno grapado de 24 páginas en color más cubiertas.", "Contiene el número 20 original."]
    assert ficha.cover_image == "https://www.tebeosfera.com/T3content/img/T3_numeros/x/y/portada.jpeg"
    assert ficha.related == ["Antes, en: Daredevil (2011, Panini) 5; Daredevil (2011, Panini) 6",
                             "Luego, en: Daredevil (2019, Panini) -Tomo- 1"]


def test_pesetas_are_converted_and_other_currencies_are_not():
    pts = parse_ficha(page(price='<span title="PESETA (PTA)" class="flecha">1.200<strong>&nbsp;pts.</strong></span>'), URL)
    assert (pts.price, pts.price_label, pts.price_euros) == (("1200", "pts"), "1200 pts.", "7.21")
    pesos = parse_ficha(page(price='<span title="PESO ARGENTINO (ARS)">12000,00<strong>&nbsp;$</strong></span>'), URL)
    assert (pesos.price_amount, pesos.price_currency, pesos.price_euros) == ("12000.00", "ARS", "")
    assert parse_ficha(page(price=""), URL).price_euros == ""


@pytest.mark.parametrize("color, expected", [
    ("COLOR (portada, interior)", "No"), ("COLOR (portada) B/N (interior)", "Yes"), ("B/N (portada, interior)", "Yes"),
    ("BICOLOR (interior)", ""), ("", "")])
def test_black_and_white_follows_the_interior(color, expected):
    assert TbFicha(color_text=color).black_and_white == expected


def test_isbn_and_language_variants():
    real = parse_ficha(page(registros="ISBN: 978-84-679-7627-4", lengua="Traducción del japonés al catalán"), URL)
    assert (real.isbn, real.gtin, real.language) == ("9788467976274", "", "ca")
    assert parse_ficha(page(lengua="Original en castellano"), URL).language == "es"
    assert parse_ficha(page(lengua=""), URL).language == ""


def test_a_page_that_is_not_a_ficha_gives_an_empty_one():
    assert parse_ficha("<html><body>404</body></html>", URL).series == ""


def test_notes_block_is_refreshed_by_metaform_and_keeps_what_the_user_wrote():
    ficha = parse_ficha(page(), URL)
    block = tbficha.edition_notes(ficha)
    assert block.splitlines()[0] == "Datos de la edición (Tebeosfera):" and "- Origen: Daredevil Vol 8 : Marvel" in block
    assert "- Correctores: Bruno Orive" in block and "Ediciones relacionadas (Tebeosfera):" in block
    assert "Comentarios de la edición:" in block
    once = append_block("Mi nota", block)
    assert append_block(once, block) == once                       # no se repite: se refresca
    assert append_block(once + "\ny algo más mío", block).endswith("y algo más mío")   # lo escrito a mano no se toca
