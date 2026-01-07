# V1 MLOps Pipeline Workflow

This document shows the complete MLOps pipeline for V1 (`churn-mlops-prod`) and what we implemented at each phase.

---

## Visual Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        V1.0 MLOps Pipeline Workflow                             │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐ │
│   │   DATA   │───▶│ VALIDATE │───▶│ FEATURES │───▶│  TRAIN   │───▶│  DEPLOY  │ │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘ │
│        │               │               │               │               │        │
│        ▼               ▼               ▼               ▼               ▼        │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐ │
│   │ Scripts  │    │ Python   │    │ Rolling  │    │ Baseline │    │ FastAPI  │ │
│   │          │    │ Checks   │    │ Windows  │    │ + Promote│    │ + K8s    │ │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘ │
│                                                                                  │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐                                  │
│   │  SCORE   │◀───│ MONITOR  │◀───│ RETRAIN  │◀─── (Weekly CronJob)            │
│   └──────────┘    └──────────┘    └──────────┘                                  │
│        │               │               │                                         │
│        ▼               ▼               ▼                                         │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐                                  │
│   │ Batch    │    │ PSI Drift│    │ Candidate│                                  │
│   │ Predict  │    │ Check    │    │ Model    │                                  │
│   └──────────┘    └──────────┘    └──────────┘                                  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: DATA (Generate & Prepare)

### What We Built
| Component | File | Purpose |
|-----------|------|---------|
| Synthetic Generator | `src/churn_mlops/data/generate_synthetic.py` | Creates realistic user + event data |
| Data Preparation | `src/churn_mlops/data/prepare_dataset.py` | Cleans, aggregates to user_daily |
| Shell Wrapper | `scripts/generate_data.sh` | Runs generator module |

### Commands
```bash
python -m churn_mlops.data.generate_synthetic
python -m churn_mlops.data.prepare_dataset
# Or via Makefile:
make data
```

### Outputs
- `data/raw/users.csv` - User profiles
- `data/raw/events.csv` - User activity events
- `data/processed/user_daily.csv` - Daily aggregated activity

---

## Phase 2: VALIDATE (Quality Gates)

### What We Built
| Component | File | Purpose |
|-----------|------|---------|
| Validation Logic | `src/churn_mlops/data/validate.py` | Schema, integrity, range checks |
| Shell Wrapper | `scripts/validate_data.sh` | Runs validation |

### Commands
```bash
python -m churn_mlops.data.validate
```

### Checks Performed
- Schema validation (column names, types)
- Null check (critical columns)
- Range validation (dates, numeric bounds)
- Referential integrity (user_id exists)

---

## Phase 3: FEATURES (Engineering)

### What We Built
| Component | File | Purpose |
|-----------|------|---------|
| Feature Builder | `src/churn_mlops/features/build_features.py` | Rolling window aggregations |
| Label Builder | `src/churn_mlops/training/build_labels.py` | Churn labels (30-day forward) |
| Training Set | `src/churn_mlops/training/build_training_set.py` | Merges features + labels |

### Commands
```bash
python -m churn_mlops.features.build_features
python -m churn_mlops.training.build_labels
python -m churn_mlops.training.build_training_set
# Or via Makefile:
make features
make labels
```

### Features Created
- `active_days_7d`, `active_days_14d`, `active_days_30d`
- `events_7d`, `events_14d`, `events_30d`
- `engagement_score`
- `days_since_first_activity`

### Outputs
- `data/features/user_features_daily.csv`
- `data/processed/labels_daily.csv`
- `data/features/training_dataset.csv`

---

## Phase 4: TRAIN (Model Training)

### What We Built
| Component | File | Purpose |
|-----------|------|---------|
| Baseline Model | `src/churn_mlops/training/train_baseline.py` | Logistic Regression |
| Candidate Model | `src/churn_mlops/training/train_candidate.py` | Same algo for retraining |
| Model Promotion | `src/churn_mlops/training/promote_model.py` | Selects best model |

### Commands
```bash
python -m churn_mlops.training.train_baseline
python -m churn_mlops.training.promote_model
# Or via Makefile:
make train
make promote
```

### Outputs
- `artifacts/models/baseline_logreg_<timestamp>.joblib`
- `artifacts/metrics/baseline_logreg_<timestamp>.json`
- `artifacts/models/production_latest.joblib` (promoted)

---

## Phase 5: DEPLOY (Containerize & Serve)

