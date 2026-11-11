#!/bin/bash
# @Uzmyjob_bot Avtomatik zaxiralash skripti (AES shifrlash va tozalash bilan)
set -euo pipefail

PROJECT_DIR="/opt/uzmyjob"
cd "$PROJECT_DIR"

echo "[$(date -Iseconds)] Zaxira nusxa yaratish boshlandi..."

docker compose -f deploy/vps/docker-compose.prod.yml exec -T bot python -c "
import asyncio
from uzmyjob.utils.backup import create_database_backup
path = asyncio.run(create_database_backup('/app/backups'))
if not path:
    raise SystemExit('Backup yaratishda xatolik yuz berdi')
print(f'Zaxira tayyor: {path}')
"

echo "[$(date -Iseconds)] Zaxira nusxa muvaffaqiyatli saqlandi va 14 kundan eskilar tozalandi."
