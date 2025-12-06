import os
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv

load_dotenv()

def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file {path} must contain a YAML mapping/object.")
    return data

def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result

def load_config(config_dir: str = "configs") -> Dict[str, Any]:
    env = os.getenv("APP_ENV", "dev").lower()

    base_path = Path(config_dir) / "config.yaml"
    env_path = Path(config_dir) / f"config.{env}.yaml"

    base_cfg = _read_yaml(base_path)
    env_cfg = _read_yaml(env_path)

    cfg = _deep_merge(base_cfg, env_cfg)
    cfg.setdefault("app", {})["env"] = env

    # Allow env override for log level
    log_level = os.getenv("LOG_LEVEL")
    if log_level:
        cfg.setdefault("logging", {})["level"] = log_level.upper()

    return cfg
