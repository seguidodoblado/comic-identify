"""Reglas de bloqueo de contenido del panel web para las fichas de Tebeosfera.

Una ficha de Tebeosfera pesa unos 6 MB y ~110 peticiones: además de su propia página carga Google Tag Manager, Google
Analytics, publicidad de Google, el analizador de Ahrefs y el compilador de Tailwind por CDN, y unas imágenes de anuncios
propios de la web que suman más de 5 MB. Para consultar una ficha no hace falta nada de eso: esos servicios solo miden
visitas (y dejan sus cookies en el panel). Se bloquean, y con ellos deja de hacer falta el aviso de cookies de la web
(que pregunta por esas mismas cookies), que se oculta. Solo afecta a las páginas de Tebeosfera y a lo que ellas piden a terceros; la propia web sigue cargando entera.
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
BANNER = ".cc-cookies"   # el aviso de cookies de la web (cookiecuttr)
HEAVY = ("cdn.tailwindcss.com",)   # un compilador de estilos que se descarga y ejecuta en cada ficha


def _block(pattern: str) -> dict:
    return {"trigger": {"url-filter": pattern, "if-domain": [DOMAIN]}, "action": {"type": "block"}}


def rules() -> list[dict]:
    """La lista de reglas en el formato de bloqueo de contenido de WebKit."""
    found = [_block(re.escape(host)) for host in (*TRACKERS, *HEAVY)]
    found += [_block(path) for path in TRACKING_PATHS]
    found += [_block(re.escape(path)) for path in PROMOTIONS]
    found.append({"trigger": {"url-filter": ".*", "if-domain": [DOMAIN]},
                  "action": {"type": "css-display-none", "selector": BANNER}})
    return found


def rules_json() -> bytes:
    return json.dumps(rules()).encode()
