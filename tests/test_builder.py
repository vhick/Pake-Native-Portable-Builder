"""Offline builder contract tests. Not a substitute for a real Windows runtime test."""
from pathlib import Path
import importlib.util
import json
from unittest import mock
import struct
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


planmod = module('plan')
patchmod = module('patch-portability')
checkmod = module('check-existing')
zipmod = module('zip-package')
validmod = module('validate')


class BuilderTests(unittest.TestCase):
    def fixture(self):
        return dict(website_url='https://excalidraw.com', app_name='Excalidraw',
                    app_version='1.0.0', pake_version='3.18.0', icon_url='',
                    width='1200', height='780')

    def test_valid_plan_and_stable_identity(self):
        plan = planmod.make_plan(self.fixture())
        self.assertEqual(plan['exe'], 'ExcalidrawPortable.exe')
        self.assertEqual(plan['folder'], 'ExcalidrawPortable')
        self.assertEqual(plan['releaseTag'], planmod.make_plan(self.fixture())['releaseTag'])
        self.assertTrue(plan['releaseTag'].startswith('portable-excalidraw-'))

    def test_config_change_changes_release_identity(self):
        a = self.fixture(); b = self.fixture(); b['width'] = '1300'
        self.assertNotEqual(planmod.make_plan(a)['releaseTag'], planmod.make_plan(b)['releaseTag'])

    def test_reject_private_or_invalid_url(self):
        for value in ('http://localhost:3000', 'http://127.0.0.1', 'http://192.168.1.2',
                      'file:///C:/x', 'ftp://google.com', 'https://a.local',
                      'https://user:pw@site.com', 'http://[::1]/'):
            obj = self.fixture(); obj['website_url'] = value
            with self.assertRaises(ValueError, msg=value): planmod.make_plan(obj)

    def test_invalid_windows_names_and_versions(self):
        for name in ('..', 'CON?', 'A/B', 'A', 'Alpha\nBeta'):
            obj = self.fixture(); obj['app_name'] = name
            with self.assertRaises(ValueError, msg=name): planmod.make_plan(obj)
        obj = self.fixture(); obj['app_version'] = '1.0.0-beta'
        with self.assertRaises(ValueError): planmod.make_plan(obj)

    def test_portable_patch_updates_both_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'src-tauri/src').mkdir(parents=True)
            lib = 'fn run() {\n    let mut context = tauri::generate_context!();\n}\n'
            util = ('pub fn get_data_dir(app: &AppHandle, package_name: String) -> std::io::Result<PathBuf> {\n'
                    '    let data_dir = app.path().config_dir()?.join(package_name);\n'
                    '    Ok(data_dir)\n}\n'
                    'pub fn read_last_url(path: &Path) -> std::io::Result<()> { Ok(()) }\n')
            (root / 'src-tauri/src/lib.rs').write_text(lib)
            (root / 'src-tauri/src/util.rs').write_text(util)
            patchmod.patch_files(root)
            self.assertIn('app_directories_override', (root / 'src-tauri/src/lib.rs').read_text())
            self.assertIn('root.join("Data").join("WebView")', (root / 'src-tauri/src/util.rs').read_text())
            with self.assertRaises(RuntimeError): patchmod.patch_files(root)

    def test_patch_fails_closed_on_unknown_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'src-tauri/src').mkdir(parents=True)
            (root / 'src-tauri/src/lib.rs').write_text('some code')
            (root / 'src-tauri/src/util.rs').write_text('more code')
            with self.assertRaises(RuntimeError): patchmod.patch_files(root)

    def test_existing_release_check_distinguishes_error(self):
        tag='portable-example-v1.0.0-pake3.18.0-r8-123456789abc'
        zipname='ExamplePortable_1.0.0_Pake3.18.0_r8_win-x64.zip'
        self.assertFalse(checkmod.classify_return(1, '', 'release not found', tag, zipname))
        valid={'isDraft':False,'body':'portable-release-publisher:managed:v2',
               'assets':[{'name':zipname},{'name':'SHA256SUMS.txt'}]}
        self.assertTrue(checkmod.classify_return(0, json.dumps(valid), '', tag, zipname))
        with self.assertRaises(RuntimeError): checkmod.classify_return(1,'','HTTP 403',tag,zipname)
        with self.assertRaises(RuntimeError): checkmod.classify_return(0,'{}','',tag,zipname)

    def test_zip_keeps_nested_empty_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'ExamplePortable'
            (root/'Data/State/deep/empty').mkdir(parents=True)
            (root/'README.txt').write_text('hello')
            output=Path(tmp)/'portable.zip'
            zipmod.make_zip(root,output)
            with zipfile.ZipFile(output) as z:
                self.assertIn('ExamplePortable/Data/State/deep/empty/',z.namelist())
                self.assertEqual(z.read('ExamplePortable/README.txt'),b'hello')

    def test_pe_x64_check(self):
        data=bytearray(1024); data[:2]=b'MZ'; struct.pack_into('<I',data,0x3c,128)
        data[128:132]=b'PE\0\0'; struct.pack_into('<H',data,132,0x8664)
        self.assertTrue(validmod.is_x64_pe(data))
        self.assertFalse(validmod.is_x64_pe(b'MZ'))
        struct.pack_into('<H',data,132,0x14c)
        self.assertFalse(validmod.is_x64_pe(data))

    def test_tauri_requires_portable_api_and_strict_lock(self):
        code = (ROOT/'scripts/upgrade-tauri.py').read_text()
        build = (ROOT/'scripts/build-website.ps1').read_text()
        self.assertIn('2.12.0', code)
        self.assertIn('cargo update -p tauri --precise 2.12.0', build)
        self.assertIn('AppDirectoriesOverride::Root', patchmod.CONTEXT_PATCH)
        self.assertIn('src-tauri', code)

    def test_r8_direct_windows_com_upgrade_matches_original_pake_manifest(self):
        up = module('upgrade-tauri')
        original = ("[package]\nname = \"pake\"\n[dependencies]\n"
                    "tauri = { version = \"2.10.2\", features = [\n"
                    "  \"tray-icon\",\n  \"image-ico\",\n] }\n"
                    "[target.'cfg(windows)'.dependencies]\n"
                    "windows-sys = { version = \"0.61.2\", features = [\n"
                    "  \"Win32_Foundation\",\n] }\n"
                    "webview2-com = \"0.38\"\n"
                    "windows-core = \"0.61.2\"\n")
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); folder=root/'src-tauri'; folder.mkdir()
            manifest=folder/'Cargo.toml'; manifest.write_text(original, encoding='utf-8')
            up.prepare(root)
            result=manifest.read_text(encoding='utf-8')
            self.assertIn('tauri = { version = "2.12.0"', result)
            self.assertIn('windows-core = "=0.62.2"', result)
            self.assertIn('webview2-com = "=0.39.1"', result)
            self.assertIn('windows-sys = { version = "0.61.2"', result)
            self.assertEqual(up.direct_windows_versions(root),
                             {'windows-core': '=0.62.2', 'webview2-com': '=0.39.1'})
            # A new unexpected Pake manifest must fail without partially updating the file.
            altered=original.replace('webview2-com = "0.38"', 'webview2-com = "0.99"')
            manifest.write_text(altered, encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'WebView2 bindings'):
                up.prepare(root)
            self.assertEqual(manifest.read_text(encoding='utf-8'), altered)

    def test_r8_cargo_metadata_checks_actual_direct_edges_not_transitive_versions(self):
        up=module('upgrade-tauri')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); cargo=root/'src-tauri/Cargo.toml'
            cargo.parent.mkdir(parents=True)
            cargo.write_text('[package]\nname="pake"\nversion="3.18.0"\n')
            packages=[
                {'name':'pake','id':'pake-id','manifest_path':str(cargo),'version':'3.18.0'},
                {'name':'windows-core','id':'win-new','version':'0.62.2'},
                {'name':'webview2-com','id':'wv-new','version':'0.39.1'},
                {'name':'windows-core','id':'win-old-transitive','version':'0.61.2'},
            ]
            meta={'packages':packages,'resolve':{'nodes':[{'id':'pake-id', 'deps':[
                {'name':'windows_core','pkg':'win-new'},
                {'name':'webview2_com','pkg':'wv-new'},
            ]}]}}
            with mock.patch.object(up.subprocess, 'run', return_value=mock.Mock(stdout=json.dumps(meta))) as run:
                up.verify_resolved_windows(root)
                meta['resolve']['nodes'][0]['deps'][0]['pkg']='win-old-transitive'
                run.return_value.stdout = json.dumps(meta)
                with self.assertRaisesRegex(RuntimeError, 'windows_core'):
                    up.verify_resolved_windows(root)

    def test_r8_windows_preflight_is_before_portability_patch_and_compile(self):
        text=(ROOT/'scripts/build-website.ps1').read_text(encoding='utf-8')
        self.assertLess(text.index('--verify-resolved-windows'), text.index('scripts/patch-portability.py'))
        self.assertLess(text.index('--verify-resolved-windows'), text.index('node dist/cli.js @cliArgs'))
        self.assertEqual(planmod.BUILDER_REVISION, 'r8')

    def test_tauri_js_rewrite_and_installed_versions(self):
        up = module('upgrade-tauri')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'package.json').write_text(json.dumps({
                'name': 'pake-cli',
                'dependencies': {'@tauri-apps/api': '~2.10.1',
                                 '@tauri-apps/cli': '^2.10.0',
                                 'other-lib': '1.0.0'},
                'scripts': {'build': 'tauri build'},
            }), encoding='utf-8')
            up.prepare_javascript(root)
            manifest = json.loads((root / 'package.json').read_text())
            self.assertEqual(manifest['dependencies']['@tauri-apps/api'], '2.12.3')
            self.assertEqual(manifest['dependencies']['@tauri-apps/cli'], '2.12.2')
            self.assertEqual(manifest['dependencies']['other-lib'], '1.0.0')
            for name, version in [('api', '2.12.3'), ('cli', '2.12.2')]:
                folder = root / 'node_modules/@tauri-apps' / name
                folder.mkdir(parents=True, exist_ok=True)
                (folder / 'package.json').write_text(json.dumps({'version': version}))
            up.verify_javascript(root)
            with self.assertRaises(RuntimeError): up.prepare_javascript(root)
            (root / 'node_modules/@tauri-apps/api/package.json').write_text(json.dumps({'version':'2.10.1'}))
            with self.assertRaisesRegex(RuntimeError, 'Installed @tauri-apps/api'):
                up.verify_javascript(root)

    def test_tauri_js_verification_precedes_application_build(self):
        build = (ROOT/'scripts/build-website.ps1').read_text(encoding='utf-8')
        self.assertIn('pnpm install --no-frozen-lockfile', build)
        self.assertIn('pnpm install --frozen-lockfile', build)
        self.assertLess(build.index('--prepare-js'), build.index('pnpm run cli:build'))
        self.assertLess(build.index('--verify-js'), build.index('node dist/cli.js @cliArgs'))
        self.assertIn('cargo update -p tauri --precise 2.12.0', build)
        # Upstream Pake 3.18.0 is known to lock API 2.10.1 and Rust 2.10.2.
        source = (ROOT / 'scripts/upgrade-tauri.py').read_text(encoding='utf-8')
        self.assertIn('ORIGINAL_JS_API', source)
        self.assertIn('JS_API_TARGET', source)

    def test_wix_uses_pinned_portable_binaries_not_quiet_install(self):
        code = (ROOT / 'scripts/ensure-wix.ps1').read_text(encoding='utf-8')
        self.assertIn('wix3112rtm/wix311-binaries.zip', code)
        self.assertIn('2C1888D5D1DBA377FC7FA14444CF556963747FF9A0A289A3599CF09DA03B9E2E', code)
        self.assertIn('Get-FileHash', code)
        self.assertIn('Expand-Archive', code)
        self.assertIn("'light.exe'", code)
        self.assertIn("'candle.exe'", code)
        self.assertIn('$env:GITHUB_PATH', code)
        self.assertNotIn('Start-Process', code)
        self.assertNotIn('wix311.exe', code)
        self.assertNotIn('ProgramFiles(x86)', code)

    def test_yaml_has_no_installer_publishing(self):
        content=(ROOT/'.github/workflows/build-native.yml').read_text()
        self.assertIn('vhick/portable-release-publisher@v1.1.1',content)
        self.assertIn('dry-run: \'true\'',content)
        self.assertIn('dry-run: \'false\'',content)
        self.assertNotIn('actions/upload-artifact',content)
        self.assertNotIn('Portable-Package-Builder',content)


if __name__=='__main__': unittest.main()
