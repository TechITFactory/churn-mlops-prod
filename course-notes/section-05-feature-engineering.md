# Section 05: Feature Engineering

## Goal

Transform raw user_daily data into ML-ready features using rolling windows, temporal aggregations, and engagement metrics.

---

## Feature Engineering Philosophy

**Goal**: Capture **patterns of decline** that precede churn

- **Activity trends**: Is user engaging less over time?
- **Content engagement**: Still watching videos? Taking quizzes?
- **Recency**: How long since last activity?
- **Payment behavior**: Payment failures signal involuntary churn risk

---

## File: `src/churn_mlops/features/build_features.py`

### Input

**`data/processed/user_daily.csv`**:
```
user_id, as_of_date, is_active_day, total_events, logins_count, watch_minutes_sum,
quiz_attempts_count, quiz_avg_score, payment_success_count, payment_failed_count, ...
```

### Output

**`data/features/user_features_daily.csv`**:
```
user_id, as_of_date, days_since_signup, plan, is_paid, country, marketing_source,
days_since_last_activity, active_days_7d, active_days_14d, active_days_30d,
events_7d, events_14d, events_30d, logins_7d, logins_14d, logins_30d,
watch_minutes_7d, watch_minutes_14d, watch_minutes_30d, quiz_avg_score_7d,
quiz_avg_score_14d, quiz_avg_score_30d, payment_fail_rate_30d, ...
```

---

## Rolling Window Features

### Configuration

**File**: `config/config.yaml`
```yaml
features:
  windows_days: [7, 14, 30]
```

**Why these windows?**
- **7 days**: Short-term trends (recent drop-off)
- **14 days**: Medium-term trends (two-week slump)
- **30 days**: Long-term trends (monthly churn window)

### Implementation

```python
def _add_rolling_features(d, windows):
    base_sum_cols = [
        "is_active_day",          # → active_days_Xd
        "total_events",           # → events_Xd
        "logins_count",           # → logins_Xd
        "watch_minutes_sum",      # → watch_minutes_Xd
        "quiz_attempts_count",    # → quiz_attempts_Xd
        "payment_success_count",  # → payment_success_Xd
        "payment_failed_count",   # → payment_failed_Xd
    ]
    
    for w in windows:
        for col in base_sum_cols:
            rolled = (
                x.groupby("user_id")[col]
                .rolling(window=w, min_periods=1)
                .sum()
                .reset_index(level=0, drop=True)
            )
            x[f"{col}_{w}d"] = rolled
    
    # Rolling mean for quiz score
    for w in windows:
        rolled_mean = (
            x.groupby("user_id")["quiz_avg_score"]
            .rolling(window=w, min_periods=1)
            .mean()
            .reset_index(level=0, drop=True)
        )
        x[f"quiz_avg_score_{w}d"] = rolled_mean
```

**Key Insight**: `min_periods=1` ensures early days (< 7d since signup) still get a feature value

---

## Recency Features

### Days Since Last Activity

```python
def _add_days_since_last_activity(d):
    # Mark last active date
    x["last_active_dt"] = np.where(
        x["is_active_day"] > 0,
        x["as_of_date"],
        np.datetime64("NaT")
    )
    
    # Forward-fill last active date per user
    x["last_active_dt"] = x.groupby("user_id")["last_active_dt"].ffill()
    
    # Calculate days since
    delta = (x["as_of_date"] - x["last_active_dt"]).dt.days
    x["days_since_last_activity"] = delta.fillna(x["days_since_signup"]).clip(lower=0)
```

**Example**:
```
user_id=101
as_of_date     is_active_day    last_active_dt    days_since_last_activity
2025-01-01     1                2025-01-01        0
2025-01-02     0                2025-01-01        1
2025-01-03     0                2025-01-01        2
2025-01-04     1                2025-01-04        0
```

