import io
import json
import sqlite3
import zlib
from contextlib import closing

import pytest

from comic_identify import umficha
from comic_identify import universomarvel as um
from comic_identify.umficha import Ficha, parse_ficha, parse_series_page
from comic_identify.universomarvel import (
    Entry,
    UniversoMarvelClient,
    UniversoMarvelError,
    UniversoMarvelIndex,
    build_index,
)

URL = "https://fichas.universomarvel.com/esp/aphff101.html"

# Ficha «antigua»: ancla de historia vacía, precio en pesetas con unidad, comentarios con <LI> sin cerrar.
OLD = """<HTML><HEAD><TITLE>	Alpha Flight vol.1 n\xba 1	- Forum	</TITLE></HEAD><BODY>
<TABLE><TR><TD><TABLE>
<TR><TD colspan="2"><A HREF="#" onClick="x()"><IMG SRC="portadas/aphff101.jpg"></A></TD></TR>
<TR><TH>Portada</TH></TR>
<TR><TD><SMALL><A HREF="../autores/byrnejohn.html">John Byrne</A></SMALL></TD></TR>
</TABLE></TD>
<TD><TABLE>
<TR><TH>Datos Generales</TH><TH>\xcdndice</TH></TR>
<TR><TD><TABLE BORDER="1">
<TR><TH COLSPAN="2"><A HREF="../fechases/1985e_mayo.html">Mayo 1985</A></TH></TR>
<TR><TH><B>	100 pts.	</B></TH><TH><B>	Color	</B></TH></TR>
<TR><TH COLSPAN="2"><B>	32 P\xe1ginas + cubiertas	</B></TH></TR>
</TABLE></TD>
<TD><OL><LI><A HREF="#1">Tundra</A> (30 p\xe1gs.)</OL></TD></TR>
<TR><TH colspan="2">Comentarios de la edici\xf3n</TH></TR>
<TR><TD colspan="2"><UL><LI>S\xf3lo incluye las primeras 30 p\xe1ginas.
<LI>Incluye un art\xedculo de <A HREF="../autores/byrnejohn.html">John Byrne</A> (2 p\xe1ginas)</LI></UL></TD></TR>
<TR><TD COLSPAN="2"><A NAME=""></A><TABLE BORDER="1">
<TR><TH colspan="6"><I>"Tundra"</I></TH></TR>
<TR><TH colspan="6">Equipo Creativo</TH></TR>
<TR><TH><SMALL>Rotulaci\xf3n</SMALL></TH><TH><SMALL>Traducci\xf3n</SMALL></TH></TR>
<TR><TD><I>Marcelino Hern\xe1ndez</I></TD><TD><A HREF="../autores/x.html">Francisco P\xe9rez Navarro</A></TD></TR>
<TR><TD colspan="6"><TABLE><TR><TH>Contenido USA</TH></TR>
<TR><TD><LI><A HREF="../usa/aphf1001.html">Alpha Flight vol.1 #1</A></LI></TD></TR></TABLE></TD></TR>
</TABLE></TD></TR></TABLE></TD></TR></TABLE></BODY></HTML>"""

# Ficha «moderna» (minúsculas, tomo con formato y medidas, precio suelto en euros, código de barras, dos historias).
NEW = """<html><head><title>\xa1Alerta! - Panini</title></head><body>
<table><tr><td><table><tr><td><a href="#"><img src="portadas/alertap.jpg"></a></td></tr>
<tr><th>Portada</th></tr>
<tr><td><small><A HREF="../autores/g.html">Patrick Gleason</A> - <A HREF="../autores/h.html">Morry Hollowell</A></small></td></tr>
<!--<tr><th>ISBN:-&nbsp;&nbsp;&nbsp;</th></tr>-->
<tr><th><small>ISBN:-&nbsp;&nbsp;&nbsp;&nbsp;</small></th></tr>
<tr><th><small>CB:977000559000400001</small></th></tr></table></td>
<td><table><tr><th>Datos Generales</th><th>\xcdndice</th></tr>
<tr><td><table>
<tr><th colspan="2"><a href="../fechases/2020e_junio.html">Junio 2020</a></th></tr>
<tr><th><b>Tomo tapa blanda</b></th><th><b>16,8 x 25,8 cm</b></th></tr>
<tr><th><b>Color</b></th><th><b>8 </b></th></tr>
<tr><th colspan="2"><b>96 P\xe1ginas + cubiertas</b></th></tr>
<tr><th colspan="2"><b>T\xedtulo del C\xf3mic</b></th></tr>
<tr><th colspan="2"><b><i>\xa1El futuro comienza aqu\xed!</i></b></th></tr>
</table></td>
<td><ol><li><a href="#1">\xa1Alerta!</a> (84 p\xe1gs.)</li><li><a href="#2">Extra</a> (12 p\xe1gs.)</li></ol></td></tr>
<tr><td colspan="2"><a name="1"></a><table>
<tr><th><i>"\xa1Alerta!"</i></th></tr><tr><th>Equipo Creativo</th></tr>
<tr><th><small>Rotulaci\xf3n</small></th><th><small>Traducci\xf3n</small></th></tr>
<tr><td><i>Norma Cuadrat</i> - <a href="x">Marina Ariza</a></td><td>Ra\xfal Sastre</td></tr>
<tr><td><table><tr><th>Contenido USA</th></tr><tr><td><li><a href="../usa/incoming.html">Incoming!</a></li></td></tr></table></td></tr>
</table></td></tr>
<tr><td colspan="2"><a name="2"></a><table>
<tr><th><i>"Extra"</i></th></tr><tr><th>Equipo Creativo</th></tr>
<tr><th>Rotulaci\xf3n</th><th>Traducci\xf3n</th></tr><tr><td>-</td><td>Ra\xfal Sastre</td></tr>
</table></td></tr></table></td></tr></table></body></html>"""

