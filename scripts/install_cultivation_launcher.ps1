[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principalContext = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principalContext.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '安装只读培养入口需要管理员权限。'
}
$taskName = 'GenshinCultivationScan'
$previous = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($previous -and $previous.State -eq 'Running') { throw '培养扫描正在运行，不能修改入口。' }
$powerShellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$actionArgs = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -Mode scan' -f (Join-Path $PSScriptRoot 'run_cultivation.ps1')
$action = New-ScheduledTaskAction -Execute $powerShellExe -Argument $actionArgs -WorkingDirectory $Root
$principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Highest
$taskSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 22)
Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $taskSettings `
    -Description '仅按需读取原神角色和材料库存，生成培养计划；不刷取、不领奖、不合成。' -Force | Out-Null
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) '原神培养计划（只读扫描）.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $powerShellExe
$shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f (Join-Path $PSScriptRoot 'start_cultivation_one_click.ps1')
$shortcut.WorkingDirectory = $Root
$shortcut.Description = '读取目标角色、当前武器和相关材料；不消耗树脂'
$shortcut.Save()
[pscustomobject]@{Installed=$true;TaskName=$taskName;Shortcut=$shortcutPath;ReadOnly=$true} | ConvertTo-Json
