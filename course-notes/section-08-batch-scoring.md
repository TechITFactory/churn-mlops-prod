# Section 08: Batch Scoring

## Goal

Generate churn predictions for all active users at once, producing a prioritized risk list for business intervention.

---

## Batch Scoring Concept

**Purpose**: Score entire user base periodically (daily/weekly) to:
1. Identify high-risk users for retention campaigns
2. Monitor churn trends across cohorts
3. Feed downstream systems (CRM, email automation)

**vs. Real-time API**:
- **Batch**: Pre-compute predictions for all users → CSV output
- **Real-time**: On-demand prediction for single user → JSON response

---

## File: `src/churn_mlops/inference/batch_score.py`

### Batch Scoring Pipeline

```
user_features_daily.csv  (all users, all dates)
    ↓
Select as_of_date (default: latest)
    ↓
Load production_latest.joblib
    ↓
Predict churn_risk for all users on that date
    ↓
Rank users by risk (descending)
    ↓
Output: churn_predictions_<date>.csv
```

---

## Implementation Details

### 1. Load Features

```python
def _read_features(features_dir):
    path = Path(features_dir) / "user_features_daily.csv"
    return pd.read_csv(path)
```

### 2. Select Scoring Date

```python
def _pick_as_of_date(df, as_of_date):
    if as_of_date:
        # User-specified date
        target = pd.to_datetime(as_of_date).date()
        if target not in df["as_of_date"].unique():
            raise ValueError(f"Date {as_of_date} not found in features")
        return target.isoformat()
    
    # Default: latest date in features
    latest = df["as_of_date"].max().date()
    return latest.isoformat()
```

### 3. Load Production Model

```python
def _load_production_model(models_dir):
    prod_path = Path(models_dir) / "production_latest.joblib"
    
    if not prod_path.exists():
        raise FileNotFoundError(
            f"Missing production model: {prod_path}. "
            f"Run ./scripts/promote_model.sh first."
        )
    
    blob = joblib.load(prod_path)
    
    # Handle dict format {"model": pipeline, ...} or raw pipeline
    if isinstance(blob, dict) and "model" in blob:
        return blob["model"], blob
    return blob, {"model": blob}
```

### 4. Prepare Scoring Frame

```python
def _prepare_scoring_frame(features, as_of_date):
    f = features.copy()
    f["as_of_date"] = pd.to_datetime(f["as_of_date"]).dt.date
    
    # Filter to single date
    day_df = f[f["as_of_date"] == pd.to_datetime(as_of_date).date()]
    
    if day_df.empty:
        raise ValueError(f"No features found for {as_of_date}")
    
    return day_df
```

### 5. Split Features from Metadata

```python
def _split_X(day_df):
    # Keep metadata for output
    meta_cols = ["user_id", "as_of_date", "plan", "is_paid", "country",
                 "marketing_source", "days_since_signup", "days_since_last_activity"]
    meta = day_df[[c for c in meta_cols if c in day_df.columns]]
    
    # Remove non-features
    drop_cols = {"user_id", "as_of_date", "signup_date", "churn_label"}
    X = day_df.drop(columns=[c for c in drop_cols if c in day_df.columns])
    
    return X, meta
```

### 6. Predict & Rank

```python
def _write_predictions(meta, proba, predictions_dir, as_of_date, top_k):
    out = meta.copy()
    out["churn_risk"] = proba.astype(float)
    
    # Rank by risk (highest first)
    out = out.sort_values("churn_risk", ascending=False).reset_index(drop=True)
    out["risk_rank"] = out.index + 1
    
    # Write full predictions
    out_path = Path(predictions_dir) / f"churn_predictions_{as_of_date}.csv"
    out.to_csv(out_path, index=False)
    
    # Write top-K preview (for demos, reports)
    if top_k > 0:
        preview = out.head(top_k)
        preview_path = Path(predictions_dir) / f"churn_top_{top_k}_{as_of_date}.csv"
        preview.to_csv(preview_path, index=False)
    
    return out_path
```

---

## Output Format

**File**: `data/predictions/churn_predictions_2025-01-15.csv`

