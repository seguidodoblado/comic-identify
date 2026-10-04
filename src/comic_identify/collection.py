"""Series de la colección y sus huecos, a partir de lo indexado (metadatos del archivo y nombres de carpeta y archivo).

Una serie es el conjunto de archivos de una misma carpeta con la misma serie de ComicInfo (y volumen). Los archivos sin
metadatos solo forman serie si su carpeta tiene un nombre normalizado (bandera, años o sello): en carpetas sueltas
como «Por colocar» los números no significan nada. El total esperado es el `Count` de los metadatos; sin él solo se
pueden detectar huecos entre los números que hay.
"""
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .i18n import _
from .naming import detect_number, looks_normalized, natural_key, parse_name

STRAY_GAP = 20        # un número a más de esta distancia del resto de la serie es «aislado»
MIN_RUN = 5           # números que hacen falta para fiarse de la serie y detectar aislados
MIN_DENSITY = 0.4     # sin total, por debajo de esta fracción del rango los números son sueltos, no una serie


@dataclass
class SeriesReport:
    folder: str
    name: str
    category: str = ""
    files: int = 0
    tagged: int = 0                                          # archivos con ComicInfo.xml
    owned: list[int] = field(default_factory=list)           # números enteros que hay, sin repetir
    count: int | None = None                                 # total de la serie según los metadatos
    missing: list[int] = field(default_factory=list)
    duplicated: list[int] = field(default_factory=list)      # números con más de un archivo
    other: int = 0                                           # archivos sin número entero (especiales, sin número…)
    starts_at: int | None = None                             # primer número que hay, si no es el 1 (o el 0)
    strays: list[int] = field(default_factory=list)          # números aislados o mayores que el total: ¿de otra serie?
    sparse: bool = False                                     # números sueltos, sin total: no se calculan huecos
    mixed: bool = False                                      # carpeta con varias series: los números no dicen nada

    @property
    def total(self) -> int:
        return self.count or max([0, *(n for n in self.owned if n not in self.strays)])

    @property
    def status_key(self) -> str:
        """Estado estable (no se traduce): mixed, incomplete, sparse o complete."""
        if self.mixed:
            return "mixed"
        if self.missing:
            return "incomplete"
        if self.sparse or not self.count:
            return "sparse"
        return "complete"

    @property
    def status(self) -> str:
        """Etiqueta del estado, en el idioma de la interfaz."""
        return {"mixed": _("mezcla"), "incomplete": _("incompleta"), "sparse": _("sin total"),
                "complete": _("completa")}[self.status_key]


def ranges(numbers: list[int], limit: int = 110) -> str:
    """`3, 7, 13-36`: los números consecutivos se agrupan. Se recorta si es muy largo."""
    parts, start, previous = [], None, None
    for number in [*sorted(numbers), None]:
        if start is not None and number is not None and number == previous + 1:
            previous = number
            continue
        if start is not None:
            parts.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = number
    text = ", ".join(parts)
    return text if len(text) <= limit else text[:limit].rsplit(", ", 1)[0] + "…"


def _strays(numbers: list[int]) -> list[int]:
    """Números que están lejos del grueso de la serie y son pocos (uno o dos): casi seguro archivos de otra serie."""
    clusters: list[list[int]] = []
    for number in numbers:
        if clusters and number - clusters[-1][-1] <= STRAY_GAP:
            clusters[-1].append(number)
        else:
            clusters.append([number])
    main = max(clusters, key=len)
    if len(main) < MIN_RUN:
        return []
    return [n for cluster in clusters if cluster is not main and len(cluster) <= 2 for n in cluster]


def _looks_normalized(folder_name: str) -> bool:
    return looks_normalized(parse_name(folder_name))


def build_series(rows: Iterable[tuple]) -> list[SeriesReport]:
    """Agrupa las filas de `Library.series_rows()` en series y calcula lo que falta de cada una."""
    groups: dict[tuple[str, str, str], list[tuple]] = defaultdict(list)
    loose: dict[str, list[tuple]] = defaultdict(list)     # sin serie en los metadatos, en una carpeta normalizada
    for row in rows:
        path, series, volume = Path(row[0]), row[1], row[2]
        if series:
            groups[(str(path.parent), series, volume)].append(row)
        elif _looks_normalized(path.parent.name):
            loose[str(path.parent)].append(row)
    for folder, members in loose.items():
        owners = [key for key in groups if key[0] == folder]
        if len(owners) == 1:                    # una sola serie con metadatos en la carpeta: los demás son suyos
            groups[owners[0]].extend(members)
        else:
            groups[(folder, Path(folder).name, "")].extend(members)
    from_folder = {key for key in groups if not any(row[1] for row in groups[key])}
    reports = []
    for key, members in groups.items():
        folder, name, volume = key
        report = SeriesReport(folder, f"{name} Volumen {volume}" if volume.isdigit() else name)
        seen: dict[int, int] = defaultdict(int)
        for path, _series, _volume, number, count, category, tagged in members:
            report.files += 1
            report.tagged += 1 if tagged else 0
            report.category = report.category or category
            report.count = max(report.count or 0, count or 0) or None
            text = number if number.isdigit() else ("" if number else detect_number(Path(path).stem)[0])
            if text.isdigit():
                seen[int(text)] += 1
            else:
                report.other += 1
        report.owned = sorted(seen)
        report.duplicated = [n for n in report.owned if seen[n] > 1]
        if key in from_folder and report.duplicated:
            report.mixed = True                 # sin metadatos, números repetidos: son varias series en una carpeta
        elif report.owned or report.count:
            if report.count:
                report.strays = [n for n in report.owned if n > report.count]
            elif report.owned:
                report.strays = _strays(report.owned)
            real = [n for n in report.owned if n not in report.strays]
            first = real[0] if real else 1
            report.starts_at = first if first > 1 else None
            if report.count:
                start = 0 if 0 in seen else 1
            else:                      # sin total, solo los huecos entre los que hay
                start = first
                span = report.total - first + 1 if real else 0
                report.sparse = bool(real) and len(real) / span < MIN_DENSITY
            if not report.sparse:
                report.missing = [n for n in range(start, report.total + 1) if n not in seen]
        reports.append(report)
    return sorted(reports, key=lambda r: natural_key(r.name))
