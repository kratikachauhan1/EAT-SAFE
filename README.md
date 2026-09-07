# EAT SAFE - Personalised Food Allergen Detection 🛡️🌿

**EAT SAFE** is an AI-assisted food label screening application designed to extract ingredient declarations from food packaging labels using **OpenCV** and **Tesseract OCR**, clean and analyze text with **Natural Language Processing (NLP)**, match ingredients against an **FSSAI-aligned Allergen Knowledge Base**, and deliver personalized warnings based on an individual user's allergy profile.

---

## 🚀 How Anyone Can Run This Project (1-Click Launch)

This project is 100% self-contained, portable, and configured so anyone receiving the project files can run it immediately on their machine.

### Option A: Windows 1-Click Automated Setup (Recommended)
1. Extract or download the project folder.
2. Double-click **`setup_and_run.bat`**.
3. The script automatically sets up the Python virtual environment, installs dependencies, generates test sample labels, starts the server, and opens **`http://127.0.0.1:5000`** in your default web browser!

### Option B: macOS / Linux Setup
Open Terminal in the project folder and run:
```bash
chmod +x setup_and_run.sh
./setup_and_run.sh
```

### Option C: Manual Run via Terminal / VS Code
```bash
# 1. Create and activate virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 2. Install requirements
pip install -r requirements.txt

# 3. Generate sample labels & run app
python generate_samples.py
python run.py
```

---

## 📱 Mobile & Local Network Sharing

When you run `python run.py` or `setup_and_run.bat`, the server binds to local network interfaces (`0.0.0.0:5000`).

- **On your PC/Laptop**: Open `http://127.0.0.1:5000`
- **On your Smartphone or another Laptop on the same Wi-Fi**:
  Open the network URL printed in the terminal (e.g. **`http://192.168.1.5:5000`**).
  You can test real label photos directly using your mobile phone camera!

---

## 🧪 Unit Tests & Tesseract Fallback

Run the automated test suite anytime using:
```bash
python -m pytest tests/
```

> [!NOTE]
> **Tesseract OCR Graceful Fallback**: If Tesseract OCR is not installed on the recipient's PC, EAT SAFE will not crash! The system gracefully flags low OCR confidence, provides a warning banner, and allows full demonstration using the built-in sample test labels.

---

## 📁 Project Structure

```
food allergen detector/
├── app/
│   ├── __init__.py          # Flask factory & database seed
│   ├── database.py          # SQLite connection manager
│   ├── models.py            # Data access layer (users, scans, results)
│   ├── preprocessing.py     # OpenCV image enhancement pipeline
│   ├── ocr.py               # Tesseract OCR wrapper & confidence evaluator
│   ├── nlp.py               # Text cleaning, normalization & sectioning
│   ├── allergen_detector.py # Rule-based + RapidFuzz matching against KB
│   ├── personalisation.py  # User profile intersection engine
│   └── routes.py            # Web endpoints (profile, scan, result, history)
├── data/
│   ├── allergen_kb.json     # FSSAI aligned Allergen Knowledge Base (9 categories)
│   └── schema.sql           # SQLite database schema
├── static/
│   ├── css/
│   │   └── style.css        # Production SaaS CSS design system
│   ├── js/
│   │   └── main.js         # Interactive camera capture & drag-drop upload
│   └── images/
│       └── logo.png         # EAT SAFE Logo Image
├── templates/
│   ├── base.html            # App shell sidebar layout
│   ├── index.html           # SaaS Dashboard & Metric Cards
│   ├── profile.html         # User Allergy Profile setup
│   ├── scan.html            # Upload photo / camera capture / guidance
│   ├── result.html          # Explainable AI result report & OCR document panel
│   └── history.html         # Past scan log table
├── tests/
│   ├── test_detection.py    # Unit tests for NLP & matching
│   └── test_personalisation.py # Unit tests for personalisation logic
├── sample_labels/           # Pre-generated sample label images
├── generate_samples.py      # Synthetic label generator script
├── test_e2e_pipeline.py     # Integration test runner script
├── setup_and_run.bat        # Windows 1-click auto launcher
├── setup_and_run.sh         # Linux/macOS auto launcher
├── requirements.txt         # Python dependencies
├── .gitignore
├── run.py                   # Server entry point with network sharing
└── README.md                # Project documentation
```

---

## 📤 Sharing to GitHub or via Zip File

### To share via Zip:
Right-click `E:\food allergen detector` folder ➔ **Compress to ZIP file**. (Send the zip to your friends or mentor!).

### To push to GitHub:
```bash
git init
git add .
git commit -m "EAT SAFE - Personalised Food Allergen Detection AI Project"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/eat-safe-allergen-detector.git
git push -u origin main
```
