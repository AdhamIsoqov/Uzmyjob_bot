"""Unit tests for i18n utility."""
from uzmyjob.utils.i18n import t


def test_i18n_translation_keys():
    """Barcha tillarda asosiy kalitlar mavjudligi."""
    assert "xush kelibsiz" in t("welcome", lang="uz")
    assert "Добро пожаловать" in t("welcome", lang="ru")
    assert "Welcome" in t("welcome", lang="en")

    for lang in ["uz", "ru", "en"]:
        assert len(t("profil_intro", lang=lang)) > 5
        assert len(t("btn_apply", lang=lang)) > 3


def test_i18n_fallback():
    """Noma'lum til yoki kalit bo'lganda to'g'ri fallback ishlashi."""
    # Mavjud bo'lmagan tilda default 'uz' ga qaytadi
    res = t("welcome", lang="unknown_lang")
    assert "xush kelibsiz" in res

    # Noma'lum kalit bo'lsa kalitning o'zi qaytadi
    assert t("non_existent_key_xyz", lang="uz") == "non_existent_key_xyz"
