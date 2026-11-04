#!/usr/bin/env python3
"""Prepare ephemeral Pake source to support documented Tauri 2.12 portable API.

Pake V3.18.0 pins tauri 2.10.x in Cargo.lock; appDirectoriesOverride
first shipped in 2.12.0. These checks fail closed if the upstream
Cargo manifest/lock layout changes. Do not modify the user's upstream repo.
"""
from pathlib import Path
import re
import sys
import tomllib

TAURI_MINIMUM = (2, 12, 0)
TAURI_TARGET = '2.12.0'


def lock_tauri_version(root: Path) -> str:
    with (root / 'src-tauri/Cargo.lock').open('rb') as stream:
        lock = tomllib.load(stream)
    versions = [item['version'] for item in lock['package'] if item['name'] == 'tauri']
    if len(versions) != 1:
        raise RuntimeError('Unexpected Cargo.lock tauri package count')
    return versions[0]


def verify(root: Path):
    actual = lock_tauri_version(root)
    if actual != TAURI_TARGET:
        raise RuntimeError(f'Expected tauri {TAURI_TARGET} after upgrade; got {actual}')
    print(f'PASS: Tauri {actual} provides appDirectoriesOverride / isolated app profile paths')


def prepare(root: Path):
    cargo = root / 'src-tauri/Cargo.toml'
    content = cargo.read_text(encoding='utf-8')
    pattern = r'(tauri\s*=\s*\{\s*version\s*=\s*")2\.10\.2(\"\s*,)'
    changed, occurrences = re.subn(pattern, r'\g<1>2.12.0\g<2>', content)
    if occurrences != 1:
        raise RuntimeError('Upstream tauri dependency version/layout changed; refusing blind upgrade')
    cargo.write_text(changed, encoding='utf-8')
    print('Source-only Cargo.toml requirement updated: tauri >=2.12.0 (no upstream fork).')


if __name__ == '__main__':
    base = Path(sys.argv[1])
    verify(base) if '--verify' in sys.argv[2:] else prepare(base)
