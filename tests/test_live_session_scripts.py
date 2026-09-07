"""Tests pour les scripts de convenance de session (skills/live-session/scripts/),
volontairement HORS du package pokercoach — importés ici par chemin de fichier."""
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from pokercoach.state import StateError, validate_and_load

SCRIPTS_DIR = Path(__file__).parent.parent / "skills" / "live-session" / "scripts"
FIXTURES = Path(__file__).parent / "fixtures"


def _load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


advance_street = _load_module("advance_street")
new_hand = _load_module("new_hand")


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# --- advance_street.py ------------------------------------------------------

def test_advance_rejects_unclosed_action():
    raw = load_fixture("hu_flop_cbet.json")  # seat1 bet 4.0, hero hasn't called yet
    with pytest.raises(StateError, match="non close"):
        advance_street.advance(copy.deepcopy(raw), "5♦")


def test_advance_opens_the_next_street_with_correct_board_and_to_act():
    raw = load_fixture("hu_flop_cbet.json")
    raw = copy.deepcopy(raw)
    raw["streets"]["flop"]["actions"].append({"seat": 0, "action": "call", "amount": 4.0})

    updated = advance_street.advance(raw, "5♦")

    assert updated["streets"]["turn"]["board"] == ["T♠", "9♥", "2♣", "5♦"]
    assert updated["streets"]["turn"]["actions"] == []
    # postflop order in HU: BB acts first -> seat 1
    assert updated["to_act"] == 1


def test_advance_rejects_wrong_card_count():
    raw = load_fixture("hu_flop_cbet.json")
    raw = copy.deepcopy(raw)
    raw["streets"]["flop"]["actions"].append({"seat": 0, "action": "call", "amount": 4.0})
    with pytest.raises(StateError, match="1 carte"):
        advance_street.advance(raw, "5♦,3♣")


def test_advance_rejects_duplicate_card():
    raw = load_fixture("hu_flop_cbet.json")
    raw = copy.deepcopy(raw)
    raw["streets"]["flop"]["actions"].append({"seat": 0, "action": "call", "amount": 4.0})
    with pytest.raises(StateError, match="double|connue"):
        advance_street.advance(raw, "T♠")


def test_advance_rejects_from_river():
    raw = load_fixture("hu_flop_cbet.json")
    raw = copy.deepcopy(raw)
    raw["streets"]["flop"]["actions"].append({"seat": 0, "action": "call", "amount": 4.0})
    raw["streets"]["turn"] = {"board": ["T♠", "9♥", "2♣", "5♦"], "actions": [
        {"seat": 1, "action": "check", "amount": 0}, {"seat": 0, "action": "check", "amount": 0}]}
    raw["streets"]["river"] = {"board": ["T♠", "9♥", "2♣", "5♦", "8♥"], "actions": [
        {"seat": 1, "action": "check", "amount": 0}, {"seat": 0, "action": "check", "amount": 0}]}
    with pytest.raises(StateError, match="river"):
        advance_street.advance(raw, "2♦")


def test_advance_allows_all_in_seats_to_have_a_lower_contribution():
    # seat1 shoves for less than the pot would require in a non-all-in call;
    # the action is still "closed" because all-in seats are excluded from
    # the equal-contribution check.
    raw = load_fixture("hu_flop_cbet.json")
    raw = copy.deepcopy(raw)
    raw["streets"]["flop"]["actions"] = [
        {"seat": 1, "action": "bet", "amount": 4.0},
        {"seat": 0, "action": "raise", "amount": 20.0},
        {"seat": 1, "action": "allin", "amount": 10.0},  # shoves for less
    ]
    raw["seats"][1]["status"] = "allin"
    updated = advance_street.advance(raw, "5♦")
    assert updated["streets"]["turn"]["board"][-1] == "5♦"


# --- new_hand.py -------------------------------------------------------------

def _hu_finished_hand() -> dict:
    raw = load_fixture("hu_flop_cbet.json")
    raw = copy.deepcopy(raw)
    raw["streets"]["flop"]["actions"].append({"seat": 0, "action": "call", "amount": 4.0})
    return raw


def test_new_hand_rotates_button_and_persists_archetype():
    raw = _hu_finished_hand()
    next_hand = new_hand.build_next_hand(raw, winners=[0])

    assert next_hand["table"]["button_seat"] == 1  # was 0
    assert next_hand["hand_id"] == raw["hand_id"] + 1
    seat1 = next(s for s in next_hand["seats"] if s["seat"] == 1)
    assert seat1["archetype"] == "fish"  # persisted from the physical seat
    assert all(s["cards"] is None for s in next_hand["seats"])  # fresh deal pending


def test_new_hand_awards_the_pot_to_the_winner():
    raw = _hu_finished_hand()
    next_hand = new_hand.build_next_hand(raw, winners=[0])
    stacks = {s["seat"]: s["stack"] for s in next_hand["seats"]}
    # pot = 14 (3+3 preflop, 4+4 flop); loser keeps their remaining stack (93)
    assert stacks[0] == pytest.approx(93.0 + 14.0)
    assert stacks[1] == pytest.approx(93.0)


