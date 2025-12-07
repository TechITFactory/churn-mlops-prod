# Section 11: Containerization & Deployment

## Goal

Package ML workloads and API into Docker containers and deploy to Kubernetes with proper resource management, health checks, and persistence.

---

## Docker Strategy

### Two Images

**Why separate images?**
- **ML image** (`churn-ml`): Heavy (includes scripts, all dependencies), used for Jobs/CronJobs
- **API image** (`churn-api`): Lean (only API deps), optimized for fast startup and low memory

---

## ML Image

### File: `docker/Dockerfile.ml`

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
  && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements ./requirements
COPY pyproject.toml README.md ./

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements/base.txt \
 && pip install --no-cache-dir -r requirements/dev.txt \
 && pip install --no-cache-dir -r requirements/serving.txt || true

# Copy source code
COPY src ./src
COPY config ./config

# ✅ Critical: Copy scripts for CronJobs
COPY scripts ./scripts
RUN chmod +x ./scripts/*.sh

# Install package
RUN pip install --no-cache-dir .

# Set default config
ENV CHURN_MLOPS_CONFIG=/app/config/config.yaml

CMD ["bash"]
```

**Key Points**:
- Includes `scripts/` directory for CronJobs
- Installs dev dependencies (for training)
- Generic CMD (overridden by K8s Job args)

**Build**:
```bash
docker build -t techitfactory/churn-ml:0.1.4 -f docker/Dockerfile.ml .
```

---

## API Image

### File: `docker/Dockerfile.api`

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
  && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements ./requirements
COPY pyproject.toml README.md ./
COPY config ./config
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements/api.txt \
 && pip install --no-cache-dir .

# Set default config
ENV CHURN_MLOPS_CONFIG=/app/config/config.yaml

# Expose port
EXPOSE 8000

# Start uvicorn
CMD ["uvicorn", "churn_mlops.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Key Points**:
- Only API dependencies (fastapi, uvicorn, prometheus_client)
- No scripts/ directory (smaller image)
- Specific CMD for uvicorn

**Build**:
```bash
docker build -t techitfactory/churn-api:0.1.4 -f docker/Dockerfile.api .
```

---

## Kubernetes Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       Namespace: churn-mlops                 │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐         ┌──────────────────┐         │
│  │  PVC (5Gi)       │         │  ConfigMap        │         │
│  │  churn-mlops-pvc │         │  churn-mlops-     │         │
│  │                  │         │  config           │         │
│  └──────────────────┘         └──────────────────┘         │
│           ↑                            ↑                     │
│           │                            │                     │
│  ┌────────┴────────┬──────────────────┴─────────────┐      │
│  │                 │                                  │      │
│  │  Seed Job       │  API Deployment (2 replicas)   │      │
│  │  (one-time)     │  + Service (ClusterIP)         │      │
│  │                 │                                  │      │
│  └─────────────────┴──────────────────────────────────┘     │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  CronJobs                                             │  │
│  │  - Batch Score + Proxy (daily)                       │  │
│  │  - Drift Check (daily)                               │  │
│  │  - Retrain (weekly)                                  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Kubernetes Manifests

### 1. Namespace

**File**: `k8s/namespace.yaml`

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: churn-mlops
```

---

### 2. PersistentVolumeClaim

**File**: `k8s/pvc.yaml`

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: churn-mlops-pvc
  namespace: churn-mlops
spec:
  accessModes:
    - ReadWriteMany  # Shared across pods
  resources:
    requests:
      storage: 5Gi
```

**Purpose**: Shared storage for data and artifacts

---

### 3. ConfigMap

**File**: `k8s/configmap.yaml`

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: churn-mlops-config
  namespace: churn-mlops
data:
  config.yaml: |
    app:
      name: churn-mlops
      env: prod
      log_level: INFO
    
    paths:
      data: /app/data
      raw: /app/data/raw
      processed: /app/data/processed
      features: /app/data/features
      predictions: /app/data/predictions
      artifacts: /app/artifacts
      models: /app/artifacts/models
      metrics: /app/artifacts/metrics
    
    features:
      windows_days: [7, 14, 30]
    
    churn:
      window_days: 30
```

---

### 4. Seed Model Job

**File**: `k8s/seed-model-job.yaml`

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: churn-seed-model
  namespace: churn-mlops
spec:
  backoffLimit: 1
  template:
    spec:
      restartPolicy: Never
      
      initContainers:
        - name: init-dirs
          image: busybox:1.36
          command: ["sh", "-c", "mkdir -p /pvc/data /pvc/artifacts"]
          volumeMounts:
            - name: mlops-storage
              mountPath: /pvc
      
      containers:
        - name: seed
          image: techitfactory/churn-ml:0.1.2
          imagePullPolicy: Always
          
          env:
            - name: CHURN_MLOPS_CONFIG
              value: /app/config/config.yaml
          
          command: ["sh", "-c"]
          args:
            - |
              set -e
              python -m churn_mlops.data.generate_synthetic
              python -m churn_mlops.data.validate
              python -m churn_mlops.data.prepare_dataset
              python -m churn_mlops.features.build_features
              python -m churn_mlops.training.build_labels
              python -m churn_mlops.training.build_training_set
              python -m churn_mlops.training.train_baseline
              
              # Promote to production alias
              LATEST_MODEL=$(ls -1 /app/artifacts/models/baseline_logreg_*.joblib | tail -n 1)
              cp "$LATEST_MODEL" /app/artifacts/models/production_latest.joblib
          
          volumeMounts:
            - name: mlops-storage
              mountPath: /app/data
              subPath: data
            - name: mlops-storage
              mountPath: /app/artifacts
              subPath: artifacts
            - name: config
              mountPath: /app/config/config.yaml
              subPath: config.yaml
      
      volumes:
        - name: config
          configMap:
            name: churn-mlops-config
        - name: mlops-storage
          persistentVolumeClaim:
            claimName: churn-mlops-pvc
```

**Purpose**: One-time job to generate data, train baseline, and create production alias

---

### 5. API Deployment

**File**: `k8s/api-deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: churn-api
  namespace: churn-mlops
  labels:
    app: churn-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: churn-api
  template:
    metadata:
      labels:
        app: churn-api
    spec:
      initContainers:
        - name: init-dirs
          image: busybox:1.36
          command:
            - sh
            - -c
            - |
              mkdir -p /pvc/data /pvc/data/predictions
              mkdir -p /pvc/artifacts /pvc/artifacts/models /pvc/artifacts/metrics
          volumeMounts:
            - name: mlops-storage
              mountPath: /pvc
      
      containers:
        - name: churn-api
          image: techitfactory/churn-api:0.1.2
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8000
          
          env:
            - name: CHURN_MLOPS_CONFIG
              value: /app/config/config.yaml
          
          volumeMounts:
            - name: mlops-storage
              mountPath: /app/data
              subPath: data
            - name: mlops-storage
              mountPath: /app/artifacts
              subPath: artifacts
            - name: config
              mountPath: /app/config/config.yaml
              subPath: config.yaml
          
          livenessProbe:
            httpGet:
              path: /live
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 20
          
          readinessProbe:
            httpGet:
              path: /ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
          
          resources:
            requests:
              cpu: "100m"
              memory: "256Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
      
      volumes:
        - name: mlops-storage
          persistentVolumeClaim:
            claimName: churn-mlops-pvc
        - name: config
          configMap:
            name: churn-mlops-config
```

---

### 6. API Service

**File**: `k8s/api-service.yaml`

```yaml
apiVersion: v1
kind: Service
metadata:
  name: churn-api
  namespace: churn-mlops
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "8000"
    prometheus.io/path: "/metrics"
spec:
  selector:
    app: churn-api
  ports:
    - protocol: TCP
      port: 8000
      targetPort: 8000
  type: ClusterIP
```

---

### 7. Drift CronJob

**File**: `k8s/drift-cronjob.yaml`

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: churn-drift-daily
  namespace: churn-mlops
spec:
  schedule: "0 1 * * *"  # Daily at 1am UTC
  successfulJobsHistoryLimit: 2
  failedJobsHistoryLimit: 2
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          
          containers:
            - name: drift
              image: techitfactory/churn-ml:0.1.2
              imagePullPolicy: Always
              env:
                - name: CHURN_MLOPS_CONFIG
                  value: /app/config/config.yaml
              command: ["sh", "-c"]
              args:
                - |
                  set -e
                  python -m churn_mlops.monitoring.run_drift_check
              
              volumeMounts:
                - name: mlops-storage
                  mountPath: /app/data
                  subPath: data
                - name: mlops-storage
                  mountPath: /app/artifacts
                  subPath: artifacts
                - name: config
                  mountPath: /app/config/config.yaml
                  subPath: config.yaml
          
          volumes:
            - name: config
              configMap:
                name: churn-mlops-config
            - name: mlops-storage
              persistentVolumeClaim:
                claimName: churn-mlops-pvc
```

---

## Deploy to Kubernetes

```bash
# Apply all manifests
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/seed-model-job.yaml
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/api-service.yaml
kubectl apply -f k8s/drift-cronjob.yaml
kubectl apply -f k8s/retrain-cronjob.yaml

# Or apply all at once
kubectl apply -f k8s/

# Check status
kubectl -n churn-mlops get all
kubectl -n churn-mlops get pvc
kubectl -n churn-mlops logs -f job/churn-seed-model
```

---

## Files Involved

| File | Purpose |
|------|---------|
| `docker/Dockerfile.ml` | ML workload image |
| `docker/Dockerfile.api` | API service image |
| `k8s/namespace.yaml` | Kubernetes namespace |
| `k8s/pvc.yaml` | Persistent storage |
| `k8s/configmap.yaml` | Configuration file |
| `k8s/seed-model-job.yaml` | Initial training job |
| `k8s/api-deployment.yaml` | API deployment |
| `k8s/api-service.yaml` | API service |
| `k8s/drift-cronjob.yaml` | Drift check CronJob |
| `k8s/retrain-cronjob.yaml` | Retrain CronJob |

---

## Verification Steps

```bash
# 1. Check namespace
kubectl get ns churn-mlops

# 2. Check PVC
kubectl -n churn-mlops get pvc

# 3. Check seed job
kubectl -n churn-mlops get job
kubectl -n churn-mlops logs -f job/churn-seed-model

# 4. Check API pods
kubectl -n churn-mlops get pods
kubectl -n churn-mlops logs -f deployment/churn-api

# 5. Port-forward and test
kubectl -n churn-mlops port-forward svc/churn-api 8000:8000
curl http://localhost:8000/ready

# 6. Check CronJobs
kubectl -n churn-mlops get cronjobs
```

---

## Troubleshooting

**Issue**: Seed job fails with "FileNotFoundError"
- **Cause**: PVC not mounted correctly
- **Fix**: Check PVC status, verify subPath mounts

**Issue**: API readiness probe fails
- **Cause**: Model not found (seed job didn't complete)
- **Fix**: Run seed job to completion first

**Issue**: CronJob fails with "scripts not found"
- **Cause**: ML image doesn't include scripts/
- **Fix**: Rebuild ML image with `COPY scripts ./scripts`

**Issue**: Out of disk space
- **Cause**: PVC too small (5Gi)
- **Fix**: Increase PVC size or clean old data

---

## Best Practices

1. **Version images**: Use tags (e.g., `0.1.4`), not `latest`
2. **Separate concerns**: ML image != API image
3. **Health checks**: Liveness + readiness probes
4. **Resource limits**: Prevent pods from consuming all cluster resources
5. **Init containers**: Ensure directories exist before main container starts

---

## Next Steps

- **[Section 12](section-12-monitoring-retrain.md)**: Monitoring and automated retraining
- **[Section 09](section-09-realtime-api.md)**: Review API implementation
- **[Section 13](section-13-capstone-runbook.md)**: End-to-end runbook

---

## Key Takeaways

1. **Two Docker images**: ML (heavy, for Jobs) and API (lean, for service)
2. **PVC for persistence**: Shared storage across pods
3. **ConfigMap for config**: Externalized configuration
4. **Init containers**: Prepare environment before main container
5. **Health probes**: Enable safe deployments and rolling updates
