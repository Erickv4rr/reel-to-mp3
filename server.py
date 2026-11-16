"""Local web UI for Reel to MP3.

Run:  .venv\\Scripts\\pythonw.exe server.py   (or double-click start-web.bat)
Open: http://localhost:8765
"""
import json
import shutil
import mimetypes
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from reel_to_mp3 import APP_DIR, BROWSERS, DEFAULT_OUT, RES_DIR, USER_DIR, download_mp3, open_path

HOST, PORT = "127.0.0.1", 8765
WEB_DIR = RES_DIR / "web"
CONFIG = USER_DIR / "config.json"

# Carry over the settings file from older versions that kept it next to the script.
if not CONFIG.exists() and (APP_DIR / "config.json").is_file():
    try:
        USER_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(APP_DIR / "config.json", CONFIG)
    except OSError:
        pass

jobs = {}  # id -> {url, status, log, file, started}
jobs_lock = threading.Lock()
picker_lock = threading.Lock()


def load_out_dir():
    try:
        return Path(json.loads(CONFIG.read_text(encoding="utf-8"))["out_dir"])
    except (OSError, ValueError, KeyError):
        return DEFAULT_OUT


OUT_DIR = load_out_dir()


def set_out_dir(raw):
    """Validate, create and save a new download folder. Returns an error message or None."""
    global OUT_DIR
    raw = str(raw or "").strip().strip('"')
    if not raw:
        return "Enter a folder path."
    p = Path(raw).expanduser()
    if not p.is_absolute():
        return "Use a full path, like D:\\Music\\Reels."
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".write_test"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as e:
        return f"Can't use that folder: {e.strerror or e}"
    OUT_DIR = p.resolve()
    USER_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps({"out_dir": str(OUT_DIR)}, indent=2), encoding="utf-8")
    return None


def _own_window_picker(initial):
    """Folder picker in a throwaway Tk window (fine on Windows; macOS needs the main thread)."""
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


# The desktop app replaces this with a picker that runs on its main (Tk) thread.
folder_picker = _own_window_picker


def pick_folder():
    """Show a folder picker. Returns a path or ''."""
    with picker_lock:
        return folder_picker(str(OUT_DIR)) or ""


def run_job(job_id, cookies):
    job = jobs[job_id]

    def log(msg):
        with jobs_lock:
            job["log"].append(msg)
            del job["log"][:-50]

    try:
        path = download_mp3(job["url"], OUT_DIR, cookies, log=log)
        with jobs_lock:
            job["status"], job["file"] = "done", path.name
    except Exception as e:
        msg = str(e).replace("ERROR: ", "").split(" Check if", 1)[0].split(" Use --cookies", 1)[0]
        if "audio codec" in msg.lower():
            msg = "This video has no sound, so there is no audio to save."
        elif "login" in msg.lower() or "empty media" in msg.lower() or "cookies" in msg.lower():
            msg += " Try again with login cookies set to the browser you use for Instagram (you must be logged in there)."
        with jobs_lock:
            job["status"], job["error"] = "error", msg


def list_files():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(OUT_DIR.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": p.name, "size": p.stat().st_size, "mtime": p.stat().st_mtime} for p in files]


def safe_file(name):
    """Resolve a file name inside OUT_DIR, refusing anything that escapes it."""
    p = (OUT_DIR / name).resolve()
    if p.parent != OUT_DIR.resolve() or p.suffix.lower() != ".mp3" or not p.is_file():
        return None
    return p


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def same_origin(self):
        # Block other websites from triggering downloads through this server.
        origin = self.headers.get("Origin")
        port = self.server.server_port
        return origin is None or origin in (f"http://localhost:{port}", f"http://127.0.0.1:{port}")

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self.send_static(WEB_DIR / "index.html")
        if path == "/favicon.svg":
            return self.send_static(WEB_DIR / "favicon.svg")
        if path == "/api/files":
            return self.send_json({"folder": str(OUT_DIR), "files": list_files()})
        if path == "/api/jobs":
            with jobs_lock:
                data = sorted(({"id": k, **{x: v[x] for x in v if x != "log"}, "last": v["log"][-1] if v["log"] else ""}
                               for k, v in jobs.items()), key=lambda j: j["started"], reverse=True)
            return self.send_json({"jobs": data[:20], "browsers": BROWSERS})
        if path.startswith("/files/"):
            p = safe_file(unquote(path[len("/files/"):]))
            if not p:
                return self.send_json({"error": "not found"}, 404)
            return self.send_static(p, download="dl=1" in (urlparse(self.path).query or ""))
        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        if not self.same_origin():
            return self.send_json({"error": "forbidden"}, 403)
        path = urlparse(self.path).path
        if path == "/api/download":
            data = self.read_json()
            urls = [u.strip() for u in str(data.get("urls", "")).split() if u.strip()]
            cookies = data.get("cookies") if data.get("cookies") in BROWSERS else "none"
            bad = [u for u in urls if "instagram.com" not in u]
            if not urls or bad:
                return self.send_json({"error": "Paste Instagram links only." if bad else "Paste a link first."}, 400)
            ids = []
            for url in urls:
                job_id = uuid.uuid4().hex[:8]
                with jobs_lock:
                    jobs[job_id] = {"url": url, "status": "running", "log": [], "file": None,
                                    "error": None, "started": time.time()}
                threading.Thread(target=run_job, args=(job_id, cookies), daemon=True).start()
                ids.append(job_id)
            return self.send_json({"jobs": ids})
        if path == "/api/delete":
            p = safe_file(self.read_json().get("name", ""))
            if not p:
                return self.send_json({"error": "not found"}, 404)
            p.unlink()
            return self.send_json({"ok": True})
        if path == "/api/folder":
            data = self.read_json()
            new = pick_folder() if data.get("pick") else data.get("path")
            if data.get("pick") and not new:
                return self.send_json({"folder": str(OUT_DIR), "cancelled": True})
            err = set_out_dir(new)
            if err:
                return self.send_json({"error": err, "folder": str(OUT_DIR)}, 400)
            return self.send_json({"folder": str(OUT_DIR)})
        if path == "/api/open-folder":
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            open_path(OUT_DIR)
            return self.send_json({"ok": True})
        if path == "/api/clear-jobs":
            with jobs_lock:
                for k in [k for k, v in jobs.items() if v["status"] != "running"]:
                    del jobs[k]
            return self.send_json({"ok": True})
        self.send_json({"error": "not found"}, 404)

    def send_static(self, p, download=False):
        data = p.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(p.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        if download:
            from urllib.parse import quote
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(p.name)}")
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        raise SystemExit(f"Port {PORT} is in use - Reel to MP3 is probably already running.")
    print(f"Reel to MP3 running at http://localhost:{PORT}")
    server.serve_forever()
