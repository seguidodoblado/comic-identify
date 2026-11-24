import os as _os

__version__ = "0.44.2"

# IBus 1.5.29 con GTK4 no confirma la tecla muerta (tilde flotando). El método integrado
# de GTK compone bien las teclas muertas. Debe fijarse antes de que GTK arranque.
if _os.environ.get("GTK_IM_MODULE") == "ibus":
    _os.environ["GTK_IM_MODULE"] = "simple"
