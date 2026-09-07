"""Couche B — grammaire de la ligne d'action : type de pot, rôle, pression pondérée.

Consomme ``data/pressure-weights.yaml`` (table taille-de-mise -> poids,
interpolée linéairement). Rejoue l'historique complet de la main pour
calculer, par siège, la pression déjà "dépensée" (ses propres mises) et
"subie" (les mises adverses auxquelles il a dû répondre) — c'est ce que
``budget.py`` décrémente des budgets ATT/DEF de base.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .state import STREETS, HandState, street_contribution

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

POT_TYPES = ("limp", "srp", "three_bet_pot", "four_bet_pot", "squeeze")
ROLES = ("aggressor", "defender", "probe")


@lru_cache(maxsize=1)
def _pressure_table() -> list[dict[str, float]]:
    with open(DATA_DIR / "pressure-weights.yaml", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    return doc["table"]


def pressure_weight(bet_pct_pot: float) -> float:
    """Poids de pression pour une mise de ``bet_pct_pot`` % du pot, par
    interpolation linéaire de la table (cap au-delà du dernier seuil)."""
    table = _pressure_table()
    if bet_pct_pot <= table[0]["threshold_pct"]:
        return table[0]["weight"] * (bet_pct_pot / table[0]["threshold_pct"]) if table[0]["threshold_pct"] else table[0]["weight"]
    for lo, hi in zip(table, table[1:]):
        if lo["threshold_pct"] <= bet_pct_pot <= hi["threshold_pct"]:
            span = hi["threshold_pct"] - lo["threshold_pct"]
            frac = (bet_pct_pot - lo["threshold_pct"]) / span if span else 0.0
            return lo["weight"] + frac * (hi["weight"] - lo["weight"])
    return table[-1]["weight"]  # cap


def pot_type(state: HandState) -> str:
    preflop = state.streets["preflop"]["actions"]
    # "allin" est une catégorie d'action à part entière (state.ACTIONS), pas
    # un synonyme de "raise" -- mais un shove EST une relance du point de vue
    # du comptage 3bet/4bet, donc il doit compter comme telle ici.
    raises = [i for i, a in enumerate(preflop) if a["action"] in ("raise", "allin")]
    if not raises:
        return "limp" if any(a["action"] == "call" for a in preflop) else "srp"
    if len(raises) == 1:
        return "srp"
    if len(raises) == 2:
        between = preflop[raises[0] + 1: raises[1]]
        return "squeeze" if any(a["action"] == "call" for a in between) else "three_bet_pot"
    return "four_bet_pot"


def is_opening_decision(state: HandState) -> bool:
    """True si personne n'a encore volontairement ouvert le pot (call/raise)
    sur la rue préflop — la BB forcée gonfle ``to_call`` avant toute action
    volontaire, ce qui ne fait de personne un "défenseur" au sens de
    ``role()``. Utilisé aussi par ``brief.py`` pour le lookup RFI."""
    if state.street != "preflop":
        return False
    # "allin" (shove) ouvre le pot tout autant qu'un call/raise classique.
    return not any(a["action"] in ("call", "raise", "allin") for a in state.streets["preflop"]["actions"])


def role(state: HandState, *, seat: int | None = None) -> str:
    seat = state.to_act if seat is None else seat
    from .state import to_call
    if to_call(state, seat=seat) > 0 and not is_opening_decision(state):
        return "defender"
    return "aggressor" if last_aggressor(state) == seat else "probe"


def last_aggressor(state: HandState) -> int | None:
    """Le siège du dernier joueur à avoir misé/relancé, toutes rues
    confondues jusqu'à la rue courante incluse (``None`` si personne n'a
    encore misé). Public : utilisé aussi par ``brief.py`` pour choisir le
    siège adverse le plus pertinent pour les bornes d'équité G3."""
    last = None
    for street in STREETS:
        node = state.streets.get(street)
        if node is None:
            break
        for act in node["actions"]:
            if act["action"] in ("bet", "raise", "allin"):
                last = act["seat"]
    return last


@dataclass
class PressureReplay:
    spent: dict[int, float]     # pression que CE siège a lui-même mise
    faced: dict[int, float]     # pression que CE siège a subie des autres

    def to_json(self) -> dict[str, Any]:
        return {
            "spent": {str(k): round(v, 3) for k, v in self.spent.items()},
            "faced": {str(k): round(v, 3) for k, v in self.faced.items()},
        }


def replay_pressure(state: HandState, *, upto_street: str | None = None) -> PressureReplay:
    """Rejoue toute la main et attribue, à chaque mise/relance, un poids de
    pression au siège qui l'a placée (`spent`) et à tous les autres sièges
    encore en lice sur cette rue à ce moment (`faced`).

    ``upto_street`` : borne le rejeu à cette rue incluse plutôt que jusqu'à
    la rue courante de ``state`` -- utilisé par ``brief._narrow_through_history``
    pour obtenir la pression réellement accumulée par un adversaire à chaque
    étape du narrowing rue-par-rue, plutôt que de repartir d'un budget neuf
    (0.0/0.0) à chaque rue comme avant ce correctif."""
    spent = {s.seat: 0.0 for s in state.seats}
    faced = {s.seat: 0.0 for s in state.seats}

    for street in STREETS:
        node = state.streets.get(street)
        if node is None:
            break
        contributed: dict[int, float] = {s.seat: 0.0 for s in state.seats}
        pot_so_far = sum(street_contribution(state, s, s2.seat) for s in STREETS[:STREETS.index(street)] for s2 in state.seats)
        folded_or_out: set[int] = set()
        still_in = [s.seat for s in state.seats]

        for act in node["actions"]:
            seat = act["seat"]
            if act["action"] == "fold":
                folded_or_out.add(seat)
                continue
            amount = float(act.get("amount", 0.0))
            if act["action"] in ("bet", "raise", "allin"):
                incremental = amount - contributed[seat]
                pot_before = pot_so_far + sum(contributed.values())
                bet_pct = (incremental / pot_before * 100) if pot_before > 0 else 100.0
                w = pressure_weight(bet_pct)
                spent[seat] += w
                for other in still_in:
                    if other != seat and other not in folded_or_out:
                        faced[other] += w
            contributed[seat] = amount

        if street == upto_street:
            break

    return PressureReplay(spent=spent, faced=faced)


def to_json(state: HandState) -> dict[str, Any]:
    replay = replay_pressure(state)
    return {
        "pot_type": pot_type(state),
        "role": role(state),
        "weighted_pressure_faced": round(replay.faced.get(state.to_act, 0.0), 3),
        "hero_pressure_spent": round(replay.spent.get(state.to_act, 0.0), 3),
    }
