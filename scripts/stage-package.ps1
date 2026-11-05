$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path .).Path
$plan = Get-Content -LiteralPath 'work/plan.json' -Raw -Encoding utf8 | ConvertFrom-Json
$upstream = (Resolve-Path 'work/upstream').Path
$stage = Join-Path $root ('work/stage/' + $plan.folder)
$appInfo = Join-Path $stage 'App/AppInfo'
$sourceDir = Join-Path $stage 'Other/Source'
$releaseDir = Join-Path $root 'release'
$exeSource = Join-Path $root 'work/generated/website.exe'
if (-not (Test-Path -LiteralPath $exeSource -PathType Leaf)) { throw 'Pake compiled EXE missing' }
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage,$appInfo,$sourceDir,$releaseDir | Out-Null
$destExe = Join-Path $stage ([string]$plan.exe)
Copy-Item -LiteralPath $exeSource -Destination $destExe
if (Test-Path 'work/generated/WebView2Loader.dll') {
    Copy-Item -LiteralPath 'work/generated/WebView2Loader.dll' -Destination (Join-Path $stage 'WebView2Loader.dll')
}
foreach($name in @('WebView','State','TraceGuard')) {
    New-Item -ItemType Directory -Force -Path (Join-Path $stage ('Data/' + $name)) | Out-Null
}

# Extract the actual icon from Pake's compiled application (website icon
# when Pake found one, otherwise Pake's original fallback icon).
# No placeholder icon graphics are generated or used.
Add-Type -AssemblyName System.Drawing
$icon = [System.Drawing.Icon]::ExtractAssociatedIcon($destExe)
if ($null -eq $icon) { throw 'The compiled application has no Windows icon; refusing fake appicon icons' }
try {
    $stream = [System.IO.File]::Create((Join-Path $appInfo 'appicon.ico'))
    try { $icon.Save($stream) } finally { $stream.Dispose() }
    foreach($size in @(16,32)) {
        $bitmap = [System.Drawing.Bitmap]::new($size, $size)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.Clear([System.Drawing.Color]::Transparent)
            $graphics.DrawIcon($icon, ([System.Drawing.Rectangle]::new(0,0,$size,$size)))
            $bitmap.Save((Join-Path $appInfo ("appicon_${size}.png")), [System.Drawing.Imaging.ImageFormat]::Png)
        } finally { $graphics.Dispose(); $bitmap.Dispose() }
    }
} finally { $icon.Dispose() }
$packageVersion = [string]$plan.version + '.0'
$appName = [string]$plan.name
$appId = [string]$plan.slug + 'Portable-vhick'
$ini = @"
[Format]
Type=PortableApps.comFormat
Version=3.9

[Details]
Name=$appName Portable
AppID=$appId
Publisher=tw93 (Pake framework) and independent website owner
Homepage=https://github.com/tw93/Pake
Category=Internet
Description=Portable Pake/Tauri website wrapper; not an official website provider app
Language=Multilingual

[License]
Shareable=true
OpenSource=true
Freeware=true
CommercialUse=true

[Version]
PackageVersion=$packageVersion
DisplayVersion=$($plan.version) Portable r8

[Dependencies]
Requires64bitOS=yes
RequiresAdmin=no

[Control]
Icons=1
Start=$($plan.exe)
"@
Set-Content -LiteralPath (Join-Path $appInfo 'appinfo.ini') -Value $ini -Encoding utf8
Copy-Item -LiteralPath (Join-Path $upstream 'LICENSE') -Destination (Join-Path $sourceDir 'PAKE-LICENSE.txt') -Force
if (Test-Path -LiteralPath (Join-Path $upstream 'LICENSE-EXCEPTION')) {
    Copy-Item -LiteralPath (Join-Path $upstream 'LICENSE-EXCEPTION') -Destination (Join-Path $sourceDir 'PAKE-LICENSE-EXCEPTION.txt') -Force
}
Copy-Item -LiteralPath (Join-Path $root 'scripts/patch-portability.py') -Destination (Join-Path $sourceDir 'portable-source-patch.py')
Copy-Item -LiteralPath (Join-Path $root 'docs/PORTABILITY.md') -Destination (Join-Path $sourceDir 'PORTABILITY.md')
$manifest = [ordered]@{
    website = [string]$plan.url
    appName = [string]$plan.name
    appVersion = [string]$plan.version
    pakeTag = [string]$env:PAKE_TAG
    pakeCommit = [string]$env:PAKE_COMMIT
    architecture = 'windows-x64-msvc'
    builder = 'r8'
    generatedFrom = 'Pake CLI --keep-binary; installer excluded'
    exe = [string]$plan.exe
    storage = @('Data/State','Data/WebView')
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $sourceDir 'PROVENANCE.json') -Encoding utf8
$traceguard = [ordered]@{
    strategy = 'source-level redirect before Tauri/WebView2 startup'
    appOwnedData = @('Data/State','Data/WebView')
    hostAppDataRecovery = 'disabled: refuse to move unknown or preexisting host data'
    emptyDirectories = 'preserved by ZIP directory entries; retained in Data during updates'
    note = 'No generalized runtime filesystem ownership attribution is claimed.'
}
$traceguard | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $sourceDir 'TRACEGUARD-BOUNDARIES.json') -Encoding utf8
$guide = @"
$appName Portable ($($plan.version))

Double-click $($plan.exe) to open the website. This is the real Pake/Tauri app,
not a command-line build tool and not an installer.

Data/State holds Tauri application/plugin state.
Data/WebView holds the isolated Microsoft Edge WebView2 profile and session.
Data/TraceGuard is reserved for future app-specific trace evidence.

On upgrades: CLOSE the program. Back up Data. Replace only the EXE and App/Other
folders from a new ZIP; never overwrite, remove, or reset your existing Data.

Windows Microsoft Edge WebView2 Runtime is a host dependency. Site downloads
normally go to the user's standard Windows Downloads folder by design.
This package is independent of PortableApps.com and is not a certified .paf.exe.

See Other/Source/PORTABILITY.md for the source-specific audit and limitations.
"@
Set-Content -LiteralPath (Join-Path $stage 'README-PORTABLE.txt') -Value $guide -Encoding utf8
# Preserve empty directories explicitly. PowerShell Compress-Archive can omit them.
$zipPath = Join-Path $releaseDir ([string]$plan.zipName)
& python (Join-Path $root 'scripts/zip-package.py') $stage $zipPath
if ($LASTEXITCODE -ne 0) { throw 'Portable ZIP generation failed' }
Write-Host "Prepared independently usable portable ZIP: $zipPath"
