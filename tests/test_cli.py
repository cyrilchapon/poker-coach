import json
from pathlib import Path

import pytest

from pokercoach.cli import main
from pokercoach.render import BB_UNIT

FIXTURES = Path(__file__).parent / "fixtures"
HAND = str(FIXTURES / "hu_flop_cbet.json")


def run(argv, capsys):
    code = main(argv)
    out = capsys.readouterr()
    return code, out.out, out.err


def test_cli_help_never_crashes_for_any_subcommand(capsys):
    # Regression guard: argparse treats "%" in help strings as old-style
    # format specifiers — an unescaped "%pot" crashes --help at parse time.
    for cmd in ["state", "hand", "texture", "line", "budget", "equity", "narrow", "ranges",
                "brief", "render", "showdown", "sizing", "glossary", "apply", "assert-state"]:
        with pytest.raises(SystemExit) as exc:
            main([cmd, "--help"])
        assert exc.value.code == 0


def test_cli_state(capsys):
    code, out, err = run(["state", "--hand", HAND], capsys)
    assert code == 0
    parsed = json.loads(out)
    assert parsed["street"] == "flop"
    # Regression: `board` was missing from DerivedState.to_json() -- pc
    # state/pc brief exposed `street` but not what's actually on it, so a
    # coach that had drifted onto a stale street had nothing structured to
    # catch the mismatch against.
    assert parsed["board"] == ["T♠", "9♥", "2♣"]


def test_cli_assert_state_passes_when_it_matches(capsys):
    code, out, err = run(["assert-state", "--hand", HAND, "--street", "flop",
                           "--board", "T♠,9♥,2♣"], capsys)
    assert code == 0, err
    assert json.loads(out)["ok"] is True


def test_cli_assert_state_fails_loudly_on_a_stale_street(capsys):
    # This is the exact failure mode the report describes: the coach narrated
    # a turn/river while hand.json was still on the flop. assert-state must
    # catch that with a non-zero exit rather than let it pass silently.
    code, out, err = run(["assert-state", "--hand", HAND, "--street", "turn"], capsys)
    assert code == 1
    assert "flop" in err and "turn" in err


def test_cli_assert_state_fails_on_a_mismatched_board(capsys):
    code, out, err = run(["assert-state", "--hand", HAND, "--board", "A♠,K♠,Q♠"], capsys)
    assert code == 1
    assert "board" in err


def test_cli_hand_and_texture(capsys):
    code, out, _ = run(["hand", "--hand", HAND], capsys)
    assert code == 0
    assert "made" in json.loads(out)
    code, out, _ = run(["texture", "--hand", HAND], capsys)
    assert code == 0
    assert "wetness" in json.loads(out)


def test_cli_brief(capsys):
    code, out, _ = run(["brief", "--hand", HAND], capsys)
    assert code == 0
    assert json.loads(out)["gate"] in ("G0", "G1", "G2", "G3", "G4", "G5")


def test_cli_narrow_two_pair_path_does_not_crash(capsys, tmp_path):
    # Board that forces the two_pair budget lookup branch (regression guard
    # for the priority_matrix indexing bug).
    hand = json.loads(Path(HAND).read_text())
    hand["streets"]["flop"]["board"] = ["9♦", "4♣", "2♥"]
    p = tmp_path / "tp.json"
    p.write_text(json.dumps(hand))
    code, out, err = run(["narrow", "--hand", str(p), "--action", "call",
                           "--range", "94o,42o,QQ+"], capsys)
    assert code == 0, err
    assert json.loads(out)["original_combos"] > 0


def test_cli_narrow_accepts_calling_station_villain_archetype(capsys):
    # Regression: --villain-archetype had no `choices=` on `pc narrow` at
    # all (unlike `pc budget`/`pc brief`), so nothing validated it and
    # "calling_station" specifically wasn't documented as accepted there.
    code, out, err = run(
        ["narrow", "--hand", HAND, "--action", "call", "--villain-archetype", "calling_station"],
        capsys)
    assert code == 0, err


