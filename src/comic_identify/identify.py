"""Pipeline de identificación: colección → código de barras → GCD → ComicVine + comparación de portadas."""
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import tebeosfera as tb
from .barcode import read_barcode
from .comicvine import ComicVineClient, ComicVineError
from .covers import read_cover, thumbnail_bytes
from .gcd import GcdHit, GcdIndex, fold
from .hashing import dhash_bytes, dhash_file, similarity
from .library import Library
from .tbficha import TbFicha
from .tbficha import edition_notes as tb_edition_notes
from .umficha import Ficha, SeriesIssue, comments_section, edition_notes, usa_section
from .universomarvel import (
    BASE,
    EDITION_BY_PUBLISHER,
    PUBLISHER_BY_SITE,
    Entry,
    UniversoMarvelIndex,
    split_ficha_title,
    split_volume,
)

# Similitud del dHash a partir de la cual se considera la misma portada. Sin calibrar
# con portadas reales todavía: ajustar tras probar con la colección.
MATCH_THRESHOLD = 0.80
MAX_VOLUMES = 3
MAX_GCD = 12
MAX_MARVEL = 8
MAX_TEBEOSFERA = 8
CATALOG_SOURCES = ("Universo Marvel", "Tebeosfera")   # catálogos de ediciones españolas: series → ficha de un ejemplar
# campos de ComicInfo que traen las fichas de un ejemplar (Tebeosfera da todos los créditos; Universo Marvel, los de la edición)
MARVEL_METADATA = ("Volume", "Year", "Month", "Day", "Count", "Web", "Translator", "Letterer", "CoverArtist", "Format",
                   "Writer", "Penciller", "Inker", "Colorist", "Editor", "Genre", "Characters", "LanguageISO")
MARVEL_PER_ISSUE = ("GTIN", "Title", "NotesBlock", "BlackAndWhite")   # de un solo ejemplar: solo al etiquetar un archivo suelto

SOURCE_ORDER = {"Mi colección": 0, "Tebeosfera": 1, "Universo Marvel": 2, "GCD": 3}   # a igual parecido, el primero gana

Progress = Callable[[str], None]


@dataclass
class Candidate:
    title: str
    source: str                     # "Mi colección" | "ComicVine" | "GCD" | "Universo Marvel" | "Tebeosfera"
    similarity: float | None = None
    subtitle: str = ""
    url: str = ""                   # ficha en ComicVine
    path: Path | None = None        # archivo en la colección
    cover: bytes | None = None      # miniatura para la interfaz
    exact: bool = False             # coincide el código de barras
    image_url: str = ""             # portada grande (ComicVine), para el panel de la ficha
    series: str = ""                # datos de la ficha de ComicVine
    issue_name: str = ""
    number: str = ""
    year: str = ""
    publisher: str = ""             # editorial, sello, país y años de la serie (GCD): sirven para normalizar nombres
    brand: str = ""
    country: str = ""
    years: str = ""
    series_id: int | None = None    # serie en GCD (para el nombre de la carpeta)
    extra: dict[str, str] = field(default_factory=dict)   # Universo Marvel: campos de ComicInfo de la ficha (añadido al final)

    @property
    def is_match(self) -> bool:
        return self.similarity is not None and self.similarity >= MATCH_THRESHOLD

    @property
    def rank(self) -> tuple[int, float, int]:
        """Orden: tu colección y el código de barras exacto, portada parecida, texto de los catálogos y el resto; a
        igualdad, tu colección, Tebeosfera, Universo Marvel y GCD, por este orden."""
        tier = 0 if self.exact or self.source == "Mi colección" else 1 if self.is_match else \
            2 if self.source in ("GCD", *CATALOG_SOURCES) else 3
        return tier, -(self.similarity or 0), SOURCE_ORDER.get(self.source, len(SOURCE_ORDER))


