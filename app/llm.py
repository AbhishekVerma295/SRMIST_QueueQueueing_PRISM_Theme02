"""Provider-agnostic LLM adapter (JSON-only calls, temperature 0).

Providers:
  gemini  - Google Gemini API (generateContent with responseSchema). Default.
  openai  - any OpenAI-compatible chat endpoint (OpenAI, Groq, ...), JSON mode.
If no key is configured, or a call fails, callers get None and fall back to the offline rules path.
Token usage is returned so cost per query can be reported (rates come from .env, per 1M tokens).
"""
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field

import httpx

from . import config  # noqa: F401  (loads .env before the settings below are read)

log = logging.getLogger("llm")

PROVIDER = os.getenv("LLM_PROVIDER", "gemini" if os.getenv("LLM_API_KEY") else "").strip().lower()
API_KEY = os.getenv("LLM_API_KEY", "").strip()
MODEL = os.getenv("LLM_MODEL", "").strip()
BASE_URL = os.getenv("LLM_BASE_URL", "").strip()        # openai-compatible only, e.g. https://api.groq.com/openai/v1
TIMEOUT = float(os.getenv("LLM_TIMEOUT_S", "7"))
PRICE_IN = float(os.getenv("LLM_PRICE_IN_PER_1M", "0.10"))   # USD per 1M input tokens  (set from the provider's pricing page)
PRICE_OUT = float(os.getenv("LLM_PRICE_OUT_PER_1M", "0.40"))  # USD per 1M output tokens
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


@dataclass
class Usage:
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    ms: float = 0.0
    errors: list = field(default_factory=list)
    model: str | None = None        # model that actually answered (after fallbacks)

    @property
    def cost_usd(self) -> float:
        return round(self.tokens_in / 1e6 * PRICE_IN + self.tokens_out / 1e6 * PRICE_OUT, 6)


_client: httpx.Client | None = None
_model_lock = threading.Lock()
_resolved_model: str | None = None
_chain: list[str] = []          # fallback order of models (Gemini), best first
_sticky: str | None = None      # last model that answered; tried first next time
THINKING = os.getenv("LLM_THINKING", "minimal").strip().lower()   # batch compile may use "low" for more careful extraction
BUDGET_S = float(os.getenv("LLM_BUDGET_S", "7.0"))   # total time for one logical call incl. retries/fallbacks
RETRYABLE = {404, 408, 429, 500, 502, 503, 504}


def enabled() -> bool:
    return bool(PROVIDER and API_KEY)


def _http() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(timeout=TIMEOUT)
    return _client


def model_name() -> str:
    """Configured model, or (Gemini) the first available Flash-Lite / Flash model that supports generateContent."""
    global _resolved_model
    if MODEL:
        return MODEL
    if _resolved_model:
        return _resolved_model
    with _model_lock:
        if _resolved_model is None:
            _resolved_model = "gemini-flash-lite-latest"
            if PROVIDER == "gemini" and API_KEY:
                try:
                    r = _http().get(f"{GEMINI_BASE}/models", headers={"x-goog-api-key": API_KEY}, params={"pageSize": 200})
                    names = [m["name"].split("/", 1)[1] for m in r.json().get("models", [])
                             if "generateContent" in m.get("supportedGenerationMethods", [])]
                    # prefer the newest *versioned* models (reproducible) over moving aliases like "-latest";
                    # Flash-Lite first (cheaper, higher free quota), then Flash as fallbacks
                    for pref in ("flash-lite", "flash"):
                        versioned = sorted(((float(m.group(1)), n) for n in names
                                            if (m := re.fullmatch(rf"gemini-(\d+(?:\.\d+)?)-{pref}", n))), reverse=True)
                        _chain.extend(n for _, n in versioned[:3])
                    if _chain:
                        _resolved_model = _chain[0]
                except Exception as exc:  # network issues: keep the alias
                    log.warning("model discovery failed: %s", exc)
    return _resolved_model


def _parse_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)      # models sometimes wrap JSON in fences
    return json.loads(text)


_dead: set = set()              # models that returned 404 (unavailable) or a quota 429 this process: skip them


