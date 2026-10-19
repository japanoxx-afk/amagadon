param(
    [string]$Python = 'python',
    [string]$Probe = ''
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
if (-not $Probe) { $Probe = Join-Path $root 'test-game\Armageddon.probe.exe' }
if (-not (Test-Path -LiteralPath $Probe)) { throw 'Generate the isolated --replay probe first.' }
$fixture = Join-Path $root '.tools\ReplayTransportFixture.exe'
& $Python (Join-Path $PSScriptRoot 'prepare-replay-fixture.py') $Probe $fixture
if ($LASTEXITCODE -ne 0) { throw 'Replay fixture preparation failed' }
$launcher = Join-Path $root 'dist\AmagadonLauncher.exe'
$test = Start-Process $launcher -ArgumentList '--test-replay-process',('"'+$fixture+'"') -WindowStyle Hidden -Wait -PassThru
if ($test.ExitCode -ne 0) { throw 'Replay cross-process test failed; see launcher.log' }
Write-Output 'REPLAY PROCESS TEST PASS: native fixture record/playback, matching state, divergence fail-stop and explicit cancellation'
