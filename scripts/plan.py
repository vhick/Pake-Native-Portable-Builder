#!/usr/bin/env python3
"""Validate manual inputs and give each unique app configuration its own release tag.
No arguments are interpolated into workflow shell commands.
"""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

BUILDER_REVISION = "r7"


def safe_public_url(value: str, field: str) -> str:
    value = value.strip()
    if not value or len(value) > 1800 or "\n" in value or "\r" in value:
        raise ValueError(f"{field} must be a nonempty URL under 1800 characters")
    parsed = urlsplit(value)
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        raise ValueError(f"{field} requires a full http(s) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{field} must not contain embedded credentials")
    host = parsed.hostname.rstrip(".").lower()
    if host in ("localhost",) or host.endswith((".localhost", ".local", ".internal", ".test")):
        raise ValueError(f"{field} must be reachable from GitHub's public runner")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if "." not in host:
            raise ValueError(f"{field} must contain a public DNS hostname")
    else:
        if not ip.is_global:
            raise ValueError(f"{field} must not point at a private or loopback IP")
    return value


def make_plan(inputs: dict) -> dict:
    url = safe_public_url(inputs["website_url"], "website_url")
    name = inputs["app_name"].strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]{1,39}", name) or name.endswith(" "):
        raise ValueError("App name must be 2-40 characters, start with a letter, and use English letters, digits, spaces, _ or -")
    slug = re.sub(r"[^A-Za-z0-9]", "", name)
    if len(slug) > 36:
        raise ValueError("App name is too long after spaces are removed")
    version = inputs["app_version"].strip()
    if not re.fullmatch(r"[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}", version):
        raise ValueError("Application version must be numeric, e.g. 1.0.0")
    upstream = inputs["pake_version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", upstream):
        raise ValueError("Upstream version must be stable x.y.z")
    icon = inputs.get("icon_url", "").strip()
    if icon:
        icon = safe_public_url(icon, "icon_url")
    width = int(inputs.get("width", "1200"))
    height = int(inputs.get("height", "780"))
    if not 320 <= width <= 3840 or not 240 <= height <= 2160:
        raise ValueError("Window dimensions must be between 320x240 and 3840x2160")
    flags = {key: str(inputs.get(key, "false")).lower() == "true" for key in
             ("new_window", "fullscreen", "hide_window_decorations", "no_restore_last_url")}
    if any(str(inputs.get(key, "false")).lower() not in ("true", "false") for key in flags):
        raise ValueError("Boolean inputs must be true or false")
    config = {"url": url, "name": name, "icon": icon, "version": version,
              "pakeVersion": upstream, "width": width, "height": height,
              "options": flags, "builderRevision": BUILDER_REVISION}
    fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]
    folder = f"{slug}Portable"
    config.update({"slug": slug, "folder": folder,
                   "exe": f"{slug}Portable.exe",
                   "fingerprint": fingerprint,
                   "releaseTag": f"portable-{slug.lower()}-v{version}-pake{upstream}-{BUILDER_REVISION}-{fingerprint}",
                   "zipName": f"{slug}Portable_{version}_Pake{upstream}_{BUILDER_REVISION}_win-x64.zip"})
    return config


def main():
    inp = {k: os.environ.get("INPUT_" + k.upper(), "") for k in
           ("website_url", "app_name", "icon_url", "width", "height", "app_version",
            "new_window", "fullscreen", "hide_window_decorations", "no_restore_last_url")}
    inp["pake_version"] = os.environ["PAKE_VERSION"]
    plan = make_plan(inp)
    Path("work").mkdir(exist_ok=True)
    Path("work/plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        raise RuntimeError("This program must run in GitHub Actions")
    with open(output, "a", encoding="utf-8") as f:
        for label, value in (("release_tag", plan["releaseTag"]),
                             ("zip_name", plan["zipName"]),
                             ("app_folder", plan["folder"])):
            f.write(f"{label}={value}\n")
    print(f"Portable build: {plan['folder']} / Pake {plan['pakeVersion']} / app {plan['version']}")
    print(f"Release identity: {plan['releaseTag']}")
    print("Website and icon inputs are intentionally not printed (avoid exposing URL tokens).")


if __name__ == "__main__":
    main()
