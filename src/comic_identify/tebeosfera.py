"""Fuente www.tebeosfera.com: el catálogo de la historieta editada en España (todas las editoriales).

Tebeosfera es un proyecto de una asociación cultural sin API ni volcado, así que NO se rastrea: el índice sale de sus
sitemaps públicos (que `robots.txt` anuncia; solo prohíbe `/adminpanel/`), unas pocas peticiones con pausa entre ellas y
una identificación honesta. De ellos se sabe qué colecciones hay y qué números tiene cada una (la dirección de un número
es la de su colección más su número). La ficha de cada ejemplar y su portada solo se piden cuando el usuario abre uno,
y quedan en la base local para no volver a pedirlas.
"""
import json
import re
import sqlite3
import time
import urllib.error
import urllib.request
import zlib
from collections import defaultdict
from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from . import __version__
from .covers import thumbnail_bytes
from .gcd import fold
from .tbficha import (
    BASE,
    HOST,
    PARSER_VERSION,
    TbFicha,
    parse_ficha,
    slug_title,
    smart_title,
)

SCHEMA_VERSION = 1
MIN_INTERVAL = 1.5          # segundos entre peticiones: es el servidor de una asociación
TIMEOUT = 30
MAX_BYTES = 8_000_000        # lo que se acepta descargar (comprimido, si el servidor lo comprime)
MAX_UNPACKED = 60_000_000    # y lo que puede ocupar ya descomprimido
COVER_SIDE = 500            # lado mayor, en píxeles, de las portadas que se guardan
MAX_SITEMAPS = 40           # tope de seguridad al recorrer los sitemaps
USER_AGENT = f"comic-identify/{__version__} (herramienta personal de catalogación; consultas puntuales)"
# `series` y `numbers` se rehacen al volver a descargar el índice; lo demás (fichas, portadas y títulos reales ya
# consultados) se conserva siempre.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS series (slug TEXT PRIMARY KEY, title TEXT, folded TEXT, year TEXT, publisher TEXT,
                                   single INTEGER);
CREATE TABLE IF NOT EXISTS numbers (slug TEXT PRIMARY KEY, data BLOB);
CREATE TABLE IF NOT EXISTS real_titles (slug TEXT PRIMARY KEY, title TEXT, folded TEXT);
CREATE TABLE IF NOT EXISTS fichas (page TEXT PRIMARY KEY, fetched_at TEXT, parser_version INTEGER, html BLOB,
                                   data TEXT, barcode TEXT);
