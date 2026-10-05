# EAT SAFE — Multi-User Food Allergen Screening Platform 🛡️

**EAT SAFE** is a production-quality, multi-user assistive food-label screening application. It enables users to configure personalized allergen monitoring profiles, upload or photograph food packaging labels, perform OpenCV preprocessing and Tesseract OCR text extraction, and analyze ingredients against FSSAI-aligned allergen knowledge standards using deterministic NLP matching.

---

## 🌟 Key Features & Capabilities

- **Assistive Safety Screening**: Explicit and precautionary allergen classification (`DANGER`, `CAUTION`, `CLEAR_USER_SAFE`, `UNREADABLE`).
- **Deterministic AI Engine**: OpenCV image preprocessing + Tesseract OCR + NLP phrase normalization.
- **Expandable Allergen Knowledge Base**: 17+ FSSAI-aligned categories across 6 category groups (`Dairy & Egg`, `Nuts & Seeds`, `Grains & Legumes`, `Seafood`, `Spices & Vegetables`, `Additives & Preservatives`).
- **User Custom Monitored Terms**: Add custom ingredient terms (e.g., *Maltodextrin*, *Red 40*, *Preservative 211*).
- **Public Guest & Authenticated Scanning**: Unauthenticated guest label scanning + personalized account screening & scan history.
- **Barcode Lookup Provider**: Open Food Facts API integration with fallback to physical label camera scan.
- **Saved Products Repository**: Bookmark scans for quick access before purchasing or consuming.
- **Background Scan Processing Pipeline**: Asynchronous worker thread queue with real-time status polling (`/api/scans/<id>/status`).
- **Security & Data Isolation**: CSRF protection (Flask-WTF), session cookie hardening, rate limiting / lockout, Pillow byte image validation, and strict SQL user isolation (`WHERE user_id = session['user_id']`).
- **GDPR Privacy & Account Controls**: Export account data (`/settings/export`) and complete transactional account deletion with physical image cleanup.
- **Dual Database Support**: SQLite for local development and PostgreSQL for production environments.

---

## 🛠️ Tech Stack & Architecture

- **Backend**: Python 3.11+, Flask 3.1, Flask-WTF (CSRF Protection), Werkzeug.
- **Database**: SQLite (local dev) / PostgreSQL (production) with dual-adapter schema migration.
- **Computer Vision & OCR**: OpenCV (`opencv-python-headless`), Tesseract OCR (`pytesseract`), Pillow (`PIL`).
- **Frontend**: Responsive Jinja2 Templates, Inter Typography, Custom SaaS CSS System, Lucide Vector Icons.
- **Deployment**: Gunicorn, Docker, Render / Cloud Hosting compatible.

---

## 🚀 Quickstart & Local Setup

### 1. Prerequisites
- Python 3.11+
- Tesseract OCR engine installed on your OS:
  - **Linux / Ubuntu**: `sudo apt-get install -y tesseract-ocr libgl1`
  - **macOS**: `brew install tesseract`
  - **Windows**: Download Tesseract OCR installer and ensure it is added to System PATH.

### 2. Environment & Dependency Setup
```bash
# 1. Clone repository
git clone https://github.com/kratikachauhan1/EAT-SAFE.git
cd EAT-SAFE

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env configuration
cp .env.example .env
```

### 3. Run Development Server
```bash
python run.py
```
Open [http://localhost:5000](http://localhost:5000) in your browser.

---

## 🧪 Running Automated Tests

Run the complete 25+ automated pytest suite covering authentication, security, authorization isolation, OCR pipeline, saved products, and API endpoints:

```bash
python -m pytest tests/
```

Run the end-to-end processing pipeline test:
```bash
python test_e2e_pipeline.py
```

---

## 🐋 Docker & Render Deployment

### Run with Docker
```bash
# Build Docker image
docker build -t eatsafe-app .

# Run container
docker run -p 5000:5000 -e SECRET_KEY="your-prod-secret" eatsafe-app
```

### Render Deployment Instructions
1. Push your repository to GitHub.
2. Create a new **Web Service** on Render connected to your repository.
3. Environment: `Docker`.
4. Build Command: (Handled automatically via Dockerfile).
5. Set Environment Variables on Render:
   - `SECRET_KEY`: Long secure random string.
   - `DATABASE_URL`: Your Render PostgreSQL database connection string.
   - `FLASK_ENV`: `production`.

---

## ⚠️ Important Safety Disclaimer

*EAT SAFE is an assistive label-screening aid and not a medical diagnostic tool or guarantee of 100% food safety. Results depend on the text successfully extracted from packaging labels. Always manually verify physical packaging ingredients before consuming.*
