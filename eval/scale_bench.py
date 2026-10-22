"""Scalability benchmark (Round 2): how easy is it to cover a new scenario, and does the system stay fast as it grows?

  1. Onboarding    D2b's 8 relevant articles are treated as brand-new scenarios: compile each once (no code change),
                   then serve the exact complaint and a hand-written rewording (D5) from the cache.
  2. Catalog reach can every phone Settings entry in the catalog be found by its own feature name and operation?
  3. Cache size    lookup latency with 1k / 10k / 100k stored keys (synthetic keys added to the shipped cache),
                   and whether the real answers stay the same.
  4. Load          requests per second and latency through the real HTTP API at 1 / 10 / 50 concurrent clients.

Everything runs on copies under .tmp/scale/; the shipped data/derived/cache.sqlite is never written.

    python eval/scale_bench.py                 # rules + LLM onboarding (LLM only if a key is set)
    python eval/scale_bench.py --offline       # rules only
"""
import argparse
import asyncio
import json
import os
import shutil
import sqlite3
import sys
import threading
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WORK = ROOT / ".tmp" / "scale"
WORK.mkdir(parents=True, exist_ok=True)
SHIPPED = ROOT / "data" / "derived" / "cache.sqlite"
os.environ["CACHE_DB"] = str(WORK / "boot_cache.sqlite")    # never the shipped file
os.environ["CACHE_WRITE"] = "1"
shutil.copyfile(SHIPPED, WORK / "boot_cache.sqlite")

from app import cache as cache_mod, catalog, config, kit, llm, pipeline  # noqa: E402

D2B = json.loads((ROOT / "eval" / "datasets" / "d2b_heldout.json").read_text(encoding="utf-8"))["cases"]
D5 = json.loads((ROOT / "eval" / "datasets" / "d5_onboarding_paraphrases.json").read_text(encoding="utf-8"))
D3B = json.loads((ROOT / "eval" / "datasets" / "d3b_paraphrases_holdout.json").read_text(encoding="utf-8"))


def pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))], 1) if xs else None


def use_cache(path: Path) -> cache_mod.SemanticCache:
    pipeline._cache = cache_mod.SemanticCache(path)
    return pipeline._cache


# ---------------------------------------------------------------- 1. onboarding
def onboarding(mode: str, pause: float) -> dict:
    path = WORK / f"onboard_{mode}.sqlite"
    shutil.copyfile(SHIPPED, path)
    cache = use_cache(path)
    before = len(cache)
    new = [c for c in D2B if c["relevant"]]
    plan_of, rows = {}, []
    for i, c in enumerate(new):
        t = time.perf_counter()
        env = pipeline.troubleshoot(c["query"], c["siis_response"])
        ms = (time.perf_counter() - t) * 1000
        acts = [a for g in env["response"]["contexts"] for a in g["actions"]]
        links = [a for a in acts if (a["stepGroups"][0].get("actionableDeeplink") or {}).get("deeplink", "").startswith("voiceassist://masked")]
        plan_of[c["id"]] = json.dumps(env["response"], sort_keys=True) if acts else None
        rows.append({"case": c["id"], "domain": c["domain"], "compile_ms": round(ms), "cost_usd": env["meta"]["cost_usd"],
                     "model": env["meta"]["model"], "actions": len(acts), "catalog_links": len(links),
                     "fallback": env["meta"].get("fallback")})
        print(f"  [{mode}] compiled {c['id']:7} {c['domain']:12} {ms:7.0f} ms  {len(acts)} actions  {env['meta']['model'][:40]}", flush=True)
        if mode == "llm" and i < len(new) - 1:
            time.sleep(pause)
    exact_ms = []
    for c in new:
        t = time.perf_counter()
        env = pipeline.troubleshoot(c["query"], c["siis_response"])
        exact_ms.append((time.perf_counter() - t) * 1000)
        assert env["meta"]["cache_hit"], c["id"]
    para = []
    for p in D5["positives"]:
        t = time.perf_counter()
        env = pipeline.troubleshoot(p["text"], None)
        ms = (time.perf_counter() - t) * 1000
        hit = env["meta"]["cache_hit"]
        right = hit and plan_of.get(p["case"]) == json.dumps(env["response"], sort_keys=True)
        para.append({"case": p["case"], "text": p["text"], "hit": hit, "right_plan": bool(right), "ms": round(ms, 1)})
    false_hits = [n for n in D5["negatives"] if pipeline.troubleshoot(n, None)["meta"]["cache_hit"]]
    planned = [r for r in rows if r["actions"]]
    return {
        "mode": mode, "articles": len(new), "code_changes": 0, "entries_before": before, "entries_after": len(cache),
        "planned": len(planned),
        "compile_ms_mean": round(sum(r["compile_ms"] for r in rows) / len(rows)), "compile_ms_max": max(r["compile_ms"] for r in rows),
        "cost_usd_total": round(sum(r["cost_usd"] for r in rows), 5), "cost_usd_per_article": round(sum(r["cost_usd"] for r in rows) / len(rows), 5),
        "exact_hit_ms_p95": pct(exact_ms, 95),
        "rewording_hits": sum(p["hit"] for p in para), "rewording_right_plan": sum(p["right_plan"] for p in para), "rewordings": len(para),
        "rewording_ms_p95": pct([p["ms"] for p in para], 95), "false_hits": false_hits, "negatives": len(D5["negatives"]),
        "rows": rows, "rewording_detail": para,
    }


