"""Flujos principales sobre la ventana real. No se ejecutan sueltos: los lanza tests/test_gui.py, que les da un
servidor X, un bus D-Bus y un HOME temporales (así `pytest` nunca abre ventanas en el escritorio del usuario)."""
import os
import socket
import sys
import threading
import time
import zipfile
from pathlib import Path

import pytest
from conftest import jpeg, make_cover

from comic_identify import gcstar, settings
from comic_identify.comicinfo import read_info
from comic_identify.ui import window as window_module
from comic_identify.ui.constants import INITIAL_STATUS

GCS = """<?xml version="1.0" encoding="UTF-8"?>
<collection type="GCcomics" items="0" version="1.8.0">
 <information>
  <maxId>0</maxId>
  <name>Comics</name>
 </information>

</collection>
"""


def pump(condition=lambda: False, timeout: float = 15, what: str = ""):
    """Hace girar el bucle de GTK hasta que se cumpla `condition`."""
    context = window_module.GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            pytest.fail(f"Se agotó el tiempo esperando: {what}")
        if not context.iteration(False):
            time.sleep(0.01)


def settle():
    """Espera a los hilos de trabajo y despacha lo que hayan dejado para la interfaz."""
    pump(lambda: threading.active_count() == 1, what="que terminen los hilos")
    context = window_module.GLib.MainContext.default()
    for _ in range(200):
        if not context.iteration(False):
            break


@pytest.fixture(scope="session")
def app():
    # Salvaguarda: sin el entorno aislado se escribiría sobre los ajustes reales
    assert os.environ.get("COMIC_IDENTIFY_GUI") == "1"
    assert settings.CONFIG_FILE.is_relative_to(os.environ["XDG_CONFIG_HOME"])
    application = window_module.App()
    assert application.register(None)
    return application


@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    """Sin red, sin mirar los procesos de la máquina, y cualquier excepción en un callback o un hilo hace fallar la
    prueba (GTK solo las imprime: la ventana se queda a medias sin avisar)."""
    def refuse(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise OSError(f"las pruebas de interfaz no usan la red: {address}")
        return real_connect(sock, address)

    real_connect = socket.socket.connect
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(window_module, "ensure_icons", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gcstar, "is_running", lambda *_args, **_kwargs: False)
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda _type, error, _trace: errors.append(repr(error)))
    monkeypatch.setattr(threading, "excepthook", lambda args: errors.append(repr(args.exc_value)))
    yield
    assert not errors


@pytest.fixture
def open_window(app, isolation):
    for path in (settings.CONFIG_FILE, settings.LIBRARY_DB, settings.METADATA_LOG, settings.GCSTAR_LOG):
        path.unlink(missing_ok=True)
    opened = []

    def build(**values):
        if values:
            settings.Settings(**values).save()
        window = window_module.Window(app)
        window.present()
        opened.append(window)
        settle()
        return window

    yield build
    settle()
    for window in opened:
        window.destroy()
    settle()


@pytest.fixture
def comic(tmp_path) -> Path:
    path = tmp_path / "comics" / "USA" / "Serie" / "Serie 001.cbz"
    path.parent.mkdir(parents=True)
    with zipfile.ZipFile(path, "w") as archive:
        for number in (1, 2):
            archive.writestr(f"{number:02d}.jpg", jpeg(make_cover(number)))
    return path


@pytest.fixture
def collection(tmp_path) -> Path:
    path = tmp_path / "gcstar" / "comics.gcs"
    path.parent.mkdir()
    path.write_text(GCS, encoding="utf-8")
    return path


def load(window, comic: Path):
    window._load(comic)
    pump(lambda: len(window.pages) == 2 and window.meta_box.get_visible() and not window.busy,
         what="que se abra el cómic")


def test_window_starts_empty(open_window):
    window = open_window()
    assert window.notebook.get_n_pages() == 3
    assert window.status.get_text() == INITIAL_STATUS
    assert not window.metadata_button.get_sensitive() and not window.gcstar_button.get_sensitive()


def test_open_cbz_and_reset(open_window, comic):
    window = open_window()
    load(window, comic)
    assert window.source_file == comic
    assert not window.cover_placeholder.get_visible()
    assert window.page_nav.get_visible()
    assert window.metadata_button.get_sensitive() and window.export_cover_button.get_sensitive()
    assert not window.gcstar_button.get_sensitive()   # sin archivo .gcs configurado

    window._reset()
    settle()
    assert window.source_file is None and window.cover_placeholder.get_visible()
    assert window.status.get_text() == INITIAL_STATUS
    assert not window.metadata_button.get_sensitive()


def test_open_broken_cbz_reports_the_error(open_window, tmp_path):
    window = open_window()
    broken = tmp_path / "roto.cbz"
    broken.write_bytes(b"esto no es un zip")
    window._load(broken)
    pump(lambda: window.status.get_text().startswith("No se pudo leer la portada"), what="el aviso de error")
    assert window.source_file is None


