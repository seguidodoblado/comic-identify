import pytest

from comic_identify.identify import Candidate
from comic_identify.naming import (
    DEFAULT_PATTERN,
    Values,
    check_pattern,
    flag_for,
    missing_content_years,
    render,
    sanitize,
    suggest_values,
)


def test_examples_from_estructura_md():
    # «Título 🇪🇸 [1991] (1993) - Forum»: contenido y edición distintos
    assert render(DEFAULT_PATTERN, Values("Punisher: P.O.V.", "", "🇪🇸", "1991", "1993", "Forum")) == \
        "Punisher: P.O.V. 🇪🇸 [1991] (1993) - Forum"
    # con volumen (un número suelto se escribe «Volumen 8»)
    assert render(DEFAULT_PATTERN, Values("Punisher", "8", "🇪🇸", "2009-2010", "2010-2011", "Panini")) == \
        "Punisher Volumen 8 🇪🇸 [2009-2010] (2010-2011) - Panini"
    # si contenido y edición coinciden, se omite el paréntesis
    assert render(DEFAULT_PATTERN, Values("Punisher: Diario de Guerra", "", "🇪🇸", "2007-2009", "2007-2009", "Panini")) == \
        "Punisher: Diario de Guerra 🇪🇸 [2007-2009] - Panini"


def test_empty_parts_leave_no_stray_separators():
    assert render(DEFAULT_PATTERN, Values("Batman", "", "🇺🇸", "1940", "1940", "")) == "Batman 🇺🇸 [1940]"   # sin sello ni « - »
    assert render(DEFAULT_PATTERN, Values("Marvels")) == "Marvels"                                        # solo el nombre
    assert render(DEFAULT_PATTERN, Values("X", "", "", "1990–1992", "1990 - 1992", "Forum")) == "X [1990-1992] - Forum"   # guiones tipográficos y espacios


def test_custom_pattern_with_the_issue_number():
    values = Values("Capitán Marvel", "", "🇪🇸", "1999-2000", "2000-2002", "Forum", "001")
    assert render("{nombre} {numero} {bandera} [{contenido}] ({edicion}) - {sello}", values) == \
        "Capitán Marvel 001 🇪🇸 [1999-2000] (2000-2002) - Forum"
    assert render("{bandera} {nombre} #{numero}", values) == "🇪🇸 Capitán Marvel #001"


def test_pattern_validation():
    check_pattern(DEFAULT_PATTERN)
    with pytest.raises(ValueError, match=r"\{titulo\}"):
        check_pattern("{titulo} {nombre}")
    with pytest.raises(ValueError, match="llave"):
        check_pattern("{nombre} {")
    with pytest.raises(ValueError):
        render("{inventada}", Values("x"))


def test_sanitize_and_flags():
    assert sanitize("  AC/DC: 1/2 . ") == "AC-DC: 1-2"
    assert flag_for("es") == "🇪🇸" and flag_for("US") == "🇺🇸" and flag_for("mx") == "" and flag_for("") == ""


def test_suggestions_from_candidates():
    gcd = Candidate("Capitán Marvel #1", "GCD", series="Capitán Marvel", number="1", year="2000",
                    publisher="Planeta DeAgostini", brand="Forum; Marvel Comics", country="es", years="2000–2002")
    suggested = suggest_values(gcd)
    assert (suggested.nombre, suggested.bandera, suggested.edicion, suggested.sello, suggested.numero) == \
        ("Capitán Marvel", "🇪🇸", "2000", "Forum", "1")
    assert suggested.contenido == ""            # el año real del original no se sabe: lo pone el usuario

    american = Candidate("X #1", "GCD", series="X", year="1990", country="us")
    assert (suggest_values(american).bandera, suggest_values(american).contenido) == ("🇺🇸", "1990")   # es su propio original
    assert suggest_values(Candidate("S", "GCD", series="S", country="mx", years="1980–1990")).bandera == ""
    assert suggest_values(Candidate("S", "GCD", series="S", country="es", years="1980–1990")).edicion == "1980-1990"

    cv = Candidate("Right Series #7", "ComicVine", series="Right Series", number="7", year="1991")
    assert (suggest_values(cv).bandera, suggest_values(cv).contenido, suggest_values(cv).edicion) == ("🇺🇸", "1991", "1991")
    assert suggest_values(Candidate("Mi Cómic 001", "Mi colección")).nombre == "Mi Cómic 001"


def test_missing_content_years_is_detected_only_when_the_pattern_needs_them():
    only_edition = Values("Capitán Marvel", "", "🇪🇸", "", "2000", "Forum")
    assert missing_content_years(DEFAULT_PATTERN, only_edition)
    assert not missing_content_years(DEFAULT_PATTERN, Values("X", contenido="2000"))
    assert not missing_content_years("{nombre} ({edicion})", only_edition)          # el patrón no usa el contenido
    assert missing_content_years(DEFAULT_PATTERN, Values("X", contenido="  "))


def test_unknown_content_years_are_simply_left_out():
    """Sin años del contenido no se inventa nada ni se bloquea: queda solo (edición), que es inequívoco."""
    assert render(DEFAULT_PATTERN, Values("Capitán Marvel", "", "🇪🇸", "", "2000", "Forum")) == "Capitán Marvel 🇪🇸 (2000) - Forum"
    assert render(DEFAULT_PATTERN, Values("Capitán Marvel", "", "🇪🇸", "", "", "Forum")) == "Capitán Marvel 🇪🇸 - Forum"
