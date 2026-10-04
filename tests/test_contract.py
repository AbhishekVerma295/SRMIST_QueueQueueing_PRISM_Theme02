"""Unit tests for the contract helpers, validators and the deeplink resolver."""
import copy

import pytest

from app import catalog, config, kit, validators
from app.text import fit_description, has_url, is_sentence_case, is_title_case, scrub_urls, title_case


@pytest.mark.parametrize("body", ["fix it", "turn on touch sensitivity", "open the navigation bar settings page directly now please ok",
                                  "It will restart and refresh your device", "rule out a faulty charger and cable issues today"])
def test_description_always_5_to_7_words_starting_it_will(body):
    d = fit_description(body)
    assert d.startswith("It will") and 5 <= len(d.split()) <= 7, d


def test_title_and_sentence_case():
    assert title_case("attempt to power on") == "Attempt to Power On"
    assert is_title_case("Enable Touch Sensitivity") and not is_title_case("Enable touch sensitivity")
    assert is_sentence_case("Blank screen display") and not is_sentence_case("Blank Screen Display")


@pytest.mark.parametrize("text", ["Visit samsung.com/support for help", "See https://example.org/x", "go to www.samsung.com",
                                  "Read [the guide](http://x.y/z) now"])
def test_url_scrubbing(text):
    out = scrub_urls(text)
    assert not has_url(out), out


def test_official_schema_imported_unchanged():
    assert hasattr(kit.schema(), "ContextDeeplinkResponse")
    assert validators.check_schema({"contexts": []}) == []


@pytest.mark.parametrize("target,op,expected_message", [
    ("Touch sensitivity", "on", "Enable Touch sensitivity"),
    ("Navigation bar", "view", "View Navigation bar"),
    ("Power saving", "on", "Enable Power saving"),
    ("Power saving", "off", "Disable Power saving"),
    ("Optimize now", None, "Optimize Device Performance"),     # button label alias
])
def test_resolver_picks_exact_screen_and_operation(target, op, expected_message):
    m = catalog.get().match(target, op)
    assert m.accepted and m.entry.raw["message"] == expected_message


def test_resolver_rejects_unrelated_target():
    assert not catalog.get().match("Pro Video shutter speed", "update").accepted


def test_catalog_never_searches_appliances():
    assert all(not e.appliance for e in catalog.get().searchable)


def _goal():
    e = catalog.get().match("Touch sensitivity", "on").entry
    return {"goal": "Follow these steps to perform this Touchscreen Troubleshooting", "title": "Touchscreen response issues", "score": 0.8,
            "actions": [
                {"actionName": "Enable Touch Sensitivity", "description": "It will turn on touch sensitivity", "category": "auto",
                 "stepGroups": [{"steps": ["Navigate to and open Settings."], "actionableDeeplink": catalog.Catalog.actionable(e),
                                 "validationDeeplink": catalog.Catalog.validation(e)}]},
                {"actionName": "Restart Your Device", "description": "It will restart and refresh your device", "category": "critical",
                 "stepGroups": [{"steps": ["Press and hold the Power button."], "actionableDeeplink": None, "validationDeeplink": None}]},
            ]}


def test_valid_goal_passes():
    assert validators.check_goal(_goal()) == []


@pytest.mark.parametrize("mutate,needle", [
    (lambda g: g.update(goal="Steps for touch"), "goal syntax"),
    (lambda g: g.update(title="Touchscreen"), "title"),
    (lambda g: g["actions"][0].update(description="It will turn on the touch sensitivity feature now"), "description"),
    (lambda g: g["actions"][0].update(actionName="enable touch sensitivity"), "Title Case"),
    (lambda g: g["actions"].reverse(), "after a critical"),
    (lambda g: g["actions"][0]["stepGroups"][0]["actionableDeeplink"].update(deeplink="voiceassist://masked/act/0000000000"), "not in catalog"),
    (lambda g: g["actions"][0]["stepGroups"][0]["actionableDeeplink"].update(message="Made up"), "verbatim"),
    (lambda g: g["actions"][1].update(category="manual") or g["actions"][1]["stepGroups"][0].update(actionableDeeplink=g["actions"][0]["stepGroups"][0]["actionableDeeplink"]), "manual action carries"),
    (lambda g: g["actions"][1]["stepGroups"][0]["steps"].append("Visit samsung.com/support."), "URL leak"),
])
def test_validator_catches_each_violation(mutate, needle):
    g = copy.deepcopy(_goal())
    mutate(g)
    assert any(needle in v for v in validators.check_goal(g)), validators.check_goal(g)


def test_dummy_deeplink_is_valid_catalog_uri():
    cat = catalog.get()
    assert cat.dummy_uri == "voiceassist://dummy_positive" and cat.dummy_uri in cat.valid_uris


def test_option_inside_a_catalog_screen_opens_that_screen_not_a_placeholder():
    from app.compile import compile_action
    from app.extract_rules import IRAction
    a = IRAction(kind="settings", heading="Use buttons", path=["Display", "Navigation bar", "Buttons"], op="off",
                 steps=["Go to Settings.", "Tap Display.", "Tap Navigation bar.", "Select Buttons."])
    c = compile_action(a, catalog.get())
    assert c.data["stepGroups"][0]["actionableDeeplink"]["message"] == "View Navigation bar"
    assert c.data["actionName"] == "Open Navigation Bar Settings"
