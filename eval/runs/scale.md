# Scalability benchmark
Generated 2026-10-22 15:47 on 16 vCPU / Windows 11 / Python 3.12.10. Script: `eval/scale_bench.py`. All runs use copies of the shipped cache; nothing in the repo is modified.

## 1. Adding new scenarios (no code changes)
D2b's 8 relevant articles (battery, charging, display, performance, Bluetooth, camera) were added as brand-new scenarios.

| Mode | Articles | Code changes | Plans made | Compile time mean / max | Cost per article | Exact repeat P95 | Rewordings answered (right plan) | Rewording P95 | False hits |
|---|---|---|---|---|---|---|---|---|---|
| rules | 8 | 0 | 8/8 | 306 / 1404 ms | $0.00000 | 0.2 ms | 6/8 (6) | 48.4 ms | 0 of 5 |
| llm | 8 | 0 | 8/8 | 2597 / 3437 ms | $0.00040 | 0.1 ms | 7/8 (7) | 31.9 ms | 0 of 5 |

## 2. Catalog reach
Each of the 556 phone Settings entries (of 578; 21 appliance entries and the placeholder excluded) was searched by its own feature name and operation.

| Found itself | Found its duplicate | Different entry | Declined | Reached | Match P50 / P95 |
|---|---|---|---|---|---|
| 534 | 21 | 0 | 1 | **99.8%** | 16.1 / 20.8 ms |

## 3. Cache size
synthetic keys are random unit vectors (they measure speed, not accuracy).

| Stored keys | Lookup P50 | Lookup P95 | Vector memory | Load time | Real answers unchanged |
|---|---|---|---|---|---|
| 1,256 | 16.8 ms | 21.6 ms | 1.9 MB | 0.01 s | 34/34 |
| 10,256 | 17.5 ms | 21.6 ms | 15.8 MB | 0.05 s | 34/34 |
| 100,256 | 25.6 ms | 39.2 ms | 154.0 MB | 0.52 s | 34/34 |

## 4. Concurrent load (real HTTP API)
Traffic: 20 official lines with article (exact hits), 24 held-out rewordings, 10 unrelated complaints; no LLM. Server: 1 uvicorn worker, CPU, pipeline in a worker thread (4 at a time); client in a separate process.

| Concurrent clients | Requests | Errors | Requests/s | Latency P50 | Latency P95 |
|---|---|---|---|---|---|
| 1 | 300 | 0 | 51.1 | 21.0 ms | 54.0 ms |
| 10 | 300 | 0 | 95.5 | 93.6 ms | 199.4 ms |
| 50 | 300 | 0 | 97.8 | 494.8 ms | 642.1 ms |

Before the request handler moved to a worker thread (22 Oct, same traffic):

| Concurrent clients | Errors | Requests/s | Latency P95 |
|---|---|---|---|
| 1 | 0 | 50.9 | 51.9 ms |
| 10 | 0 | 53.7 | 319.9 ms |
| 50 | 0 | 58.3 | 1042.0 ms |
