import json
from pathlib import Path

AUTO_MAP_PATH = Path("data/product_name_patterns.auto.json")


def load_auto_mappings() -> dict:
    if AUTO_MAP_PATH.exists():
        return json.loads(AUTO_MAP_PATH.read_text())
    return {}


def save_auto_mapping(key: str, value: str):
    mappings = load_auto_mappings()
    if key not in mappings:
        mappings[key] = value
        AUTO_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
        AUTO_MAP_PATH.write_text(json.dumps(mappings, indent=2))
