"""
Calcul de sizing DÉTERMINISTE — jamais de calcul de tête pour un %pot ou une taille de relance.

Convention canonique retenue (cohérente avec la littérature standard, cf. gto-glossary) :
- BET (première mise sur une rue, rien à callée avant) : %pot = mise / pot AVANT cette mise.
- RAISE (relance d'une mise existante) : %pot s'applique à la PORTION AU-DESSUS DU CALL,
  rapportée au pot après avoir callé — formule classique du "pot raise" :
      pot_after_call = pot_before_bet_being_raised + bet_to_call + call_amount
      raise_portion = fraction * pot_after_call
      total_raise_to = call_amount + raise_portion   (montant total à annoncer, en plus de ce qu'on a déjà misé cette rue s'il y a lieu)

Usage :
    python3 sizing.py bet-pct --bet 10 --pot-before 15.5
    python3 sizing.py raise-to --pot-before-bet 6.5 --bet-to-call 3.5 --fraction 1.0
"""
import argparse


def bet_pct(bet, pot_before):
    return round(100 * bet / pot_before, 1)


def raise_to(pot_before_bet, bet_to_call, fraction):
    pot_after_call = pot_before_bet + bet_to_call + bet_to_call
    raise_portion = fraction * pot_after_call
    total = bet_to_call + raise_portion
    return {
        "pot_after_call": round(pot_after_call, 2),
        "raise_portion": round(raise_portion, 2),
        "total_raise_to": round(total, 2),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("bet-pct", help="Calculer le %pot d'une mise simple (pas une relance)")
    p1.add_argument("--bet", type=float, required=True)
    p1.add_argument("--pot-before", type=float, required=True)

    p2 = sub.add_parser("raise-to", help="Calculer le montant total d'une relance pour une fraction de pot donnée")
    p2.add_argument("--pot-before-bet", type=float, required=True, help="Pot avant la mise adverse qu'on relance")
    p2.add_argument("--bet-to-call", type=float, required=True, help="Montant de la mise adverse à caller")
    p2.add_argument("--fraction", type=float, required=True, help="1.0 = pot raise plein, 0.5 = demi-pot, etc.")

    args = p.parse_args()
    if args.cmd == "bet-pct":
        print(f"{bet_pct(args.bet, args.pot_before)}% du pot")
    elif args.cmd == "raise-to":
        r = raise_to(args.pot_before_bet, args.bet_to_call, args.fraction)
        print(f"pot après call: {r['pot_after_call']} | portion de relance: {r['raise_portion']} | relancer à (total): {r['total_raise_to']}")
