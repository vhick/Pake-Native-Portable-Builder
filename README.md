# Pake Native Portable Builder Kit (r4)

**Upstream:** https://github.com/tw93/Pake  
**Output:** independently extractable `PakePortable_<upstream-version>_Native-r4_win-x64.zip`  
**Selected mode:** `NATIVE` (not `PORTABLEAPPS` or `BOTH`)  
**Publishing:** `vhick/portable-release-publisher@v1.1.1`

## Important project boundary

Pake is **a Node.js CLI that compiles web pages into separate Tauri desktop apps**, not itself a typical Windows WebView2 desktop application. This kit packages the **Pake CLI**; it does **not** claim that the desktop apps Pake generates are portable. Those generated applications have their own WebView2 and Tauri profiles and require separate application-specific work. You have not specified a webpage to compile.

The ZIP contains a genuine compiled `.exe` front end to the actual official CLI, bundled Node 22 runtime and upstream-declared exact pnpm version. `PakePortable.exe --help` and `--version` need no global Pake/Node install. **Building a web app needs a working host Rust toolchain (>=1.85) plus MSVC C++ build tools**, as specified by Pake. These can write compiler caches outside the ZIP; bundling a complete Windows build toolchain would substantially enlarge the package and is **not** implemented. Do not claim fully isolated native application builds on arbitrary clean PCs.

## Previous r3 fix (upstream stable-release enumeration)

The r2 GitHub Actions run (`logs_113419926172.zip`) passed PowerShell parsing but failed to select a stable upstream release. r3 corrected PowerShell's handling of a JSON release array, added a stable-release-selection self-test, and subsequently selected the new upstream `V3.18.0` successfully in the Windows workflow. The earlier PowerShell interpolation fix from r2 is retained.

## r4 fix (release precheck falsely failed after expected 404)

The r3 GitHub Actions log (`logs_113427238545.zip`) now correctly resolves stable Pake `V3.18.0` and its commit. It then prints `No prior release portable-v3.18.0-native-r3; build required.` but fails with exit code 1. This is caused by GitHub Actions' built-in PowerShell shell wrapper: it evaluates `$LASTEXITCODE` left by the GitHub CLI's expected missing-release response.

r4 classifies the response explicitly. For an expected release-not-found result, the script proceeds with `skip=false` and clears the handled native exit code. For a real authentication or API error, the build still fails loudly. A new Windows self-test validates the expected 404 / existing managed release / 403 cases before any expensive build starts. The builder is not yet Windows-build verified. The native launcher, TraceGuard, and pinned shared publisher are unchanged.

## Run it from GitHub Desktop (beginner guide)

1. On github.com select **New repository** and name it `Pake-Native-Portable-Builder`. Choose **Public** or **Private**. Do **not** check `Add a README` if you want a clean empty repository. Create it.
2. Open GitHub Desktop: **File > Clone repository**, select this new repository, choose a local folder and click **Clone**.
3. Extract this kit ZIP. **Copy the kit's contents** (including the hidden `.github` folder) directly into your cloned repository. Do not add an extra nesting folder.
4. In GitHub Desktop, review the files, type `Fix Pake release precheck exit code r4`, click **Commit to main**, then **Push origin**.
5. On github.com open your new repo > **Settings > Actions > General**. Allow use of GitHub Actions; under **Workflow permissions**, give read/write permissions if the publisher cannot create releases (the workflow itself requests `contents: write`). For a private repository, ensure allowed action policies permit the two shared public actions.
6. Open **Actions > Build Pake Native Portable > Run workflow**. Leave `upstream_tag` blank for the latest stable version. Set `publish` to true to create a release; false validates without publishing.
7. On a successful run, open the repository **Releases** page and download the `PakePortable_*_Native-r4_win-x64.zip` and `SHA256SUMS.txt`.
8. Extract ZIP to a writable folder, e.g. `D:\PortableTools\PakePortable\` (avoid nesting `PakePortable\PakePortable\`). Double-click `PakePortable.exe --help` in Terminal, or use `PakePortable.exe https://example.com --name Example` in a terminal opened in that folder.
9. Built web-app installers will go to `PakePortable\Data\Output`. The first web-app build needs Rust + Visual Studio C++ build tools. Pake itself may download dependencies.
10. Upgrade by extracting the new ZIP and replacing **only** `PakePortable.exe`, `App`, `SOURCE.json`, `LICENSE-UPSTREAM.txt` and `LICENSE-EXCEPTION.txt`. **Never overwrite/delete `Data`**. Keep an offline backup first. Do not downgrade running compiled web-apps' own profiles based on this ZIP.
11. TraceGuard's `Data\TraceGuard\manifest.json` records directories **including empty ones**. `Data\TraceGuard\Recovered\` holds files captured from explicitly allowlisted exclusive external paths. By default the outside-host allowlist is empty because no fixed, exclusive Pake CLI host folder has been proven.

There is **no shared Package Builder** invocation in this mode. The pinned packager's installer is required for `PORTABLEAPPS`/`BOTH`, not `NATIVE`; adding a packaging-only workflow here would be unnecessary. If you later select those modes, it requires a separate audited builder revision and a dedicated staged PortableApps directory.

