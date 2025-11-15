#!/bin/bash

# Bash script to run Parking Monitor on Linux

echo "========================================"
echo "  Parking Monitor System - Linux"
echo "========================================"
echo ""

# Check Python
echo "Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found. Please install Python 3.10+."
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo "  $PYTHON_VERSION"

# Check/Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
echo "Activating virtual environment..."
source venv/bin/activate

# Install/Update dependencies
echo "Installing dependencies..."
pip install -r requirements.txt --quiet

# Check FFmpeg
echo "Checking FFmpeg..."
if command -v ffmpeg &> /dev/null; then
    FFMPEG_PATH=$(which ffmpeg)
    echo "  FFmpeg found: $FFMPEG_PATH"
else
    echo "  WARNING: FFmpeg not found. Streaming features will not work."
    echo "  Install with: sudo apt-get install ffmpeg (Ubuntu/Debian)"
    echo "            or: sudo yum install ffmpeg (CentOS/RHEL)"
fi

# Create directories
echo "Creating directories..."
mkdir -p data logs

# Start application
echo ""
echo "========================================"
echo "  Starting Parking Monitor..."
echo "========================================"
echo ""

python3 backend/app.py --host 0.0.0.0 --port 5000

