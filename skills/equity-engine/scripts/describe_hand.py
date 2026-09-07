"""
Décrit une main (type de main exact) et calcule les outs réels — DÉTERMINISTE, via treys.
Obligatoire pour TOUTE affirmation sur la force d'une main ou le nombre d'outs, à n'importe
quelle rue (pas seulement au showdown — showdown.py ne sert qu'à départager un abattage complet).

Deux erreurs réelles constatées en session sans cet outil :
- annoncer un tirage quinte avec seulement 4 cartes consécutives (il en faut 5)
- annoncer "deux paires" alors que la seule paire venait du board (main = une paire, kickers)

Usage :
    python3 describe_hand.py "9d9h" "JsQs7hQc"                    # décrire la main actuelle
    python3 describe_hand.py "9d9h" "JsQs7h" --outs                # lister les outs au tirage (turn à venir)
"""
import argparse
import sys
import os
from treys import Card, Deck, Evaluator

sys.path.insert(0, os.path.dirname(__file__))
from equity import normalize_cards  # réutilise le même convertisseur Unicode/lettres


def describe(hole_str, board_str):
    hole_str = normalize_cards(hole_str)
    board_str = normalize_cards(board_str)
    hole = [Card.new(hole_str[i:i+2]) for i in range(0, len(hole_str), 2)]
    board = [Card.new(board_str[i:i+2]) for i in range(0, len(board_str), 2)]
    evaluator = Evaluator()
    score = evaluator.evaluate(board, hole)
    rank_class = evaluator.get_rank_class(score)
    return {
        "hand_type": evaluator.class_to_string(rank_class),
        "score": score,
        "board_len": len(board),
    }


def compute_outs(hole_str, board_str, dead_str=""):
    """Énumère toutes les cartes restantes possibles et compte celles qui améliorent
    strictement la classe de main (ex passer de 'paire' à 'brelan' ou mieux).
    Ne fonctionne que si le board a 3 ou 4 cartes (flop ou turn) — pas de outs à énumérer
    une fois la river tombée (aucune carte à venir)."""
    hole_str = normalize_cards(hole_str)
    board_str = normalize_cards(board_str)
    dead_str = normalize_cards(dead_str) if dead_str else ""

    hole = [Card.new(hole_str[i:i+2]) for i in range(0, len(hole_str), 2)]
    board = [Card.new(board_str[i:i+2]) for i in range(0, len(board_str), 2)]
    dead = [Card.new(dead_str[i:i+2]) for i in range(0, len(dead_str), 2)] if dead_str else []

    if len(board) not in (3, 4):
        raise ValueError(f"compute_outs nécessite un board de 3 (flop) ou 4 (turn) cartes, reçu {len(board)}.")

    evaluator = Evaluator()
    current_score = evaluator.evaluate(board, hole)
    current_class = evaluator.get_rank_class(current_score)

    used = set(hole + board + dead)
    remaining = [c for c in Deck().cards if c not in used]

    improving = []
    for c in remaining:
        new_board = board + [c]
        new_score = evaluator.evaluate(new_board, hole)
        if new_score < current_score:  # score plus bas = main meilleure
            improving.append(c)

    return {
        "current_hand": evaluator.class_to_string(current_class),
        "outs_count": len(improving),
        "outs_cards": [Card.int_to_str(c) for c in improving],
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("hole")
    p.add_argument("board")
    p.add_argument("--dead", default="")
    p.add_argument("--outs", action="store_true", help="Calculer les outs réels plutôt que juste décrire la main")
    args = p.parse_args()

    if args.outs:
        r = compute_outs(args.hole, args.board, args.dead)
        print(f"Main actuelle : {r['current_hand']}")
        print(f"Outs réels : {r['outs_count']} → {', '.join(r['outs_cards'])}")
    else:
        r = describe(args.hole, args.board)
        print(f"Type de main : {r['hand_type']}")