## Usage

Run from a Windows terminal:

```powershell
.\PakePortable.exe --help
.\PakePortable.exe --version
.\PakePortable.exe https://example.com --name Example
.\PakePortable.exe --traceguard-selftest
```

Pake uses `Data\Output` as the process working directory; use absolute paths for local HTML or JSON config files outside it. Its `--json` option remains available. The launcher forwards every argument unchanged, returns the CLI exit code, and waits for the Node process to finish. It has a regular Windows console PE, not an EXE-renamed CMD file. The ZIP is not a PortableApps Menu package, by design.

## Data safety and TraceGuard

The launcher redirects `HOME`, `APPDATA`, `LOCALAPPDATA`, `TEMP`, `TMP`, XDG, npm cache, pnpm cache and Pake's explicitly supported `CARGO_TARGET_DIR` to `Data`. Pake's Rust build target is thus kept in `Data\BuildCache\target` instead of the replaceable `App` directory. The default setup **does not change `USERPROFILE`, `RUSTUP_HOME`, or `CARGO_HOME`**: on existing Windows systems, pretending those can be overridden without changing installed Rust toolchains can stop Pake compiling apps. External Rust/Cargo toolchain state is an explicitly documented limitation.

TraceGuard creates a crash marker before launching Node and updates a manifest after exit. An interrupted run is detected and the portable Data tree is rescanned on next launch. Files and empty folders under Data are never moved out or deleted by TraceGuard. A separate **optional** `Data\TraceGuard\owned-roots.txt` allows only previously absent exclusive `PakePortable-*` absolute host roots to be copied to `Data\TraceGuard\Recovered\` and cleaned after successful hash-verified copies. Do not add `%APPDATA%`, `%LOCALAPPDATA%`, `%PROGRAMDATA%`, `PSResourceGet`, `PackageManagement`, or other shared paths. Pre-existing roots are protected and skipped. There is no evidence that default Pake builds require external roots, so this list is empty by default.

**Limitations:** No registry virtualisation, no OS-level whole-process-tree filesystem tracing, no known automatic capture of arbitrary unknown host writes, no Windows service interception. Do not interpret a `Data` snapshot as proof that every spawned process wrote nothing to the host. Child compiler processes may remain after Node exits in exceptional cases. Those behaviors require evidence and Windows tracing before safely implementing a stronger solution.

## CI validation / build integrity

- GitHub API chooses the highest stable `Vx.y.z` release; prereleases and drafts excluded. The tag ref is peeled to a 40-character commit SHA, then `git rev-parse HEAD` must match exactly.
- Upstream Node dependencies are installed using its locked pnpm lockfile; `pnpm run cli:build` produces official upstream `dist/cli.js`; `npm pack` from that checkout produces the local packaged CLI. Production module dependencies are then installed normally to avoid dangling pnpm symlinks in ZIPs.
- Windows CI compiles the `PakePortable.exe` launcher from readable C# and actually invokes `--help`, `--version`, and `--traceguard-selftest`, including empty nested folder preservation.
- CI independently checks the PE header, ZIP structure and key contents; the shared release publisher performs a `dry-run` then publishes only the validated ZIP with SHA256SUMS.
- The ZIP is compiled **in GitHub Actions**, not provided as a precompiled artifact in this source kit. No installer is generated and no Actions artifact storage is used.
- This kit's source layout and YAML were statically tested in the authoring environment, **not executed on a Windows GitHub-hosted runner yet**. Running the CI build provides evidence of compatibility. See `docs/AUDIT.md` and `docs/TESTING.md`.

## Troubleshooting

- **PakePortable.exe says Rust or Visual Studio C++ build tools missing:** install official stable Rust (`rustup`, `stable-x86_64-pc-windows-msvc`) and Visual Studio Build Tools with Desktop development with C++. Then reopen your terminal.
- **Build works but new desktop app leaves WebView2 folders:** those are created by the **generated Tauri app**, not the Pake CLI builder. It needs a separate application-specific portable launcher and storage override.
- **Permission or data issues:** extract into a writable non-protected directory; do not run it under Program Files. Check `Data\TraceGuard` and `Data\Profile`.
- **Rebuild produces an existing release-tag mismatch:** bump the builder revision consistently in filename and release tag (e.g. native-r4) rather than overwrite an immutable release.
- **Publisher cannot find ZIP:** inspect the `Validate executable, runtime and independent ZIP` step. The publisher expects `release/*.zip`, not `*.exe`.
- **Node native module errors:** Pake CLI dependencies may have changed; inspect the upstream `package.json` and pinned package manager version before increasing the builder revision.

## Licenses

Pake declares `GPL-3.0-or-later` and includes `LICENSE-EXCEPTION`. Its official license and exception are copied into every package. This builder's own source is provided under MIT; it makes no claim to own Pake, Node or third-party Rust/compiler binaries. Check third-party dependencies' notices before redistributing a compiled web application.
