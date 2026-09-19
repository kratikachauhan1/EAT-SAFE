# EATSAFE — AI-Powered Food Allergen Detection Web Application 🛡️🌿

**EATSAFE** is a production-oriented, AI-assisted food label screening application designed to protect individuals with food allergies. It allows users to create personal accounts, configure individual allergen profiles, upload or capture food label packaging photos, extract ingredient text using **OpenCV** and **Tesseract OCR**, analyze ingredient declarations via **NLP & phrase matching**, intersect detected terms against an **FSSAI-aligned Allergen Knowledge Base**, and generate personalized safety warnings.

---

## 📑 Table of Contents
1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Key Features](#3-key-features)
4. [Technology Stack](#4-technology-stack)
5. [Folder Structure](#5-folder-structure)
6. [Installation & Prerequisites](#6-installation--prerequisites)
7. [Environment Variables](#7-environment-variables)
8. [Database Setup (SQLite & PostgreSQL)](#8-database-setup-sqlite--postgresql)
9. [Local Development Guide](#9-local-development-guide)
10. [Running Automated Tests](#10-running-automated-tests)
11. [Docker Container Usage](#11-docker-container-usage)
12. [Production Deployment](#12-production-deployment)
13. [Render Deployment Configuration](#13-render-deployment-configuration)
14. [Database Migration Instructions](#14-database-migration-instructions)
15. [File & Image Storage Behavior](#15-file--image-storage-behavior)
16. [Authentication & Authorization Flow](#16-authentication--authorization-flow)
17. [Security Notes](#17-security-notes)
18. [Known Limitations](#18-known-limitations)
19. [Future Improvements](#19-future-improvements)

---

## 1. Project Overview
EATSAFE is designed as a SaaS food safety screening tool. It transforms static product packaging text into actionable risk intelligence tailored to each user's profile.
- **Core Pipeline**: Label Upload → OpenCV Preprocessing → Tesseract OCR → NLP Phrase Parsing → Knowledge Base Lookup → Personal Risk Intersection → Personalised Report.
- **Strict Product Safety Mandate**: EATSAFE is an assistive screening tool. It **NEVER** claims a product is "100% safe". When no allergens are found, it clearly states: *"No monitored allergen matching your profile was detected in the scanned label."*

---

## 2. Architecture
```text
┌────────────────────────────────────────────────────────────────────────┐
│                               FRONTEND                                 │
│          Modern HTML5 / CSS3 SaaS UI + Inter Font + Lucide Icons       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / Session
┌───────────────────────────────────▼────────────────────────────────────┐
│                             FLASK BACKEND                              │
│  ┌───────────────────────┐ ┌───────────────────┐ ┌───────────────────┐  │
│  │ @login_required Auth  │ │ Resource Access   │ │ Secure File Upload│  │
│  │ Session Management    │ │ Authorization     │ │ MIME & Magic Bytes│  │
│  └───────────┬───────────┘ └─────────┬─────────┘ └─────────┬─────────┘  │
└──────────────┼───────────────────────┼─────────────────────┼────────────┘
               │                       │                     │
┌──────────────▼───────────────────────▼─────────────────────▼────────────┐
│                      AI / OCR PIPELINE & ENGINE                        │
│  OpenCV (CLAHE/Sharpen) → Tesseract OCR → NLP Normaliser → Knowledge Base│
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Unified SQL Engine
┌───────────────────────────────────▼────────────────────────────────────┐
│                            DATABASE ENGINE                             │
│       Development: SQLite (WAL)  |  Production: PostgreSQL (Render)     │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Key Features
- **User Authentication**: Secure user registration, password hashing (`scrypt`/`pbkdf2`), login with Email/Username, and session invalidation logout.
- **Personal Profile Isolation**: User A and User B maintain completely isolated allergy profiles.
- **Scan History Ownership**: Server-enforced SQL ownership guarantees users only see their own scan results.
- **OpenCV Image Processing**: Normalizes dimensions, applies fast non-local means denoising, CLAHE contrast enhancement, sharpening, and adaptive thresholding.
- **OCR Confidence Evaluation**: Flags low-confidence scans (< 40%) with explicit warnings instructing users to perform manual inspection.
- **Context-Aware NLP**: Distinguishes between **Explicit Warnings** (`Contains: Milk`) and **Precautionary Cautions** (`May contain peanuts`).
- **Account Management**: Self-service settings for updating profiles, changing passwords, and account deletion.
- **Health Monitoring**: Dedicated `/health` endpoint for uptime monitoring and DB connectivity verification.

---

## 4. Technology Stack
- **Backend Framework**: Python 3.11+ / Flask 3.x
- **WSGI Production Server**: Gunicorn
- **Database**: SQLite (Development) / PostgreSQL (Production via `psycopg2-binary`)
- **Computer Vision**: OpenCV (`opencv-python-headless`)
- **OCR Engine**: Tesseract OCR (`pytesseract`)
- **Image Processing**: Pillow (`PIL`)
- **Authentication**: Werkzeug Security (`generate_password_hash`, `check_password_hash`)
- **Environment Management**: `python-dotenv`
- **Testing**: Pytest

---

## 5. Folder Structure
```text
EAT-SAFE/
├── app/                        # Application Package
│   ├── __init__.py             # Flask App Factory, Logging, Error Handlers, Health Route
│   ├── database.py             # SQLite & PostgreSQL Dual-Engine Database Adapter
│   ├── models.py               # User, Scan, Allergy & Detection SQL Operations
│   ├── routes.py               # Application & Auth Blueprint Routes
│   ├── preprocessing.py        # OpenCV Computer Vision Preprocessing Pipeline
│   ├── ocr.py                  # PyTesseract OCR Extraction Engine
│   ├── nlp.py                  # Text Normalization & Phrase Parser
│   ├── allergen_detector.py    # Allergen Knowledge Base Matcher
│   ├── personalisation.py     # Personal Risk Matrix & Personalised Evaluator
│   └── upload_utils.py         # Secure File Upload & MIME Magic Byte Validator
├── data/
│   ├── schema.sql              # Database Schema Definition
│   ├── allergen_kb.json        # FSSAI Allergen Categories & Synonyms Knowledge Base
│   └── allergen_app.db         # SQLite Development Database
├── static/
│   ├── css/style.css           # Modern SaaS Design System
│   ├── images/                 # Logo & Branding Assets
│   └── uploads/                # User Uploaded Label Scans
├── templates/                  # Jinja2 HTML Templates
│   ├── base.html               # Master Layout & Dynamic Navigation
│   ├── index.html              # Dashboard Page
│   ├── login.html              # Login Page
│   ├── register.html           # Account Registration Page
│   ├── scan.html               # Food Label Scanner & Preview Page
│   ├── result.html             # Personalised Allergen Screening Report
│   ├── profile.html            # User Allergy Profile Checklist
│   ├── history.html            # Scan History Log
│   ├── settings.html           # Account Settings Page
│   └── error.html              # Custom Error Page (400, 403, 404, 413, 500)
├── tests/                      # Automated Test Suite
│   ├── test_auth.py            # Registration, Login, Session Tests
│   ├── test_detection.py       # Allergen NLP Matcher Tests
│   ├── test_personalisation.py # Personalised Warning Matrix Tests
│   └── test_security_and_upload.py # Upload Validation, Authorization & Health Tests
├── .env.example                # Environment Variables Template
├── .gitignore                  # Git Ignore Specifications
├── Dockerfile                  # Container Production Definition
├── requirements.txt            # Python Dependencies Manifest
├── run.py                      # Application Entry Point
├── sample_labels/              # Sample Food Packaging Labels for Testing
├── setup_and_run.bat           # 1-Click Launch Script for Windows
└── setup_and_run.sh            # 1-Click Launch Script for Linux/macOS
```

---

## 6. Installation & Prerequisites

### System Requirements
1. **Python 3.11+**
2. **Tesseract OCR Engine**
   - **Windows**: Install Tesseract OCR from UB-Mannheim (`C:\Program Files\Tesseract-OCR`)
   - **Linux**: `sudo apt-get install tesseract-ocr libgl1`
   - **macOS**: `brew install tesseract`

---

## 7. Environment Variables
Copy `.env.example` to `.env` in the root directory:
```bash
cp .env.example .env
```

| Variable | Description | Default (Local) | Production Example |
| :--- | :--- | :--- | :--- |
| `FLASK_ENV` | Application environment mode | `development` | `production` |
| `DEBUG` | Enable Flask debug mode | `False` | `False` |
| `SECRET_KEY` | Flask session signing secret | `allergen-detector-secret-key-2026` | *(Random 64-char string)* |
| `DATABASE_URL` | Database Connection String | `sqlite:///data/allergen_app.db` | `postgresql://user:pass@host:5432/db` |
| `UPLOAD_FOLDER` | Uploaded images directory | `static/uploads` | `static/uploads` |
| `MAX_CONTENT_LENGTH` | Max file upload size in bytes | `16777216` (16 MB) | `16777216` |
| `STORAGE_TYPE` | File storage type | `local` | `local` or `s3` |

---

## 8. Database Setup (SQLite & PostgreSQL)

### Development (SQLite)
By default, if `DATABASE_URL` is omitted or points to SQLite, EATSAFE creates and connects to `data/allergen_app.db`. WAL (Write-Ahead Logging) mode and foreign keys are automatically enabled.

### Production (PostgreSQL)
Set the `DATABASE_URL` environment variable to your PostgreSQL instance:
```bash
DATABASE_URL=postgresql://eatsafe_user:password@localhost:5432/eatsafe_prod
```
The application database adapter (`app/database.py`) automatically detects PostgreSQL, connects via `psycopg2`, initializes tables, and handles SQL dialect differences.

---

## 9. Local Development Guide

### Quick 1-Click Launch (Windows)
Double-click `setup_and_run.bat`.

### Manual Setup (All Platforms)
```bash
# 1. Create and activate virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Initialize environment file
cp .env.example .env

# 4. Start server
python run.py
```
Open **`http://127.0.0.1:5000`** in your browser.

---

## 10. Running Automated Tests
Run the entire Pytest test suite:
```bash
python -m pytest tests/
```
All 15 tests verify authentication, user isolation, allergen matching, resource authorization, health monitoring, and secure file uploads.

---

## 11. Docker Container Usage

### Building the Image
```bash
docker build -t eatsafe-app .
```

### Running the Container
```bash
docker run -p 5000:5000 -e PORT=5000 -e SECRET_KEY="prod-key-123" eatsafe-app
```
Access at `http://localhost:5000`.

---

## 12. Production Deployment
Production deployments must use a production WSGI server. EATSAFE includes **Gunicorn**:
```bash
gunicorn --bind 0.0.0.0:5000 --workers 4 run:app
```

---

## 13. Render Deployment Configuration

EATSAFE is configured for seamless deployment on **Render**:

### Render Web Service Settings:
- **Environment**: `Docker`
- **Dockerfile Path**: `./Dockerfile`
- **Health Check Path**: `/health`
- **Environment Variables**:
  - `FLASK_ENV`: `production`
  - `DEBUG`: `False`
  - `SECRET_KEY`: *(Generate a secure random string)*
  - `DATABASE_URL`: *(Connect to Render PostgreSQL instance)*

---

## 14. Database Migration Instructions
- EATSAFE incorporates **automatic schema migration**. On application startup, `init_db()` executes `PRAGMA table_info` / column checks.
- If upgrading an existing SQLite database, missing columns (`full_name`, `password_hash`) are automatically added via `ALTER TABLE` without dropping existing scan or allergy records.

---

## 15. File & Image Storage Behavior
- **Local Mode** (`STORAGE_TYPE=local`): Uploaded label images are validated, assigned a UUID filename (e.g. `scan_a1b2c3d4.jpg`), and stored in `static/uploads/`.
- **Database References**: The database stores normalized relative paths (`uploads/scan_a1b2c3d4.jpg`), decoupling storage location from application code.

---

## 16. Authentication & Authorization Flow
1. **Registration**: Validates email format, username uniqueness, password complexity, hashes password via `werkzeug.security`, and creates user in database.
2. **Login**: Verifies credentials against database hash and sets `session['user_id']`.
3. **Route Protection**: `@login_required` blocks unauthenticated access to protected pages.
4. **Server Authorization**: Every route taking a resource ID (e.g., `/result/<scan_id>`) queries `WHERE scan_id = ? AND user_id = ?`. If a user attempts to access another user's scan ID, an HTTP 403 Forbidden is returned.

---

## 17. Security Notes
- **No Plaintext Passwords**: Passwords are never saved in plain text or returned in API responses.
- **No Passwords in Client Storage**: Passwords are not saved in `localStorage` or `sessionStorage`.
- **HTTP-Only Cookies**: Session cookies set `HttpOnly=True` and `SameSite=Lax`.
- **File Upload Security**: Uploads check both extension and Pillow image header magic bytes. Executable extensions are rejected, and filenames are randomized with UUIDs to prevent path traversal.
- **SQL Injection Defense**: All SQL queries use parameter placeholders (`?` or `%s`).

---

## 18. Known Limitations
- **OCR Accuracy**: OCR accuracy depends heavily on lighting, focus, image resolution, and packaging curvature.
- **Language Support**: Current OCR knowledge base focuses primarily on English ingredient packaging declarations.

---

## 19. Future Improvements
- Multi-language packaging OCR support (Hindi, Spanish, French).
- Barcode scanning lookup via Open Food Facts API integration.
- Export scan history reports to PDF.

---

## ⚠️ Safety & Product Disclaimer
EATSAFE is an **assistive food-label screening aid only** and does **NOT** provide medical diagnostic recommendations or guarantees of 100% safety. Always inspect physical food packaging labels manually before consumption.
