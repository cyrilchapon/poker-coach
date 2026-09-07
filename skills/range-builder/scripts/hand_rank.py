"""
Classe une liste de mains candidates par équité contre une range adverse donnée,
pour situer une main précise dans le "spectre" d'une range de call/3bet et
identifier les mains limitrophes (juste au-dessus / juste en dessous du seuil).

Ce n'est PAS un solver : l'équité seule ignore playability, blockers combinatoires
fins, et jeu postflop réel. À utiliser comme repère de calibration, pas comme
verdict final — toujours le dire à l'utilisateur.

Usage :
    python3 hand_rank.py "AJo,ATo,A9o,A8o,A7o,A6o,A5o,A4o" "77+,ATs+,AJo+,KQs,KQo" --iters 8000
"""
import argparse
import random
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "equity-engine", "scripts"))
from equity import parse_range, combo_to_hands
from treys import Card, Deck, Evaluator


def equity_vs_range(hand_str, range_str, board_str="", iterations=8000):
    evaluator = Evaluator()
    board = [Card.new(c) for c in [board_str[i:i+2] for i in range(0, len(board_str), 2)]] if board_str else []
    hand_combos = [h for c in parse_range(hand_str) for h in combo_to_hands(c)]
    range_combos = [h for c in parse_range(range_str) for h in combo_to_hands(c)]

    wins = ties = total = 0
    for _ in range(iterations):
        h1 = random.choice(hand_combos)
        h2 = random.choice(range_combos)
        used = set(h1 + h2 + board)
        if len(used) != len(h1) + len(h2) + len(board):
            continue
        deck = [c for c in Deck().cards if c not in used]
        random.shuffle(deck)
        full_board = board + deck[:5 - len(board)]
        s1 = evaluator.evaluate(full_board, h1)
        s2 = evaluator.evaluate(full_board, h2)
        if s1 < s2:
            wins += 1
        elif s1 == s2:
            ties += 1
        total += 1
    return round((wins + ties / 2) / total, 4) if total else None


def rank_hands(candidates, opp_range, board_str="", iterations=8000, threshold=None, target=None):
    results = []
    for h in candidates:
        eq = equity_vs_range(h, opp_range, board_str, iterations)
        results.append((h, eq))
    results.sort(key=lambda x: -x[1])
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("candidates", help="Liste de mains séparées par des virgules, ex 'AJo,ATo,A9o,A8o'")
    p.add_argument("opp_range")
    p.add_argument("--board", default="")
    p.add_argument("--iters", type=int, default=8000)
    p.add_argument("--threshold", type=float, default=None, help="Équité seuil (ex 0.38) à marquer sur le classement")
    args = p.parse_args()
    candidates = args.candidates.split(",")
    results = rank_hands(candidates, args.opp_range, args.board, args.iters)
    for h, eq in results:
        marker = ""
        if args.threshold is not None:
            marker = " <-- seuil ~ici" if eq is not None and abs(eq - args.threshold) < 0.015 else ""
        print(f"{h:6s} {eq*100:5.1f}%{marker}")
