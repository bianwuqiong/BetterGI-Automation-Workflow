param(
    [string]$Task = '',
    [int]$TimeoutMinutes = 0,
    [switch]$DryRun,
    [switch]$AllowRepeat,
    [switch]$KeepGame,
    [switch]$AllowExistingGame
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
try {
    if (-not $Task) {
        $next = Join-Path $Root 'config\next-task.txt'
        if (Test-Path -LiteralPath $next) { $Task = (Get-Content -LiteralPath $next -Encoding UTF8 | Select-Object -First 1).Trim() }
    }
    if (-not $Task) { throw '未指定任务：请传入 -Task 或写入 config/next-task.txt。' }
    $cfg = Get-Content -LiteralPath (Join-Path $Root 'config\settings.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $python = if ($cfg.pythonExe) { $cfg.pythonExe } else { 'python' }
    $invokeArgs = @((Join-Path $PSScriptRoot 'workflow.py'), '--root', $Root, 'run', '--task', $Task, '--no-delay', '--timeout-minutes', "$TimeoutMinutes")
    if ($DryRun) { $invokeArgs += '--dry-run' }
    if ($AllowRepeat) { $invokeArgs += '--allow-repeat' }
    if ($KeepGame) { $invokeArgs += '--keep-game' }
    if ($AllowExistingGame) { $invokeArgs += '--allow-existing-game' }
    & $python @invokeArgs
    exit $LASTEXITCODE
} catch {
    Write-Host ('启动失败：' + $_.Exception.Message)
    exit 4
}
