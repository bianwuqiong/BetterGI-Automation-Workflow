[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$TaskName = 'GenshinDailyCore'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principalContext = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principalContext.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '安装一键启动器需要管理员权限。请在管理员 PowerShell 中重新运行此脚本。'
}

$powerShellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$dailyScript = Join-Path $PSScriptRoot 'run_daily_scheduled.ps1'
$startScript = Join-Path $PSScriptRoot 'start_daily_one_click.ps1'
$actionArguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $dailyScript
$action = New-ScheduledTaskAction -Execute $powerShellExe -Argument $actionArguments -WorkingDirectory $Root
$principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 40)

Register-ScheduledTask -TaskName $TaskName -Action $action -Principal $principal `
    -Settings $settings -Description '无需 AI 的 BetterGI 原神 core 日常；仅按需启动。' -Force | Out-Null

$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop '原神日常自动化.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $powerShellExe
$shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $startScript
$shortcut.WorkingDirectory = $Root
$gameExe = (Get-Content -LiteralPath (Join-Path $Root 'config\settings.json') -Raw -Encoding UTF8 |
    ConvertFrom-Json).gameExe
if ($gameExe -and (Test-Path -LiteralPath $gameExe)) {
    $shortcut.IconLocation = "$gameExe,0"
}
$shortcut.Description = '启动无需 AI 的 BetterGI 原神 core 日常'
$shortcut.Save()

[pscustomobject]@{
    Installed = $true
    TaskName = $TaskName
    Shortcut = $shortcutPath
    Action = "$powerShellExe $actionArguments"
} | ConvertTo-Json
