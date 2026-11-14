param(
    [Parameter(Mandatory=$true)][string]$GameDirectory,
    [Parameter(Mandatory=$true)][string]$BuildDirectory,
    [Parameter(Mandatory=$true)][string]$LabDirectory,
    [ValidateSet(800,1024)][int]$Width=1024,
    [ValidateSet(800,1024)][int]$GuestWidth=1024,
    [switch]$Launch
)
$ErrorActionPreference='Stop'
$game=(Resolve-Path -LiteralPath $GameDirectory).Path
$build=(Resolve-Path -LiteralPath $BuildDirectory).Path
$lab=[IO.Path]::GetFullPath($LabDirectory)
if(Test-Path -LiteralPath $lab){throw 'Lab directory exists. Use a new directory; existing evidence is never overwritten.'}
if($lab.StartsWith($game.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Lab must not be inside the game installation.'}
$launcher=Join-Path $build 'AmagadonLauncher.exe'
foreach($required in @($launcher,(Join-Path $build 'compat/ddraw.dll'),(Join-Path $build 'compat/hd-preview.json'),(Join-Path $game 'Armageddon.exe'),(Join-Path $game 'Armageddon.MFP'))){
    if(!(Test-Path -LiteralPath $required)){throw "Missing required file: $required"}
}
New-Item -ItemType Directory -Path $lab | Out-Null
# Keep the helper beside a COPY of the launcher to resolve its managed assembly.
$runner=Join-Path $lab 'runner'
Copy-Item -LiteralPath $build -Destination $runner -Recurse
$helper=Join-Path $runner 'NativeMultiplayerSession.exe'
$source=Join-Path $PSScriptRoot 'native-multiplayer-session.cs'
& "$env:WINDIR/Microsoft.NET/Framework/v4.0.30319/csc.exe" /nologo /target:exe /platform:x86 "/reference:$launcher" "/out:$helper" $source
if($LASTEXITCODE -ne 0){throw 'Native session adapter compilation failed.'}
$manifest=@{createdUtc=[DateTime]::UtcNow.ToString('o');launcherSha256=(Get-FileHash -LiteralPath $launcher -Algorithm SHA256).Hash;originalExeSha256=(Get-FileHash -LiteralPath (Join-Path $game 'Armageddon.exe') -Algorithm SHA256).Hash;width=$Width;guestWidth=$GuestWidth;sessions=@()}
foreach($side in @('host','guest')){
    $copy=Join-Path $lab $side
    New-Item -ItemType Directory -Path $copy | Out-Null
    # Explicit game assets only. No user reports, saved credentials or replays.
    foreach($name in @('Armageddon.exe','Armageddon.HED','Armageddon.MFP','ArmaInfo.dat','ArmaVer.txt','option.dat','FirstMovie','binkw32.dll','Mss32.dll','dpwsockx.dll','ipxwrapper.dll','wsock32.dll','mswsock.dll')){
        $item=Join-Path $game $name
        if(Test-Path -LiteralPath $item){Copy-Item -LiteralPath $item -Destination $copy}
    }
    foreach($name in @('Bgm','wav','Map/Multiplay')){
        $item=Join-Path $game $name
        if(Test-Path -LiteralPath $item){$target=Join-Path $copy $name;New-Item -ItemType Directory -Path (Split-Path $target) -Force | Out-Null;Copy-Item -LiteralPath $item -Destination $target -Recurse}
    }
    New-Item -ItemType Directory -Path (Join-Path $copy 'Save'),(Join-Path $copy 'Map/Custom') -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $copy 'native-lab-copy.txt'),'isolated native multiplayer test copy')
    $session=Join-Path $lab ($side+'-session')
    $sideWidth=if($side -eq 'guest'){$GuestWidth}else{$Width}
    $manifest.sessions+=@{side=$side;game=$copy;session=$session;width=$sideWidth}
    if($Launch){
        $arguments='"'+$copy+'" "'+$session+'" '+$sideWidth
        Start-Process -FilePath $helper -ArgumentList $arguments -WorkingDirectory $runner -WindowStyle Hidden -RedirectStandardError (Join-Path $lab ($side+'-error.txt')) | Out-Null
    }
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $lab 'lab.json') -Encoding UTF8
Write-Output "Prepared isolated copies: $lab"
Write-Output 'No match is verified until both native clients join and exchange synchronized gameplay.'
