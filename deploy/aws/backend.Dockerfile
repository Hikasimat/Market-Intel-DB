FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       libpq-dev \
       gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .

RUN python -m pip install --upgrade pip \
    && pip wheel \
       --no-cache-dir \
       --wheel-dir /wheels \
       -r requirements.txt


FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libpq5 \
       curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd \
       --create-home \
       --uid 10001 \
       --shell /usr/sbin/nologin \
       appuser

COPY --from=builder /wheels /wheels

RUN pip install \
    --no-cache-dir \
    /wheels/* \
    && rm -rf /wheels

COPY backend/ /app/

RUN mkdir -p /app/staticfiles \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--worker-class", "gthread", "--timeout", "120", "--graceful-timeout", "30", "--keep-alive", "5", "--max-requests", "500", "--max-requests-jitter", "50", "--access-logfile", "-", "--error-logfile", "-"]