import json
from pathlib import Path

import pytest

from pokercoach import brief

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_brief_refuses_when_it_is_not_the_heros_turn():
    # Regression: hero_seat/to_act were mixed within compute() (preflop read
    # to_act's cards, postflop read hero_seat's, pressure always to_act's) --
    # if they ever diverged, the brief silently mixed hero's cards with
    # someone else's pot/to_call/budget context instead of failing loudly.
    raw = load_fixture("hu_flop_cbet.json")
    raw = dict(raw)
    raw["to_act"] = 1  # villain's seat, not hero's
    with pytest.raises(ValueError, match="hero"):
        brief.compute(raw)


def test_brief_flags_disagreement_between_g2_fold_and_a_contradicting_g3(monkeypatch):
    # Deterministic version of the review's finding (G2's budget-exhausted
    # fold can contradict a genuinely calculated G3) -- rather than hunting
    # for a fragile natural fixture that happens to trigger both budget
    # exhaustion AND a specific equity spread, force the G3 side via
    # monkeypatch and check the disagreement flag/verdict-stability directly.
    from pokercoach import brief as brief_mod
    from pokercoach.gates import GateDecision

    raw = load_fixture("hu_flop_cbet.json")
    raw = dict(raw)
    raw["streets"] = dict(raw["streets"])
    # A huge overbet exhausts hero's DEF budget on a weak hand -> G2 forces fold.
    raw["streets"]["flop"] = {"board": raw["streets"]["flop"]["board"],
                               "actions": [{"seat": 1, "action": "bet", "amount": 40.0}]}

    gate_only = brief.compute(raw)
    assert gate_only["gate"] == "G2"
    assert gate_only["verdict"] == "fold"
    assert gate_only["confidence"] == "strong"  # not "forced" (see test_gates.py)

    contradicting_g3 = GateDecision(gate="G3", verdict="call_or_raise", confidence="strong")
    monkeypatch.setattr(
        brief_mod, "_compute_equity_section",
        lambda *a, **k: ({"lower_bound": 0.6, "upper_bound": 0.7, "threshold": 0.3,
                           "vs_range_wide": "AA", "vs_range_narrow": "AA",
                           "method": "enumeration_or_monte_carlo"}, contradicting_g3),
    )
    full = brief.compute(raw, force_full=True)
    assert full["gate"] == "G2"
    assert full["verdict"] == "fold"  # G2's verdict is never overridden by G3
    assert full["gate_disagreement"]["closing_gate"] == "G2"
    assert full["gate_disagreement"]["closing_verdict"] == "fold"
    assert full["gate_disagreement"]["g3_verdict"] == "call_or_raise"


def test_brief_no_disagreement_flag_when_g3_agrees(monkeypatch):
    from pokercoach import brief as brief_mod
    from pokercoach.gates import GateDecision

    raw = load_fixture("hu_flop_cbet.json")
    raw = dict(raw)
    raw["streets"] = dict(raw["streets"])
    raw["streets"]["flop"] = {"board": raw["streets"]["flop"]["board"],
                               "actions": [{"seat": 1, "action": "bet", "amount": 40.0}]}

    agreeing_g3 = GateDecision(gate="G3", verdict="fold", confidence="strong")
    monkeypatch.setattr(
        brief_mod, "_compute_equity_section",
        lambda *a, **k: ({"lower_bound": 0.1, "upper_bound": 0.15, "threshold": 0.3,
                           "vs_range_wide": "22", "vs_range_narrow": "22",
                           "method": "enumeration_or_monte_carlo"}, agreeing_g3),
    )
    full = brief.compute(raw, force_full=True)
    assert full["verdict"] == "fold"
    assert "gate_disagreement" not in full


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


def _defend_hand(hero_cards: list[str], preflop_actions: list[dict], *, n_seats: int = 3) -> dict:
    return {
        "schema_version": "2.0",
        "table": {"big_blind": 1.0, "ante": 0.0, "button_seat": 0},
        "seats": [
            {"seat": i, "is_hero": i == n_seats - 1, "stack": 200.0, "archetype": None,
             "hud": None, "cards": hero_cards if i == n_seats - 1 else None, "status": "active"}
            for i in range(n_seats)
        ],
        "streets": {
            "preflop": {"actions": preflop_actions},
            "flop": None, "turn": None, "river": None,
        },
        "to_act": n_seats - 1, "hero_seat": n_seats - 1,
    }


