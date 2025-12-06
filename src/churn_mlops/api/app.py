from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from churn_mlops.common.config import load_config
from churn_mlops.common.logging import setup_logging


app = FastAPI(title="TechITFactory Churn API", version="0.1.0")


@dataclass
class ModelBundle:
    model: Any
    cat_cols: list[str]
    num_cols: list[str]
    raw: Dict[str, Any]


class PredictRequest(BaseModel):
    user_id: Optional[int] = Field(default=None)
    features: Dict[str, Any] = Field(default_factory=dict)


class PredictResponse(BaseModel):
    user_id: Optional[int]
    churn_risk: float
    model_type: str


_bundle: Optional[ModelBundle] = None


def _load_bundle() -> ModelBundle:
    cfg = load_config()
    models_dir = cfg["paths"]["models"]

    prod_path = Path(models_dir) / "production_latest.joblib"
    if not prod_path.exists():
        raise FileNotFoundError(
            f"Missing production model alias: {prod_path}. "
            f"Run promote step first."
        )

    blob = joblib.load(prod_path)

    if isinstance(blob, dict) and "model" in blob:
        model = blob["model"]
        cat_cols = list(blob.get("cat_cols", []))
        num_cols = list(blob.get("num_cols", []))
        return ModelBundle(model=model, cat_cols=cat_cols, num_cols=num_cols, raw=blob)

    return ModelBundle(model=blob, cat_cols=[], num_cols=[], raw={"model": blob})


def _get_bundle() -> ModelBundle:
    global _bundle
    if _bundle is None:
        _bundle = _load_bundle()
    return _bundle


def _align_features(features: Dict[str, Any], bundle: ModelBundle) -> pd.DataFrame:
    if bundle.cat_cols or bundle.num_cols:
        data = dict(features)

        for c in bundle.cat_cols:
            data.setdefault(c, None)
        for c in bundle.num_cols:
            data.setdefault(c, 0.0)

        df = pd.DataFrame([data])

        for c in bundle.cat_cols + bundle.num_cols:
            if c not in df.columns:
                df[c] = None if c in bundle.cat_cols else 0.0

        return df

    return pd.DataFrame([features])


@app.on_event("startup")
def startup():
    cfg = load_config()
    logger = setup_logging(cfg)
    try:
        b = _get_bundle()
        logger.info("API loaded production model successfully.")
        logger.info("Captured cols: cat=%d num=%d", len(b.cat_cols), len(b.num_cols))
    except Exception as e:
        logger.error("Failed to load model on startup: %s", e)


@app.get("/live")
def live():
    # Pure process health
    return {"status": "ok"}


@app.get("/ready")
def ready():
    # Readiness depends on model availability
    try:
        _get_bundle()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/health")
def health():
    # Backward-compatible alias for readiness
    return ready()


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    try:
        bundle = _get_bundle()
        X = _align_features(req.features, bundle)

        if not hasattr(bundle.model, "predict_proba"):
            raise ValueError("Loaded model does not support predict_proba")

        proba = float(bundle.model.predict_proba(X)[:, 1][0])
        return PredictResponse(user_id=req.user_id, churn_risk=proba, model_type="production_pipeline")

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
