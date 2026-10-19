$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$out = Join-Path $root 'dist'
New-Item -ItemType Directory -Force $out | Out-Null
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
& $csc /nologo /target:winexe /platform:x86 /optimize+ /codepage:65001 /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll /reference:System.Net.Http.dll /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll /resource:"$root\compat\hd-preview.json,Amagadon.HdPreviewRecipe" /out:"$out\AmagadonLauncher.exe" "$root\src\Launcher.cs" "$root\src\NativePatch.cs" "$root\src\Replay.cs" "$root\src\ReplayTests.cs"
if ($LASTEXITCODE -ne 0) { throw 'Compile failed' }
$version = [regex]::Match((Get-Content "$root\src\Launcher.cs" -Raw),'DisplayVersion = "([^"]+)"').Groups[1].Value
if ($version -notmatch '^\d+\.\d+\.\d+(-preview)?$') { throw 'Invalid build version' }
$entrypoint = "AmagadonLauncher-$version.exe"
Copy-Item "$out\AmagadonLauncher.exe" (Join-Path $out $entrypoint) -Force
Copy-Item "$root\PATCHNOTES.md" $out -Force
Copy-Item "$root\scripts\apply-update.ps1" $out -Force
$vendor = Join-Path $out 'compat'
New-Item -ItemType Directory -Force $vendor | Out-Null
if ((Get-FileHash "$root\third-party\cnc-ddraw\ddraw.dll").Hash -ne '85E0F7D530DFDA134793A57CB3E76B0287DCC96892EE57162DD68F47283B03A9') { throw 'Compatibility DLL hash mismatch' }
Copy-Item "$root\third-party\cnc-ddraw\ddraw.dll" $vendor -Force
Copy-Item "$root\third-party\LICENSE.cnc-ddraw" $vendor -Force
Copy-Item "$root\compat\hd-preview.json" $vendor -Force
$files = @('AmagadonLauncher.exe',$entrypoint,'PATCHNOTES.md','apply-update.ps1','compat\ddraw.dll','compat\LICENSE.cnc-ddraw','compat\hd-preview.json')
$manifestFiles = @($files | ForEach-Object { @{Path=$_; SHA256=(Get-FileHash (Join-Path $out $_)).Hash.ToLowerInvariant()} })
@{Version=$version; Entrypoint=$entrypoint; Files=$manifestFiles} | ConvertTo-Json -Depth 5 | Set-Content "$out\package.json" -Encoding UTF8
Compress-Archive -Path "$out\AmagadonLauncher.exe",(Join-Path $out $entrypoint),"$out\PATCHNOTES.md","$out\package.json","$out\apply-update.ps1","$out\compat" -DestinationPath "$out\AmagadonLauncher.zip" -Force
(Get-FileHash "$out\AmagadonLauncher.zip" -Algorithm SHA256).Hash.ToLower() | Set-Content "$out\AmagadonLauncher.zip.sha256" -Encoding ascii
