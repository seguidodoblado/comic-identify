"""Fuente API pública de comics.org (GCD, CC BY-SA 4.0): último recurso en «Usar esta ficha» cuando el número elegido
no está en el índice local importado del volcado (uno nuevo, o de un país que no se importa). No sustituye la
búsqueda local: la API no deja buscar por texto, solo consultar un número o una serie ya conocidos por su id. Las
portadas siguen bloqueadas por Cloudflare igual que el resto del sitio (también las de `files1.comics.org`), así que
no se piden. Tres peticiones por número -ficha, serie y editorial-, con pausa entre ellas, igual que Tebeosfera.
"""
import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from urllib.parse import urlparse

from . import __version__
from .gcd import GENRES, GcdHit, IssueDetails, _names, _split, _years
from .i18n import _

API = "https://www.comics.org/api/"
HOST = urlparse(API).hostname
MIN_INTERVAL = 2.0   # segundos entre peticiones: una consulta puntual del usuario, no un rastreo
TIMEOUT = 30
MAX_BYTES = 4_000_000
USER_AGENT = f"comic-identify/{__version__} (herramienta personal de catalogación; consultas puntuales)"

# Tipos de «historia» (gcd.storytype) que no aportan autores de contenido: portada, anuncios, cartas, créditos,
# promos… Los mismos ids que excluye el índice local (NON_CONTENT_TYPES en gcd.py), pero por nombre: la API pública
# da el nombre del tipo, no su id (fixtures de GCD: storytype.yaml).
NON_CONTENT_TYPES = {"advertisement", "(backcovers) *do not use* / *please fix*", "cover",
                     "cover reprint (on interior page)", "credits, title page", "insert or dust jacket",
                     "letters page", "promo (ad from the publisher)", "public service announcement"}
COVER_TYPE = "cover"
_ROLE_FIELDS = ("script", "pencils", "inks", "colors", "letters", "editing")
_FIELD_LABEL = {"script": "Writer", "pencils": "Penciller", "inks": "Inker", "colors": "Colorist",
               "letters": "Letterer", "editing": "Editor"}
_STORY_LABELS = (("script", "Guion"), ("pencils", "Lápiz"), ("inks", "Tinta"), ("colors", "Color"))


class GcdApiError(Exception):
    """No se pudo consultar o leer la API pública de GCD."""


def _series_id_from_url(url: str) -> int | None:
    match = re.search(r"/series/(\d+)/", url or "")
    return int(match.group(1)) if match else None


class Fetcher:
    """Consulta la API con pausa entre peticiones; nunca sale de comics.org."""

    def __init__(self, min_interval: float = MIN_INTERVAL):
        self.min_interval = min_interval
        self._last = float("-inf")

    def get(self, url: str) -> dict:
        if urlparse(url).hostname != HOST:
            raise GcdApiError(_("Solo se consulta {HOST}, no «{url}».").format(HOST=HOST, url=url))
        wait = self._last + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                data = response.read(MAX_BYTES + 1)
        except (urllib.error.URLError, OSError) as error:
            raise GcdApiError(_("No se pudo consultar {url}: {error}").format(url=url, error=error)) from error
        finally:
            self._last = time.monotonic()
        if len(data) > MAX_BYTES:
            raise GcdApiError(_("{url} es demasiado grande.").format(url=url))
        try:
            return json.loads(data)
        except json.JSONDecodeError as error:
            raise GcdApiError(_("{url} no devolvió JSON válido.").format(url=url)) from error


def _credit_names(text: str, role: str) -> list[tuple[str, str]]:
    """[(papel, nombre)] de un campo clásico de crédito («Fulano; ? (translation)»): recorta la nota entre paréntesis,
    descarta lo desconocido y pasa a «translator» el guion anotado como traducción (igual que hace el índice local con
    el modelo nuevo de creadores, en `gcd._import_stories`)."""
    found = []
    for part in text.split(";"):
        part = part.strip()
        match = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", part)
        name, note = (match.group(1).strip(), match.group(2)) if match else (part, "")
        if not name or name in ("?", "None"):
            continue
        effective = "translator" if role == "script" and re.search(r"traduc|translat", note, re.IGNORECASE) else role
        found.append((effective, name))
    return found


