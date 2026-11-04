$ErrorActionPreference='Stop'
$stage=Join-Path (Resolve-Path .).Path 'work/stage/PakePortable'
$project=Join-Path (Resolve-Path .).Path 'launcher/PakePortable.csproj'
# Pake is a CLI, not a desktop GUI; intentionally build a console subsystem PE executable.
dotnet publish $project -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:DebugType=None -p:DebugSymbols=false -o (Join-Path (Resolve-Path .).Path 'work/launcher')
if($LASTEXITCODE -ne 0){throw 'Native Windows launcher compilation failed'}
$exe=Join-Path (Resolve-Path .).Path 'work/launcher/PakePortable.exe'
if(-not (Test-Path $exe)){throw 'Missing compiled executable'}
Copy-Item -LiteralPath $exe -Destination (Join-Path $stage 'PakePortable.exe')
