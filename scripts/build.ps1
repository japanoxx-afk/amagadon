$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$out = Join-Path $root 'dist'
New-Item -ItemType Directory -Force $out | Out-Null
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
& $csc /nologo /target:winexe /platform:x86 /optimize+ /codepage:65001 /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll /reference:System.Net.Http.dll /out:"$out\AmagadonLauncher.exe" "$root\src\Launcher.cs"
if ($LASTEXITCODE -ne 0) { throw 'Compile failed' }
Copy-Item "$root\PATCHNOTES.md" $out -Force
Copy-Item "$root\scripts\apply-update.ps1" $out -Force
$vendor = Join-Path $out 'compat'
New-Item -ItemType Directory -Force $vendor | Out-Null
if ((Get-FileHash "$root\third-party\cnc-ddraw\ddraw.dll").Hash -ne '85E0F7D530DFDA134793A57CB3E76B0287DCC96892EE57162DD68F47283B03A9') { throw 'Compatibility DLL hash mismatch' }
Copy-Item "$root\third-party\cnc-ddraw\ddraw.dll" $vendor -Force
Copy-Item "$root\third-party\LICENSE.cnc-ddraw" $vendor -Force
Compress-Archive -Path "$out\AmagadonLauncher.exe","$out\PATCHNOTES.md","$out\apply-update.ps1","$out\compat" -DestinationPath "$out\AmagadonLauncher.zip" -Force
(Get-FileHash "$out\AmagadonLauncher.zip" -Algorithm SHA256).Hash.ToLower() | Set-Content "$out\AmagadonLauncher.zip.sha256" -Encoding ascii
