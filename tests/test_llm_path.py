"""LLM path tests with a fake LLM (no key or network needed).

Checks that the code, not the model, guarantees grounding, the contract and graceful fallback.
"""
import pytest

from app import kit, llm, llm_stages, pipeline, validators


def _row(i):
    return next(r for r in kit.siis_rows() if r["id"] == f"row_{i}")


def _sid(content: str, needle: str) -> int:
    """1-based sentence number of the first sentence containing `needle`."""
    _, sents = llm_stages.numbered_sentences(content)
    return next(i + 1 for i, s in enumerate(sents) if needle.lower() in s.lower())


@pytest.fixture
def fake_llm(monkeypatch):
    """Installs a fake LLM; `responses` maps 'enrich'/'extract' to the JSON it should return."""
    responses = {}

    def call_json(system, user, schema, usage, max_tokens=2048):
        usage.calls += 1
        usage.tokens_in += 1000
        usage.tokens_out += 200
        key = "enrich" if system is llm_stages.ENRICH_SYSTEM else "extract"
        return responses.get(key)

    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "call_json", call_json)
    monkeypatch.setattr(llm, "model_name", lambda: "fake-llm")
    return responses


def _enrich_ok(n=10):
    regs = llm_stages.REGISTERS
    return {"canonical_query": "Touchscreen input lag on Nexa X1", "variations": [{"register": regs[i % 5], "text": f"variation number {i} about laggy touch"} for i in range(n)]}


def test_grounded_steps_kept_and_invented_steps_dropped(fake_llm):
    r = _row(21)
    content = r["siis_response"]["content"]
    s_touch = _sid(content, "tap the switch next to Touch sensitivity")
    fake_llm["enrich"] = _enrich_ok()
    fake_llm["extract"] = {"problems": [{
        "text": r["original_query"], "topic": "Touchscreen", "title": "Touchscreen response issues", "request_type": "Troubleshooting",
        "relevant": "yes", "reason": "article is about touchscreen issues",
        "actions": [
            {"kind": "settings", "critical_kind": "none", "name": "Enable Touch Sensitivity", "benefit": "turn on touch sensitivity",
             "settings_path": ["Display", "Touch sensitivity"], "toggle": "Touch sensitivity", "op": "on",
             "steps": [{"text": "Navigate to and open Settings.", "cites": [s_touch]},
                       {"text": "Tap Display.", "cites": [s_touch]},
                       {"text": "Tap the switch next to Touch sensitivity.", "cites": [s_touch]},
                       {"text": "Download the TouchFix Pro app from the store.", "cites": [s_touch]}]},     # invented -> dropped
            {"kind": "manual", "name": "Recalibrate Digitizer", "benefit": "recalibrate the digitizer",
             "steps": [{"text": "Dial *#0*# to open the hidden digitizer calibration menu.", "cites": [1]}]},  # invented -> action dropped
        ]}]}
    env = pipeline.troubleshoot(r["original_query"], r["siis_response"], debug=True, use_cache=False)
    assert validators.check_envelope(env) == []
    actions = env["response"]["contexts"][0]["actions"]
    assert [a["actionName"] for a in actions] == ["Enable Touch Sensitivity"]
    steps = actions[0]["stepGroups"][0]["steps"]
    assert not any("TouchFix" in s for s in steps)
    assert actions[0]["stepGroups"][0]["actionableDeeplink"]["message"] == "Enable Touch sensitivity"   # mapping stays deterministic
    assert len(env["trace"]["llm_extract"]["dropped_ungrounded_steps"]) == 2
    assert env["meta"]["model"].startswith("fake-llm") and env["meta"]["cost_usd"] > 0
    assert 8 <= len(env["query_variations"]) <= 10


def test_llm_says_not_relevant_gives_no_match(fake_llm):
    r = _row(7)
    fake_llm["enrich"] = _enrich_ok()
    fake_llm["extract"] = {"problems": [{"text": r["original_query"], "relevant": "no", "reason": "multi window article", "actions": []}]}
    env = pipeline.troubleshoot(r["original_query"], r["siis_response"], use_cache=False)
    assert env["response"]["contexts"] == [] and env["meta"]["fallback"] == "no_match"


def test_llm_failure_falls_back_to_rules(fake_llm):
    r = _row(21)
    # fake returns None for both calls -> outage
    env = pipeline.troubleshoot(r["original_query"], r["siis_response"], use_cache=False)
    assert validators.check_envelope(env) == []
    assert env["response"]["contexts"] and "llm fallback" in env["meta"]["model"]


def test_llm_text_cannot_break_the_contract(fake_llm):
    r = _row(2)
    content = r["siis_response"]["content"]
    s_restart = _sid(content, "Volume down button simultaneously")
    fake_llm["enrich"] = {"canonical_query": "see https://evil.example.com", "variations": [{"register": "formal", "text": "visit www.evil.com now"}]}
    fake_llm["extract"] = {"problems": [{
        "text": r["original_query"], "topic": "Black Screen Troubleshooting Issue", "title": "Your Screen Is Totally Black Now",
        "request_type": "Troubleshooting", "relevant": "yes",
        "actions": [{"kind": "critical", "critical_kind": "force_restart", "name": "force restart!!", "benefit": "a very long benefit phrase that goes on and on",
                     "steps": [{"text": "Press and hold the Power button and the Volume down button simultaneously for at least 20 seconds. See https://x.io",
                                "cites": [s_restart]}]}]}]}
    env = pipeline.troubleshoot(r["original_query"], r["siis_response"], use_cache=False)
    assert validators.check_envelope(env) == [], validators.check_envelope(env)
    g = env["response"]["contexts"][0]
    assert g["goal"] == "Follow these steps to perform this Black Screen Troubleshooting"
    assert g["title"] == "Blank screen display"          # invalid LLM title replaced by the rules title
    assert all("http" not in v and "www." not in v for v in env["query_variations"])


def test_cold_path_output_is_cached_for_paraphrases(fake_llm):
    r = _row(21)
    fake_llm["enrich"] = _enrich_ok()
    fake_llm["extract"] = {"problems": [{"text": r["original_query"], "topic": "Touchscreen", "title": "Touchscreen response issues",
                                         "request_type": "Troubleshooting", "relevant": "yes",
                                         "actions": [{"kind": "escalation", "name": "Contact Support", "benefit": "get expert help",
                                                      "steps": [{"text": "Reach out to Customer Support for further assistance.",
                                                                 "cites": [_sid(r["siis_response"]["content"], "reach out to Customer Support")]}]}]}]}
    pipeline.get_cache().clear()
    first = pipeline.troubleshoot(r["original_query"], r["siis_response"])
    again = pipeline.troubleshoot(r["original_query"], r["siis_response"])
    assert first["meta"]["cache_hit"] is False and again["meta"]["cache_hit"] is True
    assert again["meta"]["cost_usd"] == 0.0 and again["response"] == first["response"]


def test_llm_abstains_but_rules_find_a_grounded_plan(fake_llm):
    r = _row(21)
    fake_llm["enrich"] = _enrich_ok()
    fake_llm["extract"] = {"problems": [{"text": r["original_query"], "relevant": "no", "reason": "unsure", "actions": []}]}
    env = pipeline.troubleshoot(r["original_query"], r["siis_response"], use_cache=False)
    assert validators.check_envelope(env) == []
    assert env["response"]["contexts"] and "llm abstained" in env["meta"]["model"]
