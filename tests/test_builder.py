"""Offline builder contract tests. Not a substitute for a real Windows runtime test."""
from pathlib import Path
import importlib.util
import json
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
        tag='portable-example-v1.0.0-pake3.18.0-r5-123456789abc'
        zipname='ExamplePortable_1.0.0_Pake3.18.0_r5_win-x64.zip'
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

    def test_yaml_has_no_installer_publishing(self):
        content=(ROOT/'.github/workflows/build-native.yml').read_text()
        self.assertIn('vhick/portable-release-publisher@v1.1.1',content)
        self.assertIn('dry-run: \'true\'',content)
        self.assertIn('dry-run: \'false\'',content)
        self.assertNotIn('actions/upload-artifact',content)
        self.assertNotIn('Portable-Package-Builder',content)


if __name__=='__main__': unittest.main()
