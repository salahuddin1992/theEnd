# Backup and Restore Guide

Guide to backing up and restoring NebulaCompute data.

## Table of Contents

- [Backup Strategy](#backup-strategy)
- [Database Backup](#database-backup)
- [Configuration Backup](#configuration-backup)
- [Artifact Backup](#artifact-backup)
- [Disaster Recovery](#disaster-recovery)
- [Automated Backups](#automated-backups)

## Backup Strategy

### What to Backup

| Component | Priority | Frequency | Retention |
|-----------|----------|-----------|-----------|
| Database | Critical | Hourly | 30 days |
| Configuration | High | On change | 90 days |
| Job Artifacts | Medium | Daily | 7 days |
| Logs | Low | Daily | 7 days |
| Metrics | Low | N/A | Use retention policies |

### Backup Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Production                        │
├─────────────────────────────────────────────────────┤
│  Database │ Config │ Artifacts │ Logs              │
└─────┬─────┴────┬───┴─────┬─────┴────┬──────────────┘
      │          │         │          │
      ▼          ▼         ▼          ▼
┌─────────────────────────────────────────────────────┐
│                   Backup Storage                    │
├─────────────────────────────────────────────────────┤
│  S3/MinIO  │  Git  │  S3/NFS  │  S3/Glacier        │
└─────────────────────────────────────────────────────┘
```

## Database Backup

### SQLite Backup

```bash
# Simple file copy (while cluster is stopped)
cp data/cluster.db backups/cluster-$(date +%Y%m%d_%H%M%S).db

# Online backup using SQLite CLI
sqlite3 data/cluster.db ".backup backups/cluster-$(date +%Y%m%d).db"

# Using nebula CLI
nebula db backup --output backups/
```

### PostgreSQL Backup

```bash
# Full backup with pg_dump
pg_dump -h postgres -U nebula -d nebulacompute \
  -F c -f backups/nebulacompute-$(date +%Y%m%d_%H%M%S).dump

# Schema only
pg_dump -h postgres -U nebula -d nebulacompute \
  --schema-only -f backups/schema-$(date +%Y%m%d).sql

# Data only
pg_dump -h postgres -U nebula -d nebulacompute \
  --data-only -f backups/data-$(date +%Y%m%d).sql

# Compressed backup
pg_dump -h postgres -U nebula -d nebulacompute \
  -F c -Z 9 -f backups/nebulacompute-$(date +%Y%m%d).dump.gz
```

### Continuous Archiving (PostgreSQL)

```bash
# Enable WAL archiving in postgresql.conf
archive_mode = on
archive_command = 'cp %p /backup/wal/%f'

# Base backup
pg_basebackup -h postgres -U replication -D /backup/base \
  -Ft -z -P --wal-method=stream
```

## Configuration Backup

### Manual Backup

```bash
# Backup config files
tar -czvf backups/config-$(date +%Y%m%d).tar.gz \
  config.yaml \
  .env \
  deploy/

# Backup secrets (encrypted)
gpg --symmetric --cipher-algo AES256 \
  -o backups/secrets-$(date +%Y%m%d).gpg \
  secrets.yaml
```

### Git-based Backup

```bash
# Initialize config repo
cd /etc/nebulacompute
git init
git add config.yaml deploy/

# Commit changes
git commit -m "Config backup $(date +%Y%m%d)"

# Push to backup repo
git remote add backup git@backup-server:nebulacompute-config.git
git push backup main
```

## Artifact Backup

### Local Backup

```bash
# Backup job artifacts
rsync -avz --delete \
  /var/nebula/artifacts/ \
  /backup/artifacts/

# With compression
tar -czvf backups/artifacts-$(date +%Y%m%d).tar.gz \
  /var/nebula/artifacts/
```

### S3 Backup

```bash
# Sync to S3
aws s3 sync /var/nebula/artifacts/ \
  s3://nebula-backups/artifacts/ \
  --storage-class STANDARD_IA

# With lifecycle policy
aws s3api put-bucket-lifecycle-configuration \
  --bucket nebula-backups \
  --lifecycle-configuration '{
    "Rules": [{
      "ID": "ArtifactRetention",
      "Status": "Enabled",
      "Filter": {"Prefix": "artifacts/"},
      "Expiration": {"Days": 30},
      "Transitions": [{
        "Days": 7,
        "StorageClass": "GLACIER"
      }]
    }]
  }'
```

## Disaster Recovery

### Full Restore (SQLite)

```bash
# Stop the cluster
nebula master stop

# Restore database
cp backups/cluster-20240115.db data/cluster.db

# Restore config
tar -xzvf backups/config-20240115.tar.gz -C /

# Start the cluster
nebula master start
```

### Full Restore (PostgreSQL)

```bash
# Stop the cluster
nebula master stop

# Drop and recreate database
psql -h postgres -U postgres -c "DROP DATABASE nebulacompute;"
psql -h postgres -U postgres -c "CREATE DATABASE nebulacompute OWNER nebula;"

# Restore from dump
pg_restore -h postgres -U nebula -d nebulacompute \
  backups/nebulacompute-20240115.dump

# Start the cluster
nebula master start
```

### Point-in-Time Recovery (PostgreSQL)

```bash
# Stop PostgreSQL
systemctl stop postgresql

# Restore base backup
rm -rf /var/lib/postgresql/data/*
tar -xzf /backup/base/base.tar.gz -C /var/lib/postgresql/data/

# Create recovery.conf
cat > /var/lib/postgresql/data/recovery.conf << EOF
restore_command = 'cp /backup/wal/%f %p'
recovery_target_time = '2024-01-15 14:30:00'
EOF

# Start PostgreSQL
systemctl start postgresql
```

### Partial Restore

```bash
# Restore specific jobs
nebula db restore --jobs-only --from backups/nebulacompute-20240115.dump

# Restore specific time range
nebula db restore \
  --from backups/nebulacompute-20240115.dump \
  --after "2024-01-15 00:00:00" \
  --before "2024-01-15 12:00:00"
```

## Automated Backups

### Cron Jobs

```bash
# /etc/cron.d/nebula-backup
# Daily full backup at 2 AM
0 2 * * * nebula /usr/local/bin/nebula-backup.sh full

# Hourly incremental backup
0 * * * * nebula /usr/local/bin/nebula-backup.sh incremental

# Weekly cleanup
0 3 * * 0 nebula /usr/local/bin/nebula-backup.sh cleanup
```

### Backup Script

```bash
#!/bin/bash
# /usr/local/bin/nebula-backup.sh

set -e

BACKUP_DIR="/backup/nebula"
S3_BUCKET="s3://nebula-backups"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)

case "$1" in
  full)
    # Database backup
    pg_dump -h postgres -U nebula -d nebulacompute \
      -F c -Z 9 -f "$BACKUP_DIR/db-$DATE.dump.gz"

    # Config backup
    tar -czvf "$BACKUP_DIR/config-$DATE.tar.gz" \
      /etc/nebulacompute/

    # Upload to S3
    aws s3 cp "$BACKUP_DIR/db-$DATE.dump.gz" "$S3_BUCKET/daily/"
    aws s3 cp "$BACKUP_DIR/config-$DATE.tar.gz" "$S3_BUCKET/daily/"

    echo "Full backup completed: $DATE"
    ;;

  incremental)
    # WAL backup
    aws s3 sync /backup/wal/ "$S3_BUCKET/wal/"
    echo "Incremental backup completed: $DATE"
    ;;

  cleanup)
    # Remove old local backups
    find "$BACKUP_DIR" -type f -mtime +$RETENTION_DAYS -delete

    # Remove old S3 backups (handled by lifecycle policy)
    echo "Cleanup completed"
    ;;

  *)
    echo "Usage: $0 {full|incremental|cleanup}"
    exit 1
    ;;
esac
```

### Kubernetes CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: nebula-backup
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: backup
              image: nebulacompute:latest
              command:
                - /bin/sh
                - -c
                - |
                  pg_dump -h postgres -U nebula -d nebulacompute \
                    -F c -Z 9 | aws s3 cp - s3://nebula-backups/daily/db-$(date +%Y%m%d).dump.gz
              env:
                - name: PGPASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: nebula-secrets
                      key: db-password
          restartPolicy: OnFailure
```

### Backup Monitoring

```yaml
# Prometheus alert for backup failures
groups:
  - name: backup
    rules:
      - alert: BackupFailed
        expr: nebula_backup_last_success_timestamp < (time() - 86400)
        for: 1h
        labels:
          severity: critical
        annotations:
          summary: "Backup has not succeeded in 24 hours"
```

## Backup Verification

### Automated Verification

```bash
#!/bin/bash
# verify-backup.sh

BACKUP_FILE=$1

# Create test database
createdb -h localhost -U postgres nebula_test

# Restore backup
pg_restore -h localhost -U postgres -d nebula_test "$BACKUP_FILE"

# Run verification queries
psql -h localhost -U postgres -d nebula_test -c "
  SELECT
    (SELECT COUNT(*) FROM jobs) as jobs,
    (SELECT COUNT(*) FROM workers) as workers;
"

# Cleanup
dropdb -h localhost -U postgres nebula_test

echo "Backup verification completed successfully"
```

### Restore Testing Schedule

| Test Type | Frequency | Description |
|-----------|-----------|-------------|
| Integrity check | Daily | Verify backup file integrity |
| Partial restore | Weekly | Restore to test database |
| Full DR test | Monthly | Complete disaster recovery drill |

## See Also

- [Configuration Guide](CONFIGURATION.md)
- [Production Deployment](PRODUCTION_DEPLOYMENT.md)
- [Troubleshooting](TROUBLESHOOTING.md)
