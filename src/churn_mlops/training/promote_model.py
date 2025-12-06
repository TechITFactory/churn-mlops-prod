from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from churn_mlops.common.config import load_config
from churn_mlops.common.logging import get_logger, setup_logging


@dataclass
class Candidate:
    model_path: Path
    metrics_path: Path
    score: float
    metric_name: str


def _read_metrics(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text())


def _score_from_metrics(m: Dict[str, Any]) -> Tuple[str, float]:
    # Prefer PR-AUC for imbalanced churn
    for key in ("pr_auc", "average_precision", "roc_auc", "f1", "accuracy"):
        if key in m and isinstance(m[key], (int, float)):
            return key, float(m[key])
    return "unknown", -1.0


def _find_candidates(models_dir: Path, metrics_dir: Path) -> list[Candidate]:
    out: list[Candidate] = []

    for mp in sorted(metrics_dir.glob("*.json")):
        stem = mp.stem
        model_guess = models_dir / f"{stem}.joblib"
        if not model_guess.exists():
            continue

        m = _read_metrics(mp)
        metric_name, score = _score_from_metrics(m)
        out.append(
            Candidate(
                model_path=model_guess,
                metrics_path=mp,
                score=score,
                metric_name=metric_name,
            )
        )

    return out


def promote_model() -> Dict[str, Any]:
    cfg = load_config()
    logger = get_logger()

    models_dir = Path(cfg["paths"]["models"])
    metrics_dir = Path(cfg["paths"]["metrics"])

    models_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)

    candidates = _find_candidates(models_dir, metrics_dir)

    if not candidates:
        raise FileNotFoundError(
            f"No promotable models found in {models_dir}. "
            f"Expected a .joblib with matching .json metrics."
        )

    # Choose best score
    best = sorted(candidates, key=lambda c: c.score, reverse=True)[0]

    prod_model = models_dir / "production_latest.joblib"
    prod_metrics = metrics_dir / "production_latest.json"

    shutil.copy2(best.model_path, prod_model)
    shutil.copy2(best.metrics_path, prod_metrics)

    logger.info(
        "Promoted model: %s (metric=%s score=%.5f) -> %s",
        best.model_path.name,
        best.metric_name,
        best.score,
        prod_model.name,
    )

    meta = {
        "promoted_from_model": best.model_path.name,
        "promoted_from_metrics": best.metrics_path.name,
        "metric_used": best.metric_name,
        "score": best.score,
        "production_model": str(prod_model),
        "production_metrics": str(prod_metrics),
    }

    return meta


def main():
    cfg = load_config()
    setup_logging(cfg)
    meta = promote_model()
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
