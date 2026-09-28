"""Accesos directos a webs de cómic en español: abren su búsqueda en el navegador del usuario.

No se rastrea ni se leen esas webs desde la aplicación (varias lo prohíben en su robots.txt o no tienen API):
es el navegador, a petición del usuario, quien carga la búsqueda.
"""
from typing import NamedTuple
from urllib.parse import quote_plus

GOOGLE = "https://www.google.com/search?q={}"
GENERAL, MARVEL, DC = "Generalistas", "Marvel", "DC"
GROUPS = (GENERAL, MARVEL, DC)   # orden en el menú


class Source(NamedTuple):
    name: str
    template: str | None    # búsqueda propia de la web, con {q}
    domain: str | None      # si no tiene: búsqueda «site:» en Google
    host: str               # servidor de la web: de él se toma el icono
    category: str = GENERAL  # en qué grupo se muestra en el menú


SOURCES = (
    Source("Tebeosfera", None, "tebeosfera.com", "www.tebeosfera.com"),
    Source("Whakoom", None, "whakoom.com", "www.whakoom.com"),
    Source("Norma", None, "normaeditorial.com", "www.normaeditorial.com"),
    Source("Norma Comics", None, "normacomics.com", "www.normacomics.com"),   # la tienda de cómics de Norma
    Source("Panini", "https://www.panini.es/shp_esp_es/catalogsearch/result/?q={q}", None, "www.panini.es"),
    # Catálogo de ediciones españolas de Marvel (Forum, Planeta, Panini)
    Source("Universo Marvel", None, "fichas.universomarvel.com", "fichas.universomarvel.com", MARVEL),
    # Web oficial de DC (en inglés); su robots.txt veta su buscador, por eso va por «site:» en Google
    Source("DC Comics", None, "dc.com", "www.dc.com", DC),
    # Wiki de DC (en inglés): número original, fechas y contenido de cada ejemplar
    Source("DC Database", None, "dc.fandom.com", "dc.fandom.com", DC),
    Source("Zona Negativa", "https://www.zonanegativa.com/?s={q}", None, "www.zonanegativa.com"),
)
NAMES = tuple(source.name for source in SOURCES)

# Dónde comprar el ejemplar físico: enlaces de búsqueda que se abren en el navegador (sin rastrear nada y sin enlaces
# de afiliado). Forum/Planeta y Vértice ya no publican: sus números solo se encuentran de segunda mano; Panini vende
# su catálogo actual. Direcciones comprobadas: Wallapop y Casa del Libro redirigen desde sus rutas antiguas a estas.
EDITORIAL, USED, STORES = "Editorial", "Segunda mano", "Tiendas"
SHOP_GROUPS = (EDITORIAL, USED, STORES)
SHOPS = (
    Source("Panini", "https://www.panini.es/shp_esp_es/catalogsearch/result/?q={q}", None, "www.panini.es", EDITORIAL),
    Source("Todocolección", "https://www.todocoleccion.net/buscador?bu={q}", None, "www.todocoleccion.net", USED),
    Source("eBay.es", "https://www.ebay.es/sch/i.html?_nkw={q}", None, "www.ebay.es", USED),
    Source("Wallapop", "https://es.wallapop.com/search?keywords={q}", None, "es.wallapop.com", USED),
    Source("Milanuncios", "https://www.milanuncios.com/anuncios/?s={q}", None, "www.milanuncios.com", USED),
    Source("Iberlibro", "https://www.iberlibro.com/servlet/SearchResults?kn={q}", None, "www.iberlibro.com", USED),
    Source("Amazon.es", "https://www.amazon.es/s?k={q}", None, "www.amazon.es", STORES),
    Source("Casa del Libro", "https://www.casadellibro.com/libros?q={q}", None, "www.casadellibro.com", STORES),
)


def search_url(name: str, title: str, number: str = "", publisher: str = "", year: str = "") -> str:
    """Dirección de búsqueda en la web `name` del título y, si se dan, número, editorial y año."""
    text = " ".join(part for part in (title.strip(), number.strip(), publisher.strip(), year.strip()) if part)
    if not text:
        raise ValueError("Falta el título.")
    for source in SOURCES:
        if source.name == name:
            if source.template:
                return source.template.format(q=quote_plus(text))
            return GOOGLE.format(quote_plus(f"site:{source.domain} {text}"))
    raise ValueError(f"Fuente desconocida: {name}")


def shop_url(name: str, title: str, number: str = "", publisher: str = "", year: str = "") -> str:
    """Dirección de búsqueda del título (y, si se dan, número, editorial y año) en la tienda `name`."""
    text = " ".join(part for part in (title.strip(), number.strip(), publisher.strip(), year.strip()) if part)
    if not title.strip():
        raise ValueError("Falta el título.")
    for shop in SHOPS:
        if shop.name == name:
            return shop.template.format(q=quote_plus(text))
    raise ValueError(f"Tienda desconocida: {name}")
