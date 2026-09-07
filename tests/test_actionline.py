import json
from pathlib import Path

import pytest

from pokercoach.actionline import is_opening_decision, last_aggressor, pot_type, pressure_weight, replay_pressure, role
from pokercoach.state import validate_and_load

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_pressure_weight_matches_table_breakpoints_exactly():
    assert pressure_weight(50) == pytest.approx(0.70)
    assert pressure_weight(85) == pytest.approx(1.00)
    assert pressure_weight(100) == pytest.approx(1.10)


def test_pressure_weight_interpolates_between_breakpoints():
    # halfway between 50 (0.70) and 67 (0.85) in threshold terms
    w = pressure_weight(58.5)
    assert 0.70 < w < 0.85


def test_pressure_weight_caps_beyond_last_threshold():
    assert pressure_weight(5000) == pytest.approx(4.00)


def test_pot_type_srp_and_role_defender_on_hu_fixture():
    state = validate_and_load(load_fixture("hu_flop_cbet.json"))
    assert pot_type(state) == "srp"
    assert role(state) == "defender"  # hero faces seat 1's flop bet


def test_pressure_replay_hu_fixture():
    state = validate_and_load(load_fixture("hu_flop_cbet.json"))
    replay = replay_pressure(state)
    # preflop raise 0.5 -> 3.0 into a 1.5 pot = 166.7% pot
    assert replay.spent[0] == pytest.approx(pressure_weight(2.5 / 1.5 * 100))
    assert replay.faced[1] == pytest.approx(replay.spent[0])
    # flop bet 4.0 into a 6.0 pot = 66.7% pot
    assert replay.spent[1] == pytest.approx(pressure_weight(4.0 / 6.0 * 100))
    assert replay.faced[0] == pytest.approx(replay.spent[1])


def test_pressure_faced_not_attributed_to_a_seat_folded_on_an_earlier_street():
    # Regression: `still_in`/`folded_or_out` were reset to fresh state at
    # the top of EVERY street's loop, forgetting folds from earlier streets
    # -- a seat that folded preflop would still count as "still in" (and
    # accumulate `faced` pressure) for a flop bet it was no longer exposed
    # to at all.
    raw = {
        "schema_version": "2.0",
        "table": {"big_blind": 1.0, "ante": 0.0, "button_seat": 0},
        "seats": [
            {"seat": 0, "is_hero": False, "stack": 100.0, "archetype": None, "hud": None,
             "cards": None, "status": "folded"},
            {"seat": 1, "is_hero": True, "stack": 100.0, "archetype": None, "hud": None,
             "cards": ["A♠", "K♠"], "status": "active"},
            {"seat": 2, "is_hero": False, "stack": 100.0, "archetype": None, "hud": None,
             "cards": None, "status": "active"},
        ],
        "streets": {
            "preflop": {"actions": [
                {"seat": 1, "action": "post", "amount": 0.5},
                {"seat": 2, "action": "post", "amount": 1.0},
                {"seat": 0, "action": "fold", "amount": 0.0},
                {"seat": 1, "action": "call", "amount": 1.0},
                {"seat": 2, "action": "check", "amount": 1.0},
            ]},
            "flop": {"board": ["9♦", "6♣", "2♥"], "actions": [
                {"seat": 1, "action": "bet", "amount": 4.0},
            ]},
            "turn": None, "river": None,
        },
        "to_act": 2, "hero_seat": 1,
    }
    state = validate_and_load(raw)
    replay = replay_pressure(state)
    assert replay.faced[0] == pytest.approx(0.0)  # folded before the flop bet even happened
    assert replay.faced[2] > 0.0  # still in, correctly faces it


def test_role_aggressor_and_probe_when_not_facing_a_bet():
    # Regression guard: role() must not shadow the last_aggressor() call
    # with a same-named local when to_call == 0 (aggressor/probe branch).
    raw = load_fixture("hu_flop_cbet.json")
    raw = dict(raw)
    raw["streets"]["flop"]["actions"] = []  # nobody has bet the flop yet
    raw["to_act"] = 0
    state = validate_and_load(raw)
    assert last_aggressor(state) == 0  # seat 0 raised preflop
    assert role(state, seat=0) == "aggressor"
    assert role(state, seat=1) == "probe"


