# Reel to MP3

Paste an Instagram Reel link and get its audio as an MP3. Runs on your own computer: the app opens a page in your web browser where you paste links, play the results and pick the folder they're saved in.

## Download

Get the latest version from the **[Releases page](../../releases/latest)**.

**Windows:** download `Reel-to-MP3-Windows.exe` and double-click it. If Windows shows "Windows protected your PC", click **More info → Run anyway**.

**Mac:** download the `.dmg` that matches your Mac (Apple menu → About This Mac: *Chip: Apple M…* → **AppleSilicon**, *Processor: Intel* → **Intel**). Open it and drag **Reel to MP3** into **Applications**. The first time you open it, macOS says it can't verify the app. Click **Done**, open **System Settings → Privacy & Security**, scroll down and click **Open Anyway**. You only need to do this once.

## Using it

1. Open Reel to MP3. A small window appears and the app opens in your browser. Keep the small window open while you use it. Closing it quits the app.
2. Paste one or more Reel links (one per line) and click **Download MP3**.
3. MP3s are saved in `Music/Reels` by default. Change the folder under **Your MP3s**.

If a reel fails with "login required", set **Login cookies** to the browser where you're logged into Instagram, then try again. On a Mac, Safari needs Full Disk Access for this (System Settings → Privacy & Security → Full Disk Access), so Chrome or Firefox is easier.

## Building

The apps are built by GitHub Actions (`.github/workflows/build.yml`). Push a tag such as `v1.0.1` to build and publish a new release. Rebuilding also picks up the newest yt-dlp, which fixes most "it stopped working" problems with Instagram.

To build the Windows app locally:

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt pyinstaller pillow
.venv\Scripts\python build.py
```
