import json
import os
import time
import threading
import tempfile
import fcntl
from typing import Any, Dict

DEFAULT_CACHE = {
    "last_updated": 0,
    "items": [],  # list of dicts: {title, type, rating, audienceRating, contentRating, thumb, height}
    "idle": {"last_change": 0, "index": -1}
}

class CacheStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._lock = threading.RLock()
        self._mem = None
        if not os.path.exists(self.path):
            self._write(DEFAULT_CACHE.copy())
        else:
            try:
                self._mem = self._read()
            except Exception:
                self._mem = DEFAULT_CACHE.copy()
                self._write(self._mem)

    def _read(self) -> Dict[str, Any]:
        with self._lock:
            lock_path = self.path + ".lock"
            try:
                with open(lock_path, "a+") as lf:
                    try:
                        fcntl.flock(lf.fileno(), fcntl.LOCK_SH)
                    except Exception:
                        pass
                    with open(self.path, "r", encoding="utf-8") as f:
                        data = json.load(f)
            except Exception:
                return self._mem if self._mem is not None else DEFAULT_CACHE.copy()
            if "items" not in data: data["items"] = []
            if "last_updated" not in data: data["last_updated"] = 0
            if "idle" not in data: data["idle"] = {"last_change": 0, "index": -1}
            self._mem = data
            return data

    def _atomic_replace(self, tmp_path: str):
        dir_name = os.path.dirname(self.path)
        os.replace(tmp_path, self.path)
        try:
            dir_fd = os.open(dir_name, os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except Exception:
            pass

    def _write(self, data: Dict[str, Any]):
        with self._lock:
            lock_path = self.path + ".lock"
            try:
                with open(lock_path, "a+") as lf:
                    try:
                        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
                    except Exception:
                        pass
                    dir_name = os.path.dirname(self.path)
                    fd, tmp_path = tempfile.mkstemp(prefix="cache.", suffix=".tmp", dir=dir_name)
                    try:
                        with os.fdopen(fd, "w", encoding="utf-8") as tf:
                            json.dump(data, tf, indent=2)
                            tf.flush()
                            os.fsync(tf.fileno())
                        try:
                            if os.path.exists(self.path):
                                bak = self.path + ".bak"
                                try:
                                    os.replace(self.path, bak)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        self._atomic_replace(tmp_path)
                    finally:
                        if os.path.exists(tmp_path):
                            try:
                                os.remove(tmp_path)
                            except Exception:
                                pass
            finally:
                self._mem = data

    def get(self) -> Dict[str, Any]:
        return self._read()

    def set_items(self, items):
        data = self.get()
        data["items"] = items
        data["last_updated"] = int(time.time())
        idle = data.get("idle", {"last_change": 0, "index": -1})
        if idle.get("index", -1) >= len(items):
            idle["index"] = -1
        data["idle"] = idle
        self._write(data)

    def get_idle_state(self):
        data = self.get()
        idle = data.get("idle", {"last_change": 0, "index": -1})
        if "last_change" not in idle:
            idle["last_change"] = 0
        if "index" not in idle:
            idle["index"] = -1
        return idle

    def set_idle_state(self, idle_state):
        data = self.get()
        data["idle"] = idle_state
        self._write(data)
