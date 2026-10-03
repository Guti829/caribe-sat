from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "web" / "static" / "data"
OUT_DIR = ROOT / "out"


def load_config(path: Path | None = None) -> dict:
    with open(path or ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_region(cfg: dict, region_id: str) -> dict:
    for r in cfg["regiones"]:
        if r["id"] == region_id:
            return r
    raise KeyError(f"Región desconocida: {region_id}")