SERIE = """<HTML><BODY><CAPTION><b>ALPHA FLIGHT VOL.1 - FORUM</b></CAPTION><TABLE>
<TR><TD><A HREF="esp/aphff101.html">1</A></TD><TD><A HREF="esp/aphff102.html">2</A></TD></TR></TABLE>
<CAPTION><b>MARVEL TWO-IN-ONE VOL.1 - FORUM</b></CAPTION><TABLE>
<TR><TD><A HREF="esp/aphff139.html">39</A></TD></TR></TABLE>
<A HREF="forum.html"><IMG SRC="ima_gen/logoforum.jpg"></A><A HREF="aphff_v2.html"><IMG SRC="ima_gen/arrow21.gif"></A>
</BODY></HTML>"""


def _ficha(html, url=URL):
    return parse_ficha(um.decode(html.encode("cp1252")), url)


def test_old_template_ficha_is_read_completely():
    ficha = _ficha(OLD)
    assert (ficha.title, ficha.publisher) == ("Alpha Flight vol.1 n\xba 1", "Forum")
    assert (ficha.year, ficha.month, ficha.date_text) == (1985, 5, "Mayo 1985")
    assert (ficha.price_text, ficha.price, ficha.color, ficha.pages) == ("100 pts.", ("100", "pts"), "Color", 32)
    assert ficha.cover_image == "esp/portadas/aphff101.jpg" and ficha.cover_credits == "John Byrne"
    assert ficha.comments == ["S\xf3lo incluye las primeras 30 p\xe1ginas.", "Incluye un art\xedculo de John Byrne (2 p\xe1ginas)"]
    [story] = ficha.stories                                        # el ancla vacía no impide encontrar la historia
    assert (story.title, story.pages) == ("Tundra", "30 p\xe1gs.")
    assert story.credits == {"Rotulaci\xf3n": "Marcelino Hern\xe1ndez", "Traducci\xf3n": "Francisco P\xe9rez Navarro"}
    assert [(u.text, u.page) for u in story.usa] == [("Alpha Flight vol.1 #1", "usa/aphf1001.html")]


def test_modern_template_ficha_reads_format_price_barcode_and_ignores_commented_isbn():
    ficha = _ficha(NEW, "https://fichas.universomarvel.com/esp/alertap.html")
    assert ficha.publisher == "Panini" and ficha.title == "\xa1Alerta!"
    assert (ficha.year, ficha.month, ficha.pages) == (2020, 6, 96)
    assert ficha.format == "Tomo tapa blanda" and ficha.size == "16,8 x 25,8 cm"
    assert ficha.price == ("8", "€")                            # sin unidad y de 2020: euros
    assert ficha.comic_title == "\xa1El futuro comienza aqu\xed!"
    assert ficha.barcode == "977000559000400001" and ficha.isbn == ""    # el ISBN vacío no se toma por un dato
    assert ficha.cover_credits == "Patrick Gleason, Morry Hollowell"
    assert [s.title for s in ficha.stories] == ["\xa1Alerta!", "Extra"]
    assert [s.pages for s in ficha.stories] == ["84 p\xe1gs.", "12 p\xe1gs."]      # por orden, como el índice
    assert ficha.stories[1].credits == {"Traducci\xf3n": "Ra\xfal Sastre"}         # «-» es «desconocido», no un nombre


def test_credit_joins_roles_across_stories_without_repeating_and_splits_pairs():
    ficha = _ficha(NEW)
    assert ficha.credit("Rotulaci\xf3n") == "Norma Cuadrat, Marina Ariza"
    assert ficha.credit("Traducci\xf3n") == "Ra\xfal Sastre"          # aparece en las dos historias y sale una vez
    assert ficha.credit("Guion") == ""


def test_price_defaults_to_pesetas_before_2002_and_euros_after_and_handles_no_price():
    assert Ficha(price_text="275", year=1993).price == ("275", "pts")
    assert Ficha(price_text="3,90", year=2005).price == ("3,90", "€")
    assert Ficha(price_text="3,90 €", year=None).price == ("3,90", "€")
    assert Ficha().price == ("", "")


