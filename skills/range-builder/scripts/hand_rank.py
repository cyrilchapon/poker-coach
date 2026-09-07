"""
Classe une liste de mains/groupes candidats par équité contre une range
adverse donnée, pour situer une main précise dans le "spectre" d'une range
de call/3bet et identifier les mains limitrophes (juste au-dessus / juste en
dessous du seuil).

Ce n'est PAS un solver : l'équité seule ignore playability, blockers
combinatoires fins, et jeu postflop réel. À utiliser comme repère de
calibration, pas comme verdict final — toujours le dire à l'utilisateur.

v2 : réutilise le moteur `pokercoach.equity` (installé en package, `pip
install -e .` à la racine du repo) au lieu d'une boucle Monte-Carlo dupliquée
sur treys — résultat exact par énumération quand le volume le permet.

Usage :
    python3 hand_rank.py "AJo,ATo,A9o,A8o,A7o,A6o,A5o,A4o" "77+,ATs+,AJo+,KQs,KQo"
"""
import argparse

from pokercoach.cards import parse_cards
from pokercoach.equity import equity as compute_equity


def rank_hands(candidates: list[str], opp_range: str, board_str: str = "", iterations: int = 20000):
    board = parse_cards(board_str.split(",")) if board_str else []
    results = []
    for token in candidates:
        r = compute_equity(token, opp_range, board=board, iterations=iterations)
        results.append((token, r.range1_equity))
    results.sort(key=lambda x: -x[1])
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("candidates", help="Groupes de mains séparés par des virgules, ex 'AJo,ATo,A9o,A8o'")
    p.add_argument("opp_range")
    p.add_argument("--board", default="", help="cartes séparées par des virgules, ex 'Ah,7c,2d'")
    p.add_argument("--iters", type=int, default=20000)
    p.add_argument("--threshold", type=float, default=None, help="Équité seuil (ex 0.38) à marquer sur le classement")
    args = p.parse_args()
    candidates = args.candidates.split(",")
    results = rank_hands(candidates, args.opp_range, args.board, args.iters)
    for h, eq in results:
        marker = ""
        if args.threshold is not None:
            marker = " <-- seuil ~ici" if abs(eq - args.threshold) < 0.015 else ""
        print(f"{h:6s} {eq * 100:5.1f}%{marker}")
