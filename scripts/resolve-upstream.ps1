$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$headers=@{ 'Accept'='application/vnd.github+json'; 'User-Agent'='Pake-Native-Portable-Builder' }
if($env:GH_TOKEN){ $headers['Authorization']="Bearer $env:GH_TOKEN" }
$tags=@(Invoke-RestMethod -Uri 'https://api.github.com/repos/tw93/Pake/releases?per_page=100' -Headers $headers)
$stable=@($tags | Where-Object { -not $_.draft -and -not $_.prerelease -and $_.tag_name -match '^[Vv](\d+)\.(\d+)\.(\d+)$' })
if($stable.Count -eq 0){throw 'No eligible stable upstream release; do not guess a version.'}
$selected=$null
if([string]::IsNullOrWhiteSpace($env:REQUESTED_TAG)){
  $selected=$stable | Sort-Object -Property @{Expression={ [version]($_.tag_name -replace '^[Vv]','') }} -Descending | Select-Object -First 1
}else{
  $requested=$env:REQUESTED_TAG.Trim()
  if($requested -notmatch '^[Vv]\d+\.\d+\.\d+$'){throw 'Explicit upstream tag must be Vx.y.z and stable'}
  $selected=$stable | Where-Object {$_.tag_name -ceq $requested} | Select-Object -First 1
  if(-not $selected){throw "Requested tag '$requested' is missing from the latest 100 stable-release candidates; refusing unverified tag"}
}
$tag=$selected.tag_name
$version=$tag -replace '^[Vv]',''
# Resolve an annotated OR lightweight tag to the peeled commit, using GitHub API.
$ref=Invoke-RestMethod -Uri ('https://api.github.com/repos/tw93/Pake/git/ref/tags/'+$tag) -Headers $headers
$oid=$ref.object.sha
if($ref.object.type -eq 'tag'){
  $tagObject=Invoke-RestMethod -Uri ('https://api.github.com/repos/tw93/Pake/git/tags/'+$oid) -Headers $headers
  if($tagObject.object.type -ne 'commit'){throw 'Tag does not peel to a commit'}
  $oid=$tagObject.object.sha
}elseif($ref.object.type -ne 'commit'){throw 'Tag ref does not resolve to a commit'}
if($oid -notmatch '^[0-9a-f]{40}$'){throw 'Invalid upstream commit SHA'}
"tag=$tag" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
"version=$version" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
"commit=$oid" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
Write-Host "Upstream release: $tag commit: $oid"
