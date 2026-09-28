"""Fuente Grand Comics Database (comics.org, CC BY-SA 4.0): índice local de ediciones en español.

Se importa una sola vez desde el volcado SQLite oficial y se conserva solo lo publicado en España
o en español, que es una fracción pequeña del volcado completo.
"""
import re
import sqlite3
import unicodedata
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

ISSUE_URL = "https://www.comics.org/issue/{}/"
SERIES_URL = "https://www.comics.org/series/{}/covers/"   # galería de portadas de la serie
_REQUIRED = ("gcd_issue", "gcd_series", "gcd_publisher", "gcd_brand", "gcd_issue_brand_emblem",
             "stddata_country", "stddata_language")
SCHEMA_VERSION = 3  # 2: sello editorial (brand) en cada número; 3: historias, créditos, precio y fecha de venta
_SCHEMA = """
CREATE TABLE series (id INTEGER PRIMARY KEY, name TEXT, publisher TEXT, country TEXT,
                     year_began INTEGER, year_ended INTEGER, issue_count INTEGER);
CREATE TABLE issues (id INTEGER PRIMARY KEY, series_id INTEGER, number TEXT, title TEXT,
                     barcode TEXT, isbn TEXT, key_date TEXT, is_variant INTEGER, brand TEXT,
                     price TEXT, on_sale TEXT);
CREATE TABLE stories (id INTEGER PRIMARY KEY, issue_id INTEGER, sequence INTEGER, type_id INTEGER, title TEXT,
                      genre TEXT, characters TEXT, synopsis TEXT);
CREATE TABLE credits (story_id INTEGER, role TEXT, name TEXT, inherited INTEGER);
CREATE VIRTUAL TABLE series_fts USING fts5(name, tokenize='unicode61 remove_diacritics 2');
"""
_INDEXES = """
CREATE INDEX issues_series ON issues (series_id, number);
CREATE INDEX issues_barcode ON issues (barcode) WHERE barcode <> '';
CREATE INDEX stories_issue ON stories (issue_id, sequence);
CREATE INDEX credits_story ON credits (story_id);
"""

# Tablas del volcado de las que salen las historias y los créditos (si falta alguna, el índice se crea sin ellos)
_STORY_TABLES = ("gcd_story", "gcd_story_credit", "gcd_credit_type", "gcd_creator", "gcd_creator_name_detail")
_ROLE_WORDS = ("script", "pencils", "inks", "colors", "letters", "editing")


def credit_roles(type_name: str) -> tuple[str, ...]:
    """Los papeles que abarca un tipo de crédito de GCD: «pencils and inks» -> lápiz y tinta; «painting» (pintura) ->
    lápiz y color; «script, pencils, and inks» -> guion, lápiz y tinta."""
    roles: list[str] = []
    for word in re.findall(r"[a-z]+", type_name.lower()):
        if word == "painting":
            roles += ["pencils", "colors"]
        elif word in _ROLE_WORDS:
            roles.append(word)
    return tuple(dict.fromkeys(roles))


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
            issue_columns = {r[1] for r in origin.execute("PRAGMA table_info(gcd_issue)")}
            extra_columns = ", ".join(f"i.{column}" if column in issue_columns else "NULL"
                                      for column in ("price", "on_sale_date"))

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
                f"i.variant_of_id IS NOT NULL, {extra_columns} FROM gcd_issue i JOIN gcd_series s ON s.id = i.series_id "
                f"WHERE i.deleted = 0 AND {wanted}", params)
            while rows := cursor.fetchmany(batch):
                out.executemany("INSERT INTO issues VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
                    (i, sid, number, title or "", re.sub(r"\D", "", barcode or ""), isbn or "",
                     key_date or "", variant, brands.get(i, ""), price or "", on_sale or "")
                    for i, sid, number, title, barcode, isbn, key_date, variant, price, on_sale in rows])
                total += len(rows)
                progress(f"Importando números… {total}")
            if all(table in tables for table in _STORY_TABLES):
                _import_stories(origin, out, wanted, params, progress)
            progress("Creando índices…")
            out.executescript(_INDEXES)
            out.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            out.commit()
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    temp.replace(target)
    return len(series), total


