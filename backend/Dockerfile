# DocIntel backend: FastAPI API plus the background worker in one image.
# Render runs ./start.sh (both processes). docker-compose runs them as two services.
FROM python:3.12.16-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Tesseract OCR engine with English language data (used from Phase 1).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && tesseract --version

WORKDIR /app

# Install dependencies first so code changes do not rebuild this layer.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini start.sh ./
COPY app ./app

# Run as a non-root user.
RUN useradd --create-home --uid 10001 docintel \
    && chmod +x start.sh
USER docintel

EXPOSE 8000
CMD ["./start.sh"]
