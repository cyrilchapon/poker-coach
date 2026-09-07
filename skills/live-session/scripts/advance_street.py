"""Ouvre la rue suivante d'une main (preflop->flop->turn->river) : ajoute les
cartes distribuées, remet les actions de la nouvelle rue à vide, et pointe
``to_act`` sur le premier siège actif dans l'ordre de parole postflop
(la SB en premier, le bouton en dernier — cf. ``pokercoach.state.
postflop_acting_order_offsets``).

Volontairement HORS du cœur ``pokercoach`` : c'est une commodité de session
(live-session, ou toute simulation main par main), pas une brique du moteur
d'analyse générique — cf. README, "Session/multi-hand tooling". Réutilise
``pokercoach`` (installé en package) pour la validation/dérivation, n'y
ajoute rien.

Usage :
    python3 advance_street.py --hand hand.json --deal "T♠,9♥,2♣"   # preflop -> flop
    python3 advance_street.py --hand hand.json --deal "5♦"          # flop -> turn
    python3 advance_street.py --hand hand.json --deal "8♥"          # turn -> river

Réécrit ``--hand`` en place (ou ``--out`` si fourni). Erreur (code retour
non nul, message sur stderr) si l'action de la rue courante n'est pas close,
si le nombre de cartes ne correspond pas, ou si on est déjà à la river.
"""
from __future__ import annotations

import argparse
import json
import sys

from pokercoach.cards import CardError, parse_cards
from pokercoach.state import (
    BOARD_SIZE, StateError, derive, postflop_acting_order_offsets,
    street_contribution, validate_and_load,
)

NEXT_STREET = {"preflop": "flop", "flop": "turn", "turn": "river"}


def _action_is_closed(state) -> None:
    """Tous les sièges encore ACTIFS (ni fold, ni all-in, ni out) doivent
    avoir égalé la mise la plus haute de la rue courante. Les sièges all-in
    sont exclus de cette égalité (un tapis pour moins que la mise en cours
    est légitime — side pots, simplification connue ailleurs, pas ici)."""
    node = state.streets[state.street]
    if not node["actions"]:
        raise StateError(f"aucune action enregistrée sur {state.street} — rien à clore")
    active_contributions = [
        street_contribution(state, state.street, s.seat)
        for s in state.seats if s.status == "active"
    ]
    if len(set(active_contributions)) > 1:
        raise StateError(
            f"action non close sur {state.street} : contributions inégales "
            f"parmi les sièges actifs ({active_contributions}) — il manque une action"
        )


def advance(raw: dict, deal_str: str) -> dict:
    state = validate_and_load(raw)
    current = state.street
    if current == "river":
        raise StateError(
            "déjà à la river, pas de rue suivante — résoudre par pc showdown "
            "(via skills/live-session/SKILL.md) plutôt qu'avancer encore"
        )
    next_street = NEXT_STREET[current]

    _action_is_closed(state)

    try:
        new_cards = parse_cards([c for c in deal_str.split(",") if c])
    except CardError as exc:
        raise StateError(str(exc)) from exc

    n_new = BOARD_SIZE[next_street] - BOARD_SIZE[current]
    if len(new_cards) != n_new:
        raise StateError(f"{next_street} attend {n_new} carte(s), reçu {len(new_cards)}")

    known = set(state.board)
    for s in state.seats:
        if s.cards:
            known.update(s.cards)
    conflicts = set(new_cards) & known
    if conflicts:
        raise StateError(f"carte(s) déjà connue(s) dans la main : {', '.join(str(c) for c in conflicts)}")

    full_board = state.board + new_cards
    raw["streets"][next_street] = {
        "board": [str(c) for c in full_board],
        "actions": [],
    }

    n = state.n_seats
    order = postflop_acting_order_offsets(n)
    active_by_offset = {
        (s.seat - state.button_seat) % n: s.seat for s in state.seats if s.status == "active"
    }
    next_seat = next((active_by_offset[o] for o in order if o in active_by_offset), None)
    if next_seat is None:
        raise StateError("aucun siège actif ne peut agir sur la nouvelle rue (tous fold/all-in/out)")
    raw["to_act"] = next_seat

    return raw


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--hand", required=True)
    p.add_argument("--out", default=None, help="défaut : réécrit --hand en place")
    p.add_argument("--deal", required=True, help="cartes séparées par des virgules")
    args = p.parse_args()

    with open(args.hand, encoding="utf-8") as f:
        raw = json.load(f)

    try:
        updated = advance(raw, args.deal)
    except StateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    out_path = args.out or args.hand
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)

    print(json.dumps(derive(validate_and_load(updated)).to_json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