def _import_stories(origin, out, wanted: str, params: tuple, progress: Callable[[str], None]) -> None:
    """Historias (género, personajes, sinopsis) y créditos de los números importados. Los créditos salen del modelo nuevo
    de «creadores» de GCD (el que muestra su web); una historia sin créditos propios hereda los de la historia original
    de la que es reimpresión (`inherited` = 1), como cuando una edición española reúne material americano."""
    progress("Importando historias…")
    origin.execute("ATTACH ':memory:' AS m")
    origin.execute("CREATE TABLE m.st (id INTEGER PRIMARY KEY)")
    origin.execute("INSERT INTO m.st SELECT st.id FROM gcd_story st JOIN gcd_issue i ON i.id = st.issue_id "
                   f"JOIN gcd_series s ON s.id = i.series_id WHERE st.deleted = 0 AND i.deleted = 0 AND {wanted}", params)
    out.executemany("INSERT INTO stories VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
        (sid, issue, sequence, type_id, title or "", genre or "", characters or "", synopsis or "")
        for sid, issue, sequence, type_id, title, genre, characters, synopsis in origin.execute(
            "SELECT st.id, st.issue_id, st.sequence_number, st.type_id, st.title, st.genre, st.characters, "
            "st.synopsis FROM gcd_story st WHERE st.id IN (SELECT id FROM m.st)")))

    progress("Importando créditos…")
    roles = {type_id: credit_roles(name) for type_id, name in origin.execute("SELECT id, name FROM gcd_credit_type")}
    query = ("SELECT sc.story_id, sc.credit_type_id, c.gcd_official_name, sc.credit_name FROM gcd_story_credit sc "
             "JOIN gcd_creator_name_detail d ON d.id = sc.creator_id JOIN gcd_creator c ON c.id = d.creator_id "
             "WHERE sc.deleted = 0 AND c.deleted = 0 AND sc.story_id IN ({})")

    def credits_of(table: str, column: str) -> dict[int, dict[tuple[str, str], None]]:
        found: dict[int, dict[tuple[str, str], None]] = {}
        for story, type_id, name, note in origin.execute(query.format(f"SELECT {column} FROM {table}")):
            for role in roles.get(type_id, ()):
                # en GCD el traductor se anota como «guion» con la nota «traducción»: no es un guionista
                if role == "script" and re.search(r"traduc|translat", note or "", re.IGNORECASE):
                    role = "translator"
                found.setdefault(story, {})[(role, name.strip())] = None
        return found

    own = credits_of("m.st", "id")
    out.executemany("INSERT INTO credits VALUES (?, ?, ?, 0)",
                    ((story, role, name) for story, pairs in own.items() for role, name in pairs))
    origin.execute("CREATE TABLE m.origins (origin_id INTEGER PRIMARY KEY)")
    target_of: dict[int, list[int]] = {}
    for target, source in origin.execute("SELECT r.target_id, r.origin_id FROM gcd_reprint r "
                                         "WHERE r.target_id IN (SELECT id FROM m.st)"):
        if target not in own:
            target_of.setdefault(source, []).append(target)
    origin.executemany("INSERT OR IGNORE INTO m.origins VALUES (?)", ((source,) for source in target_of))
    inherited = credits_of("m.origins", "origin_id")
    done: set[int] = set()
    for source, targets in target_of.items():
        for target in targets:
            if source in inherited and target not in done:   # el primer original que tenga créditos
                done.add(target)
                out.executemany("INSERT INTO credits VALUES (?, ?, ?, 1)",
                                ((target, role, name) for role, name in inherited[source]))


# Tipos de «historia» de GCD que no aportan autores de contenido: portada, anuncios, cartas, índices, suplementos…
NON_CONTENT_TYPES = {2, 3, 6, 7, 8, 11, 12, 16, 17}
COVER_TYPE = 6
_PESETAS_PER_EURO = 166.386
# Géneros de GCD (en inglés) en español; el resto se deja como viene
GENRES = {"superhero": "superhéroes", "crime": "crimen", "adventure": "aventuras", "humor": "humor", "fantasy": "fantasía",
          "science fiction": "ciencia ficción", "historical": "histórico", "horror": "terror", "romance": "romance",
          "western": "western", "war": "bélico", "detective-mystery": "misterio", "sword & sorcery": "espada y brujería",
          "non-fiction": "no ficción", "biography": "biografía", "sports": "deportes", "animal": "animales",
          "teen": "adolescentes", "children": "infantil", "drama": "drama", "erotica": "erótico", "mystery": "misterio",
          "true crime": "crimen real", "religious": "religioso", "school": "escolar", "spy": "espionaje"}


@dataclass
class IssueDetails:
    """Lo que GCD sabe de un número, ya en la forma en que lo usan los metadatos."""
    credits: dict[str, str] = field(default_factory=dict)   # campo de ComicInfo -> nombres separados por coma
    genre: str = ""
    characters: str = ""
    summary: str = ""
    price: str = ""
    on_sale: str = ""
    key_date: str = ""
    barcode: str = ""
    isbn: str = ""
    story_lines: list[str] = field(default_factory=list)    # una línea por historia con sus autores (varios autores)
    inherited: bool = False                                 # algún crédito viene de la historia original reimpresa

    @property
    def date(self) -> tuple[str, str, str]:
        """(año, mes, día) de la fecha de portada; «» donde no se conoce (GCD escribe «2006-12-00»)."""
        parts = (self.key_date.split("-") + ["", "", ""])[:3]
        return tuple(part.lstrip("0") if part.strip("0") else "" for part in parts)   # type: ignore[return-value]

    @property
    def cost(self) -> str:
        """El precio en euros con punto decimal, si GCD lo da en euros o en pesetas («3.50 EUR», «150 ESP»); «» si no
        (otras monedas no se convierten: mezclarían monedas en una sola columna)."""
        for part in self.price.split(";"):
            match = re.match(r"\s*(\d+(?:[.,]\d+)?)\s*(EUR|ESP|€|pts?\.?|pesetas?)(?![A-Za-z])", part.strip(), re.IGNORECASE)
            if match:
                value = float(match.group(1).replace(",", "."))
                if match.group(2).upper() not in ("EUR", "€"):
                    value /= _PESETAS_PER_EURO
                return f"{value:.2f}"
        return ""


