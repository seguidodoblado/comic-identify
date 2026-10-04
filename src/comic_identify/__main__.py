import sys


def main() -> None:
    import os

    from . import i18n
    from .settings import Settings
    # El idioma de Ajustes manda; con «Sistema» se recupera el $LANGUAGE original (los reinicios lo heredan)
    original = os.environ.setdefault("COMIC_IDENTIFY_SYSTEM_LANGUAGE", os.environ.get("LANGUAGE", ""))
    language = Settings.load().language or original
    if language:
        os.environ["LANGUAGE"] = language
    else:
        os.environ.pop("LANGUAGE", None)
    i18n.install()
    from .cli import dispatch
    image = dispatch(sys.argv[1:])   # las órdenes de texto terminan aquí, sin cargar GTK
    from .ui.gui import run_gui
    run_gui(image)


if __name__ == "__main__":
    main()
