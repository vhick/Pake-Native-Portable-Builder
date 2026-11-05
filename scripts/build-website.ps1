$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path .).Path
$upstream = (Resolve-Path 'work/upstream').Path
$plan = Get-Content -LiteralPath 'work/plan.json' -Raw -Encoding utf8 | ConvertFrom-Json
$package = Get-Content -LiteralPath (Join-Path $upstream 'package.json') -Raw -Encoding utf8 | ConvertFrom-Json
if ($package.name -ne 'pake-cli' -or $package.version -ne $plan.pakeVersion) { throw 'Upstream package/version mismatch' }
if ([version]$plan.pakeVersion -lt [version]'3.18.0') { throw 'The portable source patch is verified for Pake V3.18.0 or later only.' }
$pnpm = [regex]::Match([string]$package.packageManager, '^pnpm@(\d+\.\d+\.\d+)$')
if (-not $pnpm.Success) { throw 'Upstream no longer declares an exact pnpm package manager version' }
Write-Host "Install upstream-selected pnpm $($pnpm.Groups[1].Value)"
& npm install --global ("pnpm@" + $pnpm.Groups[1].Value) --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'Pinned pnpm installation failed' }
Push-Location $upstream
try {
    & pnpm install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { throw 'Upstream dependency installation failed' }
    # Pake 3.18.0 installs @tauri-apps/api 2.10.1 and CLI 2.10.0.
    # The Rust 2.12.0 portability patch requires matching JS packages.
    # Change only this disposable fetched source, then regenerate pnpm-lock.yaml
    # using pnpm itself instead of editing the lockfile by hand.
    & python (Join-Path $root 'scripts/upgrade-tauri.py') $upstream --prepare-js
    if ($LASTEXITCODE -ne 0) { throw 'Cannot align upstream Tauri JavaScript package versions' }
    & pnpm install --no-frozen-lockfile
    if ($LASTEXITCODE -ne 0) { throw 'Installing aligned Tauri JavaScript packages failed' }
    & pnpm install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { throw 'Regenerated Tauri JavaScript dependency lockfile is invalid' }
    & python (Join-Path $root 'scripts/upgrade-tauri.py') $upstream --verify-js
    if ($LASTEXITCODE -ne 0) { throw 'Installed Tauri JS versions do not match Rust 2.12.x; refusing build' }
    & pnpm run cli:build
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath 'dist/cli.js')) { throw 'Building Pake CLI failed' }
    # Tauri's source-level appDirectoriesOverride API was introduced in 2.12.0.
    # Pake V3.18.0 locks Tauri 2.10.2. Upgrade only the ephemeral Rust
    # dependency graph before building or fail instead of publishing host-writing apps.
    & python (Join-Path $root 'scripts/upgrade-tauri.py') $upstream
    if ($LASTEXITCODE -ne 0) { throw 'Could not safely prepare Tauri portable dependency requirements' }
    Push-Location (Join-Path $upstream 'src-tauri')
    try {
        & cargo update -p tauri --precise 2.12.0
        if ($LASTEXITCODE -ne 0) { throw 'Tauri 2.12 portable API upgrade failed; no app was published' }
    } finally { Pop-Location }
    & python (Join-Path $root 'scripts/upgrade-tauri.py') $upstream --verify
    if ($LASTEXITCODE -ne 0) { throw 'Rust lockfile does not contain required Tauri 2.12.0' }
    # Guard against Pake's direct WebView2 COM bindings being compiled against
    # windows-core 0.61 while Tauri 2.12's Wry uses windows-core 0.62.
    & python (Join-Path $root 'scripts/upgrade-tauri.py') $upstream --verify-resolved-windows
    if ($LASTEXITCODE -ne 0) { throw 'Pake direct WebView2 COM dependency graph is incompatible with Tauri 2.12' }
    # Print the direct Rust crate tree for future GitHub Actions diagnostics.
    Push-Location (Join-Path $upstream 'src-tauri')
    try {
        & cargo tree --locked --target x86_64-pc-windows-msvc --depth 1 -p pake
        if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect direct Rust dependency tree' }
    } finally { Pop-Location }
    # Patch only the ephemeral fetched source tree; not the original GitHub repository.
    & python (Join-Path $root 'scripts/patch-portability.py') $upstream
    if ($LASTEXITCODE -ne 0) { throw 'Portable source patch failed (upstream compatibility guard)' }
    $helpText = (& node dist/cli.js --help 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) { throw 'Pake CLI --help failed' }
    if ($helpText -notmatch '--keep-binary') { throw 'Upstream CLI has removed --keep-binary; refusing to publish an installer' }
    $cliArgs = @([string]$plan.url, '--name', [string]$plan.name,
                 '--app-version', [string]$plan.version,
                 '--width', [string]$plan.width,
                 '--height', [string]$plan.height,
                 '--keep-binary')
    if (-not [string]::IsNullOrWhiteSpace([string]$plan.icon)) { $cliArgs += @('--icon', [string]$plan.icon) }
    if ($plan.options.new_window) { $cliArgs += '--new-window' }
    if ($plan.options.fullscreen) { $cliArgs += '--fullscreen' }
    if ($plan.options.hide_window_decorations) { $cliArgs += '--hide-window-decorations' }
    if ($plan.options.no_restore_last_url) { $cliArgs += '--no-restore-last-url' }
    Write-Host 'Compiling generated Windows app from Pake with --keep-binary.'
    Write-Host 'The source-level portability patch runs before Rust compilation.'
    Write-Host 'An intermediate MSI may be generated by upstream Pake but is never published.'
    & node dist/cli.js @cliArgs
    if ($LASTEXITCODE -ne 0) { throw 'Pake generated application build failed' }
    $binaryPath = Join-Path $upstream ($plan.name + '.exe')
    if (-not (Test-Path -LiteralPath $binaryPath -PathType Leaf)) {
        $found = @(Get-ChildItem -LiteralPath $upstream -Filter '*.exe' -File)
        throw "Expected actual Pake --keep-binary app at $binaryPath. Found root executables: $($found.Name -join ', ')"
    }
    Write-Host "Real compiled web application found: $binaryPath"
    # Keep a deterministic copy for staging, never use the installer as input.
    New-Item -ItemType Directory -Force -Path (Join-Path $root 'work/generated') | Out-Null
    Copy-Item -LiteralPath $binaryPath -Destination (Join-Path $root 'work/generated/website.exe') -Force
    $siblingDll = Join-Path $upstream 'WebView2Loader.dll'
    if (Test-Path -LiteralPath $siblingDll) {
        Copy-Item -LiteralPath $siblingDll -Destination (Join-Path $root 'work/generated/WebView2Loader.dll') -Force
    }
} finally {
    Pop-Location
}
Write-Host 'Pake generated application compilation completed.'
