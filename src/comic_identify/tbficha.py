"""Lector de las fichas de www.tebeosfera.com: la ficha de un número y el nombre de las colecciones.

A diferencia de Universo Marvel, es HTML moderno y con clases: cada dato de la ficha es una fila con una «etiqueta»
(«Distribución:», «Formato:», «Autores:»…) y su «dato». Se busca por lo que dice la etiqueta, no por la posición, y
lo que no se reconoce se ignora: nunca se inventa un dato. Tebeosfera escribe títulos y nombres en MAYÚSCULAS; aquí se
pasan a mayúscula inicial (ver `smart_title`), que es lo único que se puede hacer sin perder información.
"""
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from .umficha import (
    COMMENTS_HEADING,
    PESETAS_PER_EURO,
    TB_EDITION_HEADING,
    TB_RELATED_HEADING,
    Node,
    parse_tree,
)

PARSER_VERSION = 1
HOST = "www.tebeosfera.com"
BASE = f"https://{HOST}/"
ROMAN_MONTHS = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11,
                "XII": 12}
# Tebeosfera -> campo de ComicInfo (por el principio de la palabra: singular, plural y femenino)
ROLE_STEMS = (("guion", ("Writer",)), ("historiet", ("Writer", "Penciller")), ("dibuj", ("Penciller",)),
              ("ilustr", ("Penciller",)), ("entint", ("Inker",)), ("color", ("Colorist",)), ("rotul", ("Letterer",)),
              ("portad", ("CoverArtist",)), ("traduct", ("Translator",)), ("editor", ("Editor",)))
LANGUAGES = {"castellano": "es", "español": "es", "espanol": "es", "catalán": "ca", "catalan": "ca", "valenciano": "ca",
             "euskera": "eu", "vasco": "eu", "gallego": "gl", "inglés": "en", "ingles": "en", "francés": "fr",
             "frances": "fr", "italiano": "it", "portugués": "pt", "portugues": "pt", "alemán": "de", "aleman": "de",
             "japonés": "ja", "japones": "ja"}
_LOWER_WORDS = {"a", "al", "con", "de", "del", "el", "en", "la", "las", "lo", "los", "o", "para", "por", "un", "una",
                "y", "e", "u", "van", "von", "da", "di", "der", "den", "le"}