# ---------------------------------------------------------------- 2. catalog reach
def catalog_reach() -> dict:
    cat = catalog.get()
    res, wrong, ms = Counter(), [], []
    for e in cat.searchable:
        op = e.op if e.op in ("on", "off", "view", "update") else None
        t = time.perf_counter()
        m = cat.match(e.feature, op)
        ms.append((time.perf_counter() - t) * 1000)
        if not m.accepted or m.entry is None:
            res["declined"] += 1
        elif m.entry.id == e.id:
            res["exact"] += 1
        elif m.entry.feature.lower() == e.feature.lower() and m.entry.op == e.op:
            res["duplicate_entry"] += 1          # two catalog entries for the same feature + operation
        else:
            res["other_entry"] += 1
            if len(wrong) < 12:
                wrong.append({"asked": f"{e.feature} ({op})", "expected": f"{e.id} {e.raw.get('message')}",
                              "got": f"{m.entry.id} {m.entry.raw.get('message')}"})
    n = len(cat.searchable)
    return {"catalog_entries": len(cat.entries) + 1, "phone_entries": n, "appliance_entries_excluded": len(cat.entries) - n,
            **{k: res[k] for k in ("exact", "duplicate_entry", "other_entry", "declined")},
            "reached_pct": round(100 * (res["exact"] + res["duplicate_entry"]) / n, 1),
            "match_ms_p50": pct(ms, 50), "match_ms_p95": pct(ms, 95), "other_entry_examples": wrong}


# ---------------------------------------------------------------- 3. cache size
def cache_size(sizes=(1_000, 10_000, 100_000)) -> dict:
    queries = [p["text"] for p in D3B["positives"]] + D3B["negatives"]
    baseline = use_cache(WORK / "boot_cache.sqlite")
    expected = {q: json.dumps(baseline.lookup(q, None)[0], sort_keys=True) for q in queries}
    dim = baseline.key_vecs.shape[1]
    rng = np.random.default_rng(7)
    out = []
    for n in sizes:
        path = WORK / f"synthetic_{n}.sqlite"
        shutil.copyfile(SHIPPED, path)
        db = sqlite3.connect(str(path))
        env = json.dumps({"query_variations": [], "response": {"contexts": []}, "meta": {}})
        per_entry = 10
        for start in range(0, n, per_entry):
            cur = db.execute("INSERT INTO entries(norm_query, siis_hash, symptoms, envelope, tier, created) VALUES (?,?,?,?,?,?)",
                             (f"synthetic complaint {start}", None, "[]", env, "auto", 0.0))
            vecs = rng.standard_normal((per_entry, dim)).astype(np.float32)
            vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
            db.executemany("INSERT INTO keys(entry_id, text, vec) VALUES (?,?,?)",
                           [(cur.lastrowid, f"synthetic {start + j}", v.tobytes()) for j, v in enumerate(vecs)])
        db.commit()
        db.close()
        t = time.perf_counter()
        c = cache_mod.SemanticCache(path)
        load_s = time.perf_counter() - t
        for q in queries[:5]:
            c.lookup(q, None)                      # warm-up
        ms, same = [], 0
        for _ in range(3):
            for q in queries:
                t = time.perf_counter()
                hit = c.lookup(q, None)[0]
                ms.append((time.perf_counter() - t) * 1000)
        for q in queries:
            same += json.dumps(c.lookup(q, None)[0], sort_keys=True) == expected[q]
        out.append({"keys": len(c.key_ids), "entries": len(c), "load_s": round(load_s, 2),
                    "lookup_ms_p50": pct(ms, 50), "lookup_ms_p95": pct(ms, 95),
                    "vector_memory_mb": round(c.key_vecs.nbytes / 1e6, 1),
                    "answers_unchanged": f"{same}/{len(queries)}"})
        print(f"  cache {out[-1]['keys']:>7} keys: P95 {out[-1]['lookup_ms_p95']} ms, answers unchanged {same}/{len(queries)}", flush=True)
        c.db.close()
        del c
        path.unlink(missing_ok=True)
    return {"queries": len(queries), "note": "synthetic keys are random unit vectors (they measure speed, not accuracy)", "runs": out}


