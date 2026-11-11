"""Umumiy matn filtrlash va xavfsizlik yordamchilari."""
import re

CANDIDATE_MARKERS: tuple[str, ...] = (
    "ish joyi kerak",
    "ish qidiryapman",
    "ish qidirmoqdaman",
    "ish qidirayapman",
    "shogird kerak",
    "ustoz kerak",
    "sherik kerak",
    "rezyume",
    "резюме",
    "ищу работу",
    "ищу заказ",
    "ищу стажировку",
    "#ishjoyikerak",
    "#shogird",
    "#ustoz",
    "#sherik",
    "burger king",
    "добро пожаловать в канал",
    "bo'sh ish o'rinlarini ochish",
)


def is_candidate_resume(title: str | None, description: str | None) -> bool:
    """Nomzod rezyumesi yoki noprofil e'lonlarni aniqlash."""
    full = f"{title or ''} {description or ''}".lower()
    if any(marker in full for marker in CANDIDATE_MARKERS):
        return True
    return bool(re.search(r"\bxodim:\s*[a-zа-яa-z]", full) or "kasbi:" in full)


def is_blacklisted(title: str | None, description: str | None, blacklist: list[str]) -> bool:
    """Sarlavha yoki tavsifda taqiqlangan so'zlar borligini tekshiradi."""
    text = f"{title or ''} {description or ''}".lower()
    return any(word and word.strip().lower() in text for word in blacklist)
