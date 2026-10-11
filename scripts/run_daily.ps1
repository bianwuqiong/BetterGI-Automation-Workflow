param([switch]$NoDelay, [int]$TimeoutMinutes = 0, [switch]$DryRun, [switch]$AllowRepeat, [ValidateSet('core','extras','configured','cultivation','combat-rehearsal','material-route','material-route-session','material-recovery','party-preparation')][string]$Profile = 'core', [ValidateSet('foreground','childSession')][string]$ExecutionMode, [ValidateSet('scan','execute')][string]$CultivationMode = 'scan', [string]$RouteSessionConfig, [string]$RecoveryConfig, [string]$PreparationConfig, [string]$RouteConfig)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
try {
    $cfg = Get-Content -LiteralPath (Join-Path $Root 'config\settings.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $python = if ($cfg.pythonExe) { $cfg.pythonExe } else { 'python' }
    $invokeArgs = @((Join-Path $PSScriptRoot 'workflow.py'), '--root', $Root, 'run', '--profile', $Profile)
    if ($Profile -eq 'cultivation') { $invokeArgs += @('--cultivation-mode', $CultivationMode) }
    if ($RouteConfig) { $invokeArgs += @('--route-config', $RouteConfig) }
    if ($RouteSessionConfig) { $invokeArgs += @('--route-session-config', $RouteSessionConfig) }
    if ($PreparationConfig) { $invokeArgs += @('--preparation-config', $PreparationConfig) }
    if ($RecoveryConfig) { $invokeArgs += @('--recovery-config', $RecoveryConfig) }
    if ($NoDelay) { $invokeArgs += '--no-delay' }
    if ($DryRun) { $invokeArgs += '--dry-run' }
    if ($AllowRepeat) { $invokeArgs += '--allow-repeat' }
    if ($ExecutionMode) { $invokeArgs += @('--execution-mode', $ExecutionMode) }
    if ($TimeoutMinutes -gt 0) { $invokeArgs += @('--timeout-minutes', "$TimeoutMinutes") }
    & $python @invokeArgs
    exit $LASTEXITCODE
} catch {
    Write-Host ('启动失败：' + $_.Exception.Message)
    exit 4
}