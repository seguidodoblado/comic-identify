import sqlite3
from contextlib import closing

import pytest

from comic_identify.gcd import GcdIndex, IssueDetails, build_index, credit_roles


@pytest.fixture
def rich_dump(dump):
    """El volcado mínimo de siempre más historias, créditos (modelo nuevo de GCD), reimpresiones, precio y fecha de venta."""
    with closing(sqlite3.connect(dump)) as db, db:
        db.executescript("""
        ALTER TABLE gcd_issue ADD COLUMN price TEXT;
        ALTER TABLE gcd_issue ADD COLUMN on_sale_date TEXT;
        CREATE TABLE gcd_story (id INTEGER, issue_id INTEGER, sequence_number INTEGER, type_id INTEGER, title TEXT,
            genre TEXT, characters TEXT, synopsis TEXT, deleted INTEGER);
        CREATE TABLE gcd_credit_type (id INTEGER, name TEXT);
        CREATE TABLE gcd_creator (id INTEGER, gcd_official_name TEXT, deleted INTEGER);
        CREATE TABLE gcd_creator_name_detail (id INTEGER, creator_id INTEGER);
        CREATE TABLE gcd_story_credit (id INTEGER, story_id INTEGER, credit_type_id INTEGER, creator_id INTEGER,
            credit_name TEXT, deleted INTEGER);
        CREATE TABLE gcd_reprint (id INTEGER, origin_id INTEGER, target_id INTEGER);
        UPDATE gcd_issue SET price = '3.50 EUR; 4.00 USD', on_sale_date = '2006-12-21' WHERE id = 100;
        INSERT INTO gcd_credit_type VALUES (1, 'script'), (2, 'pencils'), (3, 'inks'), (4, 'colors'), (5, 'letters'),
            (6, 'editing'), (7, 'pencils and inks'), (9, 'painting');
        INSERT INTO gcd_creator VALUES (1, 'Tim Bradstreet', 0), (2, 'Garth Ennis', 0), (3, 'Lewis LaRosa', 0),
            (4, 'Tom Palmer', 0), (5, 'Dean White', 0), (6, 'Randolph Gentile', 0), (7, 'Axel Alonso', 0),
            (8, 'Grant Goleash', 0), (9, 'Autor Borrado', 1), (10, 'Otro Guionista', 0), (11, 'Anunciante', 0), (12, 'Sofía Traductora', 0);
        INSERT INTO gcd_creator_name_detail VALUES (1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7), (8, 8), (9, 9),
            (10, 10), (11, 11), (12, 12);
        -- número 100: portada, dos historias de autores distintos, un anuncio
        INSERT INTO gcd_story VALUES
          (1, 100, 0, 6, '', 'crime; superhero', 'Punisher [Frank Castle]', '', 0),
          (2, 100, 1, 19, 'Uno', 'crime; superhero; noir', 'Punisher [Frank Castle]; Micro; ?', 'Micro se une a la operación.', 0),
          (3, 100, 2, 19, 'Dos', 'crime', 'Micro; Roth', '', 0),
          (4, 100, 3, 2, 'Anuncio', '', '', '', 0),
          (5, 100, 4, 19, 'Borrada', 'horror', '', '', 1),
          (6, 101, 1, 19, 'Sin créditos propios', '', '', '', 0),
          (7, 103, 1, 19, 'Sin nada', '', '', '', 0),
          (50, 999, 1, 19, 'Original americano', '', '', '', 0);
        INSERT INTO gcd_story_credit VALUES
          (1, 1, 2, 1, '', 0), (2, 1, 3, 1, '', 0), (3, 1, 4, 8, '', 0),
          (4, 2, 1, 2, '', 0), (5, 2, 7, 3, '', 0), (6, 2, 4, 5, '', 0), (7, 2, 5, 6, '', 0), (8, 2, 6, 7, 'editor original', 0),
          (9, 3, 1, 2, '', 0), (10, 3, 2, 4, '', 0), (11, 3, 3, 10, '', 0), (12, 3, 1, 9, '', 0), (13, 3, 1, 10, '', 1),
          (14, 4, 2, 11, '', 0), (18, 2, 1, 12, 'traducción', 0), (19, 2, 1, 3, 'adaptación', 0),
          (15, 50, 1, 2, '', 0), (16, 50, 2, 3, '', 0), (17, 50, 9, 4, '', 0);
        INSERT INTO gcd_reprint VALUES (1, 50, 6), (2, 60, 7);
        """)
    return dump


@pytest.fixture
def details(rich_dump, tmp_path):
    target = tmp_path / "data" / "gcd_es.db"
    build_index(rich_dump, target)
    return GcdIndex(target)


def test_credit_roles_expands_combined_credit_types():
    assert credit_roles("script") == ("script",) and credit_roles("editing") == ("editing",)
    assert credit_roles("pencils and inks") == ("pencils", "inks")
    assert credit_roles("script, pencils, and inks") == ("script", "pencils", "inks")
    assert credit_roles("painting") == ("pencils", "colors")                  # pintura: dibujo y color
    assert credit_roles("script, pencils, inks, colors, and letters") == ("script", "pencils", "inks", "colors", "letters")
    assert credit_roles("otra cosa") == ()


