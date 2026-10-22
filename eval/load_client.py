"""Load-test client, run as its own process so it does not compete with the server for Python's GIL.

    python eval/load_client.py <base_url> <concurrency> <requests_json_file>

Prints one JSON line: {concurrency, requests, errors, cache_hits, req_per_s, latency_ms_p50, latency_ms_p95}.
"""
import asyncio
import json
import sys
import time

import httpx


def pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))], 1) if xs else None


async def run(base: str, conc: int, reqs: list) -> dict:
    sem = asyncio.Semaphore(conc)
    lat, errors, hits = [], 0, 0
    async with httpx.AsyncClient(base_url=base, timeout=60, limits=httpx.Limits(max_connections=conc)) as client:
        async def one(body):
            nonlocal errors, hits
            async with sem:
                t = time.perf_counter()
                try:
                    r = await client.post("/v1/troubleshoot", json=body)
                    data = r.json()
                    ok = r.status_code == 200 and "response" in data
                    hits += bool(data.get("meta", {}).get("cache_hit"))
                except Exception:
                    ok = False
                lat.append((time.perf_counter() - t) * 1000)
                errors += not ok
        t0 = time.perf_counter()
        await asyncio.gather(*(one(b) for b in reqs))
        wall = time.perf_counter() - t0
    return {"concurrency": conc, "requests": len(reqs), "errors": errors, "cache_hits": hits,
            "req_per_s": round(len(reqs) / wall, 1), "latency_ms_p50": pct(lat, 50), "latency_ms_p95": pct(lat, 95)}


if __name__ == "__main__":
    base, conc, path = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    reqs = json.loads(open(path, encoding="utf-8").read())
    print(json.dumps(asyncio.run(run(base, conc, reqs))))
