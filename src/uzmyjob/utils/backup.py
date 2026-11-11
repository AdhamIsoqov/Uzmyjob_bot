"""PostgreSQL ma'lumotlar bazasini zaxira qilish (backup), shifrlash va tozalash moduli."""
import asyncio
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from uzmyjob.config import settings
from uzmyjob.utils.crypto import decrypt, encrypt
from uzmyjob.utils.logger import log


def _encrypt_and_save_file(source_file: Path, target_file: Path) -> int:
    """Sinxron fayl o'qish va shifrlash yordamchisi."""
    data = source_file.read_bytes()
    encrypted_data = encrypt(data)
    target_file.write_bytes(encrypted_data)
    return len(encrypted_data)


def clean_old_backups(output_dir: str = "backups", retention_days: int = 14) -> int:
    """Belgilangan muddatdan eski shifrlangan backup fayllarni o'chirish."""
    out_path = Path(output_dir)
    if not out_path.exists():
        return 0

    now = time.time()
    cutoff_seconds = retention_days * 86400
    removed_count = 0

    for file in out_path.glob("*.sql.enc"):
        try:
            if (now - file.stat().st_mtime) > cutoff_seconds:
                file.unlink()
                removed_count += 1
                log.info("old_backup_removed", file=str(file))
        except OSError as exc:
            log.warning("clean_backup_failed", file=str(file), error=str(exc))

    return removed_count


def _build_pg_dump_args_and_env(postgres_url: str, raw_file: Path) -> tuple[list[str], dict[str, str]]:
    """PostgreSQL URL dan xavfsiz pg_dump argumentlari va PGPASSWORD env yaratish."""
    clean_url = postgres_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed = urlparse(clean_url)

    args = ["pg_dump", "--file", str(raw_file)]
    if parsed.hostname:
        args.extend(["--host", parsed.hostname])
    if parsed.port:
        args.extend(["--port", str(parsed.port)])
    if parsed.username:
        args.extend(["--username", unquote(parsed.username)])
    db_name = parsed.path.lstrip("/")
    if db_name:
        args.extend(["--dbname", db_name])

    env = os.environ.copy()
    if parsed.password:
        env["PGPASSWORD"] = unquote(parsed.password)

    return args, env


async def create_database_backup(output_dir: str = "backups") -> str | None:
    """
    PostgreSQL bazasini pg_dump orqali dump qilib, Fernet bilan shifrlaydi.
    SQLite yoki pg_dump mavjud bo'lmagan muhitlarda xavfsiz ravishda None qaytaradi.
    """
    if settings.postgres_url.startswith("sqlite"):
        log.info("backup_skipped_sqlite_mode")
        return None

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    raw_file = out_path / f"uzmyjob_backup_{timestamp}.sql"
    enc_file = out_path / f"uzmyjob_backup_{timestamp}.sql.enc"

    args, env = _build_pg_dump_args_and_env(settings.postgres_url, raw_file)
    log.info("backup_started", target=str(enc_file))

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            log.error("pg_dump_failed", returncode=proc.returncode, error=stderr.decode(errors="replace")[:300])
            return None

        size_bytes = await asyncio.to_thread(_encrypt_and_save_file, raw_file, enc_file)
        log.info("backup_completed", encrypted_file=str(enc_file), size_bytes=size_bytes)

        await asyncio.to_thread(clean_old_backups, output_dir, 14)
        return str(enc_file)

    except FileNotFoundError:
        log.warning("backup_skipped_pg_dump_not_found")
        return None
    except Exception as exc:
        log.error("backup_exception", error=str(exc))
        return None
    finally:
        raw_file.unlink(missing_ok=True)


def restore_database_backup(enc_file: str, target_sql: str) -> bool:
    """Shifrlangan backup faylni deshifrlab tiklash uchun tayyor holatga keltiradi."""
    enc_path = Path(enc_file)
    target_path = Path(target_sql)

    if not enc_path.exists():
        log.error("backup_restore_file_not_found", file=enc_file)
        return False

    try:
        enc_data = enc_path.read_bytes()
        raw_sql = decrypt(enc_data)
        target_path.write_bytes(raw_sql)
        log.info("backup_decrypted_successfully", target=str(target_path))
        return True
    except Exception as exc:
        log.error("backup_decrypt_failed", error=str(exc))
        return False
