# Automatic Tauri and Windows COM dependency alignment — Pake r10

## Why r9 broke

On November 14, 2026 the uploaded Actions log shows `@tauri-apps/cli = ^2.12.4`
but the old builder expected `^2.10.0` literally. It stopped while preparing
JavaScript packages, before compiling the web app. `^2.12.4` is not an error;
that literal comparison was too restrictive.

## Version selection policy

- **Rust Tauri** — read exact `tauri` crate in upstream Cargo.lock. Accept
  stable 2.x if >=2.12.0. If older, upgrade the disposable copy to the
  minimum Tauri 2.12.0 needed by `appDirectoriesOverride`.
- **Rust Wry and WebView2** — query `cargo metadata` with the Windows x64
  target, follow the actual Tauri -> Wry -> WebView2 COM -> Windows Core
  resolution chain, and set the app's direct WebView2 and Windows COM deps
  to that family. Preserve unrelated `windows-sys` and existing features.
- **Tauri JS** — keep the installed upstream CLI/API exact version if its
  major and minor match Rust. Otherwise query the official npm registry and
  choose the highest stable patch within *the same* major.minor. Pin exact
  versions in the temporary checkout, and regenerate the pnpm lockfile.
- **Validation** — validate Cargo.lock, direct manifest requirements, actual
  resolved Pake dependency edges, installed JavaScript package versions,
  portable source patch markers, genuine compiled EXE and independent ZIP.
- **Provenance** — package `Other/Source/RESOLVED-DEPENDENCIES.json` with the
  resulting graph and installed JavaScript versions for troubleshooting.

## Safety limits

Do not automatically follow a Tauri 3.x release. Do not assume that the
highest available major/minor will work with the old source. Do not silently
continue if Cargo's Wry graph is ambiguous, a package has prerelease status,
the upstream source changes its storage code, or an expected dependency is
removed/renamed. Revisions to the source patch may still be necessary.

The upgrade is applied to `work/upstream` only, never the developer's GitHub
repository, user installation, or existing `Data`. Release tags are namespaced
with r10 so that prior working r9 releases remain intact. No MSI is published.

## Validation evidence

Offline regression fixtures include old Pake 2.10 Rust and newer 2.12 CLI,
a hypothetical future 2.13 Rust/Wry graph, UTF-8 Cargo JSON, mismatched
WebView2 dependency edges, missing package versions and Tauri 3 rejection.
Fixtures are not proof of a Windows compilation or WebView2 runtime test.

Sources:

- https://v2.tauri.app/develop/updating-dependencies/
- https://v2.tauri.app/release/tauri/v2.12.0/
- https://doc.rust-lang.org/cargo/commands/cargo-metadata.html
- https://github.com/tw93/Pake
