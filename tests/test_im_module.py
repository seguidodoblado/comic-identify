import importlib
import os

import comic_identify


def _reload(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("GTK_IM_MODULE", raising=False)
    else:
        monkeypatch.setenv("GTK_IM_MODULE", value)
    importlib.reload(comic_identify)
    return os.environ.get("GTK_IM_MODULE")


def test_ibus_pasa_a_simple(monkeypatch):
    assert _reload(monkeypatch, "ibus") == "simple"


def test_otro_valor_no_cambia(monkeypatch):
    assert _reload(monkeypatch, "fcitx") == "fcitx"


def test_sin_valor_no_se_define(monkeypatch):
    assert _reload(monkeypatch, None) is None
