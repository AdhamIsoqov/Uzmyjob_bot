---
name: rule-pii
globs: ["**/*.py"]
---
# PII himoya qoidasi

1. `structlog` orqali log yozilganda CV matni, telefon, email bo'lmasin.
2. `crypto.py` → `encrypt_str` / `decrypt_str` ishlatmasdan CV saqlamang.
3. DB backupda CV fayllar ham shifrlanadi (GPG).
4. `/delete_account` → 10 sek ichida barcha ma'lumotlar o'chadi.

