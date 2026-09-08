import pytest

from pokercoach.budget import INF, compute
from pokercoach.cards import parse_cards
from pokercoach.handclass import classify
from pokercoach.texture import classify as classify_texture


def hc_and_texture(hole, board):
    hole_c, board_c = parse_cards(hole), parse_cards(board)
    return classify(hole_c, board_c), classify_texture(board_c)


def test_not_facing_a_bet_offers_check_bet_not_call_fold():
    # Regression: budget.compute() used to always offer call/fold regardless
    # of whether there was actually a bet to call -- an underpair with no
    # ATT budget got told "call" was viable (gated by DEF, which doesn't
    # apply when checking is free) instead of "check".
    hc, tex = hc_and_texture(["8♠", "8♥"], ["K♦", "7♣", "2♥"])  # underpair, weak_showdown
    b = compute(hc, tex, pot_type="srp", street="flop", n_opponents_active=2,
                pressure_spent=0.0, pressure_faced=0.0, facing_bet=False)
    assert b.viable_actions == ["check"]
    assert b.removed == [{"action": "bet", "reason": "budget ATT insuffisant (0.0 <= 0)"}]
    assert "call" not in b.viable_actions and "fold" not in b.viable_actions


def test_facing_a_bet_still_offers_the_original_call_raise_fold_triple():
    hc, tex = hc_and_texture(["A♠", "9♥"], ["9♦", "6♣", "2♥"])  # top pair, strong ATT/DEF
    b = compute(hc, tex, pot_type="srp", street="flop", n_opponents_active=1,
                pressure_spent=0.0, pressure_faced=0.0, facing_bet=True)
    assert "raise" in b.viable_actions
    assert "call" in b.viable_actions
    assert "fold" in b.viable_actions
    assert "check" not in b.viable_actions
    assert "bet" not in b.viable_actions


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


def test_def_exhausted_fold_on_a_multiway_draw_flags_implied_odds_gap():
    # Review finding: att-def-budgets.yaml has no implied-odds term at all,
    # so a DEF-exhausted fold on a draw is exactly the spot where it is most
    # likely to be too conservative (multiway, opponents who pay wide). The
    # verdict/threshold stays a user-owned cursor (not silently changed
    # here), but compute() must at least surface the gap instead of handing
    # back a plain "budget insuffisant" fold with no caveat.
    hc, tex = hc_and_texture(["9♠", "6♥"], ["T♦", "8♣", "3♥"])  # a draw, no made value
    assert hc.draw is not None
    b = compute(hc, tex, pot_type="srp", street="flop", n_opponents_active=2,
                pressure_spent=0.0, pressure_faced=100.0, facing_bet=True)
    assert b.def_remaining == 0.0
    assert "call" not in b.viable_actions
    assert any("implied odds" in note for note in b.notes)


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


# --- two_pair priority_matrix: key-based, not positional --------------------

def test_row_by_when_finds_by_content_not_position():
    from pokercoach.budget import _row_by_when

    matrix = [
        {"when": ["a", "b"], "value": {"att": 1.0, "def": 1.0}},
        {"when": ["a"], "value": {"att": 2.0, "def": 2.0}},
        {"when": ["c"], "value": {"att": 3.0, "def": 3.0}},
    ]
    assert _row_by_when(matrix, ["c"])["value"]["att"] == 3.0
    assert _row_by_when(matrix, ["a", "b"])["value"]["att"] == 1.0
    assert _row_by_when(matrix, ["b", "a"])["value"]["att"] == 1.0  # order within `when` irrelevant

    with pytest.raises(KeyError):
        _row_by_when(matrix, ["nonexistent"])


def test_two_pair_budget_is_unchanged_by_reordering_the_priority_matrix(monkeypatch):
    # Regression: `matrix[0]`...`matrix[5]` positional indexing meant
    # reordering att-def-budgets.yaml's `two_pair.priority_matrix` list
    # would silently change which row a given board/hand matched. Now that
    # rows are found by their own `when` tags (_row_by_when), the lookup
    # must be identical regardless of list order.
    import copy

    from pokercoach import budget as budget_mod

    hc, tex = hc_and_texture(["J♠", "T♥"], ["J♦", "T♣", "4♥"])  # two pair, dry board
    assert hc.made == "two_pair"

    original_table = budget_mod._att_def()
    original_result = budget_mod._base_made_hands(hc, "srp", tex)

    # Reverse (not a random shuffle) so every one of the 6 rows is
    # GUARANTEED to land at a different index -- in particular the "dry"
    # row this hand needs (originally last) moves to first. A positional
    # `matrix[5]` lookup would then read a completely different row.
    shuffled_table = copy.deepcopy(original_table)
    shuffled_matrix = shuffled_table["made_hands"]["two_pair"]["priority_matrix"]
    shuffled_matrix.reverse()
    assert [r["when"] for r in shuffled_matrix] != [r["when"] for r in original_table["made_hands"]["two_pair"]["priority_matrix"]]

    monkeypatch.setattr(budget_mod, "_att_def", lambda: shuffled_table)
    shuffled_result = budget_mod._base_made_hands(hc, "srp", tex)

    assert shuffled_result == original_result
