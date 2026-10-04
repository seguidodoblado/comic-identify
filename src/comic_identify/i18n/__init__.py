"""Traducciones con gettext: el idioma fuente es el español; el resto, en po/*.po.

El dominio se liga a esta carpeta al importar el módulo, de modo que `_()` ya funciona en las
constantes de módulo; `install()` solo ajusta el locale del proceso (para los textos propios de
GTK) y se llama una vez al arrancar. El idioma sale del sistema o de `$LANGUAGE`.
"""
from __future__ import annotations

import gettext
import locale
from pathlib import Path

DOMAIN = "comic-identify"
LOCALE_DIR = Path(__file__).parent

gettext.bindtextdomain(DOMAIN, str(LOCALE_DIR))


def install() -> None:
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass  # locale del sistema no instalado: seguimos con el idioma por defecto (es)
    gettext.bindtextdomain(DOMAIN, str(LOCALE_DIR))
    gettext.textdomain(DOMAIN)


def _(message: str) -> str:
    return gettext.dgettext(DOMAIN, message)


def ngettext(singular: str, plural: str, count: int) -> str:
    return gettext.dngettext(DOMAIN, singular, plural, count)
