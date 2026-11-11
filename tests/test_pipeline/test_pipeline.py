"""Unit tests for JobPipeline."""
from uzmyjob.pipeline.pipeline import JobPipeline, build_vacancy_keyboard


def test_build_vacancy_keyboard():
    """Inline tugmalar to'g'ri yaratilishi kerak."""
    kb = build_vacancy_keyboard(42)
    buttons = [b for row in kb.inline_keyboard for b in row]
    callbacks = [b.callback_data for b in buttons]

    assert "apply:42" in callbacks
    assert "cover:42" in callbacks
    assert "save:42" in callbacks
    assert "dismiss:42" in callbacks


def test_blacklist_filter():
    """Taqiqlangan so'zlar bor bo'lsa True qaytarishi kerak."""
    pipeline = JobPipeline()
    blacklist = ["стажировка", "piramida", "investitsiya"]

    # Taqiqlangan so'z title da
    assert pipeline._is_blacklisted("Python стажировка", "Tavsif", blacklist) is True

    # Taqiqlangan so'z description da
    assert pipeline._is_blacklisted("Junior Dev", "Bizda yangi piramida loyihasi", blacklist) is True

    # Mos va toza vakansiya
    assert pipeline._is_blacklisted("Python Backend Lead", "FastAPI va PostgreSQL", blacklist) is False