def test_a_page_that_is_not_a_ficha_yields_an_empty_one_and_never_raises():
    assert parse_ficha("<html><body>nada</body></html>", URL) == Ficha()
    assert parse_ficha("", URL) == Ficha()
    assert parse_ficha("<<<>>>&&&<table><tr><td>", URL).stories == []


def test_series_page_lists_issues_by_table_with_root_relative_paths():
    issues = parse_series_page(SERIE, "https://fichas.universomarvel.com/aphff_v1.html")
    assert [(i.group, i.label, i.page) for i in issues] == [
        ("ALPHA FLIGHT VOL.1 - FORUM", "1", "esp/aphff101.html"),
        ("ALPHA FLIGHT VOL.1 - FORUM", "2", "esp/aphff102.html"),
        ("MARVEL TWO-IN-ONE VOL.1 - FORUM", "39", "esp/aphff139.html")]      # los enlaces con imagen (navegación) no


@pytest.fixture
def client(tmp_path):
    pages = {"forum.html": OLD.encode("cp1252"), "aphff_v1.html": SERIE.encode("cp1252"),
             "esp/aphff101.html": OLD.encode("cp1252"), "esp/alertap.html": NEW.encode("cp1252")}
    calls = []

    def fetch(url):
        calls.append(url)
        return pages[url.replace(um.BASE, "")]
    index = UniversoMarvelIndex(tmp_path / "um.db")
    build_index(index.path, {"Forum/Planeta": "forum.html"}, lambda url: b'<H2>S</H2><option value="aphff_v1.html">Alpha Flight vol.1</option>')
    client = UniversoMarvelClient(index, fetch)
    client.calls = calls
    return client


def test_series_issues_and_ficha_are_downloaded_once_and_then_come_from_the_database(client):
    entry = Entry("Forum/Planeta", "S", "Alpha Flight vol.1", "aphff_v1.html")
    assert client.index.issues_of("aphff_v1.html") is None
    assert [i.label for i in client.series_issues(entry)] == ["1", "2", "39"]
    assert [i.label for i in client.series_issues(entry)] == ["1", "2", "39"]
    ficha = client.ficha("esp/aphff101.html")
    assert client.ficha("esp/aphff101.html") == ficha and ficha.year == 1985
    assert client.calls == [um.BASE + "aphff_v1.html", um.BASE + "esp/aphff101.html"]      # una petición por página


def test_find_issue_matches_numbers_ignoring_leading_zeros_and_single_issues_are_their_own(client):
    entry = Entry("Forum/Planeta", "S", "Alpha Flight vol.1", "aphff_v1.html")
    assert client.find_issue(entry, "01").page == "esp/aphff101.html"
    assert client.find_issue(entry, "39").page == "esp/aphff139.html"
    assert client.find_issue(entry, "99") is None
    single = Entry("Panini", "Especiales", "\xa1Alerta!", "esp/alertap.html")
    assert client.find_issue(single, "").page == "esp/alertap.html" and client.calls.count(single.url) == 0


def test_rebuilding_the_index_keeps_the_fichas_and_issue_lists_already_saved(client):
    client.ficha("esp/alertap.html")
    client.series_issues(Entry("Forum/Planeta", "S", "Alpha Flight vol.1", "aphff_v1.html"))
    build_index(client.index.path, {"Forum/Planeta": "forum.html"},
                lambda url: b'<H2>S</H2><option value="otra_v1.html">Otra vol.1</option>')
    assert [e.title for e in client.index.search("otra")] == ["Otra vol.1"] and client.index.search("alpha") == []
    assert client.index.get_ficha("esp/alertap.html").year == 2020
    assert client.index.issues_of("aphff_v1.html") is not None


def test_a_ficha_read_by_an_older_parser_is_reread_from_the_stored_html_without_the_web(client, monkeypatch):
    client.ficha("esp/alertap.html")
    with closing(sqlite3.connect(client.index.path)) as db, db:
        db.execute("UPDATE fichas SET parser_version = 0, data = ?", (json.dumps({"title": "vieja"}),))
    monkeypatch.setattr(um, "PARSER_VERSION", umficha.PARSER_VERSION)
    calls_before = len(client.calls)
    assert client.index.get_ficha("esp/alertap.html").price == ("8", "€")
    assert len(client.calls) == calls_before                         # sin volver a pedir nada al servidor
    with closing(sqlite3.connect(client.index.path)) as db:
        assert db.execute("SELECT parser_version FROM fichas").fetchone()[0] == umficha.PARSER_VERSION
        assert b"Incoming!" in zlib.decompress(db.execute("SELECT html FROM fichas").fetchone()[0])