def _story_pairs(story: dict) -> list[tuple[str, str]]:
    pairs = []
    for role in _ROLE_FIELDS:
        pairs += _credit_names(story.get(role) or "", role)
    return pairs


def _issue_details(issue: dict) -> IssueDetails:
    """Lo mismo que `GcdIndex.issue_details`, pero a partir del JSON del número que da la API pública: sus historias ya
    traen los créditos clásicos (guion, lápiz, tinta, color, rótulo, edición) como campos propios, sin necesidad de
    ninguna petición más. No hay créditos heredados de la historia original reimpresa (ese dato no lo da la API)."""
    stories = issue.get("story_set") or []
    interior = [s for s in stories if (s.get("type") or "") not in NON_CONTENT_TYPES]
    cover = [s for s in stories if s.get("type") == COVER_TYPE]
    every = [pair for story in interior for pair in _story_pairs(story)]
    cover_pairs = [pair for story in cover for pair in _story_pairs(story)]
    fields = {_FIELD_LABEL[role]: _names(every, role) for role in _ROLE_FIELDS}
    fields["Translator"] = _names(every, "translator")
    fields["CoverArtist"] = _names(cover_pairs, "pencils", "inks")
    details = IssueDetails(price=issue.get("price") or "", on_sale=issue.get("on_sale_date") or "",
                           key_date=issue.get("key_date") or "", barcode=issue.get("barcode") or "",
                           isbn=issue.get("isbn") or "")
    details.credits = {label: ", ".join(names) for label, names in fields.items() if names}
    genres, characters = [], []
    for story in interior:
        genres += _split(story.get("genre") or "")
        characters += _split(story.get("characters") or "")
    details.genre = ", ".join(dict.fromkeys(GENRES.get(genre.lower(), genre) for genre in genres))
    details.characters = ", ".join(dict.fromkeys(characters))
    texts = [(story.get("title") or "", story.get("synopsis") or "") for story in interior
            if (story.get("synopsis") or "").strip()]
    details.summary = (texts[0][1] if len(texts) == 1 else
                       " ".join(f"«{title or 'Historia'}»: {text}" for title, text in texts))
    with_credits = [(story, _story_pairs(story)) for story in interior if _story_pairs(story)]
    if len(with_credits) > 1:
        for story, pairs in with_credits:
            shown = " · ".join(f"{label} {', '.join(_names(pairs, role))}" for role, label in _STORY_LABELS
                               if _names(pairs, role))
            if shown:
                details.story_lines.append(f"- «{story.get('title') or 'Historia'}»: {shown}")
    return details


class GcdApiClient:
    """Consulta bajo demanda, al pedir «Usar esta ficha» de un número que el índice local no tiene: nada se guarda, se
    vuelve a consultar cada vez (es la excepción; el índice local sigue siendo la fuente habitual)."""

    def __init__(self, fetch: Callable[[str], dict] | None = None):
        self.fetch = Fetcher().get if fetch is None else fetch

    def issue(self, issue_id: int) -> tuple[GcdHit, IssueDetails]:
        issue = self.fetch(f"{API}issue/{issue_id}/?format=json")
        if "series" not in issue:
            raise GcdApiError(_("GCD no tiene el número {issue_id} (¿lo han borrado?).").format(issue_id=issue_id))
        series = self.fetch(issue["series"])
        publisher_name = ""
        if series.get("publisher"):
            publisher_name = self.fetch(series["publisher"]).get("name", "")
        hit = GcdHit(series=series.get("name", ""), publisher=publisher_name,
                     years=_years(series.get("year_began"), series.get("year_ended")),
                     number=issue.get("number") or "", title=issue.get("title") or "",
                     date=issue.get("key_date") or "", issue_id=issue_id,
                     country=series.get("country", "") or "", brand=issue.get("brand_emblem") or "",
                     series_id=_series_id_from_url(issue.get("series", "")))
        return hit, _issue_details(issue)
