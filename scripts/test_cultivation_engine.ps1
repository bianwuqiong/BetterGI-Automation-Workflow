[CmdletBinding()]
param([string]$SourceRoot = 'better-genshin-impact')
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Source = if ([System.IO.Path]::IsPathRooted($SourceRoot)) { $SourceRoot } else { Join-Path $Root $SourceRoot }
$Manifest = Get-Content -LiteralPath (Join-Path $Root 'docs/TRANSFER_MANIFEST_2026-10-11.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$Classes = @($Manifest.modifiedSourceFiles | Where-Object {
    $_ -like 'Test/BetterGenshinImpact.UnitTest/*Tests.cs' -and
    $_ -notlike '*/ResinSnapshotImageTests.cs'
} | ForEach-Object { [System.IO.Path]::GetFileNameWithoutExtension($_) } | Sort-Object -Unique)
if ($Classes.Count -eq 0) { throw 'No development regression tests found in manifest.' }
$Filter = '(' + (($Classes | ForEach-Object { 'FullyQualifiedName~' + $_ }) -join '|') + ')&Fixture!=PrivateProtectedLoading&FullyQualifiedName!~TpAreaSelectionTests.RealRegionMenuFramesRequireTheNormalMapControls'
Write-Host ('Run ' + $Classes.Count + ' development test classes; private loading, resin and region-menu image tests excluded.')
& dotnet test (Join-Path $Source 'Test/BetterGenshinImpact.UnitTest/BetterGenshinImpact.UnitTest.csproj') -c Release --nologo -v minimal --filter $Filter
exit $LASTEXITCODE
