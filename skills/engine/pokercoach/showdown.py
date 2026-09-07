"""Couche B — résolution DÉTERMINISTE d'un showdown, jamais à l'œil.

Reprend le comportement de la v1 (``current-plugin/live-session/scripts/showdown.py``),
réécrit sur le backend ``handeval`` (eval7 ou repli pur Python) au lieu de
``treys``. Obligation de passer par ce script préservée (cf. PROMPT.md §5,
"Résolution de showdown obligatoirement par script, jamais à l'œil").
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .cards import Card
from .handeval import evaluate, handtype


@dataclass
class ShowdownEntry:
    name: str
    cards: list[Card]
    score: int
    hand_type: str
    result: str  # win | tie | lose

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name, "cards": [str(c) for c in self.cards],
            "hand_type": self.hand_type, "result": self.result,
        }


def resolve(board: list[Card], hands: list[tuple[str, list[Card]]]) -> list[ShowdownEntry]:
    """``hands``: liste de (nom, [2 cartes]). Retourne triée, meilleure main
    en premier, avec égalités marquées ``tie``."""
    scored = []
    for name, cards in hands:
        score = evaluate(list(cards) + list(board))
        scored.append((name, cards, score, handtype(score)))
    scored.sort(key=lambda t: -t[2])
    best = scored[0][2]
    winners = [t for t in scored if t[2] == best]
    results = []
    for name, cards, score, ht in scored:
        if score == best:
            result = "tie" if len(winners) > 1 else "win"
        else:
            result = "lose"
        results.append(ShowdownEntry(name=name, cards=cards, score=score, hand_type=ht, result=result))
    return results
