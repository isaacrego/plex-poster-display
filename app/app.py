import os
import random
import threading
import time
from typing import Dict, Any

from flask import Flask, render_template, jsonify, request, redirect, url_for
from .config_store import ConfigStore
from .cache_store import CacheStore
from .plex import PlexClient

APP_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(APP_DIR, "data")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
CACHE_PATH = os.path.join(DATA_DIR, "cache.json")

CACHE_REFRESH_SECONDS = 1800  # 30 minutes
POLL_SESSIONS_SECONDS = 5

config_store = ConfigStore(CONFIG_PATH)
cache_store = CacheStore(CACHE_PATH)

app = Flask(__name__, static_folder="static", template_folder="templates")

def _fetch_and_filter_items(cfg: Dict[str, Any]):
    conn = cfg.get("connection", {})
    plex_ip = conn.get("plex_ip", "").strip()
    plex_token = conn.get("plex_token", "").strip()
    if not plex_ip or not plex_token:
        cache_store.set_items([])
        return

    client = PlexClient(plex_ip, plex_token)

    poster_cfg = cfg.get("poster", {})
    sections = client.get_sections()

    items = []
    lib_key = str(poster_cfg.get("library") or "").strip()
    if lib_key:
        items.extend(client.library_items(lib_key))
    else:
        for sec in sections:
            items.extend(client.library_items(sec["key"]))

    large_only = poster_cfg.get("large_only", True)
    rating_type = poster_cfg.get("rating_type", "critic")
    threshold = float(poster_cfg.get("rating_threshold", 0.0) or 0.0)
    mpaa_allowed = set(poster_cfg.get("mpaa_allowed", []))

    filtered = []
    for it in items:
        r = it.get("rating") if rating_type == "critic" else it.get("audienceRating")
        if r is not None and r < threshold:
            continue
        cr = it.get("contentRating") or "Unknown"
        if cr not in mpaa_allowed:
            if cr.startswith("TV-"):
                if "Unknown" not in mpaa_allowed:
                    continue
            else:
                continue
        if large_only:
            h = it.get("height")
            if h is not None and h < 1080:
                continue
        filtered.append(it)

    random.shuffle(filtered)
    cache_store.set_items(filtered)

def cache_refresh_loop():
    while True:
        cfg = config_store.get()
        try:
            _fetch_and_filter_items(cfg)
        except Exception:
            pass
        time.sleep(CACHE_REFRESH_SECONDS)

def start_background_threads():
    t = threading.Thread(target=cache_refresh_loop, daemon=True)
    t.start()

start_background_threads()

def current_status_payload() -> Dict[str, Any]:
    cfg = config_store.get()
    conn = cfg.get("connection", {})
    plex_ip = conn.get("plex_ip","").strip()
    plex_token = conn.get("plex_token","").strip()
    banner_cfg = cfg.get("banner", {})
    poster_cfg = cfg.get("poster", {})

    if not plex_ip or not plex_token:
        return {"connected": False, "message": "Not connected", "show_banners": False}

    client = PlexClient(plex_ip, plex_token)

    sessions = client.get_sessions()
    playing = None
    include_paused = bool(poster_cfg.get("paused_counts_as_playing", True))
    allowed = ("playing","buffering","paused") if include_paused else ("playing","buffering")
    # Filter to allowed and pick best: playing > buffering > paused, then by viewOffset desc, then updatedAt desc
    pri = {"playing":3, "buffering":2, "paused":1}
    candidates = [s for s in sessions if (s.get("state") or "").lower() in allowed]
    if candidates:
        candidates.sort(key=lambda s: (pri.get((s.get("state") or "").lower(),0), int(s.get("viewOffset",0) or 0), int(s.get("updatedAt",0) or 0)), reverse=True)
        playing = candidates[0]

    show_banners = True
    top_text = banner_cfg.get("idle_top_text","").strip()
    bottom_text = banner_cfg.get("bottom_text","").strip()
    active_text = banner_cfg.get("active_top_text","").strip()
    if not top_text and not bottom_text and not active_text:
        show_banners = False

    payload = {
        "connected": True,
        "show_banners": show_banners and banner_cfg.get("enable", True),
        "banner": {
            "font_family": banner_cfg.get("font_family", "neon"),
            "font_size": banner_cfg.get("font_size", 48),
            "font_color": banner_cfg.get("font_color", "#ff4df0"),
        },
        "fill_mode": poster_cfg.get("fill", "crop"),
    }

    if playing:
        img_rel = playing.get("thumb") or ""
        img = client.absolute_image_url(img_rel) if img_rel else None
        payload["now_playing"] = {"title": playing.get("title","Now Playing"), "image": img}
        payload["top_text"] = banner_cfg.get("active_top_text","NOW PLAYING")
        payload["bottom_text"] = bottom_text
    else:
        cache = cache_store.get()
        items = cache.get("items", [])
        rot_seconds = int(poster_cfg.get("idle_rotation_seconds", 20) or 20)
        idle_state = cache_store.get_idle_state()
        now = int(time.time())
        idx = idle_state.get("index", -1)
        if not items:
            chosen = None
        else:
            if idx < 0 or idx >= len(items) or (now - int(idle_state.get("last_change", 0))) >= rot_seconds:
                idx = (0 if idx < 0 or idx >= len(items) else (idx + 1) % len(items))
                idle_state["index"] = idx
                idle_state["last_change"] = now
                cache_store.set_idle_state(idle_state)
            chosen = items[idx] if 0 <= idx < len(items) else None
        if chosen:
            img = client.absolute_image_url(chosen.get("thumb",""))
            title = chosen.get("title","")
        else:
            img = None
            title = ""
        payload["idle"] = {"title": title, "image": img}
        payload["top_text"] = top_text
        payload["bottom_text"] = bottom_text

    return payload