def test_cli_ranges_rfi_lookup(capsys):
    code, out, err = run(["ranges", "--hand", HAND, "--scenario", "rfi"], capsys)
    assert code == 0, err
    result = json.loads(out)
    assert result["scenario"] == "rfi"
    assert result["confidence"] in ("high", "n/a")


def test_cli_ranges_vs_rfi_requires_an_opener_when_none_is_detectable(capsys, tmp_path):
    # No preflop raise by anyone -- no aggressor to isolate as --opener-seat
    # automatically for a defend scenario, must be told explicitly.
    hand = json.loads(Path(HAND).read_text())
    hand["streets"] = {"preflop": {"actions": [
        {"seat": 0, "action": "post", "amount": 0.5},
        {"seat": 1, "action": "post", "amount": 1.0},
    ]}, "flop": None, "turn": None, "river": None}
    hand["to_act"] = 0
    p = tmp_path / "h.json"
    p.write_text(json.dumps(hand))
    code, out, err = run(["ranges", "--hand", str(p), "--scenario", "vs_rfi"], capsys)
    assert code == 1
    assert "opener" in err


def test_cli_ranges_vs_rfi_with_explicit_opener_seat(capsys, tmp_path):
    hand = json.loads(Path(HAND).read_text())
    hand["streets"] = {"preflop": {"actions": [
        {"seat": 0, "action": "post", "amount": 0.5},
        {"seat": 1, "action": "post", "amount": 1.0},
        {"seat": 0, "action": "raise", "amount": 3.0},
    ]}, "flop": None, "turn": None, "river": None}
    hand["to_act"] = 1
    p = tmp_path / "h.json"
    p.write_text(json.dumps(hand))
    code, out, err = run(["ranges", "--hand", str(p), "--scenario", "vs_rfi", "--opener-seat", "0"], capsys)
    assert code == 0, err
    result = json.loads(out)
    assert result["scenario"] == "vs_rfi"
    assert result["confidence"] == "extrapolated"


def test_cli_narrow_uses_the_villains_pressure_not_the_heros(capsys):
    # Regression: pressure_spent/pressure_faced passed to narrow() was
    # always to_act's (the hero, in this fixture) -- not the villain whose
    # range is actually being narrowed. hu_flop_cbet.json gives hero (seat
    # 0) and villain (seat 1) genuinely different accumulated pressure
    # (hero's preflop raise vs. villain's flop bet), so using the wrong
    # seat measurably changes the retained range.
    code_hero, out_hero, err = run(
        ["narrow", "--hand", HAND, "--action", "call", "--seat", "0"], capsys)
    assert code_hero == 0, err
    code_villain, out_villain, err = run(
        ["narrow", "--hand", HAND, "--action", "call", "--seat", "1"], capsys)
    assert code_villain == 0, err
    assert json.loads(out_hero) != json.loads(out_villain)

    # Default (no --seat) must resolve to the villain (seat 1, the flop
    # bettor and hero's only opponent in this HU spot) -- not to_act/hero.
    code_default, out_default, err = run(
        ["narrow", "--hand", HAND, "--action", "call"], capsys)
    assert code_default == 0, err
    assert json.loads(out_default) == json.loads(out_villain)


def test_cli_budget_refuses_when_it_is_not_the_heros_turn(capsys, tmp_path):
    # Regression: cmd_budget read to_act's cards but cmd_hand defaults to
    # hero_seat -- an inconsistency that only matters, but matters a lot,
    # when to_act != hero_seat (budget would then either crash on missing
    # cards or silently evaluate the wrong seat's pressure).
    hand = json.loads(Path(HAND).read_text())
    hand["to_act"] = 1  # villain's seat, not hero's
    p = tmp_path / "h.json"
    p.write_text(json.dumps(hand))
    code, out, err = run(["budget", "--hand", str(p)], capsys)
    assert code == 1
    assert "héros" in err or "hero" in err


