"""Asistente de IA en un terminal embebido: lanza la CLI oficial del usuario (Claude Code, OpenCode, Codex…).

La aplicación no toca credenciales ni llama a ninguna API: el usuario usa su propia sesión en el terminal.
"""
import shlex
import shutil
from pathlib import Path

DEFAULT_COMMAND = "claude {prompt}"
PROMPT = ("Identifica el cómic de la portada @{image} y dame título, número, editorial, año, edición "
          "(país e idioma) y autores si los conoces. Puedes buscar en la web y consultar mi índice local de "
          "Grand Comics Database con la orden `comic-identify buscar \"título\" número` "
          "(esa orden no abre ninguna ventana; `comic-identify --help` muestra el uso). "
          "Para ediciones españolas son útiles Tebeosfera, Whakoom, Panini.es, Norma y, para Marvel, "
          "fichas.universomarvel.com (Forum, Planeta, Panini: trae fecha, precio y el número original) y "
          "Zona Negativa. Si no estás seguro, dilo y explica en qué te basas.")


def build_prompt(image_name: str) -> str:
    return PROMPT.replace("{image}", image_name)


def build_argv(template: str, prompt: str) -> list[str]:
    """Trocea la plantilla del comando y sustituye `{prompt}`; lanza ValueError si está vacía o mal formada."""
    tokens = shlex.split(template)
    if not tokens:
        raise ValueError("El comando del asistente está vacío.")
    return [prompt if token == "{prompt}" else token for token in tokens]


def prepare_workspace(image: Path, base: Path) -> Path:
    """Carpeta de trabajo aparte con solo la portada: la sesión de IA no ve tus proyectos."""
    base.mkdir(parents=True, exist_ok=True)
    for old in base.glob("portada.*"):
        old.unlink()
    shutil.copyfile(image, base / f"portada{image.suffix.lower() or '.png'}")
    return base
