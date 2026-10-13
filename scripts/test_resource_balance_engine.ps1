[CmdletBinding()]
param([string]$SourceRoot = 'better-genshin-impact')
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Source = if ([System.IO.Path]::IsPathRooted($SourceRoot)) { $SourceRoot } else { Join-Path $Root $SourceRoot }
if (Get-Process -Name BetterGI -ErrorAction SilentlyContinue) {
    throw 'Exit BetterGI before testhost: the engine singleton IPC is shared.'
}
$Classes = @('MoraSnapshotEvidenceTests','WeaponExperienceInventoryRequestTests','BackpackInventoryEvidenceTests',
    'RecipeSlashCostEvidenceTests','CondensedCraftPolicyTests','GoToCraftingBenchTaskTests')
foreach ($Name in @('MoraSnapshotEvidenceTests','WeaponExperienceInventoryRequestTests')) {
    if (-not (Test-Path -LiteralPath (Join-Path $Source ('Test/BetterGenshinImpact.UnitTest/GameTaskTests/'+$Name+'.cs')))) {
        throw ('Sixth overlay test source missing: '+$Name)
    }
}
$Filter = '('+(($Classes | ForEach-Object {'FullyQualifiedName~'+$_}) -join '|')+')&Fixture!=PrivateMora'
& dotnet test (Join-Path $Source 'Test/BetterGenshinImpact.UnitTest/BetterGenshinImpact.UnitTest.csproj') -c Release -p:Platform=x64 --no-build --nologo -v minimal --filter $Filter
exit $LASTEXITCODE