def test_the_issue_gets_its_credits_merged_without_repeats_and_in_story_order(details):
    info = details.issue_details(100)
    # la traductora (guion con nota «traducción») va a Translator, no a Writer; una «adaptación» sí es guion
    assert info.credits == {"Writer": "Garth Ennis, Lewis LaRosa", "Penciller": "Lewis LaRosa, Tom Palmer",
                            "Inker": "Lewis LaRosa, Otro Guionista",
                            "Colorist": "Dean White", "Letterer": "Randolph Gentile", "Editor": "Axel Alonso",
                            "Translator": "Sofía Traductora", "CoverArtist": "Tim Bradstreet"}
    # «pencils and inks» (Lewis LaRosa) cuenta como lápiz y tinta; el creador borrado y el crédito borrado no salen; el
    # anuncio (otro tipo de historia) no aporta autores; el color de la portada no va al colorista ni al CoverArtist
    assert details.has_details() and not info.inherited


def test_a_cover_only_contributes_the_cover_artist_and_the_interior_never_gets_its_colorist(details):
    info = details.issue_details(100)
    assert "Grant Goleash" not in info.credits["Colorist"] and "Grant Goleash" not in info.credits["CoverArtist"]
    assert info.credits["CoverArtist"] == "Tim Bradstreet"


def test_several_stories_get_a_line_each_with_who_did_what(details):
    info = details.issue_details(100)
    assert info.story_lines == [
        "- «Uno»: Guion Garth Ennis, Lewis LaRosa · Lápiz Lewis LaRosa · Tinta Lewis LaRosa · Color Dean White",
        "- «Dos»: Guion Garth Ennis · Lápiz Tom Palmer · Tinta Otro Guionista"]
    assert details.issue_details(101).story_lines == []                        # una sola historia: no hace falta desglose


def test_a_story_without_credits_inherits_them_from_the_original_it_reprints(details):
    info = details.issue_details(101)
    assert info.inherited and info.credits["Writer"] == "Garth Ennis"
    assert info.credits["Penciller"] == "Lewis LaRosa, Tom Palmer" and info.credits["Colorist"] == "Tom Palmer"
    assert "Inker" not in info.credits                                       # Tom Palmer pintó: dibujo y color, no tinta
    assert details.issue_details(103).credits == {}                             # sin créditos ni original con ellos


def test_genre_and_characters_are_cleaned_translated_and_deduplicated(details):
    info = details.issue_details(100)
    assert info.genre == "crimen, superhéroes, noir"                        # traducidos si se conocen; el resto, tal cual
    assert info.characters == "Punisher, Micro, Roth"                           # sin identidades [entre corchetes] ni «?»
    assert info.summary == "Micro se une a la operación."                    # una historia con sinopsis: su texto tal cual


def test_price_becomes_euros_only_when_it_is_euros_or_pesetas_and_dates_split_into_parts():
    assert IssueDetails(price="3.50 EUR; 4.00 USD").cost == "3.50"
    assert IssueDetails(price="150 ESP").cost == "0.90"
    assert IssueDetails(price="19.00 MXN").cost == "" and IssueDetails(price="").cost == ""
    assert IssueDetails(price="1,20 €").cost == "1.20"
    assert IssueDetails(key_date="2008-01-17").date == ("2008", "1", "17")
    assert IssueDetails(key_date="2006-12-00").date == ("2006", "12", "")       # GCD escribe 00 donde no se sabe
    assert IssueDetails(key_date="1969-00-00").date == ("1969", "", "") and IssueDetails().date == ("", "", "")


def test_the_issue_carries_price_barcode_and_dates(details):
    info = details.issue_details(100)
    assert (info.cost, info.on_sale, info.barcode) == ("3.50", "2006-12-21", "977060120000000012")
    assert info.date == ("2006", "12", "")


def test_an_unknown_issue_gives_nothing_and_a_dump_without_story_tables_still_builds_an_index(index):
    assert index.issue_details(424242) is None
    info = index.issue_details(100)          # el volcado de siempre: sin tablas de historias ni de créditos
    assert info is not None and info.credits == {} and info.story_lines == [] and info.genre == ""
    assert index.is_ready() and index.has_details()


def test_an_older_index_still_works_for_searching_but_has_no_details(details):
    with closing(sqlite3.connect(details.path)) as db, db:
        db.execute("PRAGMA user_version = 2")
    assert details.is_ready() and not details.has_details() and details.issue_details(100) is None
    assert details.search("spiderman")
    with closing(sqlite3.connect(details.path)) as db, db:
        db.execute("PRAGMA user_version = 1")
    assert not details.is_ready() and GcdIndex(details.path.with_name("no-existe.db")).version() == 0
