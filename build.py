"""Package Reel to MP3 as a desktop app for the system this runs on.

    pip install -r requirements.txt pyinstaller pillow
    python build.py              Windows: dist/Reel to MP3/ (folder app, used by the installer)
                                 macOS:   dist/Reel to MP3.app
    python build.py --onefile    Windows: dist/Reel to MP3.exe (single portable file)

Then on Windows, installer.iss (Inno Setup) turns the folder app into Reel-to-MP3-Setup.exe.
PyInstaller only builds for the system it runs on; GitHub Actions builds the Mac app.
"""
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
SEP = ";" if IS_WIN else ":"

sys.path.insert(0, str(ROOT))
from version import APP_NAME, REPO, __version__  # noqa: E402


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


def make_icons():
    png = ROOT / "assets" / "icon.png"
    if not png.is_file():
        import runpy
        runpy.run_path(str(ROOT / "tools" / "make_icon.py"), run_name="__main__")
    BUILD.mkdir(exist_ok=True)
    if IS_WIN:
        from PIL import Image
        ico = BUILD / "icon.ico"
        Image.open(png).save(ico, sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
        return ico
    return png


def windows_version_file():
    nums = (__version__.split(".") + ["0", "0", "0"])[:4]
    v = ", ".join(nums)
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({v}), prodvers=({v}), mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Reel to MP3'),
      StringStruct('FileDescription', '{APP_NAME}'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', '{APP_NAME}'),
      StringStruct('OriginalFilename', '{APP_NAME}.exe'),
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('ProductVersion', '{__version__}'),
      StringStruct('Comments', 'https://github.com/{REPO}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
"""
    path = BUILD / "version_info.txt"
    path.write_text(text, encoding="utf-8")
    return path


def finish_mac_app():
    """Set version info in Info.plist, then re-sign (ad-hoc) since editing breaks the signature."""
    app = ROOT / "dist" / f"{APP_NAME}.app"
    plist_path = app / "Contents" / "Info.plist"
    with open(plist_path, "rb") as f:
        plist = plistlib.load(f)
    plist.update({
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "CFBundleDisplayName": APP_NAME,
        "LSApplicationCategoryType": "public.app-category.music",
        "LSMinimumSystemVersion": "11.0",
        "NSHumanReadableCopyright": f"github.com/{REPO}",
        "NSHighResolutionCapable": True,
    })
    with open(plist_path, "wb") as f:
        plistlib.dump(plist, f)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)


def main():
    onefile = "--onefile" in sys.argv
    ffmpeg = ensure_ffmpeg()
    icon = make_icons()

    args = [
        str(ROOT / "app.py"),
        "--name", APP_NAME,
        "--windowed",
        "--noconfirm",
        "--clean",
        "--icon", str(icon),
        "--add-data", f"{ROOT / 'web'}{SEP}web",
        "--add-data", f"{ROOT / 'assets'}{SEP}assets",
        "--add-binary", f"{ffmpeg}{SEP}bin",
        "--collect-data", "certifi",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(BUILD / ("onefile" if onefile else "app")),
        "--specpath", str(BUILD),
    ]
    if IS_WIN:
        args += ["--version-file", str(windows_version_file())]
        if onefile:
            args.append("--onefile")
    if IS_MAC:
        args += ["--osx-bundle-identifier", "io.github.erickv4rr.reeltomp3"]
    PyInstaller.__main__.run(args)
    if IS_MAC:
        finish_mac_app()


if __name__ == "__main__":
    main()
