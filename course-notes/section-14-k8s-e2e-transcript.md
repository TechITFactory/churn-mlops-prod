# Section 14: Kubernetes End-to-End (Transcript Style)

## What You’ll Learn
- How the churn ML system is deployed on Kubernetes (EKS) using plain manifests.
- How data is generated, models are trained/promoted, and artifacts are stored on a PVC.
- How the API, batch scoring, drift, and retrain CronJobs run—and how to trigger them manually.
- How to validate success at each step.

## Narrative Overview (Udemy-Style Walkthrough)
1) **Set the stage**: We already have container images published (`techitfactory/churn-ml:dec22`, `techitfactory/churn-api:dec22`). The goal is to run the full churn pipeline on EKS with persistent storage and scheduled automation.
2) **Provision and configure**: Terraform spins up the EKS cluster with the EBS CSI add-on (for dynamic volumes). We then point `kubectl` at the cluster and set the namespace `churn-mlops`.
3) **Lay down the basics**: Apply namespace, PVC (gp2), and configmap. The PVC backs all jobs and the API so artifacts are shared.
4) **Generate data + baseline model**: Run the seed job. It creates synthetic data, builds features, trains the baseline model, and writes `production_latest.joblib` plus metrics into the PVC.
5) **Bring up the API**: Deploy the FastAPI service that serves predictions using the `production_latest.joblib` model from the PVC.
6) **Automate with CronJobs**: Deploy three CronJobs—batch scoring, data drift check, and weekly retraining—so the system keeps producing predictions, monitoring drift, and refreshing the model.
7) **Validate end-to-end**: Manually trigger each CronJob as an ad-hoc Job, wait for completion, inspect logs and metrics files, and (optionally) restart the API to pick up a freshly trained model.

## Step-by-Step Commands (Plain Manifests on EKS)
### 0) Pre-reqs
- EKS cluster via Terraform.
- kubectl configured: `aws eks --region us-east-1 update-kubeconfig --name churn-mlops`
- Namespace: `churn-mlops`

### 1) Core resources
```bash
kubectl apply -f k8s/plain/namespace.yaml
kubectl apply -f k8s/plain/pvc.yaml
kubectl apply -f k8s/plain/configmap.yaml
```
Check PVC:
```bash
kubectl -n churn-mlops get pvc
```

### 2) Seed: data + baseline model
```bash
kubectl apply -f k8s/plain/seed-model-job.yaml
kubectl -n churn-mlops wait --for=condition=complete job/churn-seed-model --timeout=900s
```
Inspect artifacts on the job pod (PVC mount):
```bash
kubectl -n churn-mlops exec job/churn-seed-model -- ls -l /app/artifacts/models
kubectl -n churn-mlops exec job/churn-seed-model -- ls -l /app/artifacts/metrics
```
Expected: `baseline_logreg_*.joblib` and `production_latest.joblib` plus metric JSONs.

### 3) Deploy API
```bash
kubectl apply -f k8s/plain/api-deployment.yaml
kubectl apply -f k8s/plain/api-service.yaml
kubectl -n churn-mlops wait --for=condition=ready pod -l app=churn-api --timeout=180s
kubectl -n churn-mlops port-forward svc/churn-api 8000:8000 &
curl http://localhost:8000/ready
```
The API reads the model from the PVC and exposes `/ready`, `/health`, and `/metrics`.

### 4) Deploy automation (CronJobs)
```bash
kubectl apply -f k8s/batch-cronjob.yaml
kubectl apply -f k8s/drift-cronjob.yaml
kubectl apply -f k8s/retrain-cronjob.yaml
```
What they do:
- **churn-batch-score**: Scores latest features to produce batch predictions.
- **churn-drift-daily**: Checks data drift; exits non-zero if drift detected (alert condition).
- **churn-retrain-weekly**: Regenerates data/features, retrains, and updates the production alias.

### 5) Manual end-to-end validation
Run each CronJob as an on-demand Job, wait, and inspect outputs.
```bash
# Batch score
kubectl -n churn-mlops create job --from=cronjob/churn-batch-score churn-batch-manual-$(date +%s)
kubectl -n churn-mlops wait --for=condition=complete job/churn-batch-manual-* --timeout=900s
kubectl -n churn-mlops logs -l job-name=churn-batch-manual-* --tail=200

# Drift check
kubectl -n churn-mlops create job --from=cronjob/churn-drift-daily churn-drift-manual-$(date +%s)
kubectl -n churn-mlops wait --for=condition=complete job/churn-drift-manual-* --timeout=600s
kubectl -n churn-mlops logs -l job-name=churn-drift-manual-* --tail=200
kubectl -n churn-mlops exec deploy/churn-api -- cat /app/artifacts/metrics/data_drift_latest.json

# Retrain
kubectl -n churn-mlops create job --from=cronjob/churn-retrain-weekly churn-retrain-manual-$(date +%s)
kubectl -n churn-mlops wait --for=condition=complete job/churn-retrain-manual-* --timeout=1200s
kubectl -n churn-mlops logs -l job-name=churn-retrain-manual-* --tail=200
kubectl -n churn-mlops exec deploy/churn-api -- cat /app/artifacts/metrics/production_latest.json
```
If a new model is produced, reload the API:
```bash
kubectl -n churn-mlops rollout restart deployment/churn-api
kubectl -n churn-mlops rollout status deployment/churn-api --timeout=180s
```

### 6) Results to look for
- PVC: `STATUS=Bound` on `gp2`, created by the EBS CSI driver.
- Seed job: Model artifacts present; job completed without errors.
- API: `/ready` returns 200; `/metrics` exposes Prometheus metrics.
- Batch job: Prediction CSVs written under `/app/data/predictions` on the PVC; logs show counts and write paths.
- Drift job: `data_drift_latest.json` updated; non-zero exit if drift detected.
- Retrain job: `production_latest.joblib` updated and metric JSON refreshed.

### 7) Why this flow matters
- **Deterministic storage**: Single PVC shared across jobs and API, so artifacts are consistent.
- **Separation of concerns**: Seed (data/model creation), API (serving), CronJobs (ops automation).
- **Cloud-native primitives**: EBS CSI for volumes, CronJobs for scheduling, Services for access.
- **Manual triggers for confidence**: On-demand jobs let you validate before trusting schedules.

## Quick Recap (for learners)
- Provision EKS + storage → Seed baseline → Deploy API → Add CronJobs → Manually validate → Reload API on new model.
- Inspect logs and artifact files after each step to prove correctness.
- Keep monitoring for later (Prometheus/Grafana), but the operational loop is already complete.

## TODO (Student Exercise): Auto-trigger Retrain on Drift
If you want drift to automatically launch retraining:
1) Add a ServiceAccount + Role/RoleBinding in namespace `churn-mlops` that allows `create` on Jobs and `get` on CronJobs.
2) Wrap the drift CronJob command: run `python -m churn_mlops.monitoring.run_drift_check`; if it exits 2 (status FAIL), call `kubectl -n churn-mlops create job --from=cronjob/churn-retrain-weekly churn-retrain-drift-$(date +%s)`; then exit with the original status.
3) Ensure the drift job image has `kubectl` (or swap to a kubectl-enabled image) and use the new ServiceAccount. This is left as a deliberate exercise for students to wire and test.
