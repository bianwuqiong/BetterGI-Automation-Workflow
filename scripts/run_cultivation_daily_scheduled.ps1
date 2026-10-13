[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$exitCode = 4
$runIdBefore = ''
try {
    if (Test-Path (Join-Path $Root 'state\current-run.json')) {
        $runIdBefore = [string]((Get-Content (Join-Path $Root 'state\current-run.json') -Raw -Encoding UTF8 | ConvertFrom-Json).runId)
    }
    & (Join-Path $PSScriptRoot 'run_daily.ps1') -Profile cultivation -CultivationMode execute -NoDelay -TimeoutMinutes 20
    $exitCode = $LASTEXITCODE
} catch {
    Write-Host ('培养日常启动失败：' + $_.Exception.Message)
} finally {
    try {
        $current = Get-Content (Join-Path $Root 'state\current-run.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([string]$current.runId -ne $runIdBefore -and $current.profile -eq 'cultivation') {
            $message = '运行编号：' + $current.runId + "`n结果：" + $current.outcome + "`n详情：logs/runs/" + $current.runId
        } else { $message = '培养日常未启动，返回码：' + $exitCode }
        $shell = New-Object -ComObject WScript.Shell
        $null = $shell.Popup($message, 20, '原神培养日常', $(if ($exitCode -eq 0) {64} else {48}))
    } catch { Write-Host '请查看 state/current-run.json 了解运行结果。' }
}
exit $exitCode
