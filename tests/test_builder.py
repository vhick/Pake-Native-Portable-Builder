"""Source-only checks. Windows runtime tests run in scripts/validate.ps1."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]

class BuilderStructure(unittest.TestCase):
    def test_required_files(self):
        for name in [
            '.github/workflows/build-native.yml',
            'launcher/Program.cs', 'launcher/PakePortable.csproj',
            'scripts/resolve-upstream.ps1', 'scripts/fetch-upstream.ps1',
            'scripts/build-cli.ps1', 'scripts/build-launcher.ps1',
            'scripts/validate.ps1', 'scripts/check-existing.ps1',
            'README.md', 'docs/AUDIT.md', 'docs/TESTING.md',
        ]:
            self.assertTrue((ROOT / name).is_file(), name)
    def test_native_mode_has_no_fake_portableapps_installer(self):
        workflow = (ROOT / '.github/workflows/build-native.yml').read_text()
        self.assertIn('portable-release-publisher@v1.1.1', workflow)
        self.assertNotIn('Portable-Package-Builder@', workflow)
        self.assertIn('release/*.zip', workflow)
        self.assertNotIn('upload-artifact', workflow)
        self.assertRegex(workflow, r"dry-run: 'true'")
        self.assertRegex(workflow, r"dry-run: 'false'")
    def test_empty_directory_recovery_included(self):
        code = (ROOT / 'launcher/Program.cs').read_text()
        self.assertIn('Directory.EnumerateDirectories', code)
        self.assertIn('CaptureExternalRoots', code)
        self.assertIn('RunSelfTest', code)
        self.assertIn('Directory.Exists(Path.Combine(dest, "alpha", "beta", "empty"))', code)
        self.assertIn('pre-existing host root protected', code)
        self.assertIn('CopyVerified(saved, path)', code)
    def test_no_opaque_launcher(self):
        project = (ROOT / 'launcher/PakePortable.csproj').read_text()
        self.assertIn('<OutputType>Exe</OutputType>', project)
        self.assertIn('<PublishSingleFile>true</PublishSingleFile>', project)
        self.assertNotIn('ScriptToExe', project)
    def test_powershell_string_interpolation_regression(self):
        """Catch accidental '$tag:' interpolations before GitHub's actual PS parser check.

        PowerShell scopes like $env:FOO and $script:name are deliberate exceptions.
        This is a source lint test, not a replacement for the PowerShell parser.
        """
        allowed_scopes = {'env', 'script', 'global', 'local', 'private', 'using', 'function', 'variable'}
        for script in (ROOT / 'scripts').glob('*.ps1'):
            source = script.read_text(encoding='utf-8')
            for match in re.finditer(r'(?<![`$])\$([A-Za-z_][A-Za-z0-9_]*):', source):
                self.assertIn(match.group(1).lower(), allowed_scopes,
                              f'{script.name}:{source.count(chr(10), 0, match.start())+1}: ambiguous {match.group()}')

    def test_release_resolver_enumeration_regression(self):
        code = (ROOT / 'scripts/resolve-upstream.ps1').read_text()
        workflow = (ROOT / '.github/workflows/build-native.yml').read_text()
        self.assertNotRegex(code, r'(?m)^\s*\$[A-Za-z_]\w*\s*=\s*@\(Invoke-RestMethod')
        self.assertIn('[object[]]$releases = $releaseResponse', code)
        self.assertIn('foreach ($release in $Releases)', code)
        self.assertIn('if ($SelfTest)', code)
        self.assertIn('V3.17.6', code)
        self.assertIn('./scripts/resolve-upstream.ps1 -SelfTest', workflow)
        self.assertIn('native-r3', workflow)

    def test_all_script_files_are_nonempty(self):
        for script in (ROOT / 'scripts').glob('*.ps1'):
            self.assertGreater(script.stat().st_size, 100)

if __name__ == '__main__':
    unittest.main()
