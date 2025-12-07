# Section 07: Model Registry

## Goal

Manage model versions, compare performance, and promote the best model to production using a simple file-based registry.

---

## Model Registry Concept

**Problem**: Multiple models trained over time (baseline, candidates, experiments)
- How do we track which model is "production"?
- How do we compare performance?
- How do we rollback if a new model fails?

**Solution**: Model registry with versioned artifacts + promotion logic

---

## File-Based Registry Structure

```
artifacts/
├── models/
│   ├── baseline_logreg_20250101T103045Z.joblib      # Timestamped model
│   ├── baseline_logreg_20250105T140022Z.joblib      # Another version
│   ├── candidate_logreg_20250110T090015Z.joblib     # Candidate model
│   └── production_latest.joblib                     # Production alias (symlink/copy)
└── metrics/
    ├── baseline_logreg_20250101T103045Z.json        # Corresponding metrics
    ├── baseline_logreg_20250105T140022Z.json
    ├── candidate_logreg_20250110T090015Z.json
    └── production_latest.json                       # Production metrics
```

**Key Design**:
- **Timestamped artifacts**: Never overwrite, always append
- **Production alias**: Stable name (`production_latest.joblib`) that APIs/batch jobs load
- **Metrics pairing**: Each `.joblib` has a matching `.json` with performance metrics

---

## File: `src/churn_mlops/training/promote_model.py`

### Promotion Logic

```python
def promote_model():
    # 1. Find all candidates (models with metrics)
    candidates = _find_candidates(models_dir, metrics_dir)
    
    # 2. Score each candidate (prefer PR-AUC)
    for c in candidates:
        metrics = json.loads(c.metrics_path.read_text())
        c.score = metrics.get("pr_auc", metrics.get("roc_auc", -1.0))
    
    # 3. Select best
    best = sorted(candidates, key=lambda c: c.score, reverse=True)[0]
    
    # 4. Copy to production alias
    shutil.copy2(best.model_path, models_dir / "production_latest.joblib")
    shutil.copy2(best.metrics_path, metrics_dir / "production_latest.json")
    
    logger.info(f"Promoted {best.model_path.name} (PR-AUC={best.score:.4f})")
```

### Finding Candidates

```python
def _find_candidates(models_dir, metrics_dir):
    out = []
    
    for mp in sorted(metrics_dir.glob("*.json")):
        stem = mp.stem  # e.g., "baseline_logreg_20250101T103045Z"
        model_guess = models_dir / f"{stem}.joblib"
        
        if not model_guess.exists():
            continue  # Metrics without model (skip)
        
        m = json.loads(mp.read_text())
        metric_name, score = _score_from_metrics(m)
        
        out.append(Candidate(
            model_path=model_guess,
            metrics_path=mp,
            score=score,
            metric_name=metric_name,
        ))
    
    return out
```

---

## Metric Selection

```python
def _score_from_metrics(m):
    # Preference order for imbalanced classification
    for key in ("pr_auc", "average_precision", "roc_auc", "f1", "accuracy"):
        if key in m and isinstance(m[key], (int, float)):
            return key, float(m[key])
    return "unknown", -1.0
```

**Why PR-AUC first?**
- Best metric for imbalanced churn data
- Captures precision-recall trade-off
- More relevant than accuracy for business decisions

---

## Production Alias Pattern

**Why not just use latest timestamped model?**
- APIs/batch jobs would need to find latest model (complex logic)
- Rollback requires renaming files
- Version pinning is harder

**With alias**:
```python
# API always loads this stable name
model = joblib.load("artifacts/models/production_latest.joblib")
```

**Benefits**:
- API code doesn't change when model updates
- Promotion = atomic copy operation
- Rollback = copy old model to alias
- Clear "source of truth" for production

---

## Versioning Strategy

### Timestamp Format

```python
stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
# Example: 20250101T103045Z
```

**Why this format?**
- Sortable lexicographically
- Unambiguous (UTC timezone)
- ISO 8601 compatible
- File-system safe (no colons or spaces)

### Naming Convention

```
{model_type}_{timestamp}.{ext}
```

**Examples**:
- `baseline_logreg_20250101T103045Z.joblib`
- `xgboost_20250110T140022Z.joblib`
- `ensemble_20250115T090000Z.joblib`

---

## Files Involved

| File | Purpose |
|------|---------|
| `src/churn_mlops/training/promote_model.py` | Promotion logic |
| `scripts/promote_model.sh` | Shell wrapper |
| `artifacts/models/*.joblib` | Model versions |
| `artifacts/metrics/*.json` | Metrics versions |
| `artifacts/models/production_latest.joblib` | Production alias |
| `artifacts/metrics/production_latest.json` | Production metrics |

---

## Run Commands

```bash
# Promote best model to production
python -m churn_mlops.training.promote_model
./scripts/promote_model.sh

# Check production model
ls -lh artifacts/models/production_latest.joblib

# View production metrics
cat artifacts/metrics/production_latest.json | jq
```

---

## Verify Steps

```bash
# 1. List all models
ls -lh artifacts/models/*.joblib

# 2. Check which model is promoted
python -c "
import json
metrics = json.load(open('artifacts/metrics/production_latest.json'))
print(f'Promoted model: {metrics[\"artifact\"]}')
print(f'PR-AUC: {metrics[\"metrics\"][\"pr_auc\"]:.4f}')
print(f'ROC-AUC: {metrics[\"metrics\"][\"roc_auc\"]:.4f}')
"

# 3. Load production model (simulate API)
python -c "
import joblib
model_blob = joblib.load('artifacts/models/production_latest.joblib')
print(f'Model loaded: {type(model_blob[\"model\"]).__name__}')
print(f'Cat cols: {model_blob[\"cat_cols\"]}')
print(f'Num cols: {len(model_blob[\"num_cols\"])} features')
"
```

