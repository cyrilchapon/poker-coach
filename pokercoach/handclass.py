"""Couche B — classification de main : les 23 classes PokerSkill + outs + blockers.

Vocabulaire et hiérarchie : ``data/hand-classes.yaml`` (annexes D.2/E de
PokerSkill). Deux valeurs toujours retournées : une classe de main faite
(``made``, jamais nulle — "trash" est le plancher) et une classe de tirage
(``draw``, nullable).

Simplifications documentées (v2.0, à affiner) — honnêteté sur la précision,
cf. references/03-multiway-generalization.md :

- **"nuts"** est détecté génériquement : on énumère toutes les mains de 2
  cartes adverses possibles compte tenu du board et on compare le score.
  C'est plus robuste que d'encoder à la main chaque définition textuelle de
  l'annexe, et ça couvre uniformément full+/couleur nut/quinte nut/set nut.
- **two_pair sur board apparié** : suit la note du YAML — si une des deux
  paires vient du board lui-même, la main est reclassée dans la famille
  paire simple (overpair/top_pair/...) plutôt que "two_pair".
- **Kicker buckets** (tptk/tpsk/k3/k4/k5/other) : calculés par position du
  kicker parmi les rangs de board restants + le kicker lui-même, triés
  descendant. Une bonne approximation, pas une reproduction exacte des
  seuils de l'annexe (non publiés à ce niveau de détail).
- **Underpair** (paire de poche sous toutes les cartes du board, ne touchant
  pas le board) n'a pas de classe dédiée dans la taxonomie PokerSkill à 15
  classes : rangée dans ``weak_showdown``.
- **Tirages** : classification simplifiée par seuils monotones (rang de la
  couleur, ouverture de la quinte, somme des rangs pour les surcartes) —
  pas de détection des combinaisons "backdoor". Les ``outs`` restent EXACTS
  (comptage réel par amélioration stricte du score, méthode déjà validée en
  v1 dans ``equity-engine/scripts/describe_hand.py``).
- **distance_to_boundary** n'est calculé (0.15 vs 1.0) que pour la famille
  paire simple, en comparant le kicker à la frontière de bucket la plus
  proche. Ailleurs, valeur par défaut 1.0 (pas de signal de proximité).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .cards import Card, RANKS
from .handeval import FULL_DECK, evaluate, is_nuts
from .texture import Texture, classify as classify_texture

KICKER_BUCKETS = ("tptk", "tpsk", "k3", "k4", "k5", "other")


@dataclass
class HandClass:
    made: str
    made_sub: dict[str, Any]
    board_override: str | None
    draw: str | None
    draw_sub: dict[str, Any]
    outs: int | None
    blockers: list[str]
    distance_to_boundary: float

    def to_json(self) -> dict[str, Any]:
        return {
            "made": self.made,
            "made_sub": self.made_sub,
            "board_override": self.board_override,
            "draw": self.draw,
            "draw_sub": self.draw_sub,
            "outs": self.outs,
            "blockers": self.blockers,
            "distance_to_boundary": round(self.distance_to_boundary, 2),
        }


def classify(hole: list[Card], board: list[Card]) -> HandClass:
    if len(hole) != 2:
        raise ValueError("classify(hole, board) attend exactement 2 cartes en main")
    if len(board) < 3:
        raise ValueError("classify(hole, board) nécessite au moins un flop (3 cartes)")

    texture = classify_texture(board)
    made, made_sub, distance = _classify_made(hole, board, texture)
    board_override = texture.special if texture.special else None
    draw, draw_sub = _classify_draw(hole, board, texture)
    outs = _count_outs(hole, board) if len(board) < 5 else None
    blockers = _blockers(hole, board, texture)

    return HandClass(
        made=made, made_sub=made_sub, board_override=board_override,
        draw=draw, draw_sub=draw_sub, outs=outs, blockers=blockers,
        distance_to_boundary=distance,
    )


# --- Classe de main faite ---------------------------------------------------

def _board_unique_ranks_sorted(board: list[Card]) -> list[str]:
    seen: list[str] = []
    for c in sorted(board, key=lambda c: -c.rank_index):
        if c.rank not in seen:
            seen.append(c.rank)
    return seen


def _classify_made(hole: list[Card], board: list[Card], texture: Texture) -> tuple[str, dict, float]:
    all_cards = hole + board
    from .handeval import handtype
    score = evaluate(all_cards)
    cat9 = handtype(score)

    # "Full+" (full house, quads, straight flush) est INCONDITIONNELLEMENT
    # "nuts" par définition (annexe D.2) — même si une main encore plus
    # grosse (un quad supérieur, par ex.) reste possible pour l'adversaire.
    # Pour le reste (flush/straight/set), le nut-check générique ci-dessus
    # sert de proxy fidèle aux définitions ("couleur nut", "quinte nut sur
    # board sans couleur ni paire", "brelan servi sur board sans tirage") :
    # dans ces cas, "nuts" == littéralement imbattable maintenant.
    if cat9 in ("Straight Flush", "Quads", "Full House") or is_nuts(hole, board):
        return "nuts", {}, 1.0

    board_ranks = {c.rank for c in board}
    board_rank_counts = texture.board_rank_counts
    board_flushiness = {
        "rainbow": "no_flush", "two_tone": "no_flush",
        "three_flush": "three_flush", "four_plus_flush": "four_plus_flush",
    }[texture.suit]
    paired_board = texture.rank_labels[0] in ("paired", "double_paired", "trips", "quads")

    if cat9 == "Flush":
        return "flush", _flush_details(hole, board, texture), 1.0
    if cat9 == "Straight":
        return "straight", _straight_details(hole, board, texture, board_flushiness, paired_board), 1.0
    if cat9 == "Trips":
        made = "set" if (hole[0].rank == hole[1].rank and texture.special is None) else "trips"
        return made, _trips_or_set_details(hole, board, texture, board_flushiness), 1.0
    if cat9 == "Two Pair":
        hole_ranks = {c.rank for c in hole}
        matched = [r for r in hole_ranks if board_rank_counts.get(r, 0) >= 1]
        if len(matched) >= 2 and texture.rank_labels[0] == "unpaired":
            rank_bucket = _two_pair_rank_bucket(matched, board)
            return "two_pair", {"rank_bucket": rank_bucket}, 1.0
        # Une des deux paires vient du board -> reclassée en paire simple.
        return _classify_pair_family(hole, board, texture)
    if cat9 == "Pair":
        return _classify_pair_family(hole, board, texture)
    # "High Card"
    return _classify_high_card(hole, board)


def _flush_details(hole: list[Card], board: list[Card], texture: Texture) -> dict:
    suited_hole = [c for c in hole if any(b.suit == c.suit for b in board)]
    suit_counts: dict[str, int] = {}
    for c in board:
        suit_counts[c.suit] = suit_counts.get(c.suit, 0) + 1
    flush_suit = max(suit_counts, key=lambda s: suit_counts[s])
    hero_suited = [c for c in hole if c.suit == flush_suit]
    if not hero_suited:
        return {"board_type": "n/a", "rank_bucket": "n/a"}
    hero_high = max(hero_suited, key=lambda c: c.rank_index)

    if texture.suit == "four_plus_flush":
        not_on_board = sorted(
            (r for r in RANKS if not any(b.rank == r and b.suit == flush_suit for b in board)),
            key=lambda r: -RANKS.index(r),
        )
        position = not_on_board.index(hero_high.rank) + 1
        bucket = {1: "rank_1", 2: "rank_2", 3: "rank_3", 4: "rank_4", 5: "rank_5"}.get(position)
        if bucket is None:
            bucket = "rank_6_7" if position <= 7 else "rank_8_9"
        return {"board_type": "one_card_flush", "rank_bucket": bucket}

    board_type = "paired" if texture.rank_labels[0] in ("paired", "double_paired", "trips") else "three_flush"
    not_on_board = [r for r in RANKS if not any(b.rank == r and b.suit == flush_suit for b in board)]
    is_nut_flush = hero_high.rank == max(not_on_board, key=lambda r: RANKS.index(r))
    if is_nut_flush:
        bucket = "nut"
    else:
        bucket = "big" if hero_high.rank_index >= RANKS.index("T") else "small"
    return {"board_type": board_type, "rank_bucket": bucket}


def _straight_details(hole: list[Card], board: list[Card], texture: Texture,
                       board_flushiness: str, paired_board: bool) -> dict:
    from .texture import _rank_indices_with_ace_low, _WINDOWS
    combined = _rank_indices_with_ace_low(hole + board)
    board_only = _rank_indices_with_ace_low(board)
    hole_indices = {c.rank_index for c in hole}
    if 12 in hole_indices:
        hole_indices.add(13)

    candidate_windows = [w for w in _WINDOWS if w <= combined]
    winning_window = max(candidate_windows, key=_window_high)

    contribution = "two_card" if len(winning_window & hole_indices) >= 2 else "one_card"

    best_board_window = None
    for window in _WINDOWS:
        if len(window & board_only) >= 3:
            if best_board_window is None or _window_high(window) > _window_high(best_board_window):
                best_board_window = window

    if contribution == "two_card":
        bucket = "two_card"
    else:
        is_top = best_board_window is not None and winning_window == best_board_window
        bucket = "one_card_top_end" if is_top else "one_card_low_end"

    return {"contribution": bucket, "board_flushiness": board_flushiness, "paired_board": paired_board}


def _window_high(window: set[int]) -> int:
    return max(w for w in window if w != 13)


def _trips_or_set_details(hole: list[Card], board: list[Card], texture: Texture, board_flushiness: str) -> dict:
    is_set = hole[0].rank == hole[1].rank
    straight_bucket = None
    if texture.straight_shape == "gutshot":
        straight_bucket = "one_possibility"
    elif texture.straight_shape == "open_ended":
        straight_bucket = "two_possibilities"

    if is_set:
        return {"kind": "set", "board_flushiness": board_flushiness, "straight_possibility": straight_bucket}

    paired_rank = next(r for r in {c.rank for c in hole} if texture.board_rank_counts.get(r, 0) >= 2)
    kicker = next(c for c in hole if c.rank != paired_rank)
    kicker_frac = kicker.rank_index / (len(RANKS) - 1)
    return {"kind": "trips", "board_flushiness": board_flushiness,
            "straight_possibility": straight_bucket, "kicker_frac": round(kicker_frac, 3)}


def _two_pair_rank_bucket(matched_ranks: list[str], board: list[Card]) -> str:
    board_ranks_sorted = _board_unique_ranks_sorted(board)
    high, low = sorted(matched_ranks, key=lambda r: -RANKS.index(r))
    all_possible_pairs = [
        (a, b) for i, a in enumerate(board_ranks_sorted) for b in board_ranks_sorted[i + 1:]
    ]
    all_possible_pairs.sort(key=lambda p: (-RANKS.index(p[0]), -RANKS.index(p[1])))
    try:
        position = all_possible_pairs.index((high, low))
    except ValueError:
        position = len(all_possible_pairs) - 1
    decile = min(9, int(position / max(1, len(all_possible_pairs)) * 10))
    return f"r{decile + 1}"


def _classify_pair_family(hole: list[Card], board: list[Card], texture: Texture) -> tuple[str, dict, float]:
    board_ranks_sorted = _board_unique_ranks_sorted(board)
    board_rank_counts = texture.board_rank_counts

    if hole[0].rank == hole[1].rank and board_rank_counts.get(hole[0].rank, 0) == 0:
        pocket_rank_idx = hole[0].rank_index
        if board and pocket_rank_idx > RANKS.index(board_ranks_sorted[0]):
            return "overpair", {"pocket_rank": hole[0].rank}, 1.0
        return "weak_showdown", {"note": "underpair, non couvert par la taxonomie à 15 classes"}, 1.0

    matched = [c for c in hole if board_rank_counts.get(c.rank, 0) >= 1]
    if not matched:
        return "weak_showdown", {}, 1.0
    paired_card = matched[0]
    position = board_ranks_sorted.index(paired_card.rank)

    if position == 0:
        category = "top_pair"
    elif position == 1:
        category = "second_pair"
    elif position == 2:
        category = "third_pair"
    else:
        category = "fourth_fifth_pair"

    other = [c for c in hole if c is not paired_card]
    kicker_rank_idx = other[0].rank_index if other else -1
    is_pocket_pair = hole[0].rank == hole[1].rank

    remaining_board = [RANKS.index(r) for r in board_ranks_sorted if r != paired_card.rank]
    combined = sorted(set(remaining_board + ([kicker_rank_idx] if not is_pocket_pair else [])), reverse=True)
    if is_pocket_pair:
        kicker_bucket = "tptk"  # une paire de poche "kicke" comme la meilleure carte possible
        distance = 1.0
    else:
        idx = combined.index(kicker_rank_idx)
        kicker_bucket = KICKER_BUCKETS[min(idx, len(KICKER_BUCKETS) - 1)]
        # proche de la frontière si le kicker est adjacent (en rang) à la carte qui le précède
        distance = 1.0
        if idx > 0 and combined[idx - 1] - kicker_rank_idx == 1:
            distance = 0.15
        elif idx + 1 < len(combined) and kicker_rank_idx - combined[idx + 1] == 1:
            distance = 0.15

    sub = {"kicker_bucket": kicker_bucket, "pocket_pair": is_pocket_pair}
    return category, sub, distance


def _classify_high_card(hole: list[Card], board: list[Card]) -> tuple[str, dict, float]:
    board_ranks = {c.rank for c in board}
    not_on_board = sorted((r for r in RANKS if r not in board_ranks), key=lambda r: -RANKS.index(r))
    best_hole = max(hole, key=lambda c: c.rank_index)

    if not_on_board and best_hole.rank == not_on_board[0]:
        return "nuts_high", {}, 1.0
    if len(not_on_board) > 1 and best_hole.rank == not_on_board[1]:
        return "second_high", {}, 1.0
    if best_hole.rank_index >= RANKS.index("T"):
        return "weak_showdown", {}, 1.0
    return "trash", {}, 1.0


# --- Tirage ------------------------------------------------------------------

def _classify_draw(hole: list[Card], board: list[Card], texture: Texture) -> tuple[str | None, dict]:
    if len(board) >= 5:
        return None, {}  # river : plus de tirage possible

    from .texture import _rank_indices_with_ace_low, _WINDOWS

    suit_counts: dict[str, int] = {}
    for c in hole + board:
        suit_counts[c.suit] = suit_counts.get(c.suit, 0) + 1
    flush_suit = max(suit_counts, key=lambda s: suit_counts[s])
    has_flush_draw = suit_counts[flush_suit] == 4
    flush_high = max((c for c in hole if c.suit == flush_suit), key=lambda c: c.rank_index, default=None)

    combined = _rank_indices_with_ace_low(hole + board)
    hole_indices = {c.rank_index for c in hole}
    if 12 in hole_indices:
        hole_indices.add(13)
    missing: set[int] = set()
    for window in _WINDOWS:
        present = window & combined
        if len(present) == 4 and window & hole_indices:
            missing |= (window - combined)
    straight_shape = None
    if missing:
        straight_shape = "gutshot" if len(missing) == 1 else "open_ended"

    hole_ranks_idx = sorted((c.rank_index for c in hole), reverse=True)
    board_max = max((c.rank_index for c in board), default=-1)
    is_unpaired_hole = hole[0].rank != hole[1].rank
    both_overcards = is_unpaired_hole and hole_ranks_idx[1] > board_max

    combo = has_flush_draw and straight_shape is not None

    if combo:
        draw_id = "strong_draw" if (flush_high and flush_high.rank_index >= RANKS.index("J")) else "medium_strong_draw"
    elif has_flush_draw:
        r = flush_high.rank_index if flush_high else 0
        if r >= RANKS.index("J"):
            draw_id = "strong_draw"
        elif r >= RANKS.index("8"):
            draw_id = "medium_draw"
        elif r >= RANKS.index("6"):
            draw_id = "medium_weak_draw"
        else:
            draw_id = "weak_draw"
    elif straight_shape == "open_ended":
        draw_id = "medium_strong_draw" if texture.suit == "rainbow" else "medium_draw"
    elif straight_shape == "gutshot":
        draw_id = "medium_weak_draw" if both_overcards else "weak_draw"
    elif both_overcards:
        real_ranks = [RANKS.index(c.rank) + 2 for c in hole]
        if min(c.rank_index for c in hole) >= RANKS.index("Q"):
            draw_id = "strong_overcard_draw"
        elif sum(real_ranks) > 19:
            draw_id = "medium_overcard_draw"
        else:
            draw_id = "weak_overcard_draw"
    else:
        return None, {}

    sub = {
        "flush_draw": has_flush_draw,
        "straight_shape": straight_shape,
        "overcards": both_overcards,
    }
    return draw_id, sub


# --- Outs et blockers ---------------------------------------------------------

def _count_outs(hole: list[Card], board: list[Card]) -> int:
    current = evaluate(hole + board)
    known = set(hole) | set(board)
    remaining = [c for c in FULL_DECK if c not in known]
    return sum(1 for c in remaining if evaluate(hole + board + [c]) > current)


def _blockers(hole: list[Card], board: list[Card], texture: Texture) -> list[str]:
    blockers: list[str] = []
    if texture.suit in ("three_flush", "four_plus_flush"):
        suit_counts: dict[str, int] = {}
        for c in board:
            suit_counts[c.suit] = suit_counts.get(c.suit, 0) + 1
        flush_suit = max(suit_counts, key=lambda s: suit_counts[s])
        hero_suited = [c for c in hole if c.suit == flush_suit]
        if any(c.rank == "A" for c in hero_suited):
            blockers.append("bloque la couleur nut")
        elif not hero_suited:
            pass
    return blockers
