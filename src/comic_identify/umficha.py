"""Lector de las páginas de fichas.universomarvel.com: la lista de números de una serie y la ficha de un ejemplar.

Son HTML antiguo (tablas anidadas, etiquetas sin cerrar, mayúsculas, ISO-8859-1), así que se lee con un árbol propio y
tolerante y se buscan las cosas por lo que dicen (fecha, «Páginas», «Rotulación»…), no por su posición exacta: una
plantilla algo distinta no debería romperlo. Lo que no se reconoce se ignora; nunca se inventa un dato.
"""
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin

PARSER_VERSION = 2   # 2: fecha también en las fichas USA (fechas/), «Ediciones Españolas» y sinopsis por historia
PESETAS_PER_EURO = 166.386   # cambio oficial fijado en 1999
_VOID = {"img", "br", "hr", "meta", "link", "input", "area", "base", "col", "param", "wbr"}
_TRANSPARENT = {"font", "small", "b", "i", "u", "big", "center", "span", "strong", "em", "a", "p"}
# Una etiqueta de estas cierra a otra abierta (HTML antiguo: <tr>, <td>, <li>… sin cerrar)
_CLOSES = {"tr": {"tr", "td", "th"}, "td": {"td", "th"}, "th": {"td", "th"}, "li": {"li"}, "option": {"option"}}
_STOP = {"tr": {"table"}, "td": {"tr", "table"}, "th": {"tr", "table"}, "li": {"ul", "ol"}, "option": {"select"}}
MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
          "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}


class Node:
    def __init__(self, tag: str, attrs: dict[str, str], parent: "Node | None" = None):
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.children: list[Node | str] = []

    def text(self) -> str:
        parts = [child if isinstance(child, str) else child.text() for child in self.children]
        return re.sub(r"\s+", " ", "".join(parts).replace("\xa0", " ")).strip()

    def walk(self):
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.walk()

    def find_all(self, *tags: str) -> list["Node"]:
        return [node for node in self.walk() if node.tag in tags]

    def find(self, *tags: str) -> "Node | None":
        return next((node for node in self.walk() if node.tag in tags), None)


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.current = Node("#root", {})

    def handle_starttag(self, tag, attrs):
        if tag in _CLOSES:   # cierra lo que quedara abierto y no puede contener a esta etiqueta
            node = self.current
            while node is not None and node.tag not in _STOP[tag]:
                if node.tag in _CLOSES[tag]:
                    self.current = node.parent
                    break
                node = node.parent
        child = Node(tag, {key: value or "" for key, value in attrs}, self.current)
        self.current.children.append(child)
        if tag not in _VOID:
            self.current = child

    def handle_endtag(self, tag):
        node = self.current
        while node is not None and node.tag != tag:
            node = node.parent
        if node is not None and node.parent is not None:
            self.current = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def parse_tree(html: str) -> Node:
    builder = _Builder()
    builder.feed(html)
    builder.close()
    return builder.root


# ---- Lista de números de una serie ---------------------------------------------------------------------------------

@dataclass
class SeriesIssue:
    group: str       # título de la tabla («ALPHA FLIGHT VOL.1 - FORUM»): una página puede agrupar varias series
    label: str       # «1», «Especial»…
    page: str        # ruta de la ficha relativa a la web: «esp/aphff101.html»


def parse_series_page(html: str, page_url: str) -> list[SeriesIssue]:
    """Los números de una página de serie, con la tabla (CAPTION) a la que pertenecen."""
    found, group = [], ""
    for node in parse_tree(html).walk():
        if node.tag == "caption":
            group = node.text()
        elif node.tag == "a" and node.attrs.get("href", "").lower().endswith(".html") and node.find("img") is None:
            href = node.attrs["href"].strip()
            parent = node.parent.tag if node.parent else ""
            if parent in ("td", "th") and node.text() and "esp/" in href:
                found.append(SeriesIssue(group, node.text(), _site_path(href, page_url)))
    return found


@dataclass
class Subpage:
    label: str       # «1-100», «Especiales»: series largas reparten sus números en varias páginas
    page: str


def parse_series_subpages(html: str, page_url: str) -> list[Subpage]:
    """Las subpáginas (por rangos de números) que enlaza una página de serie que no lista los números directamente."""
    found = []
    for node in parse_tree(html).walk():
        href = node.attrs.get("href", "").strip() if node.tag == "a" else ""
        parent = node.parent.tag if node.parent else ""
        if href.lower().endswith(".html") and parent in ("td", "th") and node.text() and node.find("img") is None:
            found.append(Subpage(node.text(), _site_path(href, page_url)))
    return found


