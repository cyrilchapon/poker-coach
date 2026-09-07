"""Couche B — équité main/range vs range.

Notation de range supportée (grammaire reprise et étendue de la v1,
``current-plugin/range-notation/SKILL.md`` et
``equity-engine/scripts/equity.py``) :

    AA, KK+, 22-77          paires, paire+, plage de paires
    AKs, ATo, AKo+, JTs-98s combos suited/offsuit, plage
    AsKd                    une main exacte à deux cartes (limitation v1 levée)
    <token>@NN%             pondération explicite du token (nouveau en v2)

Séparateur : virgule. Espaces ignorés.

Méthode : énumération exhaustive quand le volume de travail
(paires de combos × runouts restants) tient dans un budget raisonnable ;
Monte-Carlo (boucle scalaire, backend eval7 en C — assez rapide pour un
usage mono-joueur sans avoir besoin d'un vecteur numpy) sinon. Cache
mémoïsé par ``(range1, range2, board, dead, iterations)`` sur la durée du
process.
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from .cards import Card, RANKS, SUITS_UNICODE, parse_cards
from .handeval import FULL_DECK, evaluate

ENUMERATION_BUDGET = 300_000
DEFAULT_ITERATIONS = 20_000


@dataclass(frozen=True)
class WeightedCombo:
    combo: tuple[Card, Card]
    weight: float


def parse_range(range_str: str) -> list[WeightedCombo]:
    """Retourne la liste dédupliquée des combos (avec poids) désignés par la
    range. Les poids par combo sont sommés si plusieurs tokens se recouvrent,
    puis plafonnés à 1.0."""
    weights: dict[tuple[Card, Card], float] = {}

    for raw_token in range_str.replace(" ", "").split(","):
        if not raw_token:
            continue
        token, weight = raw_token, 1.0
        if "@" in raw_token:
            token, pct = raw_token.split("@")
            weight = float(pct.rstrip("%")) / 100.0

        for combo in _expand_token(token):
            weights[combo] = min(1.0, weights.get(combo, 0.0) + weight)

    return [WeightedCombo(combo=c, weight=w) for c, w in weights.items()]


def _expand_token(token: str) -> list[tuple[Card, Card]]:
    # Main exacte à deux cartes : "AsKd" ou "A♠K♦" (4 caractères, pas de +/-)
    if len(token) == 4 and "+" not in token and "-" not in token:
        cards = parse_cards([token[0:2], token[2:4]])
        return [_sorted_pair(cards[0], cards[1])]

    if "-" in token:
        lo, hi = token.split("-")
        return _range_between(lo, hi)

    plus = token.endswith("+")
    base = token[:-1] if plus else token

    if len(base) == 2 and base[0] == base[1]:
        return _pairs(base[0], to_ace=plus)
    if len(base) == 3:
        r1, r2, suited = base[0], base[1], base[2]
        if plus:
            return _plus_connector(r1, r2, suited)
        return _combos_for_ranks(r1, r2, suited)
    raise ValueError(f"token de range invalide : {token!r}")


def _pairs(rank: str, *, to_ace: bool) -> list[tuple[Card, Card]]:
    start = RANKS.index(rank)
    ranks = RANKS[start:] if to_ace else rank
    out = []
    for r in ranks:
        out += _combos_for_ranks(r, r, "")
    return out


def _combos_for_ranks(r1: str, r2: str, suited: str) -> list[tuple[Card, Card]]:
    if r1 == r2:
        return [
            _sorted_pair(Card(r1, s1), Card(r1, s2))
            for s1, s2 in itertools.combinations(SUITS_UNICODE, 2)
        ]
    if suited == "s":
        return [_sorted_pair(Card(r1, s), Card(r2, s)) for s in SUITS_UNICODE]
    if suited == "o":
        return [
            _sorted_pair(Card(r1, s1), Card(r2, s2))
            for s1 in SUITS_UNICODE for s2 in SUITS_UNICODE if s1 != s2
        ]
    raise ValueError(f"suffixe suited/offsuit invalide : {suited!r}")


def _plus_connector(r1: str, r2: str, suited: str) -> list[tuple[Card, Card]]:
    """``r1r2s+`` (ex ``ATs+``) : carte haute FIXÉE à ``r1``, carte basse
    montant de ``r2`` jusqu'à juste sous ``r1`` (ATs+ = ATs,AJs,AQs,AKs)."""
    i1, i2 = RANKS.index(r1), RANKS.index(r2)
    out = []
    for j in range(i2, i1):
        out += _combos_for_ranks(r1, RANKS[j], suited)
    return out


def _range_between(lo: str, hi: str) -> list[tuple[Card, Card]]:
    if len(lo) == 2 and lo[0] == lo[1]:  # plage de paires, ex "22-77"
        i_lo, i_hi = RANKS.index(lo[0]), RANKS.index(hi[0])
        out = []
        for i in range(i_lo, i_hi + 1):
            out += _combos_for_ranks(RANKS[i], RANKS[i], "")
        return out
    # plage de connecteurs, ex "JTs-98s"
    suited = hi[2]
    i_lo_high, i_lo_low = RANKS.index(lo[0]), RANKS.index(lo[1])
    i_hi_high, i_hi_low = RANKS.index(hi[0]), RANKS.index(hi[1])
    gap = i_lo_high - i_lo_low
    out = []
    for i in range(i_hi_high, i_lo_high + 1):
        out += _combos_for_ranks(RANKS[i], RANKS[i - gap], suited)
    return out


