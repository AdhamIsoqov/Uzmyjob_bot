#!/bin/bash
# @Uzmyjob_bot Avtomatik zaxiralash skripti (AES-256 shifrlash va tozalash bilan)
set -e

PROJECT_DIR="/opt/uzmyjob"
cd "$PROJECT_DIR"

echo "[$(date -Iseconds)] Zaxira nusxa yaratish boshlandi..."

# Docker bot konteyneri ichidagi backup buyrug'ini ishga tushirish
docker exec uzmyjob-bot-prod python -c "
import asyncio
from uzmyjob.utils.backup import create_database_backup
path = asyncio.run(create_database_backup('/app/backups'))
print(f'Zaxira tayyor: {path}')
"

echo "[$(date -Iseconds)] Zaxira nusxa muvaffaqiyatli saqlandi va 14 kundan eskilar tozalandi."

