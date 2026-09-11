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


def test_vs_rfi_tightens_for_a_passive_archetype_that_still_raised():
    # Regression: --villain-archetype was accepted by pc brief but never
    # threaded down to the defend-range lookup -- a fish/calling_station
    # RAISING (not just calling) is a stronger signal than their table
    # image, not a wider one.
    state = validate_and_load(minimal_hand(6, button_seat=0, hero_seat=2))  # BB defending
    key = table.derive_key(state, 2, scenario="vs_rfi")
    plain = table.vs_rfi(key, opener_n_behind=4)
    vs_fish = table.vs_rfi(key, opener_n_behind=4, villain_archetype="fish")
    vs_maniac = table.vs_rfi(key, opener_n_behind=4, villain_archetype="maniac")
    assert vs_fish.pct < plain.pct
    assert vs_maniac.pct > plain.pct


def test_vs_rfi_tightens_further_for_a_raise_over_a_limp():
    # Regression: a raise over a limp (isolation, dead money + an already-
    # committed player) was treated identically to a raise into an empty
    # pot -- same "vs ouverture" note either way.
    state = validate_and_load(minimal_hand(6, button_seat=0, hero_seat=2))
    key = table.derive_key(state, 2, scenario="vs_rfi")
    plain = table.vs_rfi(key, opener_n_behind=4)
    iso = table.vs_rfi(key, opener_n_behind=4, iso_over_limp=True)
    assert iso.pct < plain.pct


def test_is_a_raise_over_a_limp_detects_the_iso_not_a_plain_open():
    from pokercoach.actionline import is_a_raise_over_a_limp

    hand = minimal_hand(6, button_seat=0, hero_seat=2)
    hand["streets"]["preflop"]["actions"] = [
        {"seat": 3, "action": "call", "amount": 1.0},   # UTG limps
        {"seat": 4, "action": "raise", "amount": 6.0},  # HJ isolates over the limp
    ]
    state = validate_and_load(hand)
    assert is_a_raise_over_a_limp(state) is True

    hand2 = minimal_hand(6, button_seat=0, hero_seat=2)
    hand2["streets"]["preflop"]["actions"] = [
        {"seat": 4, "action": "raise", "amount": 3.0},  # HJ opens a fresh pot
    ]
    state2 = validate_and_load(hand2)
    assert is_a_raise_over_a_limp(state2) is False


def test_vs_limp_widens_over_rfi():
    state = validate_and_load(minimal_hand(6, button_seat=0, hero_seat=5))  # CO
    key = table.derive_key(state, 5)
    rfi_entry = table.rfi(key)
    limp_entry = table.vs_limp(key)
    assert limp_entry.pct > rfi_entry.pct


def test_sb_rfi_is_a_disjoint_mixed_raise_limp_strategy():
    from pokercoach.equity import parse_range

    state = validate_and_load(minimal_hand(6, button_seat=0, hero_seat=1))  # seat1 = SB
    key = table.derive_key(state, 1)
    entry = table.rfi(key)

    assert entry.strategy == "mixed_raise_limp"
    assert entry.raise_range and entry.limp_range
    assert entry.range == f"{entry.raise_range},{entry.limp_range}"

    raise_combos = {frozenset((c.rank, c.suit) for c in wc.combo) for wc in parse_range(entry.raise_range)}
    limp_combos = {frozenset((c.rank, c.suit) for c in wc.combo) for wc in parse_range(entry.limp_range)}
    assert raise_combos.isdisjoint(limp_combos)  # jamais les deux à la fois pour une même main


def test_hu_btn_sb_rfi_excludes_exactly_the_documented_offsuit_combos():
    # Regression: the YAML comment claimed 11 excluded offsuit combos but
    # the actual range (via the "74o+"-style fan notation) excludes 12 --
    # "73o" was missing from the documented list, silently mismatched from
    # what the range notation actually produces.
    from pokercoach.equity import RANKS, parse_range

    state = validate_and_load(minimal_hand(2, button_seat=0, hero_seat=0))  # HU BTN/SB
    key = table.derive_key(state, 0)
    entry = table.rfi(key)

    combos = parse_range(entry.range)
    offsuit_rank_pairs = {
        frozenset(c.rank for c in wc.combo)
        for wc in combos
        if wc.combo[0].rank != wc.combo[1].rank and wc.combo[0].suit != wc.combo[1].suit
    }

    expected_excluded = {
        frozenset(pair) for pair in
        ["72", "73", "82", "92", "83", "62", "63", "52", "53", "42", "43", "32"]
    }
    all_offsuit_types = {
        frozenset((a, b)) for i, a in enumerate(RANKS) for b in RANKS[i + 1:]
    }
    expected_included = all_offsuit_types - expected_excluded

    assert offsuit_rank_pairs == expected_included
    assert offsuit_rank_pairs.isdisjoint(expected_excluded)


def test_top_pct_range_returns_a_parseable_range_close_to_the_requested_pct():
    from pokercoach.equity import parse_range

    combos = parse_range(table.top_pct_range(15.0))
    # 1326 total combos; top-15% should land close to 15% by combo count
    # (rounds up to the next full hand-type crossing the threshold).
    assert 0.10 < len(combos) / 1326 < 0.20


def test_top_pct_range_is_monotonic_and_starts_with_the_strongest_hands():
    from pokercoach.equity import parse_range

    def combo_set(pct):
        return {frozenset((c.rank, c.suit) for c in wc.combo) for wc in parse_range(table.top_pct_range(pct))}

    narrow, wide = combo_set(2.0), combo_set(20.0)
    assert narrow < wide  # strictly smaller, and a subset (monotonic widening)
    assert table.top_pct_range(1.0).startswith("AA")  # strongest hand type first


