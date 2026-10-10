# Standard syntax uses the bundled frontend; CI needs no Docker Hub frontend pull.
ARG PYTHON_BASE_IMAGE=python:3.11-slim
FROM ${PYTHON_BASE_IMAGE} AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Önce sadece requirements — değişmediğinde katman cache'lensin.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Kaynak kodu
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
COPY tests ./tests

# Non-root kullanıcı — production hijyeni
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/data/reviews \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Default: API server. Cron worker için `python scripts/run_job.py ...`
# Migration için `alembic upgrade head` (entrypoint olarak compose'da)
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
