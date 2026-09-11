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
    hc, tex = hc_and_texture(["8♠", "8♥"], ["K♦", "T♣", "9♥"])  # underpair, weak_showdown
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


# --- paire servie + paire du board : budget par proxy de force ---------------

def test_pocket_pair_plus_board_pair_uses_its_strength_proxy_not_the_two_pair_table():
    # Live-session bug report: TT on J-9-9-3 is a real two pair, but half of
    # it (the nines) is shared by every opponent -- att-def-budgets.yaml says
    # so itself in its two_pair notes ("force réelle ~ top/middle paire").
    # The budget must come from the pocket pair's rank among the board ranks
    # (second_pair here), never from the two_pair table, which assumes two
    # pairs the opponent does not have.
    hc, tex = hc_and_texture(["T♠", "T♥"], ["J♠", "9♦", "9♣", "3♥"])
    assert hc.made == "two_pair"
    b = compute(hc, tex, pot_type="srp", street="turn", n_opponents_active=1,
                pressure_spent=0.0, pressure_faced=0.0)
    second_pair_hc, second_pair_tex = hc_and_texture(["8♠", "K♥"], ["J♠", "8♦", "3♣", "2♥"])
    real_two_pair_hc, real_two_pair_tex = hc_and_texture(["9♠", "4♥"], ["9♦", "4♣", "2♥"])
    real_two_pair = compute(real_two_pair_hc, real_two_pair_tex, pot_type="srp", street="flop",
                            n_opponents_active=1, pressure_spent=0.0, pressure_faced=0.0)
    assert b.att_base == pytest.approx(1.8)   # second_pair / srp / pocket_or_top_kicker
    assert b.def_base == pytest.approx(2.8)
    assert b.att_base < real_two_pair.att_base
    assert b.def_base < real_two_pair.def_base


def test_pocket_pair_plus_board_pair_still_takes_the_paired_board_penalty():
    # The texture stage keys off the pair family. Before the fix the class
    # was `underpair` (in the family); a naive fix to `two_pair` would have
    # dropped it out of the family and silently skipped the paired-board
    # malus -- on a paired board, of all things.
    hc, tex = hc_and_texture(["T♠", "T♥"], ["J♠", "9♦", "9♣", "3♥"])
    b = compute(hc, tex, pot_type="srp", street="turn", n_opponents_active=1,
                pressure_spent=0.0, pressure_faced=0.0)
    assert b.def_after_penalties == pytest.approx(2.4)  # 2.8 + mid_low_pairs_delta (-0.4)


def test_pocket_pair_below_a_paired_board_keeps_an_underpair_budget():
    # 22 on J-9-9 is two pair by the book and worth nothing by the table.
    hc, tex = hc_and_texture(["2♠", "2♥"], ["J♠", "9♦", "9♣"])
    assert hc.made == "two_pair"
    b = compute(hc, tex, pot_type="srp", street="flop", n_opponents_active=1,
                pressure_spent=0.0, pressure_faced=0.0)
    assert b.att_base == 0.0
    assert b.def_base == pytest.approx(0.8)  # weak_showdown baseline, as for an underpair


# --- paire servie non connectée : placée par sa position au board -----------

def test_pocket_pair_between_board_ranks_gets_its_equivalent_pair_budget():
    # TT on J-9-6 used to be `underpair` -> weak_showdown (att 0 / def 0.8),
    # although it beats the nine and the six. It is a second pair and takes
    # the second-pair line, pocket-pair column.
    hc, tex = hc_and_texture(["T♠", "T♥"], ["J♠", "9♦", "6♣"])
    assert hc.made == "second_pair"
    b = compute(hc, tex, pot_type="srp", street="flop", n_opponents_active=1,
                pressure_spent=0.0, pressure_faced=0.0)
    assert (b.att_base, b.def_base) == pytest.approx((1.8, 2.8))


def test_a_true_underpair_keeps_the_weak_showdown_baseline():
    hc, tex = hc_and_texture(["5♠", "5♥"], ["9♦", "8♣", "7♥"])
    assert hc.made == "underpair"
    b = compute(hc, tex, pot_type="srp", street="flop", n_opponents_active=1,
                pressure_spent=0.0, pressure_faced=0.0)
    assert (b.att_base, b.def_base) == pytest.approx((0.0, 0.8))


