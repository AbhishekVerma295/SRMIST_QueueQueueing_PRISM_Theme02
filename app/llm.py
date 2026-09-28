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

    @property
    def cost_usd(self) -> float:
        return round(self.tokens_in / 1e6 * PRICE_IN + self.tokens_out / 1e6 * PRICE_OUT, 6)


_client: httpx.Client | None = None
_model_lock = threading.Lock()
_resolved_model: str | None = None


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
                    for pref in ("flash-lite", "flash"):
                        cands = sorted((n for n in names if pref in n and "preview" not in n and "image" not in n and "tts" not in n), reverse=True)
                        if cands:
                            _resolved_model = cands[0]
                            break
                except Exception as exc:  # network issues: keep the alias
                    log.warning("model discovery failed: %s", exc)
    return _resolved_model


def _parse_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)      # models sometimes wrap JSON in fences
    return json.loads(text)


def call_json(system: str, user: str, schema: dict, usage: Usage, max_tokens: int = 2048) -> dict | None:
    """One JSON-mode call. Returns the parsed object, or None on any failure (caller falls back)."""
    if not enabled():
        return None
    t = time.perf_counter()
    try:
        if PROVIDER == "gemini":
            body = {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0, "seed": 7, "maxOutputTokens": max_tokens,
                                     "responseMimeType": "application/json", "responseSchema": schema},
            }
            r = _http().post(f"{GEMINI_BASE}/models/{model_name()}:generateContent", headers={"x-goog-api-key": API_KEY}, json=body)
            r.raise_for_status()
            data = r.json()
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
            meta = data.get("usageMetadata", {})
            usage.tokens_in += int(meta.get("promptTokenCount", 0))
            usage.tokens_out += int(meta.get("candidatesTokenCount", 0))
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