**Interpretation**:
- `days_since_last_activity = 0`: Active today
- `days_since_last_activity = 7`: Last active 7 days ago (red flag)
- `days_since_last_activity = 30`: Likely churned

---

## Payment Features

### Payment Fail Rate

```python
# Use 30-day window (or largest available)
w_ref = 30 if 30 in windows else max(windows)
fail_col = f"payment_failed_{w_ref}d"
succ_col = f"payment_success_{w_ref}d"

denom = x[fail_col] + x[succ_col]
x[f"payment_fail_rate_{w_ref}d"] = np.where(denom > 0, x[fail_col] / denom, 0.0)
```

**Example**:
- `payment_failed_30d = 2`, `payment_success_30d = 8`
- `payment_fail_rate_30d = 2 / (2 + 8) = 0.20` (20% fail rate)

**Interpretation**: High fail rate → involuntary churn risk (card declined, insufficient funds)

---

## Static Features

```python
keep_static = [
    "user_id",
    "as_of_date",
    "signup_date",
    "days_since_signup",
    "plan",              # free vs. paid
    "is_paid",           # 0 or 1
    "country",           # IN, US, UK, CA, AU, SG
    "marketing_source",  # organic, referral, ads, youtube, community
]
```

**Why include static features?**
- `plan`: Paid users churn less
- `days_since_signup`: New users churn faster (onboarding issue)
- `country`, `marketing_source`: Cohort-specific churn patterns

---

## Feature Catalog

### Activity Features (Rolling Windows)

| Feature | Description | Window |
|---------|-------------|--------|
| `active_days_7d` | Days with any activity in last 7 days | 7d, 14d, 30d |
| `events_7d` | Total events in last 7 days | 7d, 14d, 30d |
| `logins_7d` | Login count in last 7 days | 7d, 14d, 30d |

### Content Engagement (Rolling Windows)

| Feature | Description | Window |
|---------|-------------|--------|
| `watch_minutes_7d` | Total video watch time (minutes) | 7d, 14d, 30d |
| `quiz_attempts_7d` | Quiz attempts in last 7 days | 7d, 14d, 30d |
| `quiz_avg_score_7d` | Average quiz score in last 7 days | 7d, 14d, 30d |
| `enroll_7d` | Course enrollments in last 7 days | 7d, 14d, 30d |

### Payment Features (Rolling Windows)

| Feature | Description | Window |
|---------|-------------|--------|
| `payment_success_30d` | Successful payments in last 30 days | 30d |
| `payment_failed_30d` | Failed payments in last 30 days | 30d |
| `payment_fail_rate_30d` | Ratio of failed to total payments | 30d |

### Recency Features

| Feature | Description |
|---------|-------------|
| `days_since_last_activity` | Days since user was last active |
| `days_since_signup` | Days since user signed up |

### Static Features

| Feature | Description |
|---------|-------------|
| `plan` | free or paid |
| `is_paid` | 1 if paid, 0 if free |
| `country` | User country (categorical) |
| `marketing_source` | Acquisition channel (categorical) |

---

## Feature Engineering Patterns

### 1. **Trend Features** (Compare windows)

```python
# Not implemented in this version, but useful:
df["active_decline_7d_vs_30d"] = df["active_days_7d"] / (df["active_days_30d"] + 1e-6)
# < 0.5 means recent activity is less than half of 30-day average
```

### 2. **Interaction Features**

```python
# Not implemented, but useful:
df["paid_and_low_activity"] = (df["is_paid"] == 1) & (df["active_days_7d"] < 2)
# Paid users who are barely active = high-value churn risk
```

### 3. **Categorical Encoding**

- One-hot encoding for `plan`, `country`, `marketing_source`
- Handled by sklearn pipeline during training (not here)

---

## Files Involved

| File | Purpose |
|------|---------|
| `src/churn_mlops/features/build_features.py` | Feature engineering logic |
| `scripts/build_features.sh` | Shell wrapper |
| `data/processed/user_daily.csv` | Input |
| `data/features/user_features_daily.csv` | Output |
| `config/config.yaml` | `features.windows_days` config |

