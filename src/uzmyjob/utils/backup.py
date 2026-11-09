"""PostgreSQL ma'lumotlar bazasini zaxira qilish (backup), shifrlash va tozalash moduli."""
import asyncio
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from uzmyjob.config import settings
from uzmyjob.utils.crypto import decrypt, encrypt
from uzmyjob.utils.logger import log


def _encrypt_and_save_file(source_file: Path, target_file: Path) -> int:
    """Sinxron fayl o'qish va shifrlash yordamchisi."""
    with open(source_file, "rb") as f_in:
        data = f_in.read()

    encrypted_data = encrypt(data)

    with open(target_file, "wb") as f_out:
        f_out.write(encrypted_data)

    if source_file.exists():
        os.remove(source_file)
    return len(encrypted_data)


def clean_old_backups(output_dir: str = "backups", retention_days: int = 14) -> int:
    """
    Belgilangan muddatdan (masalan 14 kundan) eski backup fayllarni o'chirish.
    Returns: o'chirilgan fayllar soni.
    """
    out_path = Path(output_dir)
    if not out_path.exists():
        return 0

    now = time.time()
    cutoff_seconds = retention_days * 86400
    removed_count = 0

    for file in out_path.glob("*.sql.enc"):
        try:
            mtime = file.stat().st_mtime
            if (now - mtime) > cutoff_seconds:
                file.unlink()
                removed_count += 1
                log.info("old_backup_removed", file=str(file))
        except Exception as e:
            log.warning("clean_backup_failed", file=str(file), error=str(e))

    return removed_count


async def create_database_backup(output_dir: str = "backups") -> str | None:
    """
    PostgreSQL bazasini pg_dump orqali dump qilib, AES-256 (Fernet) bilan shifrlaydi.
    Eski (14 kundan oshgan) zaxira nusxalarini tozalaydi.
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

        size_bytes = await asyncio.to_thread(_encrypt_and_save_file, raw_file, enc_file)
        log.info("backup_completed", encrypted_file=str(enc_file), size_bytes=size_bytes)

        # 14 kundan eski backuplarni tozalash
        await asyncio.to_thread(clean_old_backups, output_dir, 14)

        return str(enc_file)

    except Exception as e:
        log.error("backup_exception", error=str(e))
        return None


def restore_database_backup(enc_file: str, target_sql: str) -> bool:
    """
    Shifrlangan backup faylni deshifrlab, tiklash uchun tayyor holatga keltiradi.
    """
    enc_path = Path(enc_file)
    target_path = Path(target_sql)

    if not enc_path.exists():
        log.error("backup_restore_file_not_found", file=enc_file)
        return False

    try:
        with open(enc_path, "rb") as f_in:
            enc_data = f_in.read()

        raw_sql = decrypt(enc_data)

        with open(target_path, "wb") as f_out:
            f_out.write(raw_sql)

        log.info("backup_decrypted_successfully", target=str(target_path))
        return True
    except Exception as e:
        log.error("backup_decrypt_failed", error=str(e))
        return False
