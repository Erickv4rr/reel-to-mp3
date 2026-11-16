"""Reel to MP3 - extract the audio from an Instagram Reel as an MP3 file.

GUI:  run without arguments (or double-click start.bat)
CLI:  python reel_to_mp3.py <reel-url> [more urls...] [-o OUTPUT_DIR] [--cookies opera]
"""
import argparse
import os
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path

IS_MAC = sys.platform == "darwin"
IS_WIN = os.name == "nt"

# Bundled apps (PyInstaller) have no system certificates on macOS; use certifi's.
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    pass

import yt_dlp  # noqa: E402

APP_DIR = Path(__file__).resolve().parent
# Where bundled files (web/, bin/) live: the unpacked bundle when frozen, else this folder.
RES_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
DEFAULT_OUT = Path.home() / "Music" / "Reels"
if IS_MAC:
    BROWSERS = ["none", "safari", "chrome", "firefox", "opera", "brave", "edge"]
    USER_DIR = Path.home() / "Library" / "Application Support" / "Reel to MP3"
else:
    BROWSERS = ["none", "opera", "firefox", "edge", "chrome", "brave"]
    USER_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "Reel to MP3"


def find_ffmpeg():
    """Path to an ffmpeg binary: the bundled one, imageio-ffmpeg's, or None (use PATH)."""
    p = RES_DIR / "bin" / ("ffmpeg.exe" if IS_WIN else "ffmpeg")
    if p.is_file():
        if not IS_WIN and not os.access(p, os.X_OK):
            try:
                p.chmod(0o755)
            except OSError:
                pass
        return str(p.parent)  # yt-dlp wants the folder when ffprobe isn't alongside
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def open_path(path):
    """Open a folder or file with the system's default app."""
    path = str(path)
    if IS_WIN:
        os.startfile(path)
    elif IS_MAC:
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def download_mp3(url, out_dir, cookies_browser=None, bitrate="192", log=print):
    """Download one reel and convert its audio to MP3. Returns the MP3 path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    class Logger:
        def debug(self, msg):
            if not msg.startswith("[debug]"):
                log(msg)

        def info(self, msg):
            log(msg)

        def warning(self, msg):
            log("WARNING: " + msg)

        def error(self, msg):
            log("ERROR: " + msg)

    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(out_dir / "%(uploader|instagram)s - %(title).80B [%(id)s].%(ext)s"),
        "windowsfilenames": True,
        "noplaylist": True,
        "ffmpeg_location": find_ffmpeg(),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": bitrate,
        }],
        "logger": Logger(),
        "noprogress": True,
    }
    if cookies_browser and cookies_browser != "none":
        opts["cookiesfrombrowser"] = (cookies_browser,)

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if "entries" in info:  # carousel / multi-video post: take the first video
            info = next(e for e in info["entries"] if e)
        return Path(ydl.prepare_filename(info)).with_suffix(".mp3")


def run_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("Reel to MP3")
    root.geometry("640x420")
    root.minsize(480, 320)

    frm = ttk.Frame(root, padding=12)
    frm.pack(fill="both", expand=True)
    frm.columnconfigure(1, weight=1)

    ttk.Label(frm, text="Reel link(s):").grid(row=0, column=0, sticky="nw")
    urls_box = tk.Text(frm, height=4, wrap="none")
    urls_box.grid(row=0, column=1, columnspan=2, sticky="ew", pady=(0, 8))
    ttk.Label(frm, text="one link per line", foreground="gray").grid(row=1, column=1, sticky="w")

    ttk.Label(frm, text="Save to:").grid(row=2, column=0, sticky="w", pady=6)
    out_var = tk.StringVar(value=str(DEFAULT_OUT))
    ttk.Entry(frm, textvariable=out_var).grid(row=2, column=1, sticky="ew", pady=6)

    def browse():
        d = filedialog.askdirectory(initialdir=out_var.get())
        if d:
            out_var.set(d)

    ttk.Button(frm, text="Browse...", command=browse).grid(row=2, column=2, padx=(6, 0))

    ttk.Label(frm, text="Login cookies:").grid(row=3, column=0, sticky="w")
    cookies_var = tk.StringVar(value="none")
    ttk.Combobox(frm, textvariable=cookies_var, values=BROWSERS, state="readonly", width=12).grid(
        row=3, column=1, sticky="w")
    ttk.Label(frm, text="only needed if a reel says login required", foreground="gray").grid(
        row=4, column=1, sticky="w")

    btn_row = ttk.Frame(frm)
    btn_row.grid(row=5, column=0, columnspan=3, sticky="ew", pady=8)
    go_btn = ttk.Button(btn_row, text="Download MP3")
    go_btn.pack(side="left")
    open_btn = ttk.Button(btn_row, text="Open folder",
                          command=lambda: open_path(Path(out_var.get())) if Path(out_var.get()).exists() else None)
    open_btn.pack(side="left", padx=6)
    status = ttk.Label(btn_row, text="")
    status.pack(side="left", padx=6)

    log_box = tk.Text(frm, height=10, state="disabled", wrap="word", font=("Consolas", 9))
    log_box.grid(row=6, column=0, columnspan=3, sticky="nsew")
    frm.rowconfigure(6, weight=1)

    msgs = queue.Queue()

    def pump():
        while not msgs.empty():
            kind, payload = msgs.get()
            if kind == "log":
                log_box.configure(state="normal")
                log_box.insert("end", payload + "\n")
                log_box.see("end")
                log_box.configure(state="disabled")
            elif kind == "done":
                ok, failed = payload
                go_btn.configure(state="normal")
                status.configure(text=f"Done: {ok} saved, {failed} failed")
                if failed:
                    messagebox.showwarning("Reel to MP3", f"{failed} link(s) failed. See the log for details.")
        root.after(100, pump)

    def worker(urls, out_dir, cookies):
        ok = failed = 0
        for url in urls:
            msgs.put(("log", f"--- {url}"))
            try:
                path = download_mp3(url, out_dir, cookies, log=lambda m: msgs.put(("log", m)))
                msgs.put(("log", f"Saved: {path}"))
                ok += 1
            except Exception as e:  # keep going with the next link
                msgs.put(("log", f"FAILED: {e}"))
                failed += 1
        msgs.put(("done", (ok, failed)))

    def start():
        urls = [u.strip() for u in urls_box.get("1.0", "end").splitlines() if u.strip()]
        if not urls:
            messagebox.showinfo("Reel to MP3", "Paste at least one Instagram Reel link.")
            return
        go_btn.configure(state="disabled")
        status.configure(text="Working...")
        threading.Thread(target=worker, args=(urls, out_var.get(), cookies_var.get()), daemon=True).start()

    go_btn.configure(command=start)
    pump()
    urls_box.focus_set()
    root.mainloop()


def main():
    if len(sys.argv) == 1:
        run_gui()
        return
    p = argparse.ArgumentParser(description="Extract MP3 audio from Instagram Reel links.")
    p.add_argument("urls", nargs="+")
    p.add_argument("-o", "--out", default=str(DEFAULT_OUT), help=f"output folder (default: {DEFAULT_OUT})")
    p.add_argument("--cookies", choices=BROWSERS, default="none", help="use login cookies from this browser")
    p.add_argument("--bitrate", default="192", help="MP3 bitrate in kbps (default 192)")
    args = p.parse_args()
    failed = 0
    for url in args.urls:
        try:
            print("Saved:", download_mp3(url, args.out, args.cookies, args.bitrate))
        except Exception as e:
            print("FAILED:", url, "-", e, file=sys.stderr)
            failed += 1
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