def _sorted_pair(a: Card, b: Card) -> tuple[Card, Card]:
    return (a, b) if a.rank_index >= b.rank_index else (b, a)


# --- Calcul d'équité ----------------------------------------------------

@dataclass
class EquityResult:
    range1_equity: float
    range2_equity: float
    method: str
    iterations: int | None
    combos_used: int

    def to_json(self) -> dict[str, Any]:
        return {
            "range1_equity": round(self.range1_equity, 4),
            "range2_equity": round(self.range2_equity, 4),
            "method": self.method,
            "iterations": self.iterations,
            "combos_used": self.combos_used,
        }


def equity(range1_str: str, range2_str: str, *, board: list[Card] = (), dead: list[Card] = (),
           iterations: int = DEFAULT_ITERATIONS) -> EquityResult:
    board_key = tuple(sorted((c.rank, c.suit) for c in board))
    dead_key = tuple(sorted((c.rank, c.suit) for c in dead))
    return _equity_cached(range1_str, range2_str, board_key, dead_key, iterations)


@lru_cache(maxsize=2048)
def _equity_cached(range1_str: str, range2_str: str, board_key: tuple, dead_key: tuple,
                    iterations: int) -> EquityResult:
    board = [Card(r, s) for r, s in board_key]
    dead = set(Card(r, s) for r, s in dead_key) | set(board)

    r1 = [wc for wc in parse_range(range1_str) if not (set(wc.combo) & dead)]
    r2 = [wc for wc in parse_range(range2_str) if not (set(wc.combo) & dead)]
    if not r1 or not r2:
        raise ValueError("range vide une fois les cartes mortes/board retirées")

    pairs = [
        (a, b) for a in r1 for b in r2
        if not (set(a.combo) & set(b.combo))
    ]
    if not pairs:
        raise ValueError("aucune paire de combos valide entre les deux ranges (conflit total)")

    remaining_deck = [c for c in FULL_DECK if c not in dead]
    n_missing = 5 - len(board)

    n_runouts = 1
    for i in range(n_missing):
        n_runouts *= (len(remaining_deck) - i)
    n_runouts = n_runouts // (1 if n_missing <= 1 else _factorial(n_missing))

    workload = len(pairs) * max(1, n_runouts)

    if n_missing == 0 or workload <= ENUMERATION_BUDGET:
        return _enumerate_equity(pairs, board, remaining_deck, n_missing)
    return _monte_carlo_equity(pairs, board, remaining_deck, n_missing, iterations)


def _factorial(n: int) -> int:
    r = 1
    for i in range(2, n + 1):
        r *= i
    return r


def _enumerate_equity(pairs, board, remaining_deck, n_missing) -> EquityResult:
    total_w = 0.0
    r1_w = 0.0
    r2_w = 0.0
    combos_used = 0

    for a, b in pairs:
        used = set(a.combo) | set(b.combo)
        deck_for_pair = [c for c in remaining_deck if c not in used]
        runouts = itertools.combinations(deck_for_pair, n_missing) if n_missing else [()]
        pair_weight = a.weight * b.weight
        for extra in runouts:
            full_board = board + list(extra)
            s1 = evaluate(list(a.combo) + full_board)
            s2 = evaluate(list(b.combo) + full_board)
            total_w += pair_weight
            combos_used += 1
            if s1 > s2:
                r1_w += pair_weight
            elif s2 > s1:
                r2_w += pair_weight
            else:
                r1_w += pair_weight / 2
                r2_w += pair_weight / 2

    return EquityResult(
        range1_equity=r1_w / total_w, range2_equity=r2_w / total_w,
        method="enumeration", iterations=None, combos_used=combos_used,
    )


def _monte_carlo_equity(pairs, board, remaining_deck, n_missing, iterations) -> EquityResult:
    weights = [a.weight * b.weight for a, b in pairs]
    total_w = 0.0
    r1_w = 0.0
    r2_w = 0.0
    rng = random.Random(1234567)  # déterministe : le brief exige une mesure reproductible

    for _ in range(iterations):
        a, b = rng.choices(pairs, weights=weights, k=1)[0]
        used = set(a.combo) | set(b.combo)
        pool = [c for c in remaining_deck if c not in used]
        extra = rng.sample(pool, n_missing) if n_missing else []
        full_board = board + extra
        s1 = evaluate(list(a.combo) + full_board)
        s2 = evaluate(list(b.combo) + full_board)
        total_w += 1
        if s1 > s2:
            r1_w += 1
        elif s2 > s1:
            r2_w += 1
        else:
            r1_w += 0.5
            r2_w += 0.5

    return EquityResult(
        range1_equity=r1_w / total_w, range2_equity=r2_w / total_w,
        method="monte_carlo", iterations=iterations, combos_used=len(pairs),
    )