def test_brief_defends_vs_rfi_no_longer_falls_through_to_g5():
    # Regression: `pc brief` covered RFI (opening) but every DEFENDING
    # decision (facing an open/limp/3bet/4bet) fell through to G5 -- the
    # engine never used ranges/table.py's vs_rfi/vs_limp/squeeze/vs_3bet/
    # vs_4bet, even though they existed and were unit-tested in isolation.
    strong = brief.compute(_defend_hand(["A♠", "K♠"], [
        {"seat": 0, "action": "post", "amount": 0.5},
        {"seat": 1, "action": "post", "amount": 1.0},
        {"seat": 2, "action": "raise", "amount": 3.0},  # someone opened -- hero (seat0, BB here) defends
    ], n_seats=3))
    weak = brief.compute(_defend_hand(["7♠", "2♥"], [
        {"seat": 0, "action": "post", "amount": 0.5},
        {"seat": 1, "action": "post", "amount": 1.0},
        {"seat": 2, "action": "raise", "amount": 3.0},
    ], n_seats=3))
    for out in (strong, weak):
        assert out["gate"] == "G1"
        assert out["range"]["scenario"] == "vs_rfi"
        assert out["range"]["confidence"] == "extrapolated"
    assert strong["verdict"] == "raise_or_call"
    assert weak["verdict"] == "fold"


def test_brief_defends_vs_limp():
    # 4-handed, hero on the BTN (seat0) isolating a limp from CO (seat3,
    # the first to act preflop in a 4-max game -- BB (seat2) has no RFI row
    # of its own, since it can never open, so vs_limp needs a hero position
    # that DOES to produce a real range; testing from BTN matches the
    # realistic "isolate a limper" spot anyway).
    raw = {
        "schema_version": "2.0",
        "table": {"big_blind": 1.0, "ante": 0.0, "button_seat": 0},
        "seats": [
            {"seat": 0, "is_hero": True, "stack": 200.0, "archetype": None, "hud": None,
             "cards": ["A♠", "A♥"], "status": "active"},
            {"seat": 1, "is_hero": False, "stack": 200.0, "archetype": None, "hud": None,
             "cards": None, "status": "active"},
            {"seat": 2, "is_hero": False, "stack": 200.0, "archetype": None, "hud": None,
             "cards": None, "status": "active"},
            {"seat": 3, "is_hero": False, "stack": 200.0, "archetype": None, "hud": None,
             "cards": None, "status": "active"},
        ],
        "streets": {
            "preflop": {"actions": [
                {"seat": 1, "action": "post", "amount": 0.5},
                {"seat": 2, "action": "post", "amount": 1.0},
                {"seat": 3, "action": "call", "amount": 1.0},  # CO limps (first to act, 4-max)
            ]},
            "flop": None, "turn": None, "river": None,
        },
        "to_act": 0, "hero_seat": 0,
    }
    out = brief.compute(raw)
    assert out["gate"] == "G1"
    assert out["range"]["scenario"] == "vs_limp"
    assert out["verdict"] == "raise_or_call"
    # Regression: G1 rendered "raise_or_call" on an isolation decision with
    # no sizing attached at all -- the coach had nothing but its own
    # judgment for "how much". 3bb base + 1bb for the one limper (seat3).
    assert out["sizing"]["raise_to_bb"] == pytest.approx(4.0)
    assert out["sizing"]["n_limpers"] == 1


def test_brief_preflop_sizing_bumps_for_a_calling_station_and_scales_with_limpers():
    raw = {
        "schema_version": "2.0",
        "table": {"big_blind": 1.0, "ante": 0.0, "button_seat": 0},
        "seats": [
            {"seat": 0, "is_hero": True, "stack": 200.0, "archetype": None, "hud": None,
             "cards": ["A♠", "A♥"], "status": "active"},
            {"seat": 1, "is_hero": False, "stack": 200.0, "archetype": None, "hud": None,
             "cards": None, "status": "active"},
            {"seat": 2, "is_hero": False, "stack": 200.0, "archetype": None, "hud": None,
             "cards": None, "status": "active"},
            {"seat": 3, "is_hero": False, "stack": 200.0, "archetype": None, "hud": None,
             "cards": None, "status": "active"},
        ],
        "streets": {
            "preflop": {"actions": [
                {"seat": 1, "action": "post", "amount": 0.5},
                {"seat": 2, "action": "post", "amount": 1.0},
                {"seat": 3, "action": "call", "amount": 1.0},  # one limper
            ]},
            "flop": None, "turn": None, "river": None,
        },
        "to_act": 0, "hero_seat": 0,
    }
    plain = brief.compute(raw)
    vs_station = brief.compute(raw, villain_archetype="calling_station")
    assert plain["sizing"]["raise_to_bb"] == pytest.approx(4.0)   # 3 + 1*1
    assert vs_station["sizing"]["raise_to_bb"] == pytest.approx(5.0)  # 3 + 1*1 + 1 (bump)


