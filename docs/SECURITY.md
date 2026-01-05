# Security Guide

Comprehensive security guide for NebulaCompute deployments.

## Table of Contents

- [Security Overview](#security-overview)
- [Authentication](#authentication)
- [Authorization](#authorization)
- [TLS/SSL Configuration](#tlsssl-configuration)
- [Network Security](#network-security)
- [Job Isolation](#job-isolation)
- [Secrets Management](#secrets-management)
- [Security Best Practices](#security-best-practices)
- [Security Checklist](#security-checklist)

## Security Overview

NebulaCompute implements defense-in-depth with multiple security layers:

```
┌──────────────────────────────────────────────┐
│                 TLS/SSL                       │
│  ┌────────────────────────────────────────┐  │
│  │           Authentication               │  │
│  │  ┌──────────────────────────────────┐  │  │
│  │  │        Authorization             │  │  │
│  │  │  ┌────────────────────────────┐  │  │  │
│  │  │  │     Job Isolation          │  │  │  │
│  │  │  └────────────────────────────┘  │  │  │
│  │  └──────────────────────────────────┘  │  │
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
```

## Authentication

### JWT Token Authentication

NebulaCompute uses JWT (JSON Web Tokens) for authentication:

```yaml
security:
  enabled: true
  secret_key: "${JWT_SECRET}"  # Minimum 32 characters
  algorithm: "HS256"
  token_expiry_hours: 24
```

### Creating API Keys

```bash
# Create admin API key
nebula auth create-key --name "admin-key" --role admin

# Create user API key
nebula auth create-key --name "user-key" --role user --expires 30d

# List API keys
nebula auth list-keys

# Revoke key
nebula auth revoke-key <key-id>
```

### Using API Keys

```bash
# With CLI
export NEBULA_API_KEY="your-api-key"
nebula job submit "echo test"

# With curl
curl -H "Authorization: Bearer your-api-key" \
  http://localhost:8000/api/v1/jobs
```

### Worker Authentication

Workers authenticate using enrollment tokens:

```bash
# Generate enrollment token
nebula auth create-enrollment-token

# Start worker with token
nebula worker start --master http://master:8000 \
  --enrollment-token "token-abc123"
```

### Enrollment Modes

```yaml
security:
  enrollment_mode: "manual"  # Options: auto_approve, manual, disabled
```

| Mode | Description |
|------|-------------|
| `auto_approve` | Workers automatically approved |
| `manual` | Admin must approve each worker |
| `disabled` | No new workers can join |

## Authorization

### Role-Based Access Control (RBAC)

```yaml
authorization:
  enabled: true
  default_role: "user"

  roles:
    admin:
      permissions:
        - "*"
    operator:
      permissions:
        - "jobs:*"
        - "workers:read"
        - "workers:drain"
        - "metrics:read"
    user:
      permissions:
        - "jobs:create"
        - "jobs:read:own"
        - "jobs:cancel:own"
```

### Permission Syntax

```
resource:action[:scope]

Examples:
- jobs:*           # All job actions
- jobs:read        # Read all jobs
- jobs:read:own    # Read own jobs only
- workers:drain    # Drain workers
- admin:*          # All admin actions
```

### Managing Roles

```bash
# Create user with role
nebula user create --username alice --role user

# Update user role
nebula user update alice --role operator

# List users
nebula user list

# View permissions
nebula auth permissions --user alice
```

## TLS/SSL Configuration

### Generating Certificates

```bash
# Generate CA
openssl genrsa -out ca.key 4096
openssl req -new -x509 -days 3650 -key ca.key -out ca.crt \
  -subj "/CN=NebulaCompute CA"

# Generate server certificate
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr \
  -subj "/CN=master.nebula.local"
openssl x509 -req -days 365 -in server.csr -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out server.crt
```

### Enabling TLS

```yaml
tls:
  enabled: true
  cert_file: "/etc/nebula/tls/server.crt"
  key_file: "/etc/nebula/tls/server.key"
  ca_file: "/etc/nebula/tls/ca.crt"
  min_version: "TLSv1.2"
```

### Mutual TLS (mTLS)

```yaml
tls:
  enabled: true
  verify_client: true
  client_ca_file: "/etc/nebula/tls/client-ca.crt"
```

### Worker TLS Configuration

```yaml
worker:
  master_url: "https://master:8000"
  tls:
    ca_file: "/etc/nebula/tls/ca.crt"
    cert_file: "/etc/nebula/tls/worker.crt"
    key_file: "/etc/nebula/tls/worker.key"
```

## Network Security

### Firewall Rules

Master node:
```bash
# Allow API access
ufw allow 8000/tcp

# Allow worker connections
ufw allow 8001/tcp

# Allow metrics (internal only)
ufw allow from 10.0.0.0/8 to any port 9090

# Deny all other
ufw default deny incoming
```

Worker node:
```bash
# Allow master connection
ufw allow out 8000/tcp

# Allow health checks
ufw allow from 10.0.0.0/8 to any port 8081

# Deny incoming
ufw default deny incoming
```

### Network Policies (Kubernetes)

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: nebula-master
spec:
  podSelector:
    matchLabels:
      app: nebula-master
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: nebula-worker
      ports:
        - port: 8000
    - from:
        - namespaceSelector:
            matchLabels:
              name: ingress
      ports:
        - port: 8000
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: postgres
      ports:
        - port: 5432
```

## Job Isolation

### Container Isolation

```yaml
docker:
  # Run as non-root
  user: "1000:1000"

  # Disable privileged mode
  privileged: false

  # Drop capabilities
  cap_drop:
    - ALL
  cap_add:
    - NET_BIND_SERVICE

  # Read-only filesystem
  read_only: true

  # Limit resources
  memory_limit: "4g"
  cpu_limit: "2"

  # No network access (if not needed)
  network_mode: "none"
```

### Seccomp Profiles

```yaml
docker:
  security_opt:
    - "seccomp=/etc/nebula/seccomp/default.json"
```

### AppArmor Profiles

```yaml
docker:
  security_opt:
    - "apparmor=nebula-job"
```

### Resource Limits

```yaml
resources:
  # CPU limits (cores)
  max_cpu_per_job: 16

  # Memory limits (MB)
  max_memory_per_job: 32768

  # Disk limits (MB)
  max_disk_per_job: 10240

  # Time limits (seconds)
  max_runtime: 86400
```

## Secrets Management

### Environment Variables

```yaml
# DON'T do this:
security:
  secret_key: "hardcoded-secret"  # Bad!

# DO this:
security:
  secret_key: "${JWT_SECRET}"  # From environment
```

### HashiCorp Vault Integration

```yaml
secrets:
  provider: "vault"
  vault:
    address: "https://vault.example.com"
    token: "${VAULT_TOKEN}"
    path: "secret/data/nebulacompute"
```

### Kubernetes Secrets

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: nebula-secrets
type: Opaque
data:
  jwt-secret: <base64-encoded>
  db-password: <base64-encoded>
---
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
        - name: master
          envFrom:
            - secretRef:
                name: nebula-secrets
```

## Security Best Practices

### 1. Use Strong Secrets

```bash
# Generate strong secret
openssl rand -base64 48

# Store securely
vault kv put secret/nebulacompute jwt_secret=$(openssl rand -base64 48)
```

### 2. Enable All Security Features

```yaml
security:
  enabled: true  # Enable authentication
  secret_key: "${JWT_SECRET}"

authorization:
  enabled: true  # Enable authorization

tls:
  enabled: true  # Enable encryption
```

### 3. Regular Updates

```bash
# Check for updates
nebula version --check

# Update
pip install --upgrade distributed-cluster
```

### 4. Audit Logging

```yaml
logging:
  audit:
    enabled: true
    path: "/var/log/nebula/audit.log"
    events:
      - auth.login
      - auth.logout
      - job.submit
      - job.cancel
      - worker.register
      - admin.*
```

### 5. Rate Limiting

```yaml
rate_limiting:
  enabled: true
  requests_per_minute: 100
  burst: 20

  # Per-endpoint limits
  endpoints:
    "/api/v1/jobs":
      requests_per_minute: 50
    "/api/v1/auth/login":
      requests_per_minute: 10
```

## Security Checklist

### Pre-Deployment

- [ ] Generated strong JWT secret (32+ characters)
- [ ] Generated TLS certificates
- [ ] Configured firewall rules
- [ ] Created appropriate user roles
- [ ] Tested authentication flow
- [ ] Reviewed container isolation settings

### Production

- [ ] TLS enabled for all connections
- [ ] mTLS for worker connections
- [ ] Authentication required for all endpoints
- [ ] RBAC configured and tested
- [ ] Audit logging enabled
- [ ] Rate limiting configured
- [ ] Secrets stored securely (not in config files)

### Ongoing

- [ ] Regular security updates applied
- [ ] Certificates rotated before expiry
- [ ] Access logs reviewed weekly
- [ ] Unused API keys revoked
- [ ] Security scanning in CI/CD
- [ ] Penetration testing annually

## Reporting Security Issues

If you discover a security vulnerability:

1. **DO NOT** open a public issue
2. Email security@nebulacompute.io
3. Include detailed reproduction steps
4. Allow 90 days for fix before disclosure

## See Also

- [Configuration Guide](CONFIGURATION.md)
- [Production Deployment](PRODUCTION_DEPLOYMENT.md)
- [Troubleshooting](TROUBLESHOOTING.md)
