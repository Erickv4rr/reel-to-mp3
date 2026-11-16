"""Local server behind the Reel to MP3 window.

The desktop app (app.py) starts this and shows it in its own window.
For development you can also run it directly and open http://localhost:8765.
Only reachable from this computer (127.0.0.1), and it refuses requests from other websites.
"""
import json
import mimetypes
import shutil
import sys
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from reel_to_mp3 import (APP_DIR, BROWSERS, DEFAULT_OUT, IS_MAC, IS_WIN, RES_DIR, USER_DIR,
                         download_mp3, open_path, read_cover, read_tags, reveal_path)
from version import REPO, __version__

HOST, PORT = "127.0.0.1", 8765
WEB_DIR = RES_DIR / "web"
CONFIG = USER_DIR / "config.json"
BITRATES = ["128", "192", "320"]
MAX_PARALLEL = 3

# Carry over the settings file from older versions that kept it next to the script.
if not CONFIG.exists() and (APP_DIR / "config.json").is_file():
    try:
        USER_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(APP_DIR / "config.json", CONFIG)
    except OSError:
        pass

jobs = {}  # id -> job dict
jobs_lock = threading.Lock()
picker_lock = threading.Lock()
slots = threading.Semaphore(MAX_PARALLEL)
update_info = {}  # filled by check_for_update()
tag_cache = {}  # (name, mtime) -> tags


# ---------------------------------------------------------------- settings

def load_settings():
    s = {"out_dir": str(DEFAULT_OUT), "bitrate": "192", "cookies": "none"}
    try:
        s.update({k: v for k, v in json.loads(CONFIG.read_text(encoding="utf-8")).items() if k in s})
    except (OSError, ValueError, AttributeError):
        pass
    if s["bitrate"] not in BITRATES:
        s["bitrate"] = "192"
    if s["cookies"] not in BROWSERS:
        s["cookies"] = "none"
    return s


SETTINGS = load_settings()
OUT_DIR = Path(SETTINGS["out_dir"])


def save_settings():
    USER_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(SETTINGS, indent=2), encoding="utf-8")


def set_out_dir(raw):
    """Validate, create and save a new download folder. Returns an error message or None."""
    global OUT_DIR
    raw = str(raw or "").strip().strip('"')
    if not raw:
        return "Enter a folder path."
    p = Path(raw).expanduser()
    if not p.is_absolute():
        return "Use a full folder path."
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".write_test"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as e:
        return f"Can't use that folder: {e.strerror or e}"
    OUT_DIR = p.resolve()
    SETTINGS["out_dir"] = str(OUT_DIR)
    save_settings()
    return None


def _own_window_picker(initial):
    """Fallback folder picker in a throwaway Tk window (used when running server.py directly)."""
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askdirectory(parent=root, initialdir=initial,
                                       title="Choose where Reel to MP3 saves files")
    finally:
        root.destroy()


# The desktop app replaces this with its window's native folder dialog.
folder_picker = _own_window_picker


def pick_folder():
    with picker_lock:
        return folder_picker(str(OUT_DIR)) or ""


# ---------------------------------------------------------------- downloads

def friendly_error(msg):
    msg = str(msg).replace("ERROR: ", "").split(" Check if", 1)[0].split(" Use --cookies", 1)[0]
    low = msg.lower()
    if "audio codec" in low:
        return "This video has no sound, so there is no audio to save."
    if "could not copy" in low and "cookie" in low:
        return "Couldn't read that browser's cookies. Close the browser completely and try again."
    if "login" in low or "empty media" in low or "rate-limit" in low or "cookies" in low:
        return ("Instagram wants you to be logged in for this one. Open Settings, set Login cookies "
                "to the browser where you're logged into Instagram, then retry.")
    if "unsupported url" in low:
        return "That doesn't look like a Reel or video post link."
    if "private" in low:
        return "This post is private."
    if "unable to download webpage" in low or "urlopen error" in low or "timed out" in low:
        return "Couldn't reach Instagram. Check your internet connection and retry."
    return msg


def update_job(job, **fields):
    with jobs_lock:
        job.update({k: v for k, v in fields.items() if v is not None or k in ("percent",)})


def run_job(job_id):
    job = jobs[job_id]
    with slots:
        update_job(job, stage="starting")

        def log(msg):
            with jobs_lock:
                job["log"].append(msg)
                del job["log"][:-30]

        def progress(d):
            update_job(job, stage=d.get("stage"), percent=d.get("percent"), title=d.get("title"),
                       uploader=d.get("uploader"), thumbnail=d.get("thumbnail"))

        try:
            path = download_mp3(job["url"], OUT_DIR, SETTINGS["cookies"], SETTINGS["bitrate"],
                                log=log, progress=progress)
            update_job(job, status="done", stage="done", percent=100, file=path.name)
        except Exception as e:
            update_job(job, status="error", stage="error", error=friendly_error(e))


