# File Index

Complete reference of all important files in the churn-mlops-prod repository.

---

## Python Package: `src/churn_mlops/`

### Common Utilities

| File | Purpose |
|------|---------|
| `src/churn_mlops/__init__.py` | Package marker (empty) |
| `src/churn_mlops/common/config.py` | YAML config loader with env var support and deep merge |
| `src/churn_mlops/common/paths.py` | Project root path helper (PROJECT_ROOT, rel()) |
| `src/churn_mlops/common/logging.py` | Centralized logging setup with structured format |
| `src/churn_mlops/common/utils.py` | Utility functions (ensure_dir) |

### Data Pipeline

| File | Purpose |
|------|---------|
| `src/churn_mlops/data/generate_synthetic.py` | Generate synthetic users and events for e-learning churn |
| `src/churn_mlops/data/validate.py` | Data quality validation gates (schema, integrity, business rules) |
| `src/churn_mlops/data/prepare_dataset.py` | Clean raw data and create user_daily aggregation |

### Feature Engineering

| File | Purpose |
|------|---------|
| `src/churn_mlops/features/build_features.py` | Rolling window features (7d, 14d, 30d), recency, engagement metrics |

### Training Pipeline

| File | Purpose |
|------|---------|
| `src/churn_mlops/training/build_labels.py` | Create churn labels (30d forward-looking window) |
| `src/churn_mlops/training/build_training_set.py` | Join features + labels for training |
| `src/churn_mlops/training/train_baseline.py` | Train baseline Logistic Regression model with time-split |
| `src/churn_mlops/training/train_candidate.py` | Train candidate model (for retraining/comparison) |
| `src/churn_mlops/training/promote_model.py` | Promote best model to production_latest.joblib |

### Inference

| File | Purpose |
|------|---------|
| `src/churn_mlops/inference/batch_score.py` | Batch scoring for all users, produces risk-ranked CSV |

### Monitoring

| File | Purpose |
|------|---------|
| `src/churn_mlops/monitoring/api_metrics.py` | Prometheus metrics (request count, latency, predictions) |
| `src/churn_mlops/monitoring/drift.py` | PSI drift calculation for feature distributions |
| `src/churn_mlops/monitoring/run_drift_check.py` | Drift detection runner (exits 2 if drift found) |
| `src/churn_mlops/monitoring/score_proxy.py` | Collect actual churn outcomes for performance monitoring |
| `src/churn_mlops/monitoring/run_score_proxy.py` | Score proxy runner |

### API

| File | Purpose |
|------|---------|
| `src/churn_mlops/api/app.py` | FastAPI application with /predict, /health, /ready, /live, /metrics |

---

## Scripts: `scripts/`

Shell wrappers for common operations (all use `set -e` for fail-fast).

| Script | Purpose | Calls |
|--------|---------|-------|
| `scripts/generate_data.sh` | Generate synthetic data | `python -m churn_mlops.data.generate_synthetic` |
| `scripts/validate_data.sh` | Validate raw data | `python -m churn_mlops.data.validate` |
| `scripts/prepare_data.sh` | Prepare datasets | `python -m churn_mlops.data.prepare_dataset` |
| `scripts/build_features.sh` | Build features | `python -m churn_mlops.features.build_features` |
| `scripts/build_labels.sh` | Build labels | `python -m churn_mlops.training.build_labels` |
| `scripts/build_training_set.sh` | Build training set | `python -m churn_mlops.training.build_training_set` |
| `scripts/train_baseline.sh` | Train baseline | `python -m churn_mlops.training.train_baseline` |
| `scripts/train_candidate.sh` | Train candidate | `python -m churn_mlops.training.train_candidate` |
| `scripts/promote_model.sh` | Promote model | `python -m churn_mlops.training.promote_model` |
| `scripts/batch_score.sh` | Batch score | `python -m churn_mlops.inference.batch_score` |
| `scripts/batch_score_latest.sh` | Score latest date | `batch_score.sh` with latest date |
| `scripts/ensure_latest_predictions.sh` | Ensure predictions exist | Checks and runs batch_score if missing |
| `scripts/score_proxy.sh` | Run score proxy | `python -m churn_mlops.monitoring.run_score_proxy` |
| `scripts/run_batch_score_and_proxy.sh` | Combined batch + proxy | Runs both in sequence |
| `scripts/check_drift.sh` | Check drift | `python -m churn_mlops.monitoring.run_drift_check` |
| `scripts/monitor_data_drift.sh` | Monitor drift | Wrapper for drift check |
| `scripts/run_api.sh` | Start API locally | `uvicorn churn_mlops.api.app:app` |
| `scripts/bootstrap_minikube.sh` | Setup Minikube cluster | Creates cluster with proper resources |

