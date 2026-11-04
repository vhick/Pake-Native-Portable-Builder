# Pake Native Portable Builder changelog

## r3 — Stable GitHub release enumeration fix

- Fix the actual Windows CI failure at `scripts/resolve-upstream.ps1:7`: `@(Invoke-RestMethod ...)` could nest GitHub release results, causing the stable release filter to find zero releases even though upstream has `V3.17.6`.
- Explicitly verify and iterate the REST release array; select the greatest stable semantic version while rejecting drafts, prereleases and suffixes.
- Add `-SelfTest` with a mocked set of releases; run it in the Windows workflow before any GitHub API requests.
- Improve diagnostics for unexpected release API responses without guessing a source version.
- Advance ZIP filename, provenance and immutable managed release tag to `native-r3`.
- Keep launcher, TraceGuard and shared `portable-release-publisher@v1.1.1` code unchanged.

**Test boundary:** Local Python source tests and ZIP integrity checks were executed. Windows CI tests, compilation and application-runtime acceptance are pending.



## r2 — PowerShell parse fix

- Fix invalid variable interpolation after `$tag` in `scripts/check-existing.ps1`, observed in an actual Windows GitHub Actions run.
- Add a source regression test detecting unbraced variable names immediately followed by a colon, excluding PowerShell scoped variables such as `$env:`.
- Parse the upstream `pnpm@x.y.z` package-manager version with an explicit regex match object instead of an implicit `$Matches` automatic variable.
- Bump the generated ZIP name, publisher-managed release tag, display name, and provenance from r1 to r2, preserving the immutable r1 release namespace.
- Preserve existing upstream fetch, runtime launcher, portable Data, TraceGuard, and shared publisher behavior unchanged.

**Test boundary:** Local Python unit tests and ZIP structural checks are not substitutes for a GitHub-hosted Windows build. No r2 executable or Windows package has been compiled here.
