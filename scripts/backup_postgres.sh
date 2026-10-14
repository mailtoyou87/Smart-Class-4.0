#!/usr/bin/env bash
set -euo pipefail
: "${DATABASE_URL:?Set DATABASE_URL to a PostgreSQL connection string}"
mkdir -p backups
file="backups/smart_class_$(date -u +%Y%m%dT%H%M%SZ).dump"
pg_dump --format=custom --no-owner --no-acl --file "$file" "$DATABASE_URL"
chmod 600 "$file"
echo "Backup created: $file"
echo "Store encrypted off-server, restrict access, and regularly test restore."