def subpages_for(subpages: list[Subpage], number: str) -> list[Subpage]:
    """Las subpáginas cuyo rango («101-200», o un solo número) contiene `number`; ninguna si no es un número."""
    if not number.strip().isdigit():
        return []
    wanted = int(number)
    hits = []
    for sub in subpages:
        match = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", sub.label)
        if match and int(match.group(1)) <= wanted <= int(match.group(2) or match.group(1)):
            hits.append(sub)
    return hits


def _site_path(href: str, page_url: str) -> str:
    """La ruta de `href` relativa a la raíz de la web (para guardarla sin depender del servidor)."""
    absolute = urljoin(page_url, href)
    return absolute.split("://", 1)[-1].split("/", 1)[-1]


# ---- Ficha de un ejemplar ------------------------------------------------------------------------------------------

def split_names(text: str) -> list[str]:
    """«Fiona Avery - J. Michael Straczynski» -> [«Fiona Avery», «J. Michael Straczynski»]; también con coma o «y»."""
    return [name.strip() for name in re.split(r"\s*(?:,| - | y )\s*", text) if name.strip(" -–—")]


@dataclass
class UsaRef:
    text: str        # «Alpha Flight vol.1 #1»
    page: str        # «usa/aphf1001.html»


@dataclass
class Story:
    title: str
    pages: str = ""
    credits: dict[str, str] = field(default_factory=dict)   # «Rotulación» -> «Marcelino Hernández»
    usa: list[UsaRef] = field(default_factory=list)
    spanish: list[str] = field(default_factory=list)   # fichas USA: páginas españolas («esp/…») que publican esta historia
    synopsis: str = ""                                  # fichas USA: la sinopsis, si la hay


@dataclass
class Ficha:
    title: str = ""                 # «Alpha Flight vol.1 nº 1»
    publisher: str = ""             # la de la web («Forum»)
    cover_image: str = ""           # ruta relativa a la web
    cover_credits: str = ""
    year: int | None = None
    month: int | None = None
    date_text: str = ""
    price_text: str = ""
    color: str = ""
    format: str = ""
    size: str = ""
    pages: int | None = None
    comic_title: str = ""
    barcode: str = ""
    isbn: str = ""
    comments: list[str] = field(default_factory=list)
    stories: list[Story] = field(default_factory=list)

    def credit(self, *roles: str) -> str:
        """Los nombres de esos roles en todas las historias, sin repetir y separados por coma."""
        names: dict[str, None] = {}
        for story in self.stories:
            for role in roles:
                for name in split_names(story.credits.get(role, "")):
                    names.setdefault(name, None)
        return ", ".join(names)

    @property
    def price_euros(self) -> str:
        """El precio en euros con punto decimal («0.60», «3.90»): las pesetas se convierten al cambio oficial, para que
        una misma columna de costes no mezcle monedas. Vacío si la ficha no trae precio."""
        return _price_in_euros(*self.price)

    @property
    def price(self) -> tuple[str, str]:
        """(importe, moneda): «100», «pts» o «8», «€». Sin unidad, se supone euros desde 2002 y pesetas antes."""
        match = re.match(r"(\d+(?:[.,]\d+)?)\s*(.*)", self.price_text)
        if not match:
            return "", ""
        unit = match.group(2).lower()
        if "€" in unit or "eur" in unit:
            return match.group(1), "€"
        if "pt" in unit:
            return match.group(1), "pts"
        return match.group(1), "€" if (self.year or 0) >= 2002 else "pts"


def _price_in_euros(amount: str, currency: str) -> str:
    """«100», «pts» -> «0.60»; «3,90», «€» -> «3.90». Vacío si no hay un importe válido."""
    try:
        value = float(amount.replace(",", "."))
    except ValueError:
        return ""
    if currency == "pts":
        value /= PESETAS_PER_EURO
    return f"{value:.2f}" if currency in ("pts", "\u20ac") else ""


USA_HEADING, CREDITS_HEADING, COMMENTS_HEADING = "Contenido USA:", "Créditos por historia (USA):", "Comentarios de la edición:"
NOTE_HEADINGS = (USA_HEADING, CREDITS_HEADING, COMMENTS_HEADING)


def usa_section(ficha: Ficha, base_url: str) -> str:
    """«Contenido USA:» y un ejemplar por línea, con el enlace a su ficha; vacío si la ficha no cita ninguno."""
    seen: dict[str, str] = {}
    for story in ficha.stories:
        for ref in story.usa:
            seen.setdefault(ref.page, ref.text)
    return "\n".join([USA_HEADING, *(f"- {text}: {urljoin(base_url, page)}" for page, text in seen.items())]) if seen else ""