@dataclass
class Outcome:
    query: str = ""
    issue_number: str = ""
    barcode: str = ""
    candidates: list[Candidate] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _issue_candidate(issue: dict) -> Candidate:
    volume = issue.get("volume") or {}
    number = issue.get("issue_number") or ""
    series = volume.get("name", "?")
    image = issue.get("image") or {}
    return Candidate(f"{series} #{number}" if number else series, "ComicVine", url=issue.get("site_detail_url", ""),
                     subtitle=" · ".join(p for p in (issue.get("name"), issue.get("cover_date")) if p),
                     image_url=image.get("super_url") or image.get("screen_url") or image.get("medium_url") or "",
                     series=series, issue_name=issue.get("name") or "", number=number,
                     year=(issue.get("cover_date") or str(volume.get("start_year") or ""))[:4])


def _gcd_candidate(hit: GcdHit, exact: bool = False) -> Candidate:
    title = f"{hit.series} #{hit.number}" if hit.number else hit.series
    brand = f"Sello: {hit.brand}" if hit.brand else ""
    date = re.sub(r"(-00)+$", "", hit.date)   # GCD guarda "1969-00-00" cuando solo se conoce el año
    detail = [p for p in (hit.publisher, brand, hit.years if not hit.number else "", hit.title, date) if p]
    return Candidate(title, "GCD", subtitle=" · ".join(detail), url=hit.url, exact=exact, series=hit.series,
                     number=hit.number, year=date[:4], publisher=hit.publisher, brand=hit.brand,
                     country=hit.country, years=hit.years, series_id=hit.series_id,
                     extra={"issue_id": str(hit.issue_id)} if hit.issue_id else {})


def search_gcd(gcd: GcdIndex, text: str, number: str = "", publisher: str = "",
               year: str = "") -> list[Candidate]:
    """Búsqueda local por título (y número, editorial, año): rápida y sin límites; sirve al escribir."""
    return [_gcd_candidate(hit) for hit in gcd.search(text, number, publisher=publisher, year=year)][:MAX_GCD]


def gcd_issue_candidate(hit: GcdHit) -> Candidate:
    """Un número de GCD ya conocido del todo, código de barras exacto aparte (para «Usar esta ficha» al navegar por su
    web: no hace falta ninguna consulta, GCD ya está entero en local)."""
    return _gcd_candidate(hit)


def _marvel_candidate(entry: Entry) -> Candidate:
    """Una serie del catálogo (aún sin número): al elegirla con un número escrito se consulta su ficha."""
    editorial, brand = EDITION_BY_PUBLISHER.get(entry.publisher, (entry.publisher, ""))
    name, volume = split_volume(entry.title)
    where = " · ".join(part for part in (entry.publisher, entry.section) if part)
    return Candidate(entry.title, "Universo Marvel", subtitle=where, url=entry.url, series=name, publisher=editorial,
                     brand=brand, country="es", extra={"level": "series", "Volume": volume,
                                                       "page": entry.page, "index_publisher": entry.publisher,
                                                       "section": entry.section})


def page_candidate(title: str, page: str) -> Candidate:
    """Una ficha suelta de la web a la que se llegó navegando (sin serie ni editorial de índice conocidas)."""
    return _marvel_candidate(Entry("", "", title, page))


def alternative_candidate(entry: Entry, issue: SeriesIssue) -> Candidate:
    """Una ficha de la página de una serie que no se pudo buscar por número (las lista por título): se elige en la lista
    y, como cualquier ficha suelta, se consulta al seleccionarla."""
    label = issue.label or issue.group
    return _marvel_candidate(Entry(entry.publisher, entry.section, f"{entry.title} · {label}", issue.page))


def usa_refs(ficha: Ficha) -> list[list[str]]:
    """Los ejemplares USA que recoge una ficha española, sin repetir: [[página, texto]…]."""
    seen: dict[str, str] = {}
    for story in ficha.stories:
        for ref in story.usa:
            seen.setdefault(ref.page, ref.text)
    return [[page, text] for page, text in seen.items()]


