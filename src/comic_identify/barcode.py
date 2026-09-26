"""Lectura del código de barras de la portada (zbarimg) y de su complemento de 5 dígitos."""
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Barcode:
    code: str
    addon: str = ""

    @property
    def issue_number(self) -> str | None:
        """Número de ejemplar según el complemento de 5 dígitos.

        Con EAN-13 (ediciones europeas) el complemento completo es el número: `00024` es el 24.
        Con UPC-A (grapas americanos) lo son los 3 primeros dígitos: `00111` es el 1.
        """
        if len(self.addon) != 5 or not self.addon.isdigit():
            return None
        number = int(self.addon) if len(self.code) == 13 else int(self.addon[:3])
        return str(number) if number else None


def parse_barcode(lines: list[str]) -> Barcode | None:
    """Interpreta la salida de `zbarimg --raw`: código base, con complemento pegado o aparte."""
    digits = [line.strip() for line in lines if re.fullmatch(r"\d+", line.strip())]
    code = addon = ""
    for value in digits:
        if len(value) in (17, 18):
            code, addon = value[:-5], value[-5:]
        elif len(value) in (12, 13) and not code:
            code = value
        elif len(value) == 5 and not addon:
            addon = value
    return Barcode(code, addon) if code else None


def read_barcode(path: Path) -> Barcode | None:
    try:
        done = subprocess.run(["zbarimg", "--quiet", "--raw", str(path)],
                              capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_barcode(done.stdout.splitlines())