def test_new_hand_split_pot_divides_evenly():
    raw = _hu_finished_hand()
    next_hand = new_hand.build_next_hand(raw, winners=[0, 1])
    stacks = {s["seat"]: s["stack"] for s in next_hand["seats"]}
    assert stacks[0] == pytest.approx(93.0 + 7.0)
    assert stacks[1] == pytest.approx(93.0 + 7.0)


def test_new_hand_refuses_when_hero_busts():
    raw = _hu_finished_hand()
    raw["seats"][0]["stack"] = 7.0  # hero only had 7bb this hand, all of it invested
    raw["streets"]["preflop"]["actions"] = [
        {"seat": 0, "action": "post", "amount": 0.5},
        {"seat": 1, "action": "post", "amount": 1.0},
        {"seat": 0, "action": "allin", "amount": 7.0},
        {"seat": 1, "action": "call", "amount": 7.0},
    ]
    raw["streets"]["flop"]["actions"] = []
    with pytest.raises(StateError, match="bust"):
        new_hand.build_next_hand(raw, winners=[1])


def test_new_hand_marks_busted_non_hero_seat_as_out_but_keeps_the_seat():
    # 4-handed, hero at seat 1, old button at seat 0. seat0 (short-stacked)
    # busts to hero. New button becomes seat1 -> SB/BB land on seats 2/3,
    # clear of the busted seat0, so the table-shrink guard doesn't fire.
    raw = {
        "schema_version": "2.0", "session_id": "s1", "hand_id": 5,
        "table": {"big_blind": 1.0, "ante": 0.0, "button_seat": 0},
        "seats": [
            {"seat": 0, "is_hero": False, "stack": 5.0, "archetype": "nit", "hud": None,
             "cards": None, "status": "allin"},
            {"seat": 1, "is_hero": True, "stack": 50.0, "archetype": None, "hud": None,
             "cards": ["A♠", "A♥"], "status": "active"},
            {"seat": 2, "is_hero": False, "stack": 50.0, "archetype": "tag", "hud": None,
             "cards": None, "status": "folded"},
            {"seat": 3, "is_hero": False, "stack": 50.0, "archetype": "lag", "hud": None,
             "cards": None, "status": "folded"},
        ],
        "streets": {
            "preflop": {"actions": [
                {"seat": 1, "action": "post", "amount": 0.5},
                {"seat": 2, "action": "post", "amount": 1.0},
                {"seat": 3, "action": "fold", "amount": 0.0},
                {"seat": 0, "action": "allin", "amount": 5.0},
                {"seat": 1, "action": "call", "amount": 5.0},
                {"seat": 2, "action": "fold", "amount": 1.0},
            ]},
            "flop": None, "turn": None, "river": None,
        },
        "to_act": 1, "hero_seat": 1,
    }
    next_hand = new_hand.build_next_hand(raw, winners=[1])

    assert next_hand["table"]["button_seat"] == 1
    seat0 = next(s for s in next_hand["seats"] if s["seat"] == 0)
    assert seat0["status"] == "out"
    assert seat0["stack"] == 0.0
    assert seat0["archetype"] == "nit"  # préservé même bust
    assert len(next_hand["seats"]) == 4  # jamais retiré du tableau des sièges
    stacks = {s["seat"]: s["stack"] for s in next_hand["seats"]}
    assert stacks[1] == pytest.approx(45.0 + 11.0)  # 50-5 investi, + pot (5+5+1)
    assert stacks[2] == pytest.approx(49.0)
    assert stacks[3] == pytest.approx(50.0)


def test_new_hand_refuses_when_table_shrinks_past_the_expected_blind_seats():
    raw = {
        "schema_version": "2.0", "session_id": "s1", "hand_id": 5,
        "table": {"big_blind": 1.0, "ante": 0.0, "button_seat": 0},
        "seats": [
            {"seat": 0, "is_hero": True, "stack": 20.0, "archetype": None, "hud": None,
             "cards": ["A♠", "A♥"], "status": "active"},
            {"seat": 1, "is_hero": False, "stack": 20.0, "archetype": "tag", "hud": None,
             "cards": None, "status": "active"},
            {"seat": 2, "is_hero": False, "stack": 3.0, "archetype": "nit", "hud": None,
             "cards": None, "status": "active"},
        ],
        "streets": {
            "preflop": {"actions": [
                {"seat": 1, "action": "post", "amount": 0.5},
                {"seat": 2, "action": "post", "amount": 1.0},
                {"seat": 0, "action": "raise", "amount": 20.0},
                {"seat": 1, "action": "call", "amount": 20.0},
                {"seat": 2, "action": "allin", "amount": 3.0},
            ]},
            "flop": None, "turn": None, "river": None,
        },
        "to_act": 0, "hero_seat": 0,
    }
    with pytest.raises(StateError, match="rétréci"):
        new_hand.build_next_hand(raw, winners=[0, 1])  # seat 2 busts out
