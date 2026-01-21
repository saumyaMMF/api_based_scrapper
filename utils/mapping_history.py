import json
from datetime import datetime
from pathlib import Path

HISTORY_PATH = Path("data/mapping_history.log.jsonl")


def log_mapping_event(
    raw_product_name: str,
    normalized_key: str,
    internal_name: str,
    source: str = "assistant",
    confidence: float = None
):
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "raw_product_name": raw_product_name,
        "normalized_key": normalized_key,
        "internal_product_name": internal_name,
        "source": source
    }
    
    # Add confidence if provided
    if confidence is not None:
        event["confidence"] = confidence

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