def _candidates() -> list[str]:
    model_name()                                   # populates the discovery chain once
    order = ([MODEL] if MODEL else []) + ([_sticky] if _sticky else []) + _chain + ([_resolved_model] if _resolved_model else [])
    return [m for m in dict.fromkeys(m for m in order if m) if m not in _dead]


def _gemini_json(system: str, user: str, schema: dict, usage: "Usage", max_tokens: int, t0: float):
    """Tries models in fallback order until one answers, within BUDGET_S. Thinking is minimised on Gemini 3.x."""
    global _sticky
    last_err = "no model available"
    # each model gets a few tries with backoff on 503 "high demand" (transient), bounded by the time budget
    attempts = [(m, k) for m in _candidates() for k in range(3 if BUDGET_S >= 20 else 1)]
    for model, k in attempts:
        if model in _dead:
            continue
        remaining = BUDGET_S - (time.perf_counter() - t0)
        if remaining < 1.0:
            break
        if k > 0:
            time.sleep(min(2.0 * k, max(0.0, remaining - 1.0)))
            remaining = BUDGET_S - (time.perf_counter() - t0)
        gc = {"temperature": 0, "seed": 7, "maxOutputTokens": max_tokens,
              "responseMimeType": "application/json", "responseSchema": schema}
        if re.match(r"gemini-3", model):
            gc["thinkingConfig"] = {"thinkingLevel": THINKING}
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}], "generationConfig": gc}
        try:
            r = _http().post(f"{GEMINI_BASE}/models/{model}:generateContent", headers={"x-goog-api-key": API_KEY},
                             json=body, timeout=max(1.0, remaining))
            if r.status_code == 400 and "thinking" in r.text.lower():      # model rejects the thinking setting
                gc.pop("thinkingConfig", None)
                r = _http().post(f"{GEMINI_BASE}/models/{model}:generateContent", headers={"x-goog-api-key": API_KEY},
                                 json=body, timeout=max(1.0, remaining))
            if r.status_code in RETRYABLE:
                last_err = f"{model}: HTTP {r.status_code}"
                usage.errors.append(last_err)
                if r.status_code == 404 or (r.status_code == 429 and "quota" in r.text.lower()):
                    _dead.add(model)                  # unavailable / daily quota spent: stop trying it
                continue
            r.raise_for_status()
            data = r.json()
            parts = data["candidates"][0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            meta = data.get("usageMetadata", {})
            usage.tokens_in += int(meta.get("promptTokenCount", 0))
            usage.tokens_out += int(meta.get("candidatesTokenCount", 0)) + int(meta.get("thoughtsTokenCount", 0))
            usage.calls += 1
            usage.model = model
            _sticky = model
            return _parse_json(text)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_err = f"{model}: {type(exc).__name__}"
            usage.errors.append(last_err)
        except (KeyError, IndexError, ValueError) as exc:                 # empty/blocked/non-JSON answer
            last_err = f"{model}: bad response {type(exc).__name__}"
            usage.errors.append(last_err)
    raise RuntimeError(last_err)


def call_json(system: str, user: str, schema: dict, usage: Usage, max_tokens: int = 2048) -> dict | None:
    """One JSON-mode call. Returns the parsed object, or None on any failure (caller falls back)."""
    if not enabled():
        return None
    t = time.perf_counter()
    try:
        if PROVIDER == "gemini":
            return _gemini_json(system, user, schema, usage, max_tokens, t)
        else:
            base = BASE_URL or "https://api.openai.com/v1"
            body = {"model": model_name(), "temperature": 0, "seed": 7, "max_tokens": max_tokens,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "system", "content": system + "\nReturn only JSON matching this schema: " + json.dumps(schema)},
                                 {"role": "user", "content": user}]}
            r = _http().post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {API_KEY}"}, json=body)
            r.raise_for_status()
            data = r.json()
            text = data["choices"][0]["message"]["content"]
            u = data.get("usage", {})
            usage.tokens_in += int(u.get("prompt_tokens", 0))
            usage.tokens_out += int(u.get("completion_tokens", 0))
        usage.calls += 1
        return _parse_json(text)
    except Exception as exc:
        usage.errors.append(f"{type(exc).__name__}: {str(exc)[:160]}")
        log.warning("LLM call failed: %s", exc)
        return None
    finally:
        usage.ms += (time.perf_counter() - t) * 1000
