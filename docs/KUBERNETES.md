# Kubernetes Guide

Guide to deploying NebulaCompute on Kubernetes.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Deployment Options](#deployment-options)
- [Configuration](#configuration)
- [Scaling](#scaling)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

## Prerequisites

- Kubernetes 1.24+
- kubectl configured
- Helm 3.x (for Helm deployment)
- PersistentVolume provisioner (for persistence)

## Quick Start

### Using kubectl

```bash
# Clone repository
git clone https://github.com/salahuddin1992/theEnd.git
cd theEnd

# Create namespace
kubectl apply -f deploy/kubernetes/namespace.yaml

# Apply configuration
kubectl apply -f deploy/kubernetes/configmap.yaml

# Deploy master
kubectl apply -f deploy/kubernetes/master-deployment.yaml

# Deploy workers
kubectl apply -f deploy/kubernetes/worker-deployment.yaml

# Apply ingress
kubectl apply -f deploy/kubernetes/ingress.yaml

# Verify deployment
kubectl get pods -n nebulacompute
```

### Using Helm

```bash
# Add repository (if published)
helm repo add nebulacompute https://charts.nebulacompute.io

# Install
helm install nebula nebulacompute/distributed-cluster \
  --namespace nebulacompute \
  --create-namespace

# Or from local chart
helm install nebula ./deploy/helm/distributed-cluster \
  --namespace nebulacompute \
  --create-namespace
```

## Deployment Options

### Namespace

```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: nebulacompute
  labels:
    app.kubernetes.io/name: nebulacompute
```

### ConfigMap

```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: nebula-config
  namespace: nebulacompute
data:
  config.yaml: |
    master:
      host: "0.0.0.0"
      port: 8000
    scheduler:
      policy: "best_fit"
    logging:
      level: "INFO"
      format: "json"
```

### Secrets

```yaml
# secrets.yaml
apiVersion: v1
kind: Secret
metadata:
  name: nebula-secrets
  namespace: nebulacompute
type: Opaque
data:
  jwt-secret: <base64-encoded-secret>
  db-password: <base64-encoded-password>
```

### Master Deployment

```yaml
# master-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nebula-master
  namespace: nebulacompute
spec:
  replicas: 1
  selector:
    matchLabels:
      app: nebula-master
  template:
    metadata:
      labels:
        app: nebula-master
    spec:
      containers:
        - name: master
          image: ghcr.io/salahuddin1992/theend:latest
          command: ["nebula", "master", "start", "--host", "0.0.0.0"]
          ports:
            - containerPort: 8000
          env:
            - name: NEBULA_JWT_SECRET
              valueFrom:
                secretKeyRef:
                  name: nebula-secrets
                  key: jwt-secret
          volumeMounts:
            - name: config
              mountPath: /app/config.yaml
              subPath: config.yaml
            - name: data
              mountPath: /app/data
          livenessProbe:
            httpGet:
              path: /health/live
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "2"
              memory: "4Gi"
      volumes:
        - name: config
          configMap:
            name: nebula-config
        - name: data
          persistentVolumeClaim:
            claimName: nebula-master-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: nebula-master
  namespace: nebulacompute
spec:
  selector:
    app: nebula-master
  ports:
    - port: 8000
      targetPort: 8000
```

### Worker Deployment

```yaml
# worker-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nebula-worker
  namespace: nebulacompute
spec:
  replicas: 3
  selector:
    matchLabels:
      app: nebula-worker
  template:
    metadata:
      labels:
        app: nebula-worker
    spec:
      containers:
        - name: worker
          image: ghcr.io/salahuddin1992/theend:latest
          command: ["nebula", "worker", "start", "--master", "http://nebula-master:8000"]
          env:
            - name: WORKER_TAGS
              value: "cpu,docker"
          volumeMounts:
            - name: docker-sock
              mountPath: /var/run/docker.sock
          resources:
            requests:
              cpu: "1"
              memory: "2Gi"
            limits:
              cpu: "4"
              memory: "8Gi"
      volumes:
        - name: docker-sock
          hostPath:
            path: /var/run/docker.sock
```

### GPU Worker Deployment

```yaml
# worker-gpu-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nebula-gpu-worker
  namespace: nebulacompute
spec:
  replicas: 2
  selector:
    matchLabels:
      app: nebula-gpu-worker
  template:
    metadata:
      labels:
        app: nebula-gpu-worker
    spec:
      containers:
        - name: worker
          image: ghcr.io/salahuddin1992/theend:latest
          command: ["nebula", "worker", "start", "--master", "http://nebula-master:8000"]
          env:
            - name: WORKER_TAGS
              value: "gpu,nvidia,cuda"
          resources:
            limits:
              nvidia.com/gpu: 1
```

### Ingress

```yaml
# ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: nebula-ingress
  namespace: nebulacompute
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "100m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
spec:
  ingressClassName: nginx
  rules:
    - host: nebula.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: nebula-master
                port:
                  number: 8000
  tls:
    - hosts:
        - nebula.example.com
      secretName: nebula-tls
```

### Horizontal Pod Autoscaler

```yaml
# hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: nebula-worker-hpa
  namespace: nebulacompute
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: nebula-worker
  minReplicas: 3
  maxReplicas: 50
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: External
      external:
        metric:
          name: nebula_jobs_pending
          selector:
            matchLabels:
              service: nebulacompute
        target:
          type: AverageValue
          averageValue: 10
```

## Configuration

### Helm Values

```yaml
# values.yaml
replicaCount:
  master: 1
  worker: 5
  gpuWorker: 2

image:
  repository: ghcr.io/salahuddin1992/theend
  tag: latest
  pullPolicy: IfNotPresent

master:
  resources:
    requests:
      cpu: "500m"
      memory: "1Gi"
    limits:
      cpu: "2"
      memory: "4Gi"

worker:
  resources:
    requests:
      cpu: "1"
      memory: "2Gi"
    limits:
      cpu: "4"
      memory: "8Gi"
  tags:
    - cpu
    - docker

gpuWorker:
  enabled: true
  gpuCount: 1
  tags:
    - gpu
    - nvidia

persistence:
  enabled: true
  size: 10Gi
  storageClass: ""

ingress:
  enabled: true
  className: nginx
  host: nebula.example.com
  tls:
    enabled: true
    secretName: nebula-tls

database:
  type: postgresql
  host: postgres
  name: nebulacompute
  existingSecret: nebula-db-secret

redis:
  enabled: true
  host: redis-master
```

### Install with Values

```bash
helm install nebula ./deploy/helm/distributed-cluster \
  -f values.yaml \
  --namespace nebulacompute \
  --create-namespace
```

## Scaling

### Manual Scaling

```bash
# Scale workers
kubectl scale deployment nebula-worker --replicas=10 -n nebulacompute

# Scale GPU workers
kubectl scale deployment nebula-gpu-worker --replicas=5 -n nebulacompute
```

### Auto-Scaling

```bash
# Apply HPA
kubectl apply -f deploy/kubernetes/hpa.yaml

# Check HPA status
kubectl get hpa -n nebulacompute
```

### Custom Metrics Auto-Scaling

```yaml
# Using KEDA
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: nebula-worker-scaler
  namespace: nebulacompute
spec:
  scaleTargetRef:
    name: nebula-worker
  minReplicaCount: 3
  maxReplicaCount: 100
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus:9090
        metricName: nebula_jobs_pending
        threshold: "10"
        query: nebula_jobs_pending
```

## Monitoring

### ServiceMonitor

```yaml
# servicemonitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: nebula-master
  namespace: nebulacompute
spec:
  selector:
    matchLabels:
      app: nebula-master
  endpoints:
    - port: http
      path: /metrics
      interval: 15s
```

### PrometheusRule

```yaml
# prometheusrule.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: nebula-alerts
  namespace: nebulacompute
spec:
  groups:
    - name: nebulacompute
      rules:
        - alert: NoActiveWorkers
          expr: nebula_workers_active == 0
          for: 5m
          labels:
            severity: critical
          annotations:
            summary: "No active workers in cluster"
```

## Troubleshooting

### Common Issues

**Pods not starting:**
```bash
kubectl describe pod <pod-name> -n nebulacompute
kubectl logs <pod-name> -n nebulacompute
```

**Workers not connecting:**
```bash
# Check service
kubectl get svc -n nebulacompute

# Check DNS
kubectl run debug --rm -it --image=busybox -- nslookup nebula-master.nebulacompute
```

**GPU not detected:**
```bash
# Check GPU nodes
kubectl get nodes -l nvidia.com/gpu.present=true

# Check GPU plugin
kubectl get pods -n kube-system | grep nvidia
```

### Useful Commands

```bash
# Get all resources
kubectl get all -n nebulacompute

# View master logs
kubectl logs -f deployment/nebula-master -n nebulacompute

# Execute shell in master
kubectl exec -it deployment/nebula-master -n nebulacompute -- /bin/bash

# Port forward for local access
kubectl port-forward svc/nebula-master 8000:8000 -n nebulacompute
```

## See Also

- [Docker Guide](DOCKER.md)
- [Scaling Guide](SCALING.md)
- [Production Deployment](PRODUCTION_DEPLOYMENT.md)
