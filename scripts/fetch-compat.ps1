$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$archive = Join-Path $root 'third-party\cnc-ddraw.zip'
New-Item -ItemType Directory -Force (Split-Path $archive) | Out-Null
Invoke-WebRequest 'https://github.com/FunkyFr3sh/cnc-ddraw/releases/download/v7.1.0.0/cnc-ddraw.zip' -OutFile $archive
if ((Get-FileHash $archive).Hash -ne '0B13AB89A64C9918189B1DADD449EF6ED3CB3B7B19CABD96D8ADBD95505BB908') { throw 'cnc-ddraw archive hash mismatch' }
Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $root 'third-party\cnc-ddraw') -Force
