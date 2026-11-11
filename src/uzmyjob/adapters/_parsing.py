"""Adapterlar uchun umumiy matn, maosh, shahar va sana tahlil yordamchilari."""
import html
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

_CITY_ALIASES: tuple[tuple[str, str], ...] = (
    ("remote", "Masofaviy"),
    ("masofaviy", "Masofaviy"),
    ("удален", "Masofaviy"),
    ("удалён", "Masofaviy"),
    ("tashkent", "Toshkent"),
    ("ташкент", "Toshkent"),
    ("тошкент", "Toshkent"),
    ("toshkent", "Toshkent"),
    ("samarkand", "Samarqand"),
    ("самарканд", "Samarqand"),
    ("samarqand", "Samarqand"),
    ("bukhara", "Buxoro"),
    ("бухар", "Buxoro"),
    ("buxoro", "Buxoro"),
    ("andijan", "Andijon"),
    ("андиж", "Andijon"),
    ("andijon", "Andijon"),
    ("fergana", "Farg'ona"),
    ("ферган", "Farg'ona"),
    ("фарғон", "Farg'ona"),
    ("farg'ona", "Farg'ona"),
    ("farg‘ona", "Farg'ona"),
    ("namangan", "Namangan"),
    ("наманган", "Namangan"),
    ("navoi", "Navoiy"),
    ("навои", "Navoiy"),
    ("navoiy", "Navoiy"),
    ("nukus", "Nukus"),
    ("нукус", "Nukus"),
    ("qoraqalpog", "Nukus"),
    ("каракалпак", "Nukus"),
    ("xorazm", "Xorazm"),
    ("хорезм", "Xorazm"),
    ("urganch", "Xorazm"),
    ("ургенч", "Xorazm"),
    ("qashqadaryo", "Qashqadaryo"),
    ("кашкадар", "Qashqadaryo"),
    ("qarshi", "Qashqadaryo"),
    ("карши", "Qashqadaryo"),
    ("surxondaryo", "Surxondaryo"),
    ("сурхандар", "Surxondaryo"),
    ("termiz", "Surxondaryo"),
    ("термез", "Surxondaryo"),
    ("jizzax", "Jizzax"),
    ("джизак", "Jizzax"),
    ("sirdaryo", "Sirdaryo"),
    ("сырдар", "Sirdaryo"),
    ("guliston", "Sirdaryo"),
)

_SCHEDULE_PAREN_RE = re.compile(
    r"\([^)]*\b(?:час\w*|hour\w*|недел\w*|week\w*|kun\w*|день|дней)\b[^)]*\)",
    re.IGNORECASE,
)


def strip_html(raw_html: str | None) -> str:
    """HTML teglarini olib tashlab, o'qishga qulay matn qaytaradi."""
    if not raw_html:
        return ""
    text = re.sub(r"<br\s*/?>|</(?:p|div|li|tr)>", "\n", raw_html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def normalize_city(raw_city: str | None, default: str = "O'zbekiston") -> str:
    """Shahar nomini (rus/ingliz/o'zbek) standart o'zbekcha shaklga keltirish."""
    if not raw_city:
        return default
    cleaned = re.sub(r"\s+", " ", html.unescape(raw_city)).strip()
    if not cleaned:
        return default
    lowered = cleaned.lower()
    for alias, canonical in _CITY_ALIASES:
        if alias in lowered:
            if "viloyat" in lowered or "област" in lowered or "region" in lowered:
                return f"{canonical} viloyati" if canonical != "Masofaviy" else canonical
            return canonical
    return cleaned[:100]


def parse_salary_text(
    text: str | None,
    default_currency: str | None = None,
) -> tuple[int | None, int | None, str | None]:
    """Maosh matnidan (min, max, valyuta) uchligini ajratib oladi."""
    if not text:
        return None, None, None

    cleaned = _SCHEDULE_PAREN_RE.sub(" ", html.unescape(text)).replace("\xa0", " ")
    lower = cleaned.lower()

    currency: str | None = default_currency
    if any(tok in lower for tok in ("$", "usd", "у.е", "у.e", "долл")):
        currency = "USD"
    elif any(tok in lower for tok in ("€", "eur", "евро")):
        currency = "EUR"
    elif any(tok in lower for tok in ("сум", "so'm", "so‘m", "som", "uzs", "сўм")):
        currency = "UZS"
    elif "руб" in lower or "rub" in lower or "₽" in lower:
        currency = "RUB"

    matches = re.findall(r"\d+(?:[\s,]\d{3})+|\d+", cleaned)
    numbers: list[int] = []
    for token in matches:
        try:
            num = int(re.sub(r"[\s,]", "", token))
        except ValueError:
            continue
        if num > 0:
            numbers.append(num)

    if not numbers:
        return None, None, None

    if currency is None:
        currency = "USD" if numbers[0] < 20000 else "UZS"

    if len(numbers) >= 2 and re.search(r"[-–—]|до|gacha|to", lower):
        sal_min, sal_max = min(numbers[0], numbers[1]), max(numbers[0], numbers[1])
        return sal_min, sal_max, currency

    val = numbers[0]
    if re.search(r"\b(?:от|from)\b|dan\b", lower) and not re.search(r"\b(?:до|to|gacha)\b", lower):
        return val, None, currency
    if re.search(r"\b(?:до|to)\b|gacha\b", lower) and not re.search(r"\b(?:от|from)\b|dan\b", lower):
        return None, val, currency
    return val, val, currency


def extract_contacts(text: str | None) -> dict[str, str | None]:
    """Matndan telefon, Telegram username va email kontaktlarini ajratib oladi."""
    if not text:
        return {"phone": None, "telegram": None, "email": None}

    email_match = re.search(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", text)
    email = email_match.group(0) if email_match else None

    masked = text.replace(email, " ") if email else text
    tg_match = re.search(r"(?<![\w.])@([a-zA-Z0-9_]{4,32})\b", masked)
    telegram = f"@{tg_match.group(1)}" if tg_match else None

    phone_match = re.search(r"(\+?998[\d\s\-()]{7,16})", text)
    phone: str | None = None
    if phone_match:
        digits = re.sub(r"\D", "", phone_match.group(1))
        if len(digits) >= 9:
            phone = f"+{digits}" if digits.startswith("998") else phone_match.group(1).strip()

    return {"phone": phone, "telegram": telegram, "email": email}


def parse_published_at(value: str | datetime | None) -> datetime:
    """ISO-8601 yoki RFC-2822 sana satrini UTC timezone-aware datetime ga aylantiradi."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not value or not isinstance(value, str):
        return datetime.now(UTC)

    raw = value.strip()
    try:
        iso_dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return iso_dt if iso_dt.tzinfo else iso_dt.replace(tzinfo=UTC)
    except ValueError:
        pass

    try:
        rfc_dt = parsedate_to_datetime(raw)
        return rfc_dt if rfc_dt.tzinfo else rfc_dt.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return datetime.now(UTC)
