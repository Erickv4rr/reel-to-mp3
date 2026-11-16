"""Package Reel to MP3 as a desktop app for the system this runs on.

    pip install -r requirements.txt pyinstaller pillow
    python build.py

Windows -> dist/Reel to MP3.exe     macOS -> dist/Reel to MP3.app
(PyInstaller can only build for the system it runs on; GitHub Actions builds the Mac one.)
"""
import os
import shutil
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent
IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
SEP = ";" if IS_WIN else ":"


def ensure_ffmpeg():
    """Put an ffmpeg binary for this system in bin/ (copied from imageio-ffmpeg if missing)."""
    dest = ROOT / "bin" / ("ffmpeg.exe" if IS_WIN else "ffmpeg")
    if not dest.is_file():
        import imageio_ffmpeg
        dest.parent.mkdir(exist_ok=True)
        shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(), dest)
    if not IS_WIN:
        dest.chmod(0o755)
    return dest


def main():
    ffmpeg = ensure_ffmpeg()
    if not (ROOT / "assets" / "icon.png").is_file():
        import runpy
        runpy.run_path(str(ROOT / "tools" / "make_icon.py"), run_name="__main__")

    args = [
        str(ROOT / "app.py"),
        "--name", "Reel to MP3",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--icon", str(ROOT / "assets" / "icon.png"),
        "--add-data", f"{ROOT / 'web'}{SEP}web",
        "--add-data", f"{ROOT / 'assets'}{SEP}assets",
        "--add-binary", f"{ffmpeg}{SEP}bin",
        "--collect-data", "certifi",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
    ]
    if IS_WIN:
        args.append("--onefile")
    if IS_MAC:
        args += ["--osx-bundle-identifier", "io.github.reeltomp3"]
    PyInstaller.__main__.run(args)


if __name__ == "__main__":
    main()