---

## Configuration

### Main Config

| File | Purpose |
|------|---------|
| `config/config.yaml` | Main config (container paths: /app/data, /app/artifacts) |

### Multi-Environment Configs

| File | Purpose |
|------|---------|
| `configs/config.yaml` | Default config (same as config/config.yaml) |
| `configs/config.dev.yaml` | Development overrides |
| `configs/config.stage.yaml` | Staging overrides |
| `configs/config.prod.yaml` | Production overrides |

---

## Dependencies

| File | Purpose |
|------|---------|
| `requirements/base.txt` | Core ML deps (pandas, sklearn, numpy, pyyaml, joblib) |
| `requirements/runtime.txt` | Alias for base.txt |
| `requirements/api.txt` | API deps (fastapi, uvicorn, prometheus_client, pydantic) |
| `requirements/serving.txt` | Serving deps (api.txt + joblib) |
| `requirements/dev.txt` | Dev tools (pytest, ruff, black, pytest-cov) |

---

## Project Metadata

| File | Purpose |
|------|---------|
| `pyproject.toml` | Python project metadata, tool configs (pytest, black, mypy) |
| `ruff.toml` | Ruff linter configuration (line-length, rules) |
| `Makefile` | Common tasks (setup, lint, test, train, all) |
| `README.md` | Project overview, quick start, runbook summary |
| `.gitignore` | Git ignore patterns (data/, artifacts/, .venv/) |
| `.env.example` | Example environment variables |

---

## Docker

| File | Purpose |
|------|---------|
| `docker/Dockerfile.ml` | ML workload image (includes scripts, all deps) |
| `docker/Dockerfile.api` | API image (lean, only api deps) |
| `docker-compose.yml` | Docker Compose config (simple setup) |

---

## Kubernetes: Plain Manifests

### Core Resources

| File | Purpose |
|------|---------|
| `k8s/namespace.yaml` | churn-mlops namespace |
| `k8s/pvc.yaml` | 5Gi PersistentVolumeClaim (ReadWriteMany) |
| `k8s/configmap.yaml` | Config file as ConfigMap |

### Jobs & Deployments

| File | Purpose |
|------|---------|
| `k8s/seed-model-job.yaml` | One-time seed job (data → train → promote) |
| `k8s/api-deployment.yaml` | API Deployment (2 replicas, health checks, resource limits) |
| `k8s/api-service.yaml` | API Service (ClusterIP, port 8000) |

### CronJobs

| File | Purpose |
|------|---------|
| `k8s/batch-cronjob.yaml` | Daily batch scoring |
| `k8s/batch-score-proxy-cronjob.yaml` | Combined batch + proxy (daily) |
| `k8s/drift-cronjob.yaml` | Daily drift check (exits 2 if drift) |
| `k8s/retrain-cronjob.yaml` | Weekly retrain (Sunday 3am UTC) |

### Observability

| File | Purpose |
|------|---------|
| `k8s/ml-scripts-configmap.yaml` | Scripts as ConfigMap (alternative approach) |
| `k8s/api-metrics-annotations-patch.yaml` | Prometheus scrape config for API |
| `k8s/monitoring/servicemonitor.yaml` | Prometheus ServiceMonitor (if using Prometheus Operator) |

### Plain YAML (Validated Approach)

