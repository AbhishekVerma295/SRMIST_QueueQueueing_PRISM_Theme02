"""Generates results.jsonl: one Appendix-B line per input.txt line.

In-process by default; pass --url http://localhost:8000 to go through the running API (e.g. Docker).
Each input line is sent with its SIIS reference text (matched by fuzzy text match).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import kit, validators  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="base URL of a running API; omit to run in-process")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "results.jsonl"))
    ap.add_argument("--no-cache", action="store_true", help="bypass the cache (in-process only)")
    args = ap.parse_args()

    if args.url:
        import httpx
        client = httpx.Client(base_url=args.url, timeout=60)
        call = lambda q, s: client.post("/v1/troubleshoot", json={"query": q, **({"siis_response": s} if s else {})}).json()  # noqa: E731
    else:
        from app import pipeline
        call = lambda q, s: pipeline.troubleshoot(q, s, use_cache=not args.no_cache)  # noqa: E731

    bad = 0
    with open(args.out, "w", encoding="utf-8") as f:
        for i, q in enumerate(kit.input_queries(), 1):
            row = kit.match_siis(q)
            env = call(q, row["siis_response"] if row else None)
            problems = validators.check_envelope(env)
            bad += bool(problems)
            f.write(json.dumps(env, ensure_ascii=False) + "\n")
            print(f"{i:2} {(row or {}).get('id', '-'):7} {env['meta'].get('fallback') or 'plan':9} "
                  f"{env['meta']['latency_ms']:5} ms  hit={env['meta']['cache_hit']}  {'VIOLATIONS ' + str(problems) if problems else 'ok'}")
    print(f"wrote {args.out}; lines with contract violations: {bad}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