def marvel_issue_candidate(entry: Entry, issue: SeriesIssue, ficha: Ficha) -> Candidate:
    """El número concreto de una serie, a partir de su ficha: con lo que un ejemplar lleva de verdad (fecha, páginas,
    precio, créditos de la edición) y los campos de ComicInfo que de ahí salen."""
    series_title, number = split_ficha_title(ficha.title)
    name, volume = split_volume(series_title if number else entry.title)
    number = number or issue.label
    # una ficha abierta desde la web no trae la editorial del índice: se toma de cómo firma la ficha
    publisher = entry.publisher or PUBLISHER_BY_SITE.get(ficha.publisher, ficha.publisher)
    editorial, brand = EDITION_BY_PUBLISHER.get(publisher, (publisher, ""))
    amount, currency = ficha.price
    details = [ficha.date_text, f"{ficha.pages} págs." if ficha.pages else "", f"{amount} {currency}" if amount else "",
               ficha.format, ficha.comic_title]
    extra = {"Volume": volume, "Year": str(ficha.year or ""), "Month": str(ficha.month or ""), "Web": BASE + issue.page,
             "Translator": ficha.credit("Traducción"), "Letterer": ficha.credit("Rotulación"),
             "CoverArtist": ficha.cover_credits, "Format": ficha.format, "GTIN": ficha.isbn or ficha.barcode, "Title": ficha.comic_title,
             "BlackAndWhite": ficha.black_and_white, "ISBN": ficha.isbn, "Cost": ficha.price_euros, "NotesBlock": edition_notes(ficha, BASE),
             "NotesUsa": usa_section(ficha, BASE), "NotesComments": comments_section(ficha),
             "UsaRefs": json.dumps(usa_refs(ficha), ensure_ascii=False), "SpanishPage": issue.page, "level": "issue", "page": issue.page,
             "index_publisher": publisher}
    return Candidate(f"{name} #{number}" if number else name, "Universo Marvel", subtitle=" · ".join(d for d in details if d),
                     url=BASE + issue.page, series=name, issue_name=ficha.comic_title, number=number,
                     year=str(ficha.year or ""), publisher=editorial, brand=brand, country="es", extra=extra)


# ---- Tebeosfera ---------------------------------------------------------------------------------------------------

def _tebeosfera_candidate(entry: tb.Entry) -> Candidate:
    """Una colección del catálogo (aún sin número): al elegirla con un número escrito se consulta su ficha."""
    name = entry.title.split(" (")[0]
    where = " · ".join(part for part in (entry.publisher, entry.year, "Número único" if entry.single else "") if part)
    return Candidate(entry.title, "Tebeosfera", subtitle=where, url=entry.url, series=name, publisher=entry.publisher,
                     country="es", extra={"level": "series", "slug": entry.slug, "page": entry.page,
                                          "single": "1" if entry.single else "", "year": entry.year,
                                          "index_publisher": entry.publisher, "title": entry.title})


def tebeosfera_entry(candidate: Candidate) -> tb.Entry:
    """La colección que representa un candidato de Tebeosfera de nivel «series»."""
    extra = candidate.extra
    return tb.Entry(extra["slug"], extra.get("title") or candidate.title, extra.get("year", ""),
                    extra.get("index_publisher", ""), bool(extra.get("single")))


def tebeosfera_page_candidate(title: str, page: str) -> Candidate:
    """Una ficha de número a la que se llegó navegando por la web (sin colección de índice conocida)."""
    return _tebeosfera_candidate(tb.Entry(tb.page_slug(page), title, single=True))


def tebeosfera_alternative(entry: tb.Entry, issue: tb.Issue) -> Candidate:
    """Un número de la colección para elegir a mano cuando no está el escrito; como cualquier ficha suelta, se consulta
    al seleccionarlo."""
    return _tebeosfera_candidate(tb.Entry(tb.page_slug(issue.page), f"{entry.title} · nº {issue.label}", entry.year,
                                          entry.publisher, single=True))


