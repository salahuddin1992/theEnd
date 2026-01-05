# Upgrade Guide

Guide to upgrading NebulaCompute to newer versions.

## Table of Contents

- [Upgrade Strategy](#upgrade-strategy)
- [Pre-Upgrade Checklist](#pre-upgrade-checklist)
- [Upgrade Procedures](#upgrade-procedures)
- [Version-Specific Notes](#version-specific-notes)
- [Rollback Procedures](#rollback-procedures)
- [Post-Upgrade Verification](#post-upgrade-verification)

## Upgrade Strategy

### Version Numbering

NebulaCompute follows Semantic Versioning (SemVer):

```
MAJOR.MINOR.PATCH (e.g., 1.2.3)
  │     │     │
  │     │     └── Bug fixes (backward compatible)
  │     └──────── New features (backward compatible)
  └────────────── Breaking changes
```

### Upgrade Paths

| From | To | Type | Downtime |
|------|-----|------|----------|
| 0.1.x | 0.1.y | Patch | None/Minimal |
| 0.x.y | 0.z.0 | Minor | Minutes |
| 0.x.y | 1.0.0 | Major | Planned |

### Upgrade Methods

1. **Rolling Upgrade**: Zero-downtime, upgrade workers then master
2. **Blue-Green**: Parallel deployment, instant switchover
3. **Maintenance Window**: Stop cluster, upgrade, restart

## Pre-Upgrade Checklist

### Before Every Upgrade

- [ ] Read release notes for target version
- [ ] Review breaking changes and deprecations
- [ ] Backup database (see [Backup Guide](BACKUP_RESTORE.md))
- [ ] Backup configuration files
- [ ] Test upgrade in staging environment
- [ ] Verify sufficient disk space
- [ ] Schedule maintenance window (if needed)
- [ ] Notify users of planned downtime

### Verification Commands

```bash
# Check current version
nebula --version

# Check cluster status
nebula status

# Verify backup is recent
ls -la backups/

# Check disk space
df -h

# Review pending jobs
nebula job list --status pending
```

## Upgrade Procedures

### pip Upgrade

```bash
# Upgrade package
pip install --upgrade distributed-cluster

# Verify new version
nebula --version

# Run database migrations
nebula db migrate

# Restart services
systemctl restart nebula-master
systemctl restart nebula-worker
```

### Docker Upgrade

```bash
# Pull new image
docker pull ghcr.io/salahuddin1992/theend:latest

# Stop current containers
docker-compose down

# Update docker-compose.yml with new version
sed -i 's/theend:.*/theend:1.0.0/' docker-compose.yml

# Start with new version
docker-compose up -d

# Verify
docker-compose ps
```

### Kubernetes Upgrade

```bash
# Update image in deployment
kubectl set image deployment/nebula-master \
  master=ghcr.io/salahuddin1992/theend:1.0.0

kubectl set image deployment/nebula-worker \
  worker=ghcr.io/salahuddin1992/theend:1.0.0

# Or with Helm
helm upgrade nebula ./deploy/helm/distributed-cluster \
  --set image.tag=1.0.0

# Verify rollout
kubectl rollout status deployment/nebula-master
kubectl rollout status deployment/nebula-worker
```

### Rolling Upgrade (Zero Downtime)

```bash
# 1. Upgrade workers first (one at a time)
for worker in $(kubectl get pods -l app=nebula-worker -o name); do
  kubectl delete $worker
  sleep 30  # Wait for replacement
done

# 2. Verify workers are healthy
nebula worker list

# 3. Upgrade master
kubectl rollout restart deployment/nebula-master

# 4. Verify cluster health
nebula health
```

### Blue-Green Deployment

```bash
# 1. Deploy green environment
kubectl apply -f deploy/green/

# 2. Run smoke tests against green
curl http://green-master:8000/health

# 3. Switch traffic to green
kubectl patch service nebula \
  -p '{"spec":{"selector":{"version":"green"}}}'

# 4. Verify
nebula health

# 5. Remove blue environment (after verification)
kubectl delete -f deploy/blue/
```

## Version-Specific Notes

### Upgrading to 0.1.x

No special steps required for patch releases.

```bash
pip install --upgrade distributed-cluster
nebula db migrate  # If needed
```

### Upgrading to 0.2.0 (Future)

**Breaking Changes:**
- Configuration file format changes
- API endpoint changes

**Migration Steps:**

```bash
# 1. Backup current config
cp config.yaml config.yaml.bak

# 2. Run config migration
nebula config migrate --from 0.1 --to 0.2

# 3. Review migrated config
diff config.yaml config.yaml.bak

# 4. Upgrade
pip install --upgrade distributed-cluster

# 5. Run database migrations
nebula db migrate

# 6. Restart services
systemctl restart nebula-master
```

### Upgrading to 1.0.0 (Future)

**Major Changes:**
- New authentication system
- Database schema changes
- API v2

**Migration Steps:**

```bash
# 1. Full backup
nebula db backup --output backups/pre-1.0/

# 2. Stop cluster
nebula master stop
nebula worker stop --all

# 3. Upgrade
pip install --upgrade distributed-cluster==1.0.0

# 4. Run migrations
nebula db migrate --to 1.0

# 5. Migrate authentication
nebula auth migrate --from-legacy

# 6. Update config
nebula config migrate --to 1.0

# 7. Start cluster
nebula master start
```

## Rollback Procedures

### Quick Rollback (pip)

```bash
# Rollback to previous version
pip install distributed-cluster==0.1.0

# Restore database if needed
nebula db restore --from backups/pre-upgrade.dump

# Restart services
systemctl restart nebula-master
systemctl restart nebula-worker
```

### Docker Rollback

```bash
# Revert to previous image
docker-compose down
sed -i 's/theend:1.0.0/theend:0.1.0/' docker-compose.yml
docker-compose up -d
```

### Kubernetes Rollback

```bash
# Rollback to previous revision
kubectl rollout undo deployment/nebula-master
kubectl rollout undo deployment/nebula-worker

# Or rollback to specific revision
kubectl rollout undo deployment/nebula-master --to-revision=2

# With Helm
helm rollback nebula 1  # Rollback to revision 1
```

### Database Rollback

```bash
# Restore from backup
nebula db restore --from backups/pre-upgrade-20240115.dump

# Or for PostgreSQL
pg_restore -h postgres -U nebula -d nebulacompute \
  --clean backups/pre-upgrade.dump
```

## Post-Upgrade Verification

### Health Checks

```bash
# Check master health
curl http://localhost:8000/health

# Check cluster status
nebula status

# Verify workers
nebula worker list
```

### Functional Tests

```bash
# Submit test job
JOB_ID=$(nebula job submit "echo 'upgrade test'" --quiet)

# Wait for completion
nebula job wait $JOB_ID

# Verify result
nebula job status $JOB_ID
```

### Performance Verification

```bash
# Run quick benchmark
nebula benchmark --quick

# Compare with baseline
nebula benchmark --compare pre-upgrade-baseline.json
```

### Monitoring Verification

```bash
# Check metrics are being collected
curl http://localhost:8000/metrics | head

# Verify Grafana dashboards
# Open http://grafana:3000 and check dashboards

# Check for errors in logs
nebula logs --level ERROR --since 1h
```

### Checklist

- [ ] All services running
- [ ] Workers connected
- [ ] Jobs scheduling correctly
- [ ] API responding
- [ ] Metrics collecting
- [ ] No errors in logs
- [ ] Dashboard accessible
- [ ] Authentication working

## Troubleshooting Upgrades

### Common Issues

**Database migration failed:**
```bash
# Check migration status
nebula db status

# Run specific migration
nebula db migrate --step 1

# Reset and retry
nebula db migrate --reset
```

**Workers not connecting:**
```bash
# Check version compatibility
nebula worker version

# Restart workers with new version
nebula worker restart --all
```

**Configuration errors:**
```bash
# Validate config
nebula config validate

# Show differences
nebula config diff --from 0.1 --to 0.2
```

## See Also

- [Changelog](CHANGELOG.md)
- [Backup and Restore](BACKUP_RESTORE.md)
- [Troubleshooting](TROUBLESHOOTING.md)
