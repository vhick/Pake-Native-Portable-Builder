$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if($env:PAKE_TAG -notmatch '^[Vv]\d+\.\d+\.\d+$' -or $env:PAKE_COMMIT -notmatch '^[a-f0-9]{40}$'){throw 'Invalid upstream source identity'}
New-Item -ItemType Directory -Force -Path 'work' | Out-Null
# A tag-specific fetch avoids cloning the entire upstream repository and changes no upstream source.
git init -q work/upstream
if($LASTEXITCODE -ne 0){throw 'git init failed'}
git -C work/upstream remote add origin https://github.com/tw93/Pake.git
git -C work/upstream fetch --depth=1 origin "refs/tags/$env:PAKE_TAG"
if($LASTEXITCODE -ne 0){throw 'Upstream tag fetch failed'}
git -C work/upstream checkout --detach FETCH_HEAD
if($LASTEXITCODE -ne 0){throw 'Unable to check out fetched tag'}
$actual=(git -C work/upstream rev-parse HEAD).Trim()
if($LASTEXITCODE -ne 0 -or $actual -cne $env:PAKE_COMMIT){throw "Ref mismatch: actual $actual != selected $env:PAKE_COMMIT"}
$package=Get-Content work/upstream/package.json -Raw | ConvertFrom-Json
if($package.name -ne 'pake-cli' -or $package.version -ne ($env:PAKE_TAG -replace '^[Vv]','')){throw 'Upstream package identity does not match release'}
Write-Host "Fetched and verified Pake $($package.version) at $actual"
