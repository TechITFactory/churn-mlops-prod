# Section 12: Monitoring & Retraining

## Goal

Monitor model performance and data drift, then trigger automated retraining when quality degrades or data distribution shifts.

---

## Monitoring Strategy

```
Production System
    ↓
Collect Metrics (Prometheus, logs, predictions)
    ↓
Detect Issues (drift, performance degradation)
    ↓
Alert / Trigger Retrain
    ↓
New Model → Promote → Deploy
```

---

## Types of Monitoring

### 1. **Data Drift**
- Feature distributions change over time
- Detected using PSI (Population Stability Index)

### 2. **Model Performance**
- Prediction accuracy degrades
- Monitored via actual outcomes (score proxy)

### 3. **System Health**
- API latency, error rate, throughput
- Monitored via Prometheus metrics

---

## Data Drift Detection

### File: `src/churn_mlops/monitoring/drift.py`

### PSI (Population Stability Index)

**Formula**:
```
PSI = Σ (actual_pct - expected_pct) * ln(actual_pct / expected_pct)
```

**Interpretation**:
- PSI < 0.1: No significant drift
- PSI 0.1-0.25: Moderate drift (warning)
- PSI > 0.25: Significant drift (action required)

### Implementation

```python
def _psi(expected: np.ndarray, actual: np.ndarray, buckets: int = 10) -> float:
    # Bin data into buckets based on expected distribution
    quantiles = np.linspace(0, 1, buckets + 1)
    edges = np.unique(np.quantile(expected, quantiles))
    
    def _bucket_counts(x):
        counts, _ = np.histogram(x, bins=edges)
        pct = counts / max(counts.sum(), 1)
        return np.clip(pct, 1e-6, 1.0)  # Avoid zeros
    
    e_pct = _bucket_counts(expected)
    a_pct = _bucket_counts(actual)
    
    return float(np.sum((a_pct - e_pct) * np.log(a_pct / e_pct)))
```

### Drift Report

```python
@dataclass
class DriftReport:
    psi_by_feature: Dict[str, float]
    overall_max_psi: float
    status: str  # OK / WARN / FAIL
```

---

## Drift Check Script

### File: `src/churn_mlops/monitoring/run_drift_check.py`

```python
def main():
    cfg = load_config()
    
    baseline = Path("data/features/training_dataset.csv")
    current = Path("data/features/user_features_daily.csv")
    
    feature_cols = [
        "active_days_7d",
        "watch_minutes_7d",
        "watch_minutes_30d",
        "quiz_attempts_7d",
        "days_since_last_activity",
    ]
    
    report = compute_drift(
        baseline_path=baseline,
        current_path=current,
        feature_cols=feature_cols,
        warn_psi=0.1,
        fail_psi=0.25,
    )
    
    # Write report
    out = Path("artifacts/metrics/data_drift_latest.json")
    out.write_text(json.dumps({
        "status": report.status,
        "overall_max_psi": report.overall_max_psi,
        "psi_by_feature": report.psi_by_feature,
    }, indent=2))
    
    # Exit with non-zero if drift detected (alerts CronJob)
    if report.status == "FAIL":
        raise SystemExit(2)
```

**Output**: `artifacts/metrics/data_drift_latest.json`

```json
{
  "status": "WARN",
  "overall_max_psi": 0.18,
  "psi_by_feature": {
    "active_days_7d": 0.05,
    "watch_minutes_7d": 0.18,
    "watch_minutes_30d": 0.12,
    "quiz_attempts_7d": 0.08,
    "days_since_last_activity": 0.15
  }
}
```

---

## Score Proxy (Actual Outcome Collection)

### File: `src/churn_mlops/monitoring/score_proxy.py`

**Purpose**: Collect actual churn outcomes to compare with predictions

### Implementation

