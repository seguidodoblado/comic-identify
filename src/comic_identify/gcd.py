"""Fuente Grand Comics Database (comics.org, CC BY-SA 4.0): índice local de ediciones en español.

Se importa una sola vez desde el volcado SQLite oficial y se conserva solo lo publicado en España
o en español, que es una fracción pequeña del volcado completo.
"""
import re
import sqlite3
import unicodedata
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

ISSUE_URL = "https://www.comics.org/issue/{}/"
SERIES_URL = "https://www.comics.org/series/{}/covers/"   # galería de portadas de la serie
_REQUIRED = ("gcd_issue", "gcd_series", "gcd_publisher", "gcd_brand", "gcd_issue_brand_emblem",
             "stddata_country", "stddata_language")
SCHEMA_VERSION = 2  # 2: sello editorial (brand) en cada número
_SCHEMA = """
CREATE TABLE series (id INTEGER PRIMARY KEY, name TEXT, publisher TEXT, country TEXT,
                     year_began INTEGER, year_ended INTEGER, issue_count INTEGER);
CREATE TABLE issues (id INTEGER PRIMARY KEY, series_id INTEGER, number TEXT, title TEXT,
                     barcode TEXT, isbn TEXT, key_date TEXT, is_variant INTEGER, brand TEXT);
CREATE VIRTUAL TABLE series_fts USING fts5(name, tokenize='unicode61 remove_diacritics 2');
"""
_INDEXES = """
CREATE INDEX issues_series ON issues (series_id, number);
CREATE INDEX issues_barcode ON issues (barcode) WHERE barcode <> '';
"""


@dataclass
class GcdHit:
    series: str
    publisher: str
    years: str
    number: str = ""            # vacío si solo se conoce la serie
    title: str = ""
    date: str = ""
    issue_id: int | None = None
    country: str = ""
    brand: str = ""             # sello editorial, p. ej. "Forum; Marvel Comics"
    series_id: int | None = None

    @property
    def url(self) -> str:
        """Ficha del número; si solo se conoce la serie, la galería de portadas de la serie."""
        if self.issue_id:
            return ISSUE_URL.format(self.issue_id)
        return SERIES_URL.format(self.series_id) if self.series_id else ""


def fold(text: str) -> str:
    """Minúsculas y sin tildes, para comparar «Vértice» con «vertice»."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


def _in_years(began, ended, year: int) -> bool:
    return (not began or began <= year) and (not ended or year <= ended)


def _years(began, ended) -> str:
    return f"{began or '?'}–{ended or ''}".rstrip("–") if began or ended else ""


def build_index(source: Path, target: Path, progress: Callable[[str], None] = lambda _: None,
                batch: int = 20000) -> tuple[int, int]:
    """Crea `target` a partir del volcado SQLite de GCD. Devuelve (series, números)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp")
    temp.unlink(missing_ok=True)
    origin = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        with closing(origin), closing(sqlite3.connect(temp)) as out:
            tables = {r[0] for r in origin.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if missing := [t for t in _REQUIRED if t not in tables]:
                raise ValueError(f"No parece un volcado SQLite de GCD (faltan: {', '.join(missing)}).")
            spain = origin.execute("SELECT id FROM stddata_country WHERE code = 'es'").fetchone()
            spanish = origin.execute("SELECT id FROM stddata_language WHERE code = 'es'").fetchone()
            if not spain or not spanish:
                raise ValueError("El volcado no contiene España o el idioma español.")
            wanted = "s.deleted = 0 AND (s.country_id = ? OR s.language_id = ?)"
            params = (spain[0], spanish[0])
            out.executescript(_SCHEMA)

            progress("Importando series…")
            series = origin.execute(
                "SELECT s.id, s.name, p.name, c.code, s.year_began, s.year_ended, s.issue_count "
                "FROM gcd_series s JOIN gcd_publisher p ON p.id = s.publisher_id "
                f"JOIN stddata_country c ON c.id = s.country_id WHERE {wanted}", params).fetchall()
            out.executemany("INSERT INTO series VALUES (?, ?, ?, ?, ?, ?, ?)", series)
            out.executemany("INSERT INTO series_fts(rowid, name) VALUES (?, ?)", [(r[0], r[1]) for r in series])

            progress("Importando sellos…")
            brands = dict(origin.execute(
                "SELECT e.issue_id, GROUP_CONCAT(DISTINCT b.name) FROM gcd_issue_brand_emblem e "
                "JOIN gcd_brand b ON b.id = e.brand_id AND b.deleted = 0 JOIN gcd_issue i ON i.id = e.issue_id "
                f"JOIN gcd_series s ON s.id = i.series_id WHERE i.deleted = 0 AND {wanted} "
                "GROUP BY e.issue_id", params))

            total = 0
            cursor = origin.execute(
                "SELECT i.id, i.series_id, i.number, i.title, i.barcode, i.isbn, i.key_date, "
                "i.variant_of_id IS NOT NULL FROM gcd_issue i JOIN gcd_series s ON s.id = i.series_id "
                f"WHERE i.deleted = 0 AND {wanted}", params)
            while rows := cursor.fetchmany(batch):
                out.executemany("INSERT INTO issues VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [
                    (i, sid, number, title or "", re.sub(r"\D", "", barcode or ""), isbn or "",
                     key_date or "", variant, brands.get(i, ""))
                    for i, sid, number, title, barcode, isbn, key_date, variant in rows])
                total += len(rows)
                progress(f"Importando números… {total}")
            progress("Creando índices…")
            out.executescript(_INDEXES)
            out.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            out.commit()
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    temp.replace(target)
    return len(series), total


