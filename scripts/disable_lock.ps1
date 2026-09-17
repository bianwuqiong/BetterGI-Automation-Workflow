# =====================================================================
# disable_lock.ps1 - one-time: prevent Windows from locking/sleeping
# during unattended automation runs (remote-control scenario).
# Needs admin. Run once; settings persist.
# =====================================================================
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Write-Host "FATAL: need admin"; exit 2 }

Write-Host "1) disable inactivity auto-lock (InactivityTimeoutSecs=0)"
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v InactivityTimeoutSecs /t REG_DWORD /d 0 /f | Out-Null

Write-Host "2) disable console lock on wake/resume (consolelock=0)"
powercfg /setacvalueindex scheme_current sub_none consolelock 0 | Out-Null
powercfg /setactive scheme_current | Out-Null

Write-Host "3) disable sleep on AC (standby 0)"
powercfg /change standby-timeout-ac 0

Write-Host "4) disable display-off on AC (monitor 0)"
powercfg /change monitor-timeout-ac 0

Write-Host "done. verification:"
reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v InactivityTimeoutSecs
powercfg /q scheme_current sub_none | Select-String -Pattern "Console lock|唤醒|锁定" -Context 0,2
exit 0
