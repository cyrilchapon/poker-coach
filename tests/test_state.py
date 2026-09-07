import copy
import json
from pathlib import Path

import pytest

from pokercoach.state import (
    StateError, derive, ip_postflop, n_behind, position_labels,
    postflop_acting_order_offsets, preflop_acting_order_offsets, validate_and_load,
)

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
    # mdf_collective = pot / (pot + to_call) = 10 / 14 = 1 - pot_odds
    assert d.mdf_collective == pytest.approx(10 / 14)
    assert d.mdf_collective == pytest.approx(1 - d.pot_odds)
    # heads-up : un seul défenseur -> individuel == collectif
    assert d.n_defenders == 1
    assert d.mdf_individual == pytest.approx(d.mdf_collective)
    # remaining: seat0 = 100 - 3 = 97, seat1 = 100 - 3 - 4 = 93 -> effective 93
    assert d.effective_stack == pytest.approx(93.0)
    # spr = effective_stack / pot = 93 / 10
    assert d.spr == pytest.approx(9.3)
    assert d.players_active == 2


def test_mdf_individual_is_lower_than_collective_in_multiway():
    # 3-handed flop: seat2 bets into seat0 (to_act) AND seat1, both facing
    # the bet simultaneously -> n_defenders == 2. The collective obligation
    # is shared, so each individual defender may fold MORE than the
    # heads-up-style mdf_collective figure would suggest.
    raw = {
        "schema_version": "2.0",
        "table": {"big_blind": 1.0, "ante": 0.0, "button_seat": 0},
        "seats": [
            {"seat": 0, "is_hero": True, "stack": 100.0, "archetype": None, "hud": None,
             "cards": ["A♠", "K♦"], "status": "active"},
            {"seat": 1, "is_hero": False, "stack": 100.0, "archetype": None, "hud": None,
             "cards": None, "status": "active"},
            {"seat": 2, "is_hero": False, "stack": 100.0, "archetype": None, "hud": None,
             "cards": None, "status": "active"},
        ],
        "streets": {
            "preflop": {"actions": [
                {"seat": 0, "action": "call", "amount": 1.0},
                {"seat": 1, "action": "call", "amount": 1.0},
                {"seat": 2, "action": "call", "amount": 1.0},
            ]},
            "flop": {"board": ["9♦", "6♣", "2♥"], "actions": [
                {"seat": 2, "action": "bet", "amount": 3.0},
            ]},
            "turn": None, "river": None,
        },
        "to_act": 0, "hero_seat": 0,
    }
    state = validate_and_load(raw)
    d = derive(state)

    assert d.pot == pytest.approx(6.0)   # 3 (preflop) + 3 (seat2's flop bet)
    assert d.to_call == pytest.approx(3.0)
    assert d.n_defenders == 2            # seat0 (to_act) and seat1 both face the bet
    assert d.mdf_collective == pytest.approx(6 / 9)
    # mdf_individual = 1 - (1 - mdf_collective) ** (1/2)
    assert d.mdf_individual == pytest.approx(1 - (1 - 6 / 9) ** 0.5)
    assert d.mdf_individual < d.mdf_collective


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


# --- n_behind / ip_postflop : contre le tableau de 03-multiway-generalization.md

@pytest.mark.parametrize("n_seats,hero_offset,expected_n_behind,expected_ip", [
    (8, 3, 7, False),  # UTG 8-max
    (6, 3, 5, False),  # UTG 6-max
    (6, 4, 4, False),  # HJ 6-max
    (6, 5, 3, False),  # CO 6-max
    (6, 0, 2, True),   # BTN 6-max
    (6, 1, 1, False),  # SB 6-max
    (2, 0, 1, True),   # BTN/SB heads-up
])
def test_n_behind_and_ip_postflop_match_reference_table(n_seats, hero_offset, expected_n_behind, expected_ip):
    button_seat = 0
    hero_seat = (button_seat + hero_offset) % n_seats
    state = validate_and_load(minimal_hand(n_seats, button_seat=button_seat, hero_seat=hero_seat))
    assert n_behind(state, hero_seat) == expected_n_behind
    assert ip_postflop(state, hero_seat) == expected_ip


