# Pake Native Portable Builder changelog

## r2 — PowerShell parse fix

- Fix invalid variable interpolation after `$tag` in `scripts/check-existing.ps1`, observed in an actual Windows GitHub Actions run.
- Add a source regression test detecting unbraced variable names immediately followed by a colon, excluding PowerShell scoped variables such as `$env:`.
- Parse the upstream `pnpm@x.y.z` package-manager version with an explicit regex match object instead of an implicit `$Matches` automatic variable.
- Bump the generated ZIP name, publisher-managed release tag, display name, and provenance from r1 to r2, preserving the immutable r1 release namespace.
- Preserve existing upstream fetch, runtime launcher, portable Data, TraceGuard, and shared publisher behavior unchanged.

**Test boundary:** Local Python unit tests and ZIP structural checks are not substitutes for a GitHub-hosted Windows build. No r2 executable or Windows package has been compiled here.
