import json
from pathlib import Path

import pytest

from pokercoach import brief

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_brief_no_bet_facing_never_recommends_call_or_fold():
    # Regression: a weak hand with to_call == 0 (checked to) used to fall
    # through to G2 with verdict "call" (the budget module always offered
    # call/fold regardless of whether there was anything to call).
    raw = load_fixture("hu_flop_cbet.json")
    raw = dict(raw)
    raw["streets"] = dict(raw["streets"])
    raw["streets"]["flop"] = {"board": raw["streets"]["flop"]["board"], "actions": []}
    raw["seats"] = [dict(s) for s in raw["seats"]]
    raw["seats"][0]["cards"] = ["8♠", "8♥"]  # weak underpair, no ATT to bet
    out = brief.compute(raw)
    assert out["state"]["to_call"] == 0
    assert out["verdict"] not in ("call", "fold")
    assert out["gate"] == "G2"
    assert out["verdict"] == "check"
    assert out["budget"]["viable_actions"] == ["check"]


def test_brief_no_bet_facing_pot_odds_is_none_not_zero():
    # Regression: pot_odds/mdf_collective used to compute to 0.0/1.0 (a
    # meaningful-looking but wrong number) whenever to_call == 0 and the pot
    # was already non-empty (denom = pot + call > 0 even at call == 0),
    # instead of None ("no threshold to compare, nothing to call").
    raw = load_fixture("hu_flop_cbet.json")
    raw = dict(raw)
    raw["streets"] = dict(raw["streets"])
    raw["streets"]["flop"] = {"board": raw["streets"]["flop"]["board"], "actions": []}
    out = brief.compute(raw)
    assert out["state"]["to_call"] == 0
    assert out["state"]["pot_odds"] is None
    assert out["state"]["mdf_collective"] is None
    assert out["state"]["mdf_individual"] is None


def test_brief_unlimited_budget_no_bet_facing_is_a_forced_bet_not_grey_zone():
    # Regression: with pot_odds correctly None (see above), G3's equity
    # bounds can no longer fire on a check/bet decision -- but nothing else
    # closed it either, so an unambiguous "you have the nuts, of course you
    # bet" spot fell all the way through to G5 (full analysis) instead of a
    # terse forced verdict.
    raw = load_fixture("hu_flop_cbet.json")
    raw = dict(raw)
    raw["streets"] = dict(raw["streets"])
    raw["streets"]["flop"] = {"board": raw["streets"]["flop"]["board"], "actions": []}
    raw["seats"] = [dict(s) for s in raw["seats"]]
    raw["seats"][0]["cards"] = ["T♦", "T♣"]  # quads on this board -> "nuts", att = inf
    out = brief.compute(raw)
    assert out["hand"]["made"] == "nuts"
    assert out["state"]["to_call"] == 0
    assert out["gate"] == "G2"
    assert out["verdict"] == "bet"
    assert out["confidence"] == "forced"
    assert out["verbosity"] != "full"


def _sb_open_hand(hero_cards: list[str]) -> dict:
    return {
        "schema_version": "2.0",
        "table": {"big_blind": 1.0, "ante": 0.0, "button_seat": 0},
        "seats": [
            {"seat": 0, "is_hero": False, "stack": 100.0, "archetype": None, "hud": None,
             "cards": None, "status": "folded"},
            {"seat": 1, "is_hero": True, "stack": 100.0, "archetype": None, "hud": None,
             "cards": hero_cards, "status": "active"},
            {"seat": 2, "is_hero": False, "stack": 100.0, "archetype": None, "hud": None,
             "cards": None, "status": "active"},
        ],
        "streets": {
            "preflop": {"actions": [
                {"seat": 1, "action": "post", "amount": 0.5},
                {"seat": 2, "action": "post", "amount": 1.0},
                {"seat": 0, "action": "fold", "amount": 0.0},
            ]},
            "flop": None, "turn": None, "river": None,
        },
        "to_act": 1, "hero_seat": 1,
    }


def test_brief_any_opening_decision_is_not_misread_as_defending():
    # Regression: to_call() is inflated by the BB's forced post for EVERY
    # position, not just SB -- this used to make role() read "defender" for
    # any player's very first (opening) preflop decision, silently starving
    # G1 of the RFI lookup for realistic hands (a synthetic to_call==0
    # fixture was the only way G1 ever fired before this fix).
    raw = {
        "schema_version": "2.0",
        "table": {"big_blind": 1.0, "ante": 0.0, "button_seat": 0},
        "seats": [
            {"seat": i, "is_hero": i == 3, "stack": 100.0, "archetype": None, "hud": None,
             "cards": ["A♠", "K♠"] if i == 3 else None, "status": "active"}
            for i in range(6)
        ],
        "streets": {
            "preflop": {"actions": [
                {"seat": 1, "action": "post", "amount": 0.5},
                {"seat": 2, "action": "post", "amount": 1.0},
            ]},
            "flop": None, "turn": None, "river": None,
        },
        "to_act": 3, "hero_seat": 3,  # UTG in 6-max
    }
    out = brief.compute(raw)
    assert out["gate"] == "G1"
    assert out["verdict"] == "raise_or_call"
    assert out["range"]["note"] == "UTG 6-max"
    # The G1 gate now uses a local fix in brief.py's own check, but
    # `line.role` (surfaced verbatim to the coach for narration) must agree
    # with the actual verdict -- it used to still say "defender" here even
    # after the G1 lookup itself was fixed to fire correctly.
    assert out["line"]["role"] != "defender"


