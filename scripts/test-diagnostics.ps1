param([Parameter(Mandatory=$true)][string]$Launcher)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$out=Join-Path $root '.tools\diagnostic-tests'
New-Item -ItemType Directory -Force $out | Out-Null
Copy-Item -LiteralPath $Launcher -Destination (Join-Path $out 'AmagadonLauncher.exe') -Force
New-Item -ItemType Directory -Force (Join-Path $out 'compat') | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'third-party\cnc-ddraw\ddraw.dll') -Destination (Join-Path $out 'compat\ddraw.dll') -Force
$fixture=Join-Path $out 'Amagadon.DiagnosticFixture.exe'
$csc=Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
& $csc /nologo /target:winexe /platform:x86 /reference:"$out\AmagadonLauncher.exe" /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll /out:"$fixture" "$PSScriptRoot\diagnostic-fixture.cs"
if($LASTEXITCODE -ne 0) {throw 'Diagnostic fixture build failed'}
$p=Start-Process -FilePath $fixture -WindowStyle Hidden -Wait -PassThru
$result=Get-Content -LiteralPath (Join-Path $out 'diagnostic-test-result.txt') -Raw
if($p.ExitCode -ne 0) {throw $result}
Write-Output $result
