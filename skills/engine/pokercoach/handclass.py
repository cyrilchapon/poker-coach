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
- **two_pair sur board apparié** : deux cas distincts.
  *(a)* Le héros apparie lui-même un rang du board alors que le board est
  déjà apparié (ex. K♠4♥ sur 9-9-4) : une des deux paires vient du board,
  la main est reclassée dans la famille paire simple (top_pair/second_pair/
  ...), suivant la note du YAML.
  *(b)* Le héros tient une paire SERVIE qui ne touche aucun rang du board,
  et c'est le BOARD qui est apparié (ex. TT sur J-9-9-3) : la main est une
  vraie double paire (la paire servie + la paire du board), classée
  ``two_pair`` avec ``made_sub.includes_board_pair = True``. Le BUDGET de
  cette sous-classe ne passe PAS par la table ``two_pair`` (calibrée pour
  une double paire sur board non apparié) : ``made_sub.strength_proxy``
  nomme la classe de la famille paire simple qui porte sa force réelle
  (position de la paire servie parmi les rangs du board : ``second_pair``,
  ``third_pair``, ``fourth_fifth_pair`` ou ``underpair``), et c'est elle que
  ``budget.py`` interroge — exactement la note du YAML ("force réelle ~
  top/middle paire"). Une paire servie SUPÉRIEURE à tout le board reste
  ``overpair`` (terminologie standard, budgets calibrés avec leur propre
  malus "board apparié") et n'est pas concernée.
- **Kicker buckets** (tptk/tpsk/k3/k4/k5/other) : calculés par position du
  kicker parmi les rangs de board restants + le kicker lui-même, triés
  descendant. Une bonne approximation, pas une reproduction exacte des
  seuils de l'annexe (non publiés à ce niveau de détail).
- **Paire servie ne touchant aucun rang du board** : placée par sa POSITION
  parmi les rangs du board (``pocket_pair_strength_proxy``), pas par un
  binaire au-dessus/en-dessous de la carte haute. Aucun rang au-dessus ->
  ``overpair`` ; TOUS au-dessus -> ``underpair`` (le sens littéral de la
  classe) ; entre les deux, elle joue comme la paire simple de rang
  équivalent -> ``second_pair`` / ``third_pair`` / ``fourth_fifth_pair``
  (TT sur J-9-6 bat le 9 et le 6 et ne perd que contre un valet : c'est une
  seconde paire, pas une paire "sous le board"). ``made_sub`` porte
  ``pocket_pair`` et ``board_ranks_above`` pour que ``budget.py`` prenne la
  colonne "paire servie" là où le YAML en distingue une (notamment la ligne
  ``three_bet_plus_special.pocket_pair``, "paire servie surclassée, seulement
  2 outs"), et pour que la gate G4 continue de traiter un set-mining raté
  comme une ligne de bluff.
- **Underpair** : classe ajoutée à la taxonomie PokerSkill à 15 classes
  (trop fréquente pour rester noyée dans ``weak_showdown``). Budgets ATT/DEF
  alignés sur ``weak_showdown`` faute de calibration dédiée, cf.
  ``budget.py``. Sur un board APPARIÉ, une paire servie ne relève jamais de
  cette classe : elle a réellement deux paires, cf. le point *(b)* ci-dessus.
- **Tirages** : classification simplifiée par seuils monotones (rang de la
  couleur, ouverture de la quinte, somme des rangs pour les surcartes) —
  pas de détection des combinaisons "backdoor". Les ``outs`` restent EXACTS
  (comptage réel par amélioration stricte du score, méthode déjà validée en
  v1 dans ``equity-engine/scripts/describe_hand.py``) — mais "exact" ne veut
  dire ici que "chaque carte comptée améliore RÉELLEMENT la catégorie du
  héros" (cf. ``_count_outs``), pas "chaque carte comptée gagne la main au
  showdown". Aucune décote pour un out mort (qui améliore le héros ET donne
  à un adversaire encore mieux — ex. la carte qui complète la quinte du
  héros mais apparie aussi la couleur adverse) ou empoisonné (qui complète
  une main moyenne battue par une main encore meilleure dans la range
  adverse). Ce jugement demande de raisonner sur la range adverse, hors de
  portée d'un comptage mécanique sur les seules cartes connues — à faire
  porter par le gate qualitatif (G5 / decision-factors), pas par ce module.
- **distance_to_boundary** n'est calculé (0.15 vs 1.0) que pour la famille
  paire simple, en comparant le kicker à la frontière de bucket la plus
  proche. Ailleurs, valeur par défaut 1.0 (pas de signal de proximité).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .cards import Card, RANKS
from .handeval import FULL_DECK, HAND_CATEGORIES, evaluate, handtype, is_nuts
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
    outs_winning: int | None
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
            "outs_winning": self.outs_winning,
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
    if len(board) < 5:
        outs, outs_winning = _count_outs(hole, board)
    else:
        outs, outs_winning = None, None
    blockers = _blockers(hole, board, texture)

    return HandClass(
        made=made, made_sub=made_sub, board_override=board_override,
        draw=draw, draw_sub=draw_sub, outs=outs, outs_winning=outs_winning,
        blockers=blockers, distance_to_boundary=distance,
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
        if hole[0].rank == hole[1].rank and not matched and paired_board:
            # Paire SERVIE qui ne touche aucun rang du board, sur un board
            # lui-même apparié (ex. TT sur J-9-9-3) : le héros a réellement
            # DEUX PAIRES (la sienne + celle du board), pas "une paire de
            # poche sous la carte haute du board". Le classifieur rendait
            # ``underpair`` ici -- doublement faux : la main n'est pas une
            # paire simple, et TT n'est pas sous TOUTES les cartes du board
            # (ce que `underpair` veut littéralement dire).
            hero_is_over = hole[0].rank_index > RANKS.index(_board_unique_ranks_sorted(board)[0])
            if not hero_is_over:
                # Une paire servie au-dessus de TOUT le board reste `overpair`
                # (terminologie standard, budgets dédiés) -- pas reclassée ici.
                return _classify_pocket_pair_over_paired_board(hole, board, texture)
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


# Position de la paire servie parmi les rangs du board -> classe de la famille
# "paire simple" qui porte sa force RÉELLE. Sert de `strength_proxy` pour une
# double paire dont une moitié vient du board (cf. docstring du module).
_PAIR_FAMILY_BY_RANKS_ABOVE = {1: "second_pair", 2: "third_pair"}


def pocket_pair_strength_proxy(pocket_rank: str, board_ranks_sorted: list[str],
                                board_rank_counts: dict[str, int] | None = None) -> tuple[str, int]:
    """(classe de force équivalente, nombre de rangs du board au-dessus).

    Mesure la seule chose qui décide de la force d'une paire servie face à
    une paire adverse : combien de rangs du board la surclassent. 0 ->
    ``overpair``, tous -> ``underpair`` (le sens littéral de la classe),
    entre les deux -> deuxième/troisième/quatrième paire.

    ``board_rank_counts`` traite le cas où le board fournit DÉJÀ deux paires
    (``double_paired``). La meilleure double paire se compose alors des deux
    plus hautes paires disponibles, board compris : une paire servie sous la
    PLUS BASSE des deux paires du board n'en fait pas partie et ne joue pas
    du tout -- 5-5 sur J-J-9-9-3 laisse le héros avec la double paire du
    board et un 5 pour simple kicker. Compter les rangs du board au-dessus
    d'elle lui prêterait la force d'une troisième paire (att 1.2 / def 1.9)
    qu'elle n'a à aucun moment ; ``underpair`` dit ce qu'elle est vraiment.
    Sur un board à UNE seule paire le cas ne se pose pas : la paire servie
    fournit toujours la seconde moitié, quel que soit son rang."""
    above = sum(1 for r in board_ranks_sorted if RANKS.index(r) > RANKS.index(pocket_rank))
    if board_rank_counts is not None:
        board_pairs = sorted((r for r, n in board_rank_counts.items() if n >= 2),
                             key=lambda r: -RANKS.index(r))
        if len(board_pairs) >= 2 and RANKS.index(pocket_rank) < RANKS.index(board_pairs[1]):
            return "underpair", above
    if above == 0:
        return "overpair", 0
    if above >= len(board_ranks_sorted):
        return "underpair", above
    return _PAIR_FAMILY_BY_RANKS_ABOVE.get(above, "fourth_fifth_pair"), above


def _classify_pocket_pair_over_paired_board(hole: list[Card], board: list[Card],
                                             texture: Texture) -> tuple[str, dict, float]:
    """Paire servie + paire du board = ``two_pair``, avec le proxy de force
    qui évite de lui prêter le budget d'une vraie double paire.

    ``att-def-budgets.yaml`` le dit déjà dans ses propres notes ("si le board
    est apparié, la double paire inclut la paire du board : force réelle ~
    top/middle paire") : la table ``two_pair`` est calibrée sur un board NON
    apparié, où les deux paires sont des cartes que l'adversaire n'a pas. Ici
    la moitié board est partagée par tout le monde -- seule la paire servie
    départage. ``strength_proxy`` nomme la classe qui porte cette force ;
    ``budget.py`` l'interroge à la place de la table ``two_pair``."""
    board_ranks_sorted = _board_unique_ranks_sorted(board)
    pocket_rank = hole[0].rank
    proxy, above = pocket_pair_strength_proxy(pocket_rank, board_ranks_sorted,
                                               texture.board_rank_counts)
    board_pair_rank = max(
        (r for r, n in texture.board_rank_counts.items() if n >= 2),
        key=lambda r: RANKS.index(r),
    )
    sub = {
        "includes_board_pair": True,
        "pocket_pair": True,
        "pocket_rank": pocket_rank,
        "board_pair_rank": board_pair_rank,
        "board_ranks_above": above,
        "strength_proxy": proxy,
        # Une paire servie "kicke" comme la meilleure carte possible : même
        # convention que `_classify_pair_family`, pour que le lookup de budget
        # du proxy (second_pair/third_pair...) tombe sur la bonne colonne.
        "kicker_bucket": "tptk",
    }
    return "two_pair", sub, 1.0


def _classify_pair_family(hole: list[Card], board: list[Card], texture: Texture) -> tuple[str, dict, float]:
    board_ranks_sorted = _board_unique_ranks_sorted(board)
    board_rank_counts = texture.board_rank_counts

    if hole[0].rank == hole[1].rank and board_rank_counts.get(hole[0].rank, 0) == 0:
        # Une paire servie qui ne touche pas le board se situe PAR SA POSITION
        # parmi les rangs du board, pas par un binaire au-dessus/en-dessous de
        # la carte haute : `overpair` (aucun rang au-dessus), `underpair` (tous
        # au-dessus -- le sens littéral de la classe), et entre les deux elle
        # joue comme la paire simple de rang équivalent (TT sur J-9-6 bat le 9
        # et le 6, ne perd que contre un valet : c'est une seconde paire, pas
        # une paire "sous le board"). `pocket_pair` reste dans `made_sub` pour
        # que le budget prenne la colonne "paire servie" là où le YAML en
        # distingue une, et pour que la gate G4 continue de traiter un
        # set-mining raté comme une ligne de bluff.
        proxy, above = pocket_pair_strength_proxy(hole[0].rank, board_ranks_sorted,
                                                   board_rank_counts)
        sub = {"pocket_rank": hole[0].rank, "pocket_pair": True, "board_ranks_above": above}
        if proxy not in ("overpair", "underpair"):
            sub["kicker_bucket"] = "tptk"  # une paire servie "kicke" au maximum
        return proxy, sub, 1.0

    matched = [c for c in hole if board_rank_counts.get(c.rank, 0) >= 1]
    if not matched:
        return "weak_showdown", {}, 1.0
    # Régression : quand les DEUX cartes du héros matchent chacune un rang du
    # board (board déjà apparié, cf. la note "two pair reclassée" plus haut),
    # `matched[0]` dépendait de l'ORDRE d'entrée des cartes en main (JSON) et
    # non de leur force réelle -- même main, classification différente selon
    # ["7h","5d"] vs ["5d","7h"]. On trie par position dans le board (la
    # meilleure paire, celle la plus haute au board) avant d'indexer.
    matched.sort(key=lambda c: board_ranks_sorted.index(c.rank))
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
    # Même grandeur que pour une paire servie (nombre de rangs du board
    # au-dessus) : c'est elle qui choisit la colonne `fourth`/`fifth` du budget.

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

    sub = {"kicker_bucket": kicker_bucket, "pocket_pair": is_pocket_pair,
           "board_ranks_above": position}
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
    flush_high = max((c for c in hole if c.suit == flush_suit), key=lambda c: c.rank_index, default=None)
    # Régression : sur un board déjà "four flush" (4 cartes de la même
    # couleur au board), `suit_counts[flush_suit]` atteint 4 par le board
    # SEUL -- même si le héros ne possède aucune carte de cette couleur. Sans
    # la garde sur `flush_high`, ça se traduisait par has_flush_draw=True
    # avec flush_high=None, qui retombait ensuite sur `r=0` -> "weak_draw" à
    # tort (le héros "joue le board", il n'a pas de tirage couleur perso).
    has_flush_draw = suit_counts[flush_suit] == 4 and flush_high is not None

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

def _neutral_filler(exclude_ranks: set[str], board: list[Card]) -> list[Card]:
    """Deux cartes de référence, choisies pour n'interagir avec RIEN de
    pertinent (rangs de ``exclude_ranks`` — main du héros, board, carte
    candidate — évités ; suits les moins présentes au board privilégiées
    pour ne pas fabriquer un tirage couleur accidentel ; rangs écartés l'un
    de l'autre pour ne pas fabriquer une quinte accidentelle). Sert à
    mesurer ce qu'une main GÉNÉRIQUE gagnerait de la carte candidate, pour
    isoler ce que le héros gagne SPÉCIFIQUEMENT (cf. _count_outs)."""
    board_suit_counts: dict[str, int] = {}
    for c in board:
        board_suit_counts[c.suit] = board_suit_counts.get(c.suit, 0) + 1
    suits_by_rarity = sorted({c.suit for c in FULL_DECK}, key=lambda s: board_suit_counts.get(s, 0))
    pool = [c for c in FULL_DECK if c.rank not in exclude_ranks]

    for s1 in suits_by_rarity:
        for s2 in suits_by_rarity:
            if s1 == s2:
                continue
            cands1 = sorted((c for c in pool if c.suit == s1), key=lambda c: c.rank_index)
            cands2 = sorted((c for c in pool if c.suit == s2), key=lambda c: c.rank_index)
            for a in cands1:
                for b in cands2:
                    if a.rank != b.rank and abs(a.rank_index - b.rank_index) >= 4:
                        return [a, b]
    return pool[:2]  # repli improbable (deck presque épuisé)


def _is_pure_board_pairing_for_a_made_hand(hole: list[Card], board: list[Card], candidate: Card) -> bool:
    """True si le héros a DÉJÀ une main faite de la famille "paire simple"
    (pas une paire de poche) et que ``candidate`` n'apparie qu'un rang déjà
    présent au board SANS toucher à l'une ou l'autre des deux cartes du
    héros -- un pur appariement de board, partagé mécaniquement par
    QUICONQUE tient une carte de ce rang, quel que soit son kicker.

    Round 3 de la régression outs : la comparaison à une main neutre
    (round 2) ne suffit pas ici, parce que la paire PRÉ-EXISTANTE du héros
    se propage mécaniquement dans la comparaison même quand la carte
    n'apporte rien de spécifique à LUI -- un 7 qui donne KK77 sur
    K♥7♣2♦ à un héros K♦Q♠ bat une main neutre (simple paire de 7), mais
    le ferait tout autant pour N'IMPORTE QUEL AUTRE porteur de roi, peu
    importe son kicker : ce n'est pas un avantage propre au héros. Une
    carte qui apparie au contraire l'une de ses DEUX cartes en main (ex.
    le dernier roi, donnant un brelan) reste comptée normalement : c'est
    une amélioration réellement spécifique à ce qu'il tient, même si
    d'autres porteurs du même rang en profiteraient identiquement -- au
    contraire du cas board-only, ici c'est SA carte qui s'apparie."""
    if hole[0].rank == hole[1].rank:
        return False  # paire de poche -- pas concerné par cette règle
    hole_ranks = {c.rank for c in hole}
    board_ranks = {c.rank for c in board}
    return candidate.rank in board_ranks and candidate.rank not in hole_ranks


def _is_pure_board_pairing(hole: list[Card], board: list[Card], candidate: Card) -> bool:
    """Généralisation de ``_is_pure_board_pairing_for_a_made_hand`` SANS
    l'exemption "paire de poche" : vrai si ``candidate`` apparie un rang déjà
    présent au board sans toucher NI L'UNE NI L'AUTRE des deux cartes du
    héros -- y compris quand ces deux cartes forment une paire de poche.

    Rapport de bug live-session #3 : sur 2♦2♠ / 6♠9♥4♥, ``_count_outs``
    compte 11 outs (2 brelan + 9 qui apparient un rang du board -> "deux
    paires"). Ce chiffre est correct pour la définition documentée de
    ``outs`` ("améliore la CATÉGORIE"), mais dangereux affiché à côté de
    ``pot_odds`` : une carte qui apparie le board reste tout aussi partagée
    par N'IMPORTE QUEL adversaire, paire de poche ou pas -- l'exemption
    accordée aux paires de poche dans ``_is_pure_board_pairing_for_a_made_hand``
    (nécessaire pour ne pas exclure le cas légitime où LE HÉROS pairait sa
    PROPRE carte) ne dit rien de la force relative de la main obtenue au
    showdown : une double paire avec un 2 en kicker perd face à quiconque a
    un meilleur kicker ou la paire du dessus. Utilisée uniquement pour
    ``outs_winning``, jamais pour ``outs`` (comportement historique inchangé,
    contractuel avec les tests round 1-3)."""
    hole_ranks = {c.rank for c in hole}
    board_ranks = {c.rank for c in board}
    return candidate.rank in board_ranks and candidate.rank not in hole_ranks


def _count_outs(hole: list[Card], board: list[Card]) -> tuple[int, int]:
    # Régression (round 1) : comparer le score BRUT (`evaluate(...) > current`)
    # comptait presque toutes les cartes restantes comme "out", parce
    # qu'ajouter une 6e/7e carte connue améliore quasi toujours légèrement le
    # meilleur-5-de-N (elle remplace le kicker le plus faible) même sans
    # changer la NATURE de la main. Comparer la CATÉGORIE (paire -> deux
    # paires, tirage -> couleur, etc.) a corrigé l'essentiel, mais pas tout :
    #
    # Régression (round 2) : une carte qui appareille le board SANS toucher
    # aux cartes du héros fait changer de catégorie N'IMPORTE QUELLE main
    # (paire de 2 au flop 2-5-9 : tout le monde a la paire) -- ce n'est pas
    # un avantage SPÉCIFIQUE au héros, donc pas un vrai out. Pour l'exclure
    # sans braquer les tirages couleur/quinte légitimes (une carte peut à la
    # fois appareiller un rang du board ET compléter la couleur du héros --
    # ex. le 9♠ qui complète une couleur sur un board 2♠5♠9♦ : exclure par
    # simple rang casserait ce cas), on compare la catégorie obtenue par le
    # héros à celle qu'obtiendrait une main NEUTRE (sans rapport avec le
    # héros ni le board) recevant la même carte : si le héros ne fait pas
    # MIEUX qu'une main neutre, ce n'est pas un out qui lui est propre.
    #
    # Régression (round 3) : pour une main DÉJÀ FAITE (ex. top pair), la
    # comparaison à une main neutre laisse quand même passer des cartes qui
    # n'apportent rien de spécifique au héros -- un 7 qui donne KK77 à un
    # héros top-pair-Kings bat une main neutre (simple paire de 7), mais
    # bat tout aussi bien N'IMPORTE QUEL AUTRE porteur de roi (même KK + un
    # 7 quelconque) : la paire pré-existante du héros se propage
    # mécaniquement dans la comparaison au neutre, peu importe si la carte
    # touche VRAIMENT ses cartes à lui. `_is_pure_board_pairing_for_a_made_hand`
    # exclut ce cas précis (apparie le board, pas les cartes du héros) tout
    # en laissant compter les cartes qui apparient réellement l'une de ses
    # deux cartes (ex. le dernier roi, qui donne un brelan -- amélioration
    # bien spécifique à ce qu'il tient, même si tout autre porteur de ce
    # rang en profiterait pareil).
    current_category_idx = HAND_CATEGORIES.index(handtype(evaluate(hole + board)))
    # La règle round-3 ne s'applique QUE si le héros a déjà une paire simple
    # -- sinon (ex. A♠K♠ sur un board 4-flush, pas encore de paire du tout)
    # elle exclurait à tort une carte qui complète un tirage couleur juste
    # parce que son rang coïncide avec un rang du board (exactement le
    # défaut de la règle naïve écartée au round 2 : cf. _is_pure_board_
    # pairing_for_a_made_hand, qui ne regarde QUE les rangs, pas les suits).
    hero_already_has_a_pair = current_category_idx == HAND_CATEGORIES.index("Pair")
    known = set(hole) | set(board)
    remaining = [c for c in FULL_DECK if c not in known]

    outs = 0
    outs_winning = 0
    for c in remaining:
        hero_idx = HAND_CATEGORIES.index(handtype(evaluate(hole + board + [c])))
        if hero_idx <= current_category_idx:
            continue
        if hero_already_has_a_pair and _is_pure_board_pairing_for_a_made_hand(hole, board, c):
            continue
        exclude_ranks = {card.rank for card in hole} | {card.rank for card in board} | {c.rank}
        neutral = _neutral_filler(exclude_ranks, board)
        neutral_idx = HAND_CATEGORIES.index(handtype(evaluate(neutral + board + [c])))
        if hero_idx <= neutral_idx:
            continue  # amélioration générique (ex. le board s'apparie) -- pas spécifique au héros
        outs += 1
        # `outs_winning` : plus strict que `outs` -- exclut EN PLUS le cas
        # d'une paire de poche qui n'améliore sa CATÉGORIE qu'en appariant un
        # rang du board (cf. `_is_pure_board_pairing`, docstring ci-dessus).
        # `outs` garde ces cartes (comportement historique), `outs_winning`
        # ne les compte plus : elles font gagner la classe de main, pas
        # nécessairement la main. Restreint à `hero_already_has_a_pair`
        # (même garde que ci-dessus) pour ne pas exclure à tort une carte
        # qui complète un tirage couleur/quinte dont le rang coïncide par
        # hasard avec un rang du board (cf. test_outs_keeps_a_flush_
        # completion_that_happens_to_share_a_board_rank).
        if hero_already_has_a_pair and _is_pure_board_pairing(hole, board, c):
            continue
        outs_winning += 1
    return outs, outs_winning


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
