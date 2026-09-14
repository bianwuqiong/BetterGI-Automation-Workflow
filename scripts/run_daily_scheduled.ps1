[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$startedAt = Get-Date

function Show-RunNotification([string]$Message, [bool]$IsError = $false) {
    try {
        $shell = New-Object -ComObject WScript.Shell
        $icon = if ($IsError) { 16 } else { 64 }
        $null = $shell.Popup($Message, 30, '原神日常自动化', $icon)
    } catch {
        Write-Host $Message
    }
}

function Find-LatestRunResult {
    $currentPath = Join-Path $Root 'state\current-run.json'
    if (Test-Path -LiteralPath $currentPath) {
        try {
            $current = Get-Content -LiteralPath $currentPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($current.triggeredAt -and ([datetime]$current.triggeredAt) -ge $startedAt.AddSeconds(-5)) {
                return $current
            }
        } catch {}
    }
    $candidate = Get-ChildItem -LiteralPath (Join-Path $Root 'logs\runs') -Filter result.json `
        -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -ge $startedAt.AddSeconds(-5) } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($candidate) {
        try {
            return Get-Content -LiteralPath $candidate.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
        } catch {}
    }
    return $null
}

try {
    & (Join-Path $PSScriptRoot 'run_daily.ps1') -NoDelay -Profile core
    $workflowExit = $LASTEXITCODE
    $result = Find-LatestRunResult
    if ($result) {
        $resultPath = if ($result.resultPath) {
            [string]$result.resultPath
        } else {
            [string]$result.logArchive
        }
        if ($workflowExit -eq 0 -and $result.outcome -eq 'completed') {
            Show-RunNotification "原神日常自动化已完成。`n运行编号：$($result.runId)"
        } else {
            $detail = if ($result.errors -and $result.errors.Count) {
                [string]$result.errors[0]
            } else {
                "结果：$($result.outcome)；阶段：$($result.executionOutcome)；退出码：$workflowExit"
            }
            Show-RunNotification "原神日常自动化未完整通过：$detail`n`n运行记录：$resultPath" $true
        }
    } elseif ($workflowExit -ne 0) {
        Show-RunNotification "原神日常自动化退出，返回码 $workflowExit。未找到本次运行记录。" $true
    }
    exit $workflowExit
} catch {
    $message = '启动失败：' + $_.Exception.Message
    Show-RunNotification $message $true
    Write-Error $message
    exit 4
}
