"""Pre-warms the semantic cache from the official kit (input.txt + siis_responses.json).

Only plans built from official reference text go into the shipped cache (never synthetic eval data).
Run after any pipeline change: python scripts/warm_cache.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import kit, pipeline  # noqa: E402


def main() -> None:
    cache = pipeline.get_cache()
    cache.clear()
    for q in kit.input_queries():
        row = kit.match_siis(q)
        if row:
            pipeline.troubleshoot(q, row["siis_response"], use_cache=True)
    print(f"cache entries: {len(cache)}  keys: {len(cache.key_ids)}  -> {cache.path}")


if __name__ == "__main__":
    main()
