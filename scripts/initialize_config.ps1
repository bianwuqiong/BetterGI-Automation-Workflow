[CmdletBinding()]
param([switch]$IncludeTalentPlanning, [switch]$IncludeCultivation, [switch]$IncludeArtifactFarming)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Config = Join-Path $Root 'config'
$items = @('settings', 'goals')
if ($IncludeTalentPlanning) {
    $items += @('domain-calendar', 'book-progress')
}
if ($IncludeCultivation) {
    $items += @('cultivation', 'party-preparation')
}
if ($IncludeArtifactFarming) {
    $items += 'artifact-farming'
}

foreach ($name in $items) {
    $source = Join-Path $Config ($name + '.example.json')
    $target = Join-Path $Config ($name + '.json')
    if (Test-Path -LiteralPath $target) {
        Write-Host ('Keep existing ' + $target)
    } else {
        if ($name -eq 'artifact-farming') {
            $artifactConfig = Get-Content -LiteralPath $source -Raw -Encoding UTF8 | ConvertFrom-Json
            $artifactConfig.executionEnabled = $false
            $artifactConfig.policy.scopeId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
            $artifactConfig.policy.originalResinBudget = 0
            $artifactConfig.policy.condensedResinBudget = 0
            $artifactConfig.policy.maxCrafts = 0
            $artifactConfig.policy.domainValidated = $false
            $artifactConfig.policy.craftingValidated = $false
            $artifactConfig | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $target -Encoding UTF8
        } else {
            Copy-Item -LiteralPath $source -Destination $target
        }
        Write-Host ('Created ' + $target)
    }
}

Write-Host 'Configuration initialized. Edit config/settings.json and config/goals.json before a live run.'
if (-not $IncludeTalentPlanning) {
    Write-Host 'Artifact-only goals do not need domain-calendar.json or book-progress.json.'
}
