<div align="center">

# 🤖 @Uzmyjob_bot

### O'zbekiston mehnat bozori uchun AI asosidagi vakansiyalar agregatori va ariza topshirish boti

[![Python Version](https://img.shields.io/badge/Python-3.12%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Aiogram Version](https://img.shields.io/badge/Aiogram-3.13%2B-2CA5E0.svg?logo=telegram&logoColor=white)](https://docs.aiogram.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Code Style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Database](https://img.shields.io/badge/Database-PostgreSQL%20%7C%20SQLite-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![AI Engine](https://img.shields.io/badge/AI-Gemini%202.5%20Flash-8E75B2.svg?logo=googlegemini&logoColor=white)](https://ai.google.dev/)

</div>

---

## 📌 Loyiha haqida

**@Uzmyjob_bot** — O'zbekiston ish bozoridagi vakansiyalarni yagona oqimga yig'ib, nomzodning profili va rezyumesi asosida saralovchi hamda murojaat jarayonini tezlashtiruvchi Telegram bot.

### Faol ish manbalari va kengaytirish
- **Faol manbalar (`is_stub = False`):**
  - `osonish.uz` (`OsonIshAdapter`) — Bandlik vazirligining rasmiy portali JSON API orqali;
  - `uzjobs.uz` (`JobsUzScraperAdapter`, `source='jobs_uz'`) — rasmiy RSS (`rss_vak.cgi`) orqali;
  - `HeadHunter (api.hh.uz)`, ommaviy **Telegram IT-kanallari** (`t.me/s/...`) va **RSS** (`freelance.habr.com`).
- **Cheklangan adapter (`is_stub = True`):** `olx.py` (`OLXScraperAdapter`) — to'liq JSON-LD/HTML kartalar parseriga ega, biroq `www.olx.uz` CloudFront WAF (`403`) himoyasi sababli default pipeline'da o'chirilgan.

---

## ✨ Asosiy imkoniyatlar

- **Interaktiv Telegram FSM Wizard (`/wizard`):** lavozim, shahar/format, tajriba, minimal maosh, bandlik turi, kalit so'zlar, qora ro'yxat (`blacklist`), CV yuklash (PDF/DOCX, maks. 5 MB), Jinja2 Cover Letter shabloni va portfolio saqlash.
- **Profil boshqaruvi (`/profil`):** har bir maydonni alohida tahrirlash, moslik chegarasini (`threshold`) tanlash va `auto_apply` rejimini yoqish/o'chirish.
- **Ikki bosqichli aqlli moslashtirish (L1 + L2):**
  - **L1 (`compute_l1_score`):** kalit so'zlar, lavozim, shahar/remote, maosh va blacklist bo'yicha tezkor ball (`0.0 – 1.0`).
  - **L2 (`gemini-2.5-flash`):** faqat chegaraviy oraliqdagi (`0.25 <= L1 < 0.85`) vakansiyalar uchun Gemini tahlili, `asyncio.Semaphore(5)` va oylik budjet cheklovi (`GEMINI_MONTHLY_COST_LIMIT_USD`).
- **Xavfsizlik:**
  - CV va `hh.uz` OAuth2 tokenlari **Fernet** (`AES-128-CBC + HMAC-SHA256`) yordamida shifrlanadi.
  - Cover Letter shablonlari **`ImmutableSandboxedEnvironment`** va ruxsat etilgan o'zgaruvchilar (`vacancy_title`, `company_name`, `position`, `city`, `years_exp`, `sender_name`) bilan himoyalangan.
  - Telegram HTML xabarlarda `html.escape()`, CSV eksportida (`/export`) esa formula injection himoyasi mavjud.
  - `/delete_account` ikki bosqichli inline tasdiqlash orqali foydalanuvchi profili va arizalarini to'liq o'chiradi.
- **Monitoring va ishonchlilik:** `/health`, Prometheus `/metrics`, `structlog` PII filtri, `APScheduler` (`Asia/Tashkent`), `SourceHealthTracker`, `pg_dump` + Fernet backup moduli.

---

## 🤖 Telegram buyruqlari

| Buyruq | Vazifasi |
| :--- | :--- |
| `/start` | Botni boshlash yoki to'xtatilgan hisobni qayta faollashtirish |
| `/profil` | Joriy profilni ko'rish va maydonlarni tahrirlash |
| `/vacancies` | Oxirgi 7 kunlik mos vakansiyalardan eng yaxshilarini chiqarish |
| `/statistika` | Yuborilgan arizalar va vakansiyalar statistikasi |
| `/export` | Arizalar tarixini CSV fayl ko'rinishida yuklab olish |
| `/wizard` | Profilni noldan sozlash (`/cancel` bilan istalgan vaqt bekor qilish mumkin) |
| `/hh_login` (`/hh_auth`) | `hh.uz` OAuth2 avtorizatsiya havolasini olish |
| `/hh_code <kod>` | OAuth2 avtorizatsiya kodini shifrlangan tokenlarga almashtirish |
| `/hh_status` | `hh.uz` ulanish holatini tekshirish |
| `/stop` | Bildirishnomalarni vaqtinchalik to'xtatish (`is_active = False`) |
| `/delete_account` | Tasdiqlash orqali barcha shaxsiy ma'lumotlarni o'chirish |
| `/yordam` (`/help`) | Qo'llanma |

---

## 🗂 Loyiha tuzilishi

```text
Uzmyjob_bot/
├── .github/workflows/ci.yml        # Ruff, Alembic, Pytest va Smoke test CI
├── deploy/
│   ├── render/.env.render.example  # Render uchun muhit o'zgaruvchilari namunasi
│   └── vps/                        # VPS uchun systemd, nginx, prometheus, backup skriptlari
├── scripts/
│   └── smoke_test.py               # Avtonom E2E smoke test skripti
├── src/uzmyjob/
│   ├── adapters/                   # hh_api, osonish, jobs_uz (uzjobs RSS), tg_channels, rss, olx (WAF stub)
│   ├── agents/                     # Gemini client, matcher, reranker, cover_letter, auditor
│   ├── apply/                      # hh.uz OAuth2/apply va Telegram/SMTP kontakt servislari
│   ├── bot/                        # main.py (Webhook/Polling + HTTP server), middleware, handlers/
│   ├── migrations/                 # Alembic migratsiyalari (001, 002)
│   ├── models/                     # SQLAlchemy 2.0 modellar (User, Vacancy, Application, Source)
│   ├── pipeline/                   # JobPipeline (fetch, dedupe, match, notify) va SourceHealthTracker
│   ├── templates/                  # Cover letter Jinja2 shablonlari (uz, ru, en)
│   ├── utils/                      # backup, crypto, cv_parser, filters, healthcheck, i18n, logger, metrics
│   └── config.py                   # Pydantic Settings va validate_runtime()
├── tests/                          # Birlik va integratsiya testlari
├── .dockerignore
├── .env.example
├── alembic.ini
├── docker-compose.yml              # Local PostgreSQL + bot konteyneri
├── Dockerfile
├── LICENSE
├── MANIFEST.in
├── pyproject.toml
└── render.yaml                     # Render.com Blueprint (Docker + PostgreSQL)
```

---

## 🚀 Mahalliy ishga tushirish (Local Development)

### 1. Muhitni tayyorlash

```bash
git clone https://github.com/AdhamIsoqov/Uzmyjob_bot.git
cd Uzmyjob_bot

python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1

pip install -e ".[dev]"
```

### 2. `.env` faylini sozlash

```bash
cp .env.example .env
```

Majburiy `FERNET_KEY` yaratish:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Local test uchun SQLite ishlatmoqchi bo'lsangiz `.env` da:
```env
POSTGRES_URL=sqlite+aiosqlite:///./uzmyjob.db
```

### 3. Migratsiya va botni ishga tushirish

```bash
alembic upgrade head
python -m uzmyjob.bot.main
```

`WEBHOOK_URL` bo'sh bo'lsa bot **Long Polling** rejimida ishlaydi va `PORT` (standart `8080`) da `/health` hamda `/metrics` endpointlarini ko'taradi.

### 4. Docker Compose bilan ishga tushirish

```bash
docker compose up --build -d
docker compose logs -f bot
```

---

## ⚙️ Muhit o'zgaruvchilari (`.env`)

| O'zgaruvchi | Majburiyligi | Tavsif |
| :--- | :--- | :--- |
| `BOT_TOKEN` | Majburiy | `@BotFather` dan olingan Telegram bot tokeni |
| `GEMINI_API_KEY` | Tavsiya etiladi | Google AI Studio (`gemini-2.5-flash`) API kaliti |
| `FERNET_KEY` | Majburiy | 44 belgili URL-safe base64 Fernet shifrlash kaliti |
| `POSTGRES_URL` / `DATABASE_URL` | Majburiy | PostgreSQL (`postgresql+asyncpg://...`) yoki `sqlite+aiosqlite:///...` |
| `WEBHOOK_URL` | Production | Masalan `https://your-service.onrender.com` (bo'sh = Polling) |
| `WEBHOOK_SECRET` | Webhookda majburiy | Kamida 16 ta `[A-Za-z0-9_-]` belgidan iborat maxfiy token |
| `PORT` | Ixtiyoriy | HTTP server porti (`Dockerfile` da `10000`, standart `8080`) |
| `HH_CLIENT_ID`, `HH_CLIENT_SECRET` | Ixtiyoriy | `hh.uz` OAuth2 integratsiyasi uchun |
| `POLL_INTERVAL_MINUTES` | Ixtiyoriy | Vakansiya tekshirish oralig'i (standart `15`) |
| `MATCH_THRESHOLD` | Ixtiyoriy | Minimal moslik chegarasi (standart `0.55`) |
| `LLM_RERANK_THRESHOLD` | Ixtiyoriy | Re-ranker chegarasi (standart `0.40`) |
| `GEMINI_MONTHLY_COST_LIMIT_USD` | Ixtiyoriy | Oylik LLM budjet limiti (standart `5.0`) |
| `THROTTLE_RATE` | Ixtiyoriy | Foydalanuvchi uchun 1 daqiqalik so'rov limiti (standart `30`) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` | Ixtiyoriy | Email orqali ariza yuborish uchun |

---

## ☁️ Render.com da Deploy qilish

Loyiha ildizida `render.yaml` Blueprint fayli tayyorlangan (`Docker` Web Service + Managed PostgreSQL).

1. [Render Dashboard](https://dashboard.render.com) da **New -> Blueprint** ni tanlang va repozitoriyni ulang.
2. Quyidagi `sync: false` muhit o'zgaruvchilarini Render panelida qo'lda kiriting (`deploy/render/.env.render.example` ga qarang):
   - `BOT_TOKEN`
   - `GEMINI_API_KEY`
   - `FERNET_KEY` (`Fernet.generate_key()` orqali generatsiya qiling)
   - `WEBHOOK_URL` (deploy qilingan servis URL manzili, masalan `https://uzmyjob-bot.onrender.com`)
   - `WEBHOOK_SECRET` (Render `generateValue: true` avtomatik yaratadi)
3. Deploy tugagach `https://<service-name>.onrender.com/health` endpointi `200 OK` qaytarishini tekshiring.

> **Render Free rejasi cheklovlari:**
> - **Free Web Service** 15 daqiqa trafik bo'lmasa uxlaydi (`APScheduler` fon vazifalari ham to'xtaydi; doimiy polling uchun pullik reja yoki tashqi cron ping / VPS talab qilinadi).
> - **Free PostgreSQL** bazasi 90 kundan keyin muddati tugaydi.
> - Konteyner fayl tizimi vaqtinchalik (*ephemeral*), shu bois `logs/` va `backups/` konteyner qayta ishga tushganda saqlanmaydi.

VPS uchun muqobil konfiguratsiyalar [`deploy/vps/`](deploy/vps) papkasida joylashgan (`docker-compose.prod.yml`, `nginx.conf`, `prometheus.yml`, `uzmyjob.service`, `backup_cron.sh`, `logrotate.conf`).

---

## 🧪 Testlash va Sifat nazorati

```bash
# Linter
ruff check src tests scripts

# Barcha testlar
pytest tests/ -v

# Qamrov hisoboti bilan
pytest tests/ -v --cov=uzmyjob --cov-report=term-missing

# Tezkor E2E smoke test (alohida/test DB bilan)
python scripts/smoke_test.py
```

---

## 🔐 Xavfsizlik eslatmasi

Agar repozitoriy tarixida ilgari `.env` yoki maxfiy kalitlar saqlangan bo'lsa, production'ga chiqishdan oldin `@BotFather` orqali Telegram `BOT_TOKEN` ni `/revoke` qilib yangilang va yangi `FERNET_KEY` yarating.

---

## 📄 Litsenziya

Ushbu loyiha [MIT License](LICENSE) asosida tarqatiladi.
