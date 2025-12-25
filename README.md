## Churn MLOps — Production-Grade DevOps + MLOps Reference Implementation

This repository demonstrates an end-to-end, production-oriented MLOps platform for customer churn prediction:

- Repeatable **data → features → training → model promotion** pipelines
- **Batch scoring** and a lightweight **score proxy**
- A **FastAPI** realtime inference service with **Prometheus metrics**
- Containerized local workflows (Docker Compose) and production deployment patterns (Kubernetes + GitOps)

It’s designed as a practical repo for DevOps/Platform engineers building and operating ML services.

## What we do in this project (end-to-end)

1. **Generate and validate data** (local scripts)
2. **Prepare processed datasets**
3. **Build features** and **training labels**
4. **Train models** (baseline + candidate)
5. **Promote** the best model into the “production” slot
6. **Batch score** users with the production model
7. **Serve realtime predictions** via API
8. **Monitor**: health/readiness + Prometheus metrics, and drift checks
9. **Deploy** using containers locally and Kubernetes/GitOps in production

These steps are wired through `scripts/` and the `Makefile`.

## Quick start (local Python)

Prereqs: Python 3.10+, make

```bash
python -m venv .venv
source .venv/bin/activate

make setup
make lint
make test

# Full local pipeline:
make all
```

Run the API:

```bash
./scripts/run_api.sh
```

Verify endpoints:

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/live
curl -s http://localhost:8000/ready
curl -s http://localhost:8000/metrics | head
```

## Quick start (Docker Compose)

Prereqs: Docker + Docker Compose

```bash
# Optional: set Grafana admin password (see .env.example)
export GRAFANA_ADMIN_PASSWORD=CHANGE_ME

# Train+promote a production model once
docker compose run --rm seed-model

