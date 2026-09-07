"""
Moteur d'équité NLHE — range vs range ou main vs range.
Dépendance : pip install treys --break-system-packages (une seule fois par session sandbox).

Usage typique (appelé via bash_tool, pas en import direct par l'utilisateur) :
    python3 equity.py "QQ+,AKs,AKo" "22-99,ATs-AJs,KQs" --board "" --iters 20000
"""
import random
import argparse
from treys import Card, Deck, Evaluator

SUIT_MAP = {"♠": "s", "♥": "h", "♦": "d", "♣": "c",
            "s": "s", "h": "h", "d": "d", "c": "c"}


def normalize_cards(card_str):
    """Accepte indifféremment la notation lettres (Ah, Kc) ou Unicode (A♠, K♦) pour
    --board/--dead, y compris mélangées, et renvoie la notation lettres attendue par treys."""
    if not card_str:
        return card_str
    card_str = card_str.replace(" ", "")
    out = []
    i = 0
    while i < len(card_str):
        rank = card_str[i]
        suit_char = card_str[i + 1]
        out.append(rank + SUIT_MAP[suit_char])
        i += 2
    return "".join(out)


RANKS = "23456789TJQKA"


def parse_range(range_str):
    """Notation supportée : AA, KK+, 22-77, AKs, ATo+, JTs-98s, séparées par des virgules.
    Non supporté pour l'instant : pondération @xx%, mélange explicite pair+suited dans un seul token."""
    combos = set()

    def add_pair(r):
        combos.add((r, r))

    def add_suited(r1, r2):
        combos.add((r1, r2, 's'))

    def add_offsuit(r1, r2):
        combos.add((r1, r2, 'o'))

    for token in range_str.replace(" ", "").split(","):
        if not token:
            continue
        if "-" in token and "+" not in token:
            lo, hi = token.split("-")
            if len(lo) == 2 and lo[0] == lo[1]:
                i_lo, i_hi = RANKS.index(lo[0]), RANKS.index(hi[0])
                for i in range(i_lo, i_hi + 1):
                    add_pair(RANKS[i])
            else:
                suit = hi[2]
                i_lo_high, i_lo_low = RANKS.index(lo[0]), RANKS.index(lo[1])
                i_hi_high, i_hi_low = RANKS.index(hi[0]), RANKS.index(hi[1])
                gap = i_lo_high - i_lo_low
                for i in range(i_hi_high, i_lo_high + 1):
                    r_high, r_low = RANKS[i], RANKS[i - gap]
                    (add_suited if suit == 's' else add_offsuit)(r_high, r_low)
            continue

        plus = token.endswith("+")
        base = token[:-1] if plus else token
        if len(base) == 2 and base[0] == base[1]:
            start_idx = RANKS.index(base[0])
            if plus:
                for i in range(start_idx, len(RANKS)):
                    add_pair(RANKS[i])
            else:
                add_pair(base[0])
        elif len(base) == 3:
            r1, r2, suit = base[0], base[1], base[2]
            i1, i2 = RANKS.index(r1), RANKS.index(r2)
            if plus:
                for i in range(i2, i1):
                    (add_suited if suit == 's' else add_offsuit)(r1, RANKS[i])
            else:
                (add_suited if suit == 's' else add_offsuit)(r1, r2)
    return combos


def combo_to_hands(combo):
    suits = "shdc"
    hands = []
    if len(combo) == 2:
        r = combo[0]
        for i in range(4):
            for j in range(i + 1, 4):
                hands.append([Card.new(r + suits[i]), Card.new(r + suits[j])])
    else:
        r1, r2, kind = combo
        if kind == 's':
            for s in suits:
                hands.append([Card.new(r1 + s), Card.new(r2 + s)])
        else:
            for s1 in suits:
                for s2 in suits:
                    if s1 != s2:
                        hands.append([Card.new(r1 + s1), Card.new(r2 + s2)])
    return hands


def equity_range_vs_range(range1_str, range2_str, board_str="", dead_str="", iterations=20000):
    evaluator = Evaluator()
    board_str = normalize_cards(board_str)
    dead_str = normalize_cards(dead_str)
    board = [Card.new(c) for c in [board_str[i:i + 2] for i in range(0, len(board_str), 2)]] if board_str else []
    dead = [Card.new(c) for c in [dead_str[i:i + 2] for i in range(0, len(dead_str), 2)]] if dead_str else []

    range1_combos = [h for c in parse_range(range1_str) for h in combo_to_hands(c)]
    range2_combos = [h for c in parse_range(range2_str) for h in combo_to_hands(c)]

    wins1 = wins2 = ties = total = 0
    for _ in range(iterations):
        h1 = random.choice(range1_combos)
        h2 = random.choice(range2_combos)
        used = set(h1 + h2 + board + dead)
        if len(used) != len(h1) + len(h2) + len(board) + len(dead):
            continue
        deck = [c for c in Deck().cards if c not in used]
        random.shuffle(deck)
        full_board = board + deck[:5 - len(board)]
        s1 = evaluator.evaluate(full_board, h1)
        s2 = evaluator.evaluate(full_board, h2)
        if s1 < s2:
            wins1 += 1
        elif s2 < s1:
            wins2 += 1
        else:
            ties += 1
        total += 1

    return {
        "range1_equity": round((wins1 + ties / 2) / total, 4),
        "range2_equity": round((wins2 + ties / 2) / total, 4),
        "iterations_used": total,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("range1")
    p.add_argument("range2")
    p.add_argument("--board", default="")
    p.add_argument("--dead", default="")
    p.add_argument("--iters", type=int, default=20000)
    args = p.parse_args()
    print(equity_range_vs_range(args.range1, args.range2, args.board, args.dead, args.iters))
