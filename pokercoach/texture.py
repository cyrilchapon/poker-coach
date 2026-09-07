"""Couche B — classification de la texture de board.

Reprend le vocabulaire de ``data/texture-modifiers.yaml`` (annexes D.1/E de
PokerSkill). Le board est classé sur trois axes indépendants (suit, rank,
wetness) plus une détection de "board spécial" qui, quand elle s'applique,
REMPLACE la logique standard de force de paire (cf.
``special_board_overrides`` dans le YAML).

Convention sur le potentiel de quinte (choix documenté, l'annexe originale
n'est pas assez précise pour être suivie à la lettre) : on cherche, parmi les
10 fenêtres de 5 rangs consécutifs (l'As comptant bas et haut), celles où le
board fournit déjà 4 des 5 rangs. Chaque fenêtre de ce type a un rang
manquant unique ; le nombre de rangs manquants DISTINCTS observés across
toutes les fenêtres détermine la forme :
  - 1 rang manquant distinct  -> "gutshot" côté board -> straight_possible_single
  - 2+ rangs manquants distincts (typiquement les deux extrémités d'un board
    à 3 rangs consécutifs) -> "open-ended" côté board -> straight_possible_multi
Ces deux labels alimentent directement les clés `one_card_straight_gutshot` /
`one_card_straight_open_ended` de `pair_class_penalties` dans
texture-modifiers.yaml.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .cards import Card, RANKS

SUIT_LABELS = ("rainbow", "two_tone", "three_flush", "four_plus_flush")
STRAIGHT_SHAPES = ("gutshot", "open_ended")

# Les 10 fenêtres de 5 rangs consécutifs, As bas et haut. Index dans RANKS
# ("23456789TJQKA"), l'As-bas utilise l'index -1 conventionnellement (12 % 13
# donnerait la mauvaise carte, donc on encode l'As bas comme rank_index 13
# ("au-dessus" du roi) uniquement pour cette fenêtre).
_ACE_LOW = 13  # sentinelle : "As" agissant comme rang 1 dans la quinte basse


def _rank_indices_with_ace_low(cards: list[Card]) -> set[int]:
    indices = {c.rank_index for c in cards}
    if 12 in indices:  # As présent -> aussi disponible comme rang bas
        indices.add(_ACE_LOW)
    return indices


def _straight_windows() -> list[set[int]]:
    # rangs 0..12 = 2..A ; fenêtre wheel = {13(As-bas),0,1,2,3} = A2345
    windows = []
    for high in range(4, 13):  # 6-high .. As-high (5432A exclu, couvert par wheel)
        windows.append(set(range(high - 4, high + 1)))
    windows.append({_ACE_LOW, 0, 1, 2, 3})  # wheel A-2-3-4-5
    return windows


_WINDOWS = _straight_windows()


@dataclass
class Texture:
    suit: str
    rank_labels: list[str]
    wetness: str
    straight_shape: str | None
    special: str | None
    board_rank_counts: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "suit": self.suit,
            "rank_labels": self.rank_labels,
            "wetness": self.wetness,
            "straight_shape": self.straight_shape,
            "special": self.special,
        }


def classify(board: list[Card]) -> Texture:
    if len(board) < 3:
        raise ValueError("classify(board) nécessite au moins 3 cartes (flop)")

    suit = _classify_suit(board)
    rank_family, rank_counts = _classify_rank_family(board)
    straight_shape, straight_tag = _classify_straight(board)
    special = _classify_special(board, rank_family, suit)

    rank_labels = [rank_family]
    if straight_tag:
        rank_labels.append(straight_tag)

    wetness = _classify_wetness(suit, straight_tag)

    return Texture(
        suit=suit, rank_labels=rank_labels, wetness=wetness,
        straight_shape=straight_shape, special=special,
        board_rank_counts={r: n for r, n in rank_counts.items()},
    )


def _classify_suit(board: list[Card]) -> str:
    counts = Counter(c.suit for c in board)
    max_count = max(counts.values())
    if max_count >= 4:
        return "four_plus_flush"
    if max_count == 3:
        return "three_flush"
    if max_count == 2:
        return "two_tone"
    return "rainbow"


def _classify_rank_family(board: list[Card]) -> tuple[str, dict[str, int]]:
    counts = Counter(c.rank for c in board)
    max_count = max(counts.values())
    pair_count = sum(1 for n in counts.values() if n == 2)
    if max_count == 4:
        family = "quads"
    elif max_count == 3:
        family = "trips"
    elif pair_count >= 2:
        family = "double_paired"
    elif pair_count == 1:
        family = "paired"
    else:
        family = "unpaired"
    return family, dict(counts)


def _classify_straight(board: list[Card]) -> tuple[str | None, str | None]:
    indices = _rank_indices_with_ace_low(board)
    missing_ranks: set[int] = set()
    for window in _WINDOWS:
        present = window & indices
        if len(present) == 4:
            missing_ranks |= (window - indices)
    if not missing_ranks:
        return None, None
    shape = "gutshot" if len(missing_ranks) == 1 else "open_ended"
    tag = "straight_possible_single" if shape == "gutshot" else "straight_possible_multi"
    return shape, tag


def _classify_special(board: list[Card], rank_family: str, suit: str) -> str | None:
    if rank_family == "quads":
        return "quads_board"
    counts = Counter(c.rank for c in board)
    if 3 in counts.values() and 2 in counts.values():
        return "full_house_board"
    if len(board) == 5 and suit == "four_plus_flush" and max(Counter(c.suit for c in board).values()) == 5:
        return "board_flush"
    if len(board) == 5 and rank_family == "unpaired":
        indices = _rank_indices_with_ace_low(board)
        for window in _WINDOWS:
            if len(window) == 5 and window <= indices:
                return "board_straight"
    if rank_family == "trips":
        return "trips_board"
    if rank_family == "double_paired":
        return "double_paired_board"
    return None


def _classify_wetness(suit: str, straight_tag: str | None) -> str:
    score = 0
    score += {"rainbow": 0, "two_tone": 1, "three_flush": 2, "four_plus_flush": 2}[suit]
    score += {None: 0, "straight_possible_single": 1, "straight_possible_multi": 2}[straight_tag]
    if score <= 0:
        return "dry"
    if score == 1:
        return "slightly_wet"
    if score in (2, 3):
        return "wet"
    return "very_wet"