def test_cli_apply_call_computes_amount(capsys, tmp_path):
    p = tmp_path / "h.json"
    p.write_text(Path(HAND).read_text())
    code, out, err = run(["apply", "--hand", str(p), "--action", "c"], capsys)
    assert code == 0, err
    saved = json.loads(p.read_text())
    last_action = saved["streets"]["flop"]["actions"][-1]
    assert last_action == {"seat": 0, "action": "call", "amount": 4.0}


def test_cli_apply_echoes_the_seat_and_position_it_applied_to(capsys, tmp_path):
    # Regression (live-session narration bug): cmd_apply returned only the
    # RESULTING state, whose to_act/to_act_position name whoever speaks NEXT
    # -- nothing in the output identified who just acted. A coach narrating
    # villain actions therefore had no way to check its own ordering after
    # the fact, and narrated a sequence that differed from the one actually
    # applied to the engine.
    p = tmp_path / "h.json"
    p.write_text(Path(HAND).read_text())
    code, out, err = run(["apply", "--hand", str(p), "--action", "c"], capsys)
    assert code == 0, err
    parsed = json.loads(out)
    assert parsed["applied_to"] == {"seat": 0, "position": "BTN/SB",
                                     "action": "call", "amount": 4.0}
    # ...and it is NOT the seat now to act: that distinction is the whole point.
    assert parsed["to_act"] != parsed["applied_to"]["seat"]


def test_cli_apply_echo_matches_the_action_actually_written_to_hand_json(capsys, tmp_path):
    # The echo must be derived from the same write, not recomputed loosely:
    # a shorthand code ("a") and an engine-computed amount must come back
    # exactly as they were appended to streets[].actions.
    p = tmp_path / "h.json"
    p.write_text(Path(HAND).read_text())
    code, out, err = run(["apply", "--hand", str(p), "--action", "a"], capsys)
    assert code == 0, err
    echoed = json.loads(out)["applied_to"]
    written = json.loads(p.read_text())["streets"]["flop"]["actions"][-1]
    assert echoed["seat"] == written["seat"]
    assert echoed["action"] == written["action"] == "allin"
    assert echoed["amount"] == written["amount"]


def test_cli_apply_reports_no_applied_to_when_it_rejects_the_action(capsys, tmp_path):
    # Nothing was applied, so nothing must be echoed -- an `applied_to` on a
    # rejected call would be exactly the false confirmation this field exists
    # to prevent.
    p = tmp_path / "h.json"
    original = Path(HAND).read_text()
    p.write_text(original)
    code, out, err = run(["apply", "--hand", str(p), "--action", "x"], capsys)
    assert code == 1
    assert "applied_to" not in out
    assert p.read_text() == original


def test_cli_apply_rejects_check_when_facing_a_bet(capsys, tmp_path):
    # Regression: "x" (check) used to be accepted unconditionally even
    # facing seat1's flop bet (4.0), silently corrupting hand.json.
    p = tmp_path / "h.json"
    original = Path(HAND).read_text()
    p.write_text(original)
    code, out, err = run(["apply", "--hand", str(p), "--action", "x"], capsys)
    assert code == 1
    assert "illégal" in err
    assert p.read_text() == original  # file untouched on rejection


def test_cli_apply_rejects_a_raise_below_the_amount_to_call(capsys, tmp_path):
    # Regression: no amount control at all -- a raise to 2 while facing a
    # much bigger bet used to be accepted outright.
    hand = json.loads(Path(HAND).read_text())
    hand["streets"]["flop"]["actions"][0]["amount"] = 20.0  # villain bets 20 instead of 4
    p = tmp_path / "h.json"
    original = json.dumps(hand)
    p.write_text(original)
    code, out, err = run(["apply", "--hand", str(p), "--action", "r 2"], capsys)
    assert code == 1
    assert "minimum" in err
    assert p.read_text() == original


