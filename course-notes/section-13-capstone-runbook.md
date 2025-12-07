# Section 13: Capstone Runbook

## Goal

Provide end-to-end operational procedures for deploying, maintaining, and troubleshooting the churn MLOps system in production.

---

## Quick Start: Three Paths

### Path 1: Local Development

**Best for**: Learning, debugging, feature development

```bash
# 1. Setup
python -m venv .venv && source .venv/bin/activate
make setup

# 2. Full pipeline
make all

# 3. Start API
./scripts/run_api.sh

# 4. Test
curl http://localhost:8000/health
```

---

### Path 2: Docker Local

**Best for**: Testing containers before K8s

```bash
# 1. Build images
export VER=0.1.4
docker build -t techitfactory/churn-ml:$VER -f docker/Dockerfile.ml .
docker build -t techitfactory/churn-api:$VER -f docker/Dockerfile.api .

# 2. Run seed (bind mount volumes)
docker run --rm \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/artifacts:/app/artifacts \
  techitfactory/churn-ml:$VER \
  bash -c "
    python -m churn_mlops.data.generate_synthetic &&
    python -m churn_mlops.training.train_baseline &&
    python -m churn_mlops.training.promote_model
  "

# 3. Run API
docker run --rm -p 8000:8000 \
  -v $(pwd)/artifacts:/app/artifacts \
  techitfactory/churn-api:$VER
```

---

### Path 3: Kubernetes (Minikube)

**Best for**: Production-like environment

```bash
# 1. Start Minikube
minikube start --cpus 4 --memory 8192

# 2. Deploy
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/seed-model-job.yaml

# 3. Wait for seed job
kubectl -n churn-mlops wait --for=condition=complete job/churn-seed-model --timeout=600s

# 4. Deploy API
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/api-service.yaml

# 5. Port-forward
kubectl -n churn-mlops port-forward svc/churn-api 8000:8000

# 6. Test
curl http://localhost:8000/ready
```

---

## Day 1: Initial Deployment

### Pre-requisites

- [ ] Docker installed and running
- [ ] Kubernetes cluster available (Minikube or cloud)
- [ ] kubectl configured
- [ ] Images built and pushed (if using remote registry)

### Steps

```bash
# 1. Create namespace
kubectl apply -f k8s/namespace.yaml

# 2. Create storage
kubectl apply -f k8s/pvc.yaml
kubectl -n churn-mlops get pvc  # Wait for Bound status

# 3. Create config
kubectl apply -f k8s/configmap.yaml

# 4. Run seed job (generates data, trains baseline)
kubectl apply -f k8s/seed-model-job.yaml
kubectl -n churn-mlops logs -f job/churn-seed-model

# 5. Verify model created
kubectl -n churn-mlops exec job/churn-seed-model -- ls -l /app/artifacts/models/
# Expected: baseline_logreg_*.joblib + production_latest.joblib

# 6. Deploy API
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/api-service.yaml

# 7. Wait for ready
kubectl -n churn-mlops wait --for=condition=ready pod -l app=churn-api --timeout=120s

# 8. Test API
kubectl -n churn-mlops port-forward svc/churn-api 8000:8000 &
curl http://localhost:8000/ready
curl http://localhost:8000/metrics

# 9. Deploy automation (CronJobs)
kubectl apply -f k8s/drift-cronjob.yaml
kubectl apply -f k8s/retrain-cronjob.yaml
```

---

## Day 2: Operations

### Daily Checklist

- [ ] Check API health: `kubectl -n churn-mlops get pods`
- [ ] Check CronJob status: `kubectl -n churn-mlops get cronjobs`
- [ ] Review logs for errors: `kubectl -n churn-mlops logs -l app=churn-api --tail=100`
- [ ] Check Prometheus metrics: `curl http://localhost:8000/metrics`

### Weekly Tasks

- [ ] Review drift reports: `cat artifacts/metrics/data_drift_latest.json`
- [ ] Check model performance: `cat artifacts/metrics/score_proxy_latest.json`
- [ ] Verify retrain CronJob ran: `kubectl -n churn-mlops get jobs`
- [ ] Clean old Job pods: `kubectl -n churn-mlops delete jobs --all`

---

## Common Operations

### 1. Update Model (Manual Retrain)

```bash
# Trigger retrain job
kubectl -n churn-mlops create job --from=cronjob/churn-retrain-weekly retrain-manual-$(date +%s)

# Wait for completion
kubectl -n churn-mlops wait --for=condition=complete job/retrain-manual-* --timeout=600s

# Check new model metrics
kubectl -n churn-mlops exec deploy/churn-api -- cat /app/artifacts/metrics/production_latest.json

# Restart API to load new model
kubectl -n churn-mlops rollout restart deployment/churn-api
kubectl -n churn-mlops rollout status deployment/churn-api
```

