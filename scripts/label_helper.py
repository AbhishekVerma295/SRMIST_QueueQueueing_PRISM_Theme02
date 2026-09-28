"""Gold-labelling helper for the official 20 input lines (dataset D1).

Writes eval/gold/d1_draft.json: for every line, the engine's current plan (a starting point only),
every candidate action the extractor found, and the top-5 catalog candidates for each Settings action.
A human copies it to eval/gold/d1_gold.json, corrects it and sets "reviewed": true per row.

Gold row format:
  {"row_id", "query", "relevant": bool,
   "expected_actions": [{"name", "category", "deeplink_id" | null, "acceptable_deeplink_ids": [...]}],
   "reviewed": false, "notes": ""}
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import catalog, kit, pipeline  # noqa: E402
from app.extract_rules import extract  # noqa: E402


def main() -> None:
    cat = catalog.get()
    id_of = {e.raw["deeplink"]: e.id for e in cat.entries}
    rows = []
    for q in kit.input_queries():
        row = kit.match_siis(q)
        env = pipeline.troubleshoot(q, row["siis_response"] if row else None, use_cache=False)
        ctx = env["response"]["contexts"]
        expected = []
        for c in ctx:
            for a in c["actions"]:
                link = (a["stepGroups"][0].get("actionableDeeplink") or {}).get("deeplink")
                expected.append({"name": a["actionName"], "category": a["category"],
                                 "deeplink_id": id_of.get(link, "DL-DUMMY" if link else None), "acceptable_deeplink_ids": []})
        candidates = []
        if row:
            ir, _ = extract(row["siis_response"]["content"])
            for a in ir:
                item = {"kind": a.kind, "heading": a.heading, "target": a.target, "op": a.op, "steps": a.steps}
                if a.target:
                    item["catalog_top5"] = cat.match(a.target, a.op, " > ".join(a.path)).candidates
                candidates.append(item)
        rows.append({
            "row_id": (row or {}).get("id"), "query": q, "siis_title": (row or {}).get("siis_response", {}).get("title"),
            "relevant": bool(ctx), "expected_actions": expected, "reviewed": False, "notes": "",
            "_engine_fallback": env["meta"].get("fallback"), "_candidates": candidates,
        })
    out = ROOT / "eval" / "gold" / "d1_draft.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out} ({len(rows)} rows). Copy to d1_gold.json, correct, and set reviewed=true.")


if __name__ == "__main__":
    main()
