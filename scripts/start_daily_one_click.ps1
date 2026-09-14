[CmdletBinding()]
param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$TaskName = 'GenshinDailyCore'
$LauncherLogDir = Join-Path $Root 'logs\launcher'

function Read-CurrentRun {
    $path = Join-Path $Root 'state\current-run.json'
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    try {
        return Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Show-LauncherMessage([string]$Message, [bool]$IsError = $false) {
    try {
        $shell = New-Object -ComObject WScript.Shell
        $icon = if ($IsError) { 16 } else { 64 }
        $null = $shell.Popup($Message, 15, '原神日常自动化', $icon)
    } catch {
        Write-Host $Message
    }
}

try {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    if ($task.Principal.RunLevel -ne 'Highest' -or
        $task.Principal.LogonType -notin @('Interactive', 'InteractiveToken')) {
        throw "计划任务 $TaskName 的权限或登录模式不正确，请重新安装桌面启动器。"
    }

    if ($CheckOnly) {
        [pscustomobject]@{
            Ready = $true
            TaskName = $TaskName
            State = [string]$task.State
            RunLevel = [string]$task.Principal.RunLevel
            LogonType = [string]$task.Principal.LogonType
            AiRequired = $false
        } | ConvertTo-Json
        exit 0
    }

    if ($task.State -eq 'Running') {
        throw '自动化流程已经在运行，本次没有重复启动。'
    }

    $before = Read-CurrentRun
    $beforeRunId = if ($before) { [string]$before.runId } else { '' }
    $beforeTaskInfo = Get-ScheduledTaskInfo -TaskName $TaskName
    $startedAt = Get-Date
    Start-ScheduledTask -TaskName $TaskName

    $deadline = (Get-Date).AddSeconds(25)
    $newRun = $null
    do {
        Start-Sleep -Milliseconds 500
        $current = Read-CurrentRun
        if ($current -and [string]$current.runId -and [string]$current.runId -ne $beforeRunId) {
            $newRun = $current
            if ($current.outcome -eq 'failed' -and $current.executionOutcome -notin @(
                    'preflight', 'delaying', 'starting', 'running', 'stopping')) {
                $detail = if ($current.errors -and $current.errors.Count) {
                    [string]$current.errors[0]
                } else {
                    "运行状态为 $($current.executionOutcome)"
                }
                throw "自动化预检失败：$detail"
            }
            if ($current.executionOutcome -in @('delaying', 'starting', 'running')) {
                break
            }
        }
        $task = Get-ScheduledTask -TaskName $TaskName
        $taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName
        if ($task.State -ne 'Running' -and
            $taskInfo.LastRunTime -gt $beforeTaskInfo.LastRunTime -and
            $taskInfo.LastTaskResult -ne 267009) {
            throw "计划任务启动后立即退出，返回码 $($taskInfo.LastTaskResult)。"
        }
    } while ((Get-Date) -lt $deadline)

    if (-not $newRun) {
        throw '计划任务已触发，但 25 秒内没有生成新的运行记录。'
    }
    $message = "原神日常自动化已启动。`n运行编号：$($newRun.runId)`n无需保持 ChatGPT 或此窗口打开。"
    Show-LauncherMessage $message
    [pscustomobject]@{
        Started = $true
        RunId = [string]$newRun.runId
        StartedAt = $startedAt.ToString('o')
        AiRequired = $false
    } | ConvertTo-Json
    exit 0
} catch {
    New-Item -ItemType Directory -Path $LauncherLogDir -Force | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $logPath = Join-Path $LauncherLogDir "start-$stamp.log"
    $detail = $_.Exception.Message
    @(
        "Time: $((Get-Date).ToString('o'))"
        "Task: $TaskName"
        "Error: $detail"
    ) | Set-Content -LiteralPath $logPath -Encoding UTF8
    Show-LauncherMessage "启动失败：$detail`n`n错误记录：$logPath" $true
    Write-Error $detail
    exit 1
}
