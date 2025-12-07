# Section 06: Training Pipeline

## Goal

Build churn labels, create training dataset, train baseline model using time-aware split, and evaluate performance.

---

## Training Pipeline Overview

```
user_daily.csv
    ↓
build_labels.py         → labels_daily.csv (churn_label)
    ↓
user_features_daily.csv + labels_daily.csv
    ↓
build_training_set.py   → training_dataset.csv (features + labels)
    ↓
train_baseline.py       → baseline_logreg_<timestamp>.joblib + metrics.json
```

---

## Step 1: Build Labels

### File: `src/churn_mlops/training/build_labels.py`

**Logic**: For each user-date, look forward 30 days. If user has 0 active days in that window, label as churned (1).

```python
def build_labels(user_daily, churn_window_days):
    for _uid, g in user_daily.groupby("user_id"):
        active = g["is_active_day"].to_numpy()
        future_sum = _compute_future_active_sum(active, churn_window_days)
        
        tmp["future_active_days"] = future_sum
        tmp["churn_label"] = (tmp["future_active_days"] == 0).astype(int)
        
        # Remove last 30 days (no future data to label)
        if len(tmp) > churn_window_days:
            tmp = tmp.iloc[:-churn_window_days]
```

**Output**: `data/processed/labels_daily.csv`

```csv
user_id,as_of_date,future_active_days,churn_label
101,2025-01-01,5,0
101,2025-01-02,4,0
101,2025-01-03,3,0
102,2025-01-01,0,1
```

**Run**:
```bash
python -m churn_mlops.training.build_labels --window-days 30
./scripts/build_labels.sh
```

---

## Step 2: Build Training Set

### File: `src/churn_mlops/training/build_training_set.py`

**Logic**: Inner join features + labels on (user_id, as_of_date)

```python
def build_training_set(processed_dir, features_dir, output_dir):
    features = pd.read_csv(f"{features_dir}/user_features_daily.csv")
    labels = pd.read_csv(f"{processed_dir}/labels_daily.csv")
    
    df = features.merge(
        labels[["user_id", "as_of_date", "churn_label"]],
        on=["user_id", "as_of_date"],
        how="inner"
    )
    
    df.to_csv(f"{output_dir}/training_dataset.csv", index=False)
```

**Output**: `data/features/training_dataset.csv`

```csv
user_id,as_of_date,active_days_7d,watch_minutes_30d,...,churn_label
101,2025-01-01,5,120.0,...,0
102,2025-01-01,0,0.0,...,1
```

**Run**:
```bash
python -m churn_mlops.training.build_training_set
./scripts/build_training_set.sh
```

---

## Step 3: Train Baseline Model

### File: `src/churn_mlops/training/train_baseline.py`

### Model Architecture

```python
Pipeline([
    ("preprocess", ColumnTransformer([
        ("cat", Pipeline([
            ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
            ("onehot", OneHotEncoder(handle_unknown="ignore"))
        ]), cat_cols),
        ("num", Pipeline([
            ("imputer", SimpleImputer(strategy="constant", fill_value=0.0)),
            ("scaler", StandardScaler())
        ]), num_cols)
    ])),
    ("model", LogisticRegression(
        max_iter=2000,
        class_weight="balanced",
        solver="lbfgs"
    ))
])
```

**Why Logistic Regression?**
- Fast to train
- Interpretable coefficients
- Handles categorical features (via one-hot encoding)
- Good baseline before trying complex models

**Why `class_weight="balanced"`?**
- Automatically adjusts for class imbalance
- Penalizes misclassifying minority class (churners) more

---

### Time-Aware Train/Test Split

```python
def _time_split(df, test_size):
    dates = sorted(df["as_of_date"].dt.date.unique())
    cut_at = int(len(dates) * (1 - test_size))
    cutoff_date = dates[cut_at - 1]
    
    train_df = df[df["as_of_date"].dt.date <= cutoff_date]
    test_df = df[df["as_of_date"].dt.date > cutoff_date]
    
    return train_df, test_df
```

