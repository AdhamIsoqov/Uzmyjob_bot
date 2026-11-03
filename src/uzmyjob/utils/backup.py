"""PostgreSQL ma'lumotlar bazasini zaxira qilish (backup) va shifrlash moduli."""
import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

from uzmyjob.config import settings
from uzmyjob.utils.crypto import encrypt
from uzmyjob.utils.logger import log


def _encrypt_and_save_file(source_file: Path, target_file: Path) -> int:
    """Sinxron fayl o'qish va shifrlash yordamchisi."""
    with open(source_file, "rb") as f_in:
        data = f_in.read()

    encrypted_data = encrypt(data)

    with open(target_file, "wb") as f_out:
        f_out.write(encrypted_data)

    os.remove(source_file)
    return len(encrypted_data)


async def create_database_backup(output_dir: str = "backups") -> str | None:
    """
    PostgreSQL bazasini pg_dump orqali dump qilib, AES-256 (Fernet) bilan shifrlaydi.
    Returns: yaratilgan shifrlangan backup fayl yo'li.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    raw_file = out_path / f"uzmyjob_backup_{timestamp}.sql"
    enc_file = out_path / f"uzmyjob_backup_{timestamp}.sql.enc"

    db_url = settings.postgres_url.replace("postgresql+asyncpg://", "postgresql://")
    cmd = f"pg_dump {db_url} -f {raw_file}"
    log.info("backup_started", file=str(raw_file))

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            log.error("pg_dump_failed", error=stderr.decode())
            return None

        # Sinxron fayl amallarini to_thread orqali xavfsiz bajarish
        size_bytes = await asyncio.to_thread(_encrypt_and_save_file, raw_file, enc_file)

        log.info("backup_completed", encrypted_file=str(enc_file), size_bytes=size_bytes)
        return str(enc_file)

    except Exception as e:
        log.error("backup_exception", error=str(e))
        return None
