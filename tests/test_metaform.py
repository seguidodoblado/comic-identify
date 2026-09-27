from types import SimpleNamespace

from comic_identify.metaform import (
    SERIES_FIELDS,
    describe_info,
    file_changes,
    initial_category,
    initial_form,
    merge_values,
    series_changes,
    suggest_fields,
)
from comic_identify.naming import DEFAULT_PATTERN, Values, detect_number, parse_name, render


def test_parse_name_is_the_inverse_of_render_for_the_default_pattern():
    for values in (Values("Punisher: P.O.V.", "", "🇪🇸", "1991", "1993", "Forum"),
                   Values("Punisher", "8", "🇪🇸", "2009-2010", "2010-2011", "Panini"),
                   Values("Punisher: Diario de Guerra", "", "🇪🇸", "2007-2009", "2007-2009", "Panini"),
                   Values("Batman", "", "🇺🇸", "1940", "1940", ""),
                   Values("Marvels"),
                   Values("Spider-Man - Blue", "", "🇪🇸", "2002", "2003", "Forum")):
        parsed = parse_name(render(DEFAULT_PATTERN, values))
        assert (parsed.nombre, parsed.volumen, parsed.bandera, parsed.sello) == \
            (values.nombre, values.volumen, values.bandera, values.sello)
        assert parsed.contenido == values.contenido and parsed.edicion in (values.edicion, "")   # iguales: se omite uno


def test_parse_name_ignores_the_issue_number_and_keeps_what_it_does_not_understand():
    parsed = parse_name("Capitán Marvel 🇪🇸 [1999-2001] (2000-2002) - Forum #05")
    assert (parsed.nombre, parsed.bandera, parsed.contenido, parsed.edicion, parsed.sello) == \
        ("Capitán Marvel", "🇪🇸", "1999-2001", "2000-2002", "Forum")
    assert parse_name("Spider-Man (Ultimate)").nombre == "Spider-Man (Ultimate)"       # no son años: es el nombre
    assert parse_name("Star_Wars_War_Of_The_Bounty_Hunters_#01_Infinity").nombre.startswith("Star_Wars")


def test_detect_number_prefers_the_final_hash_number_of_normalized_names():
    assert detect_number("Punisher Volumen 8 🇪🇸 [2009-2010] (2010-2011) - Panini #05") == ("05", False)
    assert detect_number("Batman #12 (2011)") == ("12", False)
    assert detect_number("Star Wars 3 y 4") == ("4", True)


def test_suggestions_from_the_name_and_from_gcd():
    values = Values("Punisher", "8", "🇪🇸", "2009-2010", "2010-2011", "Panini")
    assert suggest_fields(values) == {"Series": "Punisher", "Volume": "8", "Year": "2010", "Imprint": "Panini",
                                      "LanguageISO": "es", "Notes": "Contenido original: 2009-2010"}
    info = SimpleNamespace(id=1234, publisher="Planeta DeAgostini", issue_count=36)
    fields = suggest_fields(Values("Capitán Marvel", "", "🇪🇸", "", "2000-2002", "Forum"), "", info)
    assert fields["Web"] == "https://www.comics.org/series/1234/" and fields["Count"] == "36"
    assert fields["Publisher"] == "Planeta DeAgostini" and fields["Year"] == "2000" and "Notes" not in fields
    assert suggest_fields(Values("X"), "Panini")["Publisher"] == "Panini"       # lo tecleado gana a GCD
    assert suggest_fields(Values("Punisher", "Marvel Knights"))["Series"] == "Punisher Marvel Knights"


def test_existing_metadata_wins_over_suggestions_and_differences_stay_blank():
    infos = [{"Series": "Existente", "Year": "1999", "Publisher": "Forum"}, {"Series": "Existente", "Year": "2000"}]
    texts, baseline = initial_form(infos, {"Series": "Sugerida", "Year": "1990", "Imprint": "Panini", "Volume": "3"})
    assert texts["Series"] == "Existente" and baseline["Series"] == "Existente"        # todos igual: se muestra
    assert texts["Year"] == "" and texts["Publisher"] == ""                            # difieren o solo algunos: vacío
    assert texts["Imprint"] == "Panini" and texts["Volume"] == "3"                     # nadie lo tiene: la sugerencia
    assert set(texts) == set(SERIES_FIELDS)


