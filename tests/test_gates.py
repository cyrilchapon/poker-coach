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