---

### 2. Rollback Model

```bash
# 1. List available models
kubectl -n churn-mlops exec deploy/churn-api -- ls -lt /app/artifacts/models/

# 2. Choose previous good model (e.g., baseline_logreg_20250101T103045Z.joblib)
OLD_MODEL="baseline_logreg_20250101T103045Z.joblib"

# 3. Copy to production alias (via debug pod)
kubectl -n churn-mlops run rollback-pod --rm -it --restart=Never \
  --image=busybox \
  --overrides='
  {
    "spec": {
      "containers": [{
        "name": "rollback",
        "image": "busybox",
        "command": ["sh"],
        "stdin": true,
        "tty": true,
        "volumeMounts": [{
          "name": "storage",
          "mountPath": "/pvc"
        }]
      }],
      "volumes": [{
        "name": "storage",
        "persistentVolumeClaim": {"claimName": "churn-mlops-pvc"}
      }]
    }
  }' \
  -- sh -c "cp /pvc/artifacts/models/$OLD_MODEL /pvc/artifacts/models/production_latest.joblib"

# 4. Restart API
kubectl -n churn-mlops rollout restart deployment/churn-api
```

---

### 3. Scale API

```bash
# Scale up
kubectl -n churn-mlops scale deployment/churn-api --replicas=5

# Scale down
kubectl -n churn-mlops scale deployment/churn-api --replicas=2

# Autoscale (requires metrics-server)
kubectl -n churn-mlops autoscale deployment churn-api --min=2 --max=10 --cpu-percent=80
```

---

### 4. Update Config

```bash
# 1. Edit configmap
kubectl -n churn-mlops edit configmap churn-mlops-config

# 2. Restart API to pick up changes
kubectl -n churn-mlops rollout restart deployment/churn-api
```

---

### 5. Debug Pod Issues

```bash
# View logs
kubectl -n churn-mlops logs -f deployment/churn-api

# Describe pod (check events)
kubectl -n churn-mlops describe pod -l app=churn-api

# Exec into pod
kubectl -n churn-mlops exec -it deploy/churn-api -- bash

# Inside pod: check model
ls -l /app/artifacts/models/
python -c "import joblib; m = joblib.load('/app/artifacts/models/production_latest.joblib'); print(m)"
```

---

## Troubleshooting Guide

### Issue: API Readiness Probe Fails

**Symptoms**:
- Pod status: Running but not Ready
- `/ready` endpoint returns 500

**Diagnosis**:
```bash
kubectl -n churn-mlops logs deploy/churn-api | grep -i error
kubectl -n churn-mlops exec deploy/churn-api -- ls -l /app/artifacts/models/
```

**Common Causes**:
1. **Model missing**: Seed job didn't complete
   - **Fix**: Run seed job, wait for completion
2. **PVC not mounted**: Storage issue
   - **Fix**: Check PVC status, recreate if needed
3. **Config path wrong**: CHURN_MLOPS_CONFIG env var
   - **Fix**: Verify env var in deployment YAML

---

### Issue: Seed Job Fails

**Symptoms**:
- Job status: Failed or Error
- Logs show import errors or file not found

**Diagnosis**:
```bash
kubectl -n churn-mlops logs job/churn-seed-model
kubectl -n churn-mlops describe job churn-seed-model
```

**Common Causes**:
1. **Image missing scripts**: Scripts not in ML image
   - **Fix**: Rebuild ML image with `COPY scripts ./scripts`
2. **PVC not bound**: Storage not ready
   - **Fix**: Wait for PVC to bind, check provisioner
3. **Memory limit**: Job OOM killed
   - **Fix**: Increase memory limit in job spec

---

### Issue: CronJob Never Runs

**Symptoms**:
- CronJob exists but no Job pods created

**Diagnosis**:
```bash
kubectl -n churn-mlops describe cronjob churn-drift-daily
kubectl -n churn-mlops get events --sort-by='.lastTimestamp'
```

**Common Causes**:
1. **Suspended**: `spec.suspend: true`
   - **Fix**: `kubectl patch cronjob ... -p '{"spec":{"suspend":false}}'`
2. **Schedule syntax wrong**: Invalid cron expression
   - **Fix**: Verify schedule (e.g., `0 1 * * *`)
3. **Past deadline**: Job missed and won't run
   - **Fix**: Trigger manual job

---

### Issue: Drift Check Fails

**Symptoms**:
- Drift CronJob status: Failed
- Exit code 2 in logs

**Diagnosis**:
```bash
kubectl -n churn-mlops logs jobs/churn-drift-daily-*
cat artifacts/metrics/data_drift_latest.json
```

**Expected**: This is **normal** if drift detected (exit code 2 = alert)

