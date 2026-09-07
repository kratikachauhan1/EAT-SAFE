# EAT SAFE - Personalised Food Allergen Detection 🛡️🌿

**EAT SAFE** is an AI-assisted food label screening application designed to extract ingredient declarations from food packaging labels using **OpenCV** and **Tesseract OCR**, clean and analyze text with **Natural Language Processing (NLP)**, match ingredients against an **FSSAI-aligned Allergen Knowledge Base**, and deliver personalized warnings based on an individual user's allergy profile.

---

## 🌟 Features & AI Pipeline

1. **User Profile Personalisation**: Users configure their personal allergies (e.g. Milk, Peanut, Soy, Gluten). Warnings are filtered to highlight risks specific to the active user profile.
2. **OpenCV Image Preprocessing**: Grayscale conversion, Non-Local Means Denoising (`cv2.fastNlMeansDenoising`), CLAHE contrast enhancement, sharpening, and adaptive thresholding.
3. **OCR Engine (`pytesseract`)**: Converts packaging photos into text and calculates confidence scores.
4. **NLP & Context Sectioning**: Cleans OCR typos and distinguishes **Explicit Allergen Declarations** (`Contains: Milk`) from **Precautionary Statements** (`May contain peanuts`).
5. **Explainable Evidence**: Displays the exact text snippet extracted from the label with highlighted ingredient matches.
6. **Safety First**: Clearly flags low-confidence OCR and explicitly disclaims medical diagnoses or guarantees of safety.

---

## 🚀 Deployment on Render (Docker Web Service)

This application is fully containerized and production-ready for deployment on **Render**.

### Render Configuration Settings:
- **Service Type**: Web Service
- **Repository**: `kratikachauhan1/EAT-SAFE`
- **Branch**: `main`
- **Runtime**: `Docker`
- **Root Directory**: *(Leave empty)*
- **Dockerfile Path**: `./Dockerfile`
- **Docker Build Context Directory**: `.`
- **Start Command**: `gunicorn --bind 0.0.0.0:${PORT:-5000} run:app` *(Handled automatically by Dockerfile)*

> [!NOTE]
> **Cloud Persistence Limitation**: Public cloud platforms like Render use ephemeral container storage. While SQLite database initialization and file uploads work seamlessly during container execution, uploaded scan history resets when the container restarts unless persistent disk storage is attached.

---

## 💻 Local Setup & 1-Click Launch

### Option A: Windows 1-Click Launch (Recommended)
Double-click **`setup_and_run.bat`**. The script automatically initializes the virtual environment, installs requirements, generates sample test labels, and opens `http://127.0.0.1:5000` in your browser.

### Option B: Linux / macOS Launch
```bash
chmod +x setup_and_run.sh
./setup_and_run.sh
```

### Option C: Docker Local Test
```bash
docker build -t eat-safe .
docker run -p 5000:5000 -e PORT=5000 eat-safe
```

---

## 🧪 Automated Testing

Run unit tests anytime using pytest:
```bash
python -m pytest tests/
```

---

## ⚠️ Important Safety & Reliability Disclaimer

EAT SAFE is an **assistive information tool only** and does **NOT** provide medical diagnostic recommendations or guarantees of 100% safety. Users must always inspect physical food packaging labels manually before consumption.
