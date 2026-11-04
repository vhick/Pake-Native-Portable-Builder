$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Pake's --keep-binary currently produces a temporary Windows MSI in addition
# to the actual app EXE. This kit publishes ONLY the app's portable ZIP.
# WiX is a build-time dependency only. Do not install it machine-wide.
# Verified official WiX v3.11.2 binaries: https://github.com/wixtoolset/wix3/releases/tag/wix3112rtm
# SHA-256 independently recorded in WireGuard and Google Fuchsia build sources:
# https://git.zx2c4.com/wireguard-windows/tree/installer/build.bat?h=v0.5.3
# https://fuchsia.googlesource.com/third_party/cmake/+/1aa95e1a3b0f29ca35554b1bb003f714c315e047/Utilities/Release/win/x86/deps/Dockerfile

$expected = '2C1888D5D1DBA377FC7FA14444CF556963747FF9A0A289A3599CF09DA03B9E2E'
$url = 'https://github.com/wixtoolset/wix3/releases/download/wix3112rtm/wix311-binaries.zip'
$tools = Join-Path (Resolve-Path '.').Path 'work/tools'
$zipPath = Join-Path $tools 'wix311-binaries.zip'
$bin = Join-Path $tools 'wix311'
$light = Join-Path $bin 'light.exe'
$candle = Join-Path $bin 'candle.exe'

New-Item -ItemType Directory -Path $tools -Force | Out-Null
# Fetch a fixed release archive and check the known hash even on cache hits.
if (-not (Test-Path -LiteralPath $zipPath -PathType Leaf)) {
    Write-Host 'Downloading official WiX 3.11.2 command-line binaries (no installer).'
    Invoke-WebRequest -Uri $url -OutFile $zipPath -MaximumRedirection 8
}
$actual = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash
if ($actual -cne $expected) {
    Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
    throw "WiX binaries SHA-256 mismatch: $actual. Refusing to extract an unverified dependency."
}

# Security: reject unsafe ZIP paths even though the archive is hash-pinned.
Add-Type -AssemblyName System.IO.Compression.ZipFile
$archive = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    foreach ($entry in $archive.Entries) {
        $name = $entry.FullName.Replace('\','/')
        if ($name.StartsWith('/') -or $name -match '(^|/)\.\.(/|$)' -or $name -match '^[A-Za-z]:') {
            throw "Unsafe WiX ZIP entry: $name"
        }
    }
} finally { $archive.Dispose() }

if (-not (Test-Path -LiteralPath $light -PathType Leaf) -or
    -not (Test-Path -LiteralPath $candle -PathType Leaf)) {
    New-Item -ItemType Directory -Path $bin -Force | Out-Null
    Expand-Archive -LiteralPath $zipPath -DestinationPath $bin -Force
}
foreach ($tool in @($light, $candle)) {
    if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) {
        throw "WiX 3.11.2 archive was verified but expected tool was missing: $tool"
    }
    if ((Get-Item -LiteralPath $tool).Length -lt 10000) {
        throw "Unexpectedly small WiX binary: $tool"
    }
}
# Set both discoverable PATH and the documented WiX directory environment.
# No admin rights and no modifications to Program Files or the Windows registry.
$bin | Out-File -FilePath $env:GITHUB_PATH -Append -Encoding utf8
"WIX=$bin" | Out-File -FilePath $env:GITHUB_ENV -Append -Encoding utf8
$env:PATH = "$bin;$env:PATH"
$env:WIX = $bin
Write-Host "Verified WiX 3.11.2 binaries are available at $bin (build-only; no installer installed)."
