import pytest

from pokercoach.budget import INF, compute
from pokercoach.cards import parse_cards
from pokercoach.handclass import classify
from pokercoach.texture import classify as classify_texture


def hc_and_texture(hole, board):
    hole_c, board_c = parse_cards(hole), parse_cards(board)
    return classify(hole_c, board_c), classify_texture(board_c)


def test_nuts_are_unlimited():
    hc, tex = hc_and_texture(["K♠", "K♥"], ["K♦", "K♣", "2♥"])
    b = compute(hc, tex, pot_type="srp", street="flop", n_opponents_active=1,
                pressure_spent=0.0, pressure_faced=0.0)
    assert b.att_remaining == INF
    assert b.def_remaining == INF
    assert "raise" in b.viable_actions


def test_top_pair_top_kicker_srp_matches_yaml_baseline():
    hc, tex = hc_and_texture(["A♠", "9♥"], ["9♦", "6♣", "2♥"])
    assert hc.made == "top_pair" and hc.made_sub["kicker_bucket"] == "tptk"
    b = compute(hc, tex, pot_type="srp", street="flop", n_opponents_active=1,
                pressure_spent=0.0, pressure_faced=0.0)
    # data/att-def-budgets.yaml: top_pair.srp.tptk = {att: 3.0, def: 4.0}
    assert b.att_base == pytest.approx(3.0)
    assert b.def_base == pytest.approx(4.0)


def test_budget_decrements_with_pressure_spent_and_can_exhaust():
    hc, tex = hc_and_texture(["A♠", "9♥"], ["9♦", "6♣", "2♥"])
    b = compute(hc, tex, pot_type="srp", street="flop", n_opponents_active=1,
                pressure_spent=2.9, pressure_faced=0.0)
    assert b.att_remaining == pytest.approx(3.0 - 2.9, abs=1e-6)
    assert b.att_remaining > 0
    assert "raise" in b.viable_actions

    exhausted = compute(hc, tex, pot_type="srp", street="flop", n_opponents_active=1,
                         pressure_spent=5.0, pressure_faced=0.0)
    assert exhausted.att_remaining == 0.0
    assert "raise" not in exhausted.viable_actions
    assert any("ATT insuffisant" in r["reason"] for r in exhausted.removed)


def test_multiway_kills_bluff_att_at_three_plus_opponents():
    hc, tex = hc_and_texture(["9♠", "6♥"], ["T♦", "8♣", "3♥"])  # a draw, no made value
    b_hu = compute(hc, tex, pot_type="srp", street="flop", n_opponents_active=1,
                    pressure_spent=0.0, pressure_faced=0.0)
    b_multi = compute(hc, tex, pot_type="srp", street="flop", n_opponents_active=3,
                       pressure_spent=0.0, pressure_faced=0.0)
    assert b_multi.att_remaining == 0.0
    assert b_hu.att_remaining > 0
    assert any("bluff_dies_multiway" in r["reason"] for r in b_multi.removed)


def test_exploit_gate_blocks_bluff_vs_calling_station_on_turn():
    hc, tex = hc_and_texture(["6♠", "4♥"], ["9♦", "8♣", "2♥"])  # trash, no draw
    b = compute(hc, tex, pot_type="srp", street="turn", n_opponents_active=1,
                pressure_spent=0.0, pressure_faced=0.0, villain_archetype="fish")
    assert b.att_remaining == 0.0
    assert any("bluff_multi_street_blocked" in r["reason"] for r in b.removed)


def test_exploit_gate_does_not_apply_on_flop_first_barrel():
    hc, tex = hc_and_texture(["6♠", "4♥"], ["9♦", "8♣", "2♥"])
    b = compute(hc, tex, pot_type="srp", street="flop", n_opponents_active=1,
                pressure_spent=0.0, pressure_faced=0.0, villain_archetype="fish")
    # street_index(flop)=1 < 2 -> gate not triggered (single early stab still allowed)
    assert not any("bluff_multi_street_blocked" in r["reason"] for r in b.removed)
