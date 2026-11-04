# Source-based Windows portability audit — Pake-generated apps

Audited baseline: `tw93/Pake` stable **V3.18.0**, source files listed below. New stable tags are resolved automatically, but source patches **fail closed** if the audited code layout changes.

This builder generates apps **from website URLs**. It does not package the Pake CLI for interactive use and does not package the Pake paid GUI.

| Item | Upstream behavior / evidence | This builder's adaptation | Limit |
| --- | --- | --- | --- |
| Real application | Pake CLI compiles a Rust/Tauri v2 Windows application. `--keep-binary` retains an `AppName.exe` executable alongside the Windows MSI. | Copy only the original compiled PE to `AppNamePortable/AppNamePortable.exe`; no renamed installer or script wrapper. | Pake still compiles an **intermediate** MSI during `--keep-binary`; the ZIP/release never contains it. |
| WebView2 profile, cookies, cache, local storage | `src-tauri/src/app/window.rs` sets `WebviewWindowBuilder::data_directory(_data_dir)`. `_data_dir` comes from `src-tauri/src/util.rs:get_data_dir`, which originally uses `app.path().config_dir()` (normal host config directory). | Patch `get_data_dir` **before Rust compilation** to `exe_root/Data/WebView/<Pake profile name>`; this also preserves any empty nested folders naturally. | Requires system-wide **Microsoft Edge WebView2 Runtime**, which is not bundled. WebView2/OS crash diagnostic traces outside managed directories are not guaranteed absent. |
| Tauri state, plugin storage, window state | `src-tauri/src/lib.rs:run_app` uses `tauri::generate_context!` and `tauri-plugin-window-state`. | Set Tauri `app.app_directories_override` to `exe_root/Data/State` **before constructing the Tauri application**. | Only Tauri APIs and plugins respecting the override are covered. |
| Last opened URL | `src-tauri/src/util.rs` and app window source store `last-url.txt` in `get_data_dir` location. | Follows portable `Data/WebView/...` path. | `--no-restore-last-url` option changes whether last page is restored; cookies are still kept. |
| Website downloads | Pake defaults to the Windows Downloads folder through `app.path().download_dir()`. | **Intentionally unchanged**; files downloaded by the user remain in their usual Windows Downloads folder. | Downloads outside portable Data are deliberate user files, not stealth profile traces. |
| Registry, system dependencies | WebView2 runtime, Windows shell integration, notifications, COM and website actions can use ordinary Windows system facilities. | No direct permanent registry changes made by the builder launcher (the launcher is the actual Tauri EXE). | Normal OS integration/telemetry, Windows caches and system-managed registry keys cannot be guaranteed absent. |
| ProgramData / AppData unrelated host data | Pake WebView2 path is application-owned, but same Windows account may have preexisting profiles and shared dependencies. | **Never move, delete, junction, or overwrite** unrelated `AppData`, `LocalAppData`, `ProgramData`, PowerShell/PackageManagement or shared Edge profiles. | No automatic ownership inference or blanket runtime sweep is performed. |
| Browser engines | Tauri on Windows uses Microsoft Edge WebView2, not a bundled Chromium engine. | The generated binary retains WebView2 dependency and stores *its owned profile* under portable Data. | First-run/runtime install policy of WebView2 is outside builder control. |
| Installer | Upstream's Windows CLI normally exports an MSI (see official workflow). | Publish a verified standalone ZIP only. Shared Package Builder is deliberately **not invoked** for NATIVE ZIP mode. | Not a certified `.paf.exe` or official PortableApps.com Installer distribution. |
| Icon and PortableApps Menu | Tauri embeds app-specific icon from Pake's website icon resolver or fallback. | Extract the true app's embedded icon to PortableApps `App/AppInfo/appicon.ico` and PNG sizes, and set `Control/Start` to real EXE. | Filename and generic AppID must be reviewed if redistributing under a third-party brand. |
| Repeated launches, empty directories | Windows app lives alongside Data. | Source-level redirection does not require post-exit relocation and naturally retains files/empty dirs in Data. ZIP creation explicitly retains empty Data directories. | No general dynamic TraceGuard discovery of *unidentified new host paths*. Validate on a real Windows machine; report leftovers instead of automatically deleting host data. |
| Upgrade and rollback | Pake app version and website settings are compiled into the executable. | AppNamePortable folder remains stable; replace EXE/App/Other while retaining `Data`. Use backups before rollback. | Data schemas and WebView2 profile compatibility can change upstream; old EXEs may not read newer profile formats. |

## Portability code in this kit

`scripts/patch-portability.py` implements both Rust source changes (and stops the workflow if source anchors change). `scripts/stage-package.ps1` uses the real Pake output and never extracts an EXE from an installer. `scripts/validate.py` checks actual Windows PE x64 structure, ZIP integrity, absence of installers, and presence of all Data paths. These **static** checks cannot establish GUI/browser functionality on an unattended runner.

## Upstream and docs

- https://github.com/tw93/Pake/blob/main/.github/workflows/pake-cli.yaml
- https://github.com/tw93/Pake/blob/main/docs/cli-usage.md
- https://github.com/tw93/Pake/blob/main/src-tauri/src/lib.rs
- https://github.com/tw93/Pake/blob/main/src-tauri/src/util.rs
- https://github.com/tw93/Pake/blob/main/src-tauri/src/app/window.rs
- https://v2.tauri.app/reference/config/#appdirectoriesoverride
- https://portableapps.com/development/portableapps.com_format

## Data backup and trace policy

- **Never delete an old `Data` directory during an update.** It can contain login sessions and other irreplaceable information.
- Do not restore older backups over a newer profile without keeping the newer one separately. Older WebView2 versions may not be able to read newer data.
- To investigate an unexpected external trace, compare a clean test profile before/after launching the generated app; establish exclusive app ownership before proposing recovery. Do not sweep broad Windows user profile folders.
- The `Data/TraceGuard/` folder in the ZIP is **reserved**. This project does not claim to implement dynamic external tracing or crash relocation. Pake-native source redirection is the primary portability technique.


**Tauri version:** Pake V3.18.0 uses Tauri 2.10.2 in Cargo.lock. The
source-level portable profile API requires Tauri **2.12.0** (released
September 2026). This builder updates the temporary clone's tauri Rust
dependency and checks the resulting lockfile. A dependency incompatibility
fails the build rather than publishing a profile-writing executable. This
specific Rust dependency upgrade has not yet been verified by a full Windows
build. Reference: https://tauri.app/release/tauri/v2.12.0/
