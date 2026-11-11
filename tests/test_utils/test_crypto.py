"""Crypto util uchun unit test."""
from unittest.mock import patch

from cryptography.fernet import Fernet


def test_encrypt_decrypt_roundtrip():
    """Shifrlash va qayta ochish to'g'ri ishlashi kerak."""
    test_key = Fernet.generate_key().decode()

    with patch("uzmyjob.utils.crypto.settings") as mock_settings:
        mock_settings.fernet_key = test_key

        # _fernet ni reset qilamiz
        import uzmyjob.utils.crypto as crypto_module
        crypto_module._fernet = None

        from uzmyjob.utils.crypto import decrypt_str, encrypt_str

        original = "Bu maxfiy ma'lumot"
        encrypted = encrypt_str(original)
        decrypted = decrypt_str(encrypted)

        assert decrypted == original
        assert encrypted != original
