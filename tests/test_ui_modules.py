"""La interfaz se reparte en módulos: todos deben importarse y resolver sus métodos sin abrir ninguna ventana."""
import ast
from pathlib import Path

import pytest

pytest.importorskip("gi")

UI = Path(__file__).resolve().parent.parent / "src" / "comic_identify" / "ui"


def test_window_module_imports():
    window = pytest.importorskip("comic_identify.ui.window")
    assert hasattr(window, "Window") and hasattr(window, "App") and callable(window.run_app)


def test_window_resolves_every_self_method():
    """Todo `self.método(...)` que usa algún módulo de la ventana existe en `Window` (o se asigna como atributo).

    Al repartir `Window` en mixins, un método que se quede en el sitio equivocado solo fallaría al usarlo."""
    window = pytest.importorskip("comic_identify.ui.window")
    called, assigned = {}, set()
    for path in UI.glob("*.py"):
        tree = ast.parse(path.read_text())
        classes = [c for c in ast.walk(tree) if isinstance(c, ast.ClassDef) and c.name != "App"]
        for node in (n for c in classes for n in ast.walk(c)):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
                if isinstance(node.ctx, ast.Store):
                    assigned.add(node.attr)
                else:
                    called.setdefault(node.attr, path.name)
    missing = {name: where for name, where in called.items()
               if not hasattr(window.Window, name) and name not in assigned}
    assert not missing
