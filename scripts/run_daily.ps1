param([switch]$NoDelay, [int]$TimeoutMinutes = 0, [switch]$DryRun, [switch]$AllowRepeat, [ValidateSet('core','extras','configured')][string]$Profile = 'core')
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
try {
    $cfg = Get-Content -LiteralPath (Join-Path $Root 'config\settings.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $python = if ($cfg.pythonExe) { $cfg.pythonExe } else { 'python' }
    $invokeArgs = @((Join-Path $PSScriptRoot 'workflow.py'), '--root', $Root, 'run', '--profile', $Profile)
    if ($NoDelay) { $invokeArgs += '--no-delay' }
    if ($DryRun) { $invokeArgs += '--dry-run' }
    if ($AllowRepeat) { $invokeArgs += '--allow-repeat' }
    if ($TimeoutMinutes -gt 0) { $invokeArgs += @('--timeout-minutes', "$TimeoutMinutes") }
    & $python @invokeArgs
    exit $LASTEXITCODE
} catch {
    Write-Host ('启动失败：' + $_.Exception.Message)
    exit 4
}
