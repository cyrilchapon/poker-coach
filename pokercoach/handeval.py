"""Wrapper mince autour d'``eval7`` (backend C) — évaluation brute de main.

Fournit deux primitives dont tout le reste (``handclass.py``, ``equity.py``,
``showdown.py``) a besoin :

- un score de force comparable pour 5, 6 ou 7 cartes (plus haut = meilleur,
  convention eval7) ;
- le calcul du "nut check" : la main du héros est-elle, à cet instant, la
  meilleure main possible compte tenu du board et des cartes déjà mortes ?
  C'est la façon la plus robuste de déterminer la classe "nuts" (PokerSkill) :
  plutôt que d'essayer d'encoder en dur toutes les définitions textuelles de
  l'annexe ("couleur nut", "quinte nut sur board sans couleur ni paire", ...),
  on énumère toutes les mains adverses possibles compte tenu des cartes
  connues et on compare.

Fallback : si ``eval7`` n'est pas installable dans le sandbox (contrainte
technique §6 du brief : "vérifie la disponibilité par pip install avant de
t'engager ; garde un fallback treys"), une resucée pure-Python est fournie et
prend le relais automatiquement. Elle est plus lente mais suffisante pour un
usage mono-joueur (pas de contrainte de débit d'un solveur).
"""
from __future__ import annotations

import itertools
from functools import lru_cache

from .cards import Card, RANKS, SUITS_UNICODE

try:
    import eval7 as _eval7
    _HAS_EVAL7 = True
except ImportError:  # pragma: no cover — exercised only when eval7 truly absent
    _HAS_EVAL7 = False

FULL_DECK: tuple[Card, ...] = tuple(Card(r, s) for r in RANKS for s in SUITS_UNICODE)

HAND_CATEGORIES = (
    "High Card", "Pair", "Two Pair", "Trips", "Straight",
    "Flush", "Full House", "Quads", "Straight Flush",
)


def _to_eval7(card: Card) -> "_eval7.Card":
    return _eval7.Card(card.to_letter())


def evaluate(cards: list[Card]) -> int:
    """Score de force pour 5, 6 ou 7 cartes. Plus haut = meilleure main."""
    if _HAS_EVAL7:
        return _eval7.evaluate([_to_eval7(c) for c in cards])
    return _evaluate_pure_python(cards)


def handtype(score: int) -> str:
    """Catégorie standard (une des neuf) pour un score renvoyé par ``evaluate``."""
    if _HAS_EVAL7:
        return _eval7.handtype(score)
    return HAND_CATEGORIES[_pure_python_category(score)]


def best_score_and_type(cards: list[Card]) -> tuple[int, str]:
    score = evaluate(cards)
    return score, handtype(score)


def is_nuts(hole: list[Card], board: list[Card], *, dead: list[Card] = ()) -> bool:
    """True si aucune combinaison de 2 cartes restantes ne bat la main du héros
    étant donné ``board`` (i.e. le héros a littéralement la meilleure main
    possible à cet instant)."""
    return best_possible_score(board, dead=list(hole) + list(dead)) <= evaluate(list(hole) + list(board))


def best_possible_score(board: list[Card], *, dead: list[Card] = ()) -> int:
    """Le meilleur score atteignable par N'IMPORTE QUELLE main de 2 cartes
    compatible avec ``board``, en excluant les cartes de ``dead`` (typiquement
    les cartes du héros + toute autre carte connue). Mémoïsé par (board, dead)."""
    return _best_possible_score_cached(_card_key(board), _card_key(dead))


@lru_cache(maxsize=4096)
def _best_possible_score_cached(board_key: tuple, dead_key: tuple) -> int:
    board = [Card(r, s) for r, s in board_key]
    dead = [Card(r, s) for r, s in dead_key]
    known = set(board) | set(dead)
    remaining = [c for c in FULL_DECK if c not in known]
    best = -1
    for a, b in itertools.combinations(remaining, 2):
        score = evaluate([a, b] + board)
        if score > best:
            best = score
    return best


def _card_key(cards) -> tuple:
    return tuple(sorted((c.rank, c.suit) for c in cards))


# --- Fallback pure Python (utilisé seulement si eval7 est indisponible) ----
# Évaluateur simple par énumération des C(n,5) combinaisons, comparaison par
# tuple (catégorie, tiebreakers...). Suffisant pour un usage mono-joueur,
# nettement plus lent qu'eval7 sur de gros volumes de Monte-Carlo.

def _rank_counts(cards: list[Card]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for c in cards:
        counts[c.rank_index] = counts.get(c.rank_index, 0) + 1
    return counts


def _straight_high(rank_indices: set[int]) -> int | None:
    ranks = set(rank_indices)
    if {12, 0, 1, 2, 3} <= ranks:  # wheel: A-2-3-4-5
        return 3
    best = None
    for high in range(4, 13):
        if all(r in ranks for r in range(high - 4, high + 1)):
            best = high
    return best


def _score_5(cards: list[Card]) -> tuple:
    ranks = [c.rank_index for c in cards]
    suits = [c.suit for c in cards]
    counts = _rank_counts(cards)
    is_flush = len(set(suits)) == 1
    straight_high = _straight_high(set(ranks))
    by_count = sorted(counts.items(), key=lambda kv: (-kv[1], -kv[0]))
    count_shape = tuple(c for _, c in by_count)
    tiebreak = tuple(r for r, _ in by_count)

    if is_flush and straight_high is not None:
        return (8, straight_high)
    if count_shape == (4, 1):
        return (7, tiebreak)
    if count_shape == (3, 2):
        return (6, tiebreak)
    if is_flush:
        return (5, tuple(sorted(ranks, reverse=True)))
    if straight_high is not None:
        return (4, straight_high)
    if count_shape == (3, 1, 1):
        return (3, tiebreak)
    if count_shape == (2, 2, 1):
        return (2, tiebreak)
    if count_shape == (2, 1, 1, 1):
        return (1, tiebreak)
    return (0, tuple(sorted(ranks, reverse=True)))


# Pack a (category, tiebreak) tuple into a single comparable/encodable int so
# the pure-Python path has the same evaluate()->int / handtype(int)->str
# contract as eval7.
def _encode(cat_tiebreak: tuple) -> int:
    cat, tb = cat_tiebreak
    flat = tb if isinstance(tb, tuple) else (tb,)
    value = cat
    for t in flat:
        value = value * 14 + t
    for _ in range(5 - len(flat)):
        value *= 14
    return value


def _pure_python_category(score: int) -> int:
    # Reverse the packing above just enough to recover the category digit.
    v = score
    for _ in range(5):
        v //= 14
    return v


def _evaluate_pure_python(cards: list[Card]) -> int:
    best = None
    for combo in itertools.combinations(cards, 5):
        packed = _encode(_score_5(list(combo)))
        if best is None or packed > best:
            best = packed
    return best
