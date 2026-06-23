# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12.13
ARG ALPINE_VERSION=3.23

FROM python:${PYTHON_VERSION}-alpine${ALPINE_VERSION} AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --upgrade pip setuptools wheel \
    && /opt/venv/bin/python -m pip install -r requirements.txt \
    && /opt/venv/bin/python -m pip uninstall -y pip setuptools wheel packaging

FROM python:${PYTHON_VERSION}-alpine${ALPINE_VERSION} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

RUN addgroup -S app \
    && adduser -S -G app -h /app app

COPY --from=builder /opt/venv /opt/venv

COPY --chown=app:app main.py .
COPY --chown=app:app src ./src

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ping', timeout=2)"]

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log"]