def test_brief_does_not_attach_opening_sizing_when_defending_vs_an_existing_raise():
    # Regression (PR #6 review): `verdict_if_in_range` defaults to
    # "raise_or_call" for vs_rfi/squeeze/vs_3bet/vs_4bet just as much as for
    # a plain RFI/isolation -- there "raise" means "re-raise the villain",
    # not "open to 3bb + 1bb/limper". Attaching preflop_open_to() here would
    # hand the coach a number unrelated to the real pot (and, facing a
    # 4bet, one that isn't even a legal raise). No `sizing` key at all is
    # the correct output until a real vs-raise sizing formula exists.
    raw = {
        "schema_version": "2.0",
        "table": {"big_blind": 1.0, "ante": 0.0, "button_seat": 0},
        "seats": [
            {"seat": 0, "is_hero": False, "stack": 200.0, "archetype": None, "hud": None,
             "cards": None, "status": "active"},
            {"seat": 1, "is_hero": False, "stack": 200.0, "archetype": None, "hud": None,
             "cards": None, "status": "active"},
            {"seat": 2, "is_hero": True, "stack": 200.0, "archetype": None, "hud": None,
             "cards": ["A♠", "A♥"], "status": "active"},
            {"seat": 3, "is_hero": False, "stack": 200.0, "archetype": None, "hud": None,
             "cards": None, "status": "active"},
        ],
        "streets": {
            "preflop": {"actions": [
                {"seat": 1, "action": "post", "amount": 0.5},
                {"seat": 2, "action": "post", "amount": 1.0},
                {"seat": 3, "action": "raise", "amount": 2.5},  # a plain open, not a limp
            ]},
            "flop": None, "turn": None, "river": None,
        },
        "to_act": 2, "hero_seat": 2,
    }
    out = brief.compute(raw)
    assert out["gate"] == "G1"
    assert out["range"]["scenario"] == "vs_rfi"
    assert out["verdict"] == "raise_or_call"
    assert "sizing" not in out


def test_brief_facing_a_raise_and_a_caller_squeezes_not_just_defends_vs_rfi():
    # A raise followed by a call before hero acts is a squeeze opportunity,
    # not a simple heads-up defend against the opener -- pot_type() still
    # reports "srp" (only one raise so far), so this must be distinguished
    # from test_brief_defends_vs_rfi_no_longer_falls_through_to_g5 above by
    # actually checking for a call after the raise.
    raw = _defend_hand(["A♠", "K♠"], [], n_seats=4)
    raw["streets"]["preflop"]["actions"] = [
        {"seat": 1, "action": "post", "amount": 0.5},
        {"seat": 2, "action": "post", "amount": 1.0},
        {"seat": 3, "action": "raise", "amount": 3.0},
        {"seat": 0, "action": "call", "amount": 3.0},
    ]
    out = brief.compute(raw)
    assert out["gate"] == "G1"
    assert out["range"]["scenario"] == "squeeze"


def test_brief_defends_vs_3bet():
    # Hero (seat 2) opens, villain 3bets -- hero now faces vs_3bet.
    raw = _defend_hand(["A♠", "A♥"], [], n_seats=3)
    raw["streets"]["preflop"]["actions"] = [
        {"seat": 0, "action": "post", "amount": 0.5},
        {"seat": 1, "action": "post", "amount": 1.0},
        {"seat": 2, "action": "raise", "amount": 3.0},   # hero (seat2) opens
        {"seat": 0, "action": "raise", "amount": 9.0},   # villain 3bets
    ]
    out = brief.compute(raw)
    assert out["gate"] == "G1"
    assert out["range"]["scenario"] == "vs_3bet"


def test_brief_defends_vs_4bet():
    # Hero (seat 2) 3bets, villain 4bets -- hero now faces vs_4bet.
    raw = _defend_hand(["A♠", "A♥"], [], n_seats=3)
    raw["streets"]["preflop"]["actions"] = [
        {"seat": 0, "action": "post", "amount": 0.5},
        {"seat": 1, "action": "post", "amount": 1.0},
        {"seat": 0, "action": "raise", "amount": 3.0},
        {"seat": 1, "action": "raise", "amount": 9.0},
        {"seat": 2, "action": "raise", "amount": 21.0},  # hero (seat2) 3bets
        {"seat": 0, "action": "raise", "amount": 45.0},  # villain 4bets
    ]
    out = brief.compute(raw)
    assert out["gate"] == "G1"
    assert out["range"]["scenario"] == "vs_4bet"


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