def test_cli_apply_allin_sets_seat_status_to_allin(capsys, tmp_path):
    # Regression: only "fold" updated seats[n].status -- an "allin" action
    # left the seat "active" with a 0 remaining stack, so to_act could fall
    # back on it as if it could still act.
    p = tmp_path / "h.json"
    p.write_text(Path(HAND).read_text())
    code, out, err = run(["apply", "--hand", str(p), "--action", "a"], capsys)
    assert code == 0, err
    saved = json.loads(p.read_text())
    assert saved["seats"][0]["status"] == "allin"
    last_action = saved["streets"]["flop"]["actions"][-1]
    assert last_action == {"seat": 0, "action": "allin", "amount": 97.0}  # 100 - 3 (preflop raise)


def test_cli_apply_rejects_amount_mismatch_for_deterministic_actions(capsys, tmp_path):
    # "call" has exactly one legal amount -- a mismatched explicit override
    # must be rejected, not silently accepted as a different bet size.
    p = tmp_path / "h.json"
    original = Path(HAND).read_text()
    p.write_text(original)
    code, out, err = run(["apply", "--hand", str(p), "--action", "c 999"], capsys)
    assert code == 1
    assert "incohérent" in err
    assert p.read_text() == original


def test_cli_render_shows_remaining_stack_not_the_stale_starting_stack(capsys):
    # Regression: seat_dict() showed the raw `seat.stack` field, which
    # pc apply/advance_street.py never debit mid-hand (only new_hand.py
    # reconciles it, at the end of a hand) -- render showed a stale
    # 100.0bb for both seats after a 46bb pot was contested, while
    # pc state's effective_stack (correctly derived from remaining_stack)
    # disagreed. Both must now derive the same number.
    hand = json.loads(Path(HAND).read_text())
    hand["streets"]["flop"]["actions"].append({"seat": 0, "action": "call", "amount": 4.0})
    p = FIXTURES / "_render_stack_check.json"
    p.write_text(json.dumps(hand))
    try:
        code, out, err = run(["render", "--hand", str(p)], capsys)
        assert code == 0, err
        ascii_art = json.loads(out)["ascii"]
        # "amount" is the TOTAL invested on the street, not an increment
        # (state.py's own convention) -- both seats end this flop having
        # put in 3.0 (preflop, already the total after their raise/call)
        # + 4.0 (flop) = 7.0, so 100 - 7.0 = 93.0 each. Was stuck at the
        # stale starting stack (100.0) before the fix. render() drops the
        # superfluous ".0" on whole amounts (cf. render.py docstring), so
        # the rendered stack reads "93𝄫", not "93.0𝄫".
        assert ascii_art.count("93" + BB_UNIT) == 2
        assert "100" + BB_UNIT not in ascii_art
    finally:
        p.unlink()


def test_cli_render_includes_a_structured_state_header(capsys):
    # Regression (live-session guardrail): render() only ever returned
    # {"ascii": ...} -- a hand-written table narrated instead of a real
    # pc render call, or a pc render on a drifted hand.json, had nothing
    # structured to diff against. The same derive().to_json() pc state/pc
    # brief already use is now attached alongside the ascii art.
    code, out, err = run(["render", "--hand", HAND], capsys)
    assert code == 0, err
    parsed = json.loads(out)
    assert parsed["state"]["street"] == "flop"
    assert parsed["state"]["board"] == ["T♠", "9♥", "2♣"]


def test_cli_render_seat_status_and_folded_seat_stays_visible_on_next_street(capsys):
    # Regression: cmd_render's seat_dict() dropped seat.status entirely, and
    # a folded seat's "action" only comes from the CURRENT street's actions
    # -- once play moves to the next street, a seat that folded earlier has
    # no action to show there and became indistinguishable from a seat that
    # simply hasn't acted yet. render() now falls back to "fold" from
    # status when a seat has no action on the street being drawn.
    hand = str(FIXTURES / "three_way_fold_then_turn.json")
    code, out, err = run(["render", "--hand", hand], capsys)
    assert code == 0, err
    ascii_art = json.loads(out)["ascii"]
    assert "fold" in ascii_art


