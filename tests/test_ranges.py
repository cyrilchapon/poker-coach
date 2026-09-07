import pytest

from pokercoach.cards import parse_cards
from pokercoach.ranges import narrow, table
from pokercoach.state import validate_and_load

FIXTURES_DIR = __file__.rsplit("/", 1)[0] + "/fixtures"


def minimal_hand(n_seats, button_seat, hero_seat=0):
    seats = [
        {"seat": i, "is_hero": i == hero_seat, "stack": 100.0, "archetype": None,
         "hud": None, "cards": ["A♠", "K♦"] if i == hero_seat else None, "status": "active"}
        for i in range(n_seats)
    ]
    return {
        "schema_version": "2.0",
        "table": {"big_blind": 1.0, "ante": 0.0, "button_seat": button_seat},
        "seats": seats,
        "streets": {
            "preflop": {"actions": [{"seat": hero_seat, "action": "check", "amount": 0}]},
            "flop": None, "turn": None, "river": None,
        },
        "to_act": hero_seat, "hero_seat": hero_seat,
    }


def test_rfi_matches_reference_table_for_btn_6max():
    state = validate_and_load(minimal_hand(6, button_seat=0, hero_seat=0))
    key = table.derive_key(state, 0)
    entry = table.rfi(key)
    assert entry.pct == pytest.approx(45)
    assert entry.confidence == "high"


def test_rfi_no_scenario_for_bb():
    state = validate_and_load(minimal_hand(6, button_seat=0, hero_seat=2))  # offset 2 = BB
    key = table.derive_key(state, 2)
    entry = table.rfi(key)
    assert entry.pct == 0.0


def test_vs_rfi_defends_wider_against_a_looser_opener():
    state = validate_and_load(minimal_hand(6, button_seat=0, hero_seat=2))  # BB defending
    key = table.derive_key(state, 2, scenario="vs_rfi")
    vs_utg = table.vs_rfi(key, opener_n_behind=5)   # UTG open, strong
    vs_btn = table.vs_rfi(key, opener_n_behind=2)   # BTN open, weak
    assert vs_btn.pct > vs_utg.pct


def test_vs_limp_widens_over_rfi():
    state = validate_and_load(minimal_hand(6, button_seat=0, hero_seat=5))  # CO
    key = table.derive_key(state, 5)
    rfi_entry = table.rfi(key)
    limp_entry = table.vs_limp(key)
    assert limp_entry.pct > rfi_entry.pct


def test_narrow_removes_combos_that_cannot_support_a_raise():
    board = parse_cards(["9♦", "6♣", "2♥"])
    # Some pressure already spent this street: trash (ATT baseline ~0.5) can
    # no longer fund a raise, an overpair (ATT baseline ~3+) still can.
    result = narrow.narrow("QQ+,72o", board, "raise", pot_type="srp", street="flop",
                            pressure_spent=1.0)
    assert result.remaining_combos < result.original_combos


def test_narrow_fold_keeps_everything():
    board = parse_cards(["9♦", "6♣", "2♥"])
    result = narrow.narrow("22+", board, "fold", pot_type="srp", street="flop")
    assert result.remaining_combos == result.original_combos
