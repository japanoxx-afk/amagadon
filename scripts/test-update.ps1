$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('AmagadonUpdate-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture | Out-Null
try {
    $package = Join-Path $fixture 'package.zip'
    Copy-Item (Join-Path $root 'dist\AmagadonLauncher.zip') $package
    $target = Join-Path $fixture 'success'
    New-Item -ItemType Directory -Path $target | Out-Null
    Set-Content (Join-Path $target 'user-settings.txt') 'keep'
    & "$PSScriptRoot\apply-update.ps1" -Package $package -Target $target -NoRestart
    $manifest = Get-Content (Join-Path $target 'package.json') -Raw | ConvertFrom-Json
    foreach ($file in $manifest.Files) {
        if ((Get-FileHash (Join-Path $target $file.Path)).Hash -ne $file.SHA256) { throw 'Installed file mismatch' }
    }
    if ((Get-Content (Join-Path $target 'user-settings.txt')) -ne 'keep') { throw 'Settings overwritten' }
    $rollback = Join-Path $fixture 'rollback'
    New-Item -ItemType Directory -Path $rollback | Out-Null
    Set-Content (Join-Path $rollback 'AmagadonLauncher.exe') 'original'
    $locked = Join-Path $rollback 'PATCHNOTES.md'
    Set-Content $locked 'original notes'
    $handle = [IO.File]::Open($locked,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    $rejected = $false
    try {
        try { & "$PSScriptRoot\apply-update.ps1" -Package $package -Target $rollback -NoRestart } catch { $rejected = $true }
    } finally { $handle.Dispose() }
    if (!$rejected) { throw 'Locked destination accepted' }
    if ((Get-Content (Join-Path $rollback 'AmagadonLauncher.exe')) -ne 'original') { throw 'Original launcher not restored' }
    if (Test-Path (Join-Path $rollback $manifest.Entrypoint)) { throw 'New launcher not rolled back' }
    if ((Get-Content $locked) -ne 'original notes') { throw 'Locked file changed' }
    Write-Output 'UPDATE TEST PASS: install hashes, settings preservation, locked-file rollback'
} finally {
    $resolved = [IO.Path]::GetFullPath($fixture)
    $parent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if (!$resolved.StartsWith($parent,[StringComparison]::OrdinalIgnoreCase) -or !(Split-Path $resolved -Leaf).StartsWith('AmagadonUpdate-')) { throw 'Unsafe fixture cleanup path' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