def test_cli_render_places_seats_clockwise_from_hero_and_drops_busted_seats(capsys):
    # Regression trouvée en review de PR (#8) : cmd_render ne passait jamais
    # `acting_order` à render() -- celui-ci retombait sur l'ordre d'insertion
    # de `seats_out`, construit en itérant les sièges PHYSIQUES 0..n-1 (Héros
    # exclu), pas la rotation clockwise-depuis-la-gauche-du-Héros que
    # render() exige. Les données de chaque siège restaient justes (chaque
    # label gardait son propre stack/action), mais leur PLACEMENT autour de
    # la table était faux dès que le Héros n'était pas le dernier siège
    # physique -- un désaccord invisible avec les fixtures existantes, où le
    # Héros est presque toujours en dernière position.
    #
    # Bouton = siège 0, Héros = siège 2 (BB, PAS le dernier siège physique).
    # Un siège busté (status "out") est aussi présent : il ne doit plus
    # apparaître à la table du tout, pas seulement être bien placé.
    hand = str(FIXTURES / "six_max_hero_not_last_with_bust.json")
    code, out, err = run(["render", "--hand", hand], capsys)
    assert code == 0, err
    ascii_art = json.loads(out)["ascii"]
    assert ascii_art == "\n".join([
        "             ── preflop ──              ",
        "",
        "          ╭──────────────────╮",
        "          │                  │",
        "          │                  │",
        "  CO(mnc) │                  │ BTN(tag)",
        "     100𝄫 │                  │ 100𝄫",
        "          │                  │",
        "          │  -- -- -- -- --  │",
        "          │    pot · 1.5𝄫    │",
        "          │                  │",
        " UTG(nit) │                sb│ SB(lag)",
        "     100𝄫 │              0.5𝄫│ 99.5𝄫",
        "          │     bb · 1𝄫      │",
        "          ╰──────────────────╯",
        "                BB · 99𝄫                ",
        "                 A♠ K♦                  ",
    ])
    # Le siège busté (HJ, archétype "fish") n'est plus à la table.
    assert "HJ" not in ascii_art
    assert "fsh" not in ascii_art


def test_cli_sizing_preflop_open_to(capsys):
    code, out, err = run(["sizing", "preflop-open-to", "--limpers", "2",
                           "--villain-archetype", "fish"], capsys)
    assert code == 0, err
    result = json.loads(out)
    assert result["raise_to_bb"] == pytest.approx(6.0)  # 3 + 2 + 1 (fish bump)


def test_cli_glossary_unknown_term_errors(capsys):
    code, out, err = run(["glossary", "not-a-real-term"], capsys)
    assert code == 1
    assert "inconnu" in err


def test_cli_glossary_resolves_aliases_and_new_terms(capsys):
    # Regression: "isolation" ("terme inconnu") when "iso-raise" already
    # covered the concept, and fold_equity/multiway/equity_realization/
    # realisation_equite were entirely missing despite being used
    # constantly in session.
    code, out, err = run(["glossary", "isolation"], capsys)
    assert code == 0, err
    iso = json.loads(out)["definition"]
    code, out, err = run(["glossary", "iso-raise"], capsys)
    assert json.loads(out)["definition"] == iso  # same canonical entry

    for term in ["fold_equity", "multiway", "stab", "calling station",
                 "equity_realization", "realisation_equite"]:
        code, out, err = run(["glossary", term], capsys)
        assert code == 0, f"{term}: {err}"
        assert json.loads(out)["definition"]


def test_cli_glossary_has_implied_and_reverse_implied_odds(capsys):
    # Regression: the glossary covered pot odds but not implied/reverse
    # implied odds, even though decision-factors (loaded by gate G5) uses
    # both terms directly.
    code, out, err = run(["glossary", "implied odds"], capsys)
    assert code == 0, err
    assert "cotes du pot" in json.loads(out)["definition"]

    code, out, err = run(["glossary", "reverse implied odds"], capsys)
    assert code == 0, err
    assert "kicker" in json.loads(out)["definition"]