| File | Purpose |
|------|---------|
| `k8s/plain/namespace.yaml` | Namespace (plain) |
| `k8s/plain/pvc.yaml` | PVC (plain) |
| `k8s/plain/configmap.yaml` | ConfigMap (plain) |
| `k8s/plain/seed-model-job.yaml` | Seed job (plain) |
| `k8s/plain/api-deployment.yaml` | API deployment (plain) |
| `k8s/plain/api-service.yaml` | API service (plain) |
| `k8s/plain/batch-score-proxy-cronjob.yaml` | Batch + proxy CronJob (plain) |

---

## Kubernetes: Helm Chart (WIP)

| File | Purpose |
|------|---------|
| `k8s/helm/churn-mlops/Chart.yaml` | Helm chart metadata |
| `k8s/helm/churn-mlops/values.yaml` | Default values (image tags, replicas, resources) |
| `k8s/helm/churn-mlops/templates/_helpers.tpl` | Template helpers |
| `k8s/helm/churn-mlops/templates/configmap.yaml` | ConfigMap template |
| `k8s/helm/churn-mlops/templates/pvc.yaml` | PVC template |
| `k8s/helm/churn-mlops/templates/seed-job.yaml` | Seed job template |
| `k8s/helm/churn-mlops/templates/api-deployment.yaml` | API deployment template |
| `k8s/helm/churn-mlops/templates/api-service.yaml` | API service template |

---

## Data Artifacts (Generated)

### Raw Data

| Path | Purpose |
|------|---------|
| `data/raw/users.csv` | Synthetic users (user_id, signup_date, plan, country, ...) |
| `data/raw/events.csv` | Synthetic events (event_id, user_id, event_time, event_type, ...) |

### Processed Data

| Path | Purpose |
|------|---------|
| `data/processed/users_clean.csv` | Cleaned users |
| `data/processed/events_clean.csv` | Cleaned events |
| `data/processed/user_daily.csv` | Daily activity aggregates (user_id × date grid) |
| `data/processed/labels_daily.csv` | Churn labels (user_id, as_of_date, churn_label) |

### Features

| Path | Purpose |
|------|---------|
| `data/features/user_features_daily.csv` | Rolling window features (7d, 14d, 30d) |
| `data/features/training_dataset.csv` | Features + labels joined for training |

### Predictions

| Path | Purpose |
|------|---------|
| `data/predictions/churn_predictions_<date>.csv` | Full batch predictions (all users, risk-ranked) |
| `data/predictions/churn_top_50_<date>.csv` | Top-K preview (high-risk users) |

---

## Model Artifacts (Generated)

### Models

| Path | Purpose |
|------|---------|
| `artifacts/models/baseline_logreg_<timestamp>.joblib` | Versioned baseline model |
| `artifacts/models/candidate_logreg_<timestamp>.joblib` | Versioned candidate model |
| `artifacts/models/production_latest.joblib` | Production alias (stable name) |

### Metrics

| Path | Purpose |
|------|---------|
| `artifacts/metrics/baseline_logreg_<timestamp>.json` | Model metrics (PR-AUC, ROC-AUC, confusion matrix) |
| `artifacts/metrics/candidate_logreg_<timestamp>.json` | Candidate model metrics |
| `artifacts/metrics/production_latest.json` | Production model metrics |
| `artifacts/metrics/data_drift_latest.json` | Drift report (PSI by feature, status) |
| `artifacts/metrics/score_proxy_latest.json` | Actual performance (PR-AUC vs. actuals) |

---

## Tests

| File | Purpose |
|------|---------|
| `tests/test_config.py` | Config loading tests |
| `tests/test_data.py` | Data generation/validation tests |
| `tests/test_features.py` | Feature engineering tests |
| `tests/test_training.py` | Training pipeline tests |
| `tests/test_api.py` | API endpoint tests |
| `tests/conftest.py` | Pytest fixtures |

---

## CI/CD (Example)

| File | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | Lint + test + build on push/PR |
| `.pre-commit-config.yaml` | Pre-commit hooks (ruff, black) |

---

## Documentation (Course Notes)

