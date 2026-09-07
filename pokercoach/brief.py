"""Couche C — ``pc brief`` : orchestration de tout ce qui précède en un seul
appel, avec la cascade de gates. Voir docs/brief/references/02-architecture-v2.md
pour la forme de sortie visée (reproduite ici, avec des sections omises quand
non pertinentes — ex. pas de ``hand``/``texture``/``budget`` préflop).

Ranges adverses de référence pour les bornes G3 : deux ranges génériques
FIXES (large / étroite), pas encore dérivées de l'historique réel de la main
adverse combo par combo (ça, c'est ``ranges.narrow``, utilisable séparément
via ``pc narrow``). Amélioration continue documentée, pas un blocage pour la
v2.0 — cf. l'éthique d'honnêteté du brief sur la précision des ranges.
"""
from __future__ import annotations

from typing import Any

from . import actionline, budget as budget_mod, gates, handclass, texture as texture_mod
from .cards import parse_cards
from .equity import equity as compute_equity
from .ranges import table as range_table
from .state import HandState, derive, validate_and_load

WIDE_VILLAIN_RANGE = ("22+,A2s+,K2s+,Q4s+,J6s+,T6s+,96s+,86s+,75s+,64s+,53s+,"
                      "A2o+,K8o+,Q9o+,J9o+,T9o")
NARROW_VILLAIN_RANGE = "22+,A9s+,KTs+,QTs+,JTs,T9s,98s,ATo+,KQo"


def compute(raw: dict[str, Any], *, villain_archetype: str | None = None) -> dict[str, Any]:
    state = validate_and_load(raw)
    d = derive(state)
    hero_seat = state.hero_seat
    to_act = state.to_act
    hero_active_seat = state.seats[to_act]

    out: dict[str, Any] = {"state": d.to_json()}

    # --- G0 : décision triviale -------------------------------------------
    only_action = "check_or_forced" if d.players_active <= 1 else None
    g0 = gates.g0_forced(hero_is_allin=hero_active_seat.status == "allin", only_action=only_action)
    if g0:
        return _finish(out, g0, escalate_reason=None)

    is_preflop = state.street == "preflop"

    line_json = actionline.to_json(state)
    out["line"] = line_json
    role = line_json["role"]
    pot_type = line_json["pot_type"]

    # --- Préflop : lookup de range -------------------------------------------
    if is_preflop:
        key = range_table.derive_key(state, to_act)
        in_range: bool | None = None
        range_json = None
        if role in ("aggressor", "probe") and pot_type in ("srp",):
            entry = range_table.rfi(key)
            range_json = entry.to_json()
            hero_cards = state.seats[to_act].cards
            if entry.range and hero_cards:
                from .equity import parse_range
                combos = {frozenset((c.rank, c.suit) for c in wc.combo) for wc in parse_range(entry.range)}
                hero_key = frozenset((c.rank, c.suit) for c in hero_cards)
                in_range = hero_key in combos
        out["range"] = range_json
        g1 = gates.g1_preflop_range(in_range=in_range)
        if g1:
            return _finish(out, g1, escalate_reason=None)
        # Préflop hors G0/G1 : zone grise, pas de moteur de budget préflop en v2.0.
        return _finish(out, gates.g5_grey_zone(
            escalate_reason="préflop hors plafond RFI tabulé — jugement du coach requis"),
            escalate_reason="préflop hors plafond RFI tabulé — jugement du coach requis")

    # --- Postflop -------------------------------------------------------------
    hero_cards = state.seats[hero_seat].cards
    if hero_cards is None:
        raise ValueError("hero doit avoir ses deux cartes connues pour un brief postflop")

    hc = handclass.classify(hero_cards, state.board)
    texture = texture_mod.classify(state.board)
    out["hand"] = hc.to_json()
    out["texture"] = texture.to_json()

    replay = actionline.replay_pressure(state)
    b = budget_mod.compute(
        hc, texture, pot_type=pot_type, street=state.street,
        n_opponents_active=max(0, d.players_active - 1),
        pressure_spent=replay.spent.get(to_act, 0.0),
        pressure_faced=replay.faced.get(to_act, 0.0),
        villain_archetype=villain_archetype,
    )
    out["budget"] = b.to_json()
    if villain_archetype:
        out["exploit"] = {"archetype": villain_archetype,
                           "flags": [n for n in b.notes if n.startswith("G4")]}

    envisaged = "call" if d.to_call > 0 else "raise"
    g2 = gates.g2_budget_exhausted(envisaged_action=envisaged, viable_actions=b.viable_actions)
    if g2:
        return _finish(out, g2, escalate_reason=None)

    g4 = gates.g4_exploit(exploit_notes=b.notes)
    if g4:
        return _finish(out, g4, escalate_reason=None)

    # --- G3 : bornes d'équité (seulement si un seuil de rentabilité existe) --
    if d.to_call > 0 and d.pot_odds is not None:
        hero_combo = f"{hero_cards[0]}{hero_cards[1]}"
        eq_wide = compute_equity(hero_combo, WIDE_VILLAIN_RANGE, board=state.board).range1_equity
        eq_narrow = compute_equity(hero_combo, NARROW_VILLAIN_RANGE, board=state.board).range1_equity
        lower, upper = min(eq_wide, eq_narrow), max(eq_wide, eq_narrow)
        out["equity"] = {
            "vs_range": "wide/narrow générique (pas encore narrowée par l'historique réel)",
            "lower_bound": round(lower, 4), "upper_bound": round(upper, 4),
            "threshold": round(d.pot_odds, 4), "method": "enumeration_or_monte_carlo",
        }
        g3 = gates.g3_equity_bounds(lower_bound=lower, upper_bound=upper, threshold=d.pot_odds)
        if g3:
            return _finish(out, g3, escalate_reason=None)
        return _finish(out, gates.g5_grey_zone(
            escalate_reason=f"équité [{lower:.2f}, {upper:.2f}] chevauche le seuil {d.pot_odds:.2f}"),
            escalate_reason=f"équité [{lower:.2f}, {upper:.2f}] chevauche le seuil {d.pot_odds:.2f}")

    return _finish(out, gates.g5_grey_zone(
        escalate_reason="pas de mise à comparer (check/bet) — jugement du coach requis"),
        escalate_reason="pas de mise à comparer (check/bet) — jugement du coach requis")


def _finish(out: dict[str, Any], decision: "gates.GateDecision", *, escalate_reason: str | None) -> dict[str, Any]:
    out["gate"] = decision.gate
    out["verdict"] = decision.verdict
    out["confidence"] = decision.confidence
    out["verbosity"] = decision.verbosity
    out["escalate_reason"] = decision.escalate_reason
    return out
