import gettext
import os
import string
import subprocess
import sys

import pytest

from comic_identify import i18n
from comic_identify.i18n import _, ngettext

MO = i18n.LOCALE_DIR / "en" / "LC_MESSAGES" / f"{i18n.DOMAIN}.mo"
needs_catalog = pytest.mark.skipif(not MO.exists(), reason="Falta compilar po/en.po (ver po/README.md)")


def english():
    return gettext.translation(i18n.DOMAIN, localedir=str(i18n.LOCALE_DIR), languages=["en"])


def test_spanish_is_the_source_language_and_needs_no_catalog():
    assert _("Sin resultados.") == "Sin resultados."
    assert ngettext("{count} archivo", "{count} archivos", 3) == "{count} archivos"


@needs_catalog
def test_english_catalog_translates():
    translation = english()
    assert translation.gettext("Sin resultados.") == "No results."
    assert translation.gettext("Cancelar") == "Cancel"
    assert translation.gettext("Ajustes") == "Settings"


@needs_catalog
def test_english_plural_forms():
    translation = english()
    assert translation.ngettext("{count} archivo", "{count} archivos", 1) == "{count} file"
    assert translation.ngettext("{count} archivo", "{count} archivos", 2) == "{count} files"


def placeholders(text):
    return {name for _literal, name, _spec, _conv in string.Formatter().parse(text) if name}


@needs_catalog
def test_translations_keep_the_placeholders_of_the_original():
    """Si el inglés perdiera un {nombre}, .format() fallaría en pleno uso."""
    translation = english()
    for message in ("Renombrado: {target_name} → {new_name}", "No se pudo copiar «{name}»: {error}",
                    "{changes_count} archivo(s) se renombran · {sum} ya tienen ese nombre · {sum_2} sin tocar"):
        translated = translation.gettext(message)
        assert translated != message
        assert placeholders(translated) == placeholders(message)


@needs_catalog
def test_cli_help_follows_the_language_of_the_environment():
    env = {**os.environ, "LANGUAGE": "en", "LC_ALL": "C.UTF-8", "PYTHONPATH": str(i18n.LOCALE_DIR.parents[1])}
    done = subprocess.run([sys.executable, "-m", "comic_identify", "--help"], capture_output=True, text=True, env=env, check=False)
    assert done.returncode == 0 and "opens the application" in done.stdout


def test_spanish_help_is_the_default_in_tests():
    env = {**os.environ, "LANGUAGE": "es", "PYTHONPATH": str(i18n.LOCALE_DIR.parents[1])}
    done = subprocess.run([sys.executable, "-m", "comic_identify", "--help"], capture_output=True, text=True, env=env, check=False)
    assert done.returncode == 0 and "abre la aplicación" in done.stdout
