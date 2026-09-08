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


# --- Ouverture / isolation preflop ------------------------------------------
#
# Régression : `pc brief` tranchait "raise_or_call" en G1 sur une décision
# d'ouverture ou d'isolation preflop sans jamais chiffrer de taille -- alors
# que la taille n'a pas de gate dédié (ni G0-G4, ni un calcul d'équité) : ce
# n'est pas une décision "grise" qui a besoin d'un raisonnement LLM, juste
# une formule qu'il n'y avait pas encore de brique pour appliquer. Formule
# standard de régulier (pas issue d'un solveur, cf. le reste du module) :
# taille de base + 1bb par limpeur déjà dans le pot, majorée pour un
# archétype qui ne punit pas une mise plus grosse d'un fold supplémentaire
# (calling station/fish -- sur-tarifer la valeur, aucune raison de laisser
# de l'argent sur la table contre quelqu'un qui paie large de toute façon).
# Curseurs qualité/coût explicites (même statut que UNCERTAINTY_BAND dans
# gates.py ou ARCHETYPE_AGGRESSOR_FACTOR dans ranges/table.py) : valeurs de
# départ, à ajuster après usage réel, pas une vérité figée.
PREFLOP_OPEN_BASE_BB = 3.0
PREFLOP_OPEN_PER_LIMPER_BB = 1.0
PREFLOP_OPEN_EXPLOIT_BUMP_BB: dict[str | None, float] = {
    "fish": 1.0, "calling_station": 1.0,
}


def preflop_open_to(n_limpers: int = 0, *, villain_archetype: str | None = None) -> dict[str, Any]:
    """Taille d'ouverture/isolation preflop, en bb (montants du moteur déjà
    exprimés en bb, cf. state.py). ``n_limpers`` : nombre de limpeurs déjà
    dans le pot devant le héros (0 pour une RFI classique)."""
    if n_limpers < 0:
        raise ValueError("n_limpers doit être >= 0")
    limpers_bb = PREFLOP_OPEN_PER_LIMPER_BB * n_limpers
    exploit_bump_bb = PREFLOP_OPEN_EXPLOIT_BUMP_BB.get(villain_archetype, 0.0)
    raise_to_bb = PREFLOP_OPEN_BASE_BB + limpers_bb + exploit_bump_bb
    note = f"{PREFLOP_OPEN_BASE_BB:g}bb + {PREFLOP_OPEN_PER_LIMPER_BB:g}bb par limpeur ({n_limpers})"
    if exploit_bump_bb:
        note += f" + {exploit_bump_bb:g}bb (majoration exploitante vs {villain_archetype!r})"
    return {
        "raise_to_bb": round(raise_to_bb, 2),
        "base_bb": PREFLOP_OPEN_BASE_BB,
        "n_limpers": n_limpers,
        "limpers_bb": round(limpers_bb, 2),
        "exploit_bump_bb": round(exploit_bump_bb, 2),
        "note": note,
    }
