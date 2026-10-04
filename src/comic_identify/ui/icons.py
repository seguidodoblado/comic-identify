"""Iconos (favicon) de las webs para los botones y los créditos de Ajustes.

Se descargan la primera vez, como haría un navegador, y se guardan en la caché del usuario. No se
distribuyen con la aplicación: son marcas de sus respectivas webs.

Si una web no entrega su icono (hay webs que solo sirven a navegadores), se pide al servicio público de favicons de
Google, al que solo se le envía el nombre del dominio. No se finge ser un navegador ni se esquiva ninguna protección.
"""
import io
import re
import time
import urllib.request
from collections.abc import Callable, Iterable
from pathlib import Path
from urllib.parse import urljoin

from PIL import Image

USER_AGENT = "comic-identify (aplicación personal de escritorio)"
MAX_BYTES = 512 * 1024
ICON_SIZE = 64              # se guarda a este tamaño como máximo
RETRY_AFTER = 7 * 24 * 3600  # si una web no da icono, no se vuelve a intentar durante una semana
FALLBACK_URL = "https://www.google.com/s2/favicons?domain={host}&sz=64"
MARKER = "probado con respaldo\n"   # un marcador de fallo sin esto es de antes del respaldo: se vuelve a intentar

Fetch = Callable[[str], bytes | None]


def default_fetch(url: str) -> bytes | None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return response.read(MAX_BYTES)
    except (OSError, ValueError):
        return None


def _decode(data: bytes | None) -> Image.Image | None:
    if not data:
        return None
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            return image.convert("RGBA")
    except (OSError, ValueError):
        return None


def _declared_icons(html: bytes | None, base: str) -> list[str]:
    """Iconos que la página declara (`<link rel="…icon…">`), de mayor a menor tamaño anunciado."""
    if not html:
        return []
    found = []
    for tag in re.findall(rb"<link[^>]+>", html, re.IGNORECASE):
        text = tag.decode("utf-8", "replace")
        rel = re.search(r'rel="([^"]*)"', text, re.IGNORECASE)
        href = re.search(r'href="([^"]+)"', text, re.IGNORECASE)
        if not rel or "icon" not in rel.group(1).lower() or not href:
            continue
        size = (re.search(r'sizes="(\d+)x\d+"', text, re.IGNORECASE)
                or re.search(r"(\d+)x\d+", href.group(1)))
        found.append((int(size.group(1)) if size else 0, urljoin(base, href.group(1))))
    return [url for _, url in sorted(found, reverse=True)]


def icon_file(host: str, cache_dir: Path) -> Path | None:
    path = cache_dir / f"{host}.png"
    return path if path.exists() else None


def fetch_icon(host: str, cache_dir: Path, larger: bool = False, fetch: Fetch = default_fetch) -> Path | None:
    """Descarga el icono de `host`. Con `larger`, busca también las versiones grandes que declare la web."""
    base = f"https://{host}/"
    urls = [urljoin(base, "/favicon.ico")]
    if larger:
        urls = _declared_icons(fetch(base), base)[:2] + urls
    images = [image for image in (_decode(fetch(url)) for url in urls) if image is not None]
    if not images and (fallback := _decode(fetch(FALLBACK_URL.format(host=host)))) is not None:
        images = [fallback]
    if not images:
        return None
    best = max(images, key=lambda image: image.width * image.height)
    best.thumbnail((ICON_SIZE, ICON_SIZE), Image.Resampling.LANCZOS)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{host}.png"
    best.save(path, "PNG")
    return path


def ensure_icons(requests: Iterable[tuple[str, bool]], cache_dir: Path,
                 on_ready: Callable[[str, Path], None], fetch: Fetch = default_fetch) -> None:
    """Para cada (host, grande): usa el icono en caché o lo descarga, y avisa con `on_ready`."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    for host, larger in requests:
        if (cached := icon_file(host, cache_dir)) is not None:
            on_ready(host, cached)
            continue
        failed = cache_dir / f"{host}.none"
        if failed.exists() and failed.read_text() == MARKER and time.time() - failed.stat().st_mtime < RETRY_AFTER:
            continue
        if (path := fetch_icon(host, cache_dir, larger, fetch)) is not None:
            failed.unlink(missing_ok=True)
            on_ready(host, path)
        else:
            failed.write_text(MARKER)
