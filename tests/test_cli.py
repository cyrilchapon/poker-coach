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
    for cmd in ["state", "hand", "texture", "line", "budget", "equity", "narrow",
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


def test_cli_apply_call_computes_amount(capsys, tmp_path):
    p = tmp_path / "h.json"
    p.write_text(Path(HAND).read_text())
    code, out, err = run(["apply", "--hand", str(p), "--action", "c"], capsys)
    assert code == 0, err
    saved = json.loads(p.read_text())
    last_action = saved["streets"]["flop"]["actions"][-1]
    assert last_action == {"seat": 0, "action": "call", "amount": 4.0}


def test_cli_glossary_unknown_term_errors(capsys):
    code, out, err = run(["glossary", "not-a-real-term"], capsys)
    assert code == 1
    assert "inconnu" in err


def test_cli_showdown(capsys):
    code, out, _ = run(["showdown", "--board", "Qc,9s,6d,Qd,Ks",
                         "--hand", "Hero:Ac,6h", "--hand", "HJ:Kd,Td"], capsys)
    assert code == 0
    results = json.loads(out)["results"]
    assert results[0]["result"] == "win"
