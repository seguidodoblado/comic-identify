import sys


def main() -> None:
    from . import i18n
    i18n.install()
    from .cli import dispatch
    image = dispatch(sys.argv[1:])   # las órdenes de texto terminan aquí, sin cargar GTK
    from .ui.gui import run_gui
    run_gui(image)


if __name__ == "__main__":
    main()
