"""Logotipos de las editoriales (Forum, Panini, Vértice, Planeta DeAgostini, ECC, Zinco, Norma, Bruguera) para las filas de
resultados.

No se distribuyen con la aplicación: son marcas de sus editoriales. Se descargan una vez de la web de fichas de Universo
Marvel (de donde salen las propias fichas) y se guardan en la caché del usuario, como los iconos de las webs. Si no se
pueden descargar, la fila simplemente no lleva logotipo, y no se vuelve a intentar hasta pasada una semana.
"""
import io
import re
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin

from PIL import Image

from .gcd import fold
from .universomarvel import BASE, Fetcher, UniversoMarvelError

LOGOS = {"forum": "ima_gen/logoforum.jpg", "panini": "imagen/logopanini.jpg", "vertice": "ima_gen/logover.jpg",
         "planeta": "ima_gen/logoplaneta.jpg", "ecc": "ima_gen/logoecc.jpg",
         "zinco": "ima_gen/logozinco.jpg", "norma": "ima_gen/logonorma.jpg", "bruguera": "ima_gen/logobrug.jpg"}
# Qué texto reconoce cada una, por orden de prioridad: el sello Forum (lo que distingue la edición) gana a la editorial
# Planeta DeAgostini, que se muestra cuando no hay sello Forum (p. ej. sus números de DC, Vértigo o sin sello)
_TERMS = {"forum": r"forum", "panini": r"panini", "vertice": r"vertice", "planeta": r"de ?agostini", "ecc": r"\becc\b", "zinco": r"zinco",
          "norma": r"\bnorma\b", "bruguera": r"bruguera"}
NAMES = {"forum": "Forum", "panini": "Panini", "vertice": "Vértice", "planeta": "Planeta DeAgostini", "ecc": "ECC Ediciones", "zinco": "Zinco", "norma": "Norma Editorial",
         "bruguera": "Bruguera"}
RETRY_AFTER = 7 * 24 * 3600
LOGO_BOX = (116, 24)   # tamaño máximo (px) al que se guardan: el hueco que ocupan en las filas


def logo_key(*texts: str) -> str | None:
    """La editorial reconocida en esos textos (editorial, sello, colección…): la clave de una de las editoriales de `LOGOS` (p. ej. «forum» o «ecc»)."""
    folded = " ".join(fold(text) for text in texts if text)
    return next((key for key, pattern in _TERMS.items() if re.search(pattern, folded)), None)


USER_EXTENSIONS = (".png", ".jpg", ".jpeg", ".svg")
_LEGAL = re.compile(r"[,\s]*\b(?:s\.?\s?a\.?(?:\s+de\s+c\.?\s?v\.?)?|s\.?\s?l\.?|ltda\.?)\s*$", re.IGNORECASE)


def publisher_slug(name: str) -> str:
    """El nombre de archivo (sin extensión) con que se puede poner a mano el logotipo de una editorial: minúsculas, sin
    tildes ni signos y con guiones, p. ej. «Editorial Novaro» -> «editorial-novaro»."""
    return "-".join(re.findall(r"[a-z0-9]+", fold(name)))


def short_name(name: str) -> str:
    """El nombre de la editorial para una etiqueta pequeña: sin la forma societaria («S.A. de C.V.») ni comillas."""
    return _LEGAL.sub("", name.replace('"', "")).strip(" ,.") or name.strip()


def user_logo(names: tuple[str, ...], user_dir: Path | None) -> Path | None:
    """Un logotipo que haya puesto el usuario en su carpeta, por el nombre de archivo de alguno de esos nombres."""
    if user_dir is None:
        return None
    return next((path for name in names if name for extension in USER_EXTENSIONS
                 if (path := user_dir / f"{name}{extension}").is_file()), None)


def logo_file(key: str, cache_dir: Path, user_dir: Path | None = None) -> Path | None:
    """El logotipo de una editorial conocida: el que haya puesto el usuario (`<clave>.png`…) o el descargado."""
    if (custom := user_logo((key,), user_dir)) is not None:
        return custom
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