```python
def compute_score_proxy():
    # 1. Load latest predictions
    predictions = pd.read_csv("data/predictions/churn_predictions_2025-01-15.csv")
    
    # 2. Load current activity (30 days later)
    current = pd.read_csv("data/features/user_features_daily.csv")
    current = current[current["as_of_date"] == "2025-02-14"]  # 30 days later
    
    # 3. Join predictions + current activity
    merged = predictions.merge(
        current[["user_id", "active_days_30d"]],
        on="user_id",
        how="left"
    )
    
    # 4. Compute actual churn (no activity in last 30 days)
    merged["actual_churn"] = (merged["active_days_30d"] == 0).astype(int)
    
    # 5. Evaluate predictions vs. actuals
    pr_auc = average_precision_score(merged["actual_churn"], merged["churn_risk"])
    roc_auc = roc_auc_score(merged["actual_churn"], merged["churn_risk"])
    
    return {
        "pr_auc": pr_auc,
        "roc_auc": roc_auc,
        "sample_size": len(merged),
    }
```

**Output**: `artifacts/metrics/score_proxy_latest.json`

```json
{
  "pr_auc": 0.62,
  "roc_auc": 0.72,
  "sample_size": 1850,
  "prediction_date": "2025-01-15",
  "evaluation_date": "2025-02-14"
}
```

---

## Monitoring CronJobs

### Drift Check (Daily)

**File**: `k8s/drift-cronjob.yaml`

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: churn-drift-daily
  namespace: churn-mlops
spec:
  schedule: "0 1 * * *"  # Daily at 1am UTC
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: drift
              image: techitfactory/churn-ml:0.1.2
              command: ["sh", "-c"]
              args:
                - |
                  set -e
                  python -m churn_mlops.monitoring.run_drift_check
```

**If drift detected** (exit code 2):
- CronJob status = Failed
- Alert sent (via Kubernetes events or webhook)
- Trigger retrain workflow

---

### Retrain (Weekly or On-Demand)

**File**: `k8s/retrain-cronjob.yaml`

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: churn-retrain-weekly
  namespace: churn-mlops
spec:
  schedule: "0 3 * * 0"  # Weekly, Sunday 3am UTC
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: retrain
              image: techitfactory/churn-ml:0.1.2
              command: ["sh", "-c"]
              args:
                - |
                  set -e
                  # Generate fresh data
                  python -m churn_mlops.data.generate_synthetic
                  python -m churn_mlops.data.prepare_dataset
                  python -m churn_mlops.features.build_features
                  python -m churn_mlops.training.build_labels
                  python -m churn_mlops.training.build_training_set
                  
                  # Train candidate model
                  python -m churn_mlops.training.train_candidate
                  
                  # Promote if better than current production
                  python -m churn_mlops.training.promote_model
```

**Trigger manually**:
```bash
kubectl -n churn-mlops create job --from=cronjob/churn-retrain-weekly retrain-manual-$(date +%s)
```

---

## API Metrics (Prometheus)

### Metrics Exposed by API

**File**: `src/churn_mlops/monitoring/api_metrics.py`

1. **churn_api_requests_total**: Request count by method/path/status
2. **churn_api_request_latency_seconds**: Latency histogram by method/path
3. **churn_api_predictions_total**: Total predictions served

### Prometheus Queries

```promql
# Request rate (per second)
rate(churn_api_requests_total[5m])

# Error rate
rate(churn_api_requests_total{status=~"5.."}[5m])

# P95 latency
histogram_quantile(0.95, rate(churn_api_request_latency_seconds_bucket[5m]))

# Prediction throughput
rate(churn_api_predictions_total[5m])
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "Churn API Metrics",
    "panels": [
      {
        "title": "Request Rate",
        "targets": [{"expr": "rate(churn_api_requests_total[5m])"}]
      },
      {
        "title": "Error Rate",
        "targets": [{"expr": "rate(churn_api_requests_total{status=~\"5..\"}[5m])"}]
      },
      {
        "title": "P95 Latency",
        "targets": [{"expr": "histogram_quantile(0.95, rate(churn_api_request_latency_seconds_bucket[5m]))"}]
      }
    ]
  }
}
```

---

## Alerting Rules

### Prometheus AlertManager

```yaml
groups:
  - name: churn_api_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(churn_api_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate on Churn API"
          description: "Error rate is {{ $value }} per second"
      
      - alert: HighLatency
        expr: histogram_quantile(0.95, rate(churn_api_request_latency_seconds_bucket[5m])) > 1.0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High P95 latency on Churn API"
          description: "P95 latency is {{ $value }}s"
      
      - alert: DataDriftDetected
        expr: kube_job_status_failed{job_name=~"churn-drift-.*"} > 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Data drift detected"
          description: "Drift check job failed, consider retraining"
```

