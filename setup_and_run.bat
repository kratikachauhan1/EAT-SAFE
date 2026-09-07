@echo off
TITLE EAT SAFE - Automated Setup & Launcher
echo ===================================================
echo             EAT SAFE AI - Auto Launcher
echo ===================================================
echo.

:: 1. Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to PATH.
    echo Please install Python 3.9+ from https://www.python.org/
    pause
    exit /b 1
)

:: 2. Create Virtual Environment if it doesn't exist
if not exist "venv" (
    echo [SETUP] Creating Python Virtual Environment (venv)...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: 3. Activate Virtual Environment & Install Dependencies
echo [SETUP] Activating environment and installing required packages...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt

:: 4. Generate Sample Test Labels
echo [SETUP] Generating sample food label images...
python generate_samples.py

:: 5. Check Tesseract OCR
echo [SETUP] Checking Tesseract OCR status...
python -c "from app.ocr import find_tesseract_cmd; cmd = find_tesseract_cmd(); print('[INFO] Tesseract executable path:', cmd if cmd else 'Not found (App will run in fallback/sample mode)')"

echo.
echo ===================================================
echo [SUCCESS] EAT SAFE is starting...
echo Open your browser at: http://127.0.0.1:5000
echo (To access from mobile on same Wi-Fi: http://YOUR_IP:5000)
echo ===================================================
echo.

:: Launch browser after 2 seconds
start http://127.0.0.1:5000

:: Run Flask server
python run.py

pause
