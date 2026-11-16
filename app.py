"""Reel to MP3 desktop app.

Starts the local Reel to MP3 server, opens it in your default browser, and shows a
small window that keeps it running. Closing the window quits the app.
This is the file that gets packaged into the Windows .exe and the Mac .app.
"""
import json
import os
import queue
import threading
import urllib.request
import webbrowser
from http.server import ThreadingHTTPServer

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import server
from reel_to_mp3 import RES_DIR, open_path

PORTS = list(range(8765, 8776)) + [0]  # 0 = any free port


def already_running(port):
    """True if another Reel to MP3 is already serving on this port."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/jobs", timeout=1) as r:
            return "browsers" in json.load(r)
    except Exception:
        return False


def start_server():
    ports = [int(os.environ["REEL_PORT"])] if os.environ.get("REEL_PORT") else PORTS
    for port in ports:
        try:
            return ThreadingHTTPServer((server.HOST, port), server.Handler)
        except OSError:
            continue
    raise SystemExit("Reel to MP3 could not find a free network port.")


def main():
    if not os.environ.get("REEL_PORT") and already_running(PORTS[0]):
        webbrowser.open(f"http://localhost:{PORTS[0]}")
        return

    httpd = start_server()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://localhost:{httpd.server_port}"

    root = tk.Tk()
    root.title("Reel to MP3")
    root.resizable(False, False)
    icon_file = RES_DIR / "assets" / "icon.png"
    if icon_file.is_file():
        try:
            icon = tk.PhotoImage(file=str(icon_file))
            root.iconphoto(True, icon)
            small = icon.subsample(max(1, icon.width() // 64))
        except tk.TclError:
            small = None
    else:
        small = None

    frm = ttk.Frame(root, padding=18)
    frm.pack(fill="both", expand=True)
    top = ttk.Frame(frm)
    top.pack(fill="x")
    if small:
        ttk.Label(top, image=small).pack(side="left", padx=(0, 12))
    text = ttk.Frame(top)
    text.pack(side="left", fill="x")
    ttk.Label(text, text="Reel to MP3 is running", font=("TkDefaultFont", 13, "bold")).pack(anchor="w")
    ttk.Label(text, text="It opens in your web browser.\nKeep this window open while you use it.",
              justify="left").pack(anchor="w")

    btns = ttk.Frame(frm)
    btns.pack(fill="x", pady=(16, 0))
    ttk.Button(btns, text="Open Reel to MP3", command=lambda: webbrowser.open(url)).pack(side="left")
    ttk.Button(btns, text="Open MP3 folder",
               command=lambda: (server.OUT_DIR.mkdir(parents=True, exist_ok=True), open_path(server.OUT_DIR))
               ).pack(side="left", padx=8)
    ttk.Label(frm, text=url, foreground="gray").pack(anchor="w", pady=(10, 0))

    # Folder picker requests from the web page are answered here, on the Tk main thread
    # (required on macOS, and keeps the dialog on top of this window everywhere).
    picks = queue.Queue()

    def threaded_picker(initial):
        done, result = threading.Event(), {}
        picks.put((initial, result, done))
        done.wait()
        return result.get("path", "")

    def pump():
        while not picks.empty():
            initial, result, done = picks.get()
            try:
                root.deiconify()
                root.lift()
                root.attributes("-topmost", True)
                result["path"] = filedialog.askdirectory(parent=root, initialdir=initial,
                                                         title="Choose where Reel to MP3 saves files")
            finally:
                root.attributes("-topmost", False)
                done.set()
        root.after(150, pump)

    server.folder_picker = threaded_picker

    def quit_app():
        with server.jobs_lock:
            busy = any(j["status"] == "running" for j in server.jobs.values())
        if busy and not messagebox.askyesno("Reel to MP3", "A download is still running. Quit anyway?"):
            return
        httpd.shutdown()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", quit_app)
    root.createcommand("::tk::mac::Quit", quit_app)  # Cmd+Q on macOS (ignored elsewhere)
    root.after(150, pump)
    root.after(400, lambda: webbrowser.open(url))
    root.mainloop()


if __name__ == "__main__":
    main()
