param([switch]$CheckOnly, [string]$ProjectDir = $PSScriptRoot)

$ErrorActionPreference = 'Stop'
$projectDir = $ProjectDir
$pythonExe = Join-Path $projectDir '.venv\Scripts\python.exe'
$baseUrl = 'http://127.0.0.1:8766'

function Get-ListenerId {
    foreach ($line in (& netstat.exe -ano -p tcp)) {
        if ($line -match '^\s*TCP\s+127\.0\.0\.1:8766\s+\S+\s+LISTENING\s+(\d+)\s*$') { return [int]$Matches[1] }
    }
    return $null
}

function Get-WorkspaceStatus {
    try {
        $page = Invoke-WebRequest -Uri "$baseUrl/" -UseBasicParsing -TimeoutSec 3
        $status = Invoke-RestMethod -Uri "$baseUrl/api/status" -TimeoutSec 3
        if ($page.StatusCode -ne 200 -or $page.Content -notmatch 'EconAgent Studio' -or $status.api_config_version -ne 2 -or $null -eq $status.busy) { return $null }
        return $status
    } catch { return $null }
}

function Assert-WorkspaceProcess([int]$processId) {
    $status = Get-WorkspaceStatus
    if ($null -eq $status) { throw '8766 端口正在使用，但无法确认是本工作台；未关闭任何进程。' }
    if ($status.busy) { throw '当前任务正在运行，请等任务结束后再重启。' }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction Stop
    if ($null -eq $proc -or $proc.Name -notmatch '^python(w)?\.exe$' -or $proc.CommandLine -notmatch '(?i)(?:^|\s)-m\s+uvicorn\s+app:app(?:\s|$)') {
        throw '无法确认端口所属进程为工作台后台；未关闭任何进程。'
    }
}

$mutex = [Threading.Mutex]::new($false, 'Local\EconAgentStudioSafeRestart')
$locked = $false
try {
    $locked = $mutex.WaitOne(0)
    if (-not $locked) { throw '安全重启正在进行，请稍候。' }
    if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf) -or -not (Test-Path -LiteralPath (Join-Path $projectDir 'app.py') -PathType Leaf)) { throw '找不到项目文件或 Python 环境。' }
    $existing = Get-ListenerId
    if ($existing) { Assert-WorkspaceProcess $existing }
    if ($CheckOnly) { Write-Output "检查通过；当前后台进程：$existing。未执行重启。"; return }

    Add-Type -AssemblyName System.Windows.Forms
    $message = "重启会保留上传文件、日志和已生成的文件。`n`n当前 Stata 内存中的数据修改、回归结果，以及页面对话不会自动恢复；请先保存需要的内容。`n`n确定安全重启吗？"
    $choice = [Windows.Forms.MessageBox]::Show($message, 'Stata 研究助手 · 安全重启', [Windows.Forms.MessageBoxButtons]::YesNo, [Windows.Forms.MessageBoxIcon]::Warning)
    if ($choice -ne [Windows.Forms.DialogResult]::Yes) { return }

    $now = Get-ListenerId
    if ($now -ne $existing) { throw '后台进程已发生变化，请重新启动此快捷方式。' }
    if ($existing) {
        Assert-WorkspaceProcess $existing
        & taskkill.exe /PID $existing /T /F | Out-Null
        if ($LASTEXITCODE -ne 0) { throw '无法关闭原后台，请确认没有任务运行并检查权限。' }
        $deadline = [DateTime]::UtcNow.AddSeconds(15)
        while (Get-ListenerId) {
            if ([DateTime]::UtcNow -ge $deadline) { throw '旧后台端口仍被占用，请检查后再重试。' }
            Start-Sleep -Milliseconds 250
        }
    }

    $stdout = Join-Path $projectDir 'service-restart-output.log'
    $stderr = Join-Path $projectDir 'service-restart-error.log'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $server = Start-Process -FilePath $pythonExe -ArgumentList @('-m','uvicorn','app:app','--host','127.0.0.1','--port','8766') -WorkingDirectory $projectDir -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while ($null -eq (Get-WorkspaceStatus)) {
        $server.Refresh()
        if ($server.HasExited) { throw "后台启动失败，请查看 $stderr。" }
        if ([DateTime]::UtcNow -ge $deadline) { throw "后台启动超时，请查看 $stderr。" }
        Start-Sleep -Milliseconds 500
    }
    Start-Process "$baseUrl/"
} catch {
    if ($CheckOnly) { Write-Error $_.Exception.Message; exit 1 }
    Add-Type -AssemblyName System.Windows.Forms
    [void][Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Stata 研究助手 · 安全重启', [Windows.Forms.MessageBoxButtons]::OK, [Windows.Forms.MessageBoxIcon]::Error)
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