---

## Run Commands

```bash
# Build features (default windows: 7, 14, 30)
python -m churn_mlops.features.build_features

# Using script
./scripts/build_features.sh

# Custom paths
python -m churn_mlops.features.build_features \
  --processed-dir data/processed \
  --features-dir data/features
```

---

## Verify Steps

```bash
# 1. Check output exists
ls -lh data/features/user_features_daily.csv

# 2. Inspect schema
head -n 3 data/features/user_features_daily.csv | cut -d',' -f1-10

# 3. Verify rolling features
python -c "
import pandas as pd
df = pd.read_csv('data/features/user_features_daily.csv')
print('Columns:', len(df.columns))
print('Rows:', len(df))
print()
print('Sample features:')
print(df[['user_id', 'as_of_date', 'active_days_7d', 'active_days_30d', 
          'days_since_last_activity']].head(10))
"

# 4. Check for NaNs (should be minimal, mostly in quiz_avg_score)
python -c "
import pandas as pd
df = pd.read_csv('data/features/user_features_daily.csv')
print('NaN counts per column:')
print(df.isna().sum()[df.isna().sum() > 0])
"
```

---

## Troubleshooting

**Issue**: All rolling features are 0
- **Cause**: `is_active_day` not computed correctly in user_daily
- **Fix**: Check `prepare_dataset.py` aggregation logic

**Issue**: `days_since_last_activity` always equals `days_since_signup`
- **Cause**: No active days found (wrong `is_active_day` logic)
- **Fix**: Ensure `is_active_day = (total_events > 0).astype(int)` in user_daily

**Issue**: Feature file too large (> 500 MB)
- **Cause**: Too many windows or too many users × dates
- **Fix**: Reduce windows (e.g., only [7, 30]) or sample data

**Issue**: `KeyError: 'engagement_score'`
- **Cause**: Trying to include synthetic-only column in final features
- **Fix**: Remove from static features list (or make conditional)

---

## Best Practices

1. **Keep it simple**: Start with obvious features (activity, recency)
2. **Rolling windows**: Capture temporal patterns without leakage
3. **Handle NaNs gracefully**: `min_periods=1` for rolling, `fillna(0)` for sums
4. **Avoid leakage**: Never use future information in features
5. **Document features**: Catalog helps with debugging and interpretation

---

## Feature Importance (After Training)

Once you train a model, inspect which features matter:

```python
import joblib
import pandas as pd

model_blob = joblib.load("artifacts/models/baseline_logreg_*.joblib")
model = model_blob["model"]

# Get feature names (after one-hot encoding)
feature_names = model.named_steps["preprocess"].get_feature_names_out()

# Get coefficients (for logistic regression)
coef = model.named_steps["model"].coef_[0]

# Sort by absolute coefficient
importance = pd.DataFrame({"feature": feature_names, "coef": coef})
importance["abs_coef"] = importance["coef"].abs()
importance = importance.sort_values("abs_coef", ascending=False)

print(importance.head(20))
```

**Expected Top Features**:
- `days_since_last_activity` (high = churn)
- `active_days_7d` (low = churn)
- `watch_minutes_30d` (low = churn)
- `payment_fail_rate_30d` (high = involuntary churn)
- `days_since_signup` (very low = new user churn)

---

## Next Steps

- **[Section 06](section-06-training-pipeline.md)**: Create labels and train models
- **[Section 03](section-03-data-design.md)**: Review data schema
- **[Section 04](section-04-data-validation-gates.md)**: Validation before features

---

## Key Takeaways

1. **Rolling windows capture temporal patterns** without label leakage
2. **Recency features** (days since last activity) are powerful churn signals
3. **Payment fail rate** signals involuntary churn risk
4. **Static features** (plan, country) capture cohort effects
5. **Feature catalog** documents what each feature means for model interpretation
