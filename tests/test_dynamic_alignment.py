"""Offline regression tests of upstream-compatible dependency discovery."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('upgrade_tauri_dynamic', ROOT/'scripts/upgrade-tauri.py')
up = importlib.util.module_from_spec(spec)
spec.loader.exec_module(up)


def fixture(root, *, tauri='2.12.0', api='2.10.1', cli='2.12.4'):
    cargo = root/'src-tauri'
    cargo.mkdir(parents=True)
    (cargo/'Cargo.toml').write_text('''[package]
name = "pake"
version = "3.19.0"
[dependencies]
tauri = { version = "2.10.2", features = [
 "tray-icon", "image-ico",
] }
[target.'cfg(windows)'.dependencies]
windows-sys = { version = "0.61.2", features = [
 "Win32_Foundation", ] }
webview2-com = "0.38"
windows-core = "0.61.2"
''', encoding='utf-8')
    (cargo/'Cargo.lock').write_text(f'[[package]]\nname = "tauri"\nversion = "{tauri}"\n',encoding='utf-8')
    (root/'package.json').write_text(json.dumps({'name':'pake-cli','dependencies':{
        '@tauri-apps/api':'~2.10.1','@tauri-apps/cli':'^2.12.4','unrelated':'1.0.0'}}),encoding='utf-8')
    for name, val in (('api',api),('cli',cli)):
        folder=root/'node_modules/@tauri-apps'/name
        folder.mkdir(parents=True)
        (folder/'package.json').write_text(json.dumps({'version':val}),encoding='utf-8')


def graph(root, *, tauri='2.12.0', wry='0.57.2', web='0.39.1', core='0.62.2', pake_core='0.61.2', pake_web='0.38.2'):
    cargo=root/'src-tauri/Cargo.toml'
    packages=[
        {'id':'pake','name':'pake','version':'3.18.0','manifest_path':str(cargo)},
        {'id':'tauri','name':'tauri','version':tauri},
        {'id':'runtime','name':'tauri-runtime-wry','version':tauri},
        {'id':'wry','name':'wry','version':wry},
        {'id':'web','name':'webview2-com','version':web},
        {'id':'core','name':'windows-core','version':core},
        {'id':'oldcore','name':'windows-core','version':pake_core},
        {'id':'oldweb','name':'webview2-com','version':pake_web},
    ]
    nodes=[
        {'id':'pake','deps':[{'name':'tauri','pkg':'tauri'},
                             {'name':'windows_core','pkg':'oldcore'},
                             {'name':'webview2_com','pkg':'oldweb'}]},
        {'id':'tauri','deps':[{'name':'tauri_runtime_wry','pkg':'runtime'}]},
        {'id':'runtime','deps':[{'name':'wry','pkg':'wry'}]},
        {'id':'wry','deps':[{'name':'webview2_com','pkg':'web'}]},
        {'id':'web','deps':[{'name':'windows_core','pkg':'core'}]},
        {'id':'core','deps':[]}, {'id':'oldcore','deps':[]}, {'id':'oldweb','deps':[]},
    ]
    return {'packages':packages,'resolve':{'nodes':nodes}}


class DynamicAlignmentTests(unittest.TestCase):
    def test_satisfy_new_upstream_cli_without_old_version_guard(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);fixture(root)
            with mock.patch.object(up,'latest_matching',return_value='2.12.3') as query:
                up.prepare_javascript(root)
            pkg=json.loads((root/'package.json').read_text())
            self.assertEqual(pkg['dependencies']['@tauri-apps/api'],'2.12.3')
            self.assertEqual(pkg['dependencies']['@tauri-apps/cli'],'2.12.4')
            self.assertEqual(pkg['dependencies']['unrelated'],'1.0.0')
            query.assert_called_once_with('@tauri-apps/api',2,12)
            # Verify after fake pnpm reinstall; bad version MUST fail.
            with self.assertRaisesRegex(RuntimeError,'api'):
                up.verify_javascript(root)
            (root/'node_modules/@tauri-apps/api/package.json').write_text(json.dumps({'version':'2.12.3'}))
            up.verify_javascript(root)

    def test_preserve_both_compatible_upstream_versions_without_npm_query(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);fixture(root,tauri='2.13.1',api='2.13.0',cli='2.13.4')
            with mock.patch.object(up,'latest_matching',side_effect=AssertionError('unexpected registry query')):
                up.prepare_javascript(root)
            data=json.loads((root/'package.json').read_text())['dependencies']
            self.assertEqual(data['@tauri-apps/api'],'2.13.0')
            self.assertEqual(data['@tauri-apps/cli'],'2.13.4')
            up.verify_javascript(root)

    def test_select_only_stable_matching_npm_minor_and_newest_patch(self):
        data=['2.12.3','2.12.0-beta.1','3.0.0','2.13.1','2.12.5','2.12.4']
        with mock.patch.object(up,'cmd_checked',return_value=json.dumps(data).encode()) as run:
            self.assertEqual(up.latest_matching('@tauri-apps/api',2,12),'2.12.5')
            self.assertIn('registry.npmjs.org',run.call_args.args[0][1])
        with mock.patch.object(up,'cmd_checked',return_value=b'[]'):
            with self.assertRaisesRegex(RuntimeError,'No stable'):
                up.latest_matching('@tauri-apps/api',2,12)

    def test_resolve_windows_com_from_reachable_wry_not_arbitrary_lock_entries(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);fixture(root)
            self.assertEqual(up.runtime_versions(root,graph(root)),
                             {'tauri':'2.12.0','wry':'0.57.2','webview2-com':'0.39.1','windows-core':'0.62.2'})
            future=graph(root,tauri='2.13.1',wry='0.61.0',web='0.40.3',core='0.63.4')
            self.assertEqual(up.runtime_versions(root,future)['webview2-com'],'0.40.3')
            future['resolve']['nodes'][3]['deps']=[]
            with self.assertRaisesRegex(RuntimeError,'webview2_com'):
                up.runtime_versions(root,future)

    def test_preexisting_portable_rust_is_kept_and_com_dependencies_align(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);fixture(root,tauri='2.13.1')
            before=graph(root,tauri='2.13.1',wry='0.61.0',web='0.40.3',core='0.63.4')
            after=graph(root,tauri='2.13.1',wry='0.61.0',web='0.40.3',core='0.63.4',
                        pake_core='0.63.4',pake_web='0.40.3')
            with mock.patch.object(up,'metadata',side_effect=[before,after]) as metadata, \
                 mock.patch.object(up,'cmd_checked',side_effect=AssertionError('should not force Rust upgrade')):
                up.prepare_rust(root)
            self.assertEqual(metadata.call_count,2)
            text=(root/'src-tauri/Cargo.toml').read_text()
            self.assertIn('windows-core = "=0.63.4"',text)
            self.assertIn('webview2-com = "=0.40.3"',text)
            self.assertIn('windows-sys = { version = "0.61.2"',text)
            self.assertIn('tauri = { version = "2.10.2"',text)  # unchanged declaration but lock newer

    def test_older_rust_upgrades_only_to_portable_minimum(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);fixture(root,tauri='2.10.2')
            before=graph(root)
            after=graph(root,pake_core='0.62.2',pake_web='0.39.1')
            def update(args, cwd=None):
                self.assertEqual(args[:4],['cargo','update','-p','tauri'])
                (root/'src-tauri/Cargo.lock').write_text('[[package]]\nname="tauri"\nversion="2.12.0"\n')
                return b''
            with mock.patch.object(up,'cmd_checked',side_effect=update), \
                 mock.patch.object(up,'metadata',side_effect=[before,after]):
                up.prepare_rust(root)
            self.assertIn('tauri = { version = "=2.12.0"',(root/'src-tauri/Cargo.toml').read_text())

    def test_refuse_tauri_major_upgrade_and_unrecognized_source(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);fixture(root,tauri='3.0.0')
            with self.assertRaisesRegex(RuntimeError,'major'):
                up.prepare_rust(root)
            with self.assertRaisesRegex(RuntimeError,'unsupported'):
                up.prepare_javascript(root)
            (root/'src-tauri/Cargo.toml').write_text('[package]\nname="pake"\n')
            with self.assertRaisesRegex(RuntimeError,'tauri declaration'):
                up.prepare_rust(root)

    def test_metadata_decodes_utf8_bytes_on_windows(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);fixture(root)
            payload=json.dumps(graph(root),ensure_ascii=False).replace('pake','pake 🚀',1).encode('utf-8')
            with mock.patch.object(up,'cmd_checked',return_value=payload):
                decoded=up.metadata(root,locked=True)
                self.assertEqual(decoded['resolve']['nodes'][0]['id'],'pake')
            with mock.patch.object(up,'cmd_checked',return_value=b'\x8f bad'):
                with self.assertRaisesRegex(RuntimeError,'UTF-8 JSON'):
                    up.metadata(root)

    def test_r10_workflow_is_still_zip_only_and_release_publisher_pinned(self):
        w=(ROOT/'.github/workflows/build-native.yml').read_text()
        p=(ROOT/'scripts/build-website.ps1').read_text()
        self.assertIn('portable-release-publisher@v1.1.1',w)
        self.assertNotIn('actions/upload-artifact',w)
        self.assertIn('r10',w)
        self.assertIn('--prepare-rust',p)
        self.assertLess(p.index('--prepare-rust'),p.index('node dist/cli.js @cliArgs'))
        self.assertLess(p.index('--verify-js'),p.index('node dist/cli.js @cliArgs'))
        self.assertIn('--export',p)
        self.assertIn('RESOLVED-DEPENDENCIES.json', (ROOT/'scripts/stage-package.ps1').read_text())

if __name__=='__main__': unittest.main()
