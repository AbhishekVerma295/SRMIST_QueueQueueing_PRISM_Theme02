"""Pre-warms the semantic cache from the official kit (input.txt + siis_responses.json).

Only plans built from official reference text go into the shipped cache (never synthetic eval data).
With an LLM key this is the batch "compile" step: each line runs the full cold path once, with a generous
time budget, and the validated plan is stored; later requests are served from the cache in milliseconds.
Every cold run is logged to eval/runs/cold_runs.jsonl (model, latency, tokens, cost, fallbacks) for metrics.md.

    python scripts/warm_cache.py                      # offline rules if no key in .env
    python scripts/warm_cache.py --llm-budget 60      # batch compile with the LLM
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import kit, llm, pipeline  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm-budget", type=float, default=60.0, help="seconds per LLM call incl. fallbacks (batch mode)")
    ap.add_argument("--pause", type=float, default=4.0, help="seconds between lines (free-tier rate limits)")
    ap.add_argument("--thinking", default="minimal", help="Gemini 3 thinking level for the batch compile (low was tried on 3 Oct and scored lower)")
    ap.add_argument("--resume", action="store_true", help="keep lines whose cached plan was already built by the LLM; redo the rest")
    args = ap.parse_args()
    llm.BUDGET_S = args.llm_budget
    llm.THINKING = args.thinking

    cache = pipeline.get_cache()
    log_path = ROOT / "eval" / "runs" / "cold_runs.jsonl"
    previous = {}
    if args.resume and log_path.exists():
        previous = {r["row_id"]: r for r in map(json.loads, log_path.read_text(encoding="utf-8").splitlines()) if r}
    else:
        cache.clear()
    runs = []
    lines = kit.input_queries()
    for i, q in enumerate(lines, 1):
        row = kit.match_siis(q)
        if not row:
            continue
        s_hash = pipeline.cache_mod.siis_hash(f"{row['siis_response']['title']}\n{row['siis_response']['content']}")
        if args.resume:
            kept = cache.exact_entry(q, s_hash)
            if kept and kept["envelope"]["meta"]["model"].startswith("gemini") and row["id"] in previous:
                runs.append(previous[row["id"]])
                print(f"{i:2}/{len(lines)} {row['id']:7} kept LLM plan ({kept['envelope']['meta']['model'][:30]})", flush=True)
                continue
            cache.delete_query(q, s_hash)
        t = time.perf_counter()
        env = pipeline.troubleshoot(q, row["siis_response"], use_cache=True, lookup=False, debug=True)   # store every official line
        trace = env.pop("trace", {})
        runs.append({"row_id": row["id"], "wall_ms": round((time.perf_counter() - t) * 1000), "meta": env["meta"],
                     "llm": trace.get("llm"), "dropped_ungrounded_steps": (trace.get("llm_extract") or {}).get("dropped_ungrounded_steps"),
                     "contexts": len(env["response"]["contexts"])})
        print(f"{i:2}/{len(lines)} {row['id']:7} {env['meta']['model'][:45]:45} {runs[-1]['wall_ms']:6} ms  ${env['meta']['cost_usd']:.5f}  "
              f"{env['meta'].get('fallback') or str(len(env['response']['contexts'])) + ' ctx'}", flush=True)
        if llm.enabled() and i < len(lines):
            time.sleep(args.pause)
    out = ROOT / "eval" / "runs" / "cold_runs.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r) + "\n" for r in runs), encoding="utf-8")
    llm_runs = [r for r in runs if "llm fallback" not in r["meta"]["model"] and r["meta"]["model"].startswith("gemini")]
    print(f"cache entries: {len(cache)}  keys: {len(cache.key_ids)}  -> {cache.path}")
    print(f"LLM-built plans: {len(llm_runs)}/{len(runs)}  (rest fell back to rules)  log -> {out}")


if __name__ == "__main__":
    main()
