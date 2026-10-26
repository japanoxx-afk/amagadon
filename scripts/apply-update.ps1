param([int]$LauncherPid, [string]$Package, [string]$Target, [switch]$NoRestart, [string]$CurrentEntrypoint = '')
$ErrorActionPreference = 'Stop'
if ($CurrentEntrypoint -and $CurrentEntrypoint -ne 'AmagadonLauncher.exe' -and $CurrentEntrypoint -notmatch '^AmagadonLauncher-\d+\.\d+\.\d+(-preview)?\.exe$') { throw 'Invalid current entrypoint' }
if ($LauncherPid -gt 0) { Wait-Process -Id $LauncherPid -ErrorAction SilentlyContinue }
$stage = Join-Path ([IO.Path]::GetDirectoryName($Package)) ('expanded-' + [Guid]::NewGuid().ToString('N'))
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead($Package)
try {
    foreach ($entry in $archive.Entries) {
        $name = $entry.FullName.Replace('\','/')
        if ($name.StartsWith('/') -or $name.Contains(':') -or @($name.Split('/') | Where-Object { $_ -eq '..' }).Count -gt 0) { throw 'Unsafe archive path' }
    }
} finally { $archive.Dispose() }
Expand-Archive -LiteralPath $Package -DestinationPath $stage -Force
$manifest = Get-Content (Join-Path $stage 'package.json') -Raw | ConvertFrom-Json
if ($manifest.Entrypoint -notmatch '^AmagadonLauncher-\d+\.\d+\.\d+(-preview)?\.exe$' -or $manifest.Entrypoint -ne "AmagadonLauncher-$($manifest.Version).exe") { throw 'Invalid versioned entrypoint' }
$allowed = @('AmagadonLauncher.exe',$manifest.Entrypoint,'PATCHNOTES.md','apply-update.ps1','compat\ddraw.dll','compat\LICENSE.cnc-ddraw','compat\hd-preview.json','package.json')
foreach ($file in $manifest.Files) {
    if ($file.Path -notin $allowed -or $file.Path -eq 'package.json') { throw 'Unexpected update file' }
    if ((Get-FileHash -LiteralPath (Join-Path $stage $file.Path)).Hash -ne $file.SHA256) { throw "Update file hash mismatch: $($file.Path)" }
}
if (@($manifest.Files).Count -ne 7 -or @($manifest.Files.Path | Select-Object -Unique).Count -ne 7) { throw 'Incomplete update manifest' }
if ((Get-FileHash -LiteralPath (Join-Path $stage 'AmagadonLauncher.exe')).Hash -ne (Get-FileHash -LiteralPath (Join-Path $stage $manifest.Entrypoint)).Hash) { throw 'Launcher alias mismatch' }
$backup = Join-Path $Target ('update-backup-' + (Get-Date -Format 'yyyyMMddHHmmssfff'))
New-Item -ItemType Directory -Path $backup | Out-Null
$changed = @()
$installNames = @($allowed)
if ($CurrentEntrypoint -and $CurrentEntrypoint -notin $installNames) { $installNames += $CurrentEntrypoint }
try {
    foreach ($name in $allowed) {
        $source = Join-Path $stage $name
        if (!(Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing update file: $name" }
    }
    foreach ($name in $installNames) {
        $dest = Join-Path $Target $name
        $old = Join-Path $backup $name
        New-Item -ItemType Directory -Force (Split-Path $dest),(Split-Path $old) | Out-Null
        if (Test-Path -LiteralPath $dest) { Copy-Item -LiteralPath $dest -Destination $old }
        $changed += $name
        $sourceName = if ($name -eq $CurrentEntrypoint) { 'AmagadonLauncher.exe' } else { $name }
        Copy-Item -LiteralPath (Join-Path $stage $sourceName) -Destination $dest -Force
    }
} catch {
    $failure = $_
    foreach ($name in $changed) {
        $old = Join-Path $backup $name
        $dest = Join-Path $Target $name
        try {
            if (Test-Path -LiteralPath $old) {
                if (!(Test-Path -LiteralPath $dest) -or (Get-FileHash -LiteralPath $old).Hash -ne (Get-FileHash -LiteralPath $dest).Hash) { Copy-Item -LiteralPath $old -Destination $dest -Force }
            } elseif (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest }
        } catch { $_ | Out-File (Join-Path $Target 'update-rollback-error.log') -Append }
    }
    $failure | Out-File (Join-Path $Target 'update-error.log')
    throw $failure
}
if (!$NoRestart) { Start-Process -FilePath (Join-Path $Target $manifest.Entrypoint) -WorkingDirectory $Target -WindowStyle Normal }
