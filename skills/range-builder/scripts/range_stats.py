"""
Statistiques rapides sur une range écrite en notation standard (voir skill
range-notation).

v2 : réutilise `pokercoach.equity.parse_range` (installé en package, ou
localisé sans installation par pc_bootstrap.py sur claude.ai) au lieu d'un
parseur dupliqué — un seul endroit qui connaît la grammaire de range.

Usage :
    python3 range_stats.py "77+,ATs+,AJo+,KQs"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pc_bootstrap import ensure_pokercoach_on_path  # noqa: E402

ensure_pokercoach_on_path()

from pokercoach.equity import parse_range  # noqa: E402


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
