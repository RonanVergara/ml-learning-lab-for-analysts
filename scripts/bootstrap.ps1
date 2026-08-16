$ErrorActionPreference = "Stop"

$projectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$metadataFile = Join-Path $projectRoot "app-metadata.json"
$appDataRoot = Join-Path $env:LOCALAPPDATA "MLLearningLab"
$stateDirectory = Join-Path $appDataRoot "state"
$logDirectory = Join-Path $appDataRoot "logs"
$launcherLog = Join-Path $logDirectory "launcher.log"
$instanceFile = Join-Path $stateDirectory "instance.json"
$venvDirectory = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvDirectory "Scripts\python.exe"
$lockFile = Join-Path $projectRoot "requirements.lock"
$hashMarker = Join-Path $venvDirectory ".requirements.sha256"
$headless = if ($env:MLLAB_HEADLESS -eq "1") { "true" } else { "false" }

New-Item -ItemType Directory -Force -Path $stateDirectory, $logDirectory | Out-Null

if (-not (Test-Path -LiteralPath $metadataFile)) {
    throw "app-metadata.json is missing. Restore the complete application folder."
}
$appMetadata = Get-Content -LiteralPath $metadataFile -Raw | ConvertFrom-Json
if (-not $appMetadata.app_id -or -not $appMetadata.app_version -or -not $appMetadata.port) {
    throw "app-metadata.json is incomplete. Restore the complete application folder."
}
$appInstanceId = [string]$appMetadata.app_id
$appVersion = [string]$appMetadata.app_version
$appPort = [int]$appMetadata.port
$appUrl = "http://127.0.0.1:$appPort"

if (Test-Path -LiteralPath $launcherLog) {
    $logLength = (Get-Item -LiteralPath $launcherLog).Length
    if ($logLength -ge 1MB) {
        for ($index = 4; $index -ge 1; $index--) {
            $source = if ($index -eq 1) { $launcherLog } else { "$launcherLog.$($index - 1)" }
            $target = "$launcherLog.$index"
            if (Test-Path -LiteralPath $source) {
                Move-Item -LiteralPath $source -Destination $target -Force
            }
        }
    }
}

function Write-LauncherLog([string]$Message) {
    $timestamp = (Get-Date).ToUniversalTime().ToString("o")
    Add-Content -LiteralPath $launcherLog -Value "$timestamp $Message" -Encoding UTF8
}

function Test-AppHealth {
    try {
        $health = Invoke-WebRequest -UseBasicParsing -Uri "$appUrl/_stcore/health" -TimeoutSec 2
        return $health.StatusCode -eq 200 -and $health.Content.Trim() -eq "ok"
    } catch {
        return $false
    }
}

Write-LauncherLog "Launcher started app=$appInstanceId version=$appVersion root=$projectRoot"

if (Test-Path -LiteralPath $instanceFile) {
    try {
        $registered = Get-Content -LiteralPath $instanceFile -Raw | ConvertFrom-Json
    } catch {
        throw "The ML Learning Lab instance marker is malformed. See the troubleshooting guide."
    }
    $sameApp = [string]$registered.app_id -eq $appInstanceId
    $sameRoot = [string]::Equals(
        [System.IO.Path]::GetFullPath([string]$registered.project_root),
        $projectRoot,
        [System.StringComparison]::OrdinalIgnoreCase
    )
    $samePort = [int]$registered.port -eq $appPort
    if (-not ($sameApp -and $sameRoot -and $samePort)) {
        throw "Port ownership cannot be verified for ML Learning Lab. The instance marker belongs to a different application or folder."
    }
    $owner = Get-Process -Id ([int]$registered.launcher_pid) -ErrorAction SilentlyContinue
    if ($owner) {
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            if (Test-AppHealth) {
                Write-LauncherLog "Verified existing app-specific instance pid=$($registered.launcher_pid); reopening browser"
                if ($headless -ne "true") { Start-Process $appUrl }
                exit 0
            }
            Start-Sleep -Milliseconds 500
        }
        throw "ML Learning Lab is registered as starting but did not become healthy. Check the launcher log."
    }
    Write-LauncherLog "Removing stale app-specific instance marker"
    Remove-Item -LiteralPath $instanceFile -Force
}

if (Test-AppHealth) {
    throw "Port $appPort is serving another application. ML Learning Lab will not reuse an unidentified Streamlit instance."
}

if (-not (Test-Path -LiteralPath $lockFile)) {
    Write-LauncherLog "Missing dependency lock: $lockFile"
    throw "requirements.lock is missing. Restore the complete application folder."
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creating the private Python 3.13 environment..."
    Write-LauncherLog "Creating virtual environment"
    & py -3.13 -m venv $venvDirectory
    if ($LASTEXITCODE -ne 0) { throw "Python could not create the virtual environment." }
}

$lockHash = (Get-FileHash -LiteralPath $lockFile -Algorithm SHA256).Hash
$installedHash = if (Test-Path -LiteralPath $hashMarker) {
    (Get-Content -LiteralPath $hashMarker -Raw).Trim()
} else {
    ""
}

if ($lockHash -ne $installedHash) {
    Write-Host "Installing the tested ML Learning Lab dependencies..."
    Write-Host "Internet access is needed for this first setup."
    Write-LauncherLog "Installing dependency lock $lockHash"
    & $venvPython -m pip install --disable-pip-version-check -r $lockFile
    if ($LASTEXITCODE -ne 0) {
        Write-LauncherLog "Dependency installation failed with exit code $LASTEXITCODE"
        throw "Dependency installation failed. Check internet access and the launcher log."
    }
    Set-Content -LiteralPath $hashMarker -Value $lockHash -Encoding ASCII
}

$instanceRecord = [ordered]@{
    app_id = $appInstanceId
    app_version = $appVersion
    project_root = $projectRoot
    launcher_pid = $PID
    port = $appPort
    started_at = (Get-Date).ToUniversalTime().ToString("o")
}
$instanceRecord | ConvertTo-Json | Set-Content -LiteralPath $instanceFile -Encoding UTF8

Write-Host "Starting ML Learning Lab at $appUrl"
Write-Host "Press Ctrl+C in this window when you want to stop the app."
Write-LauncherLog "Starting Streamlit with app-specific marker pid=$PID"
Set-Location -LiteralPath $projectRoot
try {
    & $venvPython -m streamlit run app.py --server.address 127.0.0.1 --server.port $appPort --server.headless $headless --browser.gatherUsageStats false
    $appExit = $LASTEXITCODE
    Write-LauncherLog "Streamlit exited with code $appExit"
    exit $appExit
} finally {
    if (Test-Path -LiteralPath $instanceFile) {
        try {
            $ownedMarker = Get-Content -LiteralPath $instanceFile -Raw | ConvertFrom-Json
            if ([string]$ownedMarker.app_id -eq $appInstanceId -and [int]$ownedMarker.launcher_pid -eq $PID) {
                Remove-Item -LiteralPath $instanceFile -Force
            }
        } catch {
            Write-LauncherLog "Could not clean the instance marker; it will be checked as stale next launch"
        }
    }
}
