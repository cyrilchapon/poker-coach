import pytest

from pokercoach.cards import parse_cards
from pokercoach.equity import equity, parse_range


def test_parse_range_pair():
    combos = parse_range("AA")
    assert len(combos) == 6  # C(4,2) combos of aces
    assert all(c.weight == 1.0 for c in combos)


def test_parse_range_pair_plus():
    combos = parse_range("KK+")
    ranks = {c.combo[0].rank for c in combos}
    assert ranks == {"K", "A"}


def test_parse_range_two_card_plus_notation_fixes_high_card_and_climbs_the_low_card():
    # Regression: _plus_connector used to keep the (r1,r2) GAP fixed and
    # slide the whole pair up, producing a single combo (just "AT") instead
    # of fanning out the low card under a fixed high card. ATs+ must be
    # ATs, AJs, AQs, AKs -- 4 hands x 4 suited combos = 16.
    combos = parse_range("ATs+")
    assert len(combos) == 16
    pairs = {(c.combo[0].rank, c.combo[1].rank) for c in combos}
    assert pairs == {("A", "T"), ("A", "J"), ("A", "Q"), ("A", "K")}

    # KQo+ : nothing between Q and K -> unchanged, just KQo (12 combos).
    assert len(parse_range("KQo+")) == 12
    # A2s+ : the widest possible fan, A2s..AKs -> 12 hands x 4 = 48 combos.
    assert len(parse_range("A2s+")) == 48


def test_parse_range_suited_offsuit_counts():
    suited = parse_range("AKs")
    offsuit = parse_range("AKo")
    assert len(suited) == 4
    assert len(offsuit) == 12


def test_parse_range_exact_hand():
    combos = parse_range("AsKd")
    assert len(combos) == 1
    ranks = {c.rank for c in combos[0].combo}
    assert ranks == {"A", "K"}


def test_parse_range_weighted_token():
    combos = parse_range("77@50%")
    assert len(combos) == 6
    assert all(c.weight == pytest.approx(0.5) for c in combos)


def test_parse_range_dash_range_pairs():
    combos = parse_range("22-44")
    ranks = {c.combo[0].rank for c in combos}
    assert ranks == {"2", "3", "4"}


def test_equity_aa_dominates_kk_preflop():
    r = equity("AA", "KK")
    assert r.range1_equity > 0.75
    assert r.range1_equity + r.range2_equity == pytest.approx(1.0, abs=1e-6)


def test_equity_exact_hands_on_river_is_deterministic():
    board = parse_cards(["A♠", "K♦", "7♣", "2♥", "3♦"])
    r = equity("AhKc", "QcQd", board=board)
    # hero makes two pair (aces and kings) on this board, beats pocket queens
    assert r.range1_equity == pytest.approx(1.0)
    assert r.method == "enumeration"


def test_equity_flop_enumeration_vs_monte_carlo_both_reasonable():
    board = parse_cards(["9♠", "6♠", "2♦"])
    r = equity("AA", "76s", board=board)
    assert 0.5 < r.range1_equity < 1.0


def test_equity_range_vs_range_sums_to_one():
    r = equity("QQ+,AKs", "22+,AQo+")
    assert r.range1_equity + r.range2_equity == pytest.approx(1.0, abs=1e-6)


def test_equity_rejects_dead_range():
    with pytest.raises(ValueError):
        equity("AsKs", "AsKs")  # même deux cartes exactes des deux côtés -> conflit total
