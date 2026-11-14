param(
    [string]$Python = "python",
    [string]$Launcher = "dist/AmagadonLauncher.exe"
)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    if (-not (Test-Path -LiteralPath $Launcher)) { throw "Build launcher first: $Launcher" }
    $before = (Get-FileHash src/SelectionRuntime.cs -Algorithm SHA256).Hash
    & $Python scripts/build-selection-runtime.py
    if ($LASTEXITCODE -ne 0) { throw 'Runtime generation failed' }
    if ((Get-FileHash src/SelectionRuntime.cs -Algorithm SHA256).Hash -ne $before) {
        throw 'Generated runtime changed. Rebuild and review before running the suite.'
    }
    foreach ($script in @('scripts/test-simulation-isolation.py', 'scripts/test-selection-runtime.py', 'scripts/test-path-production.py', 'scripts/test-unit-lifecycle.py', 'scripts/test-native-scheduler.py', 'scripts/test-real-sprites.py', 'scripts/test-ai-plan-stages.py', 'scripts/test-combat-targets.py', 'scripts/test-battle-flow.py', 'scripts/test-attack-command-flow.py', 'scripts/test-special-attack-branches.py', 'scripts/test-ead-addon-parent.py', 'scripts/test-ead-ai.py')) {
        & $Python $script $Launcher
        if ($LASTEXITCODE -ne 0) { throw "Failed: $script" }
    }
    & $Python scripts/test-selection-sync-isolation.py
    if ($LASTEXITCODE -ne 0) { throw 'Selection isolation failed' }
    Write-Output 'PASS offline simulation regressions (not a full match)'
} finally { Pop-Location }