| File | Purpose |
|------|---------|
| `course-notes/README.md` | Course overview, structure, learning paths |
| `course-notes/section-00-overview.md` | System architecture, MLOps lifecycle |
| `course-notes/section-01-understanding-churn.md` | Business problem, label definition |
| `course-notes/section-02-repo-blueprint-env.md` | Project structure, config, dependencies |
| `course-notes/section-03-data-design.md` | Synthetic data generation, schema design |
| `course-notes/section-04-data-validation-gates.md` | Quality checks, validation rules |
| `course-notes/section-05-feature-engineering.md` | Rolling features, recency, engagement |
| `course-notes/section-06-training-pipeline.md` | Labels, training set, baseline model |
| `course-notes/section-07-model-registry.md` | Versioning, promotion, production alias |
| `course-notes/section-08-batch-scoring.md` | Batch predictions, risk ranking |
| `course-notes/section-09-realtime-api.md` | FastAPI, health checks, Prometheus metrics |
| `course-notes/section-10-ci-cd-quality.md` | Linting, testing, pre-commit hooks |
| `course-notes/section-11-containerization-deploy.md` | Docker images, Kubernetes manifests |
| `course-notes/section-12-monitoring-retrain.md` | Drift detection, score proxy, automated retraining |
| `course-notes/section-13-capstone-runbook.md` | End-to-end operations, troubleshooting |
| `course-notes/file-index.md` | This file (complete file reference) |

---

## Key File Relationships

### Data Flow

```
generate_synthetic.py → raw/*.csv
                      ↓
validate.py         (quality gates)
                      ↓
prepare_dataset.py  → processed/*.csv (user_daily)
                      ↓
build_features.py   → features/user_features_daily.csv
build_labels.py     → processed/labels_daily.csv
                      ↓
build_training_set.py → features/training_dataset.csv
                      ↓
train_baseline.py   → models/*.joblib + metrics/*.json
promote_model.py    → models/production_latest.joblib
                      ↓
batch_score.py      → predictions/churn_predictions_*.csv
app.py              → real-time predictions (API)
```

### Config Hierarchy

```
DEFAULT_CONFIG (config.py)
    ↓
config/config.yaml (file)
    ↓
CHURN_MLOPS_CONFIG env var (override)
```

### Docker → Kubernetes

```
Dockerfile.ml    → techitfactory/churn-ml:0.1.4
Dockerfile.api   → techitfactory/churn-api:0.1.4
                      ↓
k8s/seed-model-job.yaml (uses ML image)
k8s/api-deployment.yaml (uses API image)
k8s/drift-cronjob.yaml  (uses ML image)
```

---

## Quick File Lookup

### Need to modify training logic?
→ `src/churn_mlops/training/train_baseline.py`

### Need to change feature windows?
→ `config/config.yaml` (`features.windows_days`)

### Need to adjust churn definition?
→ `src/churn_mlops/training/build_labels.py` or `config/config.yaml` (`churn.window_days`)

### Need to add API endpoint?
→ `src/churn_mlops/api/app.py`

### Need to change K8s resources?
→ `k8s/api-deployment.yaml` (resources section)

### Need to change CronJob schedule?
→ `k8s/drift-cronjob.yaml` or `k8s/retrain-cronjob.yaml` (spec.schedule)

### Need to debug seed job?
→ `k8s/seed-model-job.yaml` (args section with inline bash)

### Need to add new metric?
→ `src/churn_mlops/monitoring/api_metrics.py`

---

## File Count Summary

- **Python modules**: ~20 files
- **Scripts**: 18 shell scripts
- **Kubernetes manifests**: ~20 files
- **Config files**: 6 files
- **Documentation**: 15 markdown files
- **Dependencies**: 5 requirements files
- **Tests**: ~5 test files

**Total**: ~90 files (excluding generated data/artifacts)

---

## Next Steps

- **[README.md](README.md)**: Main project README
- **[Section 00](section-00-overview.md)**: System architecture overview
- **[Section 13](section-13-capstone-runbook.md)**: Operational runbook
