"""AES-256 (Fernet) orqali matn/fayl shifrlash."""
from cryptography.fernet import Fernet

from uzmyjob.config import settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(settings.fernet_key.encode())
    return _fernet


def encrypt(data: bytes) -> bytes:
    """Berilgan bytes ni shifrlaydi."""
    return _get_fernet().encrypt(data)


def decrypt(token: bytes) -> bytes:
    """Shifrlangan bytes ni qaytaradi."""
    return _get_fernet().decrypt(token)


def encrypt_str(text: str) -> str:
    return encrypt(text.encode()).decode()


def decrypt_str(token: str) -> str:
    return decrypt(token.encode()).decode()