**Action**: Review drift report, trigger retrain if needed

---

### Issue: High API Latency

**Symptoms**:
- P95 latency > 500ms
- Slow predictions

**Diagnosis**:
```bash
curl -s http://localhost:8000/metrics | grep latency
kubectl -n churn-mlops top pods
```

**Common Causes**:
1. **CPU throttling**: Requests exceed limits
   - **Fix**: Increase CPU limits or scale replicas
2. **Large feature set**: Too many features
   - **Fix**: Feature selection, dimensionality reduction
3. **Model complexity**: Slow inference
   - **Fix**: Use simpler model or ONNX runtime

---

## Production Readiness Checklist

### Code Quality
- [ ] `make lint` passes
- [ ] `make test` passes
- [ ] Code reviewed and approved

### Data Pipeline
- [ ] Validation gates in place
- [ ] Data quality monitored
- [ ] Backups configured

### Model
- [ ] Baseline model trained and promoted
- [ ] Metrics acceptable (PR-AUC > 0.60)
- [ ] Model versioning in place

### API
- [ ] Health checks working (`/live`, `/ready`)
- [ ] Metrics exposed (`/metrics`)
- [ ] Load tested (100+ req/s)

### Deployment
- [ ] Docker images built and tagged
- [ ] K8s manifests applied
- [ ] PVC provisioned
- [ ] Secrets managed (if any)

### Monitoring
- [ ] Prometheus scraping API
- [ ] Grafana dashboard configured
- [ ] Alerts defined and tested

### Automation
- [ ] CronJobs deployed (drift, retrain)
- [ ] Automated retraining tested
- [ ] Rollback procedure documented

---

## Runbook Summary

| Task | Command | Frequency |
|------|---------|-----------|
| **Check API health** | `kubectl -n churn-mlops get pods` | Daily |
| **View API logs** | `kubectl -n churn-mlops logs -f deploy/churn-api` | On issues |
| **Check drift** | `cat artifacts/metrics/data_drift_latest.json` | Weekly |
| **Manual retrain** | `kubectl create job --from=cronjob/... retrain-now` | On drift |
| **Rollback model** | Copy old model to `production_latest.joblib` | On regression |
| **Scale API** | `kubectl scale deployment/churn-api --replicas=N` | On load |
| **Update config** | `kubectl edit configmap churn-mlops-config` | As needed |
| **Clean old jobs** | `kubectl delete jobs --field-selector status.successful=1` | Weekly |

---

## Emergency Procedures

### 1. Total API Outage

```bash
# Check pod status
kubectl -n churn-mlops get pods

# If CrashLoopBackOff:
kubectl -n churn-mlops logs -l app=churn-api --tail=100

# If ImagePullBackOff:
kubectl -n churn-mlops describe pod -l app=churn-api

# Quick fix: Rollback deployment
kubectl -n churn-mlops rollout undo deployment/churn-api
```

---

### 2. Corrupted Model

```bash
# Delete production alias
kubectl -n churn-mlops exec deploy/churn-api -- rm /app/artifacts/models/production_latest.joblib

# Re-run seed job
kubectl -n churn-mlops delete job churn-seed-model
kubectl -n churn-mlops apply -f k8s/seed-model-job.yaml

# Wait and restart API
kubectl -n churn-mlops rollout restart deployment/churn-api
```

---

### 3. Out of Disk Space

```bash
# Check PVC usage
kubectl -n churn-mlops exec deploy/churn-api -- df -h /app/data /app/artifacts

# Clean old predictions
kubectl -n churn-mlops exec deploy/churn-api -- sh -c "
  find /app/data/predictions -name '*.csv' -mtime +30 -delete
"

# Increase PVC size (if supported by provisioner)
kubectl -n churn-mlops patch pvc churn-mlops-pvc -p '{"spec":{"resources":{"requests":{"storage":"10Gi"}}}}'
```

---

## Best Practices

1. **Version everything**: Images, models, configs
2. **Test locally first**: Docker → Minikube → Production
3. **Monitor continuously**: Metrics, logs, alerts
4. **Automate retraining**: Don't let models go stale
5. **Document changes**: Keep runbook updated

---

## Next Steps

- **[Section 00](section-00-overview.md)**: Review system architecture
- **[file-index.md](file-index.md)**: Complete file reference
- **[README.md](README.md)**: Course overview

---

## Key Takeaways

1. **Three deployment paths**: Local, Docker, Kubernetes (use appropriate for each stage)
2. **Daily operations**: Check health, monitor logs, review metrics
3. **Troubleshooting**: Logs + describe + exec into pods
4. **Emergency procedures**: Rollback, re-seed, scale
5. **Production readiness**: Checklists ensure nothing missed
