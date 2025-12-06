def test_api_module_import():
    from churn_mlops.api.app import app
    assert app is not None
