"""Órdenes de línea de comandos; `buscar` la usa el asistente de IA para consultar el índice local."""
import sys
from pathlib import Path

from .gcd import GcdIndex
from .identify import search_gcd
from .settings import GCD_DB


def buscar(args: list[str]) -> int:
    if not args:
        print('Uso: comic-identify buscar "título" [número]', file=sys.stderr)
        return 2
    index = GcdIndex(GCD_DB)
    if not index.is_ready():
        print("No hay índice de GCD: impórtalo desde Ajustes (Importar volcado de GCD).", file=sys.stderr)
        return 1
    found = search_gcd(index, args[0], args[1] if len(args) > 1 else "")
    for candidate in found:
        print(f"{candidate.title} | {candidate.subtitle} | {candidate.url}")
    if not found:
        print("Sin resultados.")
    return 0


USAGE = """Uso:
  comic-identify                              abre la aplicación
  comic-identify portada.jpg                  abre la aplicación con esa portada (imagen, CBR o CBZ)
  comic-identify buscar "título" [número]     busca en el índice local de GCD, sin abrir la aplicación
  comic-identify --help                       muestra esta ayuda"""


def dispatch(args: list[str]) -> Path | None:
    """Decide qué hacer con los argumentos. Devuelve la portada con la que abrir la interfaz (o None).

    Solo se abre la interfaz sin argumentos o con un archivo que exista: una orden desconocida
    (`--help`, `search`, una errata…) nunca debe abrir otra ventana, porque el asistente de IA las prueba.
    """
    if not args:
        return None
    if args[0] in ("-h", "--help", "help", "ayuda"):
        print(USAGE)
        raise SystemExit(0)
    if args[0] == "buscar":
        raise SystemExit(buscar(args[1:]))
    if len(args) == 1 and Path(args[0]).is_file():
        return Path(args[0])
    print(f"Orden no reconocida: {' '.join(args)}\n\n{USAGE}", file=sys.stderr)
    raise SystemExit(2)
