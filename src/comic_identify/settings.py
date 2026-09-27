"""Ajustes del usuario (clave de ComicVine y carpetas de la colección)."""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .assistant import PROMPT


def _xdg(variable: str, default: str) -> Path:
    return Path(os.environ.get(variable) or Path.home() / default) / "comic-identify"


CONFIG_FILE = _xdg("XDG_CONFIG_HOME", ".config") / "config.json"
LIBRARY_DB = _xdg("XDG_DATA_HOME", ".local/share") / "library.db"
GCD_DB = _xdg("XDG_DATA_HOME", ".local/share") / "gcd_es.db"
RENAME_LOG = _xdg("XDG_DATA_HOME", ".local/share") / "renames.log"
METADATA_LOG = _xdg("XDG_DATA_HOME", ".local/share") / "metadata.log"
GCSTAR_LOG = _xdg("XDG_DATA_HOME", ".local/share") / "gcstar.log"


@dataclass
class Settings:
    api_key: str = ""
    folders: list[str] = field(default_factory=list)
    assistant: str = "claude {prompt}"   # comando del asistente de IA; {prompt} se sustituye por el mensaje
    pattern: str = "{nombre} {volumen} {bandera} [{contenido}] ({edicion}) - {sello}"   # ver naming.py
    prompt: str = PROMPT   # mensaje que sustituye a {prompt} en el comando del asistente; {image} es la portada
    gcstar_path: str = ""   # archivo .gcs de GCstar al que transferir cómics ya catalogados

    @classmethod
    def load(cls, path: Path = CONFIG_FILE) -> "Settings":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        return cls(str(data.get("api_key", "")), [str(f) for f in data.get("folders", [])],
                   str(data.get("assistant") or cls.assistant), str(data.get("pattern") or cls.pattern),
                   str(data.get("prompt") or cls.prompt), str(data.get("gcstar_path", "")))

    def save(self, path: Path = CONFIG_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # La clave se guarda en claro; el archivo queda legible solo por el usuario.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"api_key": self.api_key, "folders": self.folders, "assistant": self.assistant,
                       "pattern": self.pattern,
                       "prompt": "" if self.prompt.strip() == PROMPT else self.prompt,   # el de serie no se congela
                       "gcstar_path": self.gcstar_path},
                      handle, indent=2)
