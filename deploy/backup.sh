#!/bin/sh
# Dumps the database to deploy/backups/librete-<timestamp>.sql.gz and keeps 14 days.
# Run from cron, e.g.: 30 3 * * * /opt/librete/librete-api/deploy/backup.sh
set -eu
cd "$(dirname "$0")"
mkdir -p backups
docker compose exec -T db pg_dump -U librete librete | gzip > "backups/librete-$(date +%Y%m%d-%H%M%S).sql.gz"
find backups -name 'librete-*.sql.gz' -mtime +14 -delete
