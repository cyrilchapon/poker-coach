import copy
import json
from pathlib import Path

import pytest

from pokercoach.state import StateError, derive, position_labels, validate_and_load

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# --- pot / cotes / MDF / SPR ---------------------------------------------

def test_derive_hu_flop_cbet_matches_hand_computed_numbers():
    raw = load_fixture("hu_flop_cbet.json")
    state = validate_and_load(raw)
    d = derive(state)

    assert d.street == "flop"
    assert d.hero_seat == 0
    assert d.hero_position == "BTN/SB"
    assert d.to_act == 0
    assert d.to_act_position == "BTN/SB"

    # preflop pot (3.0 + 3.0) + flop-so-far (0 + 4.0) = 10.0
    assert d.pot == pytest.approx(10.0)
    # seat1 has 4.0 in this street, seat0 (to_act) has 0
    assert d.to_call == pytest.approx(4.0)
    # pot_odds = to_call / (pot + to_call) = 4 / 14
    assert d.pot_odds == pytest.approx(4 / 14)
    # mdf = pot / (pot + to_call) = 10 / 14 = 1 - pot_odds
    assert d.mdf == pytest.approx(10 / 14)
    assert d.mdf == pytest.approx(1 - d.pot_odds)
    # remaining: seat0 = 100 - 3 = 97, seat1 = 100 - 3 - 4 = 93 -> effective 93
    assert d.effective_stack == pytest.approx(93.0)
    # spr = effective_stack / pot = 93 / 10
    assert d.spr == pytest.approx(9.3)
    assert d.players_active == 2


def test_preflop_pot_and_pot_odds_before_any_flop():
    raw = load_fixture("hu_flop_cbet.json")
    raw = copy.deepcopy(raw)
    raw["streets"]["flop"] = None
    # Truncate before seat 1's call: BB facing the open, hasn't matched yet.
    raw["streets"]["preflop"]["actions"] = raw["streets"]["preflop"]["actions"][:3]
    raw["to_act"] = 1
    state = validate_and_load(raw)
    d = derive(state)

    assert d.street == "preflop"
    # pot = sb (posted 0.5, raised to 3.0) + bb (1.0, not yet matched) = 3.0 + 1.0 = 4.0
    assert d.pot == pytest.approx(4.0)
    assert d.to_call == pytest.approx(2.0)  # bb has 1.0 in, needs to match 3.0


# --- positions -------------------------------------------------------------

def make_seats(n: int, hero_seat: int = 0) -> list[dict]:
    return [
        {
            "seat": i, "is_hero": i == hero_seat, "stack": 100.0, "archetype": None,
            "hud": None, "cards": ["A♠", "K♦"] if i == hero_seat else None, "status": "active",
        }
        for i in range(n)
    ]


def minimal_hand(n_seats: int, button_seat: int, hero_seat: int = 0) -> dict:
    return {
        "schema_version": "2.0",
        "table": {"big_blind": 1.0, "ante": 0.0, "button_seat": button_seat},
        "seats": make_seats(n_seats, hero_seat=hero_seat),
        "streets": {
            "preflop": {"actions": [{"seat": hero_seat, "action": "check", "amount": 0}]},
            "flop": None, "turn": None, "river": None,
        },
        "to_act": hero_seat,
        "hero_seat": hero_seat,
    }


def test_heads_up_button_is_small_blind():
    state = validate_and_load(minimal_hand(2, button_seat=0))
    labels = position_labels(state)
    assert labels == {0: "BTN/SB", 1: "BB"}


def test_six_max_sb_position_differs_from_heads_up_even_at_same_n_behind():
    # n_behind=1 for the SB in both 6-max and HU (only BB left to act), but
    # the label — and the range behind it — differs because ip_postflop differs.
    # button_seat chosen so seat 1 sits at offset 1 = SB.
    state = validate_and_load(minimal_hand(6, button_seat=0, hero_seat=1))
    labels = position_labels(state)
    assert labels[1] == "SB"
    assert labels[0] == "BTN"
    assert labels[2] == "BB"
    assert set(labels.values()) == {"BTN", "SB", "BB", "UTG", "HJ", "CO"}


def test_eight_max_all_labels_present():
    state = validate_and_load(minimal_hand(8, button_seat=3))
    labels = position_labels(state)
    assert set(labels.values()) == {"BTN", "SB", "BB", "UTG", "UTG+1", "MP", "HJ", "CO"}
    assert labels[3] == "BTN"
    assert labels[4] == "SB"
    assert labels[(3 - 1) % 8] == "CO"


def test_button_seat_rotates_labels_but_seats_stay_physical():
    state_a = validate_and_load(minimal_hand(6, button_seat=0))
    state_b = validate_and_load(minimal_hand(6, button_seat=4))
    assert position_labels(state_a)[0] == "BTN"
    assert position_labels(state_b)[0] == "BB"  # same physical seat, different label


# --- format is always derived, never stored --------------------------------

def test_declared_format_must_match_seat_count():
    raw = minimal_hand(6, button_seat=0)
    raw["table"]["format"] = "hu"
    with pytest.raises(StateError, match="format"):
        validate_and_load(raw)


def test_declared_format_matching_derivation_is_accepted():
    raw = minimal_hand(6, button_seat=0)
    raw["table"]["format"] = "6max"
    validate_and_load(raw)  # no raise


# --- validation errors ------------------------------------------------------

def test_missing_hero_is_rejected():
    raw = minimal_hand(2, button_seat=0)
    raw["seats"][0]["is_hero"] = False
    with pytest.raises(StateError, match="is_hero"):
        validate_and_load(raw)


def test_two_heroes_is_rejected():
    raw = minimal_hand(2, button_seat=0)
    raw["seats"][1]["is_hero"] = True
    with pytest.raises(StateError, match="is_hero"):
        validate_and_load(raw)


def test_to_act_on_folded_seat_is_rejected():
    raw = minimal_hand(2, button_seat=0, hero_seat=0)
    raw["seats"][0]["status"] = "folded"
    with pytest.raises(StateError, match="to_act"):
        validate_and_load(raw)


def test_duplicate_card_between_hero_and_board_is_rejected():
    raw = minimal_hand(2, button_seat=0)
    raw["streets"]["flop"] = {"board": ["A♠", "9♥", "2♣"], "actions": []}
    with pytest.raises(StateError, match="double"):
        validate_and_load(raw)  # hero has A♠ in hand, board also has A♠


def test_invalid_seat_numbering_is_rejected():
    raw = minimal_hand(3, button_seat=0)
    raw["seats"][1]["seat"] = 5
    with pytest.raises(StateError):
        validate_and_load(raw)


def test_out_of_range_seat_count_is_rejected():
    raw = minimal_hand(2, button_seat=0)
    raw["seats"] = raw["seats"][:1]
    with pytest.raises(StateError):
        validate_and_load(raw)
