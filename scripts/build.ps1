param([string]$OutputDirectory = "")
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$out = if ($OutputDirectory) { [IO.Path]::GetFullPath($OutputDirectory) } else { Join-Path $root 'dist' }
New-Item -ItemType Directory -Force $out | Out-Null
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
& $csc /nologo /target:winexe /platform:x86 /optimize+ /codepage:65001 /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll /reference:System.Net.Http.dll /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll /resource:"$root\scripts\apply-update.ps1,Amagadon.UpdateInstaller" /resource:"$root\compat\hd-preview.json,Amagadon.HdPreviewRecipe" /resource:"$root\compat\replay-0.3.0.json,Amagadon.LegacyReplayRecipe" /resource:"$root\compat\replay-0.3.2.json,Amagadon.Replay032Recipe" /resource:"$root\compat\replay-0.3.3-r1.json,Amagadon.Replay033Recipe" /resource:"$root\compat\replay-0.3.3.json,Amagadon.Replay033FinalRecipe" /resource:"$root\compat\replay-0.3.4.json,Amagadon.Replay034Recipe" /resource:"$root\third-party\ddrawcompat\ddraw.dll,Amagadon.EditorWrapper" /resource:"$root\compat\editor-gdi.json,Amagadon.EditorRecipe" /out:"$out\AmagadonLauncher.exe" "$root\src\Launcher.cs" "$root\src\Updates.cs" "$root\src\NativePatch.cs" "$root\src\Replay.cs" "$root\src\ReplayTests.cs" "$root\src\ReplayBrowser.cs" "$root\src\Diagnostics.cs" "$root\src\EditorCompatibility.cs" "$root\src\EditorPatch.cs"
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
if ((Get-FileHash "$root\third-party\ddrawcompat\ddraw.dll").Hash -ne '94895CF6EDE8FD0F74EE1447FDC08B7044A9C65A1A25A49A4DF893A0370975A3') {throw 'Editor wrapper hash mismatch'}
Add-Content -LiteralPath "$vendor\LICENSE.cnc-ddraw" -Value "`r`nDDrawCompat v0.7.2 - 0BSD`r`n"
Get-Content "$root\third-party\ddrawcompat\LICENSE.txt","$root\third-party\ddrawcompat\SOURCE.txt" | Add-Content -LiteralPath "$vendor\LICENSE.cnc-ddraw"
$files = @('AmagadonLauncher.exe',$entrypoint,'PATCHNOTES.md','apply-update.ps1','compat\ddraw.dll','compat\LICENSE.cnc-ddraw','compat\hd-preview.json')
$manifestFiles = @($files | ForEach-Object { @{Path=$_; SHA256=(Get-FileHash (Join-Path $out $_)).Hash.ToLowerInvariant()} })
@{Version=$version; Entrypoint=$entrypoint; Files=$manifestFiles} | ConvertTo-Json -Depth 5 | Set-Content "$out\package.json" -Encoding UTF8
Compress-Archive -Path "$out\AmagadonLauncher.exe",(Join-Path $out $entrypoint),"$out\PATCHNOTES.md","$out\package.json","$out\apply-update.ps1","$out\compat" -DestinationPath "$out\AmagadonLauncher.zip" -Force
(Get-FileHash "$out\AmagadonLauncher.zip" -Algorithm SHA256).Hash.ToLower() | Set-Content "$out\AmagadonLauncher.zip.sha256" -Encoding ascii
