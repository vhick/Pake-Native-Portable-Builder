param([switch]$SelfTest)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# gh is a native executable. Handle its exit code explicitly: GitHub's
# PowerShell runner checks $LASTEXITCODE at the end of the step, even if an
# expected "release not found" condition has already been handled.
# Treat a missing release as "build needed", not a failed workflow step.
function Test-PublishedRelease {
  param(
    [Parameter(Mandatory=$true)][int]$ExitCode,
    [AllowEmptyString()][string]$Response = '',
    [Parameter(Mandatory=$true)][string]$Tag
  )
  if ($ExitCode -ne 0) {
    if ($Response -notmatch '(?i)(release not found|HTTP 404)') {
      throw "Cannot check release ${Tag}: GitHub CLI exit code $ExitCode; $Response"
    }
    Write-Host "No prior release $Tag; build required."
    return 'false'
  }

  # Successful gh query: ensure this is an immutable managed release with the
  # expected ZIP and checksum. An invalid/partial release must never be skipped.
  $release = $Response | ConvertFrom-Json
  if ($release.isDraft -or $release.body -notmatch 'portable-release-publisher:managed:v2') {
    throw "Release $Tag exists but is not a published shared-publisher-managed release; investigate before rebuilding."
  }
  $assetNames = @($release.assets | ForEach-Object { $_.name })
  if ($assetNames -notcontains 'SHA256SUMS.txt' -or
      -not @($assetNames | Where-Object { $_ -match '^PakePortable_.+_Native-r4_win-x64\.zip$' }).Count) {
    throw "Managed release $Tag exists but required assets are missing; investigate rather than replacing it."
  }
  Write-Host "Managed $Tag already published with ZIP and checksum; skipping unchanged compilation."
  return 'true'
}

if ($SelfTest) {
  $tag='portable-v3.18.0-native-r4'
  $missing=Test-PublishedRelease -ExitCode 1 -Response 'release not found' -Tag $tag
  if ($missing -ne 'false') { throw 'Release precheck self-test: missing release must require build.' }
  $valid='{"isDraft":false,"body":"portable-release-publisher:managed:v2","assets":[{"name":"SHA256SUMS.txt"},{"name":"PakePortable_3.18.0_Native-r4_win-x64.zip"}]}'
  $existing=Test-PublishedRelease -ExitCode 0 -Response $valid -Tag $tag
  if ($existing -ne 'true') { throw 'Release precheck self-test: published managed release must skip.' }
  $failed=$false
  try { $null=Test-PublishedRelease -ExitCode 1 -Response 'HTTP 403: Resource not accessible by integration' -Tag $tag }
  catch { $failed=$true }
  if (-not $failed) { throw 'Release precheck self-test: permission errors must fail.' }
  Write-Host 'Release precheck self-test passed: 404 requires build, managed release skips, 403 fails.'
  exit 0
}

$tag="portable-v$env:PAKE_VERSION-native-r4"
$repo=$env:GITHUB_REPOSITORY
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Missing GITHUB_REPOSITORY' }
if ([string]::IsNullOrWhiteSpace($env:GITHUB_OUTPUT)) { throw 'Missing GITHUB_OUTPUT' }
$skip='false'
if ($env:DO_PUBLISH -eq 'true') {
  # A nonzero gh result is expected when this exact tag has not been published.
  # Do not let PowerShell promote a handled native-command exit to an exception.
  $PSNativeCommandUseErrorActionPreference = $false
  $result = & gh release view $tag --repo $repo --json body,assets,isDraft 2>&1
  $ghExitCode = $LASTEXITCODE
  $skip = Test-PublishedRelease -ExitCode $ghExitCode -Response ($result | Out-String) -Tag $tag
  # CRITICAL: GitHub Actions' pwsh wrapper runs `exit $LASTEXITCODE` after the
  # script. Set this only AFTER verifying that a nonzero gh exit was an expected
  # 404. Genuine failures above throw, and must remain failed.
  $global:LASTEXITCODE = 0
}
"skip=$skip" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
Write-Host "Release precheck completed successfully; skip=$skip"
