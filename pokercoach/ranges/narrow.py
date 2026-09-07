"""Range narrowing mécanique : filtre une range adverse aux combos dont le
budget ATT/DEF rend l'action observée viable, plutôt que de la resserrer "à
l'oeil". C'est le même moteur (handclass + texture + budget) qui juge le
héros, appliqué à chaque combo adverse hypothétique.

Mécanisme de rétention des bluffs (ajouté suite à une revue) : un filtre
purement binaire (combo gardé à 100% si viable, jeté à 0% sinon) fait
converger la range vers "100% mains faites, 0% bluff" dès que la pression
accumulée épuise le budget ATT de toutes les classes faibles/tirages — sur
un spot 3-barrels rivière mesuré, `vs_range_wide`/`vs_range_narrow`
tombaient toutes deux à des mains faites uniquement (sets/two pair), avec
des bornes d'équité G3 dégénérées à exactement [0.0, 0.0] : plus une
mesure d'incertitude, un artefact. Un villain réel n'est pas parfaitement
polarisé à ce point. Les combos dont le budget est épuisé PAR LA PRESSION
(pas par une règle structurelle comme "bluff_dies_multiway" ou
"bluff_multi_street_blocked", qui représentent "cette ligne n'a
structurellement aucun sens" et restent donc à zéro) sont retenus à un
poids plancher plutôt que rejetés entièrement — encodé dans le
``range_str`` de sortie via la notation ``combo@xx%`` déjà supportée par
``equity.parse_range``, pour que ce poids réduit se propage réellement
(et pas seulement "ce combo existe encore dans la liste, à 100%").

``MIN_BLUFF_FLOOR_WEIGHT`` n'est PAS calibré sur des données réelles (cf.
README, section calibration) — un plancher modeste et délibérément rond,
suffisant pour que les bornes G3 restent informatives plutôt qu'un
artefact à équité nulle, pas une fréquence de bluff précise.

Ce qui N'EST PAS corrigé ici (cause distincte, toujours ouverte, cf.
README) : le critère de viabilité lui-même (``action in b.viable_actions``)
reste lâche à budget FRAIS -- une main `trash` a un ATT de base non nul,
donc peu de combos sont exclus au tout début d'une main (avant que la
pression n'ait eu le temps de s'accumuler). C'est une question de
calibration des seuils de base (``data/att-def-budgets.yaml``), pas de
mécanisme -- corriger le mécanisme de rétention ci-dessus ne la résout pas.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..budget import Budget, compute as compute_budget
from ..cards import Card
from ..equity import WeightedCombo, parse_range
from ..handclass import classify
from ..texture import classify as classify_texture

FACING_BET_ACTIONS = ("call", "raise")     # une mise existe déjà, l'adversaire y répond
NOT_FACING_BET_ACTIONS = ("check", "bet")  # rien à suivre, l'adversaire ouvre l'action
ALL_ACTIONS = FACING_BET_ACTIONS + NOT_FACING_BET_ACTIONS + ("fold",)

MIN_BLUFF_FLOOR_WEIGHT = 0.08


@dataclass
class NarrowResult:
    original_combos: int
    remaining_combos: int
    remaining_weight: float
    original_weight: float
    range_str: str

    def to_json(self) -> dict[str, Any]:
        return {
            "original_combos": self.original_combos,
            "remaining_combos": self.remaining_combos,
            "retained_pct": round(100 * self.remaining_weight / self.original_weight, 1)
            if self.original_weight else 0.0,
            "range": self.range_str,
        }


_STRUCTURAL_ZERO_MARKERS = ("bluff_dies_multiway", "bluff_multi_street_blocked")


def _pressure_exhausted(b: Budget, action: str) -> bool:
    """True si ``action`` est absente de ``b.viable_actions`` UNIQUEMENT
    parce que le budget ATT a été épuisé par la pression déjà dépensée --
    False si elle a été coupée par une règle structurelle (multiway,
    exploit gate), qui doit rester un vrai zéro plutôt que de recevoir le
    plancher de rétention.

    Piège évité ici : ``budget.compute()`` ajoute TOUJOURS une entrée
    générique "budget ATT insuffisant" dès que ``att_remaining <= 0``, que
    ce zéro vienne de la pression OU d'une règle structurelle qui a déjà
    remis ``att`` à 0 en amont -- les deux entrées coexistent alors dans
    ``removed``. Ne se fier qu'au message générique aurait donc flooré à
    tort des combos coupés par une règle structurelle (ex. `bluff_dies_
    multiway` à 3+ adversaires) ; on vérifie donc d'abord qu'aucun marqueur
    structurel n'est présent pour le côté agressif avant de considérer
    l'épuisement par pression. Les règles structurelles ne portent que sur
    ATT (bet/raise), jamais sur DEF (call) -- restreint donc aux deux."""
    if action in ("bet", "raise") and any(
        marker in r["reason"] for r in b.removed for marker in _STRUCTURAL_ZERO_MARKERS
    ):
        return False
    return any(
        r["action"] == action and "insuffisant" in r["reason"]
        for r in b.removed
    )


def _combo_token(wc: WeightedCombo) -> str:
    base = f"{wc.combo[0]}{wc.combo[1]}"
    if wc.weight >= 1.0 - 1e-9:
        return base
    return f"{base}@{wc.weight * 100:.2f}%"


def narrow(range_str: str, board: list[Card], action: str, *, pot_type: str, street: str,
           n_opponents_active: int = 1, pressure_spent: float = 0.0, pressure_faced: float = 0.0,
           villain_archetype: str | None = None) -> NarrowResult:
    """``action`` : "fold"/"check"/"call"/"bet"/"raise" — l'action réellement
    observée. "fold" et "check" ne filtrent pas (un fold ne dit rien de
    positif sur la range restante ; un check est un signal trop faible,
    presque toute main peut checker — approximation documentée, pas un
    modèle de fréquence de check par classe)."""
    if action not in ALL_ACTIONS:
        raise ValueError(f"action inconnue pour le narrowing : {action!r}")
    facing_bet = action in FACING_BET_ACTIONS
    no_filter = action in ("fold", "check")

    board_set = set(board)
    combos = [wc for wc in parse_range(range_str) if not (set(wc.combo) & board_set)]
    texture = classify_texture(board)

    kept: list[WeightedCombo] = []
    for wc in combos:
        if no_filter:
            kept.append(wc)
            continue
        hc = classify(list(wc.combo), board)
        b = compute_budget(
            hc, texture, pot_type=pot_type, street=street, n_opponents_active=n_opponents_active,
            pressure_spent=pressure_spent, pressure_faced=pressure_faced,
            villain_archetype=villain_archetype, facing_bet=facing_bet,
        )
        if action in b.viable_actions:
            kept.append(wc)
        elif _pressure_exhausted(b, action):
            floored_weight = wc.weight * MIN_BLUFF_FLOOR_WEIGHT
            if floored_weight > 0:
                kept.append(WeightedCombo(combo=wc.combo, weight=floored_weight))
        # sinon : coupé par une règle structurelle (multiway/exploit) -- rejeté entièrement

    original_weight = sum(c.weight for c in combos)
    remaining_weight = sum(c.weight for c in kept)
    kept_str = ",".join(_combo_token(c) for c in kept)

    return NarrowResult(
        original_combos=len(combos), remaining_combos=len(kept),
        remaining_weight=remaining_weight, original_weight=original_weight,
        range_str=kept_str,
    )
