[CmdletBinding()]
param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$taskName = 'GenshinCultivationScan'
try {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
    if ($task.Principal.RunLevel -ne 'Highest') { throw '培养扫描计划任务未配置最高权限。' }
    $cfg = Get-Content -LiteralPath (Join-Path $Root 'config\settings.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $python = if ($cfg.pythonExe) { $cfg.pythonExe } else { 'python' }
    & $python -B (Join-Path $PSScriptRoot 'cultivation.py') check-config (Join-Path $Root 'config\cultivation.json') --mode scan | Out-Null
    if ($LASTEXITCODE -ne 0) { throw '培养目标配置未通过检查。' }
    if ($CheckOnly) {
        [pscustomobject]@{Ready=$true;TaskName=$taskName;State=$task.State.ToString();ReadOnly=$true;AiRequired=$false} | ConvertTo-Json
        exit 0
    }
    if ($task.State -eq 'Running') { throw '培养扫描已在运行，没有重复启动。' }
    Start-ScheduledTask -TaskName $taskName
    Write-Host '已请求只读扫描。结果保存在 logs/runs/<runId>/cultivation-report.json；现有停止入口同样有效。'
} catch {
    $message = '培养扫描启动失败：' + $_.Exception.Message
    if (-not $CheckOnly) {
        try { $shell=New-Object -ComObject WScript.Shell; $null=$shell.Popup($message,20,'原神培养计划',16) } catch { Write-Host $message }
    }
    Write-Error $message
    exit 4
}