def test_cli_showdown(capsys):
    code, out, _ = run(["showdown", "--board", "Qc,9s,6d,Qd,Ks",
                         "--hand", "Hero:Ac,6h", "--hand", "HJ:Kd,Td"], capsys)
    assert code == 0
    results = json.loads(out)["results"]
    assert results[0]["result"] == "win"


# --- showdown tied to the canonical state (live-session review #6) ----------

RIVER_HAND = str(FIXTURES / "river_showdown_3way.json")


def _preflop_unclosed(tmp_path) -> str:
    """The exact repro state: preflop, action NOT closed (so advance_street.py
    refuses), hand.json therefore still on preflop with an empty board."""
    raw = json.loads(Path(RIVER_HAND).read_text(encoding="utf-8"))
    raw["streets"]["preflop"]["actions"] = raw["streets"]["preflop"]["actions"][:3]
    raw["streets"]["flop"] = raw["streets"]["turn"] = raw["streets"]["river"] = None
    raw["seats"][2]["status"] = "active"
    raw["to_act"] = 1
    path = tmp_path / "repro.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_showdown_from_hand_refuses_a_board_the_state_never_had(tmp_path, capsys):
    # THE regression (live-session review #6): `pc showdown` never read
    # hand.json at all, so after an advance_street.py that FAILED (non-zero
    # exit, ignored by the caller) it happily resolved a complete, plausible
    # river showdown on a board that existed nowhere in the state -- hand.json
    # was still preflop. --from-hand makes that impossible: a showdown needs a
    # real river.
    hand = _preflop_unclosed(tmp_path)
    code, _, err = run(["showdown", "--from-hand", hand,
                         "--board", "T♠,9♥,2♣,5♦,8♥",
                         "--hand", "Hero:A♠,K♦", "--hand", "SB:Q♣,Q♥"], capsys)
    assert code == 1
    assert "pas à la river" in err and "preflop" in err


def test_showdown_from_hand_resolves_from_the_state(capsys):
    # Happy path: board and hero's cards come from hand.json, only the
    # villain's revealed cards are passed in.
    code, out, err = run(["showdown", "--from-hand", RIVER_HAND, "--hand", "SB:Q♣,Q♥"], capsys)
    assert code == 0, err
    payload = json.loads(out)
    assert payload["source"] == "hand.json"
    assert payload["board"] == ["T♠", "9♥", "2♣", "5♦", "8♥"]
    assert payload["street"] == "river"
    winner = payload["results"][0]
    assert winner["name"] == "SB" and winner["result"] == "win"
    hero = [r for r in payload["results"] if r["is_hero"]]
    assert len(hero) == 1 and hero[0]["seat"] == 0  # hero identified, not just named


def test_showdown_from_hand_rejects_a_board_that_contradicts_the_state(capsys):
    code, _, err = run(["showdown", "--from-hand", RIVER_HAND,
                         "--board", "T♠,9♥,2♣,5♦,7♥", "--hand", "SB:Q♣,Q♥"], capsys)
    assert code == 1
    assert "contredit le board de l'état" in err


def test_showdown_from_hand_rejects_cards_contradicting_hand_json(capsys):
    code, _, err = run(["showdown", "--from-hand", RIVER_HAND,
                         "--hand", "SB:Q♣,Q♥", "--hand", "Hero:2♦,3♦"], capsys)
    assert code == 1
    assert "contredisent celles déjà connues" in err


def test_showdown_from_hand_rejects_a_folded_seat(capsys):
    code, _, err = run(["showdown", "--from-hand", RIVER_HAND,
                         "--hand", "SB:Q♣,Q♥", "--hand", "BB:7♣,7♦"], capsys)
    assert code == 1
    assert "n'est plus en lice" in err


