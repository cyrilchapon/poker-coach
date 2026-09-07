"""Tests pour les scripts de convenance de session (skills/live-session/scripts/),
volontairement HORS du package pokercoach — importés ici par chemin de fichier."""
import copy
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import eval7
import pytest
import yaml

from pokercoach.state import StateError, validate_and_load

REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = REPO_ROOT / "skills" / "live-session" / "scripts"
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


# --- documented invocation (subprocess, not importlib) ----------------------

def test_advance_street_documented_subprocess_invocation_actually_works(tmp_path):
    # Regression: every other test here loads the script via
    # importlib.spec_from_file_location, which never exercises the
    # invocation SKILL.md actually documents (`python3 skills/live-session/
    # scripts/advance_street.py ...`, run as a real subprocess) -- that path
    # depends on `pokercoach` being importable from a FRESH interpreter
    # (i.e. `pip install -e .` actually done), which importlib loading
    # inside the already-running pytest process can't catch failing.
    raw = load_fixture("hu_flop_cbet.json")
    raw = copy.deepcopy(raw)
    raw["streets"]["flop"]["actions"].append({"seat": 0, "action": "call", "amount": 4.0})
    hand_path = tmp_path / "hand.json"
    hand_path.write_text(json.dumps(raw), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "advance_street.py"),
         "--hand", str(hand_path), "--deal", "5♦"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    derived = json.loads(result.stdout)
    assert derived["street"] == "turn"

    updated = json.loads(hand_path.read_text(encoding="utf-8"))
    assert updated["streets"]["turn"]["board"] == ["T♠", "9♥", "2♣", "5♦"]


def test_advance_street_works_without_pokercoach_pip_installed(tmp_path):
    # Regression for the claude.ai deployment failure: each skill ships as an
    # isolated directory there, with no `pip install -e .` and no repo root
    # in sight -- `pokercoach` is never importable "for free" the way it is
    # in a dev checkout. `pc_bootstrap.ensure_pokercoach_on_path()` (imported
    # at the top of this script) is what's supposed to find it anyway.
    #
    # Simulated here with `-S` (skip site initialization, so the editable
    # install's .pth-registered finder never runs) plus a PYTHONPATH limited
    # to eval7/PyYAML's own directories (real third-party deps `pokercoach`
    # needs, present in any real deployment, but deliberately NOT including
    # wherever `pokercoach` itself would be registered).
    raw = load_fixture("hu_flop_cbet.json")
    raw = copy.deepcopy(raw)
    raw["streets"]["flop"]["actions"].append({"seat": 0, "action": "call", "amount": 4.0})
    hand_path = tmp_path / "hand.json"
    hand_path.write_text(json.dumps(raw), encoding="utf-8")

    third_party_dirs = os.pathsep.join(
        os.path.dirname(os.path.dirname(mod.__file__)) for mod in (yaml, eval7)
    )
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": third_party_dirs}

    result = subprocess.run(
        [sys.executable, "-S", str(SCRIPTS_DIR / "advance_street.py"),
         "--hand", str(hand_path), "--deal", "5♦"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    derived = json.loads(result.stdout)
    assert derived["street"] == "turn"


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


def test_advance_rejects_when_one_active_seat_never_acted():
    # Regression: the action-closed check only compared CONTRIBUTIONS
    # ([0.0, 0.0] for two players who both checked -- but even a single
    # check on a two-player street trivially satisfies "equal contributions"
    # if the other player never acted at all).
    raw = load_fixture("hu_flop_cbet.json")
    raw = copy.deepcopy(raw)
    raw["streets"]["flop"]["actions"] = [{"seat": 1, "action": "check", "amount": 0}]
    with pytest.raises(StateError, match="non close"):
        advance_street.advance(raw, "5♦")


def test_advance_rejects_when_only_one_seat_is_still_contesting_the_pot():
    # Regression: if everyone else folded, the street used to still "close"
    # trivially (a single active seat's contribution is vacuously equal to
    # itself) and open the next street instead of ending the hand.
    raw = load_fixture("hu_flop_cbet.json")
    raw = copy.deepcopy(raw)
    raw["streets"]["flop"]["actions"] = [
        {"seat": 1, "action": "bet", "amount": 4.0},
        {"seat": 0, "action": "fold", "amount": 0.0},
    ]
    raw["seats"][0]["status"] = "folded"
    raw["to_act"] = 1  # the only seat left to act on anything is the winner
    with pytest.raises(StateError, match="décidée"):
        advance_street.advance(raw, "5♦")


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
    raw["seats"][0] = dict(raw["seats"][0])
    raw["seats"][0]["status"] = "allin"  # must match the allin action below
    raw["streets"]["preflop"]["actions"] = [
        {"seat": 0, "action": "post", "amount": 0.5},
        {"seat": 1, "action": "post", "amount": 1.0},
        {"seat": 0, "action": "allin", "amount": 7.0},
        {"seat": 1, "action": "call", "amount": 7.0},
    ]
    raw["streets"]["flop"]["actions"] = []
    raw["to_act"] = 1  # seat 0 is now allin, can't be to_act
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
             "cards": None, "status": "allin"},
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


def test_new_hand_rejects_a_folded_seat_as_winner():
    # Regression: eligibility was checked against `new_stacks` (built from
    # EVERY seat unconditionally), not against who was actually still in
    # the hand -- a folded seat could be declared "winner" without error.
    raw = _hu_finished_hand()
    raw["seats"][1] = dict(raw["seats"][1])
    raw["seats"][1]["status"] = "folded"
    with pytest.raises(StateError, match="invalide"):
        new_hand.build_next_hand(raw, winners=[1])


def test_new_hand_posts_the_ante_for_every_active_seat():
    # Regression: table.ante was carried forward on the new hand's table
    # config but never actually posted as an action -- the pot was
    # under-counted by n_active * ante on every subsequent hand.
    raw = _hu_finished_hand()
    raw = dict(raw)
    raw["table"] = dict(raw["table"])
    raw["table"]["ante"] = 0.1
    next_hand = new_hand.build_next_hand(raw, winners=[0])

    preflop = next_hand["streets"]["preflop"]["actions"]
    posts = {a["seat"]: a["amount"] for a in preflop if a["action"] == "post"}
    # HU: new button/SB = seat 1, BB = seat 0 (button rotated from 0 to 1).
    assert posts[1] == pytest.approx(0.5 + 0.1)  # SB + ante, folded into one action
    assert posts[0] == pytest.approx(1.0 + 0.1)  # BB + ante
    from pokercoach.state import validate_and_load as _load, pot as _pot
    assert _pot(_load(next_hand)) == pytest.approx(1.5 + 0.2)
