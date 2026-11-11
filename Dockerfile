FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=10000

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml alembic.ini MANIFEST.in ./
COPY src/ ./src/

RUN uv pip install --system --no-cache .

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/logs /app/backups \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=10s --start-period=25s --retries=3 \
    CMD sh -c 'curl -fsS http://127.0.0.1:${PORT}/health || exit 1'

CMD ["python", "-m", "uzmyjob.bot.main"]
