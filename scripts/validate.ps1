$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$root=(Resolve-Path .).Path
$stage=Join-Path $root 'work/stage/PakePortable'
$exe=Join-Path $stage 'PakePortable.exe'
$node=Join-Path $stage 'App/Node/node.exe'
$cli=Join-Path $stage 'App/Cli/node_modules/pake-cli/dist/cli.js'
foreach($p in @($exe,$node,$cli,(Join-Path $stage 'SOURCE.json'))){if(-not(Test-Path $p)){throw "Required file missing: $p"}}
# Verify PE signature AND compile/runtime execution, not only a .exe filename.
$bytes=[IO.File]::ReadAllBytes($exe)
if($bytes.Length -lt 256 -or $bytes[0] -ne 77 -or $bytes[1] -ne 90){throw 'Invalid launcher DOS signature'}
$offset=[BitConverter]::ToInt32($bytes,60)
if($offset -lt 64 -or ($offset+4) -gt $bytes.Length -or [Text.Encoding]::ASCII.GetString($bytes,$offset,4) -ne "PE`0`0"){throw 'Invalid Windows PE header'}
$env:PAKE_PORTABLE_TEST='1'
& $exe --help
if($LASTEXITCODE -ne 0){throw 'Portable EXE failed actual CLI --help execution'}
& $exe --version
if($LASTEXITCODE -ne 0){throw 'Portable EXE failed actual CLI --version execution'}
& $exe --traceguard-selftest
if($LASTEXITCODE -ne 0){throw 'TraceGuard empty-directory selftest failed'}
$manifest=Join-Path $stage 'Data/TraceGuard/manifest.json'
if(-not(Test-Path $manifest)){throw 'TraceGuard manifest missing after runtime test'}
# Verify on-disk manifests include empty nested directories and persisted files.
$empty=Join-Path $stage 'Data/TestNestedEmpty/level1/level2'
New-Item -ItemType Directory -Force -Path $empty | Out-Null
$sentinel=Join-Path $stage 'Data/TestNestedEmpty/sentinel.txt'
'SAVE_USER_DATA' | Set-Content -LiteralPath $sentinel -Encoding ascii
& $exe --help | Out-Null
if($LASTEXITCODE -ne 0){throw 'Repeated execution failed'}
$entries=@((Get-Content $manifest -Raw | ConvertFrom-Json).items | ForEach-Object { $_.path })
if(-not @($entries | Where-Object {$_ -match 'TestNestedEmpty[/\\]level1[/\\]level2$'}).Count){throw 'Missing nested empty directory in manifest'}
if((Get-Content $sentinel -Raw).Trim() -ne 'SAVE_USER_DATA'){throw 'User Data changed across repeated run'}
# Simulate an interrupted parent process and exercise the next-launch recovery path.
$active=Join-Path $stage 'Data/TraceGuard/active.json'
'{"StartedUtc":"2026-01-01T00:00:00Z","Roots":[]}' | Set-Content -LiteralPath $active -Encoding utf8
& $exe --help | Out-Null
if($LASTEXITCODE -ne 0 -or (Test-Path $active)){throw 'Interrupted-session recovery failed'}
# Protect unrelated pre-existing host data even if a user mistakenly allowlists it.
$protected=Join-Path $env:TEMP ('PakePortable-Protected-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $protected | Out-Null
try {
  'HOST_SENTINEL' | Set-Content (Join-Path $protected 'host.txt') -Encoding ascii
  $allowlist=Join-Path $stage 'Data/TraceGuard/owned-roots.txt'
  $protected | Set-Content -LiteralPath $allowlist -Encoding utf8
  & $exe --help | Out-Null
  if($LASTEXITCODE -ne 0){throw 'Pre-existing host protection test launcher failed'}
  if((Get-Content (Join-Path $protected 'host.txt') -Raw).Trim() -ne 'HOST_SENTINEL'){
    throw 'Pre-existing host data was modified'
  }
}finally{Remove-Item -Recurse -Force -LiteralPath $protected -ErrorAction SilentlyContinue}
Write-Host 'Verified repeated runs, nested empty directories, crash marker, and pre-existing host protection.'
# Remove CI smoke-test Data; never do this to a user's real Data folder.
Remove-Item -Recurse -Force -LiteralPath (Join-Path $stage 'Data')
New-Item -ItemType Directory -Force -Path (Join-Path $stage 'Data') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $root 'release') | Out-Null
$name="PakePortable_$env:PAKE_VERSION"+'_Native-r4_win-x64.zip'
$zip=Join-Path $root "release/$name"
if(Test-Path $zip){throw "Output collision: $zip"}
Compress-Archive -LiteralPath $stage -DestinationPath $zip -CompressionLevel Optimal
Add-Type -AssemblyName System.IO.Compression
$archive=[IO.Compression.ZipFile]::OpenRead($zip)
try{
  $names=@($archive.Entries|ForEach-Object FullName)
  foreach($required in @('PakePortable/PakePortable.exe','PakePortable/SOURCE.json','PakePortable/App/Node/node.exe')){
    if($names -cnotcontains $required){throw "ZIP missing $required"}
  }
  if($archive.Entries.Count -lt 50){throw 'ZIP appears incomplete'}
}finally{$archive.Dispose()}
$hash=(Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "Validated native ZIP: $zip SHA256: $hash"
