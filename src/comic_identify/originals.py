"""Años del material original de una edición, consultando ComicVine.

Una edición española suele recoger números de una serie americana: si el usuario indica el título original y los
números que contiene, se toman las fechas de portada de ComicVine de esos números (`[AAAA]` o `[AAAA-AAAA]`).
"""
from dataclasses import dataclass

from .comicvine import ComicVineClient


@dataclass
class Volume:
    id: int
    name: str
    start_year: str
    publisher: str
    issues: str

    @property
    def label(self) -> str:
        details = [self.publisher, f"{self.issues} números" if self.issues else ""]
        year = f" ({self.start_year})" if self.start_year else ""
        return f"{self.name}{year} · " + " · ".join(d for d in details if d) if any(details) else f"{self.name}{year}"


def find_volumes(client: ComicVineClient, title: str) -> list[Volume]:
    """Series de ComicVine que se llaman como `title` (el título original, normalmente en inglés)."""
    if not title.strip():
        raise ValueError("Escribe el título original.")
    return [Volume(int(v["id"]), v.get("name") or "?", str(v.get("start_year") or ""),
                   (v.get("publisher") or {}).get("name") or "", str(v.get("count_of_issues") or ""))
            for v in client.search_volumes(title.strip(), limit=10)]


def content_years(client: ComicVineClient, volume_id: int, first: str, last: str = "") -> str:
    """Años de portada de los números `first` y `last` (o solo `first`): «1999» o «1999-2001»."""
    numbers = list(dict.fromkeys(n.strip() for n in (first, last) if n.strip()))
    if not numbers:
        raise ValueError("Indica al menos el número inicial.")
    years = []
    for number in numbers:
        for record in client.issues(volume_id, number)[:1]:
            date = record.get("cover_date") or ""
            if date[:4].isdigit():
                years.append(int(date[:4]))
    if not years:
        raise LookupError("ComicVine no tiene fecha de portada para esos números.")
    low, high = min(years), max(years)
    return str(low) if low == high else f"{low}-{high}"
