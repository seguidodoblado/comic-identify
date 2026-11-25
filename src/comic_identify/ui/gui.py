"""Punto de entrada de la interfaz GTK4: carga la ventana solo si PyGObject está instalado."""
from pathlib import Path

from ..i18n import _


def run_gui(initial_image: Path | None = None) -> None:
    try:
        from .window import run_app
    except (ImportError, ValueError) as error:
        raise RuntimeError(_("GTK 4/PyGObject no está instalado.")) from error
    run_app(initial_image)