_ROMAN = re.compile(r"^(?=[IVXLCDM]+$)M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
_ACRONYMS = {"DC", "JLA", "JSA", "JLX", "TV", "USA", "EEUU", "ECC", "SHIELD", "S.H.I.E.L.D.", "X-MEN", "OVNI", "DK",
             "DVD", "CD", "UFO", "FBI", "CIA", "NBA", "SOS", "BD", "GI", "G.I.", "HP", "HD", "XL", "XXL", "3D", "RPG"}


def smart_title(text: str) -> str:
    """«UNIVERSO DC» -> «Universo DC»; «MARVEL SAGA: EL ASOMBROSO SPIDERMAN» -> «Marvel Saga: el Asombroso Spiderman».
    Solo se toca un texto que venga TODO en mayúsculas: si ya trae minúsculas, es como lo escribió Tebeosfera."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text or text != text.upper() or text == text.lower():
        return text
    words = []
    for number, word in enumerate(text.split(" ")):
        core = word.strip("()[]«»\"“”,;:.!?-–")
        if core in _ACRONYMS or _ROMAN.match(core) and 1 < len(core) <= 4 and core not in {"MI", "MIL", "DI", "CIVIL",
                                                                                          "LIL", "MIX", "DIM"}:
            words.append(word)
        elif core.lower() in _LOWER_WORDS and number > 0 and not words[-1].endswith(":"):
            words.append(word.lower())
        else:
            words.append(_capitalize(word))
    return " ".join(words)


def _capitalize(word: str) -> str:
    def part(piece: str) -> str:
        lowered = piece.lower()
        if lowered.startswith("mc") and len(lowered) > 2:
            return "Mc" + lowered[2].upper() + lowered[3:]
        if lowered.startswith("o'") and len(lowered) > 2:
            return "O'" + lowered[2].upper() + lowered[3:]
        for index, char in enumerate(lowered):
            if char.isalpha():
                return lowered[:index] + char.upper() + lowered[index + 1:]
        return lowered
    return "-".join(part(piece) for piece in word.split("-"))


def role_fields(role: str) -> tuple[str, ...]:
    """Los campos de ComicInfo de un rol de Tebeosfera («Guionistas», «Entintador»…); () si no se reconoce."""
    lowered = role.strip().lower()
    return next((fields for stem, fields in ROLE_STEMS if lowered.startswith(stem)), ())


def parse_date(text: str) -> tuple[int | None, int | None, int | None]:
    """(año, mes, día) de «XII-1989», «14-VIII-2025» o «2019»; None en lo que no venga. Con dos meses («VII-VIII-1990»)
    vale el primero."""
    years = re.findall(r"(?<!\d)(1[5-9]\d\d|20\d\d)(?!\d)", text)
    if not years:
        return None, None, None
    month = next((ROMAN_MONTHS[t] for t in re.findall(r"(?<![A-Za-z])([IVX]{1,4})(?![A-Za-z])", text.upper())
                  if t in ROMAN_MONTHS), None)
    day = re.match(r"\s*(\d{1,2})(?=\s*-\s*[IVX])", text)
    return int(years[-1]), month, int(day.group(1)) if day else None


def _has_class(node: Node, name: str) -> bool:
    return name in node.attrs.get("class", "").split()


def _find_class(root: Node, tag: str, name: str) -> Node | None:
    return next((n for n in root.walk() if n.tag == tag and _has_class(n, name)), None)


def _text_lines(node: Node) -> list[str]:
    """Los párrafos (`<p>`, `<li>` o líneas) de un bloque de texto libre."""
    items = [n.text() for n in node.find_all("p", "li") if n.text()]
    if items:
        return items
    return [line.strip() for line in re.split(r"\n+", node.text()) if line.strip()]


@dataclass
class TbFicha:
    """Un número de una colección de Tebeosfera."""
    series: str = ""                 # colección tal como la escribe la ficha, ya con mayúscula inicial: «Universo DC»
    collection_title: str = ""       # «UNIVERSO DC (1989, ZINCO)»
    collection_slug: str = ""        # «universo_dc_1989_zinco»
    slug: str = ""                   # la de este número: «universo_dc_1989_zinco_10»
    number: str = ""
    count: int | None = None         # «[de 37]»
    issue_title: str = ""            # «Catwoman»
    publisher: str = ""              # «Ediciones Zinco» (sin «S. A.»)
    imprint: str = ""                # el sello, si la ficha lo da aparte: «Forum»
    group: str = ""                  # el grupo editorial: «Grupo Planeta»
    city: str = ""
    distributor: str = ""
    date_text: str = ""              # «XII-1989»
    year: int | None = None
    month: int | None = None
    day: int | None = None
    approximate_date: bool = False
    price_text: str = ""             # «200 pts.»
    price_amount: str = ""
    price_currency: str = ""         # «PTA», «EUR»…
    edition: str = ""                # «NUEVA · TEBEO»
    origin: str = ""                 # «Daredevil Vol 8 : Marvel»
    language_text: str = ""          # «Traducción del inglés»
    language: str = ""               # ISO: «es»
    format: str = ""                 # «Cuaderno, Grapa»
    size: str = ""
    pages: int | None = None
    pages_text: str = ""
    color_text: str = ""
    printing: str = ""
    isbn: str = ""
    gtin: str = ""
    issn: str = ""
    legal_deposit: str = ""
    credits: dict[str, str] = field(default_factory=dict)          # campo de ComicInfo -> nombres separados por coma
    other_credits: dict[str, str] = field(default_factory=dict)    # roles sin campo: «Supervisor» -> nombres
    genres: list[str] = field(default_factory=list)
    sagas: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)              # «Antes, en otra lengua, en: A; B»
    comments: list[str] = field(default_factory=list)
    cover_image: str = ""            # dirección absoluta de la portada

    @property
    def date_label(self) -> str:
        """La fecha para mostrar: «14 de agosto de 2025», «diciembre de 1989», «2019» (con «aprox.» si lo es)."""
        if not self.year:
            return self.date_text
        names = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
                 "noviembre", "diciembre")
        text = f"{names[self.month - 1]} de {self.year}" if self.month else str(self.year)
        if self.month and self.day:
            text = f"{self.day} de {text}"
        return text + (" (aprox.)" if self.approximate_date else "")

    @property
    def price(self) -> tuple[str, str]:
        """(importe, moneda) con la moneda en su símbolo o abreviatura: «200», «pts» / «3.30», «€» / «12000.00», «$»."""
        return self.price_amount, {"PTA": "pts", "EUR": "€"}.get(self.price_currency, self.price_currency)

    @property
    def price_label(self) -> str:
        """El precio para mostrar: «200 pts.», «3.30 €»."""
        amount, symbol = self.price
        return f"{amount} {symbol}{'.' if symbol == 'pts' else ''}" if amount else ""

    @property
    def price_euros(self) -> str:
        """El precio en euros con punto decimal («0.60», «3.30»): las pesetas se convierten al cambio oficial; otras
        monedas no se convierten (vacío)."""
        try:
            value = float(self.price_amount)
        except ValueError:
            return ""
        if self.price_currency == "PTA":
            value /= PESETAS_PER_EURO
        elif self.price_currency != "EUR":
            return ""
        return f"{value:.2f}"

    @property
    def black_and_white(self) -> str:
        """`BlackAndWhite` de ComicInfo: «Yes» si el interior es en blanco y negro, «No» si es a color y vacío si la ficha
        no lo dice."""
        interior = {}
        for kind, where in re.findall(r"(COLOR|B/N|BLANCO Y NEGRO|BICOLOR|TRICOLOR)\s*(?:\(([^)]*)\))?",
                                      self.color_text.upper()):
            for place in re.split(r"\s*,\s*", where or "interior"):
                interior[place.strip().lower()] = kind
        kind = interior.get("interior")
        if kind in ("B/N", "BLANCO Y NEGRO"):
            return "Yes"
        return "No" if kind in ("COLOR", "TRICOLOR") else ""


def _meta(tree: Node, prop: str) -> str:
    node = next((n for n in tree.walk() if n.tag == "meta" and n.attrs.get("property") == prop), None)
    return node.attrs.get("content", "").strip() if node is not None else ""


def _rows(body: Node) -> dict[str, Node]:
    """Etiqueta (sin los dos puntos, en minúsculas) -> el nodo con su dato."""
    rows = {}
    for node in body.walk():
        if node.tag == "div" and _has_class(node, "etiqueta") and node.parent is not None:
            siblings = node.parent.children
            after = siblings[siblings.index(node) + 1:]
            value = next((s for s in after if isinstance(s, Node) and _has_class(s, "dato")), None)
            if value is not None:
                rows.setdefault(node.text().rstrip(": ").strip().lower(), value)
    return rows


def _price(text: str, hint: str) -> tuple[str, str]:
    """(importe, código de moneda) de «200 pts.», «3.30 €» o «12000,00 $»; `hint` es el nombre de la moneda que da la ficha
    («PESETA (PTA)»)."""
    match = re.search(r"(\d[\d.,]*)\s*(.*)", text)
    if not match:
        return "", ""
    amount, unit = match.group(1), match.group(2).lower()
    code = re.search(r"\(([A-Z]{3})\)", hint)
    currency = code.group(1) if code else "EUR" if "€" in unit or "eur" in unit else "PTA" if "pt" in unit else ""
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", amount):     # «1.200 pts.»: el punto separa millares
        amount = amount.replace(".", "")
    return amount.replace(",", "."), currency


def _authors(value: Node) -> tuple[dict[str, str], dict[str, str]]:
    credits: dict[str, dict[str, None]] = {}
    other: dict[str, dict[str, None]] = {}
    for row in value.walk():
        if row.tag != "div" or not _has_class(row, "tab_datos"):
            continue
        heading = next((n for n in row.walk() if n.tag == "span" and _has_class(n, "tab_subtitulo")), None)
        if heading is None:
            continue
        role = re.sub(r"\s*\d+\s*$", "", heading.text()).strip()
        names = [smart_title(a.text()) for a in row.find_all("a") if a.text()]
        fields = role_fields(role)
        for name in names:
            for target in fields or (None,):
                bucket = credits.setdefault(target, {}) if target else other.setdefault(role, {})
                bucket.setdefault(name, None)
    return ({k: ", ".join(v) for k, v in credits.items()}, {k: ", ".join(v) for k, v in other.items()})


def _related(value: Node) -> list[str]:
    """«Antes, en otra lengua, en: A; B» por cada grupo que la ficha da en «Ediciones» (el texto suelto anuncia el grupo y
    los enlaces que le siguen son sus títulos)."""
    groups: list[tuple[str, list[str]]] = []
    for child in value.children:
        if isinstance(child, str):
            if re.search(r"Antes|Luego|Despu[eé]s", child):
                groups.append((re.sub(r"\s+", " ", child).strip(" ,"), []))
        elif groups:
            for link in ([child] if child.tag == "a" else child.find_all("a")):
                if link.text():
                    groups[-1][1].append(smart_title(link.text()))
    lines = []
    for label, titles in groups:
        if titles:
            shown = "; ".join(titles[:6]) + (f"; y {len(titles) - 6} más" if len(titles) > 6 else "")
            lines.append(f"{label}: {shown}")
    return lines


def _br_lines(node: Node) -> list[str]:
    """El texto de un bloque partido por `<br>` (y por bloques hijos), una entrada por línea."""
    lines, current = [], []

    def flush():
        text = re.sub(r"\s+", " ", "".join(current).replace("\xa0", " ")).strip()
        if text:
            lines.append(text)
        current.clear()

    def walk(parent: Node):
        for child in parent.children:
            if isinstance(child, str):
                current.append(child)
            elif child.tag == "br" or child.tag == "div":
                flush()
                if child.tag == "div":
                    walk(child)
                    flush()
            else:
                walk(child)
    walk(node)
    flush()
    return lines


_LEGAL_SUFFIX = re.compile(r",?\s+S\.?\s?[AL]\.?(\s?U\.?)?\s*$", re.IGNORECASE)


def _read_publisher_line(line: Node, ficha: TbFicha) -> None:
    """«Grupo Planeta : Planeta DeAgostini · forum · Barcelona ·  [bandera]»: grupo, editorial, sello y ciudad."""
    segments: list[list[Node | str]] = [[]]
    for child in line.children:
        if isinstance(child, Node) and child.tag == "strong" and child.text() == "·":
            segments.append([])
        elif isinstance(child, Node) and child.tag == "img":
            continue
        else:
            segments[-1].append(child)

    def clean(text: str) -> str:
        return _LEGAL_SUFFIX.sub("", smart_title(text)).strip()
    first = [n for n in segments[0] if isinstance(n, Node) and n.tag == "a" and n.text()]
    if len(first) >= 2:
        ficha.group, ficha.publisher = clean(first[0].text()), clean(first[1].text())
    elif first:
        ficha.publisher = clean(first[0].text())
    for segment in segments[1:]:
        links = [n for n in segment if isinstance(n, Node) and n.tag == "a" and n.text()]
        text = " ".join(n if isinstance(n, str) else n.text() for n in segment).strip()
        if links and not ficha.imprint:
            ficha.imprint = _capitalize(links[0].text().lower()) if links[0].text().islower() else clean(links[0].text())
        elif text and not ficha.city:
            ficha.city = smart_title(text)


def parse_ficha(html: str, page_url: str) -> TbFicha:
    """La ficha de un número. Un dato que la página no trae se queda vacío."""
    tree = parse_tree(html)
    ficha = TbFicha()
    og_title = _meta(tree, "og:title")
    route = next((n.attrs.get("value", "") for n in tree.walk() if n.tag == "input" and n.attrs.get("id") == "NUMERO_RUTA"), "")
    ficha.slug = route or urlparse(page_url).path.rsplit("/", 1)[-1].removesuffix(".html")
    body = next((n for n in tree.walk() if n.tag == "div" and n.attrs.get("id") == "cuerpo2_ficha"), None)
    if body is None or not og_title:
        return ficha
    title_box = _find_class(tree, "div", "titulo")
    if title_box is not None:
        lines = _br_lines(title_box)
        ficha.series = smart_title(lines[0]) if lines else ""
        ficha.issue_title = " - ".join(smart_title(line) for line in lines[1:])
    subtitle = _find_class(tree, "div", "subtitulo")
    if subtitle is not None and subtitle.text():
        ficha.issue_title = " - ".join(p for p in (ficha.issue_title, smart_title(subtitle.text())) if p)
    ficha.collection_title = re.sub(r"\s+\S+$", "", og_title) if re.search(r"\s+\S+$", og_title) and \
        not og_title.rstrip().endswith((")", "-")) else og_title
    link = next((a for a in body.find_all("a") if a.attrs.get("href", "").lstrip("/").startswith(("colecciones/", "publicaciones/"))), None)
    if link is not None:
        ficha.collection_slug = re.sub(r"\.html/?$", "", link.attrs["href"].rstrip("/").rsplit("/", 1)[-1])
        head = link.parent
        while head is not None and not _has_class(head, "dato"):
            head = head.parent
        if head is not None:
            number = re.match(r"\s*N[º°o]\s*(\S+)", head.text(), re.IGNORECASE)
            ficha.number = number.group(1) if number else ""
            total = re.search(r"\[\s*de\s*(\d+)\s*\]", head.text())
            ficha.count = int(total.group(1)) if total else None
    if ficha.collection_slug and ficha.slug.startswith(ficha.collection_slug + "_"):
        ficha.number = ficha.slug[len(ficha.collection_slug) + 1:] if not ficha.number else ficha.number
    line = next((a.parent for a in body.find_all("a")
                 if a.attrs.get("href", "").lstrip("/").startswith("entidades/") and a.parent is not None), None)
    if line is not None:
        _read_publisher_line(line, ficha)
    rows = _rows(body)
    dist = rows.get("distribución")
    if dist is not None:
        tokens = [t.strip() for t in dist.text().split("·")]
        for token in tokens:
            if not token:
                continue
            if re.search(r"\d\s*(pts?\.?|€|\$|eur)|\d[\d.,]*\s*\S{1,3}\.?$", token, re.IGNORECASE) and not re.fullmatch(
                    r"[\d\sIVX-]+", token):
                ficha.price_text = token
            elif re.search(r"(?<!\d)(1[5-9]\d\d|20\d\d)(?!\d)", token):
                ficha.date_text = token
            else:
                ficha.distributor = smart_title(token)
        hint = next((n.attrs.get("title", "") for n in dist.walk() if n.tag == "span" and n.attrs.get("title")), "")
        ficha.price_amount, ficha.price_currency = _price(ficha.price_text, hint)
        ficha.year, ficha.month, ficha.day = parse_date(ficha.date_text)
        ficha.approximate_date = any("aproximada" in n.attrs.get("title", "") for n in dist.walk())
    if (row := rows.get("edición")) is not None:
        ficha.edition = row.text()
    if (row := rows.get("origen")) is not None:
        ficha.origin = row.text()
    if (row := rows.get("lengua")) is not None:
        ficha.language_text = row.text()
        into = re.search(r"\bal\s+(\w+)", ficha.language_text)
        named = LANGUAGES.get(into.group(1).lower()) if into else None
        if named is None and re.search(r"traducci", ficha.language_text, re.IGNORECASE):
            named = "es"      # «Traducción del inglés»: la edición está en español
        if named is None:
            original = re.search(r"\b(?:original\s+en|en)\s+(\w+)", ficha.language_text, re.IGNORECASE)
            named = LANGUAGES.get(original.group(1).lower()) if original else None
        ficha.language = named or ""
    if (row := rows.get("formato")) is not None:
        ficha.format = ", ".join(t.strip().capitalize() for t in row.text().split("·") if t.strip())
    if (row := rows.get("tamaño")) is not None:
        ficha.size = row.text()
    if (row := rows.get("paginación")) is not None:
        ficha.pages_text = row.text()
        pages = re.search(r"(\d+)\s*p[aá]g", ficha.pages_text, re.IGNORECASE)
        ficha.pages = int(pages.group(1)) if pages else None
    if (row := rows.get("color")) is not None:
        ficha.color_text = row.text()
    if (row := rows.get("impresión")) is not None:
        ficha.printing = smart_title(row.text())
    if (row := rows.get("registros")) is not None:
        text = row.text()
        isbn = re.search(r"ISBN\s*:?\s*([\dXx][\dXx\s-]{8,20})", text)
        digits = re.sub(r"[^\dXx]", "", isbn.group(1)) if isbn else ""
        if len(digits) in (10, 13) and digits[:3] in ("978", "979") or len(digits) == 10:
            ficha.isbn = digits
        elif len(digits) >= 12:
            ficha.gtin = digits
        issn = re.search(r"ISSN\s*:?\s*(\d{4}-?\d{3}[\dXx])", text)
        ficha.issn = issn.group(1) if issn else ""
        legal = re.search(r"Dep\.?\s*Legal\s*:?\s*(.+)$", text, re.IGNORECASE)
        ficha.legal_deposit = legal.group(1).strip() if legal else ""
    if (row := rows.get("autores")) is not None:
        ficha.credits, ficha.other_credits = _authors(row)
    if (row := rows.get("ediciones")) is not None:
        ficha.related = _related(row)
    ficha.genres, ficha.sagas = _tabs(tree)
    text_box = _find_class(tree, "div", "T3WISIWISI")
    if text_box is not None:
        ficha.comments = [re.sub(r"^[-–•]\s*", "", line) for line in _text_lines(text_box)]
    cover = _meta(tree, "og:image")
    if not cover:
        picture = next((n for n in tree.walk() if n.tag == "img" and n.attrs.get("id") == "img_principal"), None)
        cover = picture.attrs.get("src", "") if picture is not None else ""
    ficha.cover_image = urljoin(page_url, cover) if cover else ""
    return ficha


def _tabs(tree: Node) -> tuple[list[str], list[str]]:
    """(géneros, sagas) de las pestañas de la ficha."""
    genres, sagas = [], []
    for tab in (n for n in tree.walk() if n.tag == "div" and _has_class(n, "tabbable")):
        names = {a.attrs.get("href", "").lstrip("#"): re.sub(r"\d+$", "", a.text()).strip().lower()
                 for a in tab.find_all("a") if a.attrs.get("data-toggle") == "tab"}
        for pane in (n for n in tab.walk() if n.tag == "div" and _has_class(n, "tab-pane")):
            name = names.get(pane.attrs.get("id", ""), "")
            links = [a.text() for a in pane.find_all("a") if a.text()]
            if name.startswith("género"):
                genres = links
            elif name.startswith("saga"):
                sagas = [smart_title(x) for x in links]
    return genres, sagas


def edition_lines(ficha: TbFicha) -> list[str]:
    """Los datos de la edición que no tienen campo propio, una línea por dato."""
    rows = [("Colección", smart_title(ficha.collection_title)), ("Origen", ficha.origin), ("Edición", ficha.edition), ("Distribución", ficha.distributor),
            ("Grupo editorial", ficha.group), ("Ciudad", ficha.city), ("Lengua", ficha.language_text), ("Tamaño", ficha.size),
            ("Paginación", ficha.pages_text), ("Color", ficha.color_text), ("Impresión", ficha.printing),
            ("ISSN", ficha.issn), ("Depósito legal", ficha.legal_deposit)]
    rows += [(role, names) for role, names in ficha.other_credits.items()]
    return [f"- {label}: {value}" for label, value in rows if value]


def edition_notes(ficha: TbFicha, base_url: str = BASE) -> str:
    """Lo que la ficha aporta a las Notas: los datos de la edición, las ediciones relacionadas y el texto libre."""
    parts = []
    lines = edition_lines(ficha)
    if lines:
        parts.append("\n".join([TB_EDITION_HEADING, *lines]))
    if ficha.related:
        parts.append("\n".join([TB_RELATED_HEADING, *(f"- {line}" for line in ficha.related)]))
    if ficha.comments:
        parts.append("\n".join([COMMENTS_HEADING, *(f"- {line}" for line in ficha.comments)]))
    return "\n".join(parts)


# ---- Nombre de las colecciones a partir de su dirección (para el índice, sin descargar cada colección) ----------------

def _slug_word(token: str) -> str:
    return token.upper() if token.upper() in _SLUG_ACRONYMS else "-".join(p.capitalize() for p in token.split("-"))


def _slug_words(tokens: list[str]) -> str:
    text = " ".join(t if number and t in _LOWER_WORDS else _slug_word(t) for number, t in enumerate(tokens))
    return text[:1].upper() + text[1:]


_SLUG_ACRONYMS = {"DC", "JLA", "JSA", "JLX", "TV", "USA", "ECC", "DVD", "RPG", "FBI", "CIA", "3D", "DK"}


def slug_title(slug: str) -> tuple[str, str, str, str]:
    """(nombre, año, editorial, subtítulo) de «spiderman_1983_forum_planeta-deagostini» y de
    «batman_2019_ovni_press_-coleccion_80_aniversario-»: la dirección no lleva tildes ni mayúsculas, pero es lo único
    que trae el sitemap. La ficha completa el título real cuando se consulta."""
    tokens = slug.split("_")
    year_at = next((i for i, t in enumerate(tokens) if i > 0 and re.fullmatch(r"1[5-9]\d\d|20\d\d", t)), None)
    if year_at is None:
        return _slug_words(tokens), "", "", ""
    rest = tokens[year_at + 1:]
    sub_at = next((i for i, t in enumerate(rest) if t.startswith("-")), len(rest))
    subtitle = [t.strip("-") for t in rest[sub_at:] if t.strip("-")]
    return (_slug_words(tokens[:year_at]), tokens[year_at], " ".join(_slug_word(t) for t in rest[:sub_at]),
            _slug_words(subtitle) if subtitle else "")