def comments_section(ficha: Ficha) -> str:
    return "\n".join([COMMENTS_HEADING, *(f"- {comment}" for comment in ficha.comments)]) if ficha.comments else ""


def compose_notes(usa: str, credit_lines: Sequence[str], comments: str) -> str:
    """Las tres partes que la ficha aporta a las Notas, en este orden y sin huecos: los ejemplares USA, los créditos
    de cada historia (si se conocen) y los comentarios de la edición."""
    credits = "\n".join([CREDITS_HEADING, *credit_lines]) if credit_lines else ""
    return "\n".join(part for part in (usa, credits, comments) if part)


def edition_notes(ficha: Ficha, base_url: str, credit_lines: Sequence[str] = ()) -> str:
    """Lo que la ficha dice de la edición, para las Notas (y de ahí al comentario de GCstar). Vacío si no trae nada."""
    return compose_notes(usa_section(ficha, base_url), credit_lines, comments_section(ficha))


_PRICE = re.compile(r"^\d+(?:[.,]\d+)?\s*(?:pts?\.?|ptas\.?|pesetas|€|euros?)?$", re.IGNORECASE)
_PAGES = re.compile(r"(\d+)\s*p[aá]ginas?", re.IGNORECASE)
_SIZE = re.compile(r"\d[\d.,]*\s*x\s*\d[\d.,]*\s*cm", re.IGNORECASE)
_COLOR = re.compile(r"^(color|b/?n|blanco y negro|bicolor|blanco/negro|tricolor)$", re.IGNORECASE)
_EDITORIAL = re.compile(r"\s+-\s+([^-]+)$")
_ROLES = {"rotulación", "traducción", "adaptación", "guion", "guión", "argumento", "dibujo", "lápiz", "lápices", "tinta",
          "tintas",
          "color", "colores", "portada", "edición", "retoque", "supervisión", "coordinación", "maquetación",
          "producción", "editor", "textos"}


def parse_ficha(html: str, page_url: str) -> Ficha:
    """Lee una ficha de ejemplar. Lo que no encuentra queda vacío."""
    tree = parse_tree(html)
    ficha = Ficha()
    if (title := tree.find("title")) is not None:
        text = title.text()
        if match := _EDITORIAL.search(text):
            ficha.publisher, text = match.group(1).strip(), text[:match.start()]
        ficha.title = re.sub(r"\s+", " ", text).strip()
    cover = next((n for n in tree.find_all("img") if "portadas/" in n.attrs.get("src", "")), None)
    if cover is not None:
        ficha.cover_image = _site_path(cover.attrs["src"], page_url)
        row = cover.parent
        while row is not None and row.tag != "tr":
            row = row.parent
        table = row.parent if row is not None else None
        cells = [r.text() for r in table.find_all("tr")] if table is not None else []
        # bajo «Portada»: sus autores; luego, en filas de código, el ISBN o el código de barras
        for index, text in enumerate(cells):
            if text.lower() == "portada" and index + 1 < len(cells):
                ficha.cover_credits = re.sub(r"\s+-\s+", ", ", cells[index + 1]) if cells[index + 1] and not _code(cells[index + 1]) else ""
        for text in cells:
            if code := _code(text):
                kind, value = code
                if kind == "isbn":
                    ficha.isbn = value
                else:
                    ficha.barcode = value
    _read_general_data(tree, ficha)
    ficha.stories = _read_stories(tree, page_url)
    ficha.comments = _read_comments(tree)
    return ficha


def _code(text: str) -> tuple[str, str] | None:
    match = re.match(r"(ISBN|CB)\s*:\s*([\d Xx-]*)$", text.strip(), re.IGNORECASE)
    if not match:
        return None
    value = re.sub(r"[\s-]", "", match.group(2))
    return (match.group(1).lower(), value) if value else None


