param([string]$PackagePath = "")
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('AmagadonUpdate-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture | Out-Null
try {
    $package = Join-Path $fixture 'package.zip'
    if (-not $PackagePath) { $PackagePath = Join-Path $root 'dist\AmagadonLauncher.zip' }
    Copy-Item -LiteralPath $PackagePath -Destination $package
    $target = Join-Path $fixture 'success'
    New-Item -ItemType Directory -Path $target | Out-Null
    Set-Content (Join-Path $target 'user-settings.txt') 'keep'
    Set-Content (Join-Path $target 'AmagadonLauncher-0.0.1.exe') 'old versioned entrypoint'
    & "$PSScriptRoot\apply-update.ps1" -Package $package -Target $target -NoRestart -CurrentEntrypoint 'AmagadonLauncher-0.0.1.exe'
    $manifest = Get-Content (Join-Path $target 'package.json') -Raw | ConvertFrom-Json
    foreach ($file in $manifest.Files) {
        if ((Get-FileHash (Join-Path $target $file.Path)).Hash -ne $file.SHA256) { throw 'Installed file mismatch' }
    }
    if ((Get-Content (Join-Path $target 'user-settings.txt')) -ne 'keep') { throw 'Settings overwritten' }
    if ((Get-FileHash (Join-Path $target 'AmagadonLauncher-0.0.1.exe')).Hash -ne (Get-FileHash (Join-Path $target 'AmagadonLauncher.exe')).Hash) {throw 'Old entrypoint not upgraded'}
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
    # A headless stand-in for the new launcher proves the real restart path.
    $restartStage=Join-Path $fixture 'restart-stage'
    Expand-Archive -LiteralPath $package -DestinationPath $restartStage
    $testSource=Join-Path $fixture 'restart.cs'
    Set-Content -LiteralPath $testSource -Value 'using System;using System.IO;class Fixture{static void Main(){File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"restarted.txt"),Environment.CurrentDirectory);}}'
    $csc=Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
    & $csc /nologo /target:winexe /out:"$restartStage\AmagadonLauncher.exe" $testSource
    if($LASTEXITCODE -ne 0){throw 'Restart fixture build failed'}
    Copy-Item -LiteralPath (Join-Path $restartStage 'AmagadonLauncher.exe') -Destination (Join-Path $restartStage $manifest.Entrypoint) -Force
    foreach($file in $manifest.Files){$file.SHA256=(Get-FileHash (Join-Path $restartStage $file.Path)).Hash}
    $manifest | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $restartStage 'package.json') -Encoding UTF8
    $restartPackage=Join-Path $fixture 'restart.zip'
    Compress-Archive -Path "$restartStage\*" -DestinationPath $restartPackage
    $restartTarget=Join-Path $fixture 'restart-target'
    New-Item -ItemType Directory -Path $restartTarget | Out-Null
    & "$PSScriptRoot\apply-update.ps1" -Package $restartPackage -Target $restartTarget
    for($i=0;$i -lt 50 -and !(Test-Path (Join-Path $restartTarget 'restarted.txt'));$i++){Start-Sleep -Milliseconds 100}
    if(!(Test-Path (Join-Path $restartTarget 'restarted.txt'))){throw 'Updated launcher not restarted'}
    if((Get-Content (Join-Path $restartTarget 'restarted.txt')) -ne $restartTarget){throw 'Restart working directory mismatch'}
    Write-Output 'UPDATE TEST PASS: install hashes, settings preservation, old entrypoint replacement, locked-file rollback, updated launcher restart'
} finally {
    $resolved = [IO.Path]::GetFullPath($fixture)
    $parent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if (!$resolved.StartsWith($parent,[StringComparison]::OrdinalIgnoreCase) -or !(Split-Path $resolved -Leaf).StartsWith('AmagadonUpdate-')) { throw 'Unsafe fixture cleanup path' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