def test_showdown_from_hand_rejects_a_missing_contestant(capsys):
    # Resolving a 2-way showdown with only hero's cards known would silently
    # declare hero the winner -- coherent-looking, and wrong.
    code, _, err = run(["showdown", "--from-hand", RIVER_HAND], capsys)
    assert code == 1
    assert "cartes inconnues pour ['SB']" in err


def test_showdown_from_hand_rejects_a_card_dealt_twice(capsys):
    # validate_and_load already forbids duplicate cards STORED in hand.json,
    # but CLI-supplied cards bypass that -- two players holding the same ace
    # would resolve into an impeccably-computed, materially impossible result.
    code, _, err = run(["showdown", "--from-hand", RIVER_HAND, "--hand", "SB:A♠,Q♥"], capsys)
    assert code == 1
    assert "en double" in err and "siège BTN" in err  # hero already holds A♠

    code, _, err = run(["showdown", "--from-hand", RIVER_HAND, "--hand", "SB:T♠,Q♥"], capsys)
    assert code == 1
    assert "en double" in err and "board" in err


def test_showdown_from_hand_rejects_the_same_seat_twice(capsys):
    # Last-one-wins would silently resolve one of two contradictory hands.
    code, _, err = run(["showdown", "--from-hand", RIVER_HAND,
                         "--hand", "SB:Q♣,Q♥", "--hand", "SB:7♣,7♦"], capsys)
    assert code == 1
    assert "renseigné deux fois" in err


def test_showdown_from_hand_rejects_an_unknown_name(capsys):
    code, _, err = run(["showdown", "--from-hand", RIVER_HAND, "--hand", "Villain:Q♣,Q♥"], capsys)
    assert code == 1
    assert "ne désigne aucun siège" in err


def test_showdown_without_from_hand_still_works_as_a_free_calculator(capsys):
    # The free-floating form stays available for "what beats what" questions
    # outside a hand -- it just no longer masquerades as session tooling.
    code, out, err = run(["showdown", "--board", "Qc,9s,6d,Qd,Ks",
                          "--hand", "Hero:Ac,6h", "--hand", "HJ:Kd,Td"], capsys)
    assert code == 0, err
    assert json.loads(out)["source"] == "arguments"


def test_showdown_requires_a_board_without_from_hand(capsys):
    code, _, err = run(["showdown", "--hand", "Hero:Ac,6h"], capsys)
    assert code == 1
    assert "--board est requis" in err


# --- render tripwire (live-session review #6) -------------------------------

def test_render_expect_street_fails_loudly_on_drift(capsys):
    code, out, err = run(["render", "--hand", HAND, "--expect-street", "river"], capsys)
    assert code == 1
    assert "diverge" in err and "rien n'a été dessiné" in err
    assert out == ""  # no stale table drawn alongside the error


def test_render_expect_street_passes_when_the_state_agrees(capsys):
    code, out, err = run(["render", "--hand", HAND, "--expect-street", "flop"], capsys)
    assert code == 0, err
    assert json.loads(out)["state"]["street"] == "flop"


def test_render_expect_board_fails_loudly_on_drift(capsys):
    code, _, err = run(["render", "--hand", HAND, "--expect-board", "A♠,A♥,A♦"], capsys)
    assert code == 1
    assert "board attendu" in err


# --- runout (all-in callé) -------------------------------------------------

RUNOUT_HAND = str(FIXTURES / "hu_flop_allin_called_runout.json")