def _read_general_data(tree: Node, ficha: Ficha) -> None:
    """Fecha, precio, formato, color, páginas y título del cómic: las celdas de «Datos Generales»."""
    header = next((n for n in tree.find_all("th") if n.text().lower() == "datos generales"), None)
    if header is None:
        return
    row = header.parent
    table = row.parent
    data_row = table.find_all("tr")[1] if len(table.find_all("tr")) > 1 else None
    if data_row is None:
        return
    inner = data_row.find("table")
    if inner is None:
        return
    after_title = False
    leftovers: list[str] = []
    for cell in inner.find_all("th", "td"):
        text = cell.text()
        if not text:
            continue
        link = cell.find("a")
        if link is not None and "fechas" in link.attrs.get("href", ""):   # «fechases/» (España) y «fechas/» (USA)
            ficha.date_text = text
            words = text.lower().split()
            ficha.month = next((MONTHS[w] for w in words if w in MONTHS), None)
            year = next((int(w) for w in words if re.fullmatch(r"\d{4}", w)), None)
            ficha.year = year
        elif text.lower() in ("título del cómic", "titulo del comic"):
            after_title = True
        elif after_title:
            ficha.comic_title = text
            after_title = False
        elif _SIZE.search(text):
            ficha.size = _SIZE.search(text).group().strip()
        elif match := _PAGES.search(text):
            ficha.pages = int(match.group(1))
        elif _COLOR.match(text):
            ficha.color = text
        elif _PRICE.match(text):
            ficha.price_text = text
        else:
            leftovers.append(text)
    ficha.format = ", ".join(leftovers)


def _read_stories(tree: Node, page_url: str) -> list[Story]:
    """Una historia por cada bloque con «Equipo Creativo» (el ancla de cada historia falta en las fichas antiguas)."""
    pages_in_index = []   # «(30 págs.)» de cada historia, en el orden del índice de la ficha
    for item in tree.find_all("li"):
        link = item.find("a")
        if link is not None and link.attrs.get("href", "").startswith("#"):
            found = re.search(r"\(([^)]*p[aá]g[^)]*)\)", item.text(), re.IGNORECASE)
            pages_in_index.append(found.group(1) if found else "")
    stories = []
    for marker in (t for t in tree.find_all("th") if t.text().lower() == "equipo creativo"):
        table = marker.parent.parent
        rows = table.find_all("tr")
        title = rows[0].text().strip(' "«»“”') if rows else ""
        position = len(stories)
        story = Story(title, pages_in_index[position] if position < len(pages_in_index) else "")
        for number, row in enumerate(rows):
            headers = [c.text() for c in row.children if isinstance(c, Node) and c.tag == "th"]
            if headers and all(h.lower() in _ROLES for h in headers) and number + 1 < len(rows):
                values = [c.text() for c in rows[number + 1].children if isinstance(c, Node) and c.tag in ("td", "th")]
                story.credits.update({h: v for h, v in zip(headers, values, strict=False) if v.strip(" -–—")})
        story.spanish = _spanish_editions(table, page_url)
        for cell in table.find_all("th"):
            if cell.text().lower() == "sinopsis":
                following = cell.parent.parent.find_all("tr")
                position = following.index(cell.parent)
                text = following[position + 1].text() if position + 1 < len(following) else ""
                story.synopsis = "" if text.strip(" -–—") == "" else text
        usa_header = next((t for t in table.find_all("th") if t.text().lower().startswith("contenido usa")), None)
        if usa_header is not None:
            for link in usa_header.parent.parent.find_all("a"):
                href = link.attrs.get("href", "")
                if "usa/" in href and link.text():
                    story.usa.append(UsaRef(link.text(), _site_path(href, page_url)))
        stories.append(story)
    return stories


def _spanish_editions(table: Node, page_url: str) -> list[str]:
    """En una ficha USA, las fichas españolas (`esp/…`) enlazadas bajo «Ediciones Españolas» de una historia."""
    header = next((t for t in table.find_all("th") if t.text().lower() == "ediciones españolas"), None)
    if header is None:
        return []
    rows = header.parent.parent.find_all("tr")
    position = rows.index(header.parent)
    if position + 1 >= len(rows):
        return []
    heads = [c for c in header.parent.children if isinstance(c, Node) and c.tag == "th"]
    cells = [c for c in rows[position + 1].children if isinstance(c, Node) and c.tag in ("td", "th")]
    cell = cells[heads.index(header)] if heads.index(header) < len(cells) else None
    if cell is None:
        return []
    return [_site_path(a.attrs["href"], page_url) for a in cell.find_all("a")
            if "esp/" in a.attrs.get("href", "") and a.attrs["href"].endswith(".html")]


def _read_comments(tree: Node) -> list[str]:
    header = next((n for n in tree.find_all("th") if n.text().lower().startswith("comentarios de la edici")), None)
    if header is None:
        return []
    row = header.parent
    following = row.parent.find_all("tr")
    position = following.index(row)
    if position + 1 >= len(following):
        return []
    return [item.text() for item in following[position + 1].find_all("li") if item.text()]
