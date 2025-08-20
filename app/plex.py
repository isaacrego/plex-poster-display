import requests
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Tuple

class PlexClient:
    def __init__(self, ip: str, token: str, timeout: int = 5):
        self.ip = ip.strip()
        self.token = token.strip()
        self.timeout = timeout

    def _url(self, path: str) -> str:
        base = self.ip
        if not base.startswith("http://") and not base.startswith("https://"):
            base = "http://" + base
        if ":" not in base.split("//", 1)[1]:
            base += ":32400"
        if not path.startswith("/"):
            path = "/" + path
        return f"{base}{path}"

    def _get(self, path: str, params: Dict[str, str] = None) -> Optional[ET.Element]:
        if not self.token or not self.ip:
            return None
        params = (params or {}).copy()
        params["X-Plex-Token"] = self.token
        try:
            r = requests.get(self._url(path), params=params, timeout=self.timeout)
            r.raise_for_status()
            return ET.fromstring(r.content)
        except Exception:
            return None

    def test_connection(self) -> Tuple[bool, str]:
        root = self._get("status/sessions")
        if root is None:
            return False, "Failed to fetch /status/sessions"
        return True, "OK"

    def get_sections(self) -> List[Dict[str, str]]:
        root = self._get("library/sections")
        if root is None:
            return []
        sections = []
        for d in root.findall(".//Directory"):
            sec_type = d.get("type", "")
            if sec_type in ("movie", "show"):
                sections.append({"key": d.get("key",""), "title": d.get("title",""), "type": sec_type})
        return sections

    def get_sessions(self) -> List[Dict[str,str]]:
        root = self._get("status/sessions")
        if root is None:
            return []
        sessions: List[Dict[str, str]] = []
        for v in root.findall(".//Video"):
            # Playback state is reliably on the <Player> element
            player = v.find(".//Player")
            state = (player.get("state") if player is not None else (v.get("state") or "")) or ""
            # Choose a usable image
            thumb = v.get("thumb") or v.get("grandparentThumb") or v.get("art") or ""
            title = v.get("title") or v.get("parentTitle") or v.get("grandparentTitle") or "Now Playing"
            sessions.append({
                "state": state,
                "title": title,
                "thumb": thumb,
                "type": v.get("type","video"),
                "viewOffset": int(v.get("viewOffset","0") or 0),
                "updatedAt": int(v.get("updatedAt","0") or 0)
            })
        return sessions

    def library_items(self, section_key: str, page_size: int = 200, max_pages: int = 100):
        items = []
        start = 0
        for _ in range(max_pages):
            params = {"X-Plex-Container-Start": str(start), "X-Plex-Container-Size": str(page_size)}
            root = self._get(f"library/sections/{section_key}/all", params=params)
            if root is None:
                break
            md = root.findall(".//Video") + root.findall(".//Directory")
            if not md: break
            for el in md:
                itype = el.get("type", "unknown")
                if itype not in ("movie", "show"): continue
                thumb = el.get("thumb") or el.get("art") or ""
                title = el.get("title", "Untitled")
                rating = el.get("rating")
                audienceRating = el.get("audienceRating")
                contentRating = el.get("contentRating", "Unknown")
                height = None
                media = el.find(".//Media")
                if media is not None:
                    h = media.get("height")
                    if h and h.isdigit():
                        height = int(h)
                items.append({
                    "type": itype, "title": title, "thumb": thumb,
                    "rating": float(rating) if rating else None,
                    "audienceRating": float(audienceRating) if audienceRating else None,
                    "contentRating": contentRating or "Unknown",
                    "height": height,
                })
            size = int(root.get("size", "0") or "0")
            totalSize = int(root.get("totalSize", "0") or "0")
            if start + size >= totalSize or size == 0: break
            start += page_size
        return items

    def absolute_image_url(self, path: str) -> Optional[str]:
        if not path: return None
        return f"{self._url(path)}?X-Plex-Token={self.token}"