def test_barcode_lookup_finds_saved_fichas_and_a_non_ficha_is_refused(client):
    client.ficha("esp/alertap.html")
    assert client.index.by_barcode("977 000559 000400001") == ["esp/alertap.html"]
    assert client.index.by_barcode("") == [] and client.index.by_barcode("123") == []
    bare = UniversoMarvelClient(client.index, lambda url: b"<html><body>sorpresa</body></html>")
    with pytest.raises(UniversoMarvelError, match="no parece una ficha"):
        bare.ficha("esp/rara.html")
    assert client.index.get_ficha("esp/rara.html") is None            # lo que no es una ficha no se guarda
    empty_series = UniversoMarvelClient(client.index, lambda url: b"<html></html>")
    with pytest.raises(UniversoMarvelError, match="ningún número"):
        empty_series.series_issues(Entry("P", "S", "Rara", "rara_v1.html"))


RANGES = """<HTML><BODY><CAPTION><b>SPIDERMAN VOL.1 - FORUM</b></CAPTION><TABLE><TR>
<TD><A HREF="spf1_100.html">1-100</A></TD><TD><A HREF="spf1_200.html">101-200</A></TD>
<TD><A HREF="spf1_esp.html">Especiales</A></TD><TD><A HREF="spf1_300.html">300</A></TD></TR></TABLE>
<A HREF="forum.html"><IMG SRC="ima_gen/logoforum.jpg"></A></BODY></HTML>"""


def test_range_index_pages_link_subpages_and_only_the_matching_range_is_chosen():
    subs = umficha.parse_series_subpages(RANGES, "https://fichas.universomarvel.com/spf_v1.html")
    assert [(s.label, s.page) for s in subs] == [("1-100", "spf1_100.html"), ("101-200", "spf1_200.html"),
                                                 ("Especiales", "spf1_esp.html"), ("300", "spf1_300.html")]
    assert [s.page for s in umficha.subpages_for(subs, "150")] == ["spf1_200.html"]
    assert [s.page for s in umficha.subpages_for(subs, "100")] == ["spf1_100.html"]     # los extremos cuentan
    assert [s.page for s in umficha.subpages_for(subs, "300")] == ["spf1_300.html"]     # un solo número
    assert umficha.subpages_for(subs, "999") == [] and umficha.subpages_for(subs, "Especial") == []


def test_a_long_series_downloads_only_the_subpage_that_holds_the_requested_number(tmp_path):
    pages = {"spf_v1.html": RANGES,
             "spf1_100.html": '<CAPTION><b>A</b></CAPTION><TABLE><TR><TD><A HREF="esp/spf101.html">1</A></TD></TR></TABLE>',
             "spf1_200.html": '<CAPTION><b>B</b></CAPTION><TABLE><TR><TD><A HREF="esp/spf1150.html">150</A></TD></TR></TABLE>'}
    calls = []

    def fetch(url):
        calls.append(url.replace(um.BASE, ""))
        return pages[calls[-1]].encode("cp1252")
    index = UniversoMarvelIndex(tmp_path / "um.db")
    build_index(index.path, {"F": "forum.html"}, lambda url: b'<H2>S</H2><option value="spf_v1.html">Spiderman vol.1</option>')
    entry = Entry("Forum/Planeta", "S", "Spiderman vol.1", "spf_v1.html")
    client = UniversoMarvelClient(index, fetch)
    assert client.find_issue(entry, "150").page == "esp/spf1150.html"
    assert calls == ["spf_v1.html", "spf1_200.html"]                       # la de 1-100 ni se pidió
    assert client.find_issue(entry, "150").page == "esp/spf1150.html" and len(calls) == 2    # ya en la base
    assert client.find_issue(entry, "1").page == "esp/spf101.html" and calls[-1] == "spf1_100.html"
    assert client.find_issue(entry, "777") is None and len(calls) == 3       # ningún rango lo contiene: sin red


def test_issue_candidate_carries_the_edition_data_and_feeds_normalization_and_metadata():
    from comic_identify.identify import marvel_issue_candidate
    from comic_identify.naming import FLAGS, suggest_values
    ficha = _ficha(NEW, "https://fichas.universomarvel.com/esp/alertap.html")
    ficha.title = "Alerta vol.2 n\xba 7"
    entry = Entry("Panini", "Series Regulares", "Alerta vol.2", "alerta_v2.html")
    issue = umficha.SeriesIssue("g", "7", "esp/alertap.html")
    candidate = marvel_issue_candidate(entry, issue, ficha)
    assert (candidate.title, candidate.number, candidate.year) == ("Alerta #7", "7", "2020")
    assert candidate.url == "https://fichas.universomarvel.com/esp/alertap.html"
    assert "Junio 2020" in candidate.subtitle and "96 p\xe1gs." in candidate.subtitle and "8 \u20ac" in candidate.subtitle
    assert candidate.extra["Month"] == "6" and candidate.extra["Year"] == "2020" and candidate.extra["Volume"] == "2"
    assert candidate.extra["Translator"] == "Ra\xfal Sastre" and candidate.extra["Letterer"] == "Norma Cuadrat, Marina Ariza"
    assert candidate.extra["CoverArtist"] == "Patrick Gleason, Morry Hollowell"
    assert candidate.extra["Format"] == "Tomo tapa blanda"                       # el formato de la ficha (si lo dice)
    assert candidate.extra["Web"] == candidate.url == "https://fichas.universomarvel.com/esp/alertap.html"   # la ficha del ejemplar
    assert candidate.extra["GTIN"] == "977000559000400001" and candidate.extra["Title"] == "\xa1El futuro comienza aqu\xed!"
    values = suggest_values(candidate)
    assert (values.nombre, values.volumen, values.bandera, values.edicion, values.numero) == (
        "Alerta", "2", FLAGS["es"], "2020", "7")
    assert (values.editorial, values.sello, values.contenido) == ("Panini Comics", "", "")   # el contenido lo pones tú


