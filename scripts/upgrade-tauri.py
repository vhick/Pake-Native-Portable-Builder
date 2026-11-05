#!/usr/bin/env python3
"""Prepare ephemeral Pake source to support documented Tauri 2.12 portable API.

Pake V3.18.0 pins tauri 2.10.x, webview2-com 0.38.x, and windows-core
0.61.x. Portable appDirectoriesOverride needs Tauri 2.12.0; its WebView2
interfaces must also use windows-core 0.62 and webview2-com 0.39. These checks fail closed if the upstream
Cargo manifest/lock layout changes. Do not modify the user's upstream repo.
"""
from pathlib import Path
import re
import sys
import tomllib
import json
import subprocess

TAURI_MINIMUM = (2, 12, 0)
TAURI_TARGET = '2.12.0'
WINDOWS_CORE_TARGET = '0.62.2'
WEBVIEW2_TARGET = '0.39.1'
UPSTREAM_WINDOWS_CORE = '0.61.2'
UPSTREAM_WEBVIEW2 = '0.38'
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


def direct_windows_versions(root: Path) -> dict[str, str]:
    """Read the Pake crate's own direct Windows dependencies, not transitive crates."""
    with (root / 'src-tauri/Cargo.toml').open('rb') as stream:
        manifest = tomllib.load(stream)
    windows = manifest['target']["cfg(windows)"]['dependencies']
    return {name: windows[name] for name in ('windows-core', 'webview2-com')}


def verify(root: Path):
    actual = lock_tauri_version(root)
    if actual != TAURI_TARGET:
        raise RuntimeError(f'Expected tauri {TAURI_TARGET} after upgrade; got {actual}')
    windows = direct_windows_versions(root)
    expected = {'windows-core': '=' + WINDOWS_CORE_TARGET,
                'webview2-com': '=' + WEBVIEW2_TARGET}
    if windows != expected:
        raise RuntimeError(f'Rust WebView2/COM manifest mismatch: {windows!r}; expected {expected!r}')
    print(f'PASS: Rust Tauri {actual}; direct WebView2 COM versions declared: {windows}')


def verify_resolved_windows(root: Path):
    """Verify the dependency graph actually selected Pake's direct COM package versions.

    An older windows-core may legitimately appear elsewhere transitively; that does
    not mean Pake's own `use windows_core::...` is mismatched. Check direct edges.
    """
    cmd = ['cargo', 'metadata', '--format-version', '1', '--locked',
           '--manifest-path', str(root / 'src-tauri/Cargo.toml')]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    metadata = json.loads(result.stdout)
    packages = {pkg['id']: pkg for pkg in metadata['packages']}
    target_manifest = (root / 'src-tauri/Cargo.toml').resolve()
    matches = [pkg for pkg in metadata['packages']
               if pkg.get('manifest_path') and Path(pkg['manifest_path']).resolve() == target_manifest and pkg['name'] == 'pake']
    if len(matches) != 1:
        raise RuntimeError('Cannot locate the exact Pake crate in Cargo metadata')
    pake_id = matches[0]['id']
    nodes = [node for node in metadata['resolve']['nodes'] if node['id'] == pake_id]
    if len(nodes) != 1:
        raise RuntimeError('Cannot locate Pake direct dependency edges in Cargo metadata')
    deps = {dep['name']: packages[dep['pkg']]['version'] for dep in nodes[0]['deps']}
    for dep_name, expected in (('windows_core', WINDOWS_CORE_TARGET),
                               ('webview2_com', WEBVIEW2_TARGET)):
        actual = deps.get(dep_name)
        if actual != expected:
            raise RuntimeError(f'Actual Pake direct dependency {dep_name}: {actual!r}; expected {expected}')
    print(f'PASS: Cargo selected Pake direct windows-core {WINDOWS_CORE_TARGET} '
          f'and webview2-com {WEBVIEW2_TARGET}; WebView2 interface versions aligned')


def prepare(root: Path):
    """Fail closed on unseen upstream layout, and atomically update one manifest."""
    cargo = root / 'src-tauri/Cargo.toml'
    content = cargo.read_text(encoding='utf-8')
    changes = (
        (r'(tauri\s*=\s*\{\s*version\s*=\s*")2\.10\.2("\s*,)',
         r'\g<1>2.12.0\g<2>', 'Tauri'),
        (r'(?m)^(webview2-com\s*=\s*")0\.38("\s*(?:#.*)?)$',
         r'\g<1>=0.39.1\g<2>', 'WebView2 bindings'),
        (r'(?m)^(windows-core\s*=\s*")0\.61\.2("\s*(?:#.*)?)$',
         r'\g<1>=0.62.2\g<2>', 'Windows COM interfaces'),
    )
    updated = content
    for pattern, replacement, component in changes:
        updated, count = re.subn(pattern, replacement, updated)
        if count != 1:
            raise RuntimeError(f'Pake {component} version or Cargo layout changed; refusing partial upgrade')
    cargo.write_text(updated, encoding='utf-8', newline='\n')
    versions = direct_windows_versions(root)
    if versions != {'windows-core': '=0.62.2', 'webview2-com': '=0.39.1'}:
        raise RuntimeError('Windows COM direct version check failed after rewriting Cargo.toml')
    print('Updated ephemeral Cargo.toml: Tauri 2.12.0, webview2-com =0.39.1, windows-core =0.62.2')
    print('Pinned Windows COM crates match the Tauri 2.12 / Wry 0.57 API family.')


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
    elif '--verify-resolved-windows' in sys.argv[2:]:
        verify_resolved_windows(base)
    else:
        prepare(base)