```csv
user_id,as_of_date,plan,is_paid,country,marketing_source,days_since_signup,days_since_last_activity,churn_risk,risk_rank
1523,2025-01-15,paid,1,US,organic,45,14,0.95,1
891,2025-01-15,free,0,IN,referral,30,21,0.92,2
2104,2025-01-15,paid,1,UK,ads,60,7,0.88,3
...
```

**Top-K Preview**: `data/predictions/churn_top_50_2025-01-15.csv`
- Same format, only top 50 rows
- Quick view for business users

---

## Files Involved

| File | Purpose |
|------|---------|
| `src/churn_mlops/inference/batch_score.py` | Batch scoring logic |
| `scripts/batch_score.sh` | Shell wrapper |
| `scripts/batch_score_latest.sh` | Score latest date (convenience) |
| `scripts/ensure_latest_predictions.sh` | Ensure predictions exist |
| `data/features/user_features_daily.csv` | Input features |
| `artifacts/models/production_latest.joblib` | Production model |
| `data/predictions/churn_predictions_<date>.csv` | Full output |
| `data/predictions/churn_top_50_<date>.csv` | Top-K preview |

---

## Run Commands

```bash
# Score latest date
python -m churn_mlops.inference.batch_score
./scripts/batch_score.sh

# Score specific date
python -m churn_mlops.inference.batch_score --as-of-date 2025-01-10

# Score with custom top-K
python -m churn_mlops.inference.batch_score --top-k 100

# Using convenience script
./scripts/batch_score_latest.sh
```

---

## Verify Steps

```bash
# 1. Check output exists
ls -lh data/predictions/

# 2. Inspect predictions
head -n 10 data/predictions/churn_predictions_*.csv

# 3. Count high-risk users (churn_risk > 0.7)
python -c "
import pandas as pd
import glob

latest = sorted(glob.glob('data/predictions/churn_predictions_*.csv'))[-1]
df = pd.read_csv(latest)

print(f'Total users: {len(df)}')
print(f'High risk (>0.7): {(df[\"churn_risk\"] > 0.7).sum()}')
print(f'Medium risk (0.5-0.7): {((df[\"churn_risk\"] > 0.5) & (df[\"churn_risk\"] <= 0.7)).sum()}')
print(f'Low risk (<0.5): {(df[\"churn_risk\"] <= 0.5).sum()}')
print()
print('Top 5 high-risk users:')
print(df[['user_id', 'plan', 'days_since_last_activity', 'churn_risk']].head())
"

# 4. Compare to previous run (if exists)
python -c "
import pandas as pd
import glob

files = sorted(glob.glob('data/predictions/churn_predictions_*.csv'))
if len(files) >= 2:
    prev = pd.read_csv(files[-2])
    curr = pd.read_csv(files[-1])
    
    print(f'Previous: {len(prev)} users, avg risk {prev[\"churn_risk\"].mean():.4f}')
    print(f'Current:  {len(curr)} users, avg risk {curr[\"churn_risk\"].mean():.4f}')
"
```

---

## Business Use Cases

### 1. **Retention Campaigns**

```sql
-- Pseudo-SQL: Select high-risk paid users for retention offer
SELECT user_id, email, churn_risk
FROM churn_predictions
JOIN users USING (user_id)
WHERE churn_risk > 0.75
  AND is_paid = 1
ORDER BY churn_risk DESC
LIMIT 100;
```

### 2. **Cohort Analysis**

```python
import pandas as pd

df = pd.read_csv("data/predictions/churn_predictions_2025-01-15.csv")

# Churn risk by plan
print(df.groupby("plan")["churn_risk"].mean())

# Churn risk by country
print(df.groupby("country")["churn_risk"].mean())

# Churn risk by signup cohort
df["cohort"] = pd.cut(df["days_since_signup"], bins=[0, 30, 90, 180, 365, 9999],
                      labels=["0-30d", "30-90d", "90-180d", "180-365d", "365d+"])
print(df.groupby("cohort")["churn_risk"].mean())
```

### 3. **A/B Test Randomization**

