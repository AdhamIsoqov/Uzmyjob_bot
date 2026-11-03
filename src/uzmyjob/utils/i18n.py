"""Ko'p tilli (i18n) qo'llab-quvvatlash moduli (uz, ru, en)."""
from typing import Any

# Lug'atlar: uz, ru, en
TRANSLATIONS: dict[str, dict[str, str]] = {
    "uz": {
        "welcome": "👋 <b>@Uzmyjob_bot</b>ga xush kelibsiz!\n\nBu bot sizga O'zbekiston ish bozoridan vakansiyalarni topib, murojaat qilishga yordam beradi.\n\nBoshlash uchun /wizard yoki /profil buyrug'ini yuboring.",
        "profil_intro": "🎯 <b>Profil sozlash bosqichiga xush kelibsiz!</b>\n\n1-qadam: Qaysi <b>lavozim yoki mutaxassislik</b> bo'yicha ish qidiryapsiz?",
        "city_step": "📍 2-qadam: Qaysi <b>shahar yoki format</b> ma'qul? (Masalan: Toshkent yoki Remote)",
        "exp_step": "⏳ 3-qadam: Necha yillik <b>ish tajribasiga</b> egasiz? (Faqat son yozing, masalan: 2)",
        "salary_step": "💰 4-qadam: Kutilayotgan <b>minimal maosh</b> qancha? (Masalan: 1000)",
        "skills_step": "🔑 5-qadam: Vakansiyalarda qidiriladigan <b>kalit so'zlar / texnologiyalarni</b> vergul bilan ajrating:",
        "blacklist_step": "🚫 6-qadam: <b>Qora ro'yxat (Blacklist)</b> — qaysi so'zlar bor vakansiyalarni ko'rsatmaylik?",
        "cv_step": "📄 7-qadam: <b>Rezyumeingizni (CV) hujjat ko'rinishida yuboring</b> (PDF yoki DOCX). Yoki /skip deb yozing.",
        "cv_saved": "✅ <b>Profil va Rezyume muvaffaqiyatli saqlandi!</b>",
        "bot_stopped": "⏸ Bot to'xtatildi. Qayta boshlash uchun: /start",
        "account_deleted": "🗑 <b>Hisobingiz va barcha shaxsiy ma'lumotlaringiz o'chirildi.</b>",
        "btn_apply": "✅ Murojaat qilish",
        "btn_cover": "✉️ Xabar tayyorlash",
        "btn_save": "🔖 Saqlash",
        "btn_dismiss": "❌ Rad etish",
    },
    "ru": {
        "welcome": "👋 Добро пожаловать в <b>@Uzmyjob_bot</b>!\n\nБот помогает находить лучшие вакансии в Узбекистане и откликаться в один клик.\n\nДля начала отправьте /wizard или /profil.",
        "profil_intro": "🎯 <b>Настройка профиля:</b>\n\nШаг 1: На какую <b>должность или специальность</b> вы ищете работу?",
        "city_step": "📍 Шаг 2: Какой <b>город или формат</b> вам подходит? (Например: Ташкент или Удаленно)",
        "exp_step": "⏳ Шаг 3: Сколько у вас лет <b>опыта работы</b>? (Например: 2)",
        "salary_step": "💰 Шаг 4: Какой <b>минимальный уровень зарплаты</b> вы ожидаете? (Например: 1000)",
        "skills_step": "🔑 Шаг 5: Перечислите <b>ключевые навыки и технологии</b> через запятую:",
        "blacklist_step": "🚫 Шаг 6: <b>Черный список (Blacklist)</b> — слова, при наличии которых скрывать вакансию:",
        "cv_step": "📄 Шаг 7: Отправьте <b>ваше резюме (CV) документом</b> (PDF или DOCX). Или отправьте /skip.",
        "cv_saved": "✅ <b>Профиль и резюме успешно сохранены!</b>",
        "bot_stopped": "⏸ Бот приостановлен. Для возобновления отправьте: /start",
        "account_deleted": "🗑 <b>Ваш аккаунт и все персональные данные удалены.</b>",
        "btn_apply": "✅ Откликнуться",
        "btn_cover": "✉️ Подготовить письмо",
        "btn_save": "🔖 Сохранить",
        "btn_dismiss": "❌ Скрыть",
    },
    "en": {
        "welcome": "👋 Welcome to <b>@Uzmyjob_bot</b>!\n\nFind and apply to the best tech jobs in Uzbekistan directly from Telegram.\n\nSend /wizard or /profil to get started.",
        "profil_intro": "🎯 <b>Profile Setup:</b>\n\nStep 1: What <b>position or role</b> are you looking for?",
        "city_step": "📍 Step 2: Preferred <b>city or work format</b>? (e.g. Tashkent or Remote)",
        "exp_step": "⏳ Step 3: How many years of <b>work experience</b> do you have? (e.g. 2)",
        "salary_step": "💰 Step 4: What is your <b>minimum expected salary</b>? (e.g. 1000)",
        "skills_step": "🔑 Step 5: List your <b>key skills and technologies</b> separated by commas:",
        "blacklist_step": "🚫 Step 6: <b>Blacklist</b> — keywords to exclude vacancies:",
        "cv_step": "📄 Step 7: Send your <b>resume (CV) as a document</b> (PDF or DOCX). Or type /skip.",
        "cv_saved": "✅ <b>Profile and resume successfully saved!</b>",
        "bot_stopped": "⏸ Bot paused. To resume send: /start",
        "account_deleted": "🗑 <b>Your account and personal data have been completely deleted.</b>",
        "btn_apply": "✅ Apply",
        "btn_cover": "✉️ Cover Letter",
        "btn_save": "🔖 Bookmark",
        "btn_dismiss": "❌ Dismiss",
    },
}


def t(key: str, lang: str = "uz", **kwargs: Any) -> str:
    """
    Belgilangan tilda tarjimani qaytaradi.
    Fallback zanjiri: berilgan til -> uz -> en -> key
    """
    selected_lang = lang if lang in TRANSLATIONS else "uz"
    text = TRANSLATIONS[selected_lang].get(key)

    if not text:
        text = TRANSLATIONS["en"].get(key, key)

    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text

    return text