def test_series_changes_set_typed_values_and_delete_only_what_everyone_had():
    baseline = {"Series": "Existente", "Year": "", "Notes": "vieja"}
    texts = {"Series": "Nueva", "Year": "", "Notes": "", "Publisher": " Forum "}
    assert series_changes(texts, baseline) == {"Series": "Nueva", "Notes": "", "Publisher": "Forum"}
    assert series_changes({"Year": ""}, {"Year": ""}) == {}          # vacío y nadie lo tenía: no se toca


def test_category_is_only_written_when_chosen_and_keeps_other_tags():
    assert initial_category([{"Tags": "Categoría: Series, Otra"}, {"Tags": "Categoría: Series"}]) == "Series"
    assert initial_category([{"Tags": "Categoría: Series"}, {"Tags": ""}]) == ""
    assert file_changes({"Series": "X"}, "", "3", "", "", {}) == {"Series": "X", "Number": "3", "Title": "",
                                                                  "Summary": ""}
    changes = file_changes({"Series": "X"}, "Recopilatorios y clásicos", "05", " Título ", " Resumen ",
                           {"Tags": "Superhéroes"})
    assert changes == {"Series": "X", "Number": "5", "Title": "Título", "Summary": "Resumen",
                       "Tags": "Superhéroes, Categoría: Recopilatorios y clásicos"}
    assert "Number" not in file_changes({}, "", "  ", "", "", {})      # sin número: no se toca el existente


def test_merge_values_prefers_the_normalized_name_and_falls_back_to_gcd_then_typed_title():
    gcd = Values("Capitán Marvel", "", "🇪🇸", "", "2000-2002", "Forum")
    normalized = parse_name("Capitán Marvel 🇪🇸 [1999-2001] - Panini")
    merged = merge_values(normalized, gcd)
    assert (merged.sello, merged.edicion, merged.contenido) == ("Panini", "2000-2002", "1999-2001")   # el nombre gana
    raw = parse_name("Capitan marvel 1-20")
    assert merge_values(raw, gcd).nombre == "Capitán Marvel"                                             # sin normalizar: GCD
    assert merge_values(raw, None, "Capitán Marvel").nombre == "Capitán Marvel"                          # o lo tecleado
    assert merge_values(raw, None, "").nombre == "Capitan marvel 1-20"
    assert merge_values(parse_name("Batman - El regreso"), gcd).nombre == "Capitán Marvel"     # « - texto» no es un sello


def test_describe_info_orders_translates_and_groups_the_date_and_category():
    info = {"Notes": "Contenido original: 1999", "Series": "Capitán Marvel", "Number": "5", "Year": "2000", "Month": "3",
            "Tags": "Superhéroes, Categoría: Series", "Publisher": "Planeta", "Imprint": "Forum", "Writer": "Autor",
            "Extra": "x", "Title": "", "Web": " https://www.comics.org/series/1/ "}
    assert describe_info(info) == [
        ("Serie", "Capitán Marvel"), ("Nº", "5"), ("Notas", "Contenido original: 1999"), ("Fecha", "2000-03"),
        ("Guion", "Autor"), ("Editorial", "Planeta"), ("Sello", "Forum"), ("Categoría", "Series"),
        ("Etiquetas", "Superhéroes"), ("Web", "https://www.comics.org/series/1/"), ("Extra", "x")]
    assert describe_info({}) == [] and describe_info({"Tags": "Categoría: OGN y OneShots"}) == [("Categoría", "OGN y OneShots")]
    assert describe_info({"Year": "2000", "Day": "7"}) == [("Fecha", "2000")]        # un día suelto no significa nada
    assert describe_info({"Year": "2000", "Month": "3", "Day": "7"}) == [("Fecha", "2000-03-07")]
    assert describe_info({"Month": "3"}) == []
