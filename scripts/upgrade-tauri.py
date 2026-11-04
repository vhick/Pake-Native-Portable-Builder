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
import json

TAURI_MINIMUM = (2, 12, 0)
TAURI_TARGET = '2.12.0'
# Pin a published compatible 2.12.x JavaScript pair rather than keeping Pake 3.18.0's 2.10.x.
# Tauri's CLI rejects mismatched major/minor API and Rust versions.
JS_API_TARGET = '2.12.3'
JS_CLI_TARGET = '2.12.2'
ORIGINAL_JS_API = '~2.10.1'
ORIGINAL_JS_CLI = '^2.10.0'


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


def prepare_javascript(root: Path):
    """Update only the ephemeral checkout's package.json dependency declarations.

    pnpm install --no-frozen-lockfile is then responsible for regenerating its
    lockfile and downloading these specific packages. Do not patch lockfiles by hand.
    """
    package_path = root / 'package.json'
    package = json.loads(package_path.read_text(encoding='utf-8'))
    if package.get('name') != 'pake-cli':
        raise RuntimeError('Unexpected upstream Node package')
    deps = package.get('dependencies', {})
    for name, old in (('@tauri-apps/api', ORIGINAL_JS_API),
                      ('@tauri-apps/cli', ORIGINAL_JS_CLI)):
        if deps.get(name) != old:
            raise RuntimeError(f'Unexpected upstream {name} version {deps.get(name)!r}; refusing blind rewrite')
    deps['@tauri-apps/api'] = JS_API_TARGET
    deps['@tauri-apps/cli'] = JS_CLI_TARGET
    package_path.write_text(json.dumps(package, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Updated ephemeral package.json: @tauri-apps/api {JS_API_TARGET}, @tauri-apps/cli {JS_CLI_TARGET}')


def verify_javascript(root: Path):
    """Verify both requested and actually installed packages before CLI builds."""
    package = json.loads((root / 'package.json').read_text(encoding='utf-8'))
    deps = package.get('dependencies', {})
    for name, expected in (('@tauri-apps/api', JS_API_TARGET),
                           ('@tauri-apps/cli', JS_CLI_TARGET)):
        if deps.get(name) != expected:
            raise RuntimeError(f'Expected {name} declaration {expected}, got {deps.get(name)}')
        actual_path = root / 'node_modules' / '@tauri-apps' / name.split('/')[-1] / 'package.json'
        if not actual_path.is_file():
            raise RuntimeError(f'Missing installed Tauri package {actual_path}')
        actual = json.loads(actual_path.read_text(encoding='utf-8')).get('version')
        if actual != expected:
            raise RuntimeError(f'Installed {name} is {actual}, expected {expected}')
    print(f'PASS: installed JS Tauri API {JS_API_TARGET} and CLI {JS_CLI_TARGET} match Rust Tauri 2.12.x')


if __name__ == '__main__':
    base = Path(sys.argv[1])
    if '--prepare-js' in sys.argv[2:]:
        prepare_javascript(base)
    elif '--verify-js' in sys.argv[2:]:
        verify_javascript(base)
    elif '--verify' in sys.argv[2:]:
        verify(base)
    else:
        prepare(base)