def test_outranked_pocket_pair_reaches_the_three_bet_plus_special_row():
    # `third_pair.three_bet_plus_special.pocket_pair` ("paire servie
    # surclassée, seulement 2 outs") was unreachable while these hands were
    # classified `underpair`. It is deliberately lower than the class's
    # generic 3BP row (def 1.5): a pocket pair has 2 outs, a pair that hit the
    # board can still improve its kicker.
    hc, tex = hc_and_texture(["5♠", "5♥"], ["K♦", "9♣", "4♥"])
    b = compute(hc, tex, pot_type="three_bet_pot", street="flop", n_opponents_active=1,
                pressure_spent=0.0, pressure_faced=0.0)
    assert (b.att_base, b.def_base) == pytest.approx((0.0, 0.6))


def test_g4_still_treats_a_failed_set_mine_as_a_bluff_line():
    # The reclassification must not quietly narrow G4's cover of the
    # documented leak (barrelling on while feeling committed): a pocket pair
    # outranked by 2+ board ranks stays a bluff line even though it is now
    # `third_pair` rather than `underpair`.
    hc, tex = hc_and_texture(["5♠", "5♥"], ["K♦", "9♣", "4♥", "2♠"])
    b = compute(hc, tex, pot_type="srp", street="turn", n_opponents_active=1,
                pressure_spent=0.0, pressure_faced=0.0, villain_archetype="fish")
    assert b.att_remaining == 0.0
    assert any("bluff_multi_street_blocked" in n for n in b.notes)
    # A real third pair (hero's own card hit the board) is not a bluff line.
    hc, tex = hc_and_texture(["4♠", "A♥"], ["K♦", "9♣", "4♥", "2♠"])
    b = compute(hc, tex, pot_type="srp", street="turn", n_opponents_active=1,
                pressure_spent=0.0, pressure_faced=0.0, villain_archetype="fish")
    assert b.att_remaining > 0


# --- colonnes de kicker : toutes les orthographes du YAML ------------------

def test_fourth_and_fifth_pair_reach_their_own_rows():
    # Regression: `fourth_fifth_pair`'s SRP node is keyed `fourth`/`fifth` and
    # has no `other` row, so the single-spelling kicker map fell all the way
    # through to a bare `{"att": 0, "def": node.get("def", 0)}` -- returning
    # att 0 / def 0 for every fourth and fifth pair in a single-raised pot.
    fourth, tex4 = hc_and_texture(["2♠", "K♥"], ["9♦", "8♣", "5♥", "2♦"])
    b = compute(fourth, tex4, pot_type="srp", street="turn", n_opponents_active=1,
                pressure_spent=0.0, pressure_faced=0.0)
    assert (b.att_base, b.def_base) == pytest.approx((0.8, 1.8))

    fifth, tex5 = hc_and_texture(["2♠", "K♥"], ["9♦", "8♣", "5♥", "3♦", "2♣"])
    b = compute(fifth, tex5, pot_type="srp", street="river", n_opponents_active=1,
                pressure_spent=0.0, pressure_faced=0.0)
    assert (b.att_base, b.def_base) == pytest.approx((0.5, 1.5))


def test_top_kicker_rows_are_found_under_every_spelling_the_yaml_uses():
    # `third_pair` names the column `top_kicker_or_pocket` and `second_pair`
    # splits it into `pocket` / `top_kicker` in raised pots -- the old map only
    # knew `pocket_or_top_kicker`, so both silently took the `other` row.
    third, tex = hc_and_texture(["4♠", "A♥"], ["K♦", "9♣", "4♥"])
    b = compute(third, tex, pot_type="srp", street="flop", n_opponents_active=1,
                pressure_spent=0.0, pressure_faced=0.0)
    assert (b.att_base, b.def_base) == pytest.approx((1.2, 2.2))  # was the "other" row (1.0/2.0)

    second, tex = hc_and_texture(["8♠", "A♥"], ["K♦", "8♣", "4♥"])
    b = compute(second, tex, pot_type="three_bet_pot", street="flop", n_opponents_active=1,
                pressure_spent=0.0, pressure_faced=0.0)
    assert (b.att_base, b.def_base) == pytest.approx((1.5, 2.3))  # `top_kicker`, not `other`


# --- paire servie qui a DOUBLÉ avec la paire du board : une main de valeur ---

