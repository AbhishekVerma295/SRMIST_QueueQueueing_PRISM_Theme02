"""Architectural ablation (Appendix C, section 5): three deeplink-mapping strategies, same everything else.

  Baseline  Full LLM deeplink mapping   - the LLM picks an entry id from the whole (non-appliance) catalog
  Variant A Hybrid BM25 + dense         - our default resolver (app/catalog.py: action- and depth-aware rerank)
  Variant B Pure rules                  - keyword/phrase match of the target against catalog feature names

Extraction is held fixed (offline rules extraction, deterministic) so only the mapper changes.
Runs D1 (20 official lines) + D2 (12 held-out scenarios) cold and scores them against the gold labels.

    python eval/ablation.py            # all three (Baseline needs an LLM key)
    python eval/ablation.py --skip-llm
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["CACHE_DB"] = str(ROOT / ".tmp" / "ablation_cache.sqlite")
from app import catalog, kit, llm, pipeline  # noqa: E402
from app.text import normalize, tokens  # noqa: E402

sys.path.insert(0, str(ROOT / "eval"))
from run_eval import gates, pct, score_gold  # noqa: E402

CAT = catalog.get()
HYBRID = catalog.Catalog.match
MAP_STATS = {"calls": 0, "ms": 0.0, "tokens_in": 0, "tokens_out": 0, "cost": 0.0, "failed": 0}


def rules_match(self, target: str, op_hint: str | None = None, context: str = "") -> catalog.Match:
    """Variant B: longest catalog feature phrase contained in the target (or vice versa), op must agree."""
    t = normalize(target).lower()
    best, best_len = None, 0
    for e in self.searchable:
        f = e.feature.lower()
        if not f or not (f in t or t in f):
            continue
        if op_hint in ("on", "off") and e.op in ("on", "off") and e.op != op_hint:
            continue
        if op_hint == "view" and e.op not in ("view",) and best is not None:
            continue
        if len(f) > best_len:
            best, best_len = e, len(f)
    if best is None:                               # fall back to token overlap with the message
        q = set(tokens(target))
        scored = [(len(q & e.feature_tokens) / max(len(e.feature_tokens), 1), e) for e in self.searchable if e.feature_tokens]
        scored.sort(key=lambda s: (-s[0], s[1].id))
        if scored and scored[0][0] >= 1.0:
            best = scored[0][1]
    return catalog.Match(best, 1.0 if best else 0.0, 0.0, 1.0 if best else 0.0, best is not None, [])


_CATALOG_LINES = "\n".join(f"{e.id} | {e.op} | {e.raw.get('message', '')} | {e.raw.get('description', '')}" for e in CAT.searchable)
LLM_MAP_SYSTEM = ("You map one troubleshooting action to the single best entry of a Settings deeplink catalog. "
                  "Choose the entry for the EXACT target screen or switch (not a parent menu) and the right operation "
                  "(on/off/view/update). If no entry fits, answer NONE. Reply as JSON {\"id\": \"DL-xxxx\" or \"NONE\"}.")
LLM_MAP_SCHEMA = {"type": "OBJECT", "properties": {"id": {"type": "STRING"}}, "required": ["id"]}


def llm_match(self, target: str, op_hint: str | None = None, context: str = "") -> catalog.Match:
    """Baseline: the LLM reads the whole catalog (id | op | message | description) and picks an id."""
    u = llm.Usage()
    t = time.perf_counter()
    out = llm.call_json(LLM_MAP_SYSTEM, f"Action target: {target}\nOperation: {op_hint}\nMenu path: {context}\n\nCatalog:\n{_CATALOG_LINES}",
                        LLM_MAP_SCHEMA, u, max_tokens=40)
    MAP_STATS["calls"] += 1
    MAP_STATS["ms"] += (time.perf_counter() - t) * 1000
    MAP_STATS["tokens_in"] += u.tokens_in
    MAP_STATS["tokens_out"] += u.tokens_out
    MAP_STATS["cost"] += u.cost_usd
    by_id = {e.id: e for e in self.searchable}
    e = by_id.get((out or {}).get("id", ""))
    if out is None:
        MAP_STATS["failed"] += 1
    return catalog.Match(e, 1.0 if e else 0.0, 0.0, 1.0 if e else 0.0, e is not None, [])


def run_variant(name: str, match_fn, items, golds) -> dict:
    catalog.Catalog.match = match_fn
    for k in MAP_STATS:
        MAP_STATS[k] = 0 if k != "ms" else 0.0
    envs, ms = [], []
    for q, siis in items:
        t = time.perf_counter()
        envs.append(pipeline.troubleshoot(q, siis, use_cache=False))
        ms.append((time.perf_counter() - t) * 1000)
    catalog.Catalog.match = HYBRID
    s = score_gold(list(zip(envs, golds)))
    g = gates(envs)
    return {"name": name, "step_accuracy": s["step_accuracy"], "deeplink_relevance": s["deeplink_relevance"],
            "precision": s["link_precision"], "p95_ms": pct(ms, 95), "cost_per_query": MAP_STATS["cost"] / len(items),
            "map_calls": MAP_STATS["calls"], "map_failed": MAP_STATS["failed"], "auto_actions": g["auto_actions"],
            "dummy": g["dummy_links"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-llm", action="store_true")
    ap.add_argument("--llm-budget", type=float, default=30.0)
    args = ap.parse_args()
    llm.BUDGET_S = args.llm_budget
    key = llm.API_KEY
    llm.API_KEY = ""                                   # extraction fixed to offline rules for every variant
    gold1 = {r["query"]: r for r in json.loads((ROOT / "eval" / "gold" / "d1_gold.json").read_text(encoding="utf-8"))}
    d2 = json.loads((ROOT / "eval" / "datasets" / "d2_heldout.json").read_text(encoding="utf-8"))["cases"]
    items = [(q, (kit.match_siis(q) or {}).get("siis_response")) for q in kit.input_queries()] + [(c["query"], c["siis_response"]) for c in d2]
    golds = [gold1[q] for q in kit.input_queries()] + d2

    results = [run_variant("Variant A: Hybrid BM25 + Dense Embedding Retrieval", HYBRID, items, golds),
               run_variant("Variant B: Pure Rules-Based Deeplink Mapping", rules_match, items, golds)]
    if not args.skip_llm and key:
        llm.API_KEY = key                              # only the mapper talks to the LLM
        from app import llm_stages
        orig = llm_stages.run_parallel
        # keep extraction offline: the LLM stages return "no result", so the pipeline uses rules extraction
        llm_stages.run_parallel = lambda q, c, t, tr: (llm.Usage(), (None, None), None)
        try:
            results.insert(0, run_variant("Baseline: Full LLM Deeplink Mapping", llm_match, items, golds))
        finally:
            llm_stages.run_parallel = orig
            llm.API_KEY = ""
    out = ROOT / "eval" / "runs" / "ablation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not any(r["name"].startswith("Baseline") for r in results) and out.exists():
        # --skip-llm re-times the local variants only: keep the last measured LLM baseline
        results[:0] = [r for r in json.loads(out.read_text(encoding="utf-8")) if r["name"].startswith("Baseline")]
    out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    for r in results:
        print(f"{r['name'][:52]:52} step={r['step_accuracy']:.2f} rel={r['deeplink_relevance'] if r['deeplink_relevance'] is None else round(r['deeplink_relevance'], 2)} "
              f"prec={r['precision'] if r['precision'] is None else round(r['precision'], 3)} p95={r['p95_ms']:.0f}ms cost/q=${r['cost_per_query']:.5f} "
              f"auto={r['auto_actions']} dummy={r['dummy']} map_calls={r['map_calls']} failed={r['map_failed']}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
