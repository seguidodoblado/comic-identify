import json
import re

from comic_identify import webfilter


def blocked(url: str) -> bool:
    """Si alguna regla de bloqueo (en su sintaxis de expresión regular) casaría con esa dirección."""
    return any(rule["action"]["type"] == "block" and re.search(rule["trigger"]["url-filter"], url)
               for rule in webfilter.rules())


def test_the_third_party_trackers_of_a_ficha_are_blocked_and_the_site_itself_is_not():
    for url in ("https://www.googletagmanager.com/gtag/js?id=AW-435585661", "https://www.google-analytics.com/collect?v=1",
                "https://region1.analytics.google.com/g/collect", "https://stats.g.doubleclick.net/j/collect",
                "https://ad.doubleclick.net/activity", "https://analytics.ahrefs.com/analytics.js",
                "https://cdn.tailwindcss.com/", "https://www.google.es/pagead/1p-user-list/435585661/",
                "https://www.google.com/ccm/collect?en=page_view",
                "https://www.tebeosfera.com/T3content/img/T3_avisos/d/j/banner.png",
                "https://www.tebeosfera.com/T3content/img/T3_instituciones/5/m/tn_logo.jpg",
                "https://www.tebeosfera.com/neko/img/awasetoco.png",
                "https://static.cloudflareinsights.com/beacon.min.js"):
        assert blocked(url), url
    for url in ("https://www.tebeosfera.com/numeros/universo_dc_1989_zinco_10.html",
                "https://www.tebeosfera.com/T3content/img/T3_numeros/1/0/portada.jpg",
                "https://www.tebeosfera.com/T3content/img/T3_numeros/r/t/batman_7_port/w-423_batman_7_port.jpeg", "https://www.tebeosfera.com/neko/js/js2.js",
                "https://fonts.googleapis.com/css?family=Open+Sans", "https://www.google.com/search?q=comics"):
        assert not blocked(url), url


def test_trackers_and_the_cookie_notice_only_concern_tebeosfera_and_gcd_only_loses_its_cloudflare_beacon():
    rules = webfilter.rules()
    others = [rule for rule in rules if rule["action"]["type"] in ("block", "css-display-none")
              and rule["trigger"]["if-domain"] != ["*tebeosfera.com"]]
    assert [(r["trigger"]["if-domain"], r["trigger"]["url-filter"]) for r in others] == [
        (["*comics.org"], "cloudflareinsights\\.com")]
    hide = [rule for rule in rules if rule["action"]["type"] == "css-display-none"]
    assert [rule["action"]["selector"] for rule in hide] == [".cc-cookies"]
    assert {rule["action"]["type"] for rule in rules} == {"block", "css-display-none", "block-cookies"}


def test_only_tebeosfera_is_consulted_without_cookies():
    cookies = [rule for rule in webfilter.rules() if rule["action"]["type"] == "block-cookies"]
    assert sorted(rule["trigger"]["if-domain"][0] for rule in cookies) == ["*tebeosfera.com"]
    assert all(rule["trigger"]["url-filter"] == ".*" for rule in cookies)   # todas las peticiones de esa web
    # GCD necesita `cf_clearance` (su comprobación anti-robots) y Universo Marvel, la suya de consentimiento: a
    # ninguna de las dos se le bloquean las cookies
    assert not any(domain in ("*comics.org", "*universomarvel.com") for rule in cookies
                   for domain in rule["trigger"]["if-domain"])


def test_the_rules_are_valid_json_for_webkit():
    parsed = json.loads(webfilter.rules_json())
    assert isinstance(parsed, list) and len(parsed) == len(webfilter.rules())
    assert all({"trigger", "action"} <= set(rule) for rule in parsed)


def test_rules_only_use_the_regular_expression_syntax_webkit_supports():
    # WebKit rechaza toda la lista si una regla lleva alternativas («a|b»): «Disjunctions are not supported yet»
    assert all("|" not in rule["trigger"]["url-filter"] for rule in webfilter.rules())
