"""
Statistiques rapides sur une range écrite en notation standard (voir skill range-notation).
Réutilise le même parseur que equity-engine/scripts/equity.py (dupliqué ici volontairement,
pour que la skill reste autonome/empaquetable séparément).

Usage :
    python3 range_stats.py "77+,ATs+,AJo+,KQs"
"""
import argparse

RANKS = "23456789TJQKA"


def parse_range(range_str):
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


def combo_count(c):
    if len(c) == 2:
        return 6
    return 4 if c[2] == 's' else 12


def range_stats(range_str):
    combos = parse_range(range_str)
    total_combos = sum(combo_count(c) for c in combos)
    return {
        "distinct_hands": len(combos),
        "total_combos": total_combos,
        "pct_of_1326": round(100 * total_combos / 1326, 1),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("range")
    args = p.parse_args()
    print(range_stats(args.range))
