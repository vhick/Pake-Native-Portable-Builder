param(
  [switch]$SelfTest
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Explicitly iterate release objects. Invoke-RestMethod is documented to send a
# JSON array as ONE Object[] to the pipeline, so @(Invoke-RestMethod ...) can
# accidentally create a nested array and make Where-Object reject every release.
function Select-StablePakeRelease {
  param(
    [Parameter(Mandatory=$true)][object[]]$Releases,
    [string]$RequestedTag = ''
  )
  $stable = [System.Collections.Generic.List[object]]::new()
  foreach ($release in $Releases) {
    if ($null -eq $release) { continue }
    if ($release -is [array]) {
      throw 'Nested GitHub release array detected; expected individual release objects.'
    }
    if ($null -eq $release.PSObject.Properties['tag_name']) { continue }
    if ($null -eq $release.PSObject.Properties['draft'] -or
        $null -eq $release.PSObject.Properties['prerelease']) { continue }
    if ([bool]$release.draft -or [bool]$release.prerelease) { continue }
    $tagName = [string]$release.tag_name
    # Official upstream uses uppercase V (example: V3.17.6). Strict 3-part
    # version excludes beta/nightly/suffixed tags even if API flags are wrong.
    if ($tagName -cnotmatch '^V[0-9]+\.[0-9]+\.[0-9]+$') { continue }
    $stable.Add($release)
  }
  if ($stable.Count -eq 0) {
    $seenTags = @($Releases | ForEach-Object {
      if ($null -ne $_ -and $null -ne $_.PSObject.Properties['tag_name']) { $_.tag_name }
    } | Select-Object -First 8) -join ', '
    throw "GitHub returned $($Releases.Count) release records but found no eligible stable Vx.y.z release. First tags: [$seenTags]."
  }
  if (-not [string]::IsNullOrWhiteSpace($RequestedTag)) {
    $requested = $RequestedTag.Trim()
    if ($requested -cnotmatch '^V[0-9]+\.[0-9]+\.[0-9]+$') {
      throw 'Explicit upstream tag must have the form Vx.y.z and be stable.'
    }
    foreach ($release in $stable) {
      if ([string]$release.tag_name -ceq $requested) { return $release }
    }
    throw "Requested tag '$requested' is not a published stable release in the first 100 GitHub release records."
  }
  $highest = $null
  $highestVersion = [version]'0.0.0'
  foreach ($release in $stable) {
    $releaseVersion = [version](([string]$release.tag_name).Substring(1))
    if ($null -eq $highest -or $releaseVersion -gt $highestVersion) {
      $highest = $release
      $highestVersion = $releaseVersion
    }
  }
  return $highest
}

# Runs before any API call, on Windows GitHub Actions. Exercises realistic
# responses with both true stable versions and intentionally ineligible entries.
if ($SelfTest) {
  $fixtureJson = @'
[
  {"tag_name":"V3.17.2","draft":false,"prerelease":false},
  {"tag_name":"V3.17.6","draft":false,"prerelease":false},
  {"tag_name":"V3.18.0","draft":true,"prerelease":false},
  {"tag_name":"V3.19.0","draft":false,"prerelease":true},
  {"tag_name":"V4.0.0-beta.1","draft":false,"prerelease":true}
]
'@
  [object[]]$fixture = ConvertFrom-Json -InputObject $fixtureJson
  $latest = Select-StablePakeRelease -Releases $fixture
  if ($latest.tag_name -cne 'V3.17.6') { throw 'Release resolver self-test failed: latest stable.' }
  $explicit = Select-StablePakeRelease -Releases $fixture -RequestedTag 'V3.17.2'
  if ($explicit.tag_name -cne 'V3.17.2') { throw 'Release resolver self-test failed: explicit stable tag.' }
  $rejected = $false
  try { $null = Select-StablePakeRelease -Releases $fixture -RequestedTag 'V3.18.0' }
  catch { $rejected = $true }
  if (-not $rejected) { throw 'Release resolver self-test failed: draft was accepted.' }
  Write-Host 'Release resolver self-test passed: version ordering, explicit tag, draft/prerelease filtering.'
  exit 0
}

$headers = @{
  'Accept' = 'application/vnd.github+json'
  'User-Agent' = 'Pake-Native-Portable-Builder'
  'X-GitHub-Api-Version' = '2022-11-28'
}
if ($env:GH_TOKEN) { $headers['Authorization'] = "Bearer $env:GH_TOKEN" }

$releaseResponse = Invoke-RestMethod -Uri 'https://api.github.com/repos/tw93/Pake/releases?per_page=100' -Headers $headers
if ($null -eq $releaseResponse -or $releaseResponse -isnot [array]) {
  throw 'Unexpected GitHub releases API response: expected a JSON release array.'
}
# IMPORTANT: do NOT use @(Invoke-RestMethod ...); foreach here now sees
# individual releases rather than a nested Object[].
[object[]]$releases = $releaseResponse
Write-Host "GitHub returned $($releases.Count) Pake release records."
$selected = Select-StablePakeRelease -Releases $releases -RequestedTag $env:REQUESTED_TAG
$tag = [string]$selected.tag_name
$version = $tag.Substring(1)

# Resolve lightweight and annotated tags to their commit. The checkout script
# later verifies the fetched tag resolves to the exact same 40-character SHA.
$ref = Invoke-RestMethod -Uri ('https://api.github.com/repos/tw93/Pake/git/ref/tags/' + $tag) -Headers $headers
$oid = [string]$ref.object.sha
if ($ref.object.type -eq 'tag') {
  $tagObject = Invoke-RestMethod -Uri ('https://api.github.com/repos/tw93/Pake/git/tags/' + $oid) -Headers $headers
  if ($tagObject.object.type -ne 'commit') { throw 'Annotated tag does not peel to a commit.' }
  $oid = [string]$tagObject.object.sha
} elseif ($ref.object.type -ne 'commit') {
  throw 'Tag ref does not point to a commit.'
}
if ($oid -cnotmatch '^[0-9a-f]{40}$') { throw 'Invalid upstream commit SHA.' }
if ([string]::IsNullOrWhiteSpace($env:GITHUB_OUTPUT)) { throw 'Missing GITHUB_OUTPUT; this resolver must run in the workflow.' }
"tag=$tag" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
"version=$version" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
"commit=$oid" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
Write-Host "Selected stable upstream release: $tag, commit: $oid"
