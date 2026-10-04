"""LLM-as-judge for step accuracy (Appendix C, section 2), independent of our gold labels.

The judge sees only the user's complaint, the reference article and the plan the engine returned (titles, actions,
categories, descriptions, steps). It never sees our gold labels, the catalog or the engine's prompts. It grades the
three parts of the spec's step-accuracy anchor, each 0 / 0.5 / 1:
  completeness  every fix the article offers for THIS complaint is in the plan
  correctness   every step is faithful to the article (nothing invented, right screen names, one interaction each)
                and each action's description matches what the action does
  ordering      steps inside an action follow the article; quick settings fixes first, restart/reset/update last
Step accuracy = sum (0-3). When the engine abstained, the judge says whether the article had a viable fix.

Judge model: the strongest Gemini Flash model available (not the Flash-Lite model that writes the plans), temperature 0.
Verdicts are cached in .tmp/judge_cache.json so re-runs cost nothing.

    python eval/llm_judge.py                                   # D1 shipped plans + D2/D2b cold (offline rules)
    python eval/llm_judge.py --compare A.sqlite B.sqlite       # pairwise + absolute on the official lines of two caches
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CACHE_DB", str(ROOT / ".tmp" / "judge_eval_cache.sqlite"))
from app import cache as cache_mod, kit, llm  # noqa: E402

JUDGE_CACHE = ROOT / ".tmp" / "judge_cache.json"
OUT = ROOT / "eval" / "runs" / "judge.json"

SYSTEM = """You are a strict reviewer of phone troubleshooting guides. You get a user's complaint, the reference
support article the guide must be based on, and the guide an engine produced from it. Grade the guide against the
ARTICLE (not your own knowledge). Score each criterion 0, 0.5 or 1:
- completeness: 1 = every fix the article offers for this complaint is present; 0.5 = a useful fix is missing; 0 = most are missing.
- correctness: 1 = every step is supported by the article, names the right screen or switch, is one interaction, and each
  action's one-line description matches what that action does; 0.5 = one or two flaws; 0 = several wrong or invented steps.
- ordering: 1 = steps inside each action follow the article's order. The ACTION order is fixed by the product contract and
  is correct by definition: settings fixes, then physical checks, then contacting support, then restart / force restart /
  safe mode / software update / reset last. Do not penalise that order even if the article mentions a restart earlier.
  0.5 = one ordering problem inside an action; 0 = steps badly ordered.
If the engine returned NO guide, judge only whether the article contains a viable fix for this complaint.
Be concise: one short sentence per issue. Reply only with JSON."""

SCHEMA = {"type": "OBJECT", "properties": {
    "completeness": {"type": "NUMBER"}, "correctness": {"type": "NUMBER"}, "ordering": {"type": "NUMBER"},
    "article_has_fix": {"type": "BOOLEAN"}, "issues": {"type": "ARRAY", "items": {"type": "STRING"}}},
    "required": ["completeness", "correctness", "ordering", "article_has_fix", "issues"]}

PAIR_SYSTEM = """You compare two phone troubleshooting guides built from the same reference support article for the
same complaint. Prefer the guide that is more complete and more faithful to the article, with correct one-line action
descriptions. Action order (settings fixes, physical checks, support, then restart/reset/update last) is fixed by the
product contract, so do not judge it. Ignore formatting and deeplink codes.
Reply only with JSON: {"better": "A" | "B" | "tie", "reason": one sentence}."""
PAIR_SCHEMA = {"type": "OBJECT", "properties": {"better": {"type": "STRING"}, "reason": {"type": "STRING"}},
               "required": ["better", "reason"]}


def render(response: dict) -> str:
    """Plain-text view of a plan: what a person reads (deeplink codes removed)."""
    out = []
    for g in response.get("contexts", []):
        out.append(f"PROBLEM: {g['title']}  ({g['goal']})")
        for i, a in enumerate(g["actions"], 1):
            out.append(f"  Action {i} [{a['category']}] {a['actionName']} - {a['description']}")
            for sg in a["stepGroups"]:
                for s in sg["steps"]:
                    out.append(f"     - {s}")
    return "\n".join(out) or "(no guide: the engine abstained)"


def article(siis) -> str:
    if isinstance(siis, dict):
        return f"{siis.get('title', '')}\n{siis.get('content', '')}"
    return siis or ""


def _judge_model() -> str | None:
    """Strongest available Flash (non-Lite) model; falls back to the adapter's chain."""
    llm.model_name()
    flash = [m for m in llm._chain if re.fullmatch(r"gemini-[\d.]+-flash", m)]
    return flash[0] if flash else None


_store: dict = {}


def _call(system: str, user: str, schema: dict, max_tokens: int = 600) -> tuple[dict | None, llm.Usage]:
    key = hashlib.sha256((system + user).encode()).hexdigest()[:24]
    if key in _store:
        return _store[key], llm.Usage()
    u = llm.Usage()
    out = llm.call_json(system, user, schema, u, max_tokens=max_tokens)
    if out is not None:
        _store[key] = out
        JUDGE_CACHE.write_text(json.dumps(_store, indent=0), encoding="utf-8")
    time.sleep(PAUSE)
    return out, u


