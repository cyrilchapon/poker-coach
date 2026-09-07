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


def g2_budget_decisive(*, envisaged_action: str, viable_actions: list[str],
                        att_remaining: float | None = None,
                        facing_bet: bool = True) -> GateDecision | None:
    """Le budget ATT/DEF tranche seul, dans un sens ou dans l'autre — pas de
    raisonnement nécessaire dans les deux cas :

    - **Épuisé** : ``envisaged_action`` ("call"/"raise" face à une mise,
      "bet" sinon) n'est plus dans ``viable_actions`` -> repli forcé. Sans
      mise à suivre, le repli est TOUJOURS "check" (gratuit, jamais gaté),
      jamais "fold" qui n'a pas de sens ici.
    - **Illimité** (``att_remaining == inf``, réservé à la classe "nuts" —
      curseur volontairement strict, cf. le seuil de gate à ajuster par
      l'utilisateur) sans mise à suivre : miser est un verdict évident, pas
      la peine de calculer des bornes d'équité qui n'existent pas de toute
      façon (pas de seuil de rentabilité sans mise à comparer) ni
      d'escalader en G5 comme si c'était une décision grise.
    """
    if not facing_bet and att_remaining == float("inf") and "bet" in viable_actions:
        return GateDecision(gate="G2", verdict="bet", confidence="forced")
    if envisaged_action not in ("raise", "call", "bet") or envisaged_action in viable_actions:
        return None
    if not facing_bet:
        # Pas de mise à comparer -> pas de seuil de rentabilité -> G3 ne
        # peut structurellement pas contredire un repli "check" (toujours
        # gratuit). Confiance "forced" légitime, rien à dégrader ici.
        return GateDecision(gate="G2", verdict="check", confidence="forced")
    fallback = "call" if "call" in viable_actions else "fold"
    # Régression (revue automatisée) : ce repli s'annonçait "forced" alors
    # que c'est une heuristique tabulée (budget ATT/DEF), pas une déduction
    # déterministe comme G0/G1 -- contrairement au cas "check" ci-dessus,
    # une équité RÉELLEMENT calculée (G3) peut la contredire (repro
    # vérifiée : ce repli rendait "fold" sur un spot où l'équité calculée
    # donnait 52-64% contre 30% requis). "strong" plutôt que "forced" :
    # honnête sur le statut épistémique sans changer la verbosité ni
    # forcer un calcul de G3 systématique (qui viderait la cascade de son
    # intérêt coût/qualité) -- voir brief.py pour le flag de désaccord
    # exposé quand G3 est calculé quand même (``--depth full``).
    return GateDecision(gate="G2", verdict=fallback, confidence="strong")


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
