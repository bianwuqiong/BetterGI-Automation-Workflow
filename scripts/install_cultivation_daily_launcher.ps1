[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principalContext = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principalContext.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '安装培养日常入口需要管理员权限。'
}
$taskName = 'GenshinCultivationDaily'
$previous = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($previous -and $previous.State -eq 'Running') { throw '培养日常正在运行，不能修改入口。' }
$powerShellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$actionArgs = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f (Join-Path $PSScriptRoot 'run_cultivation_daily_scheduled.ps1')
$action = New-ScheduledTaskAction -Execute $powerShellExe -Argument $actionArgs -WorkingDirectory $Root
$principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Highest
$taskSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 23)
Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $taskSettings `
    -Description '仅按需运行培养日常，依据目标与材料缺口分配已配置预算；没有定时触发器。' -Force | Out-Null
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) '原神瑞希培养日常.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $powerShellExe
$shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f (Join-Path $PSScriptRoot 'start_cultivation_daily_one_click.ps1')
$shortcut.WorkingDirectory = $Root
$shortcut.Description = '按角色培养缺口执行日常；使用配置预算，禁止脆弱树脂，无需AI'
$shortcut.Save()
[pscustomobject]@{Installed=$true;TaskName=$taskName;Shortcut=$shortcutPath;AiRequired=$false} | ConvertTo-Json