@dataclass
class SeriesInfo:
    id: int
    name: str
    publisher: str
    country: str
    year_began: int | None
    year_ended: int | None
    issue_count: int
    brand: str = ""     # el sello más frecuente entre los números de la serie


class GcdIndex:
    def __init__(self, path: Path):
        self.path = path

    def is_ready(self) -> bool:
        """Existe y tiene el esquema actual (un índice antiguo hay que volver a importarlo)."""
        if not self.path.exists():
            return False
        try:
            with closing(sqlite3.connect(self.path)) as db:
                return db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        except sqlite3.DatabaseError:
            return False

    def counts(self) -> tuple[int, int]:
        with closing(sqlite3.connect(self.path)) as db:
            return (db.execute("SELECT COUNT(*) FROM series").fetchone()[0],
                    db.execute("SELECT COUNT(*) FROM issues").fetchone()[0])

    def search(self, text: str, number: str = "", limit: int = 12, publisher: str = "",
               year: str = "") -> list[GcdHit]:
        """Series cuyo nombre encaja con `text`; con `number`, solo los números que existen.

        `publisher` acota por editorial o por sello («Forum», «Panini»…) y `year` por el año de la serie
        (o el del número, si se pide uno concreto).
        """
        tokens = re.findall(r"\w+", text.lower())[:6]
        if not tokens:
            return []
        quoted = [f'"{t}"*' for t in tokens]
        strict = [" AND ".join(quoted)]
        if len(tokens) >= 2:  # "spider man" también debe encontrar "Spiderman"
            strict.append(" AND ".join([f'"{tokens[0]}{tokens[1]}"*', *quoted[2:]]))
        loose = " OR ".join(quoted)  # último recurso: cualquiera de las palabras
        args = (" ".join(tokens), number, limit, fold(publisher.strip()),
                int(year) if year.strip().isdigit() else None)
        with closing(sqlite3.connect(self.path)) as db:
            found = [h for match in strict for h in self._hits(db, match, *args)]
            # Último recurso (cualquier palabra del título), solo sin filtros: con editorial o año, si nada
            # cumple, el resultado correcto es «ninguno» y no series sin relación.
            if not found and loose not in strict and not (args[3] or args[4]):
                found = self._hits(db, loose, *args)
        unique: dict = {}
        for hit in found:
            unique.setdefault(hit.issue_id or (hit.series, hit.publisher, hit.years), hit)
        ordered = sorted(unique.values(), key=lambda h: h.country != "es")  # estable: España primero
        return ordered[:limit]

    @staticmethod
    def _hits(db, match: str, exact: str, number: str, limit: int, publisher: str,
              year: int | None) -> list[GcdHit]:
        rows = db.execute(
            "SELECT s.id, s.name, s.publisher, s.year_began, s.year_ended, s.country FROM series_fts f "
            "JOIN series s ON s.id = f.rowid WHERE series_fts MATCH ? "
            "ORDER BY bm25(series_fts), s.issue_count DESC LIMIT ?",
            (match, 300 if publisher or year else 60)).fetchall()
        rows.sort(key=lambda r: " ".join(re.findall(r"\w+", r[1].lower())) != exact)
        hits: list[GcdHit] = []
        for sid, name, series_publisher, began, ended, country in rows:
            if year and not _in_years(began, ended, year):
                continue
            by_publisher = not publisher or publisher in fold(series_publisher)
            if not number:
                if not by_publisher and not db.execute(
                        "SELECT 1 FROM issues WHERE series_id = ? AND brand LIKE ? LIMIT 1",
                        (sid, f"%{publisher}%")).fetchone():
                    continue
                hits.append(GcdHit(name, series_publisher, _years(began, ended), country=country, series_id=sid))
                continue
            for iid, title, date, brand in db.execute(
                    "SELECT id, title, key_date, brand FROM issues WHERE series_id = ? AND number = ? "
                    "AND is_variant = 0", (sid, number)):
                if year and date[:4].isdigit() and int(date[:4]) != year:
                    continue
                if not by_publisher and publisher not in fold(brand):
                    continue
                hits.append(GcdHit(name, series_publisher, _years(began, ended), number, title, date, iid,
                                   country, brand, sid))
            if len(hits) >= limit:
                break
        return hits[:limit]

    def series_info(self, series_id: int) -> SeriesInfo | None:
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT id, name, publisher, country, year_began, year_ended, issue_count "
                             "FROM series WHERE id = ?", (series_id,)).fetchone()
            if row is None:
                return None
            brand = db.execute("SELECT brand FROM issues WHERE series_id = ? AND brand <> '' "
                               "GROUP BY brand ORDER BY COUNT(*) DESC LIMIT 1", (series_id,)).fetchone()
        return SeriesInfo(*row, brand=brand[0] if brand else "")

    def by_barcode(self, digits: str) -> list[GcdHit]:
        digits = re.sub(r"\D", "", digits)
        if not digits:
            return []
        with closing(sqlite3.connect(self.path)) as db:
            return [GcdHit(name, publisher, _years(began, ended), number, title, date, iid, brand=brand)
                    for iid, number, title, date, brand, name, publisher, began, ended in db.execute(
                        "SELECT i.id, i.number, i.title, i.key_date, i.brand, s.name, s.publisher, "
                        "s.year_began, s.year_ended FROM issues i JOIN series s ON s.id = i.series_id "
                        "WHERE i.barcode = ? ORDER BY i.is_variant LIMIT 5", (digits,))]
