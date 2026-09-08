import pytest

from pokercoach import gates


def test_g2_budget_exhausted_fallback_facing_a_bet_is_strong_not_forced():
    # Regression: this fallback ("call"/"fold" when ATT/DEF is exhausted
    # while facing a bet) used to announce confidence="forced", implying
    # the same certainty as a deterministic G0/G1 lookup -- but it's a
    # tabulated heuristic that a genuinely calculated G3 equity CAN
    # contradict (verified: a real spot where this fallback rendered
    # "fold" while the equity engine gave 52-64% against a 30% threshold).
    decision = gates.g2_budget_decisive(
        envisaged_action="call", viable_actions=["raise", "fold"],
        att_remaining=1.0, facing_bet=True,
    )
    assert decision is not None
    assert decision.verdict == "fold"
    assert decision.confidence == "strong"


def test_g2_budget_exhausted_fallback_not_facing_a_bet_stays_forced():
    # The "check" fallback (nothing to call) can NEVER be contradicted by
    # G3 -- there's no pot-odds threshold to compare against without a bet
    # to call (state.derive() leaves pot_odds as None in that case), so G3
    # never even fires here. "forced" remains legitimate.
    decision = gates.g2_budget_decisive(
        envisaged_action="bet", viable_actions=["check"],
        att_remaining=0.0, facing_bet=False,
    )
    assert decision is not None
    assert decision.verdict == "check"
    assert decision.confidence == "forced"


def test_g2_unlimited_budget_bet_stays_forced():
    # The "unlimited ATT (nuts) -> bet" side is unrelated to the fallback
    # above and untouched by this fix: an unbeatable hand's equity can't
    # meaningfully be "contradicted" by G3.
    decision = gates.g2_budget_decisive(
        envisaged_action="bet", viable_actions=["bet"],
        att_remaining=float("inf"), facing_bet=False,
    )
    assert decision is not None
    assert decision.verdict == "bet"
    assert decision.confidence == "forced"


def test_g2_budget_exhausted_fallback_to_call_is_also_strong():
    decision = gates.g2_budget_decisive(
        envisaged_action="raise", viable_actions=["call", "fold"],
        att_remaining=0.0, facing_bet=True,
    )
    assert decision is not None
    assert decision.verdict == "call"
    assert decision.confidence == "strong"


def test_g1_raise_only_out_of_range_defers_instead_of_folding():
    # Bug fix: a "raise-only" range (squeeze()) doesn't cover the call
    # option at all -- being out of it must never mean "fold" (that's a
    # verdict on a decision G1 never evaluated), it must mean "no verdict
    # yet, ask elsewhere" (cf. brief._compute_preflop_squeeze_equity_section
    # / gate G1B).
    decision = gates.g1_preflop_range(in_range=False, range_confidence="extrapolated", raise_only=True)
    assert decision is None


def test_g1_raise_only_in_range_still_decides():
    decision = gates.g1_preflop_range(in_range=True, verdict_if_in_range="raise",
                                       range_confidence="extrapolated", raise_only=True)
    assert decision is not None
    assert decision.verdict == "raise"
    assert decision.confidence == "strong"


def test_g1_non_raise_only_out_of_range_still_folds():
    # Unchanged behaviour for the ordinary case (a full defend range, e.g.
    # vs_rfi/vs_limp/vs_3bet/vs_4bet, covers call AND raise -- being out of
    # it legitimately means fold).
    decision = gates.g1_preflop_range(in_range=False, range_confidence="extrapolated")
    assert decision is not None
    assert decision.verdict == "fold"


def test_g1b_squeeze_declined_favorable_odds_calls():
    decision = gates.g1b_squeeze_declined_pot_odds(lower_bound=0.20, upper_bound=0.25, threshold=0.1154)
    assert decision is not None
    assert decision.gate == "G1B"
    assert decision.verdict == "call"
    assert decision.confidence == "strong"


def test_g1b_squeeze_declined_unfavorable_odds_folds():
    decision = gates.g1b_squeeze_declined_pot_odds(lower_bound=0.02, upper_bound=0.03, threshold=0.30)
    assert decision is not None
    assert decision.verdict == "fold"


def test_g1b_squeeze_declined_straddling_band_escalates():
    decision = gates.g1b_squeeze_declined_pot_odds(lower_bound=0.10, upper_bound=0.13, threshold=0.1154)
    assert decision is None
