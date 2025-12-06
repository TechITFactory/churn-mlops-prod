from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def rel(*parts: str) -> Path:
    return PROJECT_ROOT.joinpath(*parts)
