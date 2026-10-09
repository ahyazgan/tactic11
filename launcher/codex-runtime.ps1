# Isolated local Manager runtime. Never stop a foreign listener.
[CmdletBinding()]
param(
    [ValidateSet('Start', 'Status', 'Stop')][string]$Action = 'Start',
    [ValidateRange(1024, 65535)][int]$WebPort = 3100,
    [ValidateRange(1024, 65535)][int]$ApiPort = 8100,
    [switch]$OpenBrowser
)
$ErrorActionPreference = 'Stop'
if ($WebPort -eq $ApiPort) { throw 'WebPort and ApiPort must differ.' }
$root = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $root 'frontend'
$cache = Join-Path $root '.cache'
$python = Join-Path $root 'venv\Scripts\python.exe'
$next = Join-Path $frontend 'node_modules\next\dist\bin\next'
$webUrl = "http://127.0.0.1:$WebPort"
$apiUrl = "http://127.0.0.1:$ApiPort"

function Get-Listener([int]$Port, [string]$Kind) {
    $connections = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
        Where-Object LocalPort -eq $Port)
    $owners = @($connections.OwningProcess | Sort-Object -Unique)
    if ($owners.Count -gt 1) { throw "Port $Port has multiple listeners; no process was stopped." }
    if (-not $owners.Count) { return $null }
    $process = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $owners[0])
    $command = [string]$process.CommandLine
    $marker = if ($Kind -eq 'web') { $next } else { $python }
    $isOwned = $command.IndexOf($marker, [StringComparison]::OrdinalIgnoreCase) -ge 0
    if ($Kind -eq 'api') { $isOwned = $isOwned -and $command.Contains('app.api.main:app') }
    if (-not $isOwned) { throw "Port $Port belongs to another process (PID $($owners[0])); left untouched." }
    return $process
}

function Wait-Http([string]$Url) {
    $lastError = ''
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return }
        } catch { $lastError = $_.Exception.Message }
        Start-Sleep -Milliseconds 300
    }
    throw "Service did not become ready: $Url. $lastError"
}

# Resolve BOTH owners before any build, configuration write or process stop.
$web = Get-Listener $WebPort 'web'
$api = Get-Listener $ApiPort 'api'
if ($Action -eq 'Status') {
    Write-Output "Manager web: $webUrl (PID $($web.ProcessId))"
    Write-Output "Manager API: $apiUrl (PID $($api.ProcessId))"
    if ($web) { Wait-Http "$webUrl/video-tracking" }
    if ($api) { Wait-Http "$apiUrl/health" }
    return
}
if ($Action -eq 'Stop') {
    foreach ($process in @($web, $api)) {
        if ($process) { Stop-Process -Id $process.ProcessId -ErrorAction Stop }
    }
    Write-Output 'Manager isolated services stopped.'
    return
}
if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $next)) {
    throw 'Existing venv and frontend/node_modules are required.'
}
$node = (Get-Command node.exe -ErrorAction Stop).Source
New-Item -ItemType Directory -Path $cache -Force | Out-Null
$buildStatePath = Join-Path $cache 'codex-runtime-build.json'
$head = (& git -C $root rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot determine the project revision.' }
$buildState = if (Test-Path -LiteralPath $buildStatePath) {
    Get-Content -LiteralPath $buildStatePath -Raw | ConvertFrom-Json
} else { $null }
$freshness = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'guncel-mi.ps1') -Bilesen frontend -Kok $root
$fresh = $LASTEXITCODE -eq 0
$needBuild = -not $fresh -or -not $buildState -or $buildState.head -ne $head -or $buildState.apiUrl -ne $apiUrl -or $buildState.demoMode -ne $false
$env:API_BASE_URL = $apiUrl
$env:NEXT_PUBLIC_DEMO_MODE = 'false'
# Avoid spawning a build worker for every CPU on memory-constrained desktops.
$env:CIRCLE_NODE_TOTAL = '2'
if ($needBuild) {
    if ($web) { Stop-Process -Id $web.ProcessId; $web = $null }
    Push-Location $frontend
    try {
        $buildLog = Join-Path $cache 'codex-runtime-build.log'
        & $node $next build *> $buildLog
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed. See $buildLog" }
    } finally { Pop-Location }
    @{ head = $head; apiUrl = $apiUrl; demoMode = $false } |
        ConvertTo-Json | Set-Content -LiteralPath $buildStatePath -Encoding UTF8
}

# Keep existing match data: no seed, schema rewrite or reset in this launcher.
$database = Join-Path $root 'demo.db'
if (-not (Test-Path -LiteralPath $database)) { throw 'demo.db is missing; database initialization is a separate operation.' }
$env:DATABASE_URL = 'sqlite:///' + $database.Replace('\', '/')
$env:APP_ENV = 'dev'
$env:DEV_DEFAULT_TENANT_ID = 't-default'
$env:PYTHONUTF8 = '1'
if ($api) {
    $newestApiFile = Get-ChildItem -LiteralPath (Join-Path $root 'app') -Filter '*.py' -Recurse |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($newestApiFile.LastWriteTime -gt $api.CreationDate) {
        Stop-Process -Id $api.ProcessId; $api = $null
    }
}
if (-not $api) {
    Start-Process -FilePath $python -ArgumentList '-X', 'utf8', '-m', 'uvicorn', 'app.api.main:app', '--host', '127.0.0.1', '--port', $ApiPort -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $cache 'codex-api.out.log') -RedirectStandardError (Join-Path $cache 'codex-api.err.log') | Out-Null
}
Wait-Http "$apiUrl/health"
if (-not $web) {
    Start-Process -FilePath $node -ArgumentList ('"' + $next + '"'), 'start', '--hostname', '127.0.0.1', '--port', $WebPort -WorkingDirectory $frontend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $cache 'codex-web.out.log') -RedirectStandardError (Join-Path $cache 'codex-web.err.log') | Out-Null
}
Wait-Http "$webUrl/video-tracking"
Wait-Http "$webUrl/api/health"
$null = Get-Listener $WebPort 'web'
$null = Get-Listener $ApiPort 'api'
Write-Output "Manager ready: $webUrl/video-tracking (live API; existing database)"
if ($OpenBrowser) { Start-Process $webUrl }
