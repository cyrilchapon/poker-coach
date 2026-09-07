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


def test_outs_counts_category_jumps_not_raw_score_improvements():
    # Regression: raw-score comparison (`evaluate(...) > current`) counted
    # nearly all 47 remaining cards as "outs" because adding any 6th known
    # card to a 5-card known set almost always improves the best-5-of-6
    # slightly (it replaces the weakest kicker) without changing the hand's
    # CATEGORY. Comparing handtype() category instead gives a sane count
    # (47 -> 11), and the round-3 fix below narrows it further to the
    # genuinely hero-specific outs: a Q (3, kicker pairs -> two pair) or
    # the last K (2, hero's own hole card trips up) = 5. The 7s/2s (board
    # pairing K's existing board pair into KK77 for ANY king holder, not
    # specific to hero) are excluded -- see
    # test_outs_excludes_pure_board_pairing_on_an_already_made_pair.
    r = H(["K♦", "Q♠"], ["K♥", "7♣", "2♦"])
    assert r.made == "top_pair"
    assert r.outs == 5


def test_outs_ghost_flush_draw_no_longer_inflates_count():
    # AsKs on 2s5s9d (a real flush draw: 4 spades between hole+board) used to
    # report outs=47; category-based counting keeps it sane (well under the
    # full remaining deck).
    r = H(["A♠", "K♠"], ["2♠", "5♠", "9♦"])
    assert r.outs is not None
    assert r.outs < 30


def test_outs_excludes_board_pairs_hero_has_no_stake_in():
    # Round-2 regression (caught by re-review of the round-1 fix): a card
    # that pairs an EXISTING board rank hero holds no stake in (e.g. 2s5s9d,
    # hero A-K) changes hero's category (High Card -> Pair) exactly as much
    # as it would for ANY random hand -- that's not a hero-specific out,
    # it's the board pairing for everyone. Filtered by comparing hero's
    # resulting category against what a neutral (unrelated) hand would get
    # from the same card: 2s/2h/2d/2c, 5s/5h/5d/5c and 9d/9h/9c/9s (9 cards,
    # minus the ones already known) all fail that test here.
    r = H(["A♠", "K♠"], ["2♠", "5♠", "9♦"])
    assert r.outs == 15  # 23 category-jumping cards, 8 are pure board pairs


def test_outs_keeps_a_flush_completion_that_happens_to_share_a_board_rank():
    # Round-2 regression: a naive "exclude any card whose RANK already
    # appears on the board" rule (the obvious first attempt at the fix
    # above) would wrongly exclude 9s here -- its rank (9) matches the
    # board's 9d, but what actually makes it an out is completing hero's
    # spade flush, which a neutral hand holding no spades would NOT get.
    # The category comparison (hero's Flush vs a neutral hand's Pair on the
    # same card) correctly keeps it.
    r = H(["A♠", "K♠"], ["2♠", "5♠", "9♦"])
    hole = ["A♠", "K♠"]
    from pokercoach.cards import parse_cards
    from pokercoach.handeval import evaluate, handtype
    nine_spades_hand = parse_cards(hole) + parse_cards(["2♠", "5♠", "9♦", "9♠"])
    assert handtype(evaluate(nine_spades_hand)) == "Flush"
    # and it must be reflected in the final outs count (see the 15 above,
    # which is 23 - 8, not 23 - 9 -- the naive rule would have given 14).
    assert r.outs == 15


def test_outs_excludes_pure_board_pairing_on_an_already_made_pair():
    # Round-3 regression (re-review of round 2's fix): on K♦Q♠/K♥7♣2♦, hero
    # already holds top pair Kings -- a 7 gives him KK77 (Two Pair), which
    # beats a NEUTRAL hand's mere Pair(7), so round 2's neutral comparison
    # counted it as an out. But that same 7 gives Two Pair to literally any
    # OTHER King holder too, since the improvement comes entirely from
    # pairing the board's own 7, not from anything specific to hero's hand.
    # The last two Kings (his own hole card tripping up) ARE genuinely
    # hero-specific and stay counted: 3 Qs (kicker pairs) + 2 Ks (trips)
    # = 5, matching the reviewer's own hand count exactly.
    r = H(["K♦", "Q♠"], ["K♥", "7♣", "2♦"])
    assert r.made == "top_pair"
    assert r.outs == 5


def test_outs_still_counts_a_real_trips_out_on_an_already_made_pair():
    # Guard against over-correcting round 3: a card that pairs one of
    # HERO'S OWN hole cards (not just an existing board rank) is a real,
    # hero-specific out -- even though any other holder of that exact rank
    # would benefit identically, it's still HIS card tripping up, not a
    # generic board-level event. An earlier draft of the round-3 fix
    # (comparing to a "same class, different kicker" reference hand)
    # wrongly excluded this case; the final fix (excluding only pure
    # board-rank pairings that don't touch either hole card) does not.
    r = H(["K♦", "Q♠"], ["K♥", "7♣", "2♦"])
    from pokercoach.cards import parse_cards
    from pokercoach.handeval import evaluate, handtype
    trips_hand = parse_cards(["K♦", "Q♠"]) + parse_cards(["K♥", "7♣", "2♦", "K♠"])
    assert handtype(evaluate(trips_hand)) == "Trips"
    # both remaining Kings (Ks, Kc) must be among the counted outs
    assert r.outs == 5  # 3 Qs + 2 Ks -- verified precisely, not just "> 0"


def test_outs_pure_board_pairing_rule_does_not_break_unpaired_hands():
    # Guard against over-scoping round 3: the "pure board pairing" rule
    # must only kick in once hero ALREADY has a made pair -- applying it to
    # an unpaired hand (no pair yet at all) would wrongly re-exclude a
    # flush-completing card just because its RANK happens to coincide with
    # an existing board rank (exactly the round-2 "naive rule" bug, cf.
    # test_outs_keeps_a_flush_completion_that_happens_to_share_a_board_rank
    # below -- this guards that round 2 fix doesn't regress under round 3).
    r = H(["A♠", "K♠"], ["2♠", "5♠", "9♦"])  # nuts_high, not a made pair
    assert r.made != "top_pair"
    assert r.outs == 15


def test_pair_family_classification_is_independent_of_hole_card_order():
    # Regression: on a board already paired (K♥K♦), both hero hole cards
    # (7h and 5d) match a board rank each -- `matched[0]` used to just be
    # "whichever hole card came first in the JSON", so the same hand
    # classified as second_pair or third_pair depending purely on input
    # order. Sorting `matched` by board-rank position fixes this.
    board = ["K♥", "K♦", "7♣", "5♠"]
    a = H(["7♥", "5♦"], board)
    b = H(["5♦", "7♥"], board)
    assert a.made == b.made == "second_pair"


def test_flush_draw_requires_hero_to_hold_a_suited_card():
    # Regression: on a board that is ALREADY a 4-flush (four board cards of
    # one suit), suit_counts[flush_suit] reaches 4 from the board alone even
    # when hero holds zero cards of that suit -- has_flush_draw was True
    # with flush_high=None, silently falling through to "weak_draw" (a
    # semi-bluff budget hero has no business getting: he's just playing the
    # board's flush, not drawing to his own).
    r = H(["A♠", "K♦"], ["2♥", "7♥", "9♥", "J♥"])
    assert r.draw_sub.get("flush_draw") is not True
    assert r.draw != "weak_draw"
