[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Config = Join-Path $Root 'config'
$items = @('settings', 'goals', 'domain-calendar', 'book-progress')

foreach ($name in $items) {
    $source = Join-Path $Config ($name + '.example.json')
    $target = Join-Path $Config ($name + '.json')
    if (Test-Path -LiteralPath $target) {
        Write-Host ('Keep existing ' + $target)
    } else {
        Copy-Item -LiteralPath $source -Destination $target
        Write-Host ('Created ' + $target)
    }
}

Write-Host 'Configuration initialized. Edit config/settings.json before a live run.'
