# Pake Portable Website App Builder r6

**Create a portable Windows website app in GitHub Actions without installing Node, Rust or a website builder on your own PC.** The generated **website app itself** launches by double-clicking its `.exe`. This replaces the old r1-r4 behavior of packaging the Pake command-line tool.

Based on the official Pake Actions process: https://github.com/tw93/Pake/blob/main/.github/workflows/pake-cli.yaml

## What this produces

Example workflow inputs:

| Input | Example |
| --- | --- |
| Website URL | `https://excalidraw.com` |
| App name | `Excalidraw` |
| Icon URL | (empty = Pake fetches site's own icon) |
| Your app version | `1.0.0` |
| Width / Height | `1200` / `780` |
| Open new windows | optional, `false` by default |
| Start fullscreen | optional, `false` by default |
| Hide window decorations | optional, `false` by default |
| Always start at home URL | optional, `false` by default |
| Pake upstream tag | empty = latest stable |
| Publish ZIP | `true` |

Result on your **repository's Releases page**:

```
ExcalidrawPortable_1.0.0_Pake3.18.0_r6_win-x64.zip
SHA256SUMS.txt                       (produced by shared publisher)
```

When extracted:

```
ExcalidrawPortable/
  ExcalidrawPortable.exe           (real compiled website GUI app, NOT a CLI or installer)
  App/
    AppInfo/
      appinfo.ini                  (PortableApps Menu entry)
      appicon.ico                  (extracted from compiled app)
      appicon_16.png
      appicon_32.png
  Data/
    State/                         (Tauri and plugins)
    WebView/                       (isolated WebView2 profile, logins, cookies, cache)
    TraceGuard/                    (reserved for future trace evidence)
  Other/Source/                   (licenses, source patch and provenance)
  README-PORTABLE.txt
```

No `.msi`, setup `.exe`, `.paf.exe`, or precompiled Pake CLI is in the published package. **Current upstream Pake still builds a temporary MSI as part of `--keep-binary`**; the workflow does not publish it. The shared `Portable-Package-Builder@v1.0.0` is deliberately not invoked for this **NATIVE ZIP-only** builder. The shared publisher remains pinned to `vhick/portable-release-publisher@v1.1.1`.

## Step-by-step with GitHub Desktop

### Existing Pake r4 builder repository — recommended upgrade

1. In GitHub Desktop, open your existing independent Pake builder repository (not a fork of `tw93/Pake`).
2. Download and extract **Pake-Portable-Website-App-Builder-r6.zip** from this conversation.
3. Copy **all** contents, including `.github`, into that repository folder, allowing overwrites.
4. The ZIP deliberately uses the same filename `.github/workflows/build-native.yml` as r4, so it **replaces** the old CLI workflow. It appears in GitHub Actions as **Build Website as Portable Windows App**.
5. Old unused r4 scripts may remain in the repository. They are not executed by the new workflow. For a clean repository, compare the folders and delete old-only `launcher/` and `scripts/build-cli.ps1`, `scripts/build-launcher.ps1`, `scripts/check-existing.ps1`, and `scripts/validate.ps1` only if the r6 equivalent is already present. (The file `scripts/validate.py` is a different new script.) The existing r4 GitHub Releases are untouched.
6. In GitHub Desktop, enter a commit summary like `Replace Pake CLI builder with portable website app workflow r6`.
7. Select **Commit to main**, then **Push origin**.
8. On GitHub, open the repository → **Actions** → **Build Website as Portable Windows App** → **Run workflow**.
9. Fill in `website_url` and `app_name`; leave the other defaults for a first test. Leave **Publish ZIP** checked.
10. When the run succeeds, go to **Releases**, select the new tag beginning `portable-`, and download the ZIP — **not** `Source code (zip)`.
11. Extract the ZIP into `PortableApps\ExcalidrawPortable` (if using PortableApps Platform) or another writable directory.
12. Double-click `ExcalidrawPortable.exe` to open the website app. Refresh PortableApps Menu to see it listed.
13. After using the app, check that session information appears under `Data\WebView` and window state under `Data\State`.

### New repository (if preferred)

Create a new empty repository in GitHub Desktop named `Pake-Portable-Website-Builder`. Choose public/private visibility intentionally, extract this ZIP inside the local repo folder, commit and **Publish repository**. Private repositories use private GitHub Releases; public repositories use public releases. Enable Actions and run the same workflow as above.

**Warning for public releases:** The website URL, compiled app and build parameters are present in public build/release metadata. Do not put secret access tokens or credentials in website URLs.

## Updating a generated portable app without losing data

Always **close** the program completely before updating. Copy the **entire existing `Data` folder** to a safe backup, then update only the executable and App/Other metadata from the newer ZIP. Do not overwrite, delete, reset or reseed `Data`. The same app name produces the same portable folder name; changing app name creates a separate app. Test upgrades and rollback manually because WebView2 storage may be incompatible between old/new runtime versions.

## Current limitations and truthfulness of tests

- Works only for Windows x64 (MSVC). Microsoft Edge **WebView2 Runtime** must be installed/available on the PC.
- A website may reject sign-in in embedded webviews; Pake cannot override website provider authentication policies.
- Source-specific patches redirect Pake's WebView2 storage and Tauri state. Broad dynamic monitoring of unknown AppData/ProgramData traces and external crash recovery is **not implemented or claimed**. `TraceGuard/` is reserved. **Never indiscriminately delete shared host data.** See `docs/PORTABILITY.md`.
- Website downloads intentionally use the normal Windows Downloads folder. Windows OS telemetry, caches, recent-file records and program integrations may also create traces.
- ZIP contains PortableApps Menu metadata, but is **not** an officially certified PortableApps.com package or `.paf.exe` installer.
- GitHub Actions performs static/package verification; unattended Windows runners do **not** prove that website GUI features, logins, relocation and host trace cleanup work. Follow the manual checks in `docs/TESTING.md`.
- Shared Publisher refuses to replace an existing different managed release. The tag includes URL/config fingerprint, Pake version, app version and builder r6.
- `publish:false` produces no downloadable asset (because this project intentionally avoids intermediate Actions artifact storage). Leave it `true` for normal use.
- Standard Windows hosted runners are free/unlimited for public repositories under GitHub's current standard-runner policy; private repositories consume GitHub Actions minutes/storage and caches. Rust cache may be turned off with workflow input `use_rust_cache:false`.
- Pake is GPL-3.0-or-later. Review both its upstream license, included license exception and website icons/trademarks before distributing resulting binaries. The kit retains the source patch and upstream commit for GPL provenance; distributing compiled GPL code may require more source-availability steps. See `docs/PORTABILITY.md`.


**Tauri version:** Pake V3.18.0 uses Tauri 2.10.2 in Cargo.lock. The
source-level portable profile API requires Tauri **2.12.0** (released
September 2026). This builder updates the temporary clone's tauri Rust
dependency and checks the resulting lockfile. A dependency incompatibility
fails the build rather than publishing a profile-writing executable. This
specific Rust dependency upgrade has not yet been verified by a full Windows
build. Reference: https://tauri.app/release/tauri/v2.12.0/

## r6 fix: Windows build prerequisite (from uploaded r5 logs)

The r5 GitHub Actions run stopped in `scripts/ensure-wix.ps1` before website compilation, reporting `WiX 3.11 light.exe missing after installation`. The earlier helper silently relied on a system-wide installer and a hardcoded `Program Files (x86)` folder.

r6 instead downloads the official WiX 3.11.2 **portable command-line ZIP** from the pinned `wix3112rtm` release, checks its fixed SHA-256 against independently published hashes, extracts into ephemeral `work/tools/wix311`, and exposes `candle.exe` / `light.exe` to the build process. No WiX system installation, elevation, or third-party installer engine is involved. Pake may still create a temporary MSI internally, but only the compiled website EXE is staged into the published portable ZIP. The shared publisher remains at `v1.1.1`.

The r5 failure is fixed by source changes, but no actual Windows compilation of r6 has been performed in this environment. If the next run stops after this step, supply its new log for a separate diagnosis.

## What changed from r4

r4 packaged the Pake CLI with `PakePortable.exe` as a console launcher. r6 runs the actual **website-to-application** build in GitHub Actions, patches the generated Tauri application to use portable Data directories, keeps the real compiled website GUI EXE, creates a native ZIP and publishes it through the existing shared publisher. This is a new build pipeline, not an upgrade to r4's CLI tool.
