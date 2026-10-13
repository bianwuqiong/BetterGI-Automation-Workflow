[CmdletBinding()]
param([string]$SourceRoot = 'better-genshin-impact')
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Source = if ([System.IO.Path]::IsPathRooted($SourceRoot)) { $SourceRoot } else { Join-Path $Root $SourceRoot }
if (Get-Process -Name BetterGI -ErrorAction SilentlyContinue) {
    throw 'Exit BetterGI before engine tests: testhost shares the singleton IPC endpoint.'
}
$Classes = @('SingleCondensedClaimSafetyTests', 'CondensedCraftPolicyTests', 'ArtifactClaimObservationTests',
    'SingleOriginal20ClaimSafetyTests', 'DomainCombatSafetyTests', 'ShieldAvatarIdentityTests',
    'GoToCraftingBenchTaskTests', 'CultivationCraftTaskTests')
foreach ($TestFile in @('AutoDomainTests/SingleCondensedClaimSafetyTests.cs', 'CommonTests/CondensedCraftPolicyTests.cs', 'AutoDomainTests/ArtifactClaimObservationTests.cs')) {
    if (-not (Test-Path -LiteralPath (Join-Path $Source ('Test/BetterGenshinImpact.UnitTest/GameTaskTests/' + $TestFile)))) {
        throw ('Fifth overlay test source missing: ' + $TestFile)
    }
}
$Filter = '(' + (($Classes | ForEach-Object { 'FullyQualifiedName~' + $_ }) -join '|') + ')&Fixture!=PrivateProtectedLoading&Fixture!=PrivateCharacterTalent'
& dotnet test (Join-Path $Source 'Test/BetterGenshinImpact.UnitTest/BetterGenshinImpact.UnitTest.csproj') -c Release -p:Platform=x64 --no-build --nologo -v minimal --filter $Filter
exit $LASTEXITCODE
