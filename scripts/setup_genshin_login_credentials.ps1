param(
    [ValidateSet('Enroll', 'Status', 'SelfTest')]
    [string]$Mode = 'Enroll'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceProject = Join-Path $projectRoot 'tools/genshin-login-credential-ui/GenshinLoginCredentialUI.csproj'
# Keep the existing enrollment and its encrypted receipt at the reviewed native broker location.
$privateOutput = Join-Path $projectRoot 'state/genshin-login-credential-ui/bin/Release/net8.0-windows'
$dotnetCommand = Get-Command dotnet -ErrorAction Stop
& $dotnetCommand.Source build $sourceProject -c Release -o $privateOutput --ignore-failed-sources
if ($LASTEXITCODE -ne 0) { throw 'Credential UI build failed; existing credentials were not changed.' }
$executable = Join-Path $privateOutput 'GenshinLoginCredentialUI.exe'

switch ($Mode) {
    'Enroll' {
        # This is a visible, human-operated dialog; the script never enters or saves credentials.
        $enrollmentProcess = Start-Process -FilePath $executable -ArgumentList '--enroll' -WindowStyle Normal -PassThru
        $enrollmentProcess.WaitForExit()
        if ($enrollmentProcess.ExitCode -ne 0) { throw 'Credential enrollment did not complete.' }
    }
    'Status' { & $executable --status; exit $LASTEXITCODE }
    'SelfTest' { & $executable --self-test; exit $LASTEXITCODE }
}
