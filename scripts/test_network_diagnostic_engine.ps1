[CmdletBinding()]
param([string]$SourceRoot = 'better-genshin-impact')
$ErrorActionPreference='Stop'
$Root=Split-Path -Parent $PSScriptRoot
$Source=if([System.IO.Path]::IsPathRooted($SourceRoot)){$SourceRoot}else{Join-Path $Root $SourceRoot}
if(Get-Process -Name BetterGI -ErrorAction SilentlyContinue){throw 'Exit BetterGI before testhost; singleton IPC is shared.'}
$TestFile=Join-Path $Source 'Test/BetterGenshinImpact.UnitTest/GameTaskTests/NetworkDisconnectEvidenceTests.cs'
if(-not(Test-Path -LiteralPath $TestFile)){throw 'Seventh diagnostic overlay test source missing.'}
$Filter='(FullyQualifiedName~NetworkDisconnectEvidenceTests|FullyQualifiedName~ShieldAvatarIdentityTests|FullyQualifiedName~DomainCombatSafetyTests)&Fixture!=PrivateNetworkDisconnect&Fixture!=PrivateProtectedLoading'
& dotnet test (Join-Path $Source 'Test/BetterGenshinImpact.UnitTest/BetterGenshinImpact.UnitTest.csproj') -c Release -p:Platform=x64 --no-build --nologo -v minimal --filter $Filter
exit $LASTEXITCODE
