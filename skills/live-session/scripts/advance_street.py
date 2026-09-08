"""Ouvre la rue suivante d'une main (preflop->flop->turn->river) : ajoute les
cartes distribuées, remet les actions de la nouvelle rue à vide, et pointe
``to_act`` sur le premier siège actif dans l'ordre de parole postflop
(la SB en premier, le bouton en dernier — cf. ``pokercoach.state.
postflop_acting_order_offsets``), ou sur ``None`` en runout (tous les sièges
encore en lice sont all-in : plus aucune décision à prendre, seules les
cartes restent à distribuer — cf. ``pokercoach.state.is_runout``).

Volontairement HORS du cœur ``pokercoach`` : c'est une commodité de session
(live-session, ou toute simulation main par main), pas une brique du moteur
d'analyse générique — cf. README, "Session/multi-hand tooling". Réutilise
``pokercoach`` (installé en package, ou localisé sans installation par
pc_bootstrap.py sur claude.ai — voir ce module) pour la validation/dérivation,
n'y ajoute rien.

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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pc_bootstrap import ensure_pokercoach_on_path  # noqa: E402

ensure_pokercoach_on_path()

from pokercoach.cards import CardError, parse_cards  # noqa: E402
from pokercoach.state import (  # noqa: E402
    BOARD_SIZE, StateError, derive, postflop_acting_order_offsets,
    street_contribution, validate_and_load,
)

NEXT_STREET = {"preflop": "flop", "flop": "turn", "turn": "river"}


def _action_is_closed(state) -> None:
    """Tous les sièges encore ACTIFS (ni fold, ni all-in, ni out) doivent
    avoir égalé la mise la plus haute de la rue courante, ET — dès qu'ils
    sont au moins deux à pouvoir se répondre — avoir tous agi au moins une
    fois sur cette rue (l'égalité seule ne suffit pas : ``[0.0, 0.0]`` est
    trivialement "égale" même quand un seul des deux sièges a effectivement
    parlé). Les sièges all-in sont exclus de cette égalité (un tapis pour
    moins que la mise en cours est légitime — side pots, simplification
    connue ailleurs, pas ici).

    Une rue sans aucune action n'est PAS forcément une rue non close : après
    un all-in callé, il ne reste plus personne à qui la parole puisse
    revenir. C'est le cas normal d'un runout — la rue est close *par
    construction*, et la refuser (« aucune action enregistrée — rien à
    clore ») bloquait le déroulé du board, sans autre issue en session que
    de retoucher ``hand.json`` à la main, exactement ce que les garde-fous
    anti-dérive interdisent. Le critère est donc « reste-t-il une décision à
    prendre ? », pas « la rue a-t-elle des actions ? ».
    """
    node = state.streets[state.street]

    # Un pot n'est contesté (au sens "il reste une décision à prendre ou un
    # showdown à faire") que s'il reste au moins deux sièges non-foldés
    # (actifs OU all-in). Si un seul reste, tous les autres ont foldé -> le
    # pot lui revient déjà, pas de rue suivante à ouvrir.
    contesting_seats = [s.seat for s in state.seats if s.status in ("active", "allin")]
    if len(contesting_seats) <= 1:
        raise StateError(
            f"un seul siège encore en lice sur {state.street} (les autres ont foldé) — "
            "la main est déjà décidée, pas de rue suivante à ouvrir : attribuer le pot "
            "directement plutôt que d'appeler advance_street.py"
        )

    active_seats = [s.seat for s in state.seats if s.status == "active"]

    # Une mise non égalée laisse toujours une décision à prendre (suivre,
    # relancer ou se coucher) — y compris au dernier siège actif face à un
    # tapis adverse. Contrôlé avant tout le reste : c'est le seul cas où un
    # siège seul en lice DOIT encore parler.
    max_committed = max(
        (street_contribution(state, state.street, s) for s in contesting_seats),
        default=0.0,
    )
    unmatched = [s for s in active_seats
                 if street_contribution(state, state.street, s) < max_committed]
    if unmatched:
        raise StateError(
            f"action non close sur {state.street} : siège(s) {unmatched} n'ont pas égalé "
            f"la mise la plus haute ({max_committed:g}) — il manque une décision"
        )

    if len(active_seats) < 2:
        # Runout : plus aucun siège ne peut se voir rendre la parole (tous
        # all-in, ou un seul actif dont la mise est déjà égalée par des
        # tapis). Rien à clore parce que rien ne peut plus s'ouvrir.
        return

    # Un ``post`` (blinde préflop) n'est pas une action volontaire : il ne
    # compte pas comme "avoir agi" au sens de la clôture de rue.
    acted_seats = {a["seat"] for a in node["actions"] if a["action"] != "post"}
    missing = [s for s in active_seats if s not in acted_seats]
    if missing:
        raise StateError(
            f"action non close sur {state.street} : siège(s) {missing} n'ont pas encore agi"
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
    # ``None`` = runout : tous les sièges encore en lice sont all-in, la
    # nouvelle rue n'a aucun siège à qui donner la parole. C'est un état
    # terminal VALIDE (cf. ``state.is_runout``), pas une erreur -- le refuser
    # ici était le second blocage du déroulé d'un all-in callé. Le cas « plus
    # personne en lice du tout » est déjà écarté par ``_action_is_closed``.
    raw["to_act"] = next(
        (active_by_offset[o] for o in order if o in active_by_offset), None
    )

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
        # Revue live-session #6 : le code retour non nul suffit... à condition
        # d'être lu. En session il ne l'a pas été, et les appels suivants
        # (`pc render`, `pc brief`, `pc showdown`) ont continué sur le dernier
        # état valide -- toujours la rue PRÉCÉDENTE -- sans que rien ne le
        # signale, jusqu'à un showdown de river complet et cohérent en
        # apparence sur un board qui n'existait pas. On nomme donc la
        # conséquence ici, au moment exact où le piège se referme, plutôt que
        # de laisser le seul code retour la porter.
        print(f"error: {exc}", file=sys.stderr)
        try:
            unchanged = derive(validate_and_load(raw))
            print(
                f"error: hand.json est INCHANGÉ — toujours sur {unchanged.street!r} "
                f"(board {[str(c) for c in unchanged.board]}). Ne pas narrer la rue suivante : "
                "tout pc render/brief/showdown appelé maintenant décrira CETTE rue-là. "
                "Corriger la cause ci-dessus, relancer, et ne continuer qu'au code retour 0.",
                file=sys.stderr,
            )
        except StateError:
            pass  # état déjà invalide en entrée : le message principal suffit
        return 1

    out_path = args.out or args.hand
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)

    print(json.dumps(derive(validate_and_load(updated)).to_json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
