param([int]$LauncherPid, [string]$Package, [string]$Target)
$ErrorActionPreference = 'Stop'
Wait-Process -Id $LauncherPid -ErrorAction SilentlyContinue
$stage = Join-Path ([IO.Path]::GetDirectoryName($Package)) 'expanded'
Expand-Archive -LiteralPath $Package -DestinationPath $stage -Force
$allowed = @('AmagadonLauncher.exe','PATCHNOTES.md','apply-update.ps1','compat\ddraw.dll','compat\LICENSE.cnc-ddraw')
$backup = Join-Path $Target ('update-backup-' + (Get-Date -Format 'yyyyMMddHHmmss'))
New-Item -ItemType Directory -Path $backup | Out-Null
$changed = @()
try {
    foreach ($name in $allowed) {
        $source = Join-Path $stage $name
        if (!(Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing update file: $name" }
    }
    foreach ($name in $allowed) {
        $dest = Join-Path $Target $name
        $old = Join-Path $backup $name
        New-Item -ItemType Directory -Force (Split-Path $dest),(Split-Path $old) | Out-Null
        if (Test-Path -LiteralPath $dest) { Copy-Item -LiteralPath $dest -Destination $old }
        $changed += $name
        Copy-Item -LiteralPath (Join-Path $stage $name) -Destination $dest -Force
    }
} catch {
    foreach ($name in $changed) {
        $old = Join-Path $backup $name
        if (Test-Path -LiteralPath $old) { Copy-Item -LiteralPath $old -Destination (Join-Path $Target $name) -Force }
    }
    $_ | Out-File (Join-Path $Target 'update-error.log')
    throw
}
Start-Process -FilePath (Join-Path $Target 'AmagadonLauncher.exe') -WorkingDirectory $Target -WindowStyle Normal
