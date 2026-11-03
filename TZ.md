# TZ — @Uzmyjob_bot: Telegram orqali vakansiya izlash va murojaat tizimi

**Versiya:** 1.1 · **Sana:** 2026-11-04
**Til:** O'zbek (bot interfeysi) · **Buyurtmachi:** dasturchi (o'zi uchun ish izlaydi)
**Ish rejimi:** Google Antigravity (App + CLI) · Windows da ishlab chiqish → Linux VPS deploy

---

## 0. Qisqa bayon

Foydalanuvchi Telegramdan chiqmasdan:
1. o'zi tanlagan vakansiyalarni olishi,
2. ularni o'z profiliga qarab filtrdan o'tgan holda ko'rishi,
3. har biriga murojaat xabari, CV, resume va portfolio yubora olishi kerak.

Bu `TZ.md` — Antigravity agenti uchun jamlangan vazifa: uni o'qib, milestone'larni
bosqichma-bosqich bajaradi, subagentlarni parallel ishga tushiradi va
Automations bilan doimiy nazoratni yoqadi.

---

## 1. Maqsad va muvaffaqiyat mezonlari (Acceptance criteria)

| # | Mezon | O'lchash |
|---|---|---|
| 1 | Bot 24/7 ishlaydi (Docker/systemd restart bilan) | 24 soatlik ish davrida < 1 tushish |
| 2 | Yangi vakansiya 15 daqiqada Telegramga yetib boradi | hh.uz test siklida |
| 3 | Filtr aniqligi: saralangan (✅) ≥ 90 % to'g'ri mos | manual tekshiruv listi |
| 4 | hh.uz-da to'liq auto-murojaat ≤ 10 sek | API log |
| 5 | OLX / jobs.uz uchun murojaat: kontakt + tayyor xabar + CV — 2 bosish | manual test |
| 6 | CV va xabar shablonlari bot ichidan (document yuborish orqali) saqlanadi | DB da fayl hujjati |
| 7 | Bir martlik hisob qayd etish: `/start` → profil + CV qo'shish ≤ 5 daqiqa | manual |
| 8 | `/stop` → foydalanuvchi ma'lumotlari to'liq o'chiriladi ≤ 10 sek | DB tekshiruv |

---

## 2. Foydalanuvchi skenariylari

