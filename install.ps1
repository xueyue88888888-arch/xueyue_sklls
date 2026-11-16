# Sync every skill in this repo into the local Alma skills directory.
#
#   .\install.ps1                # sync all skills
#   .\install.ps1 -Only html-screen-to-design-source
#
# Alma's scanner does not follow junctions/symlinks, so this copies instead of linking.
# Run it after editing a skill, then push.

param(
    [string]$Only = '',
    [string]$Dest = "$env:USERPROFILE\.config\alma\skills"
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Test-Path -LiteralPath $Dest)) { New-Item -ItemType Directory -Path $Dest | Out-Null }

$skills = Get-ChildItem -LiteralPath $root -Directory |
    Where-Object { $_.Name -notin @('.git', '.github', 'node_modules') -and (Test-Path (Join-Path $_.FullName 'SKILL.md')) }

if ($Only) { $skills = $skills | Where-Object { $_.Name -eq $Only } }
if (-not $skills) { Write-Host "no skills found (or -Only did not match)"; exit 1 }

foreach ($s in $skills) {
    $target = Join-Path $Dest $s.Name
    $first = -not (Test-Path -LiteralPath $target)
    if ($first) {
        # let Alma register the skill (writes SKILL.md + records it)
        & alma skill create $s.Name --file (Join-Path $s.FullName 'SKILL.md') | Out-Null
    }
    foreach ($item in @('scripts', 'references', 'examples', 'README.md')) {
        $src = Join-Path $s.FullName $item
        if (-not (Test-Path -LiteralPath $src)) { continue }
        Copy-Item -LiteralPath $src -Destination $target -Recurse -Force
    }
    # keep SKILL.md in sync as well
    Copy-Item -LiteralPath (Join-Path $s.FullName 'SKILL.md') -Destination $target -Force
    Write-Host ("{0} {1} -> {2}" -f ($(if ($first) { 'registered' } else { 'synced    ' })), $s.Name, $target)
}

Write-Host "`ndone. verify with:  alma skill list | Select-String html"
