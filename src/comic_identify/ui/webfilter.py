"""Reglas de bloqueo de contenido del panel web: la publicidad de Tebeosfera y la medición de visitas de GCD.

Una ficha de Tebeosfera pesa unos 6 MB y ~110 peticiones: además de su propia página carga Google Tag Manager, Google
Analytics, publicidad de Google, el analizador de Ahrefs y el compilador de Tailwind por CDN, y unas imágenes de anuncios
propios de la web que suman más de 5 MB. Para consultar una ficha no hace falta nada de eso: esos servicios solo miden
visitas (y dejan sus cookies en el panel). Se bloquean, y con ellos deja de hacer falta el aviso de cookies de la web
(que pregunta por esas mismas cookies), que se oculta. Solo afecta a las páginas de Tebeosfera y a lo que ellas piden a
terceros; la propia web sigue cargando entera. A Universo Marvel y a GCD no se les toca su publicidad ni sus cookies
(ver `NO_COOKIES`): cada una tiene una razón para necesitar la suya.
"""
import json
import re

DOMAIN = "*tebeosfera.com"
# Servidores de medición y publicidad que cargan sus fichas (los vistos en una ficha real) y los habituales que podrían
# añadir después
TRACKERS = ("googletagmanager.com", "google-analytics.com", "analytics.google.com", "doubleclick.net",
            "googleadservices.com", "googlesyndication.com", "ahrefs.com", "facebook.net", "connect.facebook.com",
            "hotjar.com", "clarity.ms")
# los píxeles de conversión de Google, que no tienen servidor propio (WebKit no admite «a|b» en sus expresiones)
TRACKING_PATHS = (r"google\.com/pagead/", r"google\.es/pagead/", r"google\.com/ccm/", r"google\.es/ccm/")
# Los anuncios propios de la web (asociarse, colaborar, sus instituciones…): imágenes de varios MB que se ven en cada ficha
# y no son de ella (la portada y las muestras están en «T3_numeros»)
PROMOTIONS = ("/T3_avisos/", "/T3_instituciones/", "/neko/img/awasetoco.png")
BANNER = ".cc-cookies"
# Tebeosfera se consulta sin cookies: ni las envía el panel ni guarda las que le den (`block-cookies`); como aquí también
# se bloquea su publicidad (arriba), nada las necesita. Universo Marvel NO puede estar aquí ni GCD tampoco: a los
# visitantes de la Unión Europea, Universo Marvel les pone un aviso de consentimiento de publicidad (invisible desde
# fuera de la UE, donde se probó esto) que necesita una cookie para recordar que ya se aceptó; sin ella, vuelve a
# preguntar en cada ficha. Y GCD (comics.org) necesita la suya, `cf_clearance`, para su comprobación anti-robots de
# Cloudflare (sin ella, la página se queda en «Un momento…»). Ambas viven solo en memoria y se pierden al cerrar la
# aplicación: no se guarda ninguna cookie en disco.
NO_COOKIES = ("*tebeosfera.com",)
# La web de GCD (comics.org) carga además la medición de visitas de Cloudflare
GCD_TRACKERS = ("cloudflareinsights.com",)   # el aviso de cookies de la web (cookiecuttr)
HEAVY = ("cdn.tailwindcss.com",)   # un compilador de estilos que se descarga y ejecuta en cada ficha


def _block(pattern: str) -> dict:
    return {"trigger": {"url-filter": pattern, "if-domain": [DOMAIN]}, "action": {"type": "block"}}


def _for(domain: str, action: dict, pattern: str = ".*") -> dict:
    return {"trigger": {"url-filter": pattern, "if-domain": [domain]}, "action": action}


def rules() -> list[dict]:
    """La lista de reglas en el formato de bloqueo de contenido de WebKit."""
    found = [_block(re.escape(host)) for host in (*TRACKERS, *HEAVY)]
    found += [_block(path) for path in TRACKING_PATHS]
    found += [_block(re.escape(path)) for path in PROMOTIONS]
    found.append({"trigger": {"url-filter": ".*", "if-domain": [DOMAIN]},
                  "action": {"type": "css-display-none", "selector": BANNER}})
    found += [_for("*comics.org", {"type": "block"}, re.escape(host)) for host in GCD_TRACKERS]
    found += [_for(domain, {"type": "block-cookies"}) for domain in NO_COOKIES]
    return found


def rules_json() -> bytes:
    return json.dumps(rules()).encode()