def tebeosfera_issue_candidate(entry: tb.Entry, issue: tb.Issue, ficha: TbFicha) -> Candidate:
    """El número concreto, a partir de su ficha: con lo que un ejemplar lleva de verdad (fecha, páginas, precio, todos sus
    créditos, géneros, ISBN…) y los campos de ComicInfo que de ahí salen."""
    name = ficha.series or entry.title.split(" (")[0]
    number = ficha.number or issue.label
    details = [ficha.date_label, f"{ficha.pages} págs." if ficha.pages else "", ficha.price_label, ficha.format,
               ficha.issue_title]
    credits = ficha.credits
    extra = {"Year": str(ficha.year or ""), "Month": str(ficha.month or ""), "Day": str(ficha.day or ""),
             "Count": str(ficha.count or ""), "Web": tb.BASE + issue.page, "LanguageISO": ficha.language,
             "Translator": credits.get("Translator", ""), "Letterer": credits.get("Letterer", ""),
             "CoverArtist": credits.get("CoverArtist", ""), "Writer": credits.get("Writer", ""),
             "Penciller": credits.get("Penciller", ""), "Inker": credits.get("Inker", ""),
             "Colorist": credits.get("Colorist", ""), "Editor": credits.get("Editor", ""),
             "Genre": ", ".join(ficha.genres), "Characters": ", ".join(ficha.sagas), "Format": ficha.format,
             "GTIN": ficha.isbn or ficha.gtin, "Title": ficha.issue_title, "BlackAndWhite": ficha.black_and_white,
             "ISBN": ficha.isbn, "Cost": ficha.price_euros, "NotesBlock": tb_edition_notes(ficha),
             "SpanishPage": issue.page, "level": "issue", "page": issue.page, "slug": ficha.slug}
    return Candidate(f"{name} #{number}" if number else name, "Tebeosfera", subtitle=" · ".join(d for d in details if d),
                     url=tb.BASE + issue.page, series=name, issue_name=ficha.issue_title, number=number,
                     year=str(ficha.year or ""), publisher=ficha.publisher or entry.publisher, brand=ficha.imprint,
                     country="es", extra=extra)


def search_tebeosfera(index: tb.TebeosferaIndex, text: str, publisher: str = "") -> list[Candidate]:
    """Colecciones de Tebeosfera (índice local) cuyo título encaja; sin números ni portadas."""
    return [_tebeosfera_candidate(entry) for entry in index.search(text, limit=MAX_TEBEOSFERA, publisher=publisher)]


def attach_cover(candidate: Candidate, cover: bytes, image: Path | None) -> None:
    """Pone la miniatura de la portada de la ficha y, si hay una portada abierta con la que compararla, el parecido
    (la misma huella y el mismo porcentaje que en las sugerencias de ComicVine). Una imagen ilegible se ignora."""
    candidate.cover = thumbnail_bytes(cover)
    remote = dhash_bytes(cover)
    if image is None or remote is None:
        return
    try:
        candidate.similarity = similarity(dhash_file(image), remote)
    except (OSError, ValueError):
        return


def search_marvel(index: UniversoMarvelIndex, text: str, publisher: str = "") -> list[Candidate]:
    """Series del catálogo de Universo Marvel (índice local) cuyo título encaja; sin números ni portadas."""
    return [_marvel_candidate(entry) for entry in index.search(text, limit=MAX_MARVEL, publisher=publisher)]


