"""Build step (also run inside Docker): downloads the embedding model, embeds the catalog and writes
data/derived/feature_graph.json. Safe to re-run; outputs are cached by content hash."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import catalog, config, embed  # noqa: E402


def main() -> None:
    t = time.perf_counter()
    embed.warmup()
    cat = catalog.get()
    config.DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    graph = cat.feature_graph()
    (config.DERIVED_DIR / "feature_graph.json").write_text(json.dumps(graph, indent=1, ensure_ascii=False), encoding="utf-8")
    twins = sum(1 for v in graph.values() if {e["op"] for e in v} >= {"on", "off"})
    print(f"catalog entries: {len(cat.entries)} (searchable {len(cat.searchable)}, appliances skipped {len(cat.entries) - len(cat.searchable)})")
    print(f"features: {len(graph)}  on/off twins: {twins}  built in {time.perf_counter() - t:.1f}s")


if __name__ == "__main__":
    main()