def test_issue_candidate_for_a_special_without_number_or_volume_uses_the_catalog_title():
    from comic_identify.identify import marvel_issue_candidate
    ficha = _ficha(NEW, "https://fichas.universomarvel.com/esp/alertap.html")
    candidate = marvel_issue_candidate(Entry("Panini", "Especiales", "\xa1Alerta!", "esp/alertap.html"),
                                       umficha.SeriesIssue("\xa1Alerta!", "", "esp/alertap.html"), ficha)
    assert candidate.title == "\xa1Alerta!" and candidate.number == "" and candidate.series == "\xa1Alerta!"


def test_translator_is_now_a_series_field_of_the_metadata_form():
    from comic_identify.metaform import SERIES_FIELDS, series_changes
    assert "Translator" in SERIES_FIELDS
    assert series_changes({"Translator": "  Ra\xfal Sastre "}, {})["Translator"] == "Ra\xfal Sastre"


def test_price_in_euros_converts_pesetas_at_the_official_rate_and_leaves_euros_alone():
    assert Ficha(price_text="100 pts.", year=1985).price_euros == "0.60"
    assert Ficha(price_text="275 ptas.", year=1993).price_euros == "1.65"
    assert Ficha(price_text="25", year=1971).price_euros == "0.15"
    assert Ficha(price_text="3,90 \u20ac", year=2005).price_euros == "3.90"
    assert Ficha(price_text="8", year=2020).price_euros == "8.00"
    assert Ficha().price_euros == "" and Ficha(price_text="gratis").price_euros == ""


def test_issue_candidate_offers_isbn_over_barcode_and_the_cost_in_euros():
    from comic_identify.identify import marvel_issue_candidate
    ficha = _ficha(NEW, "https://fichas.universomarvel.com/esp/alertap.html")
    entry, issue = Entry("Panini", "S", "\xa1Alerta!", "esp/alertap.html"), umficha.SeriesIssue("g", "", "esp/alertap.html")
    candidate = marvel_issue_candidate(entry, issue, ficha)
    assert candidate.extra["GTIN"] == "977000559000400001" and candidate.extra["ISBN"] == ""     # sin ISBN: el código de barras
    assert candidate.extra["Cost"] == "8.00"
    ficha.isbn = "9788413346120"
    assert marvel_issue_candidate(entry, issue, ficha).extra["GTIN"] == "9788413346120"          # con ISBN, este manda


def test_edition_notes_lists_usa_issues_with_links_then_the_edition_comments():
    ficha = _ficha(OLD)
    notes = umficha.edition_notes(ficha, "https://fichas.universomarvel.com/")
    assert notes == ("Contenido USA:\n"
                     "- Alpha Flight vol.1 #1: https://fichas.universomarvel.com/usa/aphf1001.html\n"
                     "Comentarios de la edici\xf3n:\n"
                     "- S\xf3lo incluye las primeras 30 p\xe1ginas.\n"
                     "- Incluye un art\xedculo de John Byrne (2 p\xe1ginas)")


def test_edition_notes_dedupes_repeated_usa_issues_and_is_empty_when_there_is_nothing():
    ficha = _ficha(NEW)
    ficha.stories[1].usa = list(ficha.stories[0].usa)                       # dos historias que citan el mismo original
    assert umficha.edition_notes(ficha, "https://h/").count("Incoming!") == 1
    assert umficha.edition_notes(Ficha(), "https://h/") == ""
    assert umficha.edition_notes(Ficha(comments=["Solo esto"]), "https://h/") == "Comentarios de la edici\xf3n:\n- Solo esto"


def test_issue_candidate_carries_the_notes_block():
    from comic_identify.identify import marvel_issue_candidate
    ficha = _ficha(OLD)
    candidate = marvel_issue_candidate(Entry("Forum/Planeta", "S", "Alpha Flight vol.1", "aphff_v1.html"),
                                       umficha.SeriesIssue("g", "1", "esp/aphff101.html"), ficha)
    assert candidate.extra["NotesBlock"].startswith("Contenido USA:\n- Alpha Flight vol.1 #1: https://")