### What We Built
| Component | File | Purpose |
|-----------|------|---------|
| FastAPI App | `src/churn_mlops/api/app.py` | REST API endpoints |
| ML Dockerfile | `docker/Dockerfile.ml` | Training/batch image |
| API Dockerfile | `docker/Dockerfile.api` | Serving image |
| K8s Manifests | `k8s/*.yaml` | Deployment, Service, Jobs |

### Commands
```bash
# Build
docker build -t techitfactory/churn-ml:0.1.4 -f docker/Dockerfile.ml .
docker build -t techitfactory/churn-api:0.1.4 -f docker/Dockerfile.api .

# Deploy
kubectl apply -f k8s/
```

### API Endpoints
| Endpoint | Purpose |
|----------|---------|
| `/health` | Liveness check |
| `/ready` | Readiness check |
| `/predict` | Single prediction |
| `/metrics` | Prometheus metrics |

---

## Phase 6: SCORE (Batch Predictions)

### What We Built
| Component | File | Purpose |
|-----------|------|---------|
| Batch Scorer | `src/churn_mlops/inference/batch_score.py` | Scores all users |
| CronJob | `k8s/batch-cronjob.yaml` | Daily scheduling |

### Commands
```bash
python -m churn_mlops.inference.batch_score
# Or via Makefile:
make batch
```

### Outputs
- `data/predictions/churn_predictions_<date>.csv`

---

## Phase 7: MONITOR (Drift Detection)

### What We Built
| Component | File | Purpose |
|-----------|------|---------|
| Drift Calculator | `src/churn_mlops/monitoring/drift.py` | PSI calculation |
| Drift Runner | `src/churn_mlops/monitoring/run_drift_check.py` | Executes drift check |
| API Metrics | `src/churn_mlops/monitoring/api_metrics.py` | Prometheus counters |
| CronJob | `k8s/drift-cronjob.yaml` | Daily/weekly scheduling |

### Commands
```bash
python -m churn_mlops.monitoring.run_drift_check
```

### Outputs
- `artifacts/metrics/data_drift_latest.json`
- Exit code 0 (OK) or 2 (drift detected)

---

## Phase 8: RETRAIN (Automated)

### What We Built
| Component | File | Purpose |
|-----------|------|---------|
| Candidate Trainer | `src/churn_mlops/training/train_candidate.py` | Retrains model |
| Promotion Logic | `src/churn_mlops/training/promote_model.py` | Promotes if better |
| CronJob | `k8s/retrain-cronjob.yaml` | Weekly scheduling |

### Commands
```bash
python -m churn_mlops.training.train_candidate
python -m churn_mlops.training.promote_model
```

### Workflow
1. CronJob triggers weekly
2. Trains candidate model
3. Compares PR-AUC with production
4. Promotes if better
5. Restarts API to load new model

---

## Infrastructure (Supporting)

### What We Built
| Component | File | Purpose |
|-----------|------|---------|
| Terraform | `terraform/main.tf` | VPC + EKS cluster |
| ConfigMap | `k8s/configmap.yaml` | App configuration |
| PVC | `k8s/pvc.yaml` | Shared storage |
| Seed Job | `k8s/seed-model-job.yaml` | Initial data + model |

---

## V1 Complete Command Flow

```bash
# 1. Setup
git clone https://github.com/TechITFactory/churn-mlops-prod.git
cd churn-mlops-prod
python -m venv .venv && source .venv/bin/activate
make setup

# 2. Run pipeline
make all            # DATA → VALIDATE → FEATURES → TRAIN → PROMOTE → BATCH

# 3. Deploy
cd terraform && terraform apply
aws eks update-kubeconfig --name churn-mlops
kubectl apply -f k8s/

# 4. Test
kubectl -n churn-mlops port-forward svc/churn-api 8000:8000
curl http://localhost:8000/ready
```

---

## Summary

| Phase | What We Did | Tool |
|-------|-------------|------|
| DATA | Synthetic generation | Python scripts |
| VALIDATE | Quality checks | Python + exit codes |
| FEATURES | Rolling aggregations | Pandas |
| TRAIN | Logistic Regression | scikit-learn |
| DEPLOY | API + K8s | FastAPI, Docker, kubectl |
| SCORE | Batch predictions | CronJob |
| MONITOR | PSI drift check | CronJob |
| RETRAIN | Weekly candidate | CronJob |
