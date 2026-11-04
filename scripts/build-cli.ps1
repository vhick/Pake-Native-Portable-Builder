$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$up=(Resolve-Path work/upstream).Path
$root=(Resolve-Path .).Path
$stage=Join-Path $root 'work/stage/PakePortable'
New-Item -ItemType Directory -Force -Path $stage, (Join-Path $stage 'App/Node'), (Join-Path $stage 'App/Cli'), (Join-Path $stage 'App/Tools'), (Join-Path $stage 'Data') | Out-Null
$pkg=Get-Content (Join-Path $up 'package.json') -Raw | ConvertFrom-Json
$packageManagerMatch = [regex]::Match([string]$pkg.packageManager, '^pnpm@(\d+\.\d+\.\d+)$')
if (-not $packageManagerMatch.Success) {
  throw "Unsupported upstream package manager '$($pkg.packageManager)'; this builder requires an exact pnpm semver"
}
$pnpmVersion = $packageManagerMatch.Groups[1].Value
# npm CLI checks registry integrity; the upstream pnpm lockfile is enforced on the source build.
npm install --global "pnpm@$pnpmVersion" --no-audit --no-fund
if($LASTEXITCODE -ne 0){throw 'Cannot install pinned pnpm'}
Push-Location $up
try {
  pnpm install --frozen-lockfile
  if($LASTEXITCODE -ne 0){throw 'Upstream lockfile install failed'}
  pnpm run cli:build
  if($LASTEXITCODE -ne 0){throw 'Official upstream CLI compilation failed'}
  if(-not (Test-Path 'dist/cli.js')){throw 'Missing compiled upstream CLI'}
  # npm package is built from actual release source. `npm pack` includes src-tauri templates.
  npm pack --ignore-scripts --pack-destination (Join-Path $root 'work')
  if($LASTEXITCODE -ne 0){throw 'Creating upstream npm package failed'}
} finally {Pop-Location}
$tar=Join-Path $root ("work/pake-cli-$env:PAKE_VERSION.tgz")
if(-not (Test-Path $tar)){throw "Expected npm package missing: $tar"}
$cliDest=Join-Path $stage 'App/Cli'
# A normal npm dependency tree (rather than pnpm junctions) survives ZIP relocation.
npm install --prefix $cliDest --omit=dev --no-audit --no-fund --no-save $tar
if($LASTEXITCODE -ne 0){throw 'Production module installation failed'}
$entry=Join-Path $cliDest 'node_modules/pake-cli/dist/cli.js'
if(-not (Test-Path $entry)){throw 'Staged CLI entry missing'}
# The runner's verified setup-node toolcache provides node.exe; do not rely on host Node after extraction.
$node=(Get-Command node.exe -ErrorAction Stop).Source
Copy-Item -LiteralPath $node -Destination (Join-Path $stage 'App/Node/node.exe')
# Pake subprocesses call pnpm. Bundle the same pinned version locally, not a global install requirement.
$nodeExe=Join-Path $stage 'App/Node/node.exe'
$tools=Join-Path $stage 'App/Tools'
& $nodeExe (Join-Path (Split-Path $node -Parent) 'node_modules/npm/bin/npm-cli.js') install --global --prefix $tools "pnpm@$pnpmVersion" --no-audit --no-fund
if($LASTEXITCODE -ne 0){throw 'Cannot stage local pnpm'}
# npm itself is used by some Pake build paths; carry the official npm distribution from setup-node.
Copy-Item -Path (Join-Path (Split-Path $node -Parent) 'node_modules/npm') -Destination (Join-Path $stage 'App/Node/npm') -Recurse -Force
@'
@echo off
"%~dp0node.exe" "%~dp0npm\bin\npm-cli.js" %*
'@ | Set-Content -Path (Join-Path $stage 'App/Node/npm.cmd') -Encoding ascii
# pnpm's installed Windows .cmd shim references node.exe via PATH, set by launcher.
# Stage exact upstream source license and exception for redistribution notice.
Copy-Item -LiteralPath (Join-Path $up 'LICENSE') -Destination (Join-Path $stage 'LICENSE-UPSTREAM.txt')
Copy-Item -LiteralPath (Join-Path $up 'LICENSE-EXCEPTION') -Destination (Join-Path $stage 'LICENSE-EXCEPTION.txt')
$provenance=[ordered]@{ upstream='https://github.com/tw93/Pake'; tag=$env:PAKE_TAG; version=$env:PAKE_VERSION; commit=$env:PAKE_COMMIT; builder='r4'; node=( & $nodeExe --version); pnpm=$pnpmVersion; source='upstream git tag checked against GitHub release API' }
$provenance|ConvertTo-Json -Depth 4|Set-Content (Join-Path $stage 'SOURCE.json') -Encoding utf8
New-Item -ItemType Directory -Force -Path (Join-Path $stage 'Data/Output') | Out-Null
Write-Host "Production CLI staged from $tar"