def identify(image: Path, library: Library | None, client: ComicVineClient | None,
             query: str = "", issue_number: str = "", progress: Progress = lambda _: None,
             gcd: GcdIndex | None = None, publisher: str = "", year: str = "",
             marvel: UniversoMarvelIndex | None = None, tebeosfera: tb.TebeosferaIndex | None = None) -> Outcome:
    """Identifica una portada. El título lo escribe el usuario: el OCR no lee los logotipos de cómic."""
    outcome = Outcome(query=query)
    variants = dhash_file(image)

    if library is not None:
        progress("Buscando en tu colección…")
        for path, score in library.find(variants, limit=3):
            if score >= MATCH_THRESHOLD - 0.1:
                data = read_cover(path)
                outcome.candidates.append(
                    Candidate(path.stem, "Mi colección", score, str(path.parent), path=path,
                              cover=thumbnail_bytes(data) if data else None))

    progress("Leyendo código de barras…")
    barcode = read_barcode(image)
    if barcode:
        outcome.barcode = barcode.code + (f" +{barcode.addon}" if barcode.addon else "")
    outcome.issue_number = issue_number or (barcode.issue_number if barcode else "") or ""

    if gcd is not None:
        progress("Consultando Grand Comics Database…")
        _add_gcd(gcd, query, barcode, outcome, publisher, year)
    if marvel is not None and query:
        outcome.candidates += search_marvel(marvel, query, publisher)
    if tebeosfera is not None and query:
        outcome.candidates += search_tebeosfera(tebeosfera, query, publisher)
    if client is None and gcd is None and marvel is None and tebeosfera is None:
        outcome.notes.append("Configura la clave de ComicVine o importa el volcado de GCD (pestaña Ajustes).")
    elif not query:
        outcome.notes.append("Escribe el título del cómic para buscarlo.")
    elif client is not None:
        try:
            _add_comicvine(client, query, outcome, variants, progress, publisher, year)
        except ComicVineError as error:
            outcome.notes.append(str(error))

    outcome.candidates.sort(key=lambda c: c.rank)
    return outcome


def _add_gcd(gcd: GcdIndex, query: str, barcode, outcome: Outcome, publisher: str, year: str) -> None:
    found = [(hit, True) for hit in gcd.by_barcode(barcode.code + barcode.addon)] if barcode else []
    if query:
        found += [(hit, False) for hit in gcd.search(query, outcome.issue_number, publisher=publisher, year=year)]
    seen: set = set()
    for hit, exact in found:
        key = hit.issue_id or (hit.series, hit.publisher, hit.years)
        if key not in seen and len(seen) < MAX_GCD:
            seen.add(key)
            outcome.candidates.append(_gcd_candidate(hit, exact))


def _add_comicvine(client, text: str, outcome: Outcome, variants, progress, publisher: str = "",
                   year: str = "") -> None:
    progress(f"Consultando ComicVine: «{text}»…")
    wanted = int(year) if year.strip().isdigit() else None
    key = fold(publisher.strip())
    volumes = _matching_volumes(client.search_volumes(text, limit=10), key, wanted)[:MAX_VOLUMES]
    for index, volume in enumerate(volumes, 1):
        # cada serie supone una consulta más (y, si hay número, otra por cada portada a comparar): esto es lo que
        # tarda varios segundos, así que se informa serie a serie en vez de un único mensaje fijo todo el rato
        progress(f"Comparando con ComicVine ({index}/{len(volumes)}): «{volume.get('name', '')}»…")
        records = client.issues(volume["id"], outcome.issue_number) if outcome.issue_number \
            else [{"volume": volume, "image": volume.get("image"),
                   "site_detail_url": volume.get("site_detail_url")}]
        for record in records:
            candidate = _issue_candidate(record)
            date = record.get("cover_date") or ""
            if wanted and outcome.issue_number and date[:4].isdigit() and int(date[:4]) != wanted:
                continue
            candidate.subtitle = candidate.subtitle or " · ".join(
                str(p) for p in ((volume.get("publisher") or {}).get("name"), volume.get("start_year")) if p)
            image = record.get("image") or {}
            url = image.get("medium_url") or image.get("small_url")
            if url:
                candidate.cover = client.download(url)
                remote = dhash_bytes(candidate.cover)
                candidate.similarity = similarity(variants, remote) if remote else None
            outcome.candidates.append(candidate)


def _matching_volumes(volumes: list[dict], publisher: str, year: int | None) -> list[dict]:
    """Series de ComicVine que cumplen la editorial (contiene) y el año (la serie ya había empezado)."""
    def keep(volume: dict) -> bool:
        if publisher and publisher not in fold((volume.get("publisher") or {}).get("name") or ""):
            return False
        start = str(volume.get("start_year") or "")
        return not (year and start.isdigit() and int(start) > year)
    return [volume for volume in volumes if keep(volume)]
