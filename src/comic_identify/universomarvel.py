"""Fuente fichas.universomarvel.com: catálogo de las ediciones españolas de Marvel (Forum/Planeta, Panini, Vértice…).

Es una web personal, sin API ni volcado y con publicidad, así que NO se rastrea entera: aquí solo se descarga el
índice de series (una página por editorial: unas pocas peticiones, con pausa entre ellas y una identificación
honesta) y se guarda en una base local para buscar al escribir. Las fichas de cada ejemplar se pedirán solo cuando
el usuario abra una.
"""
import html
import json
import re
import sqlite3
import time
import urllib.error
import urllib.request
import zlib
from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

from . import __version__
from .gcd import fold
from .umficha import (
    PARSER_VERSION,
    Ficha,
    SeriesIssue,
    Story,
    Subpage,
    UsaRef,
    parse_ficha,
    parse_series_page,
    parse_series_subpages,
    subpages_for,
)

HOST = "fichas.universomarvel.com"
BASE = f"https://{HOST}/"
PUBLISHERS = {"Forum/Planeta": "forum.html", "Panini": "panini.html", "Vértice": "vertice.html"}
# Editorial y sello de cada colección (tus dos datos distintos al normalizar): el sello es lo impreso en el ejemplar y
# la editorial quien lo publica. Solo se rellena lo que se sabe con certeza; el resto se completa a mano al normalizar.
EDITION_BY_PUBLISHER = {"Forum/Planeta": ("Planeta DeAgostini", "Forum"), "Panini": ("Panini Comics", ""),
                        "Vértice": ("Ediciones Vértice", "")}
SCHEMA_VERSION = 1
MIN_INTERVAL = 1.5          # segundos entre peticiones: es un servidor pequeño
TIMEOUT = 20
MAX_BYTES = 5_000_000
USER_AGENT = f"comic-identify/{__version__} (herramienta personal de catalogación; consultas puntuales)"
# `series` se rehace al volver a descargar el índice; lo demás (números y fichas ya consultados) se conserva siempre.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS series (id INTEGER PRIMARY KEY, publisher TEXT, section TEXT, title TEXT, folded TEXT,
                                   page TEXT, UNIQUE (publisher, title, page));
CREATE TABLE IF NOT EXISTS series_issues (series_page TEXT, position INTEGER, group_title TEXT, label TEXT, page TEXT,
                                          PRIMARY KEY (series_page, position));
CREATE TABLE IF NOT EXISTS series_subpages (series_page TEXT, position INTEGER, label TEXT, page TEXT,
                                            PRIMARY KEY (series_page, position));