def test_brief_g3_bounds_are_not_degenerate_after_heavy_multi_street_pressure():
    # Regression: narrow.narrow()'s binary keep/drop filter made villain
    # ranges collapse to "100% value hands, 0% bluffs" once accumulated
    # pressure exhausted every weak class's ATT budget -- a 3-barrel river
    # spot narrowed both wide and narrow seeds down to sets/two-pair only,
    # giving G3 equity bounds of EXACTLY [0.0, 0.0] (an artefact, not a
    # measurement: every remaining combo trivially beats hero). The
    # bluff-retention floor (MIN_BLUFF_FLOOR_WEIGHT) keeps a residual
    # non-value presence in the range so the bounds stay informative.
    raw = {
        "schema_version": "2.0",
        "table": {"big_blind": 1.0, "ante": 0.0, "button_seat": 0},
        "seats": [
            {"seat": 0, "is_hero": False, "stack": 500.0, "archetype": "tag", "hud": None,
             "cards": None, "status": "active"},
            {"seat": 1, "is_hero": True, "stack": 500.0, "archetype": None, "hud": None,
             "cards": ["A♥", "Q♦"], "status": "active"},
        ],
        "streets": {
            "preflop": {"actions": [
                {"seat": 1, "action": "post", "amount": 0.5},
                {"seat": 0, "action": "post", "amount": 1.0},
                {"seat": 1, "action": "raise", "amount": 3.0},
                {"seat": 0, "action": "call", "amount": 3.0},
            ]},
            "flop": {"board": ["A♣", "7♦", "2♠"], "actions": [
                {"seat": 0, "action": "bet", "amount": 6.0},
                {"seat": 1, "action": "call", "amount": 6.0},
            ]},
            "turn": {"board": ["A♣", "7♦", "2♠", "9♥"], "actions": [
                {"seat": 0, "action": "bet", "amount": 40.0},
                {"seat": 1, "action": "call", "amount": 40.0},
            ]},
            "river": {"board": ["A♣", "7♦", "2♠", "9♥", "4♣"], "actions": [
                {"seat": 0, "action": "bet", "amount": 150.0},
            ]},
        },
        "to_act": 1, "hero_seat": 1,
    }
    out = brief.compute(raw, force_full=True)
    assert out["state"]["street"] == "river"
    eq = out["equity"]
    assert (eq["lower_bound"], eq["upper_bound"]) != (0.0, 0.0)
    assert eq["upper_bound"] > eq["lower_bound"] >= 0.0


def test_brief_bb_defense_multiway_declined_never_folds_strong_without_computing_equity():
    # Regression (bug report): BB with J8o closing the action at 7.7:1 in a
    # 5-way pot (UTG LAG opens, three Fish call, hero BB last to speak).
    # bb_defense_multiway()'s range (top 10%) never contains J8o, but that's
    # a formula's cutoff, not a fold verdict -- it used to fall straight
    # through G1 as "fold"/"strong" without ever comparing equity to pot
    # odds. Exact repro fixture attached to the bug report -- the expected
    # result is not necessarily "call", but it must never be "fold" with
    # confidence "strong" on an unevaluated decision.
    #
    # Also the repro fixture for a SEPARATE bug (live-session report #2):
    # hero here CLOSES the action (players_to_act_behind == 0, cf.
    # state.py) -- she isn't squeezing, she's defending. The scenario used
    # to be mislabeled "squeeze" (a genuinely different, more polarized
    # range) purely because a call followed the last raise, regardless of
    # whether hero had anyone left to act behind her.
    raw = load_fixture("squeeze_bb_j8o_repro.json")
    out = brief.compute(raw, villain_archetype="fish")
    assert out["state"]["hero_closes_action"] is True
    assert out["range"]["scenario"] == "bb_defense_multiway"
    assert not (out["verdict"] == "fold" and out["confidence"] == "strong")
    # The call was never even considered before this fix -- now it must be,
    # whichever gate ends up deciding (G1B outright, or G5 if the computed
    # bounds straddle the uncertainty band around the threshold).
    assert out["gate"] in ("G1B", "G5")
    assert "equity" in out
    assert out["equity"]["threshold"] == pytest.approx(out["state"]["pot_odds"])


def test_brief_bb_defense_multiway_in_range_still_decides_directly():
    # The in-range side must keep deciding directly at G1 (not deferred) --
    # only the out-of-range side needs the equity carve-out above.
    raw = load_fixture("squeeze_bb_j8o_repro.json")
    raw = dict(raw)
    raw["seats"] = [dict(s) for s in raw["seats"]]
    raw["seats"][0]["cards"] = ["A♠", "A♥"]  # comfortably inside the defense range
    out = brief.compute(raw)
    assert out["gate"] == "G1"
    assert out["range"]["scenario"] == "bb_defense_multiway"
    assert out["verdict"] == "raise_or_call"


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
