"""Pruebas de la interfaz (tests/gui/): se lanzan en otro proceso, con servidor X y bus D-Bus propios.

Va aparte porque las rutas de `settings` se resuelven al importar el módulo: HOME y XDG tienen que ser ya los
temporales cuando arranca el intérprete, y así las pruebas nunca tocan los datos ni el escritorio del usuario.
Se omite si faltan las herramientas; con COMIC_IDENTIFY_REQUIRE_GUI=1 (la CI) esa falta es un fallo.
"""
import os
import shutil
import site
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _unavailable(reason: str):
    (pytest.fail if os.environ.get("COMIC_IDENTIFY_REQUIRE_GUI") else pytest.skip)(reason)


def test_gui_flows(tmp_path):
    if missing := [tool for tool in ("xvfb-run", "Xvfb", "dbus-run-session") if shutil.which(tool) is None]:
        _unavailable(f"faltan: {', '.join(missing)}")
    probe = "import gi; gi.require_version('Gtk', '4.0'); from gi.repository import Gtk"
    if subprocess.run([sys.executable, "-c", probe], capture_output=True, check=False).returncode:
        _unavailable("este Python no tiene PyGObject con GTK 4")

    env = dict(os.environ)
    for variable, folder in (("HOME", "home"), ("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                             ("XDG_CACHE_HOME", "cache"), ("XDG_RUNTIME_DIR", "runtime")):
        path = tmp_path / folder
        path.mkdir(mode=0o700)
        env[variable] = str(path)
    for variable in ("WAYLAND_DISPLAY", "DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "GTK_IM_MODULE", "GTK_THEME"):
        env.pop(variable, None)
    env.update(COMIC_IDENTIFY_GUI="1", LANGUAGE="es", GDK_BACKEND="x11", GSK_RENDERER="cairo",
               GSETTINGS_BACKEND="memory", GTK_A11Y="none", NO_AT_BRIDGE="1", GTK_USE_PORTAL="0",
               GIO_USE_VFS="local",
               PYTHONUSERBASE=site.getuserbase())   # al cambiar HOME no se pierde lo instalado con pip --user

    command = ["xvfb-run", "-a", "dbus-run-session", "--", sys.executable, "-m", "pytest", "-q", "-rs",
               "-p", "no:cacheprovider", "tests/gui"]
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=300, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