def judge_one(query: str, siis, response: dict) -> dict | None:
    user = f"COMPLAINT:\n{query}\n\nREFERENCE ARTICLE:\n{article(siis)}\n\nGUIDE:\n{render(response)}"
    v, _ = _call(SYSTEM, user, SCHEMA)
    if v is None:
        return None
    clamp = lambda x: min(1.0, max(0.0, round(float(x) * 2) / 2))  # noqa: E731
    v = {k: clamp(v[k]) for k in ("completeness", "correctness", "ordering")} | {"article_has_fix": bool(v["article_has_fix"]), "issues": v.get("issues", [])[:4]}
    planned = bool(response.get("contexts"))
    v["planned"] = planned
    v["step_accuracy"] = v["completeness"] + v["correctness"] + v["ordering"] if planned else None
    v["abstention_ok"] = planned == v["article_has_fix"]
    return v


def summarise(name: str, verdicts: list[dict]) -> dict:
    ok = [v for v in verdicts if v]
    planned = [v for v in ok if v["planned"]]
    mean = lambda k: round(sum(v[k] for v in planned) / len(planned), 3) if planned else None  # noqa: E731
    return {"set": name, "judged": len(ok), "failed": len(verdicts) - len(ok), "plans": len(planned),
            "step_accuracy": mean("step_accuracy"), "completeness": mean("completeness"), "correctness": mean("correctness"),
            "ordering": mean("ordering"), "abstention_agreement": round(sum(v["abstention_ok"] for v in ok) / len(ok), 3) if ok else None}


def official_plans_from_cache(path: Path) -> list[tuple[str, dict, dict]]:
    c = cache_mod.SemanticCache(path)
    out = []
    for q in kit.input_queries():
        row = kit.match_siis(q)
        if not row:
            continue
        s = row["siis_response"]
        e = c.exact_entry(q, cache_mod.siis_hash(f"{s['title']}\n{s['content']}"))
        if e:
            out.append((q, s, e["envelope"]["response"]))
    return out


def compare(a: Path, b: Path) -> dict:
    pa, pb = official_plans_from_cache(a), official_plans_from_cache(b)
    rb = {q: r for q, _, r in pb}
    abs_a = [judge_one(q, s, r) for q, s, r in pa]
    abs_b = [judge_one(q, s, rb[q]) if q in rb else None for q, s, _ in pa]
    wins = {"A": 0, "B": 0, "tie": 0}
    for q, s, r in pa:
        if q not in rb or json.dumps(r, sort_keys=True) == json.dumps(rb[q], sort_keys=True):
            wins["tie"] += 1
            continue
        votes = []
        for first, second, swap in ((r, rb[q], False), (rb[q], r, True)):          # both orders: cancels position bias
            v, _ = _call(PAIR_SYSTEM, f"COMPLAINT:\n{q}\n\nREFERENCE ARTICLE:\n{article(s)}\n\nGUIDE A:\n{render(first)}\n\nGUIDE B:\n{render(second)}",
                         PAIR_SCHEMA, 200)
            if v:
                w = str(v.get("better", "tie")).strip().upper()
                votes.append({"A": "B", "B": "A"}.get(w, "tie") if swap else ({"A": "A", "B": "B"}.get(w, "tie")))
        w = votes[0] if len(votes) == 2 and votes[0] == votes[1] else "tie"
        wins[w] += 1
    return {"A": str(a), "B": str(b), "absolute_A": summarise("A", abs_a), "absolute_B": summarise("B", abs_b), "pairwise": wins}


def main() -> None:
    global PAUSE
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"))
    ap.add_argument("--pause", type=float, default=4.0, help="seconds between judge calls (free-tier rate limits)")
    ap.add_argument("--budget", type=float, default=60.0)
    args = ap.parse_args()
    PAUSE = args.pause
    llm.BUDGET_S = args.budget
    if not llm.enabled():
        sys.exit("the judge needs LLM_API_KEY in .env")
    if JUDGE_CACHE.exists():
        _store.update(json.loads(JUDGE_CACHE.read_text(encoding="utf-8")))
    llm.MODEL = os.getenv("LLM_JUDGE_MODEL") or _judge_model() or llm.MODEL
    print("judge model:", llm.model_name(), flush=True)

    if args.compare:
        res = compare(Path(args.compare[0]), Path(args.compare[1]))
        res["judge_model"] = llm.model_name()
        out = ROOT / "eval" / "runs" / "judge_compare.json"
        out.write_text(json.dumps(res, indent=1), encoding="utf-8")
        print(json.dumps(res, indent=1))
        return

    from app import pipeline
    key, llm.API_KEY = llm.API_KEY, ""                 # the ENGINE runs offline (deterministic); only the judge is online
    envs = [json.loads(line) for line in (ROOT / "results.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    d1 = [(e["query"], (kit.match_siis(e["query"]) or {}).get("siis_response"), e["response"]) for e in envs]
    sets = {"D1 official (results.jsonl)": d1}
    for name, file in (("D2 dev", "d2_heldout.json"), ("D2b held-out", "d2b_heldout.json")):
        cases = json.loads((ROOT / "eval" / "datasets" / file).read_text(encoding="utf-8"))["cases"]
        sets[name] = [(c["query"], c["siis_response"], pipeline.troubleshoot(c["query"], c["siis_response"], use_cache=False)["response"]) for c in cases]
    llm.API_KEY = key
    results, detail = [], {}
    for name, items in sets.items():
        verdicts = [judge_one(q, s, r) for q, s, r in items]
        results.append(summarise(name, verdicts))
        detail[name] = [{"query": q, **(v or {"failed": True})} for (q, _, _), v in zip(items, verdicts)]
        print(results[-1], flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"judge_model": llm.model_name(), "summary": results, "detail": detail}, indent=1), encoding="utf-8")
    print(f"wrote {OUT}")


PAUSE = 4.0

if __name__ == "__main__":
    main()
