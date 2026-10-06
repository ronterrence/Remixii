param([switch]$NoBrowser)

$ErrorActionPreference = "Stop"
$bundleRoot = $PSScriptRoot
$app = Join-Path $bundleRoot "AI Remix Studio.exe"
$project = Join-Path $bundleRoot "Offline playback test.remix"
if (-not (Test-Path -LiteralPath $app -PathType Leaf)) { throw "App executable is missing: $app" }
if (-not (Test-Path -LiteralPath $project -PathType Leaf)) { throw "Offline test project is missing: $project" }

$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$listener.Start()
$port = $listener.LocalEndpoint.Port
$listener.Stop()
$base = "http://127.0.0.1:$port"

$env:REMIXII_INBROWSER = "0"
$env:GRADIO_SERVER_PORT = "$port"
$process = Start-Process -FilePath $app -WorkingDirectory $bundleRoot -WindowStyle Hidden -PassThru
try {
    $page = $null
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($process.HasExited) { throw "The app exited during startup with code $($process.ExitCode)." }
        try {
            $page = Invoke-WebRequest -UseBasicParsing -Uri $base -TimeoutSec 2
            if ($page.StatusCode -eq 200) { break }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $page -or $page.StatusCode -ne 200) { throw "The app did not serve $base." }
    if ($page.Content.Contains("cdnjs.cloudflare.com")) { throw "An external CDN script remains in the page." }

    $paths = [regex]::Matches($page.Content, '(?:src|href)="(/assets/index-[^"]+\.(?:js|css))"') |
        ForEach-Object { $_.Groups[1].Value }
    if ($paths.Count -ne 2) { throw "Expected two local frontend entry assets; found $($paths.Count)." }
    foreach ($path in $paths) {
        $asset = Invoke-WebRequest -UseBasicParsing -Uri ($base + $path) -TimeoutSec 10
        if ($asset.StatusCode -ne 200 -or $asset.RawContentLength -eq 0) {
            throw "Frontend asset failed: $path"
        }
        Write-Output "PASS $path ($($asset.RawContentLength) bytes)"
    }
    $config = Invoke-WebRequest -UseBasicParsing -Uri ($base + "/config") -TimeoutSec 10
    if ($config.StatusCode -ne 200) { throw "The app configuration is unavailable." }
    Write-Output "PASS local interface: $base"

    if (-not $NoBrowser) {
        Start-Process $base
        Write-Output "In the browser, open the Open project tab and import: $project"
        Write-Output "Play Original excerpt and Remix, then press Enter here to close the app."
        [void](Read-Host)
    }
} finally {
    if (-not $process.HasExited) { Stop-Process -Id $process.Id }
}