def _names(rows, *roles: str) -> list[str]:
    seen: dict[str, None] = {}
    for role, name in rows:
        if role in roles:
            seen.setdefault(name, None)
    return list(seen)


def _split(text: str) -> list[str]:
    """«Punisher [Frank Castle]; Micro; ?» -> [«Punisher», «Micro»]: sin identidades entre corchetes ni desconocidos."""
    return [name for name in (re.sub(r"\s*\[[^\]]*\]", "", part).strip() for part in text.split(";"))
            if name and name != "?"]


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

    def version(self) -> int:
        """La versión del esquema del índice; 0 si no existe o no es un índice."""
        if not self.path.exists():
            return 0
        try:
            with closing(sqlite3.connect(self.path)) as db:
                return db.execute("PRAGMA user_version").fetchone()[0]
        except sqlite3.DatabaseError:
            return 0

    def is_ready(self) -> bool:
        """Existe y se puede usar. Un índice de la versión 2 sigue valiendo para buscar, pero no trae historias ni
        créditos (`has_details`): hay que volver a importar el volcado para tenerlos."""
        return self.version() in (2, SCHEMA_VERSION)

    def has_details(self) -> bool:
        return self.version() == SCHEMA_VERSION

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

    def issue_details(self, issue_id: int) -> IssueDetails | None:
        """Créditos, género, personajes, sinopsis y datos del número `issue_id`; None si no existe o el índice es de
        una versión sin historias. Los autores de las historias se juntan sin repetir y en su orden en el número;
        la portada aporta el `CoverArtist` (lápiz y tinta) y no se mezcla con los autores del interior."""
        if not self.has_details():
            return None
        with closing(sqlite3.connect(self.path)) as db:
            issue = db.execute("SELECT key_date, price, on_sale, barcode, isbn FROM issues WHERE id = ?",
                               (issue_id,)).fetchone()
            if issue is None:
                return None
            key_date, price, on_sale, barcode, isbn = issue
            stories = db.execute("SELECT id, sequence, type_id, title, genre, characters, synopsis FROM stories "
                                 "WHERE issue_id = ? ORDER BY sequence, id", (issue_id,)).fetchall()
            credits = {sid: db.execute("SELECT role, name, inherited FROM credits WHERE story_id = ?", (sid,)).fetchall()
                       for sid, *_ in stories}
        details = IssueDetails(price=price, on_sale=on_sale, key_date=key_date, barcode=barcode, isbn=isbn)
        rows = [(story, [(role, name) for role, name, _ in credits[story[0]]]) for story in stories]
        interior = [(story, pairs) for story, pairs in rows if story[2] not in NON_CONTENT_TYPES]
        cover = [pairs for story, pairs in rows if story[2] == COVER_TYPE]
        every = [pair for _, pairs in interior for pair in pairs]
        fields = {"Writer": _names(every, "script"), "Penciller": _names(every, "pencils"),
                  "Inker": _names(every, "inks"), "Colorist": _names(every, "colors"),
                  "Letterer": _names(every, "letters"), "Editor": _names(every, "editing"),
                  "Translator": _names(every, "translator"),
                  "CoverArtist": _names([pair for pairs in cover for pair in pairs], "pencils", "inks")}
        details.credits = {field_name: ", ".join(names) for field_name, names in fields.items() if names}
        details.inherited = any(inherited for sid, *_ in stories for _, _, inherited in credits[sid])
        genres, characters = [], []
        for story, _ in interior:
            genres += _split(story[4])
            characters += _split(story[5])
        details.genre = ", ".join(dict.fromkeys(GENRES.get(genre.lower(), genre) for genre in genres))
        details.characters = ", ".join(dict.fromkeys(characters))
        texts = [(story[3], story[6]) for story, _ in interior if story[6].strip()]
        details.summary = texts[0][1] if len(texts) == 1 else " ".join(f"«{title or 'Historia'}»: {text}" for title, text in texts)
        with_credits = [(story, pairs) for story, pairs in interior if pairs]
        if len(with_credits) > 1:   # varias historias: quién hizo qué en cada una
            labels = (("script", "Guion"), ("pencils", "Lápiz"), ("inks", "Tinta"), ("colors", "Color"))
            for story, pairs in with_credits:
                shown = " · ".join(f"{label} {', '.join(_names(pairs, role))}" for role, label in labels
                                   if _names(pairs, role))
                if shown:
                    details.story_lines.append(f"- «{story[3] or f'Historia {story[1]}'}»: {shown}")
        return details

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
