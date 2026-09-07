import json
from pathlib import Path

import pytest

from pokercoach.cli import main

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
                "brief", "render", "showdown", "sizing", "glossary", "apply"]:
        with pytest.raises(SystemExit) as exc:
            main([cmd, "--help"])
        assert exc.value.code == 0


def test_cli_state(capsys):
    code, out, err = run(["state", "--hand", HAND], capsys)
    assert code == 0
    assert json.loads(out)["street"] == "flop"


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


def test_cli_glossary_unknown_term_errors(capsys):
    code, out, err = run(["glossary", "not-a-real-term"], capsys)
    assert code == 1
    assert "inconnu" in err


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