```python
# Stratified sampling: Half get retention offer, half control
import pandas as pd

df = pd.read_csv("data/predictions/churn_predictions_2025-01-15.csv")
high_risk = df[df["churn_risk"] > 0.7]

# Random 50/50 split
high_risk["test_group"] = high_risk["user_id"].apply(lambda x: "treatment" if x % 2 == 0 else "control")

treatment = high_risk[high_risk["test_group"] == "treatment"]
print(f"Treatment group: {len(treatment)} users")
```

---

## Scheduled Batch Scoring

### Daily CronJob (Kubernetes)

**File**: `k8s/batch-cronjob.yaml`

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: churn-batch-score
  namespace: churn-mlops
spec:
  schedule: "0 3 * * *"  # Daily at 3am UTC
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: batch-score
              image: techitfactory/churn-ml:0.1.2
              command: ["sh", "-c"]
              args:
                - |
                  set -e
                  python -m churn_mlops.inference.batch_score
```

### Local Cron (Development)

```bash
# Edit crontab
crontab -e

# Add line (daily at 3am)
0 3 * * * cd /path/to/repo && ./scripts/batch_score_latest.sh
```

---

## Performance Optimization

### Scaling to Large User Bases

**Current**: ~2000 users score in < 10 seconds

**For 1M+ users**:
1. **Batch in chunks**:
   ```python
   chunk_size = 10000
   for i in range(0, len(X), chunk_size):
       chunk = X.iloc[i:i+chunk_size]
       proba = model.predict_proba(chunk)[:, 1]
   ```

2. **Use Dask or Spark**:
   ```python
   import dask.dataframe as dd
   ddf = dd.read_csv("user_features_daily.csv")
   # Parallel scoring across partitions
   ```

3. **Feature caching**:
   - Pre-compute features weekly
   - Only update deltas daily

---

## Troubleshooting

**Issue**: `FileNotFoundError: production_latest.joblib`
- **Cause**: No model promoted yet
- **Fix**: Run `./scripts/promote_model.sh` first

**Issue**: Predictions have NaN churn_risk
- **Cause**: Model fails on some rows (missing features, type mismatch)
- **Fix**: Inspect failing rows, ensure feature schema matches training

**Issue**: All predictions same value (e.g., 0.5)
- **Cause**: Model not trained or features all zeros
- **Fix**: Check model metrics, inspect features for variance

**Issue**: Batch scoring takes > 5 minutes
- **Cause**: Too many users or complex model
- **Fix**: Chunk scoring or optimize model (reduce features, simpler algorithm)

**Issue**: Date not found in features
- **Cause**: Features not built for requested date
- **Fix**: Run `./scripts/build_features.sh` to refresh features

---

## Integration with Downstream Systems

### Export to Database

```python
import pandas as pd
from sqlalchemy import create_engine

df = pd.read_csv("data/predictions/churn_predictions_2025-01-15.csv")

engine = create_engine("postgresql://user:pass@host/db")
df.to_sql("churn_predictions", engine, if_exists="replace", index=False)
```

### Export to S3

```python
import boto3

s3 = boto3.client("s3")
s3.upload_file(
    "data/predictions/churn_predictions_2025-01-15.csv",
    "my-bucket",
    "churn/predictions/2025-01-15.csv"
)
```

### Trigger Alerts

```python
import smtplib

df = pd.read_csv("data/predictions/churn_predictions_2025-01-15.csv")
critical = df[df["churn_risk"] > 0.9]

if len(critical) > 10:
    # Send alert email
    msg = f"ALERT: {len(critical)} users with churn risk > 0.9"
    # ... send via SMTP
```

---

## Next Steps

- **[Section 09](section-09-realtime-api.md)**: Real-time prediction API
- **[Section 12](section-12-monitoring-retrain.md)**: Monitor prediction drift
- **[Section 07](section-07-model-registry.md)**: Review model registry

---

## Key Takeaways

1. **Batch scoring** generates predictions for entire user base at once
2. **Risk ranking** enables prioritized interventions (top-K users)
3. **Top-K preview** provides quick view for business stakeholders
4. **Scheduled scoring** (CronJob) ensures fresh predictions daily/weekly
5. **Output CSV** integrates easily with downstream systems (CRM, BI tools)
