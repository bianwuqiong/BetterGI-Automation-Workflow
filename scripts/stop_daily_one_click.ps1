[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root 'logs\launcher'

function Show-StopMessage([string]$Message, [bool]$IsError = $false) {
    try {
        $shell = New-Object -ComObject WScript.Shell
        $icon = if ($IsError) { 16 } else { 64 }
        $null = $shell.Popup($Message, 12, '停止原神日常自动化', $icon)
    } catch {
        Write-Host $Message
    }
}

try {
    $currentPath = Join-Path $Root 'state\current-run.json'
    if (-not (Test-Path -LiteralPath $currentPath)) {
        Show-StopMessage '当前没有可停止的自动化运行。'
        exit 0
    }
    $current = Get-Content -LiteralPath $currentPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $activeStates = @('preflight', 'delaying', 'starting', 'running', 'stopping')
    if ([string]$current.executionOutcome -notin $activeStates) {
        Show-StopMessage "当前运行 $($current.runId) 已经结束，无需停止。"
        exit 0
    }

    $cfg = Get-Content -LiteralPath (Join-Path $Root 'config\settings.json') -Raw -Encoding UTF8 |
        ConvertFrom-Json
    $python = if ($cfg.pythonExe) { [string]$cfg.pythonExe } else { 'python' }
    $arguments = @((Join-Path $PSScriptRoot 'workflow.py'), '--root', $Root, 'stop',
        '--run-id', [string]$current.runId)
    $output = & $python @arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($output | Out-String).Trim()
    }
    Show-StopMessage "已请求停止原神日常自动化。`n运行编号：$($current.runId)"
    $output
    exit 0
} catch {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    $logPath = Join-Path $LogDir ("stop-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    $detail = $_.Exception.Message
    @(
        "Time: $((Get-Date).ToString('o'))"
        "Error: $detail"
    ) | Set-Content -LiteralPath $logPath -Encoding UTF8
    Show-StopMessage "停止请求失败：$detail`n`n错误记录：$logPath" $true
    Write-Error $detail
    exit 1
}
