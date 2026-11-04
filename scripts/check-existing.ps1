$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$tag="portable-v$env:PAKE_VERSION-native-r2"
$repo=$env:GITHUB_REPOSITORY
if([string]::IsNullOrWhiteSpace($repo)){throw 'Missing GITHUB_REPOSITORY'}
$skip='false'
if($env:DO_PUBLISH -eq 'true'){
  $result=& gh release view $tag --repo $repo --json body,assets,isDraft 2>&1
  if($LASTEXITCODE -eq 0){
    $release=($result | Out-String) | ConvertFrom-Json
    if($release.isDraft -or $release.body -notmatch 'portable-release-publisher:managed:v2'){
      throw "Release $tag exists but is not a published shared-publisher-managed release; investigate before rebuilding."
    }
    $assetNames=@($release.assets | ForEach-Object { $_.name })
    if($assetNames -notcontains 'SHA256SUMS.txt' -or -not @($assetNames | Where-Object {$_ -match '^PakePortable_.+_Native-r2_win-x64\.zip$'}).Count){
      throw "Managed release $tag exists but required assets are missing; investigate rather than replacing it."
    }
    Write-Host "Managed $tag already published with ZIP and checksum; skipping unchanged compilation."
    $skip='true'
  } else {
    $message=($result|Out-String)
    if($message -notmatch 'release not found|HTTP 404|not found'){
      throw "Cannot check release ${tag}: $message"
    }
    Write-Host "No prior release $tag; build required."
  }
}
"skip=$skip" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
