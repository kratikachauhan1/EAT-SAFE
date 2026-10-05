FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Render Build Arguments to prevent stale Docker layer caching
ARG RENDER_GIT_COMMIT=unknown
ARG BUILD_DATE=unknown

ENV ENVIRONMENT=production
ENV FLASK_ENV=production
ENV RENDER_GIT_COMMIT=${RENDER_GIT_COMMIT}

# COPY source files fresh on every build
COPY . .

EXPOSE 5000

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} run:app"]