def test_pocket_pair_that_made_two_pair_is_not_a_bluff_line_for_the_exploit_gate():
    # Live-session bug: G4 treats an outranked pocket pair as a bluff line
    # (the documented set-mining leak) -- but 7-7 on J-9-9-3 is not a missed
    # set, it is two pair, nines and sevens. Against a calling station the
    # gate zeroed its ATT and removed bet/raise from the viable actions of a
    # hand we specifically want to bet against that profile.
    hc, tex = hc_and_texture(["7♥", "7♦"], ["J♠", "9♥", "9♣", "3♦"])
    b = compute(hc, tex, pot_type="srp", street="turn", n_opponents_active=1,
                villain_archetype="calling_station", pressure_spent=0.0,
                pressure_faced=0.0, facing_bet=False)
    assert "bet" in b.viable_actions


def test_bare_outranked_pocket_pair_is_still_a_bluff_line_for_the_exploit_gate():
    # Guard for the exclusion above: the real missed set -- a bare pocket
    # pair that paired nothing -- must keep triggering the gate.
    hc, tex = hc_and_texture(["5♥", "5♦"], ["A♠", "K♥", "9♣", "3♦"])
    b = compute(hc, tex, pot_type="srp", street="turn", n_opponents_active=1,
                villain_archetype="calling_station", pressure_spent=0.0,
                pressure_faced=0.0, facing_bet=False)
    assert "bet" not in b.viable_actions


def test_two_pair_through_a_pocket_pair_is_budgeted_like_the_same_hand_hit_on_board():
    # 7-7 on J-9-9-3 and 7-6 on J-9-9-7 are the SAME five cards: nines and
    # sevens, jack kicker. The "paire servie surclassée, seulement 2 outs"
    # special was firing on the first (def 0.6 -> 0.3 in a 3BP) while the
    # second took the generic line at 1.5 -- the premise of that special is
    # a BARE pocket pair with 2 outs to improve, and this one is already
    # improved. Both must land on the same budget.
    pocket_hc, pocket_tex = hc_and_texture(["7♥", "7♦"], ["J♠", "9♥", "9♣", "3♦"])
    board_hc, board_tex = hc_and_texture(["7♥", "6♦"], ["J♠", "9♥", "9♣", "7♦"])
    kw = dict(pot_type="three_bet_pot", street="turn", n_opponents_active=1,
              pressure_spent=0.0, pressure_faced=0.0, facing_bet=True)
    pocket = compute(pocket_hc, pocket_tex, **kw)
    board = compute(board_hc, board_tex, **kw)
    assert (pocket.att_base, pocket.def_base) == (board.att_base, board.def_base)


def test_bare_outranked_pocket_pair_keeps_its_three_bet_pot_penalty():
    # Guard for the exclusion above: the special still applies to the hand it
    # was written for -- a bare pocket pair, 2 outs, in a raised pot.
    hc, tex = hc_and_texture(["5♥", "5♦"], ["A♠", "K♥", "9♣", "3♦"])
    b = compute(hc, tex, pot_type="three_bet_pot", street="turn", n_opponents_active=1,
                pressure_spent=0.0, pressure_faced=0.0, facing_bet=True)
    srp = compute(hc, tex, pot_type="srp", street="turn", n_opponents_active=1,
                  pressure_spent=0.0, pressure_faced=0.0, facing_bet=True)
    assert b.att_base == 0.0
    assert b.def_base < srp.def_base


def test_board_hit_pair_stab_is_wired_in_a_raised_pot():
    # `three_bet_plus_special.board_hit_pair: {att: 1.5}` was dead code --
    # only the pocket_pair half was read. The 3BP/4BP nodes of third_pair and
    # fourth_fifth_pair carry a bare `def`, so a board-hit third pair came
    # out at att 0.0: no stab possible in a raised pot, though the table
    # prescribes one explicitly ("stab <= 30% pot quand l'adversaire montre
    # de la faiblesse").
    hc, tex = hc_and_texture(["9♠", "2♦"], ["K♠", "Q♥", "9♣", "4♦"])
    assert hc.made == "third_pair"
    b = compute(hc, tex, pot_type="three_bet_pot", street="turn", n_opponents_active=1,
                pressure_spent=0.0, pressure_faced=0.0, facing_bet=True)
    assert b.att_base == 1.5
    # Only the ATT is overridden: the line carries no `def` of its own.
    assert b.def_base == 1.5
