[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Authorized,
    [switch]$WithMaterialRoutes,
    [string]$RouteSessionConfig,
    [string]$PreparationConfig = 'config/party-preparation.json',
    [ValidateRange(0,35)][int]$MaximumMinutes = 0,
    [string[]]$ResumeChild = @()
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
try {
    $settings = Get-Content -LiteralPath (Join-Path $Root 'config/settings.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $python = if ($settings.pythonExe) { $settings.pythonExe } else { 'python' }
    $invokeArgs = @('-B', (Join-Path $PSScriptRoot 'cultivation_full.py'), '--root', $Root)
    if ($MaximumMinutes -gt 0) { $invokeArgs += @('--maximum-minutes', [string]$MaximumMinutes) }
    if ($DryRun) { $invokeArgs += '--dry-run' }
    if ($Authorized) { $invokeArgs += '--authorized' }
    if ($WithMaterialRoutes) { $invokeArgs += '--with-material-routes' }
    if ($RouteSessionConfig) { $invokeArgs += @('--route-session-config', $RouteSessionConfig) }
    $invokeArgs += @('--preparation-config', $PreparationConfig)
    foreach ($identifier in $ResumeChild) { $invokeArgs += @('--resume-child', $identifier) }
    & $python @invokeArgs
    exit $LASTEXITCODE
} catch {
    Write-Error ('培养完整入口未完成：' + $_.Exception.Message)
    exit 4
}