# ---------------------------------------------------------------- 4. load
def load_test(levels=(1, 10, 50), n_requests=300, port=8799) -> dict:
    import httpx
    import uvicorn
    from app.main import app

    shutil.copyfile(SHIPPED, WORK / "load_cache.sqlite")
    use_cache(WORK / "load_cache.sqlite")
    config.CACHE_WRITE = False
    key, llm.API_KEY = llm.API_KEY, ""             # cached traffic only; no LLM calls during the load test
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(600):
        try:
            if httpx.get(base + "/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    rows = kit.siis_rows()
    official = [{"query": q, "siis_response": (kit.match_siis(q) or {}).get("siis_response")} for q in kit.input_queries()]
    mix = official + [{"query": p["text"]} for p in D3B["positives"]] + [{"query": n} for n in D3B["negatives"]]
    reqs = [mix[i % len(mix)] for i in range(n_requests)]

    req_file = WORK / "load_requests.json"
    req_file.write_text(json.dumps(reqs), encoding="utf-8")

    def run(conc: int) -> dict:
        # the client runs in its own process, like real users would; in-process clients would compete with
        # the server for Python's GIL and distort the numbers
        import subprocess
        out = subprocess.run([sys.executable, str(ROOT / "eval" / "load_client.py"), base, str(conc), str(req_file)],
                             capture_output=True, text=True, timeout=600)
        return json.loads(out.stdout.strip().splitlines()[-1])

    out = []
    for conc in levels:
        out.append(run(conc))
        print(f"  load c={conc:>2}: {out[-1]['req_per_s']} req/s, P95 {out[-1]['latency_ms_p95']} ms, errors {out[-1]['errors']}", flush=True)
    server.should_exit = True
    th.join(timeout=10)
    llm.API_KEY = key
    config.CACHE_WRITE = True
    return {"mix": f"{len(official)} official lines with article (exact hits), {len(D3B['positives'])} held-out rewordings, "
                   f"{len(D3B['negatives'])} unrelated complaints; no LLM", "server": f"1 uvicorn worker, CPU, pipeline in a worker thread ({os.getenv('PIPELINE_CONCURRENCY', '4')} at a time); client in a separate process", "runs": out,
            "rows_in_kit": len(rows)}


def to_md(r: dict) -> str:
    lines = ["# Scalability benchmark", f"Generated {r['generated']} on {r['env']}. Script: `eval/scale_bench.py`. "
             "All runs use copies of the shipped cache; nothing in the repo is modified.", ""]
    lines += ["## 1. Adding new scenarios (no code changes)",
              "D2b's 8 relevant articles (battery, charging, display, performance, Bluetooth, camera) were added as brand-new scenarios.", "",
              "| Mode | Articles | Code changes | Plans made | Compile time mean / max | Cost per article | Exact repeat P95 | Rewordings answered (right plan) | Rewording P95 | False hits |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for o in r["onboarding"]:
        lines.append(f"| {o['mode']} | {o['articles']} | {o['code_changes']} | {o['planned']}/{o['articles']} | {o['compile_ms_mean']} / {o['compile_ms_max']} ms | "
                     f"${o['cost_usd_per_article']:.5f} | {o['exact_hit_ms_p95']} ms | {o['rewording_hits']}/{o['rewordings']} ({o['rewording_right_plan']}) | "
                     f"{o['rewording_ms_p95']} ms | {len(o['false_hits'])} of {o['negatives']} |")
    c = r["catalog"]
    lines += ["", "## 2. Catalog reach",
              f"Each of the {c['phone_entries']} phone Settings entries (of {c['catalog_entries']}; {c['appliance_entries_excluded']} appliance entries and the placeholder excluded) "
              "was searched by its own feature name and operation.", "",
              "| Found itself | Found its duplicate | Different entry | Declined | Reached | Match P50 / P95 |", "|---|---|---|---|---|---|",
              f"| {c['exact']} | {c['duplicate_entry']} | {c['other_entry']} | {c['declined']} | **{c['reached_pct']}%** | {c['match_ms_p50']} / {c['match_ms_p95']} ms |"]
    if c["other_entry_examples"]:
        lines += ["", "Examples of a different entry:"] + [f"- {w['asked']}: expected {w['expected']}, got {w['got']}" for w in c["other_entry_examples"][:6]]
    lines += ["", "## 3. Cache size", r["cache_size"]["note"] + ".", "",
              "| Stored keys | Lookup P50 | Lookup P95 | Vector memory | Load time | Real answers unchanged |", "|---|---|---|---|---|---|"]
    for s in r["cache_size"]["runs"]:
        lines.append(f"| {s['keys']:,} | {s['lookup_ms_p50']} ms | {s['lookup_ms_p95']} ms | {s['vector_memory_mb']} MB | {s['load_s']} s | {s['answers_unchanged']} |")
    if r.get("load"):
        lines += ["", "## 4. Concurrent load (real HTTP API)", f"Traffic: {r['load']['mix']}. Server: {r['load']['server']}.", "",
                  "| Concurrent clients | Requests | Errors | Requests/s | Latency P50 | Latency P95 |", "|---|---|---|---|---|---|"]
        for s in r["load"]["runs"]:
            lines.append(f"| {s['concurrency']} | {s['requests']} | {s['errors']} | {s['req_per_s']} | {s['latency_ms_p50']} ms | {s['latency_ms_p95']} ms |")
        if r.get("load_before_threadpool"):
            lines += ["", "Before the request handler moved to a worker thread (22 Oct, same traffic):", "",
                      "| Concurrent clients | Errors | Requests/s | Latency P95 |", "|---|---|---|---|"]
            for s in r["load_before_threadpool"]["runs"]:
                lines.append(f"| {s['concurrency']} | {s['errors']} | {s['req_per_s']} | {s['latency_ms_p95']} ms |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="rules-only onboarding")
    ap.add_argument("--llm-budget", type=float, default=30.0, help="seconds per LLM call when compiling new articles")
    ap.add_argument("--pause", type=float, default=3.0)
    ap.add_argument("--skip-load", action="store_true")
    ap.add_argument("--load-only", action="store_true", help="re-run only the load test; keep the other results")
    args = ap.parse_args()
    out = ROOT / "eval" / "runs"
    if args.load_only:
        res = json.loads((out / "scale.json").read_text(encoding="utf-8"))
        if res.get("load") and "load_before_threadpool" not in res:
            res["load_before_threadpool"] = res["load"]
        print("4. load", flush=True)
        res["load"] = load_test()
        res["load_generated"] = time.strftime("%Y-%m-%d %H:%M")
        (out / "scale.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
        (out / "scale.md").write_text(to_md(res), encoding="utf-8")
        print(to_md(res))
        return
    import platform
    res = {"generated": time.strftime("%Y-%m-%d %H:%M"), "env": f"{os.cpu_count()} vCPU / {platform.system()} {platform.release()} / Python {platform.python_version()}"}
    key = llm.API_KEY
    print("1. onboarding", flush=True)
    llm.API_KEY = ""
    res["onboarding"] = [onboarding("rules", 0)]
    if key and not args.offline:
        llm.API_KEY, llm.BUDGET_S = key, args.llm_budget
        res["onboarding"].append(onboarding("llm", args.pause))
        llm.API_KEY = ""
    print("2. catalog reach", flush=True)
    res["catalog"] = catalog_reach()
    print("3. cache size", flush=True)
    res["cache_size"] = cache_size()
    if not args.skip_load:
        print("4. load", flush=True)
        res["load"] = load_test()
    out.mkdir(parents=True, exist_ok=True)
    (out / "scale.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    (out / "scale.md").write_text(to_md(res), encoding="utf-8")
    print(to_md(res))
    print(f"wrote {out / 'scale.json'} and {out / 'scale.md'}")


if __name__ == "__main__":
    main()
