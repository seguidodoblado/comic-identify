"""Tema claro/oscuro: el nombre del tema GTK hermano y qué icono usar en cada modo.

Mismo criterio que Telegraph Writer y Joseflix: el tema hermano se deriva del que tenga el sistema (conservando el
acento: `Mint-Y-Aqua` <-> `Mint-Y-Dark-Aqua`), en oscuro se usan los iconos simbólicos (monocromos, que GTK recolorea) y
en claro los de color que proporcione el tema de iconos del usuario. No se cambia de tema de iconos: se pide otro nombre.
"""
import re
from collections.abc import Callable

# Iconos de color que el tema no trae en versión simbólica (Mint-Y-Yaru): se sustituyen por un equivalente que sí la tenga.
SYMBOLIC_ALTERNATIVES = {
    "applications-internet": "network-workgroup",
    "preferences-desktop-theme": "preferences-desktop-appearance",
}


def theme_variant(name: str, dark: bool) -> str:
    """Deriva el tema GTK hermano (claro/oscuro) preservando el acento. Sigue la convención Mint-Y[-Dark]-<Acento> de
    Linux Mint y, para el resto de temas, la de Adwaita/Yaru (<tema>[-<acento>]-dark)."""
    base = re.sub(r"-dark(?=-|$)", "", name, count=1, flags=re.IGNORECASE)
    if not dark:
        return base
    parts = base.split("-", 2)
    if parts[0] == "Mint" and len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}-Dark" + (f"-{parts[2]}" if len(parts) > 2 else "")
    return base + "-dark"


def is_dark_theme(name: str | None) -> bool:
    """¿Es una variante oscura de tema GTK?"""
    return bool(name and "-dark" in name.lower())


def icon_choice(names: tuple[str, ...], dark: bool, has_icon: Callable[[str], bool]) -> str:
    """El primer icono de la lista que exista, con la variante que toca: en oscuro la simbólica y en claro la de color
    (si el tema no la tiene, la otra). Las peticiones pueden venir con o sin `-symbolic`; '' si no hay ninguno."""
    for name in names:
        base = name.removesuffix("-symbolic")
        alternative = SYMBOLIC_ALTERNATIVES.get(base)
        symbolic = [base + "-symbolic"] + ([alternative + "-symbolic"] if alternative else [])
        options = [*symbolic, base] if dark else [base, *symbolic]
        if found := next((option for option in options if has_icon(option)), None):
            return found
    return ""
