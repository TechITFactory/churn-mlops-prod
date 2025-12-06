from churn_mlops.common.config import load_config


def test_config_loads():
    cfg = load_config()
    assert "app" in cfg
    assert "paths" in cfg
    assert cfg["app"]["env"] in {"dev", "stage", "prod"}