# Start API + Prometheus + Grafana
docker compose up --build
```

URLs:
- API: http://localhost:8000
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000

## Deploy (production patterns)

This repo includes Kubernetes and GitOps assets for production-style deployments:

- `k8s/`: Kubernetes manifests (deployments, services, cronjobs, configmaps)
- `argocd/`: ArgoCD applications/projects (GitOps)
- `terraform/`: IaC examples for cloud infrastructure

Start with:
- `docs/PRODUCTION_DEPLOYMENT.md`
- `docs/GITOPS_WORKFLOW.md`

## Repository entrypoints

### Make targets

The `Makefile` orchestrates the core pipeline:

- `make data` → generate + validate + prepare
- `make features` → feature engineering
- `make labels` → labels + training set
- `make train` → baseline + candidate training
- `make promote` → promote best model
- `make batch` → batch score with production model
- `make all` → end-to-end local run

### Scripts

Key scripts (see `scripts/`):

- `generate_data.sh`, `validate_data.sh`, `prepare_data.sh`
- `build_features.sh`, `build_labels.sh`, `build_training_set.sh`
- `train_baseline.sh`, `train_candidate.sh`, `promote_model.sh`
- `batch_score.sh`, `score_proxy.sh`
- `run_api.sh`

## Configuration

Primary config is loaded via `CHURN_MLOPS_CONFIG`.

- Defaults are under `config/` and `configs/`.
- The API launcher (`scripts/run_api.sh`) auto-selects a config if you don’t set one.

## Monitoring

- API exposes Prometheus metrics at `/metrics`
- Docker Compose brings up Prometheus + Grafana locally
- Kubernetes manifests include scheduled jobs for batch scoring/drift checks

## Security notes (public repo)

- Do not commit secrets (tokens, passwords, private keys). Use GitHub Actions secrets, Kubernetes Secrets, or external secret managers.
- This repo includes placeholders and safe examples; if you fork it, ensure your own credentials are stored in secret managers.

## Helpful docs

- `HOW_TO_TEST.md` (start here for verification)
- `QUICK_REFERENCE.md` (common commands)
- `PRODUCTION_README.md` (longer production overview)


* `ModuleNotFoundError: pandas` or `prometheus_client`

Fix:

* ensure dependency exists in `requirements/api.txt`
* rebuild API image with same `VER`
* rollout restart

### C) Batch/cron scripts not found in K8s

If a Job says:

* `./scripts/*.sh: not found`

It means the image does not include the scripts.
Use the **plain K8s approach** you already validated or mount scripts via ConfigMap (we’ll clean this in Helm later).
EOF

````

---

## 13.2 Rollback plan

```bash
cat << 'EOF' > docs/rollback.md
# Rollback Plan — TechITFactory Churn MLOps

This rollback plan covers:
- Model artifacts
- API deployment
- Scheduled jobs

---

## 1) Model rollback (fastest)

We keep:
- versioned models: `baseline_logreg_<timestamp>.joblib`
- stable alias: `production_latest.joblib`

### 1.1 Local

List models:
```bash
ls -1 artifacts/models | sort
````

Pick a known-good model and overwrite alias:

```bash
cp artifacts/models/<GOOD_MODEL>.joblib artifacts/models/production_latest.joblib
```

Restart local API if running.

### 1.2 Kubernetes

Check models inside PVC:

```bash
kubectl -n churn-mlops exec deploy/churn-api -- ls -l /app/artifacts/models
```

If needed, copy a known good model to alias using a one-off debug pod or a tiny helper job (optional for course).

---

## 2) API image rollback (K8s)

```bash
kubectl -n churn-mlops rollout history deployment/churn-api
kubectl -n churn-mlops rollout undo deployment/churn-api
```

---

## 3) Pause automation during incidents

```bash
kubectl -n churn-mlops patch cronjob churn-drift-daily -p '{"spec":{"suspend":true}}'
kubectl -n churn-mlops patch cronjob churn-retrain-weekly -p '{"spec":{"suspend":true}}'
```

Resume:

```bash
kubectl -n churn-mlops patch cronjob churn-drift-daily -p '{"spec":{"suspend":false}}'
kubectl -n churn-mlops patch cronjob churn-retrain-weekly -p '{"spec":{"suspend":false}}'
```

---

## 4) Minikube resilience note

Minikube is a learning target.
If the cluster is recreated, PVC data may be lost.
For classes:

* keep `artifacts/models` backed up locally
* rebuild images with a single version tag across ML + API
  EOF

````

---

## 13.3 Final checklist

```bash
cat << 'EOF' > docs/final-checklist.md
# Final Checklist — Production-Grade Churn MLOps

Use this before recording the final capstone video.

---

## Code & Quality

- [ ] `make lint` passes
- [ ] `make test` passes
- [ ] Imports formatted (ruff)
- [ ] Config contains `app.env` (dev/stage/prod)

---

## Data Pipeline

- [ ] Synthetic generator runs
- [ ] Raw validation passes
- [ ] Processed tables created
- [ ] Features + labels created
- [ ] Training dataset created

---

## Model Registry

- [ ] Timestamped model exists
- [ ] Metrics JSON exists
- [ ] `production_latest.joblib` exists

---

## Batch Scoring

- [ ] Batch output exists in `data/predictions/`
- [ ] Score proxy script can find latest file

---

## API

- [ ] API starts without missing modules
- [ ] `/health` OK
- [ ] `/ready` OK
- [ ] `/live` OK
- [ ] `/metrics` OK

---

## Containers

- [ ] ML + API images built with SAME version
- [ ] Images pushed (if using remote registry)

---

## Kubernetes

- [ ] Seed Job completes
- [ ] API Deployment stable
- [ ] Drift CronJob present
- [ ] Retrain CronJob present
- [ ] Port-forward demo works

---

## Student Experience

- [ ] Runbook is copy-paste ready
- [ ] One happy-path script works
- [ ] Troubleshooting steps validated
EOF
````

---

## 13.4 Helper scripts

### A) Local happy-path

```bash
cat << 'EOF' > scripts/happy_path_local.sh
#!/usr/bin/env bash
set -e

if [ ! -d .venv ]; then
  echo "❌ .venv not found. Create it first."
  exit 1
fi

source .venv/bin/activate

echo "✅ Lint"
make lint

echo "✅ Tests"
make test

echo "✅ Seed + train baseline"
./scripts/seed_model_local.sh

echo "✅ Batch score"
./scripts/batch_score.sh

echo "✅ Score proxy (non-fatal if missing latest alias)"
./scripts/score_proxy.sh || true

echo "🎉 Local happy path done"
EOF

chmod +x scripts/happy_path_local.sh
```

### B) K8s smoke

```bash
cat << 'EOF' > scripts/k8s_smoke.sh
#!/usr/bin/env bash
set -e

NS="${1:-churn-mlops}"

echo "🔎 Namespace: $NS"
kubectl get ns "$NS" >/dev/null

echo "🔎 PVC"
kubectl -n "$NS" get pvc || true

echo "🔎 ConfigMaps"
kubectl -n "$NS" get cm || true

echo "🔎 Jobs"
kubectl -n "$NS" get jobs || true

echo "🔎 CronJobs"
kubectl -n "$NS" get cronjobs || true

echo "🔎 Deployments"
kubectl -n "$NS" get deploy || true

echo "🔎 Pods"
kubectl -n "$NS" get pods || true

echo "✅ K8s smoke check done"
EOF

chmod +x scripts/k8s_smoke.sh
```

---

## 13.5 Quick verify

```bash
ls -l docs
ls -l scripts
```

---

# Where you are now (based on your logs)

You have already proven these in your environment:

* Seed Job can generate data, features, labels, train baseline, and produce:

  * `baseline_logreg_<timestamp>.joblib`
  * `production_latest.joblib`
* API is healthy and exposes:

  * `/health`, `/ready`, `/live`, `/metrics`
* Drift + retrain CronJobs exist in `churn-mlops`