def _usa_story(title, credits, spanish, synopsis="-"):
    heads = "".join(f"<TH><SMALL>{role}</SMALL></TH>" for role in credits)
    values = "".join(f"<TD>{name}</TD>" for name in credits.values())
    links = "".join(f'<LI><A HREF="../{page}">Edici\xf3n</A> - <A HREF="../panini.html">Panini</A> (1\xaa Historia)' for page in spanish)
    return f"""<TR><TD COLSPAN="2"><A NAME="1"></A><TABLE>
<TR><TH colspan="6"><I>"{title}"</I></TH></TR><TR><TH>Equipo Creativo</TH></TR>
<TR>{heads}</TR><TR>{values}</TR>
<TR><TH>Detalles</TH></TR><TR><TD>x</TD></TR>
<TR><TH>Sinopsis</TH></TR><TR><TD>{synopsis}</TD></TR>
<TR><TH>Ediciones Espa\xf1olas</TH><TH>Reimpresiones</TH></TR>
<TR><TD>{links}</TD><TD><LI><A HREF="otra.html">Reedici\xf3n</A></TD></TR>
</TABLE></TD></TR>"""


USA = ("""<HTML><HEAD><TITLE>Two-Gun Kid vol.1 n\xba 60</TITLE></HEAD><BODY><TABLE><TR><TD><TABLE>
<TR><TH>Datos Generales</TH><TH>\xcdndice</TH></TR>
<TR><TD><TABLE><TR><TH><A HREF="../fechas/1962_noviembre.html">Noviembre 1962</A></TH></TR>
<TR><TH><B>12\xa2</B></TH></TR></TABLE></TD><TD></TD></TR>""" +
       _usa_story("Uno", {"Argumento": "Stan Lee - Larry Lieber", "Gui\xf3n": "Stan Lee", "L\xe1piz": "Jack Kirby",
                          "Tinta": "Dick Ayers", "Color": "Stan Goldberg", "Rotulaci\xf3n": "Artie Simek"},
                  ["esp/2piskidv101.html", "esp/otro.html"], "Una sinopsis larga.") +
       _usa_story("Dos", {"Gui\xf3n": "Stan Lee", "L\xe1piz": "Don Heck", "Tinta": "Don Heck", "Color": "Stan Goldberg"},
                  ["esp/2piskidv103.html"]) + "</TABLE></TD></TR></TABLE></BODY></HTML>")
USA_URL = "https://fichas.universomarvel.com/usa/twogk1060.html"


def test_usa_ficha_reads_cover_date_credits_spanish_editions_and_synopsis():
    ficha = _ficha(USA, USA_URL)
    assert (ficha.year, ficha.month, ficha.date_text) == (1962, 11, "Noviembre 1962")      # «fechas/», no «fechases/»
    one, two = ficha.stories
    assert one.credits["Argumento"] == "Stan Lee - Larry Lieber" and one.credits["Gui\xf3n"] == "Stan Lee"
    assert (one.spanish, two.spanish) == (["esp/2piskidv101.html", "esp/otro.html"], ["esp/2piskidv103.html"])
    assert one.synopsis == "Una sinopsis larga." and two.synopsis == ""                    # «-» es «sin sinopsis»


def _usa_client(tmp_path, pages):
    calls = []

    def fetch(url):
        calls.append(url.replace(um.BASE, ""))
        page = pages.get(calls[-1])
        if page is None:
            raise UniversoMarvelError("HTTP Error 404: Not Found")
        return page.encode("cp1252")
    index = UniversoMarvelIndex(tmp_path / "um.db")
    build_index(index.path, {"F": "forum.html"}, lambda url: b'<H2>S</H2><option value="a_v1.html">A vol.1</option>')
    client = UniversoMarvelClient(index, fetch)
    client.calls = calls
    return client


def test_usa_info_keeps_only_the_stories_that_link_to_this_edition(tmp_path):
    client = _usa_client(tmp_path, {"usa/twogk1060.html": USA})
    only_two = client.usa_info([("usa/twogk1060.html", "Two-Gun Kid #60")], "esp/2piskidv103.html")
    assert only_two.credits == {"Writer": "Stan Lee", "Penciller": "Don Heck", "Inker": "Don Heck", "Colorist": "Stan Goldberg"}
    assert only_two.years == [1962] and only_two.missing == [] and only_two.approximate == []
    only_one = client.usa_info([("usa/twogk1060.html", "Two-Gun Kid #60")], "esp/2piskidv101.html")
    assert only_one.credits["Writer"] == "Stan Lee, Larry Lieber"     # el argumento cuenta como guion, sin repetir a Stan Lee
    assert only_one.credits["Penciller"] == "Jack Kirby"
    assert client.calls == ["usa/twogk1060.html"]                     # una sola descarga: la segunda vez sale de la base


def test_usa_info_falls_back_to_all_stories_and_says_so_when_the_edition_is_not_linked(tmp_path):
    client = _usa_client(tmp_path, {"usa/twogk1060.html": USA})
    info = client.usa_info([("usa/twogk1060.html", "Two-Gun Kid #60")], "esp/no-enlazada.html")
    assert info.credits["Penciller"] == "Jack Kirby, Don Heck" and info.approximate == ["Two-Gun Kid #60"]