def start_job(url):
    job_id = uuid.uuid4().hex[:8]
    with jobs_lock:
        jobs[job_id] = {"url": url, "status": "running", "stage": "queued", "percent": None,
                        "title": None, "uploader": None, "thumbnail": None, "log": [],
                        "file": None, "error": None, "started": time.time()}
    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()
    return job_id


def clean_url(u):
    u = u.strip().strip("<>\"'")
    if u and not u.startswith("http"):
        u = "https://" + u
    return u


# ---------------------------------------------------------------- library

def list_files():
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted(OUT_DIR.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []
    out = []
    for p in files:
        st = p.stat()
        key = (p.name, st.st_mtime)
        if key not in tag_cache:
            tag_cache[key] = read_tags(p)
        out.append({"name": p.name, "size": st.st_size, "mtime": st.st_mtime, **tag_cache[key]})
    return out


def safe_file(name):
    """Resolve a file name inside OUT_DIR, refusing anything that escapes it."""
    p = (OUT_DIR / name).resolve()
    if p.parent != OUT_DIR.resolve() or p.suffix.lower() != ".mp3" or not p.is_file():
        return None
    return p


def delete_file(p):
    try:
        from send2trash import send2trash
        send2trash(str(p))
    except ImportError:
        p.unlink()


# ---------------------------------------------------------------- misc

def read_clipboard():
    try:
        if IS_WIN:
            import ctypes
            from ctypes import wintypes
            u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
            u32.GetClipboardData.restype = wintypes.HANDLE
            k32.GlobalLock.restype = ctypes.c_void_p
            k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
            k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
            if not u32.OpenClipboard(None):
                return ""
            try:
                h = u32.GetClipboardData(13)  # CF_UNICODETEXT
                if not h:
                    return ""
                ptr = k32.GlobalLock(h)
                try:
                    return ctypes.wstring_at(ptr) if ptr else ""
                finally:
                    k32.GlobalUnlock(h)
            finally:
                u32.CloseClipboard()
        if IS_MAC:
            import subprocess
            return subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        pass
    return ""


def version_tuple(v):
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except ValueError:
        return (0,)


def check_for_update():
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                     headers={"User-Agent": "reel-to-mp3", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.load(r)
        latest = data.get("tag_name", "")
        if version_tuple(latest) > version_tuple(__version__):
            update_info.update({"version": latest.lstrip("v"), "url": data.get("html_url")})
    except Exception:
        pass


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def local_host(self):
        # Refuse requests whose Host isn't this machine (blocks DNS-rebinding tricks).
        port = self.server.server_port
        return self.headers.get("Host") in (f"localhost:{port}", f"127.0.0.1:{port}")

    def same_origin(self):
        # Block other websites from triggering actions through this server.
        port = self.server.server_port
        origin = self.headers.get("Origin")
        return origin is None or origin in (f"http://localhost:{port}", f"http://127.0.0.1:{port}")

    def do_GET(self):
        if not self.local_host():
            return self.send_json({"error": "forbidden"}, 403)
        url = urlparse(self.path)
        path = url.path
        if path in ("/", "/index.html"):
            return self.send_static(WEB_DIR / "index.html")
        if path in ("/favicon.svg", "/app.js", "/app.css"):
            return self.send_static(WEB_DIR / path.lstrip("/"))
        if path == "/api/state":
            return self.send_json({
                "version": __version__, "platform": "mac" if IS_MAC else "windows" if IS_WIN else "other",
                "folder": str(OUT_DIR), "settings": SETTINGS, "browsers": BROWSERS,
                "bitrates": BITRATES, "update": update_info or None, "repo": REPO})
        if path == "/api/files":
            return self.send_json({"folder": str(OUT_DIR), "files": list_files()})
        if path == "/api/jobs":
            with jobs_lock:
                data = sorted(({"id": k, **{x: v[x] for x in v if x != "log"}}
                               for k, v in jobs.items()), key=lambda j: j["started"], reverse=True)
            return self.send_json({"jobs": data[:30]})
        if path == "/api/clipboard":
            return self.send_json({"text": read_clipboard()})
        if path.startswith("/api/cover/"):
            p = safe_file(unquote(path[len("/api/cover/"):]))
            cover = read_cover(p) if p else None
            if not cover:
                return self.send_json({"error": "no cover"}, 404)
            return self.send_bytes(cover[0], cover[1], cache=True)
        if path.startswith("/files/"):
            p = safe_file(unquote(path[len("/files/"):]))
            if not p:
                return self.send_json({"error": "not found"}, 404)
            return self.send_file_range(p)
        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        if not self.local_host() or not self.same_origin():
            return self.send_json({"error": "forbidden"}, 403)
        path = urlparse(self.path).path
        data = self.read_json()
        if path == "/api/download":
            urls = [clean_url(u) for u in str(data.get("urls", "")).split()]
            urls = list(dict.fromkeys(u for u in urls if u))
            bad = [u for u in urls if "instagram.com/" not in u]
            if not urls:
                return self.send_json({"error": "Paste a Reel link first."}, 400)
            if bad:
                return self.send_json({"error": "That isn't an Instagram link."}, 400)
            return self.send_json({"jobs": [start_job(u) for u in urls]})
        if path == "/api/retry":
            with jobs_lock:
                job = jobs.pop(str(data.get("id")), None)
            if not job:
                return self.send_json({"error": "not found"}, 404)
            return self.send_json({"jobs": [start_job(job["url"])]})
        if path == "/api/dismiss":
            with jobs_lock:
                job = jobs.get(str(data.get("id")))
                if job and job["status"] != "running":
                    del jobs[str(data.get("id"))]
            return self.send_json({"ok": True})
        if path == "/api/clear-jobs":
            with jobs_lock:
                for k in [k for k, v in jobs.items() if v["status"] != "running"]:
                    del jobs[k]
            return self.send_json({"ok": True})
        if path == "/api/settings":
            if data.get("bitrate") in BITRATES:
                SETTINGS["bitrate"] = data["bitrate"]
            if data.get("cookies") in BROWSERS:
                SETTINGS["cookies"] = data["cookies"]
            if data.get("pick") or "path" in data:
                new = pick_folder() if data.get("pick") else data.get("path")
                if data.get("pick") and not new:
                    return self.send_json({"settings": SETTINGS, "folder": str(OUT_DIR), "cancelled": True})
                err = set_out_dir(new)
                if err:
                    return self.send_json({"error": err, "settings": SETTINGS, "folder": str(OUT_DIR)}, 400)
            save_settings()
            return self.send_json({"settings": SETTINGS, "folder": str(OUT_DIR)})
        if path == "/api/reveal":
            p = safe_file(str(data.get("name", "")))
            if not p:
                return self.send_json({"error": "not found"}, 404)
            reveal_path(p)
            return self.send_json({"ok": True})
        if path == "/api/delete":
            p = safe_file(str(data.get("name", "")))
            if not p:
                return self.send_json({"error": "not found"}, 404)
            try:
                delete_file(p)
            except OSError as e:
                return self.send_json({"error": f"Couldn't delete: {e.strerror or e}"}, 400)
            return self.send_json({"ok": True})
        if path == "/api/open-folder":
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            open_path(OUT_DIR)
            return self.send_json({"ok": True})
        if path == "/api/open-url":
            url = str(data.get("url", ""))
            allowed = (f"https://github.com/{REPO}", "https://www.instagram.com/")
            if not url.startswith(allowed):
                return self.send_json({"error": "forbidden"}, 403)
            import webbrowser
            webbrowser.open(url)
            return self.send_json({"ok": True})
        self.send_json({"error": "not found"}, 404)

    def send_bytes(self, data, ctype, cache=False):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def send_static(self, p):
        self.send_bytes(p.read_bytes(), (mimetypes.guess_type(p.name)[0] or "application/octet-stream")
                        + ("; charset=utf-8" if p.suffix in (".html", ".js", ".css", ".svg") else ""))

    def send_file_range(self, p):
        """Serve a file with HTTP Range support, so the audio player can seek."""
        size = p.stat().st_size
        start, end = 0, size - 1
        rng = self.headers.get("Range", "")
        partial = rng.startswith("bytes=")
        if partial:
            try:
                a, b = rng[6:].split(",")[0].split("-")
                if a:
                    start, end = int(a), int(b) if b else size - 1
                else:
                    start = max(0, size - int(b))
                end = min(end, size - 1)
                if start > end:
                    raise ValueError
            except ValueError:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Disposition", f"inline; filename*=UTF-8''{quote(p.name)}")
        self.end_headers()
        with open(p, "rb") as f:
            f.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    chunk = f.read(min(65536, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (ConnectionError, OSError):
                pass  # the player stopped reading (seek / pause)


def make_server(ports):
    for port in ports:
        try:
            return ThreadingHTTPServer((HOST, port), Handler)
        except OSError:
            continue
    raise SystemExit("Reel to MP3 could not find a free network port.")


if __name__ == "__main__":
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else PORT
    srv = make_server([port])
    threading.Thread(target=check_for_update, daemon=True).start()
    print(f"Reel to MP3 {__version__} running at http://localhost:{srv.server_port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
