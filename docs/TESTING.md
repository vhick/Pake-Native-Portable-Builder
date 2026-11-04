# Testing matrix and manual Windows acceptance

## Automated in Windows workflow

| Test | Implemented step |
| --- | --- |
| Stable tag and SHA match | resolve-upstream + fetch-upstream |
| Build real CLI | pnpm lock install + cli:build + npm pack |
| Compile launcher | `dotnet publish -r win-x64 --self-contained true` |
| PE header + execution | validate.ps1 + `--help`/`--version` |
| TraceGuard files + empty folders | `--traceguard-selftest` |
| ZIP integrity and required entries | validate.ps1 with `System.IO.Compression` |
| Publisher selection and dry-run | shared publisher @v1.1.1 |

## Manual checks (not claimed as passing)

1. Extract the ZIP on a Windows 10/11 x64 system to `D:\PakePortable` and execute `PakePortable.exe --version`.
2. Run `PakePortable.exe https://example.com --name Example` on a PC with Rust and MSVC; check `Data\Output` for its real MSI output.
3. Check that `Data\Profile`, `Data\Temp`, `Data\Cache` contain CLI-managed data. Search external APPDATA and LocalAppData for new Pake-related writes using a Windows tracing tool.
4. Check unrelated pre-existing `%APPDATA%`, `%LOCALAPPDATA%`, `%PROGRAMDATA%` and Rust configurations remain untouched.
5. Create nested empty directories in Data, run `PakePortable.exe --help`, and verify `Data\TraceGuard\manifest.json` lists them.
6. Copy whole folder to another drive and run `PakePortable.exe --version`.
7. Place a sentinel file in `Data`, replace only App, EXE and source metadata during a version upgrade, verify sentinel survives. Repeat with downgrade.
8. Kill a build unexpectedly, then run `PakePortable.exe --help` to check interrupted-session recovery. Check cleanup errors rather than removing host data manually.
9. If a generated Windows Tauri app must also become portable, audit and package that app in a **separate** builder with its own WebView2 and TraceGuard implementation.

No installer was requested in NATIVE mode; installation/PAF validation and PortableApps Menu discovery are not applicable.
