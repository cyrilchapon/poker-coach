"""
Résolution DÉTERMINISTE d'un showdown — ne jamais déclarer un gagnant sans passer par ce script
(ou un appel équivalent direct à treys.Evaluator). Aucune évaluation "à l'œil".

Usage :
    python3 showdown.py "Qc9s6dQdKs" "Ac6h:Hero" "KdTd:HJ"
    (board, puis une ou plusieurs mains au format "cartes:nom")
"""
import argparse
from treys import Card, Evaluator

SUIT_MAP = {"♠": "s", "♥": "h", "♦": "d", "♣": "c",
            "s": "s", "h": "h", "d": "d", "c": "c"}


def normalize_cards(card_str):
    """Accepte indifféremment la notation lettres (Ah, Kc) ou Unicode (A♠, K♦),
    y compris mélangées ou séparées par des espaces, et renvoie la notation lettres
    concaténée sans espace attendue par treys (ex "AhKc")."""
    card_str = card_str.replace(" ", "")
    out = []
    i = 0
    while i < len(card_str):
        rank = card_str[i]
        suit_char = card_str[i + 1]
        out.append(rank + SUIT_MAP[suit_char])
        i += 2
    return "".join(out)



def resolve(board_str, hands):
    """hands: liste de (cards_str, name). Retourne liste triée (meilleure main en premier) avec le type de main."""
    evaluator = Evaluator()
    board_str = normalize_cards(board_str)
    board = [Card.new(board_str[i:i+2]) for i in range(0, len(board_str), 2)]
    results = []
    for cards_str, name in hands:
        cards_str = normalize_cards(cards_str)
        hole = [Card.new(cards_str[i:i+2]) for i in range(0, len(cards_str), 2)]
        score = evaluator.evaluate(board, hole)
        rank_class = evaluator.get_rank_class(score)
        results.append({
            "name": name,
            "cards": cards_str,
            "score": score,
            "hand_type": evaluator.class_to_string(rank_class),
        })
    results.sort(key=lambda r: r["score"])  # score plus bas = meilleure main
    best_score = results[0]["score"]
    for r in results:
        r["result"] = "win" if r["score"] == best_score else ("tie" if False else "lose")
    # gérer les égalités
    winners = [r for r in results if r["score"] == best_score]
    if len(winners) > 1:
        for r in results:
            r["result"] = "tie" if r["score"] == best_score else "lose"
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("board")
    p.add_argument("hands", nargs="+", help="format cartes:nom, ex Ac6h:Hero")
    args = p.parse_args()
    parsed = []
    for h in args.hands:
        cards, name = h.split(":")
        parsed.append((cards, name))
    for r in resolve(args.board, parsed):
        print(f"{r['name']:10s} {r['cards']:6s} {r['hand_type']:20s} {r['result']}")