---

## Model Comparison

```bash
# Compare all models
python -c "
import json
from pathlib import Path

metrics_dir = Path('artifacts/metrics')
models = []

for p in sorted(metrics_dir.glob('baseline_*.json')):
    m = json.loads(p.read_text())
    models.append({
        'artifact': m['artifact'],
        'pr_auc': m['metrics']['pr_auc'],
        'roc_auc': m['metrics']['roc_auc'],
        'train_rows': m['train_rows'],
    })

for m in models:
    print(f'{m[\"artifact\"]:<40} PR-AUC={m[\"pr_auc\"]:.4f} ROC-AUC={m[\"roc_auc\"]:.4f}')
"
```

---

## Rollback Procedure

### Manual Rollback

```bash
# 1. Identify previous good model
ls -lt artifacts/models/baseline_*.joblib

# 2. Copy to production alias
cp artifacts/models/baseline_logreg_20250101T103045Z.joblib \
   artifacts/models/production_latest.joblib

cp artifacts/metrics/baseline_logreg_20250101T103045Z.json \
   artifacts/metrics/production_latest.json

# 3. Restart API (if running)
kubectl -n churn-mlops rollout restart deployment/churn-api
```

### Automated Rollback (Future)

```python
def rollback_model(target_artifact_name):
    models_dir = Path("artifacts/models")
    metrics_dir = Path("artifacts/metrics")
    
    target_model = models_dir / target_artifact_name
    target_metrics = metrics_dir / target_artifact_name.replace(".joblib", ".json")
    
    if not target_model.exists():
        raise FileNotFoundError(f"Model not found: {target_artifact_name}")
    
    shutil.copy2(target_model, models_dir / "production_latest.joblib")
    shutil.copy2(target_metrics, metrics_dir / "production_latest.json")
    
    logger.info(f"Rolled back to {target_artifact_name}")
```

---

## Advanced: Model Metadata

### Enhanced Metrics File

```json
{
  "model_type": "logistic_regression",
  "artifact": "baseline_logreg_20250101T103045Z.joblib",
  "trained_at": "2025-01-01T10:30:45Z",
  "trained_by": "github-actions",
  "git_commit": "a3f9c21",
  "data_version": "2025-01-01",
  "train_rows": 160000,
  "test_rows": 40000,
  "churn_rate_train": 0.35,
  "churn_rate_test": 0.34,
  "metrics": {
    "pr_auc": 0.68,
    "roc_auc": 0.75,
    "precision@50": 0.82,
    "recall@50": 0.45
  },
  "hyperparameters": {
    "C": 1.0,
    "max_iter": 2000,
    "class_weight": "balanced"
  }
}
```

---

## Production Readiness Checklist

Before promoting a model:

- [ ] **Metrics exist**: `.json` file with PR-AUC, ROC-AUC
- [ ] **Performance threshold**: PR-AUC > 0.60 (adjust for your domain)
- [ ] **No degradation**: New model >= current production model
- [ ] **Test set representative**: Recent data, not stale
- [ ] **Model serializable**: Can load/predict without errors
- [ ] **Feature schema matches**: Inference pipeline expects same features

---

## Integration with CI/CD

```yaml
# .github/workflows/train.yml
name: Train and Promote

on:
  schedule:
    - cron: "0 2 * * 0"  # Weekly, Sunday 2am UTC

jobs:
  train:
    runs-on: ubuntu-latest
    steps:
      - name: Train candidate
        run: ./scripts/train_candidate.sh
      
      - name: Evaluate candidate
        id: eval
        run: |
          PR_AUC=$(jq '.metrics.pr_auc' artifacts/metrics/candidate_*.json)
          echo "pr_auc=$PR_AUC" >> $GITHUB_OUTPUT
      
      - name: Promote if better
        if: steps.eval.outputs.pr_auc > 0.65
        run: ./scripts/promote_model.sh
      
      - name: Deploy to K8s
        if: steps.eval.outputs.pr_auc > 0.65
        run: kubectl -n churn-mlops rollout restart deployment/churn-api
```

---

## Troubleshooting

**Issue**: No candidates found for promotion
- **Cause**: No metrics files or model files missing
- **Fix**: Ensure training writes both `.joblib` and `.json` with matching names

**Issue**: Promotion selects wrong model
- **Cause**: Metric preference order doesn't match your goal
- **Fix**: Customize `_score_from_metrics()` logic

**Issue**: API fails after promotion
- **Cause**: Model format mismatch or missing dependencies
- **Fix**: Test model loading in isolation before promotion

**Issue**: `production_latest.joblib` doesn't exist
- **Cause**: Never ran promotion or seed job
- **Fix**: Run `./scripts/promote_model.sh` at least once

---

## Best Practices

1. **Never delete old models**: Disk is cheap, rollback is critical
2. **Pair metrics with models**: Same filename stem for easy lookup
3. **Automate promotion**: CI/CD pipeline ensures consistency
4. **Version everything**: Code, data, models, metrics
5. **Test before promote**: Validate model loads and predicts

---

## Next Steps

- **[Section 08](section-08-batch-scoring.md)**: Use promoted model for batch predictions
- **[Section 09](section-09-realtime-api.md)**: Serve production model via API
- **[Section 06](section-06-training-pipeline.md)**: Review training pipeline

---

## Key Takeaways

1. **File-based registry** is simple and effective for small-scale MLOps
2. **Production alias** decouples API from specific model versions
3. **Timestamped artifacts** enable safe experimentation and rollback
4. **Promotion logic** automates "best model" selection based on metrics
5. **Metrics pairing** (`.joblib` + `.json`) ensures traceability
