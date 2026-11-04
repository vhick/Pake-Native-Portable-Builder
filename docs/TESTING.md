# Tests and acceptance checklist

## Automated checks supplied (run on GitHub Windows runner)

- Python input validation and unique release identity tests.
- Pake stable tag selection self-test and verified git commit retrieval.
- PowerShell parse check for all build scripts.
- Source layout gate: both Rust patches must land exactly once or build fails.
- Pake CLI build with frozen upstream pnpm lockfile and `--keep-binary` flag.
- Original Pake output must be a real x64 PE app (not an MSI renamed to EXE).
- Real executable icon extraction into PortableApps Menu metadata.
- ZIP integrity, independent packaging and empty directory entries.
- Shared release publisher `dry-run:true` before `dry-run:false`.

**These tests are included in the kit but have not yet run on a GitHub Windows runner in this conversation.** The current build has only passed local Python tests and YAML/ZIP checks.

## Manual Windows test plan (mandatory before declaring proven portable)

1. Download the published ZIP from GitHub Releases and extract it, not the repository's source-code archive.
2. In `AppNamePortable`, double-click `AppNamePortable.exe`. Confirm the website opens in a graphical window.
3. Sign in if the site allows embedded browser authentication, browse a few pages, then **quit** (not just minimize to tray).
4. Inspect `AppNamePortable/Data/WebView` for WebView2 profile data and `Data/State` for plugin/state data.
5. Check whether the intended app created new data under `%APPDATA%`, `%LOCALAPPDATA%`, `%LOCALAPPDATA%\Low`, or `%PROGRAMDATA%`, comparing the **before** and **after** snapshots. Do not delete shared or preexisting files.
6. Create an empty directory at `Data/State/test-empty` and a nested empty tree at `Data/WebView/test-empty/a/b`. Quit, copy the entire folder to another drive and verify these directories survive.
7. Relaunch from the other drive; verify browsing state/session persists and check for new external app-owned traces.
8. Close, back up `Data`, and test updating EXE/App/Other from a new ZIP **without overwriting Data**.
9. Test rolling back with a backed-up copy of the newer `Data`, not by replacing profiles with old defaults.
10. Put the extracted folder under `PortableApps\AppNamePortable` and refresh PortableApps Menu; check icon, name and launcher execution.
11. Check whether any website feature requires browser access that WebView2 disallows (OAuth sign-in, browser extensions, custom protocol integrations).
12. On machines without Edge WebView2 Runtime, confirm that runtime is separately available and document failures; the app is not fully standalone from Windows components.

## Failure triage

- **Missing EXE**: check the Pake `--keep-binary` build step and its output filename; source UI/CLI may have changed.
- **Rust compilation failed**: check the patch source-compatibility error, pinned upstream version and Windows toolchain before modifying portable code.
- **App opens but profile writes to host**: do not delete host data. Collect actual paths, parent process, pre-launch snapshots and relevant app logs; fix the source path redirect.
- **MSI present during the build**: expected intermediate from upstream Pake, not published. The GitHub Release should contain **only a ZIP plus publisher checksums**.
- **No download after green workflow**: if `publish:false`, nothing is uploaded by design. Run again with `publish:true`.
- **Old release skipped**: the same app configuration and Pake version already exists; change app version or an option for a distinct release if needed.


**Tauri version:** Pake V3.18.0 uses Tauri 2.10.2 in Cargo.lock. The
source-level portable profile API requires Tauri **2.12.0** (released
September 2026). This builder updates the temporary clone's tauri Rust
dependency and checks the resulting lockfile. A dependency incompatibility
fails the build rather than publishing a profile-writing executable. This
specific Rust dependency upgrade has not yet been verified by a full Windows
build. Reference: https://tauri.app/release/tauri/v2.12.0/


## r6 WiX dependency preflight

The GitHub runner validates `wix311-binaries.zip` against the known upstream-release SHA-256 and checks that `candle.exe` and `light.exe` were extracted into `work/tools/wix311`. No WiX installer is executed. This is a build prerequisite only: the final release ZIP must not contain an MSI or WiX binaries.


### r7 dependency alignment
Before Pake generates a website app, verify that its temporary Node packages are `@tauri-apps/api` 2.12.3 and `@tauri-apps/cli` 2.12.2, and its Rust `tauri` crate is 2.12.0. The build fails closed if they disagree.
