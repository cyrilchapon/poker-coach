"""Point d'entrée `pc` : dispatch des sous-commandes, JSON strict sur stdout.

Contrat (docs/brief/references/02-architecture-v2.md) :
- stdout : uniquement du JSON, jamais de prose.
- stderr : les erreurs.
- code de retour non nul si l'état est invalide.

Sous-commandes :
    pc state    --hand hand.json                  validation + dérivations
    pc hand     --hand hand.json [--seat N]        classe de main, outs, blockers
    pc texture  --hand hand.json                   labels de texture du board
    pc line     --hand hand.json                   scénario de ligne d'action + pression
    pc budget   --hand hand.json [--villain-archetype X]   ATT/DEF restants
    pc equity   --range1 R1 --vs R2 [--board ...] [--dead ...] [--iterations N]
                (ou --hand hand.json pour utiliser les cartes du héros + le board de la main)
    pc narrow   --hand hand.json --action ACTION [--range R] [--villain-archetype X]
    pc brief    --hand hand.json [--villain-archetype X]    ⭐ tout en un appel
    pc render   --hand hand.json
    pc showdown --board B --hand NAME:C1C2 [--hand NAME:C1C2 ...]
    pc glossary <terme>
    pc apply    --hand hand.json --action "b 5.5"  applique une action, réécrit l'état
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import actionline, brief as brief_mod, budget as budget_mod, glossary, handclass
from . import render as render_mod, showdown as showdown_mod, sizing as sizing_mod, texture as texture_mod
from .cards import Card, CardError, parse_card, parse_cards
from .equity import equity as compute_equity
from .state import StateError, derive, position_labels, validate_and_load


def _load_hand_json(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise StateError(f"fichier introuvable : {path}") from exc
    except json.JSONDecodeError as exc:
        raise StateError(f"JSON invalide dans {path} : {exc}") from exc


def _load_state(path: str):
    return validate_and_load(_load_hand_json(path))


# --- state / hand / texture / line -----------------------------------------

def cmd_state(args: argparse.Namespace) -> dict[str, Any]:
    return derive(_load_state(args.hand)).to_json()


def cmd_hand(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state(args.hand)
    seat = args.seat if args.seat is not None else state.hero_seat
    cards = state.seats[seat].cards
    if cards is None:
        raise StateError(f"seats[{seat}].cards inconnu — impossible de classifier")
    return handclass.classify(cards, state.board).to_json()


def cmd_texture(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state(args.hand)
    return texture_mod.classify(state.board).to_json()


def cmd_line(args: argparse.Namespace) -> dict[str, Any]:
    return actionline.to_json(_load_state(args.hand))


def cmd_budget(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state(args.hand)
    hero_cards = state.seats[state.to_act].cards
    if hero_cards is None or len(state.board) < 3:
        raise StateError("budget nécessite un flop et les cartes du siège au trait")
    hc = handclass.classify(hero_cards, state.board)
    texture = texture_mod.classify(state.board)
    line = actionline.to_json(state)
    replay = actionline.replay_pressure(state)
    d = derive(state)
    b = budget_mod.compute(
        hc, texture, pot_type=line["pot_type"], street=state.street,
        n_opponents_active=max(0, d.players_active - 1),
        pressure_spent=replay.spent.get(state.to_act, 0.0),
        pressure_faced=replay.faced.get(state.to_act, 0.0),
        villain_archetype=args.villain_archetype,
    )
    return b.to_json()


# --- equity / narrow ---------------------------------------------------------

def _parse_card_list(s: str | None) -> list[Card]:
    if not s:
        return []
    return parse_cards([t for t in s.split(",") if t])


def cmd_equity(args: argparse.Namespace) -> dict[str, Any]:
    board = _parse_card_list(args.board)
    dead = _parse_card_list(args.dead)
    range1 = args.range1
    if args.hand:
        state = _load_state(args.hand)
        board = state.board
        hero_cards = state.seats[state.hero_seat].cards
        if range1 is None and hero_cards:
            range1 = f"{hero_cards[0]}{hero_cards[1]}"
    if range1 is None:
        raise StateError("fournir --range1 ou --hand (avec les cartes du héros connues)")
    result = compute_equity(range1, args.vs, board=board, dead=dead, iterations=args.iterations)
    return result.to_json()


def cmd_narrow(args: argparse.Namespace) -> dict[str, Any]:
    from .ranges import narrow as narrow_mod

    state = _load_state(args.hand)
    if len(state.board) < 3:
        raise StateError("narrow nécessite au moins un flop")
    line = actionline.to_json(state)
    replay = actionline.replay_pressure(state)
    d = derive(state)
    range_str = args.range or ",".join([
        "22+", "A2s+", "K2s+", "Q4s+", "J6s+", "T6s+", "96s+", "86s+", "75s+", "64s+", "53s+",
        "A2o+", "K8o+", "Q9o+", "J9o+", "T9o",
    ])
    result = narrow_mod.narrow(
        range_str, state.board, args.action, pot_type=line["pot_type"], street=state.street,
        n_opponents_active=max(0, d.players_active - 1),
        pressure_spent=replay.spent.get(state.to_act, 0.0),
        pressure_faced=replay.faced.get(state.to_act, 0.0),
        villain_archetype=args.villain_archetype,
    )
    return result.to_json()


# --- brief -------------------------------------------------------------------

def cmd_brief(args: argparse.Namespace) -> dict[str, Any]:
    raw = _load_hand_json(args.hand)
    try:
        return brief_mod.compute(raw, villain_archetype=args.villain_archetype)
    except StateError:
        raise
    except ValueError as exc:
        raise StateError(str(exc)) from exc


# --- render / showdown / glossary --------------------------------------------

def cmd_render(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state(args.hand)
    labels = position_labels(state)
    node = state.streets[state.street]

    def seat_dict(seat) -> dict[str, Any]:
        action, amount = "", None
        for act in node["actions"]:
            if act["seat"] == seat.seat:
                action, amount = act["action"], act.get("amount")
        d: dict[str, Any] = {"stack": round(seat.stack, 2), "action": action, "amount": amount}
        if seat.archetype:
            d["archetype"] = seat.archetype
        if seat.cards:
            d["cards"] = [str(c) for c in seat.cards]
        return d

    seats_out = {labels[s.seat]: seat_dict(s) for s in state.seats if s.seat != state.hero_seat}
    hero = state.seats[state.hero_seat]
    ascii_art = render_mod.render(
        seats=seats_out, hero_position=labels[state.hero_seat], hero=seat_dict(hero),
        board=[str(c) for c in state.board], pot=round(derive(state).pot, 2), street=state.street,
    )
    return {"ascii": ascii_art}


def cmd_showdown(args: argparse.Namespace) -> dict[str, Any]:
    board = parse_cards(args.board.split(","))
    hands = []
    for h in args.hand_entry:
        name, cards_str = h.split(":")
        hands.append((name, parse_cards(cards_str.split(","))))
    return {"results": [r.to_json() for r in showdown_mod.resolve(board, hands)]}


def cmd_sizing(args: argparse.Namespace) -> dict[str, Any]:
    if args.sizing_cmd == "bet-pct":
        return {"bet_pct": sizing_mod.bet_pct(args.bet, args.pot_before)}
    return sizing_mod.raise_to(args.pot_before_bet, args.bet_to_call, args.fraction)


def cmd_glossary(args: argparse.Namespace) -> dict[str, Any]:
    definition = glossary.lookup(args.term)
    if definition is None:
        raise StateError(f"terme inconnu du glossaire : {args.term!r}")
    return {"term": args.term, "definition": definition}


# --- apply ---------------------------------------------------------------

_SHORTHAND = {"f": "fold", "x": "check", "c": "call", "b": "bet", "r": "raise", "a": "allin"}


def cmd_apply(args: argparse.Namespace) -> dict[str, Any]:
    from .state import street_contribution, to_call as compute_to_call

    raw = _load_hand_json(args.hand)
    state = validate_and_load(raw)
    parts = args.action.strip().split()
    code = parts[0].lower()
    action = _SHORTHAND.get(code, code)
    already_in = street_contribution(state, state.street, state.to_act)

    if len(parts) > 1:
        amount = float(parts[1])
    elif action == "call":
        amount = already_in + compute_to_call(state)
    elif action == "check":
        amount = already_in
    elif action == "fold":
        amount = already_in  # convention v1 : fold affiche quand même le montant engagé
    elif action == "allin":
        from .state import remaining_stack
        amount = already_in + remaining_stack(state, state.to_act)
    else:
        raise StateError(f'montant requis pour "{action}" : ex "b 5.5", "r 12"')

    node = raw["streets"][state.street]
    node["actions"].append({"seat": state.to_act, "action": action, "amount": amount})

    if action == "fold":
        raw["seats"][state.to_act]["status"] = "folded"
    n = state.n_seats
    order = [(state.to_act + i) % n for i in range(1, n + 1)]
    next_seat = next((s for s in order if raw["seats"][s]["status"] == "active"), None)
    if next_seat is not None:
        raw["to_act"] = next_seat

    with open(args.hand, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)

    return derive(validate_and_load(raw)).to_json()


# --- dispatch ------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pc", description="Moteur déterministe poker-coach v2")
    sub = parser.add_subparsers(dest="command", required=True)

    def hand_arg(p):
        p.add_argument("--hand", required=True, help="chemin vers hand.json")

    p = sub.add_parser("state", help="valide et dérive l'état d'une main")
    hand_arg(p); p.set_defaults(func=cmd_state)

    p = sub.add_parser("hand", help="classe de main, tirage, outs, blockers")
    hand_arg(p)
    p.add_argument("--seat", type=int, default=None)
    p.set_defaults(func=cmd_hand)

    p = sub.add_parser("texture", help="labels de texture du board")
    hand_arg(p); p.set_defaults(func=cmd_texture)

    p = sub.add_parser("line", help="type de pot, rôle, pression pondérée")
    hand_arg(p); p.set_defaults(func=cmd_line)

    p = sub.add_parser("budget", help="ATT/DEF restants + options viables")
    hand_arg(p)
    p.add_argument("--villain-archetype", default=None, choices=["nit", "tag", "lag", "fish", "maniac", "calling_station"])
    p.set_defaults(func=cmd_budget)

    p = sub.add_parser("equity", help="équité range vs range")
    p.add_argument("--hand", default=None, help="hand.json (cartes héros + board), optionnel")
    p.add_argument("--range1", default=None, help="range/main du héros (omis si --hand fournit les cartes)")
    p.add_argument("--vs", required=True, help="range adverse")
    p.add_argument("--board", default=None, help="cartes communes séparées par des virgules")
    p.add_argument("--dead", default=None, help="cartes mortes séparées par des virgules")
    p.add_argument("--iterations", type=int, default=20000)
    p.set_defaults(func=cmd_equity)

    p = sub.add_parser("narrow", help="range adverse après filtrage par action observée")
    hand_arg(p)
    p.add_argument("--action", required=True, choices=["fold", "check", "call", "bet", "raise"])
    p.add_argument("--range", default=None, help="range de départ (défaut : range générique large)")
    p.add_argument("--villain-archetype", default=None)
    p.set_defaults(func=cmd_narrow)

    p = sub.add_parser("brief", help="⭐ tout ce qui précède, en un appel")
    hand_arg(p)
    p.add_argument("--villain-archetype", default=None, choices=["nit", "tag", "lag", "fish", "maniac", "calling_station"])
    p.set_defaults(func=cmd_brief)

    p = sub.add_parser("render", help="dessin ASCII de la table")
    hand_arg(p); p.set_defaults(func=cmd_render)

    p = sub.add_parser("showdown", help="résolution déterministe d'un abattage")
    p.add_argument("--board", required=True)
    p.add_argument("--hand", dest="hand_entry", action="append", required=True,
                    metavar="NOM:CARTES", help="ex --hand Hero:Ac6h --hand HJ:KdTd")
    p.set_defaults(func=cmd_showdown)

    p = sub.add_parser("sizing", help="calcul déterministe de %%pot / montant de relance")
    sizing_sub = p.add_subparsers(dest="sizing_cmd", required=True)
    p1 = sizing_sub.add_parser("bet-pct")
    p1.add_argument("--bet", type=float, required=True)
    p1.add_argument("--pot-before", type=float, required=True)
    p2 = sizing_sub.add_parser("raise-to")
    p2.add_argument("--pot-before-bet", type=float, required=True)
    p2.add_argument("--bet-to-call", type=float, required=True)
    p2.add_argument("--fraction", type=float, required=True)
    p.set_defaults(func=cmd_sizing)

    p = sub.add_parser("glossary", help="une définition de terme GTO")
    p.add_argument("term")
    p.set_defaults(func=cmd_glossary)

    p = sub.add_parser("apply", help="applique une action et réécrit hand.json")
    hand_arg(p)
    p.add_argument("--action", required=True, help='ex "b 5.5", "c", "x", "f", "r 12"')
    p.set_defaults(func=cmd_apply)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
    except (StateError, CardError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
