$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
# Pake's --keep-binary retains the real EXE but Pake's current Windows CLI
# still generates an intermediate MSI. The MSI is NOT distributed by this kit.
$wixBin = Join-Path ${env:ProgramFiles(x86)} 'WiX Toolset v3.11/bin'
$light = Join-Path $wixBin 'light.exe'
if (-not (Test-Path -LiteralPath $light -PathType Leaf)) {
    $url = 'https://github.com/wixtoolset/wix3/releases/download/wix3112rtm/wix311.exe'
    # WiX 3.11.2 official release checksum, independently documented by Chocolatey.
    # https://community.chocolatey.org/packages/wixtoolset/3.11.2
    $expected = '32BB76C478FCB356671D4AAF006AD81CA93EEA32C22A9401B168FC7471FECCD2'
    New-Item -ItemType Directory -Force -Path 'work/tools' | Out-Null
    $download = Join-Path (Resolve-Path 'work/tools') 'wix311.exe'
    Invoke-WebRequest -Uri $url -OutFile $download -UseBasicParsing
    $actual = (Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash
    if ($actual -cne $expected) { throw 'WiX installer SHA-256 mismatch. Refusing to run unverified installer.' }
    $process = Start-Process -FilePath $download -ArgumentList '/quiet' -Wait -PassThru
    if ($process.ExitCode -notin @(0,3010)) { throw "Upstream WiX installer returned exit code $($process.ExitCode)" }
}
if (-not (Test-Path -LiteralPath $light -PathType Leaf)) { throw 'WiX 3.11 light.exe missing after installation' }
$wixBin | Out-File -FilePath $env:GITHUB_PATH -Append -Encoding utf8
$env:PATH = "$wixBin;$env:PATH"
Write-Host 'Verified WiX 3.11 tool available for upstream Pake temporary MSI compilation.'
