$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$appDataRoot = Join-Path $env:LOCALAPPDATA "MLLearningLab"
$logDirectory = Join-Path $appDataRoot "logs"
$launcherLog = Join-Path $logDirectory "launcher.log"
$venvDirectory = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvDirectory "Scripts\python.exe"
$lockFile = Join-Path $projectRoot "requirements.lock"
$hashMarker = Join-Path $venvDirectory ".requirements.sha256"
$appUrl = "http://127.0.0.1:8501"
$headless = if ($env:MLLAB_HEADLESS -eq "1") { "true" } else { "false" }

New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null

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

Write-LauncherLog "Launcher started from $projectRoot"

try {
    $health = Invoke-WebRequest -UseBasicParsing -Uri "$appUrl/_stcore/health" -TimeoutSec 2
    if ($health.StatusCode -eq 200 -and $health.Content.Trim() -eq "ok") {
        Write-LauncherLog "Existing ML Learning Lab instance found; reopening browser"
        if ($headless -ne "true") { Start-Process $appUrl }
        exit 0
    }
} catch {
    Write-LauncherLog "No existing healthy instance found"
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

Write-Host "Starting ML Learning Lab at $appUrl"
Write-Host "Press Ctrl+C in this window when you want to stop the app."
Write-LauncherLog "Starting Streamlit"
Set-Location -LiteralPath $projectRoot
& $venvPython -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless $headless --browser.gatherUsageStats false
$appExit = $LASTEXITCODE
Write-LauncherLog "Streamlit exited with code $appExit"
exit $appExit
