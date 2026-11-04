# Source-based audit: tw93/Pake (inspected stable release V3.17.5)

Sources inspected on 2026-11-04:
- https://github.com/tw93/Pake/releases/tag/V3.17.5 (release tag, short commit `35bac8f`)
- https://raw.githubusercontent.com/tw93/Pake/V3.17.5/package.json (Node >=20.9, pnpm 10.26.2, CLI entry `dist/cli.js`, dependencies, GPL-3.0-or-later)
- https://raw.githubusercontent.com/tw93/Pake/V3.17.5/rollup.config.js (source entry `bin/cli.ts`, production output `dist/cli.js`)
- https://raw.githubusercontent.com/tw93/Pake/V3.17.5/docs/cli-usage.md (Rust >=1.85, MSVC C++ toolchain, current-directory output and CLI behavior)
- https://raw.githubusercontent.com/tw93/Pake/V3.17.5/src-tauri/tauri.conf.json (Tauri app template; NOT the CLI's own runtime)
- https://raw.githubusercontent.com/tw93/Pake/V3.17.5/bin/utils/build-workspace.ts (temporary `pake-build-*` workspace from `os.tmpdir`; honors `CARGO_TARGET_DIR` and sets build cache lock)
- https://raw.githubusercontent.com/tw93/Pake/V3.17.5/bin/utils/dir.ts (CLI installed package directory and dynamic workspace)
- https://raw.githubusercontent.com/tw93/Pake/V3.17.5/bin/builders/WinBuilder.ts (Windows MSI output and target cache lookup)

| Item | Source-based finding | Strategy | Limitation |
| --- | --- | --- | --- |
| Pake CLI | Node.js entry `dist/cli.js` from TypeScript, built by Rollup | Compile upstream CLI from verified stable source; stage packaged npm distribution | Package native modules vary with upstream release |
| Node CLI runtime | Requires Node >=20.9 | Bundle Node 22 x64 from setup-node toolcache | Only Windows x64 targeted |
| pnpm | packageManager pinned 10.26.2 in inspected release | Bundle exact upstream-declared pnpm semver | Build aborts for unsupported package-manager formats |
| Web-app compilation | Rust/Tauri toolchain, host C++ build tools | Preserve host Rust discovery and document installation | Not a fully self-contained portable compiler |
| Pake's PWD output | CLI guide says output in current working directory | Launcher starts in `Data\Output` | CLI arguments with relative paths resolve there |
| Pake Rust build target | `build-workspace.ts` reads `CARGO_TARGET_DIR`, otherwise defaults to `<package>/src-tauri/target` | Set `CARGO_TARGET_DIR=Data\BuildCache\target` **before** CLI starts; WinBuilder respects it | Large cache may grow quickly |
| Pake temporary workspace | `build-workspace.ts` creates `pake-build-*` beneath `os.tmpdir()` | Redirect `TMP`/`TEMP` to `Data\Temp` before launch | Abnormal child-process failure may leave temporary workspace |
| npm/pnpm cache | Node package managers conventionally use user cache directories | Override npm config cache, pnpm home and HOME inside `Data` | Tools invoked outside launch env may differ |
| APPDATA/LOCALAPPDATA | Node and child subprocesses can use Windows profile paths | Override inherited env variables to `Data\Profile` | Tools using Win32 known-folder API may ignore env vars |
| `%USERPROFILE%`, `.cargo`, `.rustup` | Rust discovery may depend on real Windows user profile | Do not redirect by default | Host Rust/Cargo caches and state can persist |
| Registry | No confirmed application-specific registry keys from inspected CLI/template evidence | No blind registry cleanup | Windows WebView2/compiler/system integrations are not virtualized |
| WebView2 | Tauri **generated apps** use host webview runtime and per-app storage | Out of scope for CLI-portable mode | Separate generated-app portability needed |
| ProgramData | No verified exclusive Pake CLI ProgramData folder | No destructive cleanup | Unknown writes require Windows trace evidence |
| Empty folders | CLI or tools can create empty nested Data directories | Recursive Data manifest and optional exclusive-root recovery copy them | Arbitrary external host roots are intentionally not captured |
| Upstream licensing | GPL-3.0-or-later and license exception | Include upstream license files | Web-app content rights vary by target website |

## Pinned shared actions: verified contracts

Package Builder v1.0.0: https://raw.githubusercontent.com/vhick/Portable-Package-Builder/v1.0.0/action.yml
  - `source-dir`, `output-dir`, `engine`, `running-exe`, `timeout-seconds`, `package-revision`, `official-tool-url`, `official-tool-sha256`
  - outputs `installer-file`, `installer-sha256`, `app-id`, `app-version`
  - only for PortableApps staging; not invoked by `NATIVE` mode.

Publisher v1.1.1: https://raw.githubusercontent.com/vhick/portable-release-publisher/v1.1.1/action.yml
  - `files`, `tag`, `release-title`, `tag-prefix`, `keep-releases`, `prune`, `dry-run`.
  - ZIP or `.paf.exe` only; SHA256SUMS, idempotent release verification, pruning off by default.

## Acceptance evidence vs untested scenarios

**Implemented in kit:** Stable release resolver, source commit verification, source CLI compilation, local production dependency install, compiled launcher source, Data profile redirection, journal, empty-directory manifest, opt-in protected external-root recovery, ZIP validation, shared publisher dry-run and publish steps.

**Not performed during kit authoring:** Windows compilation/execution, real `pake https://...` Rust/Tauri web-app build, moving drives, portable generated app behavior, Windows Registry trace, antivirus scan, upgrade/rollback with real user data. CI smoke tests will execute when workflow is run.

## Exception to broad original spec

User selected **NATIVE** not **PORTABLEAPPS**. There is no PortableApps metadata/menu/installer and no shared packager invocation. This avoids inventing a PortableApps-style application GUI out of the Pake CLI and avoids duplicating the shared packager. Dynamic external file attribution is limited to exclusive, opt-in roots; indiscriminately collecting arbitrary profile changes would risk data corruption.

Pinned action release-tag commit identities verified from release pages:
- `vhick/Portable-Package-Builder@v1.0.0` → `0112c35580e83b37eb8757ebcb949274e1631a04`.
- `vhick/portable-release-publisher@v1.1.1` → `cb64f86ac2d8c67506db5832de07f9ff58cbeaeb`.
These SHA values were inspected in GitHub release commit links, while workflow integration stays on the exact user-requested tags.
