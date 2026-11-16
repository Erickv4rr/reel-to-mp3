<p align="center"><img src="assets/icon.png" width="96" alt=""></p>

<h1 align="center">Reel to MP3</h1>

<p align="center">Paste an Instagram Reel link and get its audio as an MP3, with the title, artist and cover art already filled in.<br>A desktop app for Windows and Mac. Everything runs on your own computer.</p>

<p align="center"><a href="../../releases/latest"><b>Download the latest version</b></a></p>

## Features

- **Paste and go:** paste a link, click Convert, done. Press Ctrl+V (⌘V on Mac) anywhere in the window to convert straight away, or paste several links at once.
- **Proper MP3s:** each file gets the Reel's caption as its title, the creator as the artist, and the Reel's thumbnail as cover art.
- **Built-in library and player:** browse, search, play, show in folder, or move to the Recycle Bin / Trash.
- **Your choice of quality:** 128, 192 or 320 kbps, saved to any folder you pick.
- **Update notices:** the app tells you when a new version is out.
- **Light and dark mode:** follows your system.

## Install

**Windows:** download **Reel-to-MP3-Setup.exe** from the [Releases page](../../releases/latest) and run it. It adds Reel to MP3 to the Start menu. If Windows shows "Windows protected your PC", click **More info → Run anyway**. Prefer not to install? Use **Reel-to-MP3-Windows-Portable.exe** instead.

**Mac:** download the `.dmg` that matches your Mac (Apple menu → About This Mac: *Chip: Apple M…* → **AppleSilicon**, *Processor: Intel* → **Intel**). Open it and drag **Reel to MP3** into **Applications**. The first time you open it, macOS says it can't verify the app. Click **Done**, open **System Settings → Privacy & Security**, scroll down and click **Open Anyway**. You only need to do this once.

## Tips

- MP3s are saved in `Music/Reels` by default. Change it in **Settings** (the sliders icon, top right).
- If a Reel says you need to log in, open **Settings → Instagram login** and pick the browser where you're logged into Instagram. On a Mac, Safari needs Full Disk Access for this, so Chrome or Firefox is easier.
- If Instagram changes something and downloads stop working, a new release usually fixes it.

## Building

GitHub Actions builds the apps (`.github/workflows/build.yml`). Bump `version.py`, then push a matching tag (for example `v1.2.0`) to build and publish a release. Each build also picks up the newest yt-dlp.

Windows, locally:

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt pyinstaller pillow
.venv\Scripts\python build.py
```

The app is `app.py` (window), `server.py` (local server, only reachable from this computer) and `web/` (the interface). Downloads use [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [FFmpeg](https://ffmpeg.org).
