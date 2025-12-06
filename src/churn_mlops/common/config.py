from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# Optional dotenv support
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


DEFAULT_CONFIG: Dict[str, Any] = {
    "app": {
        "name": "churn-mlops",
        "log_level": "INFO",
    },
    "paths": {
        "data": "data",
        "raw": "data/raw",
        "processed": "data/processed",
        "features": "data/features",
        "predictions": "data/predictions",
        "artifacts": "artifacts",
        "models": "artifacts/models",
        "metrics": "artifacts/metrics",
    },
    "features": {
        "windows_days": [7, 14, 30],
    },
    "churn": {
        "window_days": 30,
    },
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_yaml(path: Path) -> Optional[Dict[str, Any]]:
    try:
        content = yaml.safe_load(path.read_text())
        return content if isinstance(content, dict) else None
    except Exception:
        return None


def load_config() -> Dict[str, Any]:
    cfg = deepcopy(DEFAULT_CONFIG)

    # 1) explicit env path wins
    env_path = os.getenv("CHURN_MLOPS_CONFIG")

    candidates = []
    if env_path:
        candidates.append(Path(env_path))

    # 2) common repo defaults
    candidates.extend(
        [
            Path("config/config.yaml"),
            Path("config/app.yaml"),
            Path("config/base.yaml"),
        ]
    )

    for p in candidates:
        if p.exists():
            file_cfg = _load_yaml(p)
            if file_cfg:
                cfg = _deep_merge(cfg, file_cfg)
            break

    # Ensure required structure always exists
    cfg.setdefault("app", {})
    cfg.setdefault("paths", {})

    # Backfill any missing path keys
    for k, v in DEFAULT_CONFIG["paths"].items():
        cfg["paths"].setdefault(k, v)

    # Backfill log level
    cfg["app"].setdefault("log_level", DEFAULT_CONFIG["app"]["log_level"])
    cfg["app"].setdefault("name", DEFAULT_CONFIG["app"]["name"])

    return cfg
