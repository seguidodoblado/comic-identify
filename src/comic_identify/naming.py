"""Nombres normalizados de archivo según `Estructura.md`.

Formato: `Título Volumen X 🇺🇸/🇪🇸 [años del contenido] (años de la edición) - Sello - Editorial`, y si contenido y
edición coinciden se omite el paréntesis. El patrón es configurable con las variables de `VARIABLES`.
"""
import re
from dataclasses import dataclass

VARIABLES = ("nombre", "volumen", "bandera", "contenido", "edicion", "editorial", "sello", "numero")
DEFAULT_PATTERN = "{nombre} {volumen} {bandera} [{contenido}] ({edicion}) - {sello} - {editorial}"
FLAGS = {"es": "🇪🇸", "us": "🇺🇸"}   # los demás países se dejan vacíos: los elige el usuario
MAX_NAME_BYTES = 255                  # límite de nombre de archivo en ext4


@dataclass
class Values:
    nombre: str = ""
    volumen: str = ""      # «8» se escribe «Volumen 8»; cualquier otro texto se respeta
    bandera: str = ""      # 🇪🇸 o 🇺🇸: la edición concreta, no el idioma
    contenido: str = ""    # años del material original, [AAAA] o [AAAA-AAAA]
    edicion: str = ""      # años de la edición concreta, (AAAA) o (AAAA-AAAA)
    sello: str = ""        # el sello impreso en el ejemplar (Forum, Vértice…), que es lo que distingue la edición
    numero: str = ""
    editorial: str = ""    # quién la publica (Planeta DeAgostini, Panini…); al final, para no desplazar posicionalmente
                           # los campos existentes (no va en el patrón por defecto)


def check_pattern(pattern: str) -> None:
    """Lanza ValueError si el patrón usa variables desconocidas o llaves sueltas."""
    unknown = sorted(set(re.findall(r"\{(\w+)\}", pattern)) - set(VARIABLES))
    if unknown:
        raise ValueError(f"Variable desconocida: {', '.join('{' + u + '}' for u in unknown)}. "
                         f"Disponibles: {', '.join('{' + v + '}' for v in VARIABLES)}.")
    if re.search(r"[{}]", re.sub(r"\{\w+\}", "", pattern)):
        raise ValueError("Hay una llave { o } sin cerrar en el patrón.")


def _years(text: str) -> str:
    return re.sub(r"\s+", "", text.replace("–", "-").replace("—", "-"))


def _volume(text: str) -> str:
    text = text.strip()
    return f"Volumen {text}" if text.isdigit() else text


def sanitize(name: str) -> str:
    """Un nombre válido en Linux: sin «/» ni NUL, ni espacios o puntos al principio o al final."""
    return name.replace("/", "-").replace("\x00", "").strip(" .")


def render(pattern: str, values: Values) -> str:
    """Nombre (sin extensión). Los grupos `[…]`/`(…)` vacíos se omiten, y cada tramo del patrón separado por
    « - » que quede vacío se omite entero (no solo el último): así se pueden encadenar varios datos opcionales,
    como el sello y la editorial, sin dejar guiones sueltos si falta alguno de ellos.

    Esto divide el propio texto del PATRÓN por « - » (no el resultado ya sustituido), así que un valor que
    contenga esa misma secuencia (p. ej. un rango de años escrito «1990 - 1992») no se confunde con un separador.
    """
    check_pattern(pattern)
    contenido, edicion = _years(values.contenido), _years(values.edicion)
    if edicion == contenido:   # regla de Estructura.md: si coinciden, solo los años del contenido
        edicion = ""
    parts = {"nombre": values.nombre.strip(), "volumen": _volume(values.volumen), "bandera": values.bandera.strip(),
             "contenido": contenido, "edicion": edicion, "editorial": values.editorial.strip(),
             "sello": values.sello.strip(), "numero": values.numero.strip()}

    def substitute(chunk: str) -> str:
        text = re.sub(r"\{(\w+)\}", lambda match: parts[match.group(1)], chunk)
        text = re.sub(r"\[\s*\]|\(\s*\)", "", text)
        return re.sub(r"\s{2,}", " ", text).strip()

    chunks = [substitute(chunk) for chunk in pattern.split(" - ")]
    return sanitize(" - ".join(chunk for chunk in chunks if chunk))


def missing_content_years(pattern: str, values: Values) -> bool:
    """El patrón lleva los años del contenido pero no se conocen: el nombre llevará solo los de la edición."""
    return "{contenido}" in pattern and not values.contenido.strip()


def flag_for(country: str) -> str:
    return FLAGS.get(country.lower(), "")