def test_usa_info_survives_broken_links_and_merges_several_originals_without_repeats(tmp_path):
    client = _usa_client(tmp_path, {"usa/twogk1060.html": USA})
    refs = [("usa/twogk1060.html", "A"), ("usa/roto.html", "Incoming!"), ("usa/twogk1060.html", "A otra vez")]
    info = client.usa_info(refs, "esp/2piskidv101.html", progress=(seen := []).append)
    assert info.missing == ["Incoming!"] and info.credits["Penciller"] == "Jack Kirby"
    assert len(seen) == 2 and "Incoming!" in seen[1]                  # una l\xednea de progreso por original distinto
    nothing = client.usa_info([("usa/roto.html", "X")], "esp/y.html")
    assert nothing.credits == {"Writer": "", "Penciller": "", "Inker": "", "Colorist": ""} and nothing.years == []


def test_split_names():
    assert umficha.split_names("Fiona Avery - J. Michael Straczynski") == ["Fiona Avery", "J. Michael Straczynski"]
    assert umficha.split_names("A, B y C") == ["A", "B", "C"] and umficha.split_names("-") == [] and umficha.split_names("") == []


def test_issue_candidate_lists_its_usa_originals_and_the_spanish_page_for_the_credits_lookup():
    from comic_identify.identify import marvel_issue_candidate
    candidate = marvel_issue_candidate(Entry("Forum/Planeta", "S", "Alpha Flight vol.1", "aphff_v1.html"),
                                       umficha.SeriesIssue("g", "1", "esp/aphff101.html"), _ficha(OLD))
    assert json.loads(candidate.extra["UsaRefs"]) == [["usa/aphf1001.html", "Alpha Flight vol.1 #1"]]
    assert candidate.extra["SpanishPage"] == "esp/aphff101.html"


def test_usa_info_gives_one_line_per_matching_story_with_who_did_what(tmp_path):
    client = _usa_client(tmp_path, {"usa/twogk1060.html": USA})
    lines = client.usa_info([("usa/twogk1060.html", "Two-Gun Kid vol.1 #60")], "esp/2piskidv101.html").story_lines
    assert lines == [("- \xabUno\xbb (Two-Gun Kid vol.1 #60): Argumento Stan Lee, Larry Lieber \xb7 Gui\xf3n Stan Lee \xb7 "
                      "L\xe1piz Jack Kirby \xb7 Tinta Dick Ayers \xb7 Color Stan Goldberg")]   # la rotulaci\xf3n USA no cuenta
    both = client.usa_info([("usa/twogk1060.html", "Two-Gun Kid vol.1 #60")], "esp/desconocida.html").story_lines
    assert [line.split("\xbb")[0] for line in both] == ["- \xabUno", "- \xabDos"]                   # aproximado: todas las historias
    assert "Argumento" not in both[1] and "L\xe1piz Don Heck" in both[1]


def test_compose_notes_orders_usa_credits_and_comments_and_skips_empty_parts():
    usa, comments = "Contenido USA:\n- A: https://x/a", "Comentarios de la edici\xf3n:\n- algo"
    assert umficha.compose_notes(usa, ["- L1", "- L2"], comments) == (
        "Contenido USA:\n- A: https://x/a\nCr\xe9ditos por historia (USA):\n- L1\n- L2\nComentarios de la edici\xf3n:\n- algo")
    assert umficha.compose_notes(usa, [], comments) == usa + "\n" + comments       # sin desglose: como antes
    assert umficha.compose_notes("", [], "") == ""
    ficha = _ficha(OLD)
    assert umficha.edition_notes(ficha, "https://h/", ["- L"]).index("Cr\xe9ditos") < umficha.edition_notes(
        ficha, "https://h/", ["- L"]).index("Comentarios")


def test_append_block_refreshes_a_previous_block_but_never_touches_hand_written_text():
    from comic_identify.metaform import append_block
    old = "Contenido original: 1983\nContenido USA:\n- A: https://x/a\nComentarios de la edici\xf3n:\n- algo"
    new = ("Contenido USA:\n- A: https://x/a\nCr\xe9ditos por historia (USA):\n- L1\nComentarios de la edici\xf3n:\n- algo")
    refreshed = append_block(old, new)
    assert refreshed == "Contenido original: 1983\n" + new                        # el bloque viejo se sustituye, no se duplica
    assert append_block(refreshed, new) == refreshed                              # y repetirlo no cambia nada
    written_after = old + "\nMi nota al final"
    assert append_block(written_after, new) == written_after                     # hay algo tuyo debajo: no se toca
    assert append_block("Solo mi nota", new) == "Solo mi nota\n" + new


