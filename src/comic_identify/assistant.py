"""Asistente de IA en un terminal embebido: lanza la CLI oficial del usuario (Claude Code, OpenCode, Codex…).

La aplicación no toca credenciales ni llama a ninguna API: el usuario usa su propia sesión en el terminal.
"""
import os
import shlex
import shutil
from pathlib import Path

DEFAULT_COMMAND = "claude {prompt}"
PROMPT = ("Identifica el cómic de la portada @{image} y dame título, número, editorial, año, edición "
          "(país e idioma) y autores si los conoces. Puedes buscar en la web y consultar mi índice local de "
          "Grand Comics Database con la orden `comic-identify buscar \"título\" número` "
          "(esa orden no abre ninguna ventana; `comic-identify --help` muestra el uso). "
          "Para ediciones españolas son útiles Tebeosfera, Whakoom, Panini.es, Norma, ecccomics.com (ECC: DC) y "
          "Zona Negativa; para Marvel, fichas.universomarvel.com (Forum, Planeta, Panini: trae fecha, precio y el "
          "número original) y, para DC, dc.fandom.com (número original y fechas). "
          "Si no estás seguro, dilo y explica en qué te basas.")


def build_prompt(image_name: str, template: str = PROMPT) -> str:
    """El mensaje para el asistente: `template` (el editable de Ajustes o el de serie) con `{image}` ya sustituido."""
    return (template.strip() or PROMPT).replace("{image}", image_name)


def build_argv(template: str, prompt: str) -> list[str]:
    """Trocea la plantilla del comando y sustituye `{prompt}`; lanza ValueError si está vacía o mal formada."""
    tokens = shlex.split(template)
    if not tokens:
        raise ValueError("El comando del asistente está vacío.")
    return [prompt if token == "{prompt}" else token for token in tokens]


def shell_argv(argv: list[str]) -> list[str]:
    """Lanza `argv` desde tu shell interactiva: así encuentra las CLIs que solo están en el PATH de tu ~/.bashrc
    (opencode en ~/.opencode/bin, codex bajo nvm…), que una app lanzada desde el menú no ve."""
    shell = os.environ.get("SHELL") or "/bin/bash"
    return [shell, "-ic", "exec " + shlex.join(argv)]


def prepare_workspace(image: Path, base: Path) -> Path:
    """Carpeta de trabajo aparte con solo la portada: la sesión de IA no ve tus proyectos."""
    base.mkdir(parents=True, exist_ok=True)
    for old in base.glob("portada.*"):
        old.unlink()
    shutil.copyfile(image, base / f"portada{image.suffix.lower() or '.png'}")
    return base
