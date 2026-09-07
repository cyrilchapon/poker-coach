"""Couche B — sizing déterministe (%pot / montant de relance).

Repris tel quel de la v1 (``current-plugin/equity-engine/scripts/sizing.py``),
la formule elle-même n'avait pas de défaut identifié — seulement portée dans
le moteur au lieu de rester un script sandbox à part.

Convention canonique (cf. ``glossary.py``) :
- BET (première mise, rien à caller avant) : %pot = mise / pot AVANT la mise.
- RAISE (relance d'une mise existante) : %pot s'applique à la PORTION AU-DESSUS
  DU CALL, rapportée au pot après avoir callé (formule du "pot raise").
"""
from __future__ import annotations

from typing import Any


def bet_pct(bet: float, pot_before: float) -> float:
    return round(100 * bet / pot_before, 1)


def raise_to(pot_before_bet: float, bet_to_call: float, fraction: float) -> dict[str, Any]:
    pot_after_call = pot_before_bet + bet_to_call + bet_to_call
    raise_portion = fraction * pot_after_call
    total = bet_to_call + raise_portion
    return {
        "pot_after_call": round(pot_after_call, 2),
        "raise_portion": round(raise_portion, 2),
        "total_raise_to": round(total, 2),
    }