**Why time-based split?**
- **Respects temporal order**: Train on past, test on future
- **Prevents leakage**: No future information in training
- **Realistic evaluation**: Simulates production scenario

**Example**:
- 120 days of data
- test_size = 0.2 → last 24 days for test
- Train on days 1-96, test on days 97-120

---

### Feature Selection

```python
def _select_feature_columns(df):
    y = df["churn_label"]
    
    drop_cols = {
        "churn_label",        # Target
        "user_id",            # Identifier (not a feature)
        "as_of_date",         # Date (not a feature)
        "signup_date",        # Date (not a feature)
    }
    
    X = df.drop(columns=[c for c in drop_cols if c in df.columns])
    return X, y
```

---

### Evaluation Metrics

```python
def _evaluate(model, X_test, y_test):
    proba = model.predict_proba(X_test)[:, 1]  # Churn probability
    
    # Key metrics for imbalanced classification
    pr_auc = average_precision_score(y_test, proba)  # Precision-Recall AUC
    roc_auc = roc_auc_score(y_test, proba)           # ROC AUC
    
    # Classification report
    y_pred = (proba >= 0.5).astype(int)
    report = classification_report(y_test, y_pred, output_dict=True)
    cm = confusion_matrix(y_test, y_pred)
    
    return {
        "pr_auc": pr_auc,
        "roc_auc": roc_auc,
        "confusion_matrix": cm.tolist(),
        "classification_report": report,
    }
```

**Why PR-AUC over Accuracy?**
- Accuracy misleading for imbalanced data (predicting all "not churned" = 70% accuracy)
- PR-AUC focuses on minority class (churners)
- Better for business: "Of users we predict will churn, how many actually churn?"

---

### Model Artifacts

**Model File**: `artifacts/models/baseline_logreg_20250101T103045Z.joblib`

```python
joblib.dump({
    "model": pipeline,
    "cat_cols": cat_cols,
    "num_cols": num_cols,
    "settings": settings.__dict__,
}, model_path)
```

**Metrics File**: `artifacts/metrics/baseline_logreg_20250101T103045Z.json`

```json
{
  "model_type": "logistic_regression",
  "artifact": "baseline_logreg_20250101T103045Z.joblib",
  "train_rows": 160000,
  "test_rows": 40000,
  "churn_rate_train": 0.35,
  "churn_rate_test": 0.34,
  "metrics": {
    "pr_auc": 0.68,
    "roc_auc": 0.75,
    "confusion_matrix": [[24000, 3000], [5000, 8000]],
    "classification_report": {
      "0": {"precision": 0.83, "recall": 0.89, "f1-score": 0.86},
      "1": {"precision": 0.73, "recall": 0.62, "f1-score": 0.67}
    }
  }
}
```

---

## Training Candidate Model

### File: `src/churn_mlops/training/train_candidate.py`

**Purpose**: Retrain model with same logic (for retraining/comparison)

**Difference from baseline**:
- Typically runs on newer data
- Same algorithm, same hyperparameters (for now)
- Used for A/B testing or scheduled retraining

**Run**:
```bash
python -m churn_mlops.training.train_candidate
./scripts/train_candidate.sh
```

---

## Files Involved

| File | Purpose |
|------|---------|
| `src/churn_mlops/training/build_labels.py` | Create churn labels |
| `src/churn_mlops/training/build_training_set.py` | Join features + labels |
| `src/churn_mlops/training/train_baseline.py` | Train baseline model |
| `src/churn_mlops/training/train_candidate.py` | Train candidate model |
| `scripts/build_labels.sh` | Label creation wrapper |
| `scripts/build_training_set.sh` | Training set wrapper |
| `scripts/train_baseline.sh` | Baseline training wrapper |
| `scripts/train_candidate.sh` | Candidate training wrapper |
| `data/processed/labels_daily.csv` | Labels output |
| `data/features/training_dataset.csv` | Training set output |
| `artifacts/models/*.joblib` | Model artifacts |
| `artifacts/metrics/*.json` | Metrics artifacts |

---

## Run Commands

