# PowerShell script to run Parking Monitor on Windows

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Parking Monitor System - Windows" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
Write-Host "Checking Python..." -ForegroundColor Yellow
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "ERROR: Python not found. Please install Python 3.10+." -ForegroundColor Red
    exit 1
}

$pythonVersion = & python --version
Write-Host "  $pythonVersion" -ForegroundColor Green

# Check/Create virtual environment
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}

# Activate venv
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& .\venv\Scripts\Activate.ps1

# Install/Update dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt --quiet

# Check FFmpeg
Write-Host "Checking FFmpeg..." -ForegroundColor Yellow
$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($ffmpeg) {
    Write-Host "  FFmpeg found: $($ffmpeg.Source)" -ForegroundColor Green
} else {
    Write-Host "  WARNING: FFmpeg not found. Streaming features will not work." -ForegroundColor Yellow
    Write-Host "  Download from: https://ffmpeg.org/download.html" -ForegroundColor Yellow
}

# Create directories
Write-Host "Creating directories..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path data, logs | Out-Null

# Start application
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Starting Parking Monitor..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

python backend/app.py --host 0.0.0.0 --port 5000

