[CmdletBinding()]
param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$taskName = 'GenshinCultivationDaily'
try {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
    if ($task.Principal.RunLevel -ne 'Highest' -or $task.Principal.LogonType -notin @('Interactive','InteractiveToken')) {
        throw '培养日常计划任务的权限或登录模式不正确。'
    }
    $settings = Get-Content (Join-Path $Root 'config\settings.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $config = Get-Content (Join-Path $Root 'config\cultivation.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $python = if ($settings.pythonExe) { $settings.pythonExe } else { 'python' }
    & $python -B (Join-Path $PSScriptRoot 'cultivation.py') check-config (Join-Path $Root 'config\cultivation.json') --mode execute | Out-Null
    if ($LASTEXITCODE -ne 0) { throw '培养目标或执行预算配置未通过检查。' }
    if ($CheckOnly) {
        [pscustomobject]@{Ready=$true;TaskName=$taskName;State=[string]$task.State;ExecutionMode=$settings.executionMode;
            OriginalResinBudget=$config.policy.originalResinBudget;CondensedResinBudget=$config.policy.condensedResinBudget;
            ValidationMode=[bool]$config.policy.validationMode;AiRequired=$false} | ConvertTo-Json
        exit 0
    }
    if ($task.State -eq 'Running') { throw '培养日常已在运行，没有重复启动。' }
    Start-ScheduledTask -TaskName $taskName
    Write-Host '已请求培养日常；共享锁、预算核验与停止入口同样有效。'
} catch {
    $message = '培养日常启动失败：' + $_.Exception.Message
    if (-not $CheckOnly) {
        try { $shell=New-Object -ComObject WScript.Shell; $null=$shell.Popup($message,20,'原神培养日常',16) } catch { Write-Host $message }
    }
    Write-Error $message
    exit 4
}