def test_write_and_undo_metadata(open_window, comic):
    window = open_window()
    load(window, comic)
    window.metadata_button.emit("clicked")
    pump(lambda: hasattr(window, "metadata_dialog"), what="el diálogo de metadatos")
    dialog = window.metadata_dialog
    dialog["entries"]["Series"].set_text("Serie de prueba")
    assert dialog["apply"].get_sensitive()
    dialog["apply"].emit("clicked")
    pump(lambda: not dialog["window"].get_visible(), what="que se escriban los metadatos")
    settle()
    assert read_info(comic)["Series"] == "Serie de prueba"

    window.metadata_undo_button.emit("clicked")
    pump(window.metadata_undo_button.get_sensitive, what="que se deshagan los metadatos")
    settle()
    assert not read_info(comic).get("Series")


def test_invalid_metadata_cannot_be_applied(open_window, comic):
    window = open_window()
    load(window, comic)
    window.metadata_button.emit("clicked")
    pump(lambda: hasattr(window, "metadata_dialog"), what="el diálogo de metadatos")
    dialog = window.metadata_dialog
    dialog["entries"]["Year"].set_text("no es un año")
    assert dialog["problem"].get_text() and not dialog["apply"].get_sensitive()
    dialog["window"].close()


def open_gcstar_dialog(window, comic: Path):
    load(window, comic)
    assert window.gcstar_button.get_sensitive()
    window.gcstar_button.emit("clicked")
    pump(lambda: hasattr(window, "gcstar_dialog"), what="el diálogo de GCstar")
    return window.gcstar_dialog


def test_transfer_to_gcstar_and_undo(open_window, comic, collection, tmp_path):
    window = open_window(gcstar_path=str(collection), folders=[str(tmp_path / "comics")])
    dialog = open_gcstar_dialog(window, comic)
    assert dialog["entries"]["type"].get_text() == "Americano"
    dialog["apply"].emit("clicked")
    pump(lambda: not dialog["window"].get_visible(), what="que termine la transferencia")
    assert "<item " in collection.read_text(encoding="utf-8")
    assert len(list((collection.parent / "comics").rglob("*.jpg"))) == 2
    assert window.status.get_text().startswith("Transferido a GCstar")

    window.gcstar_undo_button.emit("clicked")
    pump(window.gcstar_undo_button.get_sensitive, what="que se deshaga la transferencia")
    assert "<item " not in collection.read_text(encoding="utf-8")
    assert not list((collection.parent / "comics").rglob("*.jpg"))


def test_gcstar_file_error_is_shown_in_the_dialog(open_window, comic, collection, tmp_path):
    """Regresión de la 0.45.0: si la portada ya existía, el diálogo se quedaba bloqueado sin mensaje."""
    window = open_window(gcstar_path=str(collection), folders=[str(tmp_path / "comics")])
    existing = collection.parent / "comics" / "USA" / "Serie" / "Serie 001 - Portada.jpg"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"ya estaba")
    dialog = open_gcstar_dialog(window, comic)
    dialog["apply"].emit("clicked")
    pump(lambda: bool(dialog["problem"].get_text()), what="el error en el diálogo")
    assert dialog["window"].get_visible() and dialog["apply"].get_sensitive()
    assert existing.read_bytes() == b"ya estaba"
    assert collection.read_text(encoding="utf-8") == GCS
    dialog["window"].close()


def test_settings_are_saved(open_window, comic, collection):
    window = open_window()
    load(window, comic)
    window.key.set_text("  clave  ")
    window._save_key(None)
    window.gcstar_entry.set_text(str(collection))
    window._save_gcstar_path(None)
    saved = settings.Settings.load()
    assert saved.api_key == "clave" and saved.gcstar_path == str(collection)
    assert window.gcstar_button.get_sensitive()


def test_backup_now(open_window, tmp_path):
    window = open_window()
    assert not window.backup_now_button.get_sensitive()
    folder = tmp_path / "copias"
    folder.mkdir()
    window.key.set_text("clave")
    window._save_key(None)
    window.backup_entry.set_text(str(folder))
    window._save_backup_settings(None)
    window.backup_now_button.emit("clicked")
    pump(lambda: window.backup_info.get_text().startswith("Copia guardada"), what="la copia de seguridad")
    assert len(list(folder.glob("*.zip"))) == 1


def test_index_the_collection(open_window, comic, tmp_path):
    window = open_window(folders=[str(tmp_path / "comics")])
    window.notebook.set_current_page(1)
    window.index_button.emit("clicked")
    pump(lambda: not window.indexing, what="que termine la indexación")
    assert "Nuevas: 1" in window.index_info.get_text()


def test_about_dialog(open_window, app):
    window = open_window()
    before = set(window_module.Gtk.Window.list_toplevels())
    window._about(None)
    settle()
    about = [w for w in set(window_module.Gtk.Window.list_toplevels()) - before
             if isinstance(w, window_module.Gtk.AboutDialog)]
    assert len(about) == 1
    about[0].destroy()
