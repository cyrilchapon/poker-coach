"""Couche C — la cascade de gates : chaque niveau peut clore la décision sans
raisonnement LLM. Voir docs/brief/references/02-architecture-v2.md.

Curseurs volontairement isolés en constantes de module (§8 du brief : "la
valeur exacte des seuils de gate... c'est un curseur qualité/coût qui
appartient à l'utilisateur"). Valeurs de départ choisies pour ce lancement
v2.0, à ajuster après usage réel — pas une vérité figée.
"""
from __future__ import annotations

from dataclasses import dataclass

# Largeur de la bande d'incertitude autour du seuil de rentabilité, en
# fraction d'équité (G3). En dehors de cette bande, les deux bornes tombent
# du même côté -> verdict forcé. Dedans -> escalade G5.
UNCERTAINTY_BAND = 0.04

GATES = ("G0", "G1", "G2", "G3", "G4", "G5")
VERBOSITY_BY_GATE = {
    "G0": "one_line", "G1": "verdict_plus_reason", "G2": "verdict_plus_reason",
    "G3": "verdict_plus_number", "G4": "verdict_plus_exploit_reason", "G5": "full",
}


@dataclass
class GateDecision:
    gate: str
    verdict: str | None
    confidence: str  # forced | strong | grey
    escalate_reason: str | None = None

    @property
    def verbosity(self) -> str:
        return VERBOSITY_BY_GATE[self.gate]


def g0_forced(*, hero_is_allin: bool, only_action: str | None) -> GateDecision | None:
    if hero_is_allin:
        return GateDecision(gate="G0", verdict=None, confidence="forced",
                             escalate_reason=None)
    if only_action is not None:
        return GateDecision(gate="G0", verdict=only_action, confidence="forced")
    return None


def g1_preflop_range(*, in_range: bool | None, verdict_if_in_range: str = "raise_or_call") -> GateDecision | None:
    """``verdict_if_in_range`` : "raise_or_call" pour une range simple, ou
    "raise"/"limp" pour un scénario à stratégie mixte (SB vs BB) où
    l'appelant a déjà déterminé dans quel bucket tombe la main du héros."""
    if in_range is None:
        return None
    if in_range:
        return GateDecision(gate="G1", verdict=verdict_if_in_range, confidence="forced")
    return GateDecision(gate="G1", verdict="fold", confidence="forced")


def g2_budget_exhausted(*, envisaged_action: str, viable_actions: list[str]) -> GateDecision | None:
    if envisaged_action in ("raise", "call") and envisaged_action not in viable_actions:
        fallback = "call" if "call" in viable_actions else "fold"
        return GateDecision(gate="G2", verdict=fallback, confidence="forced")
    return None


def g3_equity_bounds(*, lower_bound: float, upper_bound: float, threshold: float) -> GateDecision | None:
    if lower_bound >= threshold + UNCERTAINTY_BAND and upper_bound >= threshold + UNCERTAINTY_BAND:
        return GateDecision(gate="G3", verdict="call_or_raise", confidence="strong")
    if lower_bound <= threshold - UNCERTAINTY_BAND and upper_bound <= threshold - UNCERTAINTY_BAND:
        return GateDecision(gate="G3", verdict="fold", confidence="strong")
    return None  # le seuil retombe dans la bande -> escalade G5


def g4_exploit(*, exploit_notes: list[str]) -> GateDecision | None:
    if any("G4" in n for n in exploit_notes):
        verdict = "fold" if any("bluff_multi_street_blocked" in n for n in exploit_notes) else None
        return GateDecision(gate="G4", verdict=verdict, confidence="strong")
    return None


def g5_grey_zone(*, escalate_reason: str) -> GateDecision:
    return GateDecision(gate="G5", verdict=None, confidence="grey", escalate_reason=escalate_reason)
