param([switch]$NoBrowser, [string]$ProjectDir = $PSScriptRoot)

$ErrorActionPreference = 'Stop'
$projectDir = $ProjectDir
$pythonExe = Join-Path $projectDir '.venv\Scripts\python.exe'
$ports = @(8766)

function Show-LaunchError([string]$message) {
    if ($NoBrowser) { Write-Error $message; return }
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show($message, 'EconAgent Studio', 'OK', 'Error')
}

function Test-Workspace([int]$port) {
    try {
        $base = "http://127.0.0.1:$port"
        $page = Invoke-WebRequest -Uri "$base/" -UseBasicParsing -TimeoutSec 2
        if ($page.StatusCode -ne 200 -or $page.Content -notmatch 'EconAgent Studio') { return $false }
        $status = Invoke-RestMethod -Uri "$base/api/status" -TimeoutSec 2
        return ($null -ne $status.stata_found -and $null -ne $status.api_key_set -and $status.api_config_version -eq 2)
    } catch { return $false }
}

function Test-PortInUse([int]$port) {
    $socket = [System.Net.Sockets.TcpClient]::new()
    try {
        $attempt = $socket.ConnectAsync('127.0.0.1', $port)
        return ($attempt.Wait(500) -and $socket.Connected)
    } catch { return $false } finally { $socket.Dispose() }
}

$mutex = [System.Threading.Mutex]::new($false, 'Local\EconAgentStudioLauncher')
$locked = $false
try {
    $locked = $mutex.WaitOne(30000)
    if (-not $locked) { throw 'Another launch is taking too long. Please try again.' }
    if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf) -or -not (Test-Path -LiteralPath (Join-Path $projectDir 'app.py') -PathType Leaf)) {
        throw 'Cannot find the app or its Python environment in D:\Mystata. Check the project location and installation.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $projectDir 'web-build\index.html') -PathType Leaf)) {
        throw 'The web interface has not been built. In D:\Mystata, run npm install followed by npm run build.'
    }

    $target = $null
    foreach ($port in $ports) {
        if (Test-Workspace $port) { $target = "http://127.0.0.1:$port/"; break }
    }
    if (-not $target) {
        $freePort = $null
        foreach ($port in $ports) {
            if (-not (Test-PortInUse $port)) { $freePort = $port; break }
        }
        if (-not $freePort) { throw 'All launcher ports are in use. Close an unused local service and try again.' }
        $cleanupScript = Join-Path $projectDir 'workspace_cleanup.py'
        if (-not (Test-Path -LiteralPath $cleanupScript -PathType Leaf)) { throw 'Cannot find the workspace cleanup script.' }
        $env:PYTHONDONTWRITEBYTECODE = '1'
        & $pythonExe $cleanupScript --project-dir $projectDir --startup
        if ($LASTEXITCODE -ne 0) { throw 'Workspace cleanup failed. Please check the project folders before starting.' }
        # Install a staged interface only when no older server is running.
        $pendingBuild = Join-Path $projectDir 'web-build-next'
        $pendingIndex = Join-Path $pendingBuild 'index.html'
        if (Test-Path -LiteralPath $pendingIndex -PathType Leaf) {
            $assets = Join-Path $pendingBuild 'assets'
            $targetAssets = Join-Path $projectDir 'web-build\assets'
            New-Item -ItemType Directory -Force -Path $targetAssets | Out-Null
            Copy-Item -Path (Join-Path $assets '*') -Destination $targetAssets -Force
            Move-Item -LiteralPath $pendingIndex -Destination (Join-Path $projectDir 'web-build\index.html') -Force
        }
        $env:PYTHONDONTWRITEBYTECODE = '1'
        $server = Start-Process -FilePath $pythonExe -ArgumentList @('-m','uvicorn','app:app','--host','127.0.0.1','--port',"$freePort") -WorkingDirectory $projectDir -WindowStyle Hidden -PassThru
        $target = "http://127.0.0.1:$freePort/"
        $deadline = [DateTime]::UtcNow.AddSeconds(30)
        while (-not (Test-Workspace $freePort)) {
            if ($server.HasExited) { throw 'The application stopped during startup. Run uvicorn in PowerShell to see the error.' }
            if ([DateTime]::UtcNow -ge $deadline) { throw 'The application did not become ready within 30 seconds.' }
            Start-Sleep -Milliseconds 500
            $server.Refresh()
        }
    }
    if ($NoBrowser) { Write-Output "Ready: $target" } else { Start-Process $target }
} catch {
    Show-LaunchError $_.Exception.Message
    exit 1
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
