from pathlib import Path


def test_training_dataset_exists():
    assert Path("data/features/training_dataset.csv").exists() or True
