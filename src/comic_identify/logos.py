"""Logotipos de las editoriales (Forum, Panini, Vértice) para las filas de resultados.

No se distribuyen con la aplicación: son marcas de sus editoriales. Se descargan una vez de la web de fichas de Universo
Marvel (de donde salen las propias fichas) y se guardan en la caché del usuario, como los iconos de las webs. Si no se
pueden descargar, la fila simplemente no lleva logotipo, y no se vuelve a intentar hasta pasada una semana.
"""
import io
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin

from PIL import Image

from .gcd import fold
from .universomarvel import BASE, Fetcher, UniversoMarvelError

LOGOS = {"forum": "ima_gen/logoforum.jpg", "panini": "imagen/logopanini.jpg", "vertice": "ima_gen/logover.jpg"}
RETRY_AFTER = 7 * 24 * 3600
LOGO_BOX = (116, 24)   # tamaño máximo (px) al que se guardan: el hueco que ocupan en las filas


def logo_key(*texts: str) -> str | None:
    """La editorial reconocida en esos textos (editorial, sello, colección…): «forum», «panini» o «vertice»."""
    folded = " ".join(fold(text) for text in texts if text)
    return next((key for key in LOGOS if key in folded), None)


def logo_file(key: str, cache_dir: Path) -> Path | None:
    path = cache_dir / f"{key}.png"
    return path if path.exists() else None


def fetch_logo(key: str, cache_dir: Path, fetch: Callable[[str], bytes] | None = None) -> Path | None:
    """Descarga y guarda el logotipo de `key`; None si no se pudo (y se anota para no insistir durante una semana)."""
    if key not in LOGOS:
        return None
    if (cached := logo_file(key, cache_dir)) is not None:
        return cached
    cache_dir.mkdir(parents=True, exist_ok=True)
    failed = cache_dir / f"{key}.none"
    if failed.exists() and time.time() - failed.stat().st_mtime < RETRY_AFTER:
        return None
    try:
        data = (fetch or Fetcher().get)(urljoin(BASE, LOGOS[key]))
        with Image.open(io.BytesIO(data)) as image:
            small = image.convert("RGBA")
            small.thumbnail(LOGO_BOX, Image.Resampling.LANCZOS)   # ya al tamaño con que se muestra: GTK no lo reescala
            small.save(cache_dir / f"{key}.png", "PNG")
    except (UniversoMarvelError, OSError, ValueError):
        failed.write_text("sin logotipo\n")
        return None
    failed.unlink(missing_ok=True)
    return cache_dir / f"{key}.png"
