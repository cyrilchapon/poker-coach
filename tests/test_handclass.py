import pytest

from pokercoach.cards import parse_cards
from pokercoach.handclass import classify


def H(hole, board):
    return classify(parse_cards(hole), parse_cards(board))


def test_nuts_full_house():
    r = H(["K♠", "K♥"], ["K♦", "K♣", "2♥"])  # quads
    assert r.made == "nuts"


def test_nut_flush():
    r = H(["A♠", "5♠"], ["K♠", "7♠", "2♠"])
    assert r.made == "nuts"  # nut flush = unbeatable on this board


def test_non_nut_flush_big_bucket():
    r = H(["Q♠", "T♠"], ["K♠", "7♠", "2♠", "9♦"])  # ace of spades still out there
    assert r.made == "flush"
    assert r.made_sub["board_type"] == "three_flush"
    assert r.made_sub["rank_bucket"] == "big"  # Q high, >= T


def test_two_card_straight_not_nuts_when_a_higher_straight_remains_possible():
    # board T-9-8 already supplies 3 of a HIGHER window (J-T-9-8-7): an
    # opponent holding J + a different 7 would beat hero's straight, so this
    # is a genuine (non-nut) two-card straight, not "nuts".
    r = H(["7♠", "6♦"], ["T♦", "9♣", "8♥"])
    assert r.made == "straight"
    assert r.made_sub["contribution"] == "two_card"


def test_one_card_top_end_straight_beaten_by_a_live_flush():
    # Ace-high straight (the top of the straight hierarchy, nothing outranks
    # it as a straight) but the board is three-flush, so a made flush for the
    # opponent still beats it -> not globally "nuts", but the nut STRAIGHT.
    r = H(["T♦", "2♥"], ["A♦", "K♦", "Q♦", "J♣"])
    assert r.made == "straight"
    assert r.made_sub["contribution"] == "one_card_top_end"
    assert r.made_sub["board_flushiness"] == "three_flush"


def test_set_vs_trips():
    set_hand = H(["7♠", "7♥"], ["7♦", "K♣", "2♥"])
    assert set_hand.made == "set"
    trips_hand = H(["7♠", "K♥"], ["7♦", "7♣", "2♥"])
    assert trips_hand.made == "trips"


def test_genuine_two_pair_on_unpaired_board():
    r = H(["9♠", "4♥"], ["9♦", "4♣", "2♥"])
    assert r.made == "two_pair"
    assert "rank_bucket" in r.made_sub


def test_two_pair_reclassified_when_board_already_paired():
    # board 9-9-4: hero pairs the 4 -> "two pair" structurally, but one pair
    # comes purely from the board, so PokerSkill treats it as a plain pair.
    r = H(["4♠", "K♥"], ["9♦", "9♣", "4♥"])
    assert r.made in ("top_pair", "second_pair", "third_pair", "fourth_fifth_pair")


def test_double_paired_board_is_flagged_as_special_override():
    r = H(["4♠", "K♥"], ["9♦", "9♣", "4♥", "4♦"])
    assert r.board_override == "double_paired_board"


def test_overpair():
    r = H(["Q♠", "Q♥"], ["9♦", "6♣", "2♥"])
    assert r.made == "overpair"
    assert r.made_sub["pocket_rank"] == "Q"


def test_top_pair_top_kicker():
    r = H(["A♠", "9♥"], ["9♦", "6♣", "2♥"])
    assert r.made == "top_pair"
    assert r.made_sub["kicker_bucket"] == "tptk"


def test_top_pair_weak_kicker():
    r = H(["9♠", "2♥"], ["9♦", "8♣", "6♥", "3♦"])
    assert r.made == "top_pair"
    assert r.made_sub["kicker_bucket"] in ("k4", "k5", "other")


def test_second_and_third_pair():
    second = H(["8♠", "K♥"], ["9♦", "8♣", "2♥"])
    assert second.made == "second_pair"
    third = H(["2♠", "K♥"], ["9♦", "8♣", "2♥"])
    assert third.made == "third_pair"


def test_underpair_is_weak_showdown():
    r = H(["5♠", "5♥"], ["9♦", "8♣", "2♥"])
    assert r.made == "weak_showdown"


def test_high_card_buckets():
    # board has no ace, no king -> A-high is the nut no-pair hand
    nuts_high = H(["A♠", "4♥"], ["9♦", "8♣", "2♥"])
    assert nuts_high.made == "nuts_high"
    second_high = H(["K♠", "4♥"], ["9♦", "8♣", "2♥"])
    assert second_high.made == "second_high"
    trash = H(["6♠", "4♥"], ["9♦", "8♣", "2♥"])
    assert trash.made in ("trash", "weak_showdown")


def test_flush_draw_detected():
    r = H(["A♠", "K♠"], ["9♠", "6♠", "2♥"])
    assert r.draw is not None
    assert r.draw_sub["flush_draw"] is True


def test_open_ended_straight_draw():
    r = H(["9♠", "8♥"], ["7♦", "6♣", "2♥"])
    assert r.draw_sub["straight_shape"] == "open_ended"


def test_gutshot_draw():
    r = H(["9♠", "6♥"], ["T♦", "8♣", "3♥"])
    assert r.draw_sub["straight_shape"] == "gutshot"


def test_no_draw_on_river():
    r = H(["A♠", "K♥"], ["9♦", "6♣", "2♥", "3♦", "7♠"])
    assert r.draw is None
    assert r.outs is None


def test_outs_present_on_flop_and_turn():
    r = H(["A♠", "K♠"], ["9♠", "6♠", "2♥"])
    assert r.outs is not None
    assert r.outs > 0


def test_nut_flush_ace_blocker():
    r = H(["A♠", "4♥"], ["9♠", "6♠", "2♠"])  # three-flush board + hero holds the ace of spades
    assert "bloque la couleur nut" in r.blockers
