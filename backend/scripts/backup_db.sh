#!/bin/sh
# Daily encrypted DB backup (NFR). Cron on the staging host:
#   0 2 * * * /srv/fawtara/backend/scripts/backup_db.sh
# Requires: BACKUP_PASSPHRASE in the environment; keeps 30 days locally.
set -eu
STAMP=$(date +%Y%m%d-%H%M%S)
DIR=${BACKUP_DIR:-/var/backups/fawtara}
mkdir -p "$DIR"
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U fawtara -d fawtara --format=custom \
  | gpg --batch --symmetric --passphrase "${BACKUP_PASSPHRASE:?}" \
  > "$DIR/fawtara-$STAMP.dump.gpg"
find "$DIR" -name 'fawtara-*.dump.gpg' -mtime +30 -delete
echo "backup written: $DIR/fawtara-$STAMP.dump.gpg"