def test_cli_apply_writes_to_act_null_when_the_allin_is_called(capsys, tmp_path):
    # Regression : `cmd_apply` n'écrivait `to_act` que si un siège actif
    # restait (`if next_seat is not None`). Le call all-in laissait donc
    # `to_act` sur le siège qui venait de faire tapis -- un état que
    # `validate_and_load` refuse -- et `pc apply` échouait SANS écrire
    # l'action qu'on venait de lui demander d'appliquer.
    hand = json.loads(Path(HAND).read_text())
    hand["streets"]["flop"]["actions"] = [
        {"seat": 1, "action": "bet", "amount": 4.0},
        {"seat": 0, "action": "allin", "amount": 97.0},
    ]
    hand["seats"][0]["status"] = "allin"
    hand["to_act"] = 1
    p = tmp_path / "h.json"
    p.write_text(json.dumps(hand))

    code, out, err = run(["apply", "--hand", str(p), "--action", "a"], capsys)
    assert code == 0, err
    assert json.loads(p.read_text())["to_act"] is None
    parsed = json.loads(out)
    assert parsed["to_act"] is None and parsed["runout"] is True
    assert parsed["applied_to"] == {"seat": 1, "position": "BB",
                                     "action": "allin", "amount": 97.0}


def test_cli_render_and_assert_state_accept_a_runout(capsys):
    code, out, err = run(["render", "--hand", RUNOUT_HAND, "--expect-street", "flop"], capsys)
    assert code == 0, err
    assert json.loads(out)["state"]["runout"] is True

    code, out, err = run(["assert-state", "--hand", RUNOUT_HAND, "--street", "flop"], capsys)
    assert code == 0, err
    parsed = json.loads(out)
    assert parsed["ok"] is True
    # `to_act: null` seul se lit aussi bien "personne ne parle" que "champ
    # absent" -- le booléen dit lequel.
    assert parsed["to_act"] is None and parsed["runout"] is True


def test_cli_apply_brief_and_budget_refuse_a_runout(capsys, tmp_path):
    p = tmp_path / "h.json"
    original = Path(RUNOUT_HAND).read_text()
    p.write_text(original)
    for argv in (["apply", "--hand", str(p), "--action", "x"],
                 ["brief", "--hand", str(p)],
                 ["budget", "--hand", str(p)]):
        code, out, err = run(argv, capsys)
        assert code == 1, argv
        assert "runout" in err, (argv, err)
    assert p.read_text() == original


def test_cli_brief_refuses_a_runout_where_the_hero_is_still_the_active_seat(capsys, tmp_path):
    # Le héros a callé le tapis avec le stack le plus profond : il reste
    # "active" et `to_act` pointe sur lui, mais il n'a plus aucune décision à
    # prendre. Sans la garde runout, `pc brief` déroulait ses gates jusqu'à un
    # verdict sur une décision qui n'existe pas.
    hand = json.loads(Path(RUNOUT_HAND).read_text())
    hand["seats"][0]["stack"] = 200.0
    hand["seats"][0]["status"] = "active"
    hand["streets"]["flop"]["actions"] = [
        {"seat": 1, "action": "bet", "amount": 4.0},
        {"seat": 1, "action": "allin", "amount": 97.0},
        {"seat": 0, "action": "call", "amount": 97.0},
    ]
    hand["to_act"] = 0
    p = tmp_path / "h.json"
    p.write_text(json.dumps(hand))
    code, out, err = run(["brief", "--hand", str(p)], capsys)
    assert code == 1
    assert "runout" in err


def test_cli_showdown_from_hand_resolves_a_runout_at_the_river(capsys, tmp_path):
    # Le bout de chaîne que les deux blocages rendaient inatteignable sans
    # retoucher hand.json à la main.
    hand = json.loads(Path(RUNOUT_HAND).read_text())
    hand["streets"]["turn"] = {"board": ["T♠", "9♥", "2♣", "5♦"], "actions": []}
    hand["streets"]["river"] = {"board": ["T♠", "9♥", "2♣", "5♦", "8♥"], "actions": []}
    p = tmp_path / "h.json"
    p.write_text(json.dumps(hand, ensure_ascii=False))
    code, out, err = run(["showdown", "--from-hand", str(p), "--hand", "BB:K♣,Q♣"], capsys)
    assert code == 0, err
    results = {r["name"]: r["result"] for r in json.loads(out)["results"]}
    assert results == {"BTN/SB": "win", "BB": "lose"}