def test_brief_sb_opening_decision_is_not_misread_as_defending():
    # Regression: to_call() is inflated by the BB's forced post even though
    # nobody has voluntarily entered the pot yet -- the RFI lookup must
    # still fire for the SB's own opening decision.
    out = brief.compute(_sb_open_hand(["A♠", "T♦"]))  # ATo -> raise_range
    assert out["gate"] == "G1"
    assert out["verdict"] == "raise"
    assert out["range"]["strategy"] == "mixed_raise_limp"


def test_brief_sb_mixed_strategy_three_way_split():
    raise_hand = brief.compute(_sb_open_hand(["A♠", "T♦"]))   # ATo
    limp_hand = brief.compute(_sb_open_hand(["9♠", "8♠"]))    # 98s
    fold_hand = brief.compute(_sb_open_hand(["7♦", "2♣"]))    # 72o, in neither bucket

    assert raise_hand["verdict"] == "raise"
    assert limp_hand["verdict"] == "limp"
    assert fold_hand["verdict"] == "fold"
    assert all(out["gate"] == "G1" for out in (raise_hand, limp_hand, fold_hand))


def test_brief_postflop_smoke():
    raw = load_fixture("hu_flop_cbet.json")
    out = brief.compute(raw)
    assert out["gate"] in ("G0", "G1", "G2", "G3", "G4", "G5")
    assert "state" in out and "hand" in out and "texture" in out and "line" in out and "budget" in out
    assert out["state"]["street"] == "flop"


def test_brief_postflop_with_villain_archetype():
    raw = load_fixture("hu_flop_cbet.json")
    out = brief.compute(raw, villain_archetype="fish")
    assert "exploit" in out
    assert out["exploit"]["archetype"] == "fish"


def test_brief_preflop_clear_open_hits_g1():
    raw = load_fixture("hu_flop_cbet.json")
    raw = dict(raw)
    raw["streets"] = {
        "preflop": {"actions": [
            {"seat": 0, "action": "post", "amount": 0.5},
            {"seat": 1, "action": "post", "amount": 1.0},
        ]},
        "flop": None, "turn": None, "river": None,
    }
    raw["to_act"] = 0
    raw["seats"][0]["cards"] = ["A♠", "K♦"]  # premium hand, clearly in any RFI range
    out = brief.compute(raw)
    assert out["state"]["street"] == "preflop"
    assert out["gate"] in ("G1", "G5")  # AK is in range for HU BTN/SB open either way


def test_brief_force_full_adds_detail_without_changing_the_verdict():
    raw = load_fixture("hu_flop_cbet.json")
    raw = dict(raw)
    raw["streets"] = dict(raw["streets"])
    # An overbet big enough to exhaust hero's DEF budget on a weak hand -> G2 (forced fold).
    raw["streets"]["flop"] = {"board": raw["streets"]["flop"]["board"],
                               "actions": [{"seat": 1, "action": "bet", "amount": 40.0}]}

    gate_only = brief.compute(raw)
    assert gate_only["gate"] == "G2"
    assert gate_only["verdict"] == "fold"
    assert "equity" not in gate_only
    assert gate_only["verbosity"] != "full"

    full = brief.compute(raw, force_full=True)
    # Same decision, more detail.
    assert full["gate"] == "G2"
    assert full["verdict"] == "fold"
    assert full["verbosity"] == "full"
    assert "equity" in full
    assert "vs_range_wide" in full["equity"] and "vs_range_narrow" in full["equity"]


def test_brief_narrows_villain_range_through_action_history():
    raw = load_fixture("hu_flop_cbet.json")
    raw = dict(raw)
    raw["streets"] = dict(raw["streets"])
    # Villain bets big on the flop, then bets again on the turn -> the narrow
    # (premium-only) seed should shrink further than it started.
    raw["streets"]["flop"] = {"board": raw["streets"]["flop"]["board"],
                               "actions": [{"seat": 1, "action": "bet", "amount": 8.0}]}
    raw["streets"]["turn"] = {"board": raw["streets"]["flop"]["board"] + ["5♦"],
                               "actions": [{"seat": 1, "action": "bet", "amount": 24.0}]}
    raw["to_act"] = 0

    out = brief.compute(raw, force_full=True)
    from pokercoach.equity import parse_range
    from pokercoach.brief import NARROW_VILLAIN_SEED

    seed_combos = len(parse_range(NARROW_VILLAIN_SEED))
    result_combos = len(parse_range(out["equity"]["vs_range_narrow"]))
    assert result_combos < seed_combos


def test_brief_never_crashes_on_river():
    raw = load_fixture("hu_flop_cbet.json")
    raw = dict(raw)
    raw["streets"]["flop"]["actions"].append({"seat": 0, "action": "call", "amount": 4.0})
    raw["streets"]["turn"] = {"board": ["T♠", "9♥", "2♣", "5♦"], "actions": [
        {"seat": 1, "action": "check", "amount": 0}, {"seat": 0, "action": "check", "amount": 0}]}
    raw["streets"]["river"] = {"board": ["T♠", "9♥", "2♣", "5♦", "8♥"], "actions": [
        {"seat": 1, "action": "bet", "amount": 6.0}]}
    raw["to_act"] = 0
    out = brief.compute(raw)
    assert out["state"]["street"] == "river"
    assert out["hand"]["outs"] is None  # plus de tirage possible à la river
