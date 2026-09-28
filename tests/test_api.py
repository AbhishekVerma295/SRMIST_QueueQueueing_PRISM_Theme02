"""End-to-end API tests against the Theme 02 contract."""
import json
import pytest
from fastapi.testclient import TestClient

from app import kit, pipeline, validators
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _row(i=21):
    return next(r for r in kit.siis_rows() if r["id"] == f"row_{i}")


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_siis_as_object_and_as_string_give_same_plan(client):
    r = _row()
    a = client.post("/v1/troubleshoot", json={"query": r["original_query"], "siis_response": r["siis_response"]}).json()
    pipeline.get_cache().clear()
    b = client.post("/v1/troubleshoot", json={"query": r["original_query"],
                                              "siis_response": r["siis_response"]["title"] + "\n" + r["siis_response"]["content"]}).json()
    assert validators.check_envelope(a) == [] and validators.check_envelope(b) == []
    assert a["response"]["contexts"] and b["response"]["contexts"]
    assert [x["actionName"] for x in a["response"]["contexts"][0]["actions"]] == [x["actionName"] for x in b["response"]["contexts"][0]["actions"]]


def test_envelope_shape_matches_appendix_b(client):
    r = _row()
    env = client.post("/v1/troubleshoot", json={"query": r["original_query"], "siis_response": r["siis_response"]}).json()
    assert set(env) == {"query", "query_variations", "response", "meta"}
    assert {"latency_ms", "cache_hit", "model", "cost_usd"} <= set(env["meta"])
    assert 8 <= len(env["query_variations"]) <= 10


def test_repeat_is_cache_hit_and_identical(client):
    r = _row(2)
    body = {"query": r["original_query"], "siis_response": r["siis_response"]}
    first = client.post("/v1/troubleshoot", json=body).json()
    second = client.post("/v1/troubleshoot", json=body).json()
    assert second["meta"]["cache_hit"] is True and second["meta"]["cost_usd"] == 0.0
    assert first["response"] == second["response"]


def test_no_siis_and_no_cache_hit_returns_no_siis_context(client):
    env = client.post("/v1/troubleshoot", json={"query": "My smartwatch strap keeps squeaking loudly"}).json()
    assert env["response"]["contexts"] == [] and env["meta"]["fallback"] == "no_siis_context"


def test_irrelevant_reference_text_returns_no_match(client):
    env = client.post("/v1/troubleshoot", json={"query": "My Galaxy S23 battery dies really fast after the update",
                                                 "siis_response": _row(8)["siis_response"]}).json()
    assert env["response"]["contexts"] == [] and env["meta"]["fallback"] == "no_match"


def test_injected_urls_in_reference_text_never_leak(client):
    siis = dict(_row(21)["siis_response"])
    siis["content"] = siis["content"].replace("go to Settings", "visit https://evil.example.com or www.samsung.com/support and go to Settings")
    env = client.post("/v1/troubleshoot", json={"query": "touch screen laggy and delayed on my Galaxy S22", "siis_response": siis}).json()
    assert validators.check_envelope(env) == []


@pytest.mark.parametrize("payload,code", [(b"not json", 400), (b'{"siis_response": "x"}', 422), (b'{"query": ""}', 422)])
def test_bad_requests_still_return_json_envelope(client, payload, code):
    res = client.post("/v1/troubleshoot", content=payload, headers={"content-type": "application/json"})
    assert res.status_code == code
    assert res.json()["meta"]["fallback"] == "invalid_request"


def test_every_official_input_line_is_contract_valid():
    for q in kit.input_queries():
        row = kit.match_siis(q)
        env = pipeline.troubleshoot(q, row["siis_response"] if row else None, use_cache=False)
        assert validators.check_envelope(env) == [], (q[:60], validators.check_envelope(env))


def test_multi_intent_line_splits_into_intents():
    line = next(q for q in kit.input_queries() if q.startswith('1. "My Nexa Fold X1'))
    env = pipeline.troubleshoot(line, kit.match_siis(line)["siis_response"], debug=True, use_cache=False)
    assert len(env["trace"]["intents"]) == 3


def test_deterministic_cold_path():
    r = _row(20)
    a = pipeline.troubleshoot(r["original_query"], r["siis_response"], use_cache=False)
    b = pipeline.troubleshoot(r["original_query"], r["siis_response"], use_cache=False)
    assert a["response"] == b["response"] and a["query_variations"] == b["query_variations"]


def test_official_kit_outputs_stay_brand_neutral_and_dummy_text_is_5_to_7_words():
    """The official kit is de-branded (TechCorp / Nexa / VoiceAssist); we must not inject real brand names,
    and the DL-DUMMY entry asks for a 5-7 word description/message naming the concrete screen."""
    from app import catalog
    dummy = catalog.get().dummy_uri
    for q in kit.input_queries():
        row = kit.match_siis(q)
        env = pipeline.troubleshoot(q, row["siis_response"] if row else None, use_cache=False)
        blob = json.dumps(env["response"]) + " ".join(env["query_variations"])
        for word in ("Samsung", "Galaxy", "bixby://", "Bixby"):
            assert word not in blob, (word, q[:50])
        for c in env["response"]["contexts"]:
            for a in c["actions"]:
                link = a["stepGroups"][0].get("actionableDeeplink")
                if link and link["deeplink"] == dummy:
                    assert 5 <= len(link["description"].split()) <= 7 and 5 <= len(link["message"].split()) <= 7, link
