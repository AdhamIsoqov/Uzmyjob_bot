---
name: rule-scrapers-rps
globs: ["src/uzmyjob/adapters/**/*.py"]
---
# Scraper rate-limit qoidasi

1. Har bir manba uchun max **1 req/sek**.
2. `asyncio.sleep(1.0)` har so'rovdan keyin.
3. `User-Agent` to'g'ri o'rnating (bot emasligini bildirmang).
4. Playwright faqat `httpx` yetmagan hollarda.
5. robots.txt M0 da tekshiriladi — taqiq bo'lsa adapter o'chiriladi.