from flask import Flask

@app.get("/")
def index():
    cfg = config_store.get()
    return render_template("index.html", cfg=cfg)

@app.get("/api/current")
def api_current():
    try:
        return jsonify(current_status_payload())
    except Exception:
        return jsonify({"connected": False, "message": "Temporary cache error"}), 200

@app.get("/config")
def config_page():
    cfg = config_store.get()
    return render_template("config.html", cfg=cfg)

@app.post("/config")
def save_config():
    cfg = config_store.get()

    plex_ip = request.form.get("plex_ip","").strip()
    plex_token = request.form.get("plex_token","").strip()
    cfg["connection"]["plex_ip"] = plex_ip
    cfg["connection"]["plex_token"] = plex_token

    cfg["poster"]["fill"] = request.form.get("fill","crop")
    cfg["poster"]["library"] = request.form.get("library","").strip()
    cfg["poster"]["large_only"] = bool(request.form.get("large_only"))
    cfg["poster"]["rating_type"] = request.form.get("rating_type","critic")
    cfg["poster"]["paused_counts_as_playing"] = bool(request.form.get("paused_counts_as_playing"))
    try:
        cfg["poster"]["rating_threshold"] = float(request.form.get("rating_threshold","0") or 0.0)
    except ValueError:
        cfg["poster"]["rating_threshold"] = 0.0
    try:
        cfg["poster"]["idle_rotation_seconds"] = int(request.form.get("idle_rotation_seconds","20") or 20)
    except ValueError:
        cfg["poster"]["idle_rotation_seconds"] = 20

    mpaa_allowed = request.form.getlist("mpaa_allowed")
    if not mpaa_allowed:
        mpaa_allowed = ["G","PG","PG-13","R","NC-17","Unknown"]
    cfg["poster"]["mpaa_allowed"] = mpaa_allowed

    cfg["banner"]["enable"] = bool(request.form.get("banner_enable"))
    cfg["banner"]["font_family"] = request.form.get("font_family","neon")
    try:
        cfg["banner"]["font_size"] = int(request.form.get("font_size","48") or "48")
    except ValueError:
        cfg["banner"]["font_size"] = 48
    cfg["banner"]["font_color"] = request.form.get("font_color","#ff4df0")
    cfg["banner"]["idle_top_text"] = request.form.get("idle_top_text","").strip()
    cfg["banner"]["active_top_text"] = request.form.get("active_top_text","").strip()
    cfg["banner"]["bottom_text"] = request.form.get("bottom_text","").strip()

    config_store.save(cfg)

    threading.Thread(target=_fetch_and_filter_items, args=(cfg,), daemon=True).start()

    return redirect(url_for("index"))

@app.post("/config/test")
def config_test():
    plex_ip = request.form.get("plex_ip","").strip()
    plex_token = request.form.get("plex_token","").strip()
    if not plex_ip or not plex_token:
        return jsonify({"ok": False, "message": "Please provide Plex IP and Token"}), 200
    client = PlexClient(plex_ip, plex_token)
    ok, msg = client.test_connection()
    return jsonify({"ok": ok, "message": msg}), 200

@app.post("/config/reset")
def config_reset():
    config_store.reset_except_connection()
    return redirect(url_for("config_page"))
