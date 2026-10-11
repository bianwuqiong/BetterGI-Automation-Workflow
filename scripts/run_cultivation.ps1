[CmdletBinding()]
param(
    [ValidateSet('scan', 'execute')][string]$Mode = 'scan',
    [switch]$DryRun,
    [switch]$KeepGame,
    [switch]$AllowExistingGame,
    [ValidateSet('foreground', 'childSession')][string]$ExecutionMode
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
try {
    $cfg = Get-Content -LiteralPath (Join-Path $Root 'config\settings.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $python = if ($cfg.pythonExe) { $cfg.pythonExe } else { 'python' }
    $invokeArgs = @('-B', (Join-Path $PSScriptRoot 'workflow.py'), '--root', $Root, 'run',
        '--task', '培养材料', '--cultivation-mode', $Mode, '--no-delay', '--timeout-minutes', '20')
    if ($ExecutionMode) { $invokeArgs += @('--execution-mode', $ExecutionMode) }
    if ($DryRun) { $invokeArgs += '--dry-run' }
    if ($KeepGame) { $invokeArgs += '--keep-game' }
    if ($AllowExistingGame) { $invokeArgs += '--allow-existing-game' }
    & $python @invokeArgs
    exit $LASTEXITCODE
} catch {
    Write-Error ('培养工作流启动失败：' + $_.Exception.Message)
    exit 4
}
