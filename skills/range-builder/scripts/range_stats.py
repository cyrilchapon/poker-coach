"""
Statistiques rapides sur une range écrite en notation standard (voir skill
range-notation).

v2 : réutilise `pokercoach.equity.parse_range` (installé en package) au lieu
d'un parseur dupliqué — un seul endroit qui connaît la grammaire de range.

Usage :
    python3 range_stats.py "77+,ATs+,AJo+,KQs"
"""
import argparse

from pokercoach.equity import parse_range


def range_stats(range_str: str) -> dict:
    combos = parse_range(range_str)
    total_weighted = sum(c.weight for c in combos)
    return {
        "distinct_combos": len(combos),
        "total_weighted_combos": round(total_weighted, 2),
        "pct_of_1326": round(100 * total_weighted / 1326, 1),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("range")
    args = p.parse_args()
    print(range_stats(args.range))