---

## Retraining Decision Logic

### When to Retrain?

**Scheduled**:
- Weekly/monthly (CronJob)
- Keeps model fresh even if no drift

**Event-driven**:
1. **Data drift detected** (PSI > 0.25)
2. **Performance degradation** (score proxy PR-AUC drops > 10%)
3. **New data available** (e.g., 30 days accumulated)

### Automated Retrain Workflow

```bash
#!/bin/bash
# scripts/auto_retrain.sh

# 1. Check drift
python -m churn_mlops.monitoring.run_drift_check
DRIFT_STATUS=$?

# 2. Check score proxy
python -m churn_mlops.monitoring.run_score_proxy
SCORE_PROXY=$(jq '.pr_auc' artifacts/metrics/score_proxy_latest.json)
PRODUCTION_SCORE=$(jq '.metrics.pr_auc' artifacts/metrics/production_latest.json)

# 3. Decide if retrain needed
if [ $DRIFT_STATUS -ne 0 ] || [ $(echo "$SCORE_PROXY < $PRODUCTION_SCORE - 0.1" | bc) -eq 1 ]; then
  echo "Retraining triggered"
  
  # 4. Train candidate
  python -m churn_mlops.training.train_candidate
  
  # 5. Promote if better
  python -m churn_mlops.training.promote_model
  
  # 6. Restart API
  kubectl -n churn-mlops rollout restart deployment/churn-api
fi
```

---

## Files Involved

| File | Purpose |
|------|---------|
| `src/churn_mlops/monitoring/drift.py` | PSI drift calculation |
| `src/churn_mlops/monitoring/run_drift_check.py` | Drift check runner |
| `src/churn_mlops/monitoring/score_proxy.py` | Actual outcome collection |
| `src/churn_mlops/monitoring/run_score_proxy.py` | Score proxy runner |
| `src/churn_mlops/monitoring/api_metrics.py` | Prometheus metrics |
| `k8s/drift-cronjob.yaml` | Drift check CronJob |
| `k8s/retrain-cronjob.yaml` | Retrain CronJob |
| `artifacts/metrics/data_drift_latest.json` | Drift report |
| `artifacts/metrics/score_proxy_latest.json` | Performance report |

---

## Run Commands

```bash
# Check drift locally
python -m churn_mlops.monitoring.run_drift_check

# Run score proxy
python -m churn_mlops.monitoring.run_score_proxy

# Trigger retrain in K8s
kubectl -n churn-mlops create job --from=cronjob/churn-retrain-weekly retrain-now

# Check CronJob status
kubectl -n churn-mlops get cronjobs
kubectl -n churn-mlops get jobs
```

---

## Troubleshooting

**Issue**: Drift check always fails
- **Cause**: PSI threshold too low or feature columns mismatch
- **Fix**: Adjust `fail_psi` threshold or verify feature names

**Issue**: Score proxy returns NaN
- **Cause**: No matching users (prediction date + 30d not in current data)
- **Fix**: Ensure data spans correct time range

**Issue**: Retrain CronJob never triggers
- **Cause**: Cron schedule wrong or CronJob suspended
- **Fix**: Check schedule syntax, ensure `spec.suspend: false`

**Issue**: API not updated after retrain
- **Cause**: Deployment not restarted
- **Fix**: `kubectl rollout restart deployment/churn-api`

---

## Best Practices

1. **Monitor drift continuously**: Daily checks catch issues early
2. **Automate retraining**: Scheduled + event-driven
3. **Validate before promote**: Compare candidate vs. production metrics
4. **Gradual rollout**: A/B test new model before full deployment
5. **Keep history**: Store drift reports and score proxy results

---

## Next Steps

- **[Section 13](section-13-capstone-runbook.md)**: End-to-end runbook and troubleshooting
- **[Section 09](section-09-realtime-api.md)**: Review API metrics
- **[Section 11](section-11-containerization-deploy.md)**: Review Kubernetes deployment

---

## Key Takeaways

1. **Data drift** is detected using PSI on feature distributions
2. **Score proxy** collects actual outcomes to monitor model performance
3. **Prometheus metrics** track API health (latency, errors, throughput)
4. **Automated retraining** triggers on drift or schedule
5. **CronJobs** enable scheduled monitoring and retraining in Kubernetes