def test_postflop_acting_order_button_is_always_last():
    # Heads-up: BB acts first postflop, BTN/SB last.
    assert postflop_acting_order_offsets(2) == [1, 0]
    # 6-max: SB first, ..., BTN last.
    assert postflop_acting_order_offsets(6) == [1, 2, 3, 4, 5, 0]
    # Preflop order stays UTG-first / BB-last for comparison -- the two are
    # genuinely different orders, not the same list rotated.
    assert preflop_acting_order_offsets(6) == [3, 4, 5, 0, 1, 2]


def test_out_of_range_seat_count_is_rejected():
    raw = minimal_hand(2, button_seat=0)
    raw["seats"] = raw["seats"][:1]
    with pytest.raises(StateError):
        validate_and_load(raw)


# --- status vs. action-history cross-check --------------------------------

def test_seat_that_folded_but_kept_active_status_is_rejected():
    # Regression: nothing cross-checked a seat's declared status against its
    # OWN action history -- a seat could fold and stay "active", silently
    # breaking players_active/n_defenders/effective_stack/mdf_individual.
    raw = minimal_hand(3, button_seat=0, hero_seat=0)
    raw["seats"] = [dict(s) for s in raw["seats"]]
    raw["streets"]["preflop"]["actions"] = [
        {"seat": 1, "action": "fold", "amount": 0.0},
        {"seat": 0, "action": "check", "amount": 0.0},
    ]
    # seat 1 folded but its declared status is still "active"
    with pytest.raises(StateError, match="incohérent avec son historique"):
        validate_and_load(raw)


def test_seat_that_went_allin_but_kept_active_status_is_rejected():
    raw = minimal_hand(2, button_seat=0, hero_seat=0)
    raw["seats"] = [dict(s) for s in raw["seats"]]
    raw["seats"][1]["stack"] = 5.0
    raw["streets"]["preflop"]["actions"] = [
        {"seat": 1, "action": "allin", "amount": 5.0},
        {"seat": 0, "action": "call", "amount": 5.0},
    ]
    # seat 1 shoved but its declared status is still "active"
    with pytest.raises(StateError, match="incohérent avec son historique"):
        validate_and_load(raw)


def test_folded_and_allin_seats_with_matching_status_are_accepted():
    raw = minimal_hand(3, button_seat=0, hero_seat=0)
    raw["seats"] = [dict(s) for s in raw["seats"]]
    raw["seats"][1]["status"] = "folded"
    raw["seats"][2]["status"] = "allin"
    raw["seats"][2]["stack"] = 3.0
    raw["streets"]["preflop"]["actions"] = [
        {"seat": 1, "action": "fold", "amount": 0.0},
        {"seat": 2, "action": "allin", "amount": 3.0},
        {"seat": 0, "action": "call", "amount": 3.0},
    ]
    state = validate_and_load(raw)  # must not raise
    assert state.seats[1].status == "folded"
    assert state.seats[2].status == "allin"


# --- street-gap validation -------------------------------------------------

def test_calling_station_is_a_valid_seat_archetype():
    # Regression: "calling_station" is a real villain_archetype accepted by
    # budget.compute() and offered via --villain-archetype on `pc budget`/
    # `pc brief`, but was missing from state.ARCHETYPES -- a live-session
    # HUD tag of "calling_station" on a physical seat was rejected outright.
    raw = minimal_hand(2, button_seat=0)
    raw["seats"] = [dict(s) for s in raw["seats"]]
    raw["seats"][1]["archetype"] = "calling_station"
    state = validate_and_load(raw)  # must not raise
    assert state.seats[1].archetype == "calling_station"


def test_street_gap_is_rejected():
    # Regression: `flop: null` followed by `turn: {...}` used to be silently
    # accepted -- a hand can't skip a street.
    raw = minimal_hand(2, button_seat=0)
    raw["streets"]["turn"] = {"board": ["9♦", "6♣", "2♥", "3♦"], "actions": []}
    with pytest.raises(StateError, match="trou"):
        validate_and_load(raw)
