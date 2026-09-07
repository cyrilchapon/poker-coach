"""Range narrowing mécanique : filtre une range adverse aux combos dont le
budget ATT/DEF rend l'action observée viable, plutôt que de la resserrer "à
l'oeil". C'est le même moteur (handclass + texture + budget) qui juge le
héros, appliqué à chaque combo adverse hypothétique.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..budget import compute as compute_budget
from ..cards import Card
from ..equity import WeightedCombo, parse_range
from ..handclass import classify
from ..texture import classify as classify_texture

ACTION_TO_VIABLE = {
    "raise": "raise", "bet": "raise",
    "call": "call", "check": "call",
    "fold": "fold",
}


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


def narrow(range_str: str, board: list[Card], action: str, *, pot_type: str, street: str,
           n_opponents_active: int = 1, pressure_spent: float = 0.0, pressure_faced: float = 0.0,
           villain_archetype: str | None = None) -> NarrowResult:
    viable_key = ACTION_TO_VIABLE.get(action)
    if viable_key is None:
        raise ValueError(f"action inconnue pour le narrowing : {action!r}")

    board_set = set(board)
    combos = [wc for wc in parse_range(range_str) if not (set(wc.combo) & board_set)]
    texture = classify_texture(board)

    kept: list[WeightedCombo] = []
    for wc in combos:
        hc = classify(list(wc.combo), board)
        b = compute_budget(
            hc, texture, pot_type=pot_type, street=street, n_opponents_active=n_opponents_active,
            pressure_spent=pressure_spent, pressure_faced=pressure_faced,
            villain_archetype=villain_archetype,
        )
        if viable_key == "fold" or viable_key in b.viable_actions:
            kept.append(wc)

    original_weight = sum(c.weight for c in combos)
    remaining_weight = sum(c.weight for c in kept)
    kept_str = ",".join(f"{c.combo[0]}{c.combo[1]}" for c in kept)

    return NarrowResult(
        original_combos=len(combos), remaining_combos=len(kept),
        remaining_weight=remaining_weight, original_weight=original_weight,
        range_str=kept_str,
    )
