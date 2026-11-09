# Render.com Production Dockerfile for @Uzmyjob_bot
FROM python:3.12-slim

WORKDIR /app

# Tizim paketlari
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Tezkor uv paket menejeri
RUN pip install --no-cache-dir uv

# Qaramliklar va loyiha konfiguratsiyalari
COPY pyproject.toml alembic.ini ./
COPY src/ ./src/

# Loyihani tizim darajasida o'rnatish
RUN uv pip install --system .

# Render dinamik PORT beradi (sukut bo'yicha 10000)
ENV PORT=10000
EXPOSE 10000

# Ilovani ishga tushirish (Webhook yoki Polling)
CMD ["python", "-m", "uzmyjob.bot.main"]
