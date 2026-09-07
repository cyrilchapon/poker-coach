import json
from pathlib import Path

import pytest

from pokercoach import brief

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_brief_postflop_smoke():
    raw = load_fixture("hu_flop_cbet.json")
    out = brief.compute(raw)
    assert out["gate"] in ("G0", "G1", "G2", "G3", "G4", "G5")
    assert "state" in out and "hand" in out and "texture" in out and "line" in out and "budget" in out
    assert out["state"]["street"] == "flop"


def test_brief_postflop_with_villain_archetype():
    raw = load_fixture("hu_flop_cbet.json")
    out = brief.compute(raw, villain_archetype="fish")
    assert "exploit" in out
    assert out["exploit"]["archetype"] == "fish"


def test_brief_preflop_clear_open_hits_g1():
    raw = load_fixture("hu_flop_cbet.json")
    raw = dict(raw)
    raw["streets"] = {
        "preflop": {"actions": [
            {"seat": 0, "action": "post", "amount": 0.5},
            {"seat": 1, "action": "post", "amount": 1.0},
        ]},
        "flop": None, "turn": None, "river": None,
    }
    raw["to_act"] = 0
    raw["seats"][0]["cards"] = ["A♠", "K♦"]  # premium hand, clearly in any RFI range
    out = brief.compute(raw)
    assert out["state"]["street"] == "preflop"
    assert out["gate"] in ("G1", "G5")  # AK is in range for HU BTN/SB open either way


def test_brief_never_crashes_on_river():
    raw = load_fixture("hu_flop_cbet.json")
    raw = dict(raw)
    raw["streets"]["flop"]["actions"].append({"seat": 0, "action": "call", "amount": 4.0})
    raw["streets"]["turn"] = {"board": ["T♠", "9♥", "2♣", "5♦"], "actions": [
        {"seat": 1, "action": "check", "amount": 0}, {"seat": 0, "action": "check", "amount": 0}]}
    raw["streets"]["river"] = {"board": ["T♠", "9♥", "2♣", "5♦", "8♥"], "actions": [
        {"seat": 1, "action": "bet", "amount": 6.0}]}
    raw["to_act"] = 0
    out = brief.compute(raw)
    assert out["state"]["street"] == "river"
    assert out["hand"]["outs"] is None  # plus de tirage possible à la river