def test_top_pct_range_clamps_to_full_range_above_100_pct():
    from pokercoach.equity import parse_range
    assert len(parse_range(table.top_pct_range(100.0))) == 1326
    assert len(parse_range(table.top_pct_range(150.0))) == 1326


def test_narrow_removes_combos_that_cannot_support_a_raise():
    board = parse_cards(["9♦", "6♣", "2♥"])
    # Some pressure already spent this street: trash (ATT baseline ~0.5) can
    # no longer fund a raise, an overpair (ATT baseline ~3+) still can.
    # Regression: combos that fail purely because pressure exhausted their
    # budget are no longer dropped outright -- they're retained at a small
    # floor weight (MIN_BLUFF_FLOOR_WEIGHT) rather than vanishing entirely,
    # so `remaining_combos` (a count) no longer shrinks; `remaining_weight`
    # (the actual retained probability mass) does.
    result = narrow.narrow("QQ+,72o", board, "raise", pot_type="srp", street="flop",
                            pressure_spent=1.0)
    assert result.remaining_weight < result.original_weight
    assert "72o" not in result.range_str  # exact combos, not the bare token
    assert "@8.00%" in result.range_str  # 72o's combos floored, not dropped


def test_narrow_drops_structurally_excluded_combos_entirely_not_floored():
    # Regression guard alongside the floor mechanism above: a combo cut by a
    # STRUCTURAL rule (bluff_dies_multiway -- "this line makes no sense
    # multiway", not "pressure ran the budget dry") must stay a hard
    # exclusion, not receive the pressure-exhaustion floor -- otherwise the
    # fix for the degenerate-bounds problem would silently walk back the
    # multiway/exploit gates' own deliberate "no bluffs here" rulings.
    board = parse_cards(["T♦", "8♣", "3♥"])
    result = narrow.narrow("96s,QQ+", board, "bet", pot_type="srp", street="flop",
                            n_opponents_active=3)
    for suit in "♠♥♦♣":
        assert f"9{suit}6{suit}" not in result.range_str  # dropped entirely, no @xx% floor either


def test_narrow_fold_keeps_everything():
    board = parse_cards(["9♦", "6♣", "2♥"])
    result = narrow.narrow("22+", board, "fold", pot_type="srp", street="flop")
    assert result.remaining_combos == result.original_combos


def test_narrow_check_keeps_everything():
    # Regression: "check" used to be mapped onto the same "call" bucket as
    # a real call (gated by DEF), when checking is free and shouldn't be
    # filtered by budget at all.
    board = parse_cards(["9♦", "6♣", "2♥"])
    result = narrow.narrow("22+,72o", board, "check", pot_type="srp", street="flop")
    assert result.remaining_combos == result.original_combos


def test_narrow_bet_removes_combos_that_cannot_fund_a_bet():
    board = parse_cards(["9♦", "6♣", "2♥"])
    result = narrow.narrow("QQ+,72o", board, "bet", pot_type="srp", street="flop",
                            pressure_spent=1.0)
    assert result.remaining_weight < result.original_weight


# --- cohérence des compteurs de narrow (rapport de bug live-session) --------

def test_narrow_counters_separate_kept_floored_and_removed():
    # Bug report: `remaining_combos` stayed equal to `original_combos` on
    # check/bet/call while `retained_pct` moved -- the two read as
    # contradictory. They are not: a combo whose budget can't fund the action
    # is RETAINED at the bluff floor, not removed, so the count is flat by
    # design and the weighted percentage is what carries the filtering. The
    # output now says which is which instead of leaving it to be inferred.
    board = parse_cards(["9♦", "6♣", "2♥"])
    result = narrow.narrow("QQ+,72o", board, "bet", pot_type="srp", street="flop",
                            pressure_spent=1.0)
    out = result.to_json()
    assert out["combos_kept_full_weight"] + out["combos_kept_at_bluff_floor"] == out["remaining_combos"]
    assert out["remaining_combos"] + out["combos_removed"] == out["original_combos"]
    assert out["combos_kept_at_bluff_floor"] > 0
    assert out["retained_pct"] < 100.0
    assert out["retained_pct_basis"].startswith("poids")
    assert "plancher" in out["note"]


def test_narrow_reports_no_filtering_for_fold_and_check():
    # `retained_pct` == 100 on these two actions is not a measurement, it is
    # "this action filters nothing" -- stated explicitly rather than left to
    # look like a filter that happened to keep everything.
    board = parse_cards(["9♦", "6♣", "2♥"])
    for action in ("fold", "check"):
        out = narrow.narrow("22+,72o", board, action, pot_type="srp", street="flop").to_json()
        assert out["action"] == action
        assert out["filters_combos"] is False
        assert out["combos_kept_at_bluff_floor"] == 0
        assert out["combos_removed"] == 0
        assert out["retained_pct"] == 100.0
        assert "AUCUN filtrage" in out["note"]


def test_narrow_counts_structurally_removed_combos_as_removed():
    # The other side: a combo cut by a structural rule really does leave the
    # output range, so it lands in `combos_removed`, not in the floor bucket.
    board = parse_cards(["T♦", "8♣", "3♥"])
    out = narrow.narrow("96s,QQ+", board, "bet", pot_type="srp", street="flop",
                         n_opponents_active=3).to_json()
    assert out["combos_removed"] > 0
    assert out["remaining_combos"] < out["original_combos"]