```bash
# Full training pipeline
./scripts/build_labels.sh
./scripts/build_training_set.sh
./scripts/train_baseline.sh

# Or use Makefile
make labels  # build_labels + build_training_set
make train   # train_baseline + train_candidate

# Check outputs
ls -lh artifacts/models/
ls -lh artifacts/metrics/
```

---

## Verify Steps

```bash
# 1. Check labels
python -c "
import pandas as pd
df = pd.read_csv('data/processed/labels_daily.csv')
print(f'Rows: {len(df)}')
print(f'Churn rate: {df[\"churn_label\"].mean():.2%}')
"

# 2. Check training set
python -c "
import pandas as pd
df = pd.read_csv('data/features/training_dataset.csv')
print(f'Rows: {len(df)}')
print(f'Columns: {len(df.columns)}')
print(f'Churn rate: {df[\"churn_label\"].mean():.2%}')
"

# 3. Check model exists
ls -lh artifacts/models/baseline_logreg_*.joblib

# 4. Inspect metrics
cat artifacts/metrics/baseline_logreg_*.json | jq '.metrics'
```

---

## Troubleshooting

**Issue**: `FileNotFoundError: user_features_daily.csv`
- **Cause**: Features not built
- **Fix**: Run `./scripts/build_features.sh` first

**Issue**: Training set has 0 rows
- **Cause**: No matching (user_id, as_of_date) between features and labels
- **Fix**: Check date formats, ensure both use same date range

**Issue**: PR-AUC < 0.55 (near random)
- **Cause**: Features not predictive, or label definition wrong
- **Fix**: Inspect feature distributions, check label logic

**Issue**: `ValueError: Input contains NaN`
- **Cause**: NaNs in features not handled
- **Fix**: Ensure imputers in pipeline (`SimpleImputer`)

**Issue**: Training takes > 10 minutes
- **Cause**: Too many samples or too many features
- **Fix**: Sample data or reduce feature windows

---

## Model Interpretation

```python
import joblib
import pandas as pd

# Load model
blob = joblib.load("artifacts/models/baseline_logreg_*.joblib")
model = blob["model"]

# Get coefficients
coef = model.named_steps["model"].coef_[0]
feature_names = model.named_steps["preprocess"].get_feature_names_out()

# Top positive coefficients (increase churn risk)
importance = pd.DataFrame({"feature": feature_names, "coef": coef})
print("Top churn risk factors:")
print(importance.sort_values("coef", ascending=False).head(10))

# Top negative coefficients (reduce churn risk)
print("\nTop retention factors:")
print(importance.sort_values("coef", ascending=True).head(10))
```

**Expected Insights**:
- **High churn risk**: `days_since_last_activity`, `payment_fail_rate_30d`, low `active_days_7d`
- **Low churn risk**: High `watch_minutes_30d`, high `quiz_attempts_7d`, `is_paid=1`

---

## Hyperparameter Tuning (Future)

```python
# Not implemented in baseline, but easy to add:
from sklearn.model_selection import GridSearchCV

param_grid = {
    "model__C": [0.01, 0.1, 1.0, 10.0],
    "model__max_iter": [1000, 2000, 5000],
}

grid = GridSearchCV(pipeline, param_grid, cv=3, scoring="average_precision")
grid.fit(X_train, y_train)

print(f"Best params: {grid.best_params_}")
print(f"Best PR-AUC: {grid.best_score_:.4f}")
```

---

## Next Steps

- **[Section 07](section-07-model-registry.md)**: Model promotion and versioning
- **[Section 05](section-05-feature-engineering.md)**: Review feature engineering
- **[Section 08](section-08-batch-scoring.md)**: Batch predictions using trained model

---

## Key Takeaways

1. **Time-aware split** respects temporal nature of churn (no future leakage)
2. **Logistic Regression** is a strong baseline (fast, interpretable)
3. **PR-AUC > Accuracy** for imbalanced classification
4. **Class weights** handle imbalance automatically
5. **Versioned artifacts** (timestamp in filename) enable rollback
