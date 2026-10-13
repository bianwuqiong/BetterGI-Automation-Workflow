[CmdletBinding()]
param(
    [ValidateSet('core', 'extras', 'configured', 'cultivation', 'combat-rehearsal','material-route','material-route-session','material-recovery','party-preparation')][string]$Profile = 'core',
    [ValidateSet('scan', 'execute')][string]$CultivationMode = 'scan',
    [ValidateSet('培养材料')][string]$Task,
    [string]$RouteSessionConfig,
    [string]$RecoveryConfig,
    [string]$PreparationConfig,
    [string]$RouteConfig,
    [int]$TimeoutMinutes = 0,
    [switch]$DryRun,
    [switch]$DebugRecording,
    [switch]$CultivationTalentPreview,
    [ValidateSet('normal-attack','elemental-skill','elemental-burst')][string]$TalentType = 'elemental-skill',
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$SettingsPath = Join-Path $Root 'config\settings.json'
$SupervisorLogDir = Join-Path $Root 'logs\recording-supervisor'
New-Item -ItemType Directory -Path $SupervisorLogDir -Force | Out-Null
$SupervisorLog = Join-Path $SupervisorLogDir ('recorded-core-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')

function Write-SupervisorLog([string]$Message) {
    ('{0:o} {1}' -f (Get-Date), $Message) | Add-Content -LiteralPath $SupervisorLog -Encoding UTF8
}

function Read-JsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try {
        return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Write-AtomicJson([string]$Path, $Value) {
    $temporary = $Path + '.' + $PID + '.tmp'
    $Value | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Find-Executable([string]$Configured, [string]$CommandName) {
    if ($Configured -and (Test-Path -LiteralPath $Configured -PathType Leaf)) {
        return (Resolve-Path -LiteralPath $Configured).Path
    }
    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    throw "找不到 $CommandName。请在 config/settings.json 中配置 recordingFfmpegExe。"
}

function Get-ConfiguredGameProcesses($Config) {
    $found = @()
    foreach ($name in @($Config.gameProcessNames)) {
        $found += @(Get-Process -Name $name -ErrorAction SilentlyContinue)
    }
    return @($found | Sort-Object Id -Unique)
}

function Request-WorkflowStop($Config) {
    try {
        $python = if ($Config.pythonExe) { [string]$Config.pythonExe } else { 'python' }
        $output = & $python (Join-Path $PSScriptRoot 'workflow.py') --root $Root stop 2>&1
        Write-SupervisorLog ('已请求工作流停止：' + (($output | Out-String).Trim()))
    } catch {
        Write-SupervisorLog ('请求工作流停止失败：' + $_.Exception.Message)
    }
}

function Attach-RecordingToResults([string]$RunId, $Recording) {
    if (-not $RunId) { return }
    $paths = @(
        (Join-Path $Root "logs\runs\$RunId\result.json"),
        (Join-Path $Root 'state\current-run.json'),
        (Join-Path $Root 'results.json')
    )
    foreach ($path in $paths) {
        $document = Read-JsonFile $path
        if ($document -and [string]$document.runId -eq $RunId) {
            $document | Add-Member -NotePropertyName recording -NotePropertyValue $Recording -Force
            Write-AtomicJson $path $document
        }
    }
}

$config = Read-JsonFile $SettingsPath
if (-not $config) { throw "无法读取 $SettingsPath" }
$executionMode = [string]$config.executionMode
$ffmpeg = Find-Executable ([string]$config.recordingFfmpegExe) 'ffmpeg'
$ffprobe = Find-Executable ([string]$config.recordingFfprobeExe) 'ffprobe'
$frameRate = [Math]::Max(1, [Math]::Min(30, [int]($config.recordingFrameRate | ForEach-Object { if ($_){$_}else{15} })))
$outputWidth = [Math]::Max(640, [Math]::Min(1920, [int]($config.recordingWidth | ForEach-Object { if ($_){$_}else{1280} })))
$quality = [Math]::Max(18, [Math]::Min(40, [int]($config.recordingQuality | ForEach-Object { if ($_){$_}else{30} })))
$averageKbps = 0
$maximumKbps = 0
if ($DebugRecording) {
    $frameRate = 8
    $outputWidth = 960
    $quality = 32
    $averageKbps = 400
    $maximumKbps = 500
}
$windowTimeoutSec = [Math]::Max(30, [Math]::Min(300, [int]($config.recordingWindowTimeoutSec | ForEach-Object { if ($_){$_}else{120} })))
$minimumFrameCoverage = [Math]::Max(0.1, [Math]::Min(1.0,
    [double]($config.recordingMinimumFrameCoverage | ForEach-Object { if ($_){$_}else{0.7} })))
if ($CultivationTalentPreview -and ($Profile -ne 'cultivation' -or $CultivationMode -ne 'scan')) {
    throw '天赋录屏预览仅允许cultivation scan零预算。'
}

if ($CheckOnly) {
    [pscustomobject]@{
        Ready = $true
        ExecutionMode = 'foreground'
        DefaultConfigExecutionMode = $executionMode
        Ffmpeg = $ffmpeg
        Ffprobe = $ffprobe
        FrameRate = $frameRate
        OutputWidth = $outputWidth
        Quality = $quality
        AverageKbps = $averageKbps
        MaximumKbps = $maximumKbps
        StartupRecordingSkipped = [bool]$DebugRecording
        MinimumFrameCoverage = $minimumFrameCoverage
        WindowTimeoutSec = $windowTimeoutSec
        Codec = 'h264_nvenc'
        Priority = 'AboveNormal'
        InputQueueFrames = 4
        StatsDisabled = $true
    } | ConvertTo-Json
    exit 0
}

Write-SupervisorLog ("带录屏工作流显式使用 foreground 前台模式（全局默认配置为 $executionMode）。")

$currentPath = Join-Path $Root 'state\current-run.json'
$before = Read-JsonFile $currentPath
$beforeRunId = if ($before) { [string]$before.runId } else { '' }
$runId = ''
$runDirectory = ''
$gameSeenAt = $null
$gameProcess = $null
$recorder = $null
$recordingPath = ''
$recordingStartedAt = $null
$recordingStoppedAt = $null
$recordingError = ''
$recorderTerminationDetail = ''
$recorderPriorityApplied = $false
$stopRequested = $false

$workflowInfo = New-Object System.Diagnostics.ProcessStartInfo
$workflowInfo.FileName = if ($config.pythonExe) { [string]$config.pythonExe } else { (Get-Command python -ErrorAction Stop).Source }
$workflowArguments = '-B "{0}" --root "{1}" run --no-delay --profile {2} --execution-mode foreground' -f `
    (Join-Path $PSScriptRoot 'workflow.py'), $Root, $Profile
if ($Profile -eq 'cultivation') { $workflowArguments += ' --cultivation-mode ' + $CultivationMode }
if ($CultivationTalentPreview) {
    if ($Profile -ne 'cultivation' -or $CultivationMode -ne 'scan') { throw '天赋录屏预览仅允许cultivation scan零预算。' }
    $workflowArguments += ' --cultivation-talent-preview --talent-type ' + $TalentType
}
if ($Task) {
    if ($Profile -ne 'cultivation') { throw '录屏单节点只允许 cultivation 档的培养材料。' }
    $workflowArguments += ' --task "培养材料"'
}
if ($RouteConfig) {
    if ($RouteConfig.IndexOf('"') -ge 0 -or $RouteConfig.Contains("`r") -or $RouteConfig.Contains("`n")) {
        throw '单段路线配置路径包含无效字符。'
    }
    $routeConfigPath = if ([IO.Path]::IsPathRooted($RouteConfig)) { $RouteConfig } else { Join-Path $Root $RouteConfig }
    if (-not (Test-Path -LiteralPath $routeConfigPath -PathType Leaf)) { throw '单段路线配置文件不存在。' }
    $routeConfigPath = (Resolve-Path -LiteralPath $routeConfigPath).Path
    $workflowArguments += ' --route-config "' + $routeConfigPath + '"'
}
if ($RouteSessionConfig) {
    if ($RouteSessionConfig.IndexOf('"') -ge 0 -or $RouteSessionConfig.Contains("`r") -or $RouteSessionConfig.Contains("`n")) {
        throw '路线会话配置路径包含无效字符。'
    }
    $sessionConfigPath = if ([IO.Path]::IsPathRooted($RouteSessionConfig)) { $RouteSessionConfig } else { Join-Path $Root $RouteSessionConfig }
    if (-not (Test-Path -LiteralPath $sessionConfigPath -PathType Leaf)) { throw '路线会话配置文件不存在。' }
    $sessionConfigPath = (Resolve-Path -LiteralPath $sessionConfigPath).Path
    $workflowArguments += ' --route-session-config "' + $sessionConfigPath + '"'
}
if ($RecoveryConfig) {
    if ($RecoveryConfig.IndexOf('"') -ge 0 -or $RecoveryConfig.Contains("`r") -or $RecoveryConfig.Contains("`n")) {
        throw '安全恢复配置路径包含无效字符。'
    }
    $recoveryConfigPath = if ([IO.Path]::IsPathRooted($RecoveryConfig)) { $RecoveryConfig } else { Join-Path $Root $RecoveryConfig }
    if (-not (Test-Path -LiteralPath $recoveryConfigPath -PathType Leaf)) { throw '安全恢复配置文件不存在。' }
    $recoveryConfigPath = (Resolve-Path -LiteralPath $recoveryConfigPath).Path
    $workflowArguments += ' --recovery-config "' + $recoveryConfigPath + '"'
}
if ($PreparationConfig) {
    if ($PreparationConfig.IndexOf('"') -ge 0 -or $PreparationConfig.Contains("`r") -or $PreparationConfig.Contains("`n")) {
        throw '队伍恢复配置路径包含无效字符。'
    }
    $preparationConfigPath = if ([IO.Path]::IsPathRooted($PreparationConfig)) { $PreparationConfig } else { Join-Path $Root $PreparationConfig }
    if (-not (Test-Path -LiteralPath $preparationConfigPath -PathType Leaf)) { throw '队伍恢复配置文件不存在。' }
    $preparationConfigPath = (Resolve-Path -LiteralPath $preparationConfigPath).Path
    $workflowArguments += ' --preparation-config "' + $preparationConfigPath + '"'
}
if ($Profile -eq 'party-preparation' -and $TimeoutMinutes -le 0) { $TimeoutMinutes = 5 }
if ($Profile -eq 'party-preparation' -and $TimeoutMinutes -gt 5) { throw '队伍恢复整轮预算不能超过5分钟。' }
if ($TimeoutMinutes -gt 0) { $workflowArguments += ' --timeout-minutes ' + $TimeoutMinutes }
if ($DryRun) { $workflowArguments += ' --dry-run' }
$workflowInfo.Arguments = $workflowArguments
$workflowInfo.WorkingDirectory = $Root
$workflowInfo.UseShellExecute = $false
$workflowInfo.CreateNoWindow = $true
$workflowInfo.RedirectStandardOutput = $true
$workflowInfo.RedirectStandardError = $true

$workflow = New-Object System.Diagnostics.Process
$workflow.StartInfo = $workflowInfo
if (-not $workflow.Start()) { throw '无法启动本地工作流。' }
Write-SupervisorLog ("工作流进程已启动：PID=$($workflow.Id)，profile=$Profile，dryRun=$DryRun")

try {
    while (-not $workflow.HasExited) {
        if (-not $runId) {
            $current = Read-JsonFile $currentPath
            if ($current -and [string]$current.runId -and [string]$current.runId -ne $beforeRunId) {
                $runId = [string]$current.runId
                $runDirectory = Join-Path $Root "logs\runs\$runId"
                Write-SupervisorLog ("已关联运行：$runId")
            }
        }

        if (-not $DryRun -and -not $recorder -and -not $recordingError -and $runId) {
            $gameCandidates = @(Get-ConfiguredGameProcesses $config)
            if ($gameCandidates.Count -gt 0 -and -not $gameSeenAt) {
                $gameSeenAt = Get-Date
                Write-SupervisorLog ('检测到原神进程，等待主窗口。')
            }
            $gameProcess = $gameCandidates | Where-Object { $_.MainWindowHandle -ne 0 } |
                Sort-Object StartTime | Select-Object -First 1

            if ($gameProcess) {
                if ($DebugRecording) {
                    $python = if ($config.pythonExe) { [string]$config.pythonExe } else { 'python' }
                    & $python -B (Join-Path $PSScriptRoot 'recording_readiness.py') --root $Root --run-id $runId
                    if ($LASTEXITCODE -ne 0) { Start-Sleep -Milliseconds 500; continue }
                }
                New-Item -ItemType Directory -Path $runDirectory -Force | Out-Null
                $recordingPath = Join-Path $runDirectory 'genshin-window.mkv'
                $windowHandle = '0x{0:X}' -f $gameProcess.MainWindowHandle.ToInt64()
                $recorderInfo = New-Object System.Diagnostics.ProcessStartInfo
                $recorderInfo.FileName = $ffmpeg
                $recorderInfo.Arguments = ('-hide_banner -nostats -loglevel error -y ' +
                    '-thread_queue_size 4 -rtbufsize 64M -f gdigrab -framerate {0} ' +
                    '-draw_mouse 0 -i hwnd={1} -vf scale={2}:-2:flags=fast_bilinear ' +
                    '-c:v h264_nvenc -preset p4 -rc vbr -cq {3} -b:v 0 -pix_fmt yuv420p ' +
                    '-an -f matroska "{4}"') -f $frameRate, $windowHandle, $outputWidth, $quality, $recordingPath
                if ($DebugRecording) {
                    $recorderInfo.Arguments = $recorderInfo.Arguments.Replace('-b:v 0', ('-b:v {0}k -maxrate {1}k -bufsize {2}k' -f $averageKbps, $maximumKbps, ($maximumKbps * 2)))
                }
                $recorderInfo.WorkingDirectory = $Root
                $recorderInfo.UseShellExecute = $false
                $recorderInfo.CreateNoWindow = $true
                $recorderInfo.RedirectStandardInput = $true
                $recorderInfo.RedirectStandardError = $true
                $recorder = New-Object System.Diagnostics.Process
                $recorder.StartInfo = $recorderInfo
                if (-not $recorder.Start()) { throw '无法启动 FFmpeg 录屏。' }
                try {
                    $recorder.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::AboveNormal
                    $recorderPriorityApplied = $true
                } catch {
                    Write-SupervisorLog ('设置 FFmpeg AboveNormal 优先级失败，继续录制：' + $_.Exception.Message)
                }
                $recordingStartedAt = Get-Date
                Write-SupervisorLog ("录屏已启动：PID=$($recorder.Id)，gamePid=$($gameProcess.Id)，hwnd=$windowHandle")
                Start-Sleep -Seconds 3
                if ($recorder.HasExited) {
                    $recordingError = ($recorder.StandardError.ReadToEnd()).Trim()
                    if (-not $recordingError) { $recordingError = "FFmpeg 提前退出，代码 $($recorder.ExitCode)" }
                    Write-SupervisorLog ('录屏启动失败：' + $recordingError)
                    Request-WorkflowStop $config
                    $stopRequested = $true
                }
            } elseif ($gameSeenAt -and ((Get-Date) - $gameSeenAt).TotalSeconds -ge $windowTimeoutSec) {
                $recordingError = "检测到原神进程后 $windowTimeoutSec 秒内未找到可录制主窗口。"
                Write-SupervisorLog $recordingError
                Request-WorkflowStop $config
                $stopRequested = $true
            }
        }

        if ($recorder -and $recorder.HasExited -and -not $recordingStoppedAt) {
            $recordingStoppedAt = Get-Date
            $remainingGameProcesses = @(Get-ConfiguredGameProcesses $config)
            $remainingGameWindows = @($remainingGameProcesses | Where-Object { $_.MainWindowHandle -ne 0 })
            $currentRun = Read-JsonFile $currentPath
            $activeStates = @('preflight', 'delaying', 'starting', 'running')
            $workflowEnding = ($workflow.HasExited -or -not $currentRun -or
                [string]$currentRun.executionOutcome -notin $activeStates)
            $exitDetail = ($recorder.StandardError.ReadToEnd()).Trim()
            if ($remainingGameWindows.Count -eq 0 -or $workflowEnding) {
                $recorderTerminationDetail = $exitDetail
                Write-SupervisorLog '原神录制窗口已关闭或工作流正在收尾；等待 ffprobe 验证已有录像。'
            } else {
                if (-not $recordingError) {
                    $recordingError = $exitDetail
                    if (-not $recordingError) { $recordingError = "FFmpeg 意外退出，代码 $($recorder.ExitCode)" }
                }
                Write-SupervisorLog ('录屏在工作流结束前退出：' + $recordingError)
                if (-not $stopRequested) {
                    Request-WorkflowStop $config
                    $stopRequested = $true
                }
            }
        }
        Start-Sleep -Seconds 1
    }
} finally {
    if ($recorder -and -not $recorder.HasExited) {
        try {
            $recorder.StandardInput.WriteLine('q')
            $recorder.StandardInput.Flush()
            if (-not $recorder.WaitForExit(15000)) {
                $recorder.Kill()
                $recorder.WaitForExit()
                if (-not $recordingError) { $recordingError = 'FFmpeg 未能正常收尾，已强制结束。' }
            }
        } catch {
            if (-not $recordingError) { $recordingError = '结束 FFmpeg 失败：' + $_.Exception.Message }
        }
    }
    if ($recorder -and -not $recordingStoppedAt) { $recordingStoppedAt = Get-Date }
}

$workflow.WaitForExit()
$workflowOutput = $workflow.StandardOutput.ReadToEnd().Trim()
$workflowError = $workflow.StandardError.ReadToEnd().Trim()
if ($workflowOutput) { Write-SupervisorLog ('工作流输出：' + $workflowOutput) }
if ($workflowError) { Write-SupervisorLog ('工作流错误：' + $workflowError) }

$probe = $null
if ($recordingPath -and (Test-Path -LiteralPath $recordingPath -PathType Leaf)) {
    try {
        $probeText = & $ffprobe -v error -count_frames -select_streams v:0 `
            -show_entries 'stream=codec_name,width,height,avg_frame_rate,nb_read_frames:format=duration,size' `
            -of json $recordingPath 2>&1
        if ($LASTEXITCODE -eq 0) { $probe = ($probeText | Out-String | ConvertFrom-Json) }
        elseif (-not $recordingError) { $recordingError = ($probeText | Out-String).Trim() }
    } catch {
        if (-not $recordingError) { $recordingError = 'ffprobe 验证失败：' + $_.Exception.Message }
    }
}

$fileBytes = 0
if ($recordingPath -and (Test-Path -LiteralPath $recordingPath -PathType Leaf)) {
    $fileBytes = (Get-Item -LiteralPath $recordingPath).Length
}
$videoStream = if ($probe -and @($probe.streams).Count -gt 0) { @($probe.streams)[0] } else { $null }
$probeValid = [bool]($videoStream -and [double]$probe.format.duration -gt 0 -and
    [long]$videoStream.nb_read_frames -gt 0)
$durationSeconds = if ($probeValid) { [double]$probe.format.duration } else { 0.0 }
$recordedFrames = if ($probeValid) { [long]$videoStream.nb_read_frames } else { 0L }
$expectedFrames = [long][Math]::Floor($durationSeconds * $frameRate)
$frameCoverage = if ($expectedFrames -gt 0) { $recordedFrames / [double]$expectedFrames } else { 0.0 }
$actualFrameRate = if ($durationSeconds -gt 0) { $recordedFrames / $durationSeconds } else { 0.0 }
$frameCoveragePassed = [bool]($probeValid -and $frameCoverage -ge $minimumFrameCoverage)
if ($recordingStartedAt -and $fileBytes -gt 0 -and -not $probeValid -and -not $recordingError) {
    $recordingError = '录屏文件未通过 ffprobe 时长与帧数验证。'
}
if ($probeValid -and -not $frameCoveragePassed -and -not $recordingError) {
    $recordingError = ('录屏帧覆盖率 {0:P1} 低于要求 {1:P0}；文件可播放但画面不连续。' -f `
        $frameCoverage, $minimumFrameCoverage)
}
$recording = [ordered]@{
    schemaVersion = 1
    requested = (-not $DryRun)
    started = [bool]$recordingStartedAt
    complete = [bool]($recordingStartedAt -and $fileBytes -gt 0 -and $probeValid -and
        $frameCoveragePassed -and -not $recordingError)
    file = $recordingPath
    bytes = $fileBytes
    gamePid = if ($gameProcess) { $gameProcess.Id } else { $null }
    ffmpegPid = if ($recorder) { $recorder.Id } else { $null }
    startedAt = if ($recordingStartedAt) { $recordingStartedAt.ToString('o') } else { $null }
    stoppedAt = if ($recordingStoppedAt) { $recordingStoppedAt.ToString('o') } else { $null }
    settings = [ordered]@{ frameRate = $frameRate; outputWidth = $outputWidth; quality = $quality; codec = 'h264_nvenc'; audio = $false; priority = 'AboveNormal'; priorityApplied = $recorderPriorityApplied; inputQueueFrames = 4; statsDisabled = $true; debugRecording = [bool]$DebugRecording; startupRecordingSkipped = [bool]$DebugRecording; averageKbps = $averageKbps; maximumKbps = $maximumKbps }
    probe = $probe
    expectedFrames = $expectedFrames
    frameCoverage = [Math]::Round($frameCoverage, 4)
    actualFrameRate = [Math]::Round($actualFrameRate, 3)
    minimumFrameCoverage = $minimumFrameCoverage
    frameCoveragePassed = $frameCoveragePassed
    error = if ($recordingError) { $recordingError } else { $null }
    terminationDetail = if ($recorderTerminationDetail) { $recorderTerminationDetail } else { $null }
    supervisorLog = $SupervisorLog
}

if ($runId) {
    Write-AtomicJson (Join-Path $runDirectory 'recording.json') $recording
    Attach-RecordingToResults $runId $recording
}
Write-SupervisorLog ("工作流结束：exitCode=$($workflow.ExitCode)，recordingComplete=$($recording.complete)")
$recording | ConvertTo-Json -Depth 20

if ($workflow.ExitCode -ne 0) { exit $workflow.ExitCode }
if (-not $DryRun -and -not $recording.complete) { exit 5 }
exit 0
