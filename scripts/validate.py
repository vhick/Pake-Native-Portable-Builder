#!/usr/bin/env python3
"""Static/package validations; never claim interactive Windows verification."""
import configparser
import hashlib
import json
from pathlib import Path
import struct
import zipfile


def is_x64_pe(data: bytes) -> bool:
    if len(data) < 512 or data[:2] != b"MZ":
        return False
    offset = struct.unpack_from("<I", data, 0x3C)[0]
    return offset + 6 < len(data) and data[offset:offset + 4] == b"PE\x00\x00" and struct.unpack_from("<H", data, offset + 4)[0] == 0x8664


def check(plan: dict, base: Path = Path("work/stage"), releases: Path = Path("release")):
    root = base / plan["folder"]
    file = root / plan["exe"]
    exe = file.read_bytes()
    if not is_x64_pe(exe):
        raise RuntimeError("Generated launcher is not a genuine x64 Windows PE executable")
    if len(exe) < 250_000:
        raise RuntimeError("Compiled Tauri application is implausibly small (expected Rust/WebView app)")
    appinfo = root / "App/AppInfo"
    ini = configparser.ConfigParser(interpolation=None)
    ini.read(appinfo / "appinfo.ini", encoding="utf-8-sig")
    if ini.get("Control", "Start") != plan["exe"] or ini.get("Format", "Type") != "PortableApps.comFormat":
        raise RuntimeError("PortableApps Menu entry does not start actual application")
    for icon in ("appicon.ico", "appicon_16.png", "appicon_32.png"):
        if (appinfo / icon).stat().st_size < 64:
            raise RuntimeError(f"Invalid/empty icon {icon}")
    path = releases / plan["zipName"]
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("ZIP CRC mismatch")
        files = set(archive.namelist())
        dirname = plan["folder"] + "/"
        required = [dirname + plan["exe"], dirname + "App/AppInfo/appinfo.ini",
                    dirname + "Data/WebView/", dirname + "Data/State/", dirname + "Data/TraceGuard/",
                    dirname + "Other/Source/portable-source-patch.py"]
        if not all(name in files for name in required):
            raise RuntimeError("ZIP missing required files or empty portable Data folders")
        if any(name.lower().endswith((".msi", ".paf.exe", "-setup.exe")) for name in files):
            raise RuntimeError("Installer accidentally included in portable ZIP")
        if hashlib.sha256(archive.read(dirname + plan["exe"])).digest() != hashlib.sha256(exe).digest():
            raise RuntimeError("ZIP executable does not match independently compiled Pake application")
    print("PASS: genuine x64 application PE, icon extraction, appinfo, independent ZIP, empty Data dirs, no installer")
    print("SHA256 ZIP:", hashlib.sha256(path.read_bytes()).hexdigest())
    print("NOT TESTED: interactive WebView2 website session, actual host leftovers or upgrade/rollback on end-user PC")


if __name__ == "__main__":
    check(json.loads(Path("work/plan.json").read_text(encoding="utf-8")))
