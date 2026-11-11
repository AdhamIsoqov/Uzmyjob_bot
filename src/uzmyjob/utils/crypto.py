"""Fernet (AES-128-CBC + HMAC-SHA256) orqali matn va fayllarni shifrlash."""
from cryptography.fernet import Fernet

from uzmyjob.config import settings

_fernet: Fernet | None = None
_fernet_key_used: str = ""


def _get_fernet() -> Fernet:
    global _fernet, _fernet_key_used
    key = settings.fernet_key
    if not key:
        raise RuntimeError("FERNET_KEY sozlanmagan. Shifrlash imkonsiz.")

    if _fernet is None or _fernet_key_used != key:
        _fernet = Fernet(key.encode())
        _fernet_key_used = key
    return _fernet


def encrypt(data: bytes) -> bytes:
    """Berilgan bytes ni shifrlaydi."""
    return _get_fernet().encrypt(data)


def decrypt(token: bytes) -> bytes:
    """Shifrlangan bytes ni deshifrlaydi."""
    return _get_fernet().decrypt(token)


def encrypt_str(text: str) -> str:
    """Matnni shifrlab UTF-8 string qaytaradi."""
    return encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_str(token: str) -> str:
    """Shifrlangan stringni asl matnga qaytaradi."""
    return decrypt(token.encode("utf-8")).decode("utf-8")
