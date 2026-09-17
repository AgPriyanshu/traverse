# syntax=docker/dockerfile:1.9
#
# Build context is the REPO ROOT, not api/ — alembic and the app share one
# import root (the repo root), so `api` must be an importable package at /app.
ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim-bookworm AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl \
      libgl1 \
      libglib2.0-0 \
      libtesseract5 \
      libleptonica-dev \
      tesseract-ocr \
      tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*


FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /bin/
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential pkg-config libtesseract-dev \
 && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /src
# Only the lock inputs, so `uv sync` stays cached when application source
# changes — the difference between a 4-minute and a 6-second rebuild.
COPY api/pyproject.toml api/uv.lock ./
RUN touch README.md
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project


FROM base AS runtime
COPY --from=builder /opt/venv /opt/venv

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app \
    MODELS_CACHE_DIR=/models \
    HF_HOME=/models/huggingface \
    TRANSFORMERS_CACHE=/models/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/models/sentence-transformers \
    DOCLING_ARTIFACTS_DIR=/models/docling \
    TORCH_HOME=/models/torch

RUN groupadd --system --gid 10001 traverse \
 && useradd --system --uid 10001 --gid 10001 --create-home traverse \
 && mkdir -p /models /data \
 && chown -R traverse:traverse /models /data

WORKDIR /app
COPY --chown=traverse:traverse api/ /app/api/

USER traverse
EXPOSE 8000

# Overridden per service in compose (worker, migrate, healthcheck entrypoints).
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