CREATE TABLE IF NOT EXISTS series_fetched (series_page TEXT PRIMARY KEY, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS fichas (page TEXT PRIMARY KEY, fetched_at TEXT, parser_version INTEGER, html BLOB,
                                   data TEXT, barcode TEXT);
CREATE INDEX IF NOT EXISTS fichas_barcode ON fichas (barcode) WHERE barcode <> '';
"""
_SECTION_OR_OPTION = re.compile(r"<H2[^>]*>(.*?)</H2>|<option([^>]*)>(.*?)</option>", re.DOTALL | re.IGNORECASE)
_VALUE = re.compile(r'value\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
_CHARSET = re.compile(rb'charset\s*=\s*["\']?([\w-]+)', re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")


class UniversoMarvelError(Exception):
    """No se pudo descargar o leer el índice."""


@dataclass(frozen=True)
class Entry:
    publisher: str
    section: str        # «Series Regulares y Limitadas», «Especiales», «Formato Bolsillo»…
    title: str          # «Alpha Flight vol.1»
    page: str           # ruta relativa a la web: «aphff_v1.html» (o «esp/alertap.html» si es una ficha suelta)

    @property
    def url(self) -> str:
        return urljoin(BASE, self.page)

    @property
    def is_single_issue(self) -> bool:
        """Una ficha suelta (un especial, un número único) y no la página de una serie con su lista de números."""
        return self.page.startswith("esp/")


_VOLUME = re.compile(r"^(?P<name>.+?)\s+vol\.?\s*(?P<volume>\d+)\b\s*(?P<rest>.*)$", re.IGNORECASE)
_TITLE_NUMBER = re.compile(r"^(?P<series>.+?\s+vol\.?\s*\d+)\s+n[º°o]\s*\.?\s*(?P<number>\S.*)$", re.IGNORECASE)


def split_volume(title: str) -> tuple[str, str]:
    """«Spiderman vol.2» -> («Spiderman», «2»); sin «vol.N», (título, «»). El volumen 1 se deja vacío: solo importa
    cuando hay un reinicio de numeración."""
    match = _VOLUME.match(title.strip())
    if not match or match.group("rest").strip():
        return title.strip(), ""
    return match.group("name").strip(), "" if match.group("volume") == "1" else match.group("volume")


def split_ficha_title(title: str) -> tuple[str, str]:
    """«Spiderman vol.1 nº 301» -> («Spiderman vol.1», «301»); si no tiene número, (título, «»)."""
    match = _TITLE_NUMBER.match(title.strip())
    return (match.group("series").strip(), match.group("number").strip()) if match else (title.strip(), "")


def decode(data: bytes) -> str:
    """El texto de una página. La web declara ISO-8859-1 en unas páginas y nada en otras, pero en todas usa el € y las
    comillas de Windows-1252 (como hace un navegador con ese «ISO-8859-1»), que es lo que se lee."""
    match = _CHARSET.search(data[:2048])
    declared = match.group(1).decode("ascii", "replace").lower() if match else ""
    charset = "cp1252" if declared in ("", "iso-8859-1", "latin-1", "latin1", "windows-1252") else declared
    try:
        return data.decode(charset, errors="replace")
    except LookupError:
        return data.decode("cp1252", errors="replace")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAGS.sub("", text))).strip()


def parse_index(data: bytes, publisher: str) -> list[Entry]:
    """Las series que lista la página de una editorial: cada `<option value="página.html">Título</option>`, con la
    sección (`<H2>`) bajo la que aparece. Se ignoran los que no llevan una página `.html` propia."""
    section, found, seen = "", [], set()
    for match in _SECTION_OR_OPTION.finditer(decode(data)):
        if match.group(1) is not None:
            section = _clean(match.group(1))
            continue
        value = _VALUE.search(match.group(2))
        title = _clean(match.group(3))
        if not value or not title or not value.group(1).lower().endswith(".html"):
            continue
        entry = Entry(publisher, section, title, value.group(1).strip())
        if (entry.title, entry.page) not in seen:
            seen.add((entry.title, entry.page))
            found.append(entry)
    return found


class Fetcher:
    """Descarga páginas de la web con pausa entre peticiones; nunca sale de su servidor."""

    def __init__(self, min_interval: float = MIN_INTERVAL):
        self.min_interval = min_interval
        self._last = 0.0

    def get(self, url: str) -> bytes:
        if urlparse(url).netloc != HOST:
            raise UniversoMarvelError(f"Solo se consulta {HOST}, no «{url}».")
        wait = self._last + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                data = response.read(MAX_BYTES + 1)
        except (urllib.error.URLError, OSError) as error:
            raise UniversoMarvelError(f"No se pudo descargar {url}: {error}") from error
        finally:
            self._last = time.monotonic()
        if len(data) > MAX_BYTES:
            raise UniversoMarvelError(f"{url} es demasiado grande.")
        return data


def build_index(target: Path, publishers: dict[str, str] | None = None, fetch: Callable[[str], bytes] | None = None,
                progress: Callable[[str], None] = lambda _: None) -> int:
    """Descarga las páginas de las editoriales y guarda sus series en `target`; devuelve cuántas. Todo se descarga
    antes de tocar la base y se sustituye en una sola transacción: si algo falla (o una página viene vacía), el
    índice anterior sigue igual. Las fichas ya consultadas no se tocan."""
    publishers = PUBLISHERS if publishers is None else publishers
    fetch = Fetcher().get if fetch is None else fetch
    entries: list[Entry] = []
    for number, (publisher, page) in enumerate(publishers.items(), 1):
        progress(f"Descargando el índice de {publisher} ({number}/{len(publishers)})…")
        found = parse_index(fetch(urljoin(BASE, page)), publisher)
        if not found:
            raise UniversoMarvelError(f"La página de {publisher} no trae ninguna serie: ¿ha cambiado la web?")
        entries += found
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(target)) as db:
        db.executescript(_SCHEMA)
        with db:
            db.execute("DELETE FROM series")
            db.executemany("INSERT INTO series (publisher, section, title, folded, page) VALUES (?, ?, ?, ?, ?)",
                           [(e.publisher, e.section, e.title, fold(e.title), e.page) for e in entries])
            db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return len(entries)


def _ficha_from_json(text: str) -> Ficha:
    data = json.loads(text)
    data["stories"] = [Story(**{**story, "usa": [UsaRef(**ref) for ref in story.get("usa", [])]})
                       for story in data.get("stories", [])]
    return Ficha(**data)


def _like(token: str) -> str:
    return "%" + token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class UniversoMarvelIndex:
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

    def issues_of(self, series_page: str) -> list[SeriesIssue] | None:
        """Los números de una página de serie ya consultada; None si aún no se ha descargado."""
        with closing(sqlite3.connect(self.path)) as db:
            if not db.execute("SELECT 1 FROM series_fetched WHERE series_page = ?", (series_page,)).fetchone():
                return None
            return [SeriesIssue(*row) for row in db.execute(
                "SELECT group_title, label, page FROM series_issues WHERE series_page = ? ORDER BY position",
                (series_page,))]

    def subpages_of(self, series_page: str) -> list[Subpage]:
        with closing(sqlite3.connect(self.path)) as db:
            return [Subpage(*row) for row in db.execute(
                "SELECT label, page FROM series_subpages WHERE series_page = ? ORDER BY position", (series_page,))]

    def store_issues(self, series_page: str, issues: list[SeriesIssue], subpages: list[Subpage] = ()) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM series_issues WHERE series_page = ?", (series_page,))
            db.execute("DELETE FROM series_subpages WHERE series_page = ?", (series_page,))
            db.executemany("INSERT INTO series_subpages VALUES (?, ?, ?, ?)",
                           [(series_page, n, sub.label, sub.page) for n, sub in enumerate(subpages)])
            db.executemany("INSERT INTO series_issues VALUES (?, ?, ?, ?, ?)",
                           [(series_page, n, i.group, i.label, i.page) for n, i in enumerate(issues)])
            db.execute("INSERT OR REPLACE INTO series_fetched VALUES (?, ?)",
                       (series_page, datetime.now().astimezone().isoformat(timespec="seconds")))

    def get_ficha(self, page: str) -> Ficha | None:
        """La ficha guardada de esa página; si se leyó con una versión anterior del lector, se vuelve a leer del HTML
        original guardado (sin volver a pedirlo a la web)."""
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT parser_version, html, data FROM fichas WHERE page = ?", (page,)).fetchone()
            if row is None:
                return None
            version, packed, data = row
            if version == PARSER_VERSION:
                return _ficha_from_json(data)
            ficha = parse_ficha(decode(zlib.decompress(packed)), urljoin(BASE, page))
            with db:
                db.execute("UPDATE fichas SET parser_version = ?, data = ?, barcode = ? WHERE page = ?",
                           (PARSER_VERSION, json.dumps(asdict(ficha), ensure_ascii=False), ficha.barcode, page))
            return ficha

    def store_ficha(self, page: str, raw: bytes, ficha: Ficha) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT OR REPLACE INTO fichas VALUES (?, ?, ?, ?, ?, ?)",
                       (page, datetime.now().astimezone().isoformat(timespec="seconds"), PARSER_VERSION,
                        zlib.compress(raw), json.dumps(asdict(ficha), ensure_ascii=False), ficha.barcode))

    def by_barcode(self, code: str) -> list[str]:
        """Páginas de las fichas ya guardadas con ese código de barras (solo dígitos)."""
        digits = re.sub(r"\D", "", code)
        if not digits:
            return []
        with closing(sqlite3.connect(self.path)) as db:
            return [row[0] for row in db.execute("SELECT page FROM fichas WHERE barcode = ?", (digits,))]

    def counts(self) -> dict[str, int]:
        """Series por editorial."""
        with closing(sqlite3.connect(self.path)) as db:
            return dict(db.execute("SELECT publisher, COUNT(*) FROM series GROUP BY publisher ORDER BY publisher"))

    def search(self, text: str, limit: int = 30, publisher: str = "") -> list[Entry]:
        """Series cuyo título contiene todas las palabras de `text` (sin tildes ni mayúsculas); «spider man» también
        encuentra «Spiderman». `publisher` acota por editorial (contiene). Primero los que empiezan por lo escrito."""
        tokens = re.findall(r"\w+", fold(text))[:6]
        if not tokens:
            return []
        variants = [tokens]
        if len(tokens) >= 2:
            variants.append([tokens[0] + tokens[1], *tokens[2:]])
        wanted = fold(publisher.strip())
        found: dict[tuple[str, str, str], tuple[int, int, Entry]] = {}
        with closing(sqlite3.connect(self.path)) as db:
            for variant in variants:
                clause = " AND ".join("folded LIKE ? ESCAPE '\\'" for _ in variant)
                rows = db.execute(f"SELECT publisher, section, title, page, folded FROM series WHERE {clause}",
                                  [_like(t) for t in variant]).fetchall()
                for pub, section, title, page, folded in rows:
                    if wanted and wanted not in fold(pub):
                        continue
                    starts = 0 if folded.startswith(variant[0]) else 1
                    found.setdefault((pub, title, page), (starts, len(title), Entry(pub, section, title, page)))
        return [item[2] for item in sorted(found.values(), key=lambda item: item[:2])][:limit]


class UniversoMarvelClient:
    """Consulta bajo demanda: cada página se descarga una sola vez y queda en la base local."""

    def __init__(self, index: UniversoMarvelIndex, fetch: Callable[[str], bytes] | None = None):
        self.index = index
        self.fetch = Fetcher().get if fetch is None else fetch

    def _load(self, key: str, url: str, title: str, refresh: bool = False) -> tuple[list[SeriesIssue], list[Subpage]]:
        """Los números (o, en series largas, las subpáginas por rangos) de una página de serie; se descarga una vez."""
        if not refresh and (known := self.index.issues_of(key)) is not None:
            return known, self.index.subpages_of(key)
        html = decode(self.fetch(url))
        issues = parse_series_page(html, url)
        subpages = [] if issues else parse_series_subpages(html, url)
        if not issues and not subpages:
            raise UniversoMarvelError(f"La página de «{title}» no trae ningún número: ¿ha cambiado la web?")
        self.index.store_issues(key, issues, subpages)
        return issues, subpages

    def series_issues(self, entry: Entry, refresh: bool = False) -> list[SeriesIssue]:
        """Los números que lista directamente la página de la serie (una entrada que ya es una ficha suelta, como un
        especial, es su único número). Las series largas los reparten en subpáginas: ver `find_issue`."""
        if entry.is_single_issue:
            return [SeriesIssue(entry.title, "", entry.page)]
        return self._load(entry.page, entry.url, entry.title, refresh)[0]

    def find_issue(self, entry: Entry, number: str) -> SeriesIssue | None:
        """El número `number` de la serie («07» y «7» son el mismo); en un especial suelto, el único que hay. Si la
        serie reparte sus números por rangos, solo se descarga la subpágina cuyo rango lo contiene."""
        if entry.is_single_issue:
            return self.series_issues(entry)[0]
        wanted = number.strip().lstrip("0") or number.strip()

        def match(issues):
            return next((i for i in issues if i.label.strip().lstrip("0") == wanted), None)
        issues, subpages = self._load(entry.page, entry.url, entry.title)
        if hit := match(issues):
            return hit
        for sub in subpages_for(subpages, number):
            if hit := match(self._load(sub.page, urljoin(BASE, sub.page), entry.title)[0]):
                return hit
        return None

    def ficha(self, page: str, refresh: bool = False) -> Ficha:
        if not refresh and (known := self.index.get_ficha(page)) is not None:
            return known
        url = urljoin(BASE, page)
        raw = self.fetch(url)
        ficha = parse_ficha(decode(raw), url)
        if not ficha.title:
            raise UniversoMarvelError(f"«{page}» no parece una ficha: ¿ha cambiado la web?")
        self.index.store_ficha(page, raw, ficha)
        return ficha
