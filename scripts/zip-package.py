#!/usr/bin/env python3
"""Independently archive all staged files AND empty directories, no installer."""
from pathlib import Path
import sys
import zipfile


def make_zip(root: Path, archive: Path):
    if not root.is_dir():
        raise FileNotFoundError(root)
    archive.parent.mkdir(parents=True, exist_ok=True)
    # Include root directory explicitly for clean extraction into PortableApps.
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        base = root.parent
        for item in [root] + sorted(root.rglob("*")):
            arc = item.relative_to(base).as_posix()
            if item.is_symlink():
                raise ValueError(f"Unexpected symlink in package: {item}")
            if item.is_dir():
                z.writestr(arc.rstrip("/") + "/", "")
            else:
                z.write(item, arc)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None, "Archive CRC check failed"


if __name__ == "__main__":
    make_zip(Path(sys.argv[1]), Path(sys.argv[2]))
