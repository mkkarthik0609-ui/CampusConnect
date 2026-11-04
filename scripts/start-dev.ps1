[CmdletBinding()]
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$venvActivate = Join-Path $projectRoot ".venv\Scripts\Activate.ps1"

function Find-Python {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) { return @($launcher.Source, "-3") }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return @($python.Source) }

    throw "Python 3.12+ is required. Install it from https://www.python.org/downloads/ and run this script again."
}

Set-Location $projectRoot

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "Node.js 20+ is required. Install it from https://nodejs.org/ and run this script again."
}

if (-not (Test-Path $venvPython)) {
    $pythonCommand = Find-Python
    Write-Host "Creating .venv..."
    if ($pythonCommand.Count -gt 1) {
        & $pythonCommand[0] $pythonCommand[1] -m venv .venv
    } else {
        & $pythonCommand[0] -m venv .venv
    }
}

Write-Host "Installing backend dependencies..."
& $venvPython -m pip install --disable-pip-version-check -q -r requirements.txt

if (-not (Test-Path ".env")) {
    @"
# Local development configuration. This file is ignored by Git.
APP_ENV=development
DEBUG=1
ENABLE_SCHEDULER=0
BOOTSTRAP_ADMIN=1
ADMIN_NAME=Development Admin
ADMIN_EMAIL=admin@campusconnect.local
ADMIN_PASSWORD=CampusConnect1
"@ | Set-Content -Encoding utf8 ".env"
    Write-Host "Created .env with development login: admin@campusconnect.local / CampusConnect1"
}

if (-not (Test-Path "frontend\node_modules")) {
    Write-Host "Installing frontend dependencies..."
    Push-Location frontend
    try { npm ci } finally { Pop-Location }
}

$apiArgs = "Set-Location '$projectRoot'; & '$venvPython' app.py"
$webArgs = "Set-Location '$projectRoot\frontend'; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiArgs
Start-Process powershell -ArgumentList "-NoExit", "-Command", $webArgs

if (-not $NoBrowser) {
    Start-Process "http://localhost:5173"
}

Write-Host "Campus Connect is starting at http://localhost:5173"
Write-Host "Development admin: admin@campusconnect.local / CampusConnect1"
