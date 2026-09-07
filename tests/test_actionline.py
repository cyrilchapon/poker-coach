import json
from pathlib import Path

import pytest

from pokercoach.actionline import pot_type, pressure_weight, replay_pressure, role
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
