[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Baseline,
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$WorkspaceRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$BaselineRoot = (Resolve-Path -LiteralPath $Baseline).Path
$SnapshotRoot = Join-Path $BaselineRoot 'production'

function Assert-NoReparseAncestor([string]$Path) {
    $candidate = [IO.Path]::GetFullPath($Path)
    while ($candidate) {
        $item = Get-Item -LiteralPath $candidate -Force -ErrorAction SilentlyContinue
        if ($item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Restore path contains a reparse point: $candidate"
        }
        $parent = [IO.Path]::GetDirectoryName($candidate)
        if ($parent -eq $candidate) { break }
        $candidate = $parent
    }
}

function Assert-WithinRoot([string]$Path, [string]$Root) {
    $prefix = $Root.TrimEnd([char[]]@('\', '/')) + [IO.Path]::DirectorySeparatorChar
    if (-not $Path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Restore path escaped its expected root.'
    }
}

Assert-NoReparseAncestor $SnapshotRoot
if (-not (Test-Path -LiteralPath $SnapshotRoot -PathType Container)) {
    throw 'Baseline production snapshot is missing.'
}
if (-not (Test-Path -LiteralPath (Join-Path $BaselineRoot 'manifest.json'))) {
    throw 'Baseline manifest is missing.'
}

$python = 'python'
$settingsPath = Join-Path $WorkspaceRoot 'config\settings.json'
if (Test-Path -LiteralPath $settingsPath) {
    $cfg = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($cfg.pythonExe) { $python = [string]$cfg.pythonExe }
}
$verifier = Join-Path $PSScriptRoot 'verify_version_baseline.py'
$restoreBackup = Join-Path $WorkspaceRoot ('backups\before-baseline-restore-' + [guid]::NewGuid().ToString('N'))
$lockStream = $null
try {
    $lockPath = Join-Path $WorkspaceRoot 'state\workflow.lock'
    Assert-NoReparseAncestor $lockPath
    New-Item -ItemType Directory -Path (Split-Path -Parent $lockPath) -Force | Out-Null
    try {
        # Exclusive sharing rejects the runner's existing byte-range lock handle
        # and prevents another runner from opening this same file during restore.
        $lockStream = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate,
            [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        if ($lockStream.Length -eq 0) { $lockStream.WriteByte(48); $lockStream.Flush() }
    } catch {
        throw 'Workflow lock is busy or unavailable; no files were restored.'
    }

    $busyNames = @('BetterGI', 'BetterGenshinImpact', 'GenshinImpact', 'YuanShen', 'HYP', 'HYPHelper', 'ffmpeg')
    $busy = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $busyNames -contains $_.ProcessName })
    $runningTasks = @(Get-ScheduledTask -TaskName 'GenshinDailyCore', 'GenshinDailyCoreRecorded', 'GenshinTaskRun' `
        -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Running' })
    if ($busy.Count -gt 0 -or $runningTasks.Count -gt 0) {
        throw 'Game, BetterGI, recorder, launcher, or workflow task is running; close it before restoring.'
    }

    & $python -B $verifier $BaselineRoot
    if ($LASTEXITCODE -ne 0) { throw 'Snapshot checksum verification failed; no files were restored.' }
    $inventory = Get-Content -LiteralPath (Join-Path $BaselineRoot 'files.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $plan = @()
    foreach ($entry in $inventory) {
        if (-not $entry.path.StartsWith('production/', [StringComparison]::Ordinal)) { continue }
        $relative = $entry.path.Substring('production/'.Length)
        if ($relative -ieq 'state/workflow.lock') { throw 'The workflow lock cannot be restored.' }
        $source = [IO.Path]::GetFullPath((Join-Path $SnapshotRoot $relative))
        $destination = [IO.Path]::GetFullPath((Join-Path $WorkspaceRoot $relative))
        $saved = [IO.Path]::GetFullPath((Join-Path $restoreBackup $relative))
        Assert-WithinRoot $source $SnapshotRoot
        Assert-WithinRoot $destination $WorkspaceRoot
        Assert-WithinRoot $saved $restoreBackup
        Assert-NoReparseAncestor $source
        Assert-NoReparseAncestor $destination
        Assert-NoReparseAncestor $saved
        if (Test-Path -LiteralPath $destination -PathType Container) {
            throw "Restore target is an existing directory: $destination"
        }
        $plan += [pscustomobject]@{ Source = $source; Destination = $destination; Saved = $saved }
    }
    if ($plan.Count -eq 0) { throw 'The baseline has no production files to restore.' }

    if (-not $Apply) {
        [pscustomobject]@{ Ready = $true; Applied = $false; Baseline = $BaselineRoot } | ConvertTo-Json
    } else {
        # Validate all paths before the first overwrite; preserve every old file.
        # No delete, mirror, or cleanup operation is used.
        New-Item -ItemType Directory -Path $restoreBackup -Force | Out-Null
        foreach ($item in $plan) {
            Assert-NoReparseAncestor $item.Source
            Assert-NoReparseAncestor $item.Destination
            Assert-NoReparseAncestor $item.Saved
            if (Test-Path -LiteralPath $item.Destination -PathType Leaf) {
                New-Item -ItemType Directory -Path (Split-Path -Parent $item.Saved) -Force | Out-Null
                Copy-Item -LiteralPath $item.Destination -Destination $item.Saved
            }
            New-Item -ItemType Directory -Path (Split-Path -Parent $item.Destination) -Force | Out-Null
            Copy-Item -LiteralPath $item.Source -Destination $item.Destination -Force
        }
        & $python -B $verifier $BaselineRoot --workspace $WorkspaceRoot
        if ($LASTEXITCODE -ne 0) { throw 'Restore comparison failed.' }
        [pscustomobject]@{ Applied = $true; Baseline = $BaselineRoot; PreviousFiles = $restoreBackup } | ConvertTo-Json
    }
} catch {
    throw ($_.Exception.Message + " Previous files, if any were replaced, are recoverable from: $restoreBackup")
} finally {
    if ($lockStream) { $lockStream.Dispose() }
}
