param(
    [string]$Python = "python",
    [string]$Launcher = "dist/AmagadonLauncher.exe",
    [ValidateSet(0, 1, 2)][int[]]$Variants = @(0, 1, 2),
    [ValidateRange(1000, 200000)][int]$Ticks = 60000,
    [ValidateRange(0, 200000)][int]$CombatStartTick = 0,
    [ValidateRange(0, 200001)][int]$CombatWaveTick = 30000
)
$ErrorActionPreference = 'Stop'
$settings = @{
    PYTHONUTF8 = '1'
    AMAGADON_LAB_REAL_SPRITES = '1'
    AMAGADON_LAB_AI_PLAYERS = '3'
    AMAGADON_LAB_TICK_INSTRUCTIONS = '500000000'
    AMAGADON_LAB_VERIFY_EAD = '1'
    AMAGADON_LAB_COMBAT_PRESSURE = '1'
    AMAGADON_LAB_COMBAT_START_TICK = "$CombatStartTick"
    AMAGADON_LAB_COMBAT_WAVE_TICK = "$CombatWaveTick"
    AMAGADON_LAB_SUPPLEMENT_EAD_PARENT = '0'
    AMAGADON_LAB_TICKS = "$Ticks"
    AMAGADON_LAB_AI_VARIANT = '0'
}
$previous = @{}
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    if (-not (Test-Path -LiteralPath $Launcher)) { throw "Build launcher first: $Launcher" }
    if ($Variants.Count -eq 0) { throw 'At least one AI variant is required' }
    foreach ($key in $settings.Keys) {
        $previous[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
        [Environment]::SetEnvironmentVariable($key, $settings[$key], 'Process')
    }
    foreach ($variant in $Variants) {
        $env:AMAGADON_LAB_AI_VARIANT = "$variant"
        Write-Output "Ead$($variant + 1): native production and research, two peers, up to $Ticks ticks"
        & $Python scripts/diagnose-natural-ai.py $Launcher
        if ($LASTEXITCODE -ne 0) { throw "Ead$($variant + 1) incomplete or mismatched; inspect .tools/natural-ai-real-3-v$variant-*.json" }
    }
    Write-Output 'PASS requested EAD plans, actual air creation and research completion; controlled opponent, not a full match'
} finally {
    foreach ($key in $previous.Keys) {
        [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process')
    }
    Pop-Location
}
