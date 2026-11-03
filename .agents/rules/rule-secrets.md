---
name: rule-secrets
globs: ["**/*.py", "**/*.yml", "**/*.yaml", "**/*.json"]
---
# Secrets qoidasi

1. Hech qachon token, parol, API key ni kod ichiga yozmang.
2. Faqat `.env` dan o'qing (`pydantic-settings` orqali).
3. `.env.example` commit qilinadi, `.env` HECH QACHON.
4. `FERNET_KEY` va `HH_CLIENT_SECRET` har 90 kunda almashtiring.
5. `GEMINI_API_KEY` ni log chiqarmang.

