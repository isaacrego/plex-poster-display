import json
import os
from typing import Any, Dict

DEFAULT_CONFIG = {
    "connection": {
        "plex_ip": "",
        "plex_token": ""
    },
    "poster": {
        "library": "",
        "fill": "crop",  # fill-stretch | crop | fill-aspect
        "large_only": True,
        "rating_type": "critic",  # critic | audience
        "rating_threshold": 0.0,
        "idle_rotation_seconds": 20,
        "paused_counts_as_playing": True,
        "mpaa_allowed": ["G", "PG", "PG-13", "R", "NC-17", "Unknown"]
    },
    "banner": {
        "enable": True,
        "font_family": "neon",
        "font_size": 48,
        "font_color": "#ff4df0",
        "idle_top_text": "COMING SOON",
        "active_top_text": "NOW PLAYING",
        "bottom_text": ""
    }
}

class ConfigStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.exists(self.path):
            self._write(DEFAULT_CONFIG.copy())

    def _read(self) -> Dict[str, Any]:
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data: Dict[str, Any]):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get(self) -> Dict[str, Any]:
        data = self._read()
        def merge(defaults, current):
            for k, v in defaults.items():
                if k not in current:
                    current[k] = v
                elif isinstance(v, dict) and isinstance(current[k], dict):
                    merge(v, current[k])
            return current
        return merge(json.loads(json.dumps(DEFAULT_CONFIG)), data)

    def save(self, data: Dict[str, Any]):
        self._write(data)

    def reset_except_connection(self):
        current = self.get()
        kept = current.get("connection", {})
        new_data = json.loads(json.dumps(DEFAULT_CONFIG))
        new_data["connection"] = kept
        self._write(new_data)
