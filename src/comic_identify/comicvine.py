"""Cliente mínimo de la API de ComicVine (clave gratuita: https://comicvine.gamespot.com/api/)."""
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

from .i18n import _

API = "https://comicvine.gamespot.com/api"
USER_AGENT = "comic-identify/0.1 (+https://github.com/)"


class ComicVineError(RuntimeError):
    pass


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise ComicVineError(_("HTTP {code} al consultar ComicVine.").format(code=error.code)) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise ComicVineError(_("No se pudo conectar con ComicVine: {error}").format(error=error)) from error


class ComicVineClient:
    def __init__(self, api_key: str, fetch: Callable[[str], bytes] = _fetch):
        self.api_key, self._fetch = api_key, fetch

    def _get(self, path: str, **params) -> list[dict]:
        query = urllib.parse.urlencode({"api_key": self.api_key, "format": "json", **params})
        try:
            data = json.loads(self._fetch(f"{API}/{path}/?{query}"))
        except ValueError as error:
            raise ComicVineError(_("Respuesta de ComicVine no válida.")) from error
        if data.get("status_code") != 1:
            raise ComicVineError(_("ComicVine: {error}").format(error=data.get('error', _('error desconocido'))))
        return data.get("results", [])

    def search_volumes(self, text: str, limit: int = 5) -> list[dict]:
        return self._get("search", resources="volume", query=text, limit=limit,
                         field_list="id,name,start_year,publisher,image,site_detail_url,count_of_issues")

    def issues(self, volume_id: int, number: str) -> list[dict]:
        return self._get("issues", filter=f"volume:{volume_id},issue_number:{number}",
                         field_list="id,name,issue_number,cover_date,volume,image,site_detail_url")

    def download(self, url: str) -> bytes:
        return self._fetch(url)
