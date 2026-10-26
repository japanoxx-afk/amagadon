param([Parameter(Mandatory=$true)][string]$Launcher,[Parameter(Mandatory=$true)][string]$Original)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$out=Join-Path $root '.tools\editor-patch-tests'
New-Item -ItemType Directory -Force $out | Out-Null
Copy-Item -LiteralPath $Launcher -Destination (Join-Path $out 'AmagadonLauncher.exe') -Force
$csc=Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
& $csc /nologo /platform:x86 /reference:"$out\AmagadonLauncher.exe" /out:"$out\EditorPatchFixture.exe" "$PSScriptRoot\editor-patch-fixture.cs"
if($LASTEXITCODE -ne 0){throw 'Editor patch fixture compile failed'}
& "$out\EditorPatchFixture.exe" $Original
if($LASTEXITCODE -ne 0){throw 'Editor patch fixture failed'}
