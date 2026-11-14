#!/usr/bin/env python3
"""Auto-align disposable Pake Tauri dependencies without hardcoded upstream versions.

This tool edits ONLY the fetched source checkout. It needs no credentials or
separate developer repository. The resolved dependency graph, not release dates
or regexes for yesterday's Pake version, determines Windows COM compatibility.
It deliberately refuses Tauri 3, a changed manifest layout, missing graph
edges, prerelease packages, and source changes outside its proven patch area.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib

MIN_PORTABLE = (2, 12, 0)
SEMVER = re.compile(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$')


def version(value):
    match = SEMVER.fullmatch(str(value))
    if not match:
        raise RuntimeError(f'Expected stable exact numeric version, got {value!r}')
    return tuple(map(int, match.groups()))


def read_lock(root):
    with (root / 'src-tauri/Cargo.lock').open('rb') as f:
        return tomllib.load(f)


def lock_tauri_version(root):
    candidates = [p['version'] for p in read_lock(root)['package'] if p['name'] == 'tauri']
    if len(candidates) != 1:
        raise RuntimeError('Expected exactly one resolved Rust tauri crate in Cargo.lock')
    return candidates[0]


def load_manifest(root):
    with (root / 'src-tauri/Cargo.toml').open('rb') as f:
        data = tomllib.load(f)
    if data.get('package', {}).get('name') != 'pake':
        raise RuntimeError('Cargo.toml is not the Pake crate')
    if not isinstance(data.get('dependencies', {}).get('tauri'), dict):
        raise RuntimeError('Unexpected Pake Rust tauri declaration; manual review needed')
    windows = data.get('target', {}).get('cfg(windows)', {}).get('dependencies', {})
    if not all(isinstance(windows.get(k), str) for k in ('webview2-com', 'windows-core')):
        raise RuntimeError('Missing/changed Pake direct Windows COM dependencies; review required')
    return data


def rewrite_exact(text, name, new, *, table=False):
    """Replace one unambiguous TOML dependency version; reject other shapes."""
    pat = (rf'(?m)^(?P<start>\s*{re.escape(name)}\s*=\s*)'
           + (r'\{\s*version\s*=\s*' if table else r'')
           + r'(?P<quote>")(?P<version>[^"]+)(?P<end>"' + (r'\s*,' if table else r'') + r')')
    matches = list(re.finditer(pat, text))
    if len(matches) != 1:
        raise RuntimeError(f'Cannot safely find exactly one {name} dependency entry')
    match = matches[0]
    # Preserve the surrounding table, feature list, comments and unrelated dependencies.
    return text[:match.start('version')] + new + text[match.end('version'):]


def cmd_checked(args, cwd=None):
    result = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        details = (result.stderr or b'').decode('utf-8', errors='replace')
        raise RuntimeError(f'Command failed ({result.returncode}): {args[:3]}: {details[-2600:]}')
    return result.stdout


def metadata(root, *, locked=False):
    args = ['cargo', 'metadata', '--format-version', '1', '--manifest-path',
            str(root / 'src-tauri/Cargo.toml'), '--filter-platform', 'x86_64-pc-windows-msvc']
    if locked:
        args.append('--locked')
    try:
        # Cargo metadata writes UTF-8 regardless of the Windows runner locale.
        return json.loads(cmd_checked(args).decode('utf-8-sig'))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise RuntimeError('cargo metadata did not return valid UTF-8 JSON') from e


def graph(meta):
    packages = {p['id']: p for p in meta['packages']}
    nodes = {n['id']: n for n in meta['resolve']['nodes']}
    if len(packages) != len(meta['packages']) or len(nodes) != len(meta['resolve']['nodes']):
        raise RuntimeError('Duplicate Cargo package IDs')
    return packages, nodes


def edge(nodes, src_id, name):
    deps = [dep['pkg'] for dep in nodes[src_id].get('deps', []) if dep['name'] == name]
    if len(deps) != 1:
        raise RuntimeError(f'Expected one direct Cargo edge {name}, got {len(deps)}')
    return deps[0]


def locate_pake(root, packages):
    want = (root / 'src-tauri/Cargo.toml').resolve()
    matches = [p['id'] for p in packages.values()
               if p['name'] == 'pake' and p.get('manifest_path')
               and Path(p['manifest_path']).resolve() == want]
    if len(matches) != 1:
        raise RuntimeError('Cannot uniquely locate the Pake crate in Cargo dependency graph')
    return matches[0]


def runtime_versions(root, meta):
    """Follow Pake -> Tauri -> runtime-wry -> wry -> WebView2 -> Windows COM."""
    packages, nodes = graph(meta)
    start = locate_pake(root, packages)
    tauri = edge(nodes, start, 'tauri')
    if version(packages[tauri]['version']) < MIN_PORTABLE or version(packages[tauri]['version'])[0] != 2:
        raise RuntimeError('Resolved Tauri is too old or not supported for portable appDirectoriesOverride')
    # Find *reachable* wry package from the Tauri runtime, not another Wry
    # version appearing incidentally in the lockfile or build dependencies.
    queue = [tauri]
    seen = set()
    found = set()
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        if packages[current]['name'] == 'wry':
            found.add(current)
            continue
        for dep in nodes[current].get('deps', []):
            if dep['pkg'] in packages and dep['pkg'] not in seen:
                queue.append(dep['pkg'])
    if len(found) != 1:
        raise RuntimeError(f'Cannot uniquely identify Tauri Windows Wry runtime ({len(found)} found)')
    wry_id = next(iter(found))
    web_id = edge(nodes, wry_id, 'webview2_com')
    core_id = edge(nodes, web_id, 'windows_core')
    if packages[web_id]['name'] != 'webview2-com' or packages[core_id]['name'] != 'windows-core':
        raise RuntimeError('Wry WebView2 / Windows COM dependency chain changed')
    result = {'tauri': packages[tauri]['version'],
              'wry': packages[wry_id]['version'],
              'webview2-com': packages[web_id]['version'],
              'windows-core': packages[core_id]['version']}
    for val in result.values():
        version(val)
    return result


def direct_windows_versions(root):
    d = load_manifest(root)['target']['cfg(windows)']['dependencies']
    return {name: d[name] for name in ('windows-core', 'webview2-com')}


def prepare_rust(root):
    """Select the upstream locked Rust Tauri if portable-capable, else minimum 2.12.0."""
    load_manifest(root)
    locked = lock_tauri_version(root)
    current = version(locked)
    if current[0] != 2:
        raise RuntimeError(f'Unsupported Tauri major {locked}: do not auto-upgrade across major APIs')
    selected = locked if current >= MIN_PORTABLE else '.'.join(map(str, MIN_PORTABLE))
    if current < MIN_PORTABLE:
        path = root / 'src-tauri/Cargo.toml'
        old = path.read_text(encoding='utf-8')
        new = rewrite_exact(old, 'tauri', '=' + selected, table=True)
        if old == new:
            raise RuntimeError('Tauri version did not change when portable upgrade was required')
        path.write_text(new, encoding='utf-8', newline='\n')
        cmd_checked(['cargo', 'update', '-p', 'tauri', '--precise', selected], cwd=root / 'src-tauri')
    if lock_tauri_version(root) != selected:
        raise RuntimeError(f'Tauri Cargo.lock mismatch: expected {selected}')
    # Cargo graph can include Pake's old direct COM versions at this point;
    # the correct versions are derived from Wry's selected interfaces.
    need = runtime_versions(root, metadata(root))
    if need['tauri'] != selected:
        raise RuntimeError('Cargo resolved a different Rust Tauri than selected')
    path = root / 'src-tauri/Cargo.toml'
    original = path.read_text(encoding='utf-8')
    updated = rewrite_exact(original, 'webview2-com', '=' + need['webview2-com'])
    updated = rewrite_exact(updated, 'windows-core', '=' + need['windows-core'])
    if updated != original:
        path.write_text(updated, encoding='utf-8', newline='\n')
    # Reconcile Cargo.lock from the changed direct declarations, not by hand.
    # Do not globally update unrelated crates or overwrite any host project.
    resolved = metadata(root)
    verify_rust(root, resolved)
    print('AUTO-ALIGNED Rust: ' + ', '.join(f'{k}={v}' for k, v in need.items()))
    return need


def verify_rust(root, meta=None):
    meta = meta if meta is not None else metadata(root, locked=True)
    require = runtime_versions(root, meta)
    packages, nodes = graph(meta)
    pake = locate_pake(root, packages)
    declared = direct_windows_versions(root)
    for name in ('webview2-com', 'windows-core'):
        expected = '=' + require[name]
        if declared[name] != expected:
            raise RuntimeError(f'Pake direct {name} declaration {declared[name]!r}; expected {expected}')
        resolved_id = edge(nodes, pake, name.replace('-', '_'))
        actual = packages[resolved_id]['version']
        if actual != require[name]:
            raise RuntimeError(f'Pake direct {name} resolved {actual}; expected Wry {require[name]}')
    if lock_tauri_version(root) != require['tauri']:
        raise RuntimeError('Rust Tauri Cargo.lock mismatch after COM alignment')
    print('PASS: selected Wry WebView2 COM interface versions match Pake direct crate versions')
    return require


def installed(root, name):
    path = root / 'node_modules' / '@tauri-apps' / name / 'package.json'
    if not path.is_file():
        raise RuntimeError(f'Upstream pnpm installation missing {path}')
    data = json.loads(path.read_text(encoding='utf-8'))
    return data['version']


def latest_matching(package, major, minor):
    npm = 'npm.cmd' if os.name == 'nt' else 'npm'
    # Official npm registry; get version list once, choose highest *stable*
    # patch within the selected Rust major.minor. Do not upgrade to another minor.
    blob = cmd_checked([npm, '--registry=https://registry.npmjs.org', 'view',
                        package, 'versions', '--json'])
    try:
        entries = json.loads(blob.decode('utf-8-sig'))
    except (ValueError, UnicodeDecodeError) as e:
        raise RuntimeError(f'Invalid npm registry version data for {package}') from e
    if isinstance(entries, str):
        entries = [entries]
    if not isinstance(entries, list):
        raise RuntimeError('Unexpected npm versions API response')
    matches = [v for v in entries if isinstance(v, str) and SEMVER.fullmatch(v)
               and version(v)[:2] == (major, minor)]
    if not matches:
        raise RuntimeError(f'No stable {package} {major}.{minor}.x available from npm')
    return max(matches, key=version)


def prepare_javascript(root):
    """Keep installed compatible upstream packages; replace only mismatches."""
    rust = lock_tauri_version(root)
    rv = version(rust)
    if rv[0] != 2 or rv < MIN_PORTABLE:
        raise RuntimeError(f'Cannot align JavaScript to unsupported Rust Tauri {rust}')
    path = root / 'package.json'
    original = json.loads(path.read_text(encoding='utf-8'))
    if original.get('name') != 'pake-cli':
        raise RuntimeError('Unexpected upstream Node package')
    deps = original.get('dependencies', {})
    for name in ('@tauri-apps/api', '@tauri-apps/cli'):
        if not isinstance(deps.get(name), str):
            raise RuntimeError(f'Missing/invalid upstream {name} dependency')
        old = installed(root, name.split('/')[-1])
        if version(old)[:2] == rv[:2]:
            selected = old
        else:
            selected = latest_matching(name, *rv[:2])
        deps[name] = selected   # exact, no ^ or ~, for consistent pnpm.lock
        print(f'AUTO-ALIGNED {name}: {old} -> {selected} (Rust Tauri {rust})')
    path.write_text(json.dumps(original, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def verify_javascript(root):
    rv = version(lock_tauri_version(root))
    data = json.loads((root / 'package.json').read_text(encoding='utf-8'))
    deps = data['dependencies']
    for name in ('@tauri-apps/api', '@tauri-apps/cli'):
        declared = deps[name]
        actual = installed(root, name.split('/')[-1])
        if not SEMVER.fullmatch(declared) or declared != actual or version(actual)[:2] != rv[:2]:
            raise RuntimeError(f'JavaScript {name} declared {declared}, installed {actual}, Rust Tauri {rv}')
    print(f'PASS: actual installed JavaScript Tauri packages match Rust {rv[0]}.{rv[1]} and exact pnpm declarations')


def export_versions(root, destination):
    resolved = verify_rust(root)
    verify_javascript(root)
    data = {'source': 'resolved Cargo.lock and installed pnpm packages',
            'rust': resolved,
            'javascript': {name: installed(root, name.split('/')[-1])
                           for name in ('@tauri-apps/api', '@tauri-apps/cli')},
            'policy': 'retain upstream portable-capable Tauri 2.x; minimum 2.12; '
                      'match Rust minor and Wry direct Windows COM versions'}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    print(f'Verified resolved dependency provenance: {destination}')


def main():
    if len(sys.argv) not in (3, 4):
        raise SystemExit('Usage: upgrade-tauri.py upstream-source --prepare-rust|--verify-rust|--prepare-js|--verify-js|--export [file]')
    root = Path(sys.argv[1]).resolve()
    action = sys.argv[2]
    if action == '--prepare-rust':
        prepare_rust(root)
    elif action == '--verify-rust':
        verify_rust(root)
    elif action == '--prepare-js':
        prepare_javascript(root)
    elif action == '--verify-js':
        verify_javascript(root)
    elif action == '--export' and len(sys.argv) == 4:
        export_versions(root, Path(sys.argv[3]).resolve())
    else:
        raise SystemExit('Unknown action: ' + action)


if __name__ == '__main__':
    main()
