"""Prépare la main suivante d'une session : fait tourner le bouton d'un
siège, reconduit stacks/archétypes par SIÈGE PHYSIQUE (jamais par position —
règle dure de l'état canonique, cf. pokercoach.state), poste les blinds, et
remet la main à zéro (cartes/rues vides).

Volontairement HORS du cœur ``pokercoach`` — cf. advance_street.py et le
README, section "Session/multi-hand tooling".

Répartition du pot : ``--winner SEAT`` (un seul gagnant, y compris pot non
disputé) ou ``--split SEAT1,SEAT2,...`` (partage égal, ex égalité au
showdown). Les montants manipulés ici sont des floats sans unité de jeton
minimale imposée par le reste du moteur -- le partage est une division
exacte, pas de reliquat à gérer. Side pots multiway non gérés
(simplification connue) : si plusieurs gagnants n'ont pas misé le même
montant sur la main, répartir à la main et ajuster le stack en éditant le
hand.json produit. ``--winner``/``--split`` ne peuvent désigner qu'un siège
qui était encore en lice (actif ou all-in) à la fin de la main précédente —
un siège foldé ne peut pas être déclaré gagnant.

Bust du Héros = fin de session, jamais de recharge silencieuse (règle
produit v1 préservée) : si le nouveau stack du Héros est <= 0, ce script
REFUSE de produire une main suivante.

Usage :
    python3 new_hand.py --hand hand.json --winner 1
    python3 new_hand.py --hand hand.json --split 0,1 --out hand_next.json
"""
from __future__ import annotations

import argparse
import json
import sys

from pokercoach.state import StateError, preflop_acting_order_offsets, remaining_stack, validate_and_load


def _blind_seats(button_seat: int, n: int) -> tuple[int, int]:
    """(siège SB, siège BB) pour un bouton donné. En heads-up, le bouton
    poste la petite blinde lui-même (BTN/SB)."""
    if n == 2:
        return button_seat, (button_seat + 1) % n
    return (button_seat + 1) % n, (button_seat + 2) % n


def build_next_hand(raw: dict, *, winners: list[int]) -> dict:
    state = validate_and_load(raw)
    n = state.n_seats

    # Seul un siège encore EN LICE (actif ou all-in) à la fin de la main
    # précédente peut être déclaré gagnant -- un siège foldé n'a jamais pu
    # remporter ce pot, quelle que soit sa position dans state.seats.
    eligible_winners = {s.seat for s in state.seats if s.status in ("active", "allin")}
    invalid = [w for w in winners if w not in eligible_winners]
    if invalid:
        raise StateError(
            f"siège(s) gagnant(s) invalide(s) : {invalid} — foldé(s) ou hors de la main, "
            f"seuls {sorted(eligible_winners)} étaient encore en lice"
        )

    pot_total = sum(s.stack - remaining_stack(state, s.seat) for s in state.seats)
    share = pot_total / len(winners)

    new_stacks: dict[int, float] = {}
    for s in state.seats:
        new_stacks[s.seat] = remaining_stack(state, s.seat)
    for w in winners:
        new_stacks[w] += share

    hero_seat = state.hero_seat
    if new_stacks[hero_seat] <= 0:
        raise StateError(
            "le Héros est bust (stack <= 0) — fin de session, ne pas recharger "
            "silencieusement (règle produit préservée de la v1) ; démarrer une "
            "nouvelle session explicitement si l'utilisateur le demande"
        )

    new_button = (state.button_seat + 1) % n
    sb_seat, bb_seat = _blind_seats(new_button, n)
    big_blind = state.big_blind

    new_seats = []
    for s in state.seats:
        status = "active" if new_stacks[s.seat] > 0 else "out"
        new_seats.append({
            "seat": s.seat,
            "is_hero": s.seat == hero_seat,
            "stack": round(new_stacks[s.seat], 4),
            "archetype": s.archetype,
            "hud": s.hud,
            "cards": None,
            "status": status,
        })

    # Limitation connue : ce script ne gère pas le rétrécissement de table
    # (un bust qui fait passer, ex., un 3-handed à un heads-up) — les règles
    # de "dead button"/décalage de blindes qui s'appliquent alors sont hors
    # scope ici. Refuser plutôt que produire une main sans SB postée.
    if new_seats[sb_seat]["status"] != "active" or new_seats[bb_seat]["status"] != "active":
        raise StateError(
            f"le siège SB ({sb_seat}) ou BB ({bb_seat}) attendu pour le nouveau bouton "
            f"n'est plus actif (bust) — la table a rétréci, ajuster button_seat/les "
            f"blindes à la main (règles de dead button non gérées par ce script)"
        )
    # Régression : `table.ante` était reconduit d'une main à l'autre mais
    # jamais réellement posté -- le pot était sous-évalué à chaque main dès
    # qu'une ante était configurée. Chaque siège encore actif la poste (ante
    # "par joueur" classique ; pas de convention "big blind ante" ici).
    # ``amount`` sur une action est le montant TOTAL investi sur la rue par
    # ce siège (cf. state.py) -- pour SB/BB, l'ante se fond donc dans LEUR
    # unique action "post" plutôt que d'en émettre une seconde qui
    # écraserait la première (street_contribution ne prend que la dernière
    # action par siège, elle ne les somme pas).
    ante = round(state.ante, 4) if state.ante > 0 else 0.0
    preflop_actions = [
        {"seat": sb_seat, "action": "post", "amount": round(big_blind / 2 + ante, 4)},
        {"seat": bb_seat, "action": "post", "amount": round(big_blind + ante, 4)},
    ]
    if ante > 0:
        preflop_actions.extend(
            {"seat": s["seat"], "action": "post", "amount": ante}
            for s in new_seats
            if s["status"] == "active" and s["seat"] not in (sb_seat, bb_seat)
        )

    order = preflop_acting_order_offsets(n)
    active_by_offset = {
        (i - new_button) % n: i for i, seat in enumerate(new_seats) if seat["status"] == "active"
    }
    to_act = next((active_by_offset[o] for o in order if o in active_by_offset), None)
    if to_act is None:
        raise StateError("aucun siège actif pour démarrer la main suivante")

    return {
        "schema_version": raw.get("schema_version", "2.0"),
        "session_id": raw.get("session_id"),
        "hand_id": raw.get("hand_id", 0) + 1,
        "table": {"big_blind": big_blind, "ante": state.ante, "button_seat": new_button},
        "seats": new_seats,
        "streets": {"preflop": {"actions": preflop_actions}, "flop": None, "turn": None, "river": None},
        "to_act": to_act,
        "hero_seat": hero_seat,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--hand", required=True)
    p.add_argument("--out", default=None, help="défaut : réécrit --hand en place")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--winner", type=int, help="siège du seul gagnant du pot")
    g.add_argument("--split", help="sièges séparés par des virgules, partage égal")
    args = p.parse_args()

    with open(args.hand, encoding="utf-8") as f:
        raw = json.load(f)

    winners = [args.winner] if args.winner is not None else [int(x) for x in args.split.split(",")]

    try:
        next_hand = build_next_hand(raw, winners=winners)
    except StateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    out_path = args.out or args.hand
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(next_hand, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "hand_id": next_hand["hand_id"],
        "button_seat": next_hand["table"]["button_seat"],
        "to_act": next_hand["to_act"],
        "stacks": {s["seat"]: s["stack"] for s in next_hand["seats"]},
        "busted_seats": [s["seat"] for s in next_hand["seats"] if s["status"] == "out"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
