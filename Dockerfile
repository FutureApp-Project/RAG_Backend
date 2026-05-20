FROM cgr.dev/chainguard/python:latest-dev AS builder

USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PATH="/app/venv/bin:${PATH}"

WORKDIR /app

RUN apk add --no-cache \
  build-base \
  ffmpeg \
  glib \
  mesa-gl \
  tesseract-ocr

RUN python -m venv /app/venv

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

FROM cgr.dev/chainguard/python:latest-dev

USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  PATH="/app/venv/bin:${PATH}"

WORKDIR /app

RUN apk add --no-cache \
  ffmpeg \
  glib \
  mesa-gl \
  tesseract-ocr

COPY --from=builder /app/venv /app/venv
COPY --chown=nonroot:nonroot . .

USER nonroot

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=5)"]

ENTRYPOINT ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]