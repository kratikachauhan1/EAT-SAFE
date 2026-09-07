#!/bin/bash

echo "==================================================="
echo "            EAT SAFE AI - Auto Launcher"
echo "==================================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null
then
    echo "[ERROR] python3 could not be found. Please install Python 3.9+."
    exit 1
fi

# Create venv if needed
if [ ! -d "venv" ]; then
    echo "[SETUP] Creating virtual environment..."
    python3 -m venv venv
fi

# Activate & Install
echo "[SETUP] Activating environment & installing dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Generate sample labels
echo "[SETUP] Generating sample label images..."
python generate_samples.py

echo ""
echo "==================================================="
echo "[SUCCESS] EAT SAFE is starting..."
echo "Open your browser at: http://127.0.0.1:5000"
echo "==================================================="
echo ""

# Run App
python run.py
