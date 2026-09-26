"""Pipeline de identificación: colección → código de barras → GCD → ComicVine + comparación de portadas."""
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .barcode import read_barcode
from .comicvine import ComicVineClient, ComicVineError
from .covers import read_cover, thumbnail_bytes
from .gcd import GcdHit, GcdIndex, fold
from .hashing import dhash_bytes, dhash_file, similarity
from .library import Library

# Similitud del dHash a partir de la cual se considera la misma portada. Sin calibrar
# con portadas reales todavía: ajustar tras probar con la colección.
MATCH_THRESHOLD = 0.80
MAX_VOLUMES = 3
MAX_GCD = 12

Progress = Callable[[str], None]


@dataclass
class Candidate:
    title: str
    source: str                     # "Mi colección" | "ComicVine" | "GCD"
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

    @property
    def is_match(self) -> bool:
        return self.similarity is not None and self.similarity >= MATCH_THRESHOLD

    @property
    def rank(self) -> tuple[int, float]:
        """Orden: código de barras exacto, portada parecida, texto de GCD y el resto."""
        tier = 0 if self.exact else 1 if self.is_match else 2 if self.source == "GCD" else 3
        return tier, -(self.similarity or 0)


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
                     country=hit.country, years=hit.years, series_id=hit.series_id)


def search_gcd(gcd: GcdIndex, text: str, number: str = "", publisher: str = "",
               year: str = "") -> list[Candidate]:
    """Búsqueda local por título (y número, editorial, año): rápida y sin límites; sirve al escribir."""
    return [_gcd_candidate(hit) for hit in gcd.search(text, number, publisher=publisher, year=year)][:MAX_GCD]


def identify(image: Path, library: Library | None, client: ComicVineClient | None,
             query: str = "", issue_number: str = "", progress: Progress = lambda _: None,
             gcd: GcdIndex | None = None, publisher: str = "", year: str = "") -> Outcome:
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
    if client is None and gcd is None:
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
    for volume in _matching_volumes(client.search_volumes(text, limit=10), key, wanted)[:MAX_VOLUMES]:
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