### 2.1 Birinchi sozlash (wizard)
1. `/start` → til tanlanadi (uz / ru / en).
2. Wizard: pozitsiya (masalan "Backend / Python / Django / FastAPI"), shahar (Toshkent / Remote), tajriba darajasi, minimal maosh, bandlik turi (to'liq / yarim / proyekt / freelance), kalit so'zlar, **black-list** (masalan `стажировка, шаблон, инвестиции, пирамида`).
3. Foydalanuvchi CV faylni **document** sifatida yuboradi (PDF/DOCX), cover-letter shablonini Jinja2 sintaksida yozadi (`{{ vacancy_title }}`, `{{ company_name }}` o'zgaruvchilari bilan), portfolio linklarini qo'shadi.
4. Birinchi ishga tushish: so'nggi 7 kunlik vakansiyalar bo'yicha "backfill" yuboriladi.

### 2.2 Kündagi ishlash (standart)
1. Bot har 15 daqiqada manbalarni tekshiradi (dedupe bilan — `(source, external_id)` unique, ham vakansiya, ham murojaat jadvallarida).
2. Yangi vakansiya `match_score` bilan filtrlanadi (threshold ≥ 0.55); yaxshi moslari inline tugmalar bilan:
   ✅[Murojaat qilish] · ✉️[Xabar + CV yuborish] · 🔖[Keyingi o'qish] · ❌[Filtrdan chiqarish].
3. Foydalanuvchi bir tugma bosadi → bot cover letter ni Jinja2 template engine orqali render qiladi → murojaatni yuboradi (platform API / e-pochta / kontakt bo'yicha) va **"Yuborildi"** statusini DB'da saqlaydi.
4. Telegram anti-flood: `aiogram` `ThrottlingMiddleware` bilan har foydalanuvchi uchun ≤ 30 xabar/min cheklov.

### 2.3 Boshqaruv va hisobot
- `/profil` — sozlamalarni tahrirlash (threshold, black-list, kalit so'zlar).
- `/statistika` — bugungi ko'rdingiz, murojaat qilingan, javob kelgan.
- `/export` — murojaatlar tarixi CSV formatida yuborish.
- `/stop` — bot to'xtatiladi; `/delete_account` — barcha shaxsiy ma'lumotlar va CV fayllar DB'dan o'chiriladi (GDPR-analog).

### 2.4 Cover letter personalizatsiyasi
Foydalanuvchi shablon yozadi, bot uni vakansiya ma'lumotlari bilan to'ldiradi:
```
Salom! Men {{ position }} lavozimiга murojaat qilyapman.
Kompaniya: {{ company_name }}.
Tajriba: {{ years_exp }} yil.
```
`Jinja2` render → ko'rsatish preview (foydalanuvchi tasdiqlaydi) → yuborish.

---

## 3. Ma'lumot manbalari (Uzbekistan job platforms)

| Priority | Manba | Usul | Auto-murojaat? | Milestone | Xavf/Eslatma |
|---|---|---|---|---|---|
| P0 | **hh.uz** | rasmiy ochiq API (`api.hh.uz`) | ✅ TO'LIQ (API orqali CV bilan) | M1 | OAuth2 flow lozim (§3.1) |
| P0 | **OLX.uz** ish bo'limi | scraping (httpx → Playwright) | ⚠️ kontakt + tayyor xabar (telefon/telegram/taklif) | M2 | robots.txt tekshirish (§11) |
| P1 | **jobs.uz** | scraping | ⚠️ e-pochta / kontakt | M2 | |
| P1 | **UstozShogird & shunga o'xshash Telegram kanallar** | `t.me/s/kanal` scrape yoki Telethon | ✅ kanal/post ga link + tayyor xabar | M2 | |
| P1 | **Freelance** (Upwork RSS / Kwork / Freelancer.com) | RSS/API | ❌ link out | M3 | Upwork RSS auth talab qiladi; region bloklash xavfi bor |
| P2 | **xati.uz va boshqalar aggregates** | scraping | ❌ | keyinroq | |

### 3.1 hh.uz OAuth2 autentifikatsiya oqimi
hh.uz `POST /negotiations` uchun OAuth2 access token kerak:
1. `GET /authorize?response_type=code&client_id=...` → foydalanuvchi brauzerda ruxsat beradi.
2. `POST /token` → `access_token` + `refresh_token` olinadi.
3. Tokenlar DB'da shifrlab saqlanadi; `access_token` muddati tugaganda `refresh_token` bilan yangilanadi.
4. hh.uz resume: foydalanuvchi CV'ni `POST /resumes` orqali hh.uz'ga yuklaydi → `resume_id` olinadi → murojaat paytida ishlatiladi.

⚠️ Arxitektura qoida: har manba **alohida `ScraperAdapter`** (interface) bo'ladi.
Bir manba buzilsa, tizimning qolgan qismi ishlashda davom etadi.

**Rate-limit va xatolik strategiyasi:**
- Har manba: max 1 req/sek; `httpx` Retry + exponential backoff (3 urinish).
- Barcha urinishlar tugasa → `source_status = "error"` DB'da saqlanadi.
- Kritik xato bo'lsa → foydalanuvchiga Telegram xabar: "⚠️ [Manba nomi] vaqtincha mavjud emas".
- Dead-letter queue: xato vakansiyalar JSON logga yoziladi, keyingi siklda qayta uriniladi.
- User-Agent rotatsiya; anti-bot uchun Playwright faqat kerak bo'lganda.

---

## 4. Texnologiya stack va file structure

| Qatlam | Yechim |
|---|---|
| Bot | `aiogram 3.x` (Python 3.12, async), FSM, ThrottlingMiddleware, long-polling (dev) / webhook (VPS + nginx + SSL) |
| DB | PostgreSQL (Docker) + SQLAlchemy 2.0 async + Alembic (zero-downtime migration) |
| Scheduler | APScheduler (bot ichida), interval 15 min, retry exponential backoff |
| Scraping | `httpx` (APIlar) + Playwright (JS-heavy sahifalar, headless Chromium) |
| Template | `Jinja2` — cover letter personalizatsiyasi |
| i18n | `babel` + `.po/.mo` fayllari; uz/ru majburiy, en fallback; `LOCALE_DIR = src/locales/` |
| Matching | L1: kalit so'z + TF-IDF skoring (threshold ≥ 0.55); L2 (optional): Gemini Flash re-rank (faqat threshold 0.4–0.55 orasidagi "qiyin" vakansiyalar uchun, cost limit: $5/oy) |
| CV parsing | `pdfplumber` / `python-docx` |
| Shifrlash | CV fayllari disk va DB'da AES-256 (Fernet) bilan shifrlangan; key `.env`'da |
| Logging | `structlog` JSON formatda; loglardan PII (ism, telefon, CV matni) filtrlanadi |
| Monitoring | Prometheus (`prometheus_client`) + Grafana (Docker); Sentry DSN `.env`'da |
| Deploy | Docker Compose (app + postgres + prometheus + grafana) → VPS, systemd, healthcheck |
| Reverse proxy | nginx + Let's Encrypt (certbot) — webhook HTTPS endpoint uchun |
| CI/CD | GitHub Actions: `pytest` → `ruff` lint → `docker build` → VPS'ga `ssh deploy` |
| Muhit | `.env` + pydantic-settings (BOT_TOKEN, HH_CLIENT_ID, HH_CLIENT_SECRET, SMTP_*, POSTGRES_URL, FERNET_KEY, SENTRY_DSN, GEMINI_API_KEY) |

```
@Uzmyjob_bot/
├── TZ.md                     ← bu fayl
├── .github/
│   └── workflows/
│       └── ci.yml            ← pytest + ruff + docker build + ssh deploy
├── .agents/
│   ├── skills/               ← 7 ta skill (§6)
│   ├── agents/               ← 5 ta subagent (§7)
│   ├── rules/                ← doimiy qoidalar (§8)
│   ├── mcp_config.json       ← MCP serverlar (§5)
│   └── plugins/              ← keyinroq (§9)
├── sidecars/
│   └── uzmyjob-watchdog/sidecar.json
├── src/uzmyjob/
│   ├── bot/                  ← aiogram handlers, FSM, keyboards, middleware
│   ├── pipeline/             ← fetch → normalize → dedupe → match → notify
│   ├── adapters/             ← hh_api.py, olx.py, jobs_uz.py, tg_channels.py, rss.py
│   ├── apply/                ← hh_apply.py, email_apply.py, contact_apply.py
│   ├── models/               ← User, Vacancy, Application, CV, Source
│   ├── locales/              ← uz/, ru/, en/ .po/.mo fayllar
│   ├── templates/            ← Jinja2 cover letter shablonlari
│   └── utils/
│       ├── crypto.py         ← AES-256 Fernet wraper
│       └── logger.py         ← structlog konfiguratsiyasi
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── nginx/
│   └── nginx.conf
├── docker-compose.yml
├── docker-compose.prod.yml
└── pyproject.toml
```

---

## 5. MCP konfiguratsiyasi — `.agents/mcp_config.json`

Antigravity bu faylni auto-discovery qiladi. App'dagi MCP Store'dan ham qo'shish mumkin.

```json
{
  "mcpServers": {
    "chrome-devtools": { "command": "npx", "args": ["-y", "chrome-devtools-mcp@latest"] },
    "playwright":     { "command": "npx", "args": ["-y", "@playwright/mcp@latest"] },
    "context7":       { "command": "npx", "args": ["-y", "@upstash/context7-mcp@latest"] },
    "github":         { "serverUrl": "https://api.githubcopilot.com/mcp/",
                        "headers": { "Authorization": "Bearer <GITHUB_PAT>" } },
    "postgres":       { "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-postgres",
                                 "postgres://uzmyjob:pass@localhost/uzmyjob"] },
    "sequential-thinking": { "command": "npx",
                             "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"] }
  }
}
```

**MCP'lar nima uchun:**
- `chrome-devtools` / `playwright` — OLX, jobs.uz JS-heavy sahifalarini brauzer tekshiruvi, scraper debug.
- `context7` — aiogram 3, SQLAlchemy 2, Jinja2, babel hujjatlarini yangi versiyadan o'qish.
- `github` — repo push, PR, issue, GitHub Actions workflow nazorat.
- `postgres` — migratsiya tekshirish, test data bilan ishlash.
- `sequential-thinking` — matching algoritmini rejalashtirish.

Kerak bo'lmagan serverlar `disabled: true` qilinadi.

---

## 6. Agent Skills (`.agents/skills/<name>/SKILL.md`)

| Skill | Qachon ishlaydi | Mundarija |
|---|---|---|
| **uz-job-sources** | scraper/adapter yozilganda | hh.uz API endpoint'lari + OAuth2 flow, OLX/jobs.uz sahifa tuzilishi, kanal linklari, rate-limit va etika qoidalari, robots.txt holati |
| **apply-flows** | murojaat moduli yozilganda | hh.uz apply API (resume_id oqimi), SMTP orqali e-pochta apply, contact-only apply, Jinja2 cover letter render |
| **bot-fsm** | bot handlerlari yozilganda | aiogram 3 FSM, inline callbacks, keyboards, ThrottlingMiddleware, Telegram rate-limit, HTML parse mode, `/stop` + `/delete_account` oqimlari |
| **db-conventions** | schema o'zgarganda | SQLAlchemy 2 async, Alembic zero-downtime, naming, test factories, Fernet encrypt/decrypt field |
| **deploy-vps** | deploy fayllari yozilganda | Docker build, compose (prod/dev), nginx + Let's Encrypt, systemd, healthcheck, log rotation, backup, Prometheus/Grafana setup |
| **test-runners** | criteria pass qilish uchun | pytest, Playwright E2E, smoke script buyruqlari, GitHub Actions CI konfiguratsiyasi |
| **i18n-localization** | bot UI matni yozilganda | babel `.po/.mo` workflow, uz/ru/en kataloglari, `gettext` wraper, fallback strategiyasi |

---

## 7. Custom Subagents (`.agents/agents/*.md`) — parallel bajarish

| Subagent | Vazifa | tools | model |
|---|---|---|---|
| **hh-api-builder** | hh.uz adapter (OAuth2 + fetch + match + apply API) | view_file, replace_file_content, run_command, mcp(context7) | pro |
| **scraper-builder** | OLX / jobs.uz / kanallar scraperlari + error handling | view_file, replace_file_content, grep_search, run_command, mcp(playwright) | pro |
| **bot-builder** | aiogram handlerlar + FSM + keyboards + i18n | view_file, replace_file_content, run_command | inherit |
| **test-runner** | pytest + GitHub Actions ishga tushirish + xatolarni tahlil | run_command, view_file | flash |
| **code-auditor** | security / ToS / PII / Fernet usage tekshiruvi | view_file, grep_search, run_command | pro |

Misol:

```markdown
---
name: scraper-builder
description: OLX/jobs.uz va Telegram kanal scraperlarini yozadi. Adapter pattern,
  rate-limit, anti-bot strategiyalar, dead-letter queue va error handling.
tools: [view_file, replace_file_content, grep_search, run_command]
subagent: true
mainAgent: false
model: pro
commandExecutionPolicy: sandbox
skills:
  - skills/uz-job-sources
---
# System Prompt
Sen web-scraper mutaxassisi, adapter'larni yozadi. Hech qachon 1 rps dan oshirma,
User-Agent to'g'ri qo'y, Playwright faqat httpx yetmasa ishlat.
Xato bo'lsa dead-letter log yoz, retry 3 marta, keyin source_status="error" qo'y.
```

Bu yerda Antigravity kuchi: subagentlar parallel — scraper va bot ikki zamonda
yoziladi, main agent integratsiya qiladi. Murakkab ishlarda `/teamwork` (pullik plan),
algoritmik qiyin joyda `/boost` ishlatiladi.

---

## 8. Rules (`.agents/rules/`) — doimiy qoidalar

- **rule-code-review:** merge oldin `code-auditor` subagenti tekshiradi.
- **rule-scrapers-rps:** hech bir scraper 1 rps dan oshmasin; Playwright faqat HTTP yetmaganda; robots.txt va ToS M0 da tekshiriladi.
- **rule-i18n:** bot UI uz/ru majburiy; xato holatlarda en fallback; barcha matnlar `babel` `.po` fayllarda, hardcode yo'q.
- **rule-secrets:** kalitlar kodda yo'q, faqat `.env`; `.env.example` commit qilinadi; `FERNET_KEY` va `HH_CLIENT_SECRET` aylantirilishi (rotation) har 90 kunda eslatiladi.
- **rule-tests:** har milestone adapteri uchun unit test (mock fetch) majburiy; CI yashil bo'lmasa merge yo'q.
- **rule-pii:** server loglarida CV matni, telefon, email bo'lmasin; `structlog` filtri majburiy; `crypto.py` orqali saqlash.
- **rule-anti-flood:** aiogram `ThrottlingMiddleware` har foydalanuvchi uchun ≤ 30 msg/min; xabar ommaviy yuborishda `asyncio.sleep(0.05)` bilan throttle.

---

## 9. Automation / Sidecars — doimiy rejali ishlar

**Watchdog** (`sidecars/uzmyjob-watchdog/sidecar.json`):

```json
{
  "name": "uzmyjob-watchdog",
  "builtin": "schedule",
  "cron": "0 */6 * * *",
  "prompt": "smoke script ishga tushir; bot tushgan bo'lsa log yoz va docker compose restart; Prometheus metrikalarini tekshir (memory < 300 MB, uptime); hisobotni aytkaz."
}
```

**Daily report** (har 22:00): bugun nechta yangi vakansiya, nechta murojaat,
nechta javob kelgan, Gemini re-rank sarflangan cost — bot orqali foydalanuvchiga.

**Token refresh** (har 1 soat): hh.uz OAuth2 access_token muddati tekshiriladi;
muddati tugay degan bo'lsa refresh_token bilan yangilanadi.

Bular Antigravity **Automations** panelida ko'rinadi; dev jarayonida `/schedule`
 bilan "15 daqiqa keyin testlarni qayta ko'r" kabi timerlar ishlatiladi.

---

## 10. Milestones

| M | Vazifa | Qamrab oladigan criteria |
|---|---|---|
| **M0** | Repo init, DB schema (dedupe unique constraints bilan), `.env`, docker-compose, nginx skeleton, `/start` + `/stop` + `/delete_account` ishlovchi, i18n scaffold | — |
| **M1** | hh.uz OAuth2 flow + adapter: fetch + match + Telegram notify + API orqali auto-apply (resume_id oqimi bilan) | 2, 3, 4 |
| **M2** | OLX + jobs.uz + Telegram-kanal adapterlar + contact-apply (xabar + CV) + dead-letter queue | 5 |
| **M3** | CV parsing (pdfplumber/docx), full wizard, Jinja2 cover letter, RSS/freelance adapterlar | 6, 7 |
| **M4** | Matching: LLM re-rank (Gemini Flash, cost-gated), dedupe takomil, black-list, statistik, CSV export, ThrottlingMiddleware | 3 (≥90%) |
| **M5** | VPS deploy (Docker prod), nginx + SSL, systemd, watchdog sidecar, Prometheus/Grafana, structured logging, backup | 1, 8 |
| **M6** | CI/CD (GitHub Actions), E2E test (Playwright), 24 soatlik stress (memory < 300 MB), hujjatlashtirish | barcha |

---

## 11. Xavfsizlik va etika

1. **Rate limit:** har manba 1 rps max; hh.uz API rasmiy limitiga moslash; exponential backoff.
2. **ToS tekshiruvi (M0 da):**
   - hh.uz — rasmiy API (✅ OK).
   - OLX — `robots.txt` va Terms of Service o'qiladi; agresiv crawl yo'q; agar taqiq bo'lsa M2 da OLX o'chiriladi yoki minimal headless session ishlatiladi.
   - jobs.uz — xuddi OLX tartibida.
3. **PII himoyasi:**
   - CV fayllar DB'da AES-256 (Fernet) bilan shifrlangan.
   - Backup ham shifrlangan (GPG).
   - Server loglarida CV matni, email, telefon bo'lmasin (`structlog` PII filter).
   - `/delete_account` → foydalanuvchi barcha ma'lumotlari + CV fayllari DB'dan va diskdan 10 sek ichida o'chiriladi.
4. **No-spam:** bir vakansiyaga faqat **bir marta** murojaat; DB'da `(source, external_id)` unique — ham `vacancies`, ham `applications` jadvalida.
5. **Preview majburiy (hozir):** CV yuborishdan oldin foydalanuvchiga cover letter preview ko'rsat; auto rejim faqat foydalanuvchi "Doim tasdiqlash" tanlasa.
6. **Secret rotation:** `BOT_TOKEN`, `HH_CLIENT_SECRET`, `FERNET_KEY` har 90 kunda almashtiriladi; Watchdog eslatadi.
7. **OAuth2 token xavfsizligi:** tokenlar memory'da emas, faqat shifrlangan DB'da; `.env`'da `FERNET_KEY`.

---

## 12. Qabul testlari

- [ ] `pytest` barcha yashil (unit + integration)
- [ ] GitHub Actions CI: push → test → lint → docker build — barchasi yashil
- [ ] E2E smoke: `/start` → wizard → soxta hh.uz vakansiya → murojaat → "Yuborildi"
- [ ] `/delete_account` → DB tekshiruv: foydalanuvchi ma'lumotlari yo'q
- [ ] Cover letter Jinja2 render: shablon + vakansiya ma'lumoti → to'g'ri matn
- [ ] Manual: OLX'dan real vakansiya → kontakt + tayyor xabar formatini ko'rish
- [ ] `docker compose up -d` → `curl /health` → 200
- [ ] Prometheus metric: `curl /metrics` → `bot_uptime`, `vacancy_fetched_total` ko'rinadi
- [ ] 24 soatlik ish: memory < 300 MB, tushish bo'lmagan
- [ ] hh.uz OAuth2: token muddati tugaganda refresh ishlaydi
- [ ] Telegram flood: 50 ta xabar ketma-ket → ThrottlingMiddleware 429 qaytaradi emas, throttle qiladi

---

## 13. Agentga birinchi beriladigan prompt

```
TZ.md o'qi, M0 ni boshla. Har bir milestone'dan oldin plan chiz, subagentlarga
bo'lsam /teamwork ishlatish kerak bo'lsa ishlat. Code review'dan keyin commit,
milestone yakunida criteria'ni test qilib hisobot ber.

M0 uchun:
1. robots.txt tekshiruvi: OLX va jobs.uz saytlari uchun scraping ruxsatini aniqlash.
2. `pyproject.toml` + `docker-compose.yml` + `docker-compose.prod.yml` yaratish.
3. DB schema: User, Vacancy (unique source+external_id), Application, CV (Fernet field), Source.
4. Alembic initial migration.
5. `/start`, `/stop`, `/delete_account` minimal handlers.
6. i18n scaffold: babel `uz/ru/en` kataloglar.
7. `crypto.py` (Fernet wrap), `logger.py` (structlog + PII filter).
8. nginx skeleton + Let's Encrypt placeholder.
9. `.github/workflows/ci.yml` (pytest + ruff + docker build).
```

---

*Antigravity imkoniyatlari bu TZ da ishlatiladi:* Skills (progressive disclosure) · Custom subagents (parallel) · MCP (Chrome DevTools, Playwright, Context7, GitHub, Postgres, Sequential Thinking) · Rules · Sidecars/Automations (watchdog + daily report + token refresh) · `/schedule` (dev timerlar) · `/browser` subagent (sahifa tahlili) · `/teamwork` (katta refaktorlar) · `/boost` (qiyin algoritm) · Permissions & Sandbox (scraperlarning xavfsiz ishlashi).