def suggest_values(candidate) -> Values:
    """Valores iniciales a partir de una sugerencia; el usuario los revisa y corrige antes de renombrar."""
    if candidate.source == "GCD":
        flag = flag_for(candidate.country)
        edition = candidate.year or _years(candidate.years)
        # El sello es lo que otro colaborador transcribió en GCD: el primer tramo («Forum; Marvel Comics»).
        return Values(nombre=candidate.series, bandera=flag, edicion=edition,
                      contenido=edition if flag == FLAGS["us"] else "",   # una edición 🇺🇸 es su propio original
                      editorial=candidate.publisher.strip(), sello=candidate.brand.split(";")[0].strip(),
                      numero=candidate.number)
    if candidate.source == "Universo Marvel":   # una edición española: el año es el de la edición
        return Values(nombre=candidate.series, volumen=candidate.extra.get("Volume", ""), bandera=FLAGS["es"],
                      edicion=candidate.year, editorial=candidate.publisher, sello=candidate.brand,
                      numero=candidate.number)
    if candidate.source == "ComicVine":
        return Values(nombre=candidate.series, bandera=FLAGS["us"], contenido=candidate.year,
                      edicion=candidate.year, numero=candidate.number)
    return Values(nombre=candidate.title)


def detect_number(stem: str) -> tuple[str, bool]:
    """Número de ejemplar que trae el nombre de un archivo: (número, dudoso). ('', False) si no hay ninguno.

    Se prefiere lo que está fuera de paréntesis y corchetes, se descartan los años (1900-2100) y, si aún quedan
    varios números, se toma el último y se marca como dudoso.
    """
    if match := re.search(r"#\s*(\d+)\s*$", stem):   # « #05» al final: un archivo ya normalizado
        return match.group(1), False
    outside = re.sub(r"[(\[][^)\]]*[)\]]", " ", stem)
    for text in (outside, stem):
        candidates = [n for n in re.findall(r"\d+", text) if not (len(n) == 4 and 1900 <= int(n) <= 2100)]
        if candidates:
            return candidates[-1], len(candidates) > 1
    return "", False


def parse_name(name: str) -> Values:
    """Lo contrario de `render` con el patrón por defecto: nombre, volumen, bandera, años y sello de un nombre de
    carpeta o de archivo ya normalizado (se ignora el « #05» final). Lo que no reconoce queda en `nombre`."""
    text = re.sub(r"\s+#\s*\d+\s*$", "", name.strip())
    sello = ""
    if match := re.search(r"\s-\s+([^\[\]()\U0001F1E6-\U0001F1FF]+)$", text):
        sello, text = match.group(1).strip(), text[:match.start()]
    edicion = contenido = ""
    if match := re.search(r"\(([\d\s\-–—]+)\)\s*$", text):
        edicion, text = _years(match.group(1)), text[:match.start()].rstrip()
    if match := re.search(r"\[([\d\s\-–—]+)\]\s*$", text):
        contenido, text = _years(match.group(1)), text[:match.start()].rstrip()
    bandera = next((flag for flag in FLAGS.values() if flag in text), "")
    if bandera:
        text = text.replace(bandera, " ")
    volumen = ""
    if match := re.search(r"\s+Volumen\s+(\S+)\s*$", text):
        volumen, text = match.group(1), text[:match.start()]
    return Values(nombre=re.sub(r"\s{2,}", " ", text).strip(), volumen=volumen, bandera=bandera, contenido=contenido,
                  edicion=edicion, sello=sello)


def looks_normalized(values: Values) -> bool:
    """¿Un nombre leído con `parse_name` parece normalizado? Hace falta bandera o años: un « - texto» final por sí solo
    (como en «00 - Por colocar» o «Batman - El regreso») no es un sello."""
    return bool(values.bandera or values.contenido or values.edicion)


def pad_number(number: int, width: int) -> str:
    return str(number).zfill(width)


def number_width(numbers: list[int]) -> int:
    """Cifras con las que se escriben los números: mínimo dos (01, 02…) y las del número más alto si tiene más."""
    return max([2] + [len(str(n)) for n in numbers])


def years_text(began: int | None, ended: int | None) -> str:
    """`2000-2002`, `2006` (un solo año) o `2011-` (sigue publicándose o no consta el final)."""
    if not began:
        return ""
    if not ended:
        return f"{began}-"
    return str(began) if began == ended else f"{began}-{ended}"


def series_values(info) -> Values:
    """Valores iniciales para el nombre de una carpeta a partir de los datos de la serie en GCD."""
    return Values(nombre=info.name, bandera=flag_for(info.country), edicion=years_text(info.year_began, info.year_ended),
                  editorial=info.publisher.strip(), sello=info.brand.split(";")[0].strip())


def natural_key(name: str) -> list:
    """Orden natural: `Batman 2` antes que `Batman 10`."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name.lower())]