CREATE TABLE IF NOT EXISTS covers (image TEXT PRIMARY KEY, fetched_at TEXT, data BLOB);
CREATE INDEX IF NOT EXISTS series_folded ON series (folded);
"""
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
_SITEMAP_LINE = re.compile(r"^\s*Sitemap:\s*(\S+)", re.IGNORECASE | re.MULTILINE)


class TebeosferaError(Exception):
    """No se pudo descargar o leer una página de Tebeosfera."""


@dataclass(frozen=True)
class Entry:
    slug: str           # «universo_dc_1989_zinco»
    title: str          # «Universo Dc (1989, Zinco)»: sale de la dirección (o de la ficha, si ya se consultó)
    year: str = ""
    publisher: str = ""
    single: bool = False  # un número único (un libro, un especial): la colección no tiene más que su ficha

    @property
    def page(self) -> str:
        """La página de la colección (o, si es un número único, la de su ficha)."""
        return f"numeros/{self.slug}.html" if self.single else f"colecciones/{self.slug}.html"

    @property
    def url(self) -> str:
        return BASE + self.page

    @property
    def is_single_issue(self) -> bool:
        return self.single


@dataclass(frozen=True)
class Issue:
    label: str          # «10», «variante_2»
    page: str           # «numeros/universo_dc_1989_zinco_10.html»


def ficha_page(url: str) -> str:
    """La ruta relativa («numeros/x.html») si `url` es la ficha de un número de Tebeosfera; si no, vacío."""
    parsed = urlparse(url or "")
    if parsed.hostname != HOST or not re.fullmatch(r"/numeros/[^/]+\.html/?", parsed.path):
        return ""
    return parsed.path.strip("/")


def page_slug(page: str) -> str:
    return re.sub(r"^.*/|\.html/?$", "", page)


class Fetcher:
    """Descarga páginas de la web con pausa entre peticiones; nunca sale de su servidor."""

    def __init__(self, min_interval: float = MIN_INTERVAL):
        self.min_interval = min_interval
        self._last = float("-inf")   # aún no hubo petición: la primera no espera (monotonic arranca con el equipo)

    def get(self, url: str) -> bytes:
        if urlparse(url).netloc != HOST:
            raise TebeosferaError(f"Solo se consulta {HOST}, no «{url}».")
        wait = self._last + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        # se pide comprimido (los sitemaps pasan de 8 MB sin comprimir y así son unos 800 KB): menos carga para su servidor
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                data = response.read(MAX_BYTES + 1)
                packed = response.headers.get("Content-Encoding", "").lower() == "gzip"
        except (urllib.error.URLError, OSError) as error:
            raise TebeosferaError(f"No se pudo descargar {url}: {error}") from error
        finally:
            self._last = time.monotonic()
        if len(data) > MAX_BYTES:
            raise TebeosferaError(f"{url} es demasiado grande.")
        if packed:
            try:
                unpacker = zlib.decompressobj(16 + zlib.MAX_WBITS)
                data = unpacker.decompress(data, MAX_UNPACKED + 1)
            except zlib.error as error:
                raise TebeosferaError(f"{url} llegó dañado: {error}") from error
            if len(data) > MAX_UNPACKED:
                raise TebeosferaError(f"{url} es demasiado grande.")
        return data


def decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _sitemap_urls(robots: str) -> list[str]:
    found = _SITEMAP_LINE.findall(robots)
    return [u for u in found if urlparse(u).netloc == HOST] or [f"{BASE}sitemap{n}.xml" for n in range(1, MAX_SITEMAPS)]


def parse_sitemaps(pages: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    """(colecciones, números de cada una) de los sitemaps: «publicaciones/x.html» son las colecciones y
    «numeros/x_10.html» sus números (la dirección es la de la colección más «_» y el número; un número único usa la de
    su colección tal cual). Lo que no encaje en ninguna colección se ignora."""
    collections: list[str] = []
    numbers: list[str] = []
    for text in pages:
        for url in _LOC.findall(text):
            kind, _, name = url.removeprefix(BASE).partition("/")
            name = re.sub(r"\.html/?$", "", name)
            if kind == "publicaciones" and name:
                collections.append(name)
            elif kind == "numeros" and name:
                numbers.append(name)
    known = set(collections)
    found: dict[str, list[str]] = defaultdict(list)
    for name in numbers:
        if name in known:
            found[name].append("")
            continue
        parts = name.split("_")
        for cut in range(len(parts) - 1, 0, -1):
            slug = "_".join(parts[:cut])
            if slug in known:
                found[slug].append("_".join(parts[cut:]))
                break
    return collections, found


def build_index(target: Path, fetch: Callable[[str], bytes] | None = None,
                progress: Callable[[str], None] = lambda _: None) -> int:
    """Descarga los sitemaps y guarda las colecciones y sus números en `target`; devuelve cuántas colecciones. Todo se
    descarga antes de tocar la base y se sustituye en una sola transacción: si algo falla, el índice anterior sigue
    igual. Las fichas y portadas ya consultadas no se tocan."""
    fetch = Fetcher().get if fetch is None else fetch
    progress("Buscando los sitemaps de Tebeosfera…")
    try:
        robots = decode(fetch(BASE + "robots.txt"))
    except TebeosferaError:
        robots = ""
    pages: list[str] = []
    wanted = 0
    for number, url in enumerate(_sitemap_urls(robots)[:MAX_SITEMAPS], 1):
        progress(f"Descargando el índice de Tebeosfera (sitemap {number})…")
        text = decode(fetch(url))
        useful = "/publicaciones/" in text or "/numeros/" in text
        if useful:
            pages.append(text)
            wanted += 1
        elif wanted:
            break     # los sitemaps de colecciones y números van seguidos: al primero de otra cosa, se acabó
    collections, numbers = parse_sitemaps(pages)
    if not collections:
        raise TebeosferaError("Los sitemaps de Tebeosfera no traen ninguna colección: ¿ha cambiado la web?")
    progress(f"Guardando {len(collections)} colecciones…")
    rows = []
    for slug in collections:
        name, year, publisher, subtitle = slug_title(slug)
        title = f"{name} ({', '.join(p for p in (year, publisher) if p)})" + (f" -{subtitle}-" if subtitle else "")
        found = numbers.get(slug, [])
        rows.append((slug, title, fold(f"{name} {publisher} {subtitle} {year}"), year, publisher, int(found == [""])))
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(target)) as db:
        db.executescript(_SCHEMA)
        with db:
            db.execute("DELETE FROM series")
            db.execute("DELETE FROM numbers")
            db.executemany("INSERT INTO series VALUES (?, ?, ?, ?, ?, ?)", rows)
            db.executemany("INSERT INTO numbers VALUES (?, ?)",
                           [(slug, zlib.compress(json.dumps(sorted(found), ensure_ascii=False).encode()))
                            for slug, found in numbers.items() if found != [""]])
            db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return len(collections)


def _like(token: str) -> str:
    return "%" + token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _sort_key(label: str) -> tuple[int, int, str]:
    digits = re.fullmatch(r"0*(\d+)", label)
    return (0, int(digits.group(1)), "") if digits else (1, 0, label)


class TebeosferaIndex:
    def __init__(self, path: Path):
        self.path = path

    def is_ready(self) -> bool:
        if not self.path.exists():
            return False
        try:
            with closing(sqlite3.connect(self.path)) as db:
                return db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        except sqlite3.DatabaseError:
            return False

    def counts(self) -> dict[str, int]:
        """(colecciones, números) del índice."""
        with closing(sqlite3.connect(self.path)) as db:
            collections = db.execute("SELECT COUNT(*) FROM series").fetchone()[0]
            numbers = sum(len(json.loads(zlib.decompress(row[0]))) for row in db.execute("SELECT data FROM numbers"))
            singles = db.execute("SELECT COUNT(*) FROM series WHERE single = 1").fetchone()[0]
        return {"colecciones": collections, "números": numbers + singles}

    def search(self, text: str, limit: int = 30, publisher: str = "") -> list[Entry]:
        """Colecciones cuyo título contiene todas las palabras de `text` (sin tildes ni mayúsculas); «spider man» también
        encuentra «Spiderman». `publisher` acota por editorial (contiene). Primero las que empiezan por lo escrito."""
        tokens = re.findall(r"\w+", fold(text))[:6]
        if not tokens:
            return []
        variants = [tokens]
        if len(tokens) >= 2:
            variants.append([tokens[0] + tokens[1], *tokens[2:]])
        wanted = fold(publisher.strip())
        found: dict[str, tuple[int, int, Entry]] = {}
        with closing(sqlite3.connect(self.path)) as db:
            for variant in variants:
                clause = " AND ".join("(s.folded || ' ' || IFNULL(r.folded, '')) LIKE ? ESCAPE '\\'" for _ in variant)
                rows = db.execute(
                    "SELECT s.slug, IFNULL(r.title, s.title), s.year, s.publisher, s.single, s.folded, "
                    "IFNULL(r.folded, '') FROM series s LEFT JOIN real_titles r ON r.slug = s.slug "
                    f"WHERE {clause}", [_like(t) for t in variant]).fetchall()
                for slug, title, year, pub, single, folded, real in rows:
                    if wanted and wanted not in fold(pub):
                        continue
                    starts = 0 if (real or folded).startswith(variant[0]) else 1
                    found.setdefault(slug, (starts, len(title), Entry(slug, title, year, pub, bool(single))))
        return [item[2] for item in sorted(found.values(), key=lambda item: item[:2])][:limit]

    def get_entry(self, slug: str) -> Entry | None:
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT s.slug, IFNULL(r.title, s.title), s.year, s.publisher, s.single FROM series s "
                             "LEFT JOIN real_titles r ON r.slug = s.slug WHERE s.slug = ?", (slug,)).fetchone()
        return Entry(row[0], row[1], row[2], row[3], bool(row[4])) if row else None

    def numbers_of(self, slug: str) -> list[str]:
        """Los números («10», «variante_2») que el sitemap daba para esa colección, ordenados; vacío si no hay."""
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT data FROM numbers WHERE slug = ?", (slug,)).fetchone()
        return sorted(json.loads(zlib.decompress(row[0])), key=_sort_key) if row else []

    def set_real_title(self, slug: str, title: str) -> None:
        """El título de una colección tal como lo escribe su ficha (con tildes), para mostrarlo y buscarlo."""
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT OR REPLACE INTO real_titles VALUES (?, ?, ?)", (slug, title, fold(title)))

    def get_ficha(self, page: str) -> TbFicha | None:
        """La ficha guardada de esa página; si se leyó con una versión anterior del lector, se vuelve a leer del HTML
        original guardado (sin volver a pedirlo a la web)."""
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT parser_version, html, data FROM fichas WHERE page = ?", (page,)).fetchone()
            if row is None:
                return None
            version, packed, data = row
            if version == PARSER_VERSION:
                return TbFicha(**json.loads(data))
            ficha = parse_ficha(decode(zlib.decompress(packed)), BASE + page)
            with db:
                db.execute("UPDATE fichas SET parser_version = ?, data = ?, barcode = ? WHERE page = ?",
                           (PARSER_VERSION, json.dumps(asdict(ficha), ensure_ascii=False), ficha.isbn or ficha.gtin,
                            page))
            return ficha

    def store_ficha(self, page: str, raw: bytes, ficha: TbFicha) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript(_SCHEMA)
            db.execute("INSERT OR REPLACE INTO fichas VALUES (?, ?, ?, ?, ?, ?)",
                       (page, datetime.now().astimezone().isoformat(timespec="seconds"), PARSER_VERSION,
                        zlib.compress(raw), json.dumps(asdict(ficha), ensure_ascii=False), ficha.isbn or ficha.gtin))

    def get_cover(self, image: str) -> bytes | None:
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript(_SCHEMA)
            row = db.execute("SELECT data FROM covers WHERE image = ?", (image,)).fetchone()
            return row[0] if row else None

    def store_cover(self, image: str, data: bytes) -> None:
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript(_SCHEMA)
            with db:
                db.execute("INSERT OR REPLACE INTO covers VALUES (?, ?, ?)",
                           (image, datetime.now().astimezone().isoformat(timespec="seconds"), data))

    def by_barcode(self, code: str) -> list[str]:
        """Páginas de las fichas ya guardadas con ese ISBN o código de barras (solo dígitos)."""
        digits = re.sub(r"\D", "", code)
        if not digits:
            return []
        with closing(sqlite3.connect(self.path)) as db:
            return [row[0] for row in db.execute("SELECT page FROM fichas WHERE barcode = ?", (digits,))]


class TebeosferaClient:
    """Consulta bajo demanda: cada página se descarga una sola vez y queda en la base local."""

    def __init__(self, index: TebeosferaIndex, fetch: Callable[[str], bytes] | None = None):
        self.index = index
        self.fetch = Fetcher().get if fetch is None else fetch

    def issues(self, entry: Entry) -> list[Issue]:
        """Los números de la colección según el índice (una colección de número único es su propio y único número)."""
        if entry.single:
            return [Issue(entry.title, entry.page)]
        return [Issue(label, f"numeros/{entry.slug}_{label}.html") for label in self.index.numbers_of(entry.slug)]

    def find_issue(self, entry: Entry, number: str) -> Issue | None:
        """El número `number` de la colección («07» y «7» son el mismo); en un número único, el único que hay. Si el
        índice no conoce los números de esa colección (es posterior al sitemap), se prueba la dirección
        `colección_número`, que la web sirve igual."""
        if entry.single:
            return self.issues(entry)[0]
        wanted = number.strip().lstrip("0") or number.strip()
        if not wanted:
            return None
        known = self.index.numbers_of(entry.slug)
        for label in known:
            if label.strip().lstrip("0") == wanted or label == number.strip():
                return Issue(label, f"numeros/{entry.slug}_{label}.html")
        if known:
            return None
        return Issue(wanted, f"numeros/{entry.slug}_{wanted}.html")

    def nearest(self, entry: Entry, number: str, limit: int = 30) -> list[Issue]:
        """Números de la colección para elegir a mano cuando no está el escrito: los más cercanos a él si es un número
        (el resto, por orden)."""
        issues = self.issues(entry)
        wanted = int(number) if number.strip().isdigit() else None
        if wanted is not None:
            def distance(issue: Issue) -> tuple[int, str]:
                digits = re.fullmatch(r"0*(\d+)", issue.label)
                return (abs(int(digits.group(1)) - wanted) if digits else 10**9), issue.label
            issues = sorted(issues, key=distance)
        return sorted(issues[:limit], key=lambda i: _sort_key(i.label))

    def cover(self, image: str, refresh: bool = False) -> bytes:
        """La portada de una ficha (dirección absoluta), reducida a `COVER_SIDE` px: se descarga una vez y queda en la
        base local (las originales pesan más de lo que hace falta para la huella y la miniatura)."""
        if not refresh and (known := self.index.get_cover(image)) is not None:
            return known
        small = thumbnail_bytes(self.fetch(image), COVER_SIDE)
        if small is None:
            raise TebeosferaError(f"«{image}» no es una imagen válida.")
        self.index.store_cover(image, small)
        return small

    def ficha(self, page: str, refresh: bool = False) -> TbFicha:
        if not refresh and (known := self.index.get_ficha(page)) is not None:
            return known
        raw = self.fetch(BASE + page)
        ficha = parse_ficha(decode(raw), BASE + page)
        if not ficha.collection_slug and not ficha.series:
            raise TebeosferaError(f"«{page}» no parece una ficha de Tebeosfera (¿no existe ese número?).")
        self.index.store_ficha(page, raw, ficha)
        if ficha.collection_slug and ficha.collection_title:
            self.index.set_real_title(ficha.collection_slug, smart_title(ficha.collection_title))
        return ficha