def test_role_is_not_defender_on_the_very_first_preflop_decision():
    # Regression: to_call() is inflated by the BB's forced post before
    # anyone has voluntarily acted -- role() used to read "defender" for
    # literally anyone's opening decision (blinds-only preflop state).
    raw = load_fixture("hu_flop_cbet.json")
    raw = dict(raw)
    raw["streets"] = dict(raw["streets"])
    raw["streets"]["preflop"] = {"actions": [
        {"seat": 0, "action": "post", "amount": 0.5},
        {"seat": 1, "action": "post", "amount": 1.0},
    ]}
    raw["streets"]["flop"] = None
    raw["to_act"] = 0
    state = validate_and_load(raw)
    assert is_opening_decision(state) is True
    assert role(state) != "defender"


def test_pot_type_limp_srp_3bet_squeeze_4bet():
    def preflop_state(actions):
        raw = load_fixture("hu_flop_cbet.json")
        raw["streets"]["flop"] = None
        raw["streets"]["preflop"]["actions"] = actions
        raw["to_act"] = actions[-1]["seat"]
        return validate_and_load(raw)

    limp = preflop_state([
        {"seat": 0, "action": "post", "amount": 0.5},
        {"seat": 1, "action": "post", "amount": 1.0},
        {"seat": 0, "action": "call", "amount": 1.0},
    ])
    assert pot_type(limp) == "limp"

    srp = preflop_state([
        {"seat": 0, "action": "post", "amount": 0.5},
        {"seat": 1, "action": "post", "amount": 1.0},
        {"seat": 0, "action": "raise", "amount": 3.0},
    ])
    assert pot_type(srp) == "srp"

    three_bet = preflop_state([
        {"seat": 0, "action": "post", "amount": 0.5},
        {"seat": 1, "action": "post", "amount": 1.0},
        {"seat": 0, "action": "raise", "amount": 3.0},
        {"seat": 1, "action": "raise", "amount": 9.0},
    ])
    assert pot_type(three_bet) == "three_bet_pot"

    four_bet = preflop_state([
        {"seat": 0, "action": "post", "amount": 0.5},
        {"seat": 1, "action": "post", "amount": 1.0},
        {"seat": 0, "action": "raise", "amount": 3.0},
        {"seat": 1, "action": "raise", "amount": 9.0},
        {"seat": 0, "action": "raise", "amount": 21.0},
    ])
    assert pot_type(four_bet) == "four_bet_pot"


def _allin_shove_state() -> "object":
    raw = {
        "schema_version": "2.0",
        "table": {"big_blind": 1.0, "ante": 0.0, "button_seat": 0},
        "seats": [
            {"seat": 0, "is_hero": False, "stack": 100.0, "archetype": None, "hud": None,
             "cards": None, "status": "active"},
            {"seat": 1, "is_hero": True, "stack": 100.0, "archetype": None, "hud": None,
             "cards": ["A♦", "K♣"], "status": "active"},
            {"seat": 2, "is_hero": False, "stack": 100.0, "archetype": None, "hud": None,
             "cards": None, "status": "folded"},
            {"seat": 3, "is_hero": False, "stack": 0.0, "archetype": None, "hud": None,
             "cards": None, "status": "allin"},
        ],
        "streets": {
            "preflop": {"actions": [
                {"seat": 0, "action": "post", "amount": 0.5},
                {"seat": 1, "action": "post", "amount": 1.0},
                {"seat": 2, "action": "fold", "amount": 0.0},
                {"seat": 3, "action": "allin", "amount": 100.0},
            ]},
            "flop": None, "turn": None, "river": None,
        },
        "to_act": 1, "hero_seat": 1,
    }
    return validate_and_load(raw)


def test_allin_action_is_treated_like_a_bet_or_raise_throughout():
    # Regression: "allin" is a distinct member of state.ACTIONS, not a
    # synonym of "bet"/"raise"/"call" -- is_opening_decision, last_aggressor
    # and replay_pressure all missed it, so a shove was invisible: role()
    # read "probe" instead of "defender", and weighted_pressure_faced stayed
    # 0.0 despite facing a 100bb shove.
    state = _allin_shove_state()
    assert is_opening_decision(state) is False
    assert last_aggressor(state) == 3
    assert role(state) == "defender"
    replay = replay_pressure(state)
    assert replay.faced[1] > 0.0