def test_attach_cover_gives_a_thumbnail_and_the_same_kind_of_similarity_as_comicvine(tmp_path):
    from conftest import jpeg, make_cover

    from comic_identify.identify import Candidate, attach_cover
    mine = tmp_path / "mia.jpg"
    mine.write_bytes(jpeg(make_cover(1)))
    same, other = Candidate("a", "Universo Marvel"), Candidate("b", "Universo Marvel")
    attach_cover(same, jpeg(make_cover(1), quality=30), mine)          # la misma portada, otra calidad de imagen
    attach_cover(other, jpeg(make_cover(2)), mine)
    assert same.similarity > 0.9 and same.is_match and same.cover                # «Coincidencia probable»
    assert other.similarity < 0.75 and not other.is_match and other.cover        # «Poco parecida»


def test_attach_cover_without_an_open_comic_or_with_bad_data_never_raises(tmp_path):
    from conftest import jpeg, make_cover

    from comic_identify.identify import Candidate, attach_cover
    lonely = Candidate("a", "Universo Marvel")
    attach_cover(lonely, jpeg(make_cover(1)), None)
    assert lonely.similarity is None and lonely.cover                              # sin portada abierta: solo la miniatura
    broken = Candidate("b", "Universo Marvel")
    attach_cover(broken, b"no soy una imagen", tmp_path / "no-existe.jpg")
    assert broken.similarity is None and broken.cover is None
    unreadable = tmp_path / "rota.jpg"
    unreadable.write_bytes(b"tampoco")
    fine = Candidate("c", "Universo Marvel")
    attach_cover(fine, jpeg(make_cover(1)), unreadable)
    assert fine.similarity is None and fine.cover                                  # la portada abierta no se puede leer


def test_client_downloads_a_cover_once_and_refuses_what_is_not_an_image(tmp_path):
    from conftest import jpeg, make_cover
    data = jpeg(make_cover(3))
    calls = []

    def fetch(url):
        calls.append(url)
        return data if url.endswith("ok.jpg") else b"<html>no soy una imagen</html>"
    index = UniversoMarvelIndex(tmp_path / "um.db")
    build_index(index.path, {"F": "forum.html"}, lambda url: b'<H2>S</H2><option value="a_v1.html">A vol.1</option>')
    client = UniversoMarvelClient(index, fetch)
    stored = client.cover("esp/portadas/ok.jpg")
    assert client.cover("esp/portadas/ok.jpg") == stored
    assert calls == [um.BASE + "esp/portadas/ok.jpg"]                              # una sola petici\xf3n
    from PIL import Image

    from comic_identify.hashing import dhash_bytes, dhash_variants, similarity
    with Image.open(io.BytesIO(stored)) as small, Image.open(io.BytesIO(data)) as big:
        assert max(small.size) <= um.COVER_SIDE < max(big.size)                    # se guarda reducida
        assert similarity(dhash_variants(big), dhash_bytes(stored)) > 0.95         # y la huella sigue siendo la misma
    assert len(stored) < len(data)
    with pytest.raises(UniversoMarvelError, match="no es una imagen"):
        client.cover("esp/portadas/mala.jpg")
    assert index.get_cover("esp/portadas/mala.jpg") is None                       # lo que no es una imagen no se guarda


def test_a_database_created_before_covers_existed_gets_the_table_when_first_needed(tmp_path):
    index = UniversoMarvelIndex(tmp_path / "um.db")
    build_index(index.path, {"F": "forum.html"}, lambda url: b'<H2>S</H2><option value="a_v1.html">A vol.1</option>')
    with closing(sqlite3.connect(index.path)) as db, db:
        db.execute("DROP TABLE covers")
    assert index.get_cover("esp/portadas/x.jpg") is None
    index.store_cover("esp/portadas/x.jpg", b"datos")
    assert index.get_cover("esp/portadas/x.jpg") == b"datos"


def test_usa_info_summary_is_the_synopsis_of_the_matching_stories(tmp_path):
    client = _usa_client(tmp_path, {"usa/twogk1060.html": USA})
    one = client.usa_info([("usa/twogk1060.html", "T #60")], "esp/2piskidv101.html")
    assert one.summary == "Una sinopsis larga."                      # una sola historia: su texto tal cual
    empty = client.usa_info([("usa/twogk1060.html", "T #60")], "esp/2piskidv103.html")
    assert empty.summary == ""                                        # su sinopsis es «-»: no se inventa nada
    several = client.usa_info([("usa/twogk1060.html", "T #60")], "esp/desconocida.html")
    assert several.summary == "\xabUno\xbb: Una sinopsis larga."         # varias historias: con t\xedtulo, en una l\xednea
    assert "\n" not in several.summary


@pytest.mark.parametrize("color, expected", [("Color", "No"), ("Tricolor", "No"), ("Blanco y Negro", "Yes"), ("B/N", "Yes"),
                                            ("Bicolor", ""), ("", "")])
def test_black_and_white_follows_the_ficha_colour_word(color, expected):
    assert Ficha(color=color).black_and_white == expected
