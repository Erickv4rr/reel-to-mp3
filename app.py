"""Reel to MP3 desktop app.

Runs the local Reel to MP3 server and shows it in the app's own window
(Edge WebView2 on Windows, WebKit on macOS). If that window can't be created,
it falls back to opening the page in the default browser.
This is the file that gets packaged into the Windows and Mac apps.
"""
import os
import subprocess
import sys
import threading
import webbrowser

import server
from reel_to_mp3 import IS_MAC, IS_WIN, RES_DIR, USER_DIR, open_path
from version import APP_NAME

PORTS = list(range(8765, 8776)) + [0]  # 0 = any free port


def dark_mode():
    try:
        if IS_WIN:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
        if IS_MAC:
            out = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                                 capture_output=True, text=True, timeout=2).stdout
            return "dark" in out.lower()
    except Exception:
        pass
    return False


def run_in_window(url):
    """Show the app in its own native window. Returns False if that isn't possible."""
    try:
        import webview
    except Exception:
        return False

    if IS_WIN:
        try:  # own taskbar entry and icon instead of python's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ReelToMP3.App")
        except Exception:
            pass

    window = webview.create_window(
        APP_NAME, url, width=1060, height=800, min_size=(720, 560),
        background_color="#0F0F13" if dark_mode() else "#F4F4F7", text_select=True)

    folder_dialog = getattr(getattr(webview, "FileDialog", None), "FOLDER", None)
    if folder_dialog is None:
        folder_dialog = webview.FOLDER_DIALOG

    def pick(initial):
        result = window.create_file_dialog(folder_dialog, directory=initial)
        return (result or [""])[0]

    server.folder_picker = pick
    try:
        USER_DIR.mkdir(parents=True, exist_ok=True)
        webview.start(private_mode=False, storage_path=str(USER_DIR / "webview"))
    except Exception:
        return False
    return True


def run_in_browser(url):
    """Fallback: open the page in the browser and keep a small control window open."""
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title(APP_NAME)
    root.resizable(False, False)
    icon_file = RES_DIR / "assets" / "icon.png"
    if icon_file.is_file():
        try:
            root.iconphoto(True, tk.PhotoImage(file=str(icon_file)))
        except tk.TclError:
            pass
    frm = ttk.Frame(root, padding=18)
    frm.pack(fill="both", expand=True)
    ttk.Label(frm, text=f"{APP_NAME} is running", font=("TkDefaultFont", 13, "bold")).pack(anchor="w")
    ttk.Label(frm, text="It opened in your web browser.\nKeep this window open while you use it.",
              justify="left").pack(anchor="w")
    btns = ttk.Frame(frm)
    btns.pack(fill="x", pady=(14, 0))
    ttk.Button(btns, text=f"Open {APP_NAME}", command=lambda: webbrowser.open(url)).pack(side="left")
    ttk.Button(btns, text="Open MP3 folder", command=lambda: open_path(server.OUT_DIR)).pack(side="left", padx=8)
    root.after(300, lambda: webbrowser.open(url))
    root.mainloop()


def main():
    ports = [int(os.environ["REEL_PORT"])] if os.environ.get("REEL_PORT") else PORTS
    httpd = server.make_server(ports)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    threading.Thread(target=server.check_for_update, daemon=True).start()
    url = f"http://localhost:{httpd.server_port}/"

    if os.environ.get("REEL_BROWSER") or not run_in_window(url):
        run_in_browser(url)
    httpd.shutdown()
    sys.exit(0)


if __name__ == "__main__":
    main()
