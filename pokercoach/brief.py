"""Couche C — ``pc brief`` : orchestration de tout ce qui précède en un seul
appel, avec la cascade de gates. Voir docs/brief/references/02-architecture-v2.md
pour la forme de sortie visée (reproduite ici, avec des sections omises quand
non pertinentes — ex. pas de ``hand``/``texture``/``budget`` préflop).

Ranges adverses pour les bornes G3 : deux SEEDS génériques (large / étroite),
ensuite RÉELLEMENT rejouées à travers l'historique d'actions du siège adverse
le plus pertinent, rue par rue, via ``ranges.narrow`` (le même mécanisme
qu'expose ``pc narrow`` séparément) — pas juste les seeds brutes. Les seeds
elles-mêmes restent une approximation documentée (pas encore dérivées de la
position/l'archétype adverse comme le prévoit l'architecture) ; c'est le
narrowing par l'historique réel qui est maintenant réel, pas approximé.

Escalade de profondeur à la demande (``force_full``) : la cascade de gates
tranche toujours le verdict normalement (aucun changement de décision), mais
quand ``force_full=True`` les sections de détail (ranges narrowées, bornes
d'équité, budget) sont calculées et incluses même si un gate précoce (G0-G2,
G4) a déjà tranché, et ``verbosity`` passe à ``"full"``. Permet à
``live-session`` de répondre à "on peut voir les ranges exactes ?" sans
changer le verdict déjà rendu.
"""
from __future__ import annotations

from typing import Any

from . import actionline, budget as budget_mod, gates, handclass, texture as texture_mod
from .cards import Card
from .equity import equity as compute_equity
from .ranges import narrow as narrow_mod, table as range_table
from .state import STREETS, HandState, derive, validate_and_load

WIDE_VILLAIN_SEED = ("22+,A2s+,K2s+,Q4s+,J6s+,T6s+,96s+,86s+,75s+,64s+,53s+,"
                     "A2o+,K8o+,Q9o+,J9o+,T9o")
NARROW_VILLAIN_SEED = "22+,A9s+,KTs+,QTs+,JTs,T9s,98s,ATo+,KQo"


def compute(raw: dict[str, Any], *, villain_archetype: str | None = None,
            force_full: bool = False) -> dict[str, Any]:
    state = validate_and_load(raw)
    d = derive(state)
    hero_seat = state.hero_seat
    to_act = state.to_act
    hero_active_seat = state.seats[to_act]

    out: dict[str, Any] = {"state": d.to_json()}
    decision: gates.GateDecision | None = None

    # --- G0 : décision triviale -------------------------------------------
    only_action = "check_or_forced" if d.players_active <= 1 else None
    decision = gates.g0_forced(hero_is_allin=hero_active_seat.status == "allin", only_action=only_action)

    is_preflop = state.street == "preflop"

    line_json = actionline.to_json(state)
    out["line"] = line_json
    role = line_json["role"]
    pot_type = line_json["pot_type"]

    # --- Préflop : lookup de range -------------------------------------------
    if is_preflop:
        if decision is None:
            key = range_table.derive_key(state, to_act)
            in_range: bool | None = None
            verdict_if_in_range = "raise_or_call"
            range_json = None
            # Décision d'ouverture (RFI) : personne n'a encore volontairement
            # ouvert le pot (call/raise) — cf. actionline.is_opening_decision,
            # dont dépend aussi `role` désormais (il ne lit plus le `to_call`
            # gonflé par la blind forcée de la BB comme un "je défends").
            if pot_type == "srp" and actionline.is_opening_decision(state):
                entry = range_table.rfi(key)
                range_json = entry.to_json()
                hero_cards = state.seats[to_act].cards
                if hero_cards:
                    from .equity import parse_range

                    def _hand_in(range_str: str) -> bool:
                        if not range_str:
                            return False
                        combos = {frozenset((c.rank, c.suit) for c in wc.combo) for wc in parse_range(range_str)}
                        return frozenset((c.rank, c.suit) for c in hero_cards) in combos

                    if entry.strategy == "mixed_raise_limp":
                        # Deux buckets disjoints (raise / limp), pas une fréquence par
                        # main — arbitrage utilisateur, cf. data/preflop-rfi.yaml.
                        if _hand_in(entry.raise_range):
                            in_range, verdict_if_in_range = True, "raise"
                        elif _hand_in(entry.limp_range):
                            in_range, verdict_if_in_range = True, "limp"
                        else:
                            in_range = False
                    elif entry.range:
                        in_range = _hand_in(entry.range)
            out["range"] = range_json
            decision = gates.g1_preflop_range(in_range=in_range, verdict_if_in_range=verdict_if_in_range)
        if decision is None:
            # Préflop hors G0/G1 : zone grise, pas de moteur de budget préflop en v2.0.
            decision = gates.g5_grey_zone(
                escalate_reason="préflop hors plafond RFI tabulé — jugement du coach requis")
        return _finish(out, decision, force_full=force_full)

    # --- Postflop -------------------------------------------------------------
    hero_cards = state.seats[hero_seat].cards
    if hero_cards is None:
        raise ValueError("hero doit avoir ses deux cartes connues pour un brief postflop")

    hc = handclass.classify(hero_cards, state.board)
    texture = texture_mod.classify(state.board)
    out["hand"] = hc.to_json()
    out["texture"] = texture.to_json()

    n_opponents_active = max(0, d.players_active - 1)
    facing_bet = d.to_call > 0
    replay = actionline.replay_pressure(state)
    b = budget_mod.compute(
        hc, texture, pot_type=pot_type, street=state.street,
        n_opponents_active=n_opponents_active,
        pressure_spent=replay.spent.get(to_act, 0.0),
        pressure_faced=replay.faced.get(to_act, 0.0),
        villain_archetype=villain_archetype, facing_bet=facing_bet,
    )
    out["budget"] = b.to_json()
    if villain_archetype:
        out["exploit"] = {"archetype": villain_archetype,
                           "flags": [n for n in b.notes if n.startswith("G4")]}

    envisaged = "call" if facing_bet else "bet"
    if decision is None:
        decision = gates.g2_budget_decisive(envisaged_action=envisaged, viable_actions=b.viable_actions,
                                             att_remaining=b.att_remaining, facing_bet=facing_bet)
    if decision is None:
        decision = gates.g4_exploit(exploit_notes=b.notes)

    # --- G3 : bornes d'équité — calculées si rien n'a encore tranché, ou sur
    # demande explicite de profondeur (force_full) même si G0/G2/G4 a déjà
    # rendu un verdict (le verdict n'est jamais recalculé, juste détaillé).
    if decision is None or force_full:
        equity_section, g3 = _compute_equity_section(state, hero_cards, d, pot_type, n_opponents_active)
        out["equity"] = equity_section
        if decision is None:
            decision = g3

    if decision is None:
        reason = (f"équité [{out['equity']['lower_bound']:.2f}, {out['equity']['upper_bound']:.2f}] "
                   f"chevauche le seuil {d.pot_odds:.2f}") if d.pot_odds is not None else (
            "pas de mise à comparer (check/bet) — jugement du coach requis")
        decision = gates.g5_grey_zone(escalate_reason=reason)

    return _finish(out, decision, force_full=force_full)


def _villain_seat_for_equity(state: HandState) -> int | None:
    """Le siège adverse le plus pertinent pour les bornes d'équité : le
    dernier agresseur (celui dont l'action motive la décision du héros) si
    connu et encore en lice, sinon le premier autre siège encore en lice.
    En heads-up c'est le seul choix possible ; en multiway c'est une
    simplification documentée (un seul adversaire modélisé, pas tous)."""
    others = [s.seat for s in state.seats if s.seat != state.to_act and s.status in ("active", "allin")]
    if not others:
        return None
    agg = actionline.last_aggressor(state)
    return agg if agg in others else others[0]


def _narrow_through_history(seed: str, state: HandState, villain_seat: int, pot_type: str,
                             n_opponents_active: int) -> str:
    """Rejoue les actions POSTFLOP de ``villain_seat``, rue par rue jusqu'à
    la rue courante incluse, en filtrant ``seed`` à chaque étape via
    ``ranges.narrow`` (le même moteur qu'expose ``pc narrow``). Le préflop
    n'est pas rejoué ici : ``narrow()`` (via ``handclass.classify``) exige un
    flop minimum — la range de départ à choisir en position préflop reste un
    choix de ``seed``, pas un narrowing mécanique."""
    current = seed
    for street in STREETS:
        node = state.streets.get(street)
        if node is None:
            break
        if street == "preflop":
            continue
        villain_actions = [a for a in node["actions"] if a["seat"] == villain_seat]
        if villain_actions:
            last_action = villain_actions[-1]["action"]
            if last_action != "post":
                try:
                    result = narrow_mod.narrow(
                        current, node["board"], last_action, pot_type=pot_type, street=street,
                        n_opponents_active=n_opponents_active,
                    )
                    if result.range_str:
                        current = result.range_str
                except ValueError:
                    pass  # range épuisée par le narrowing -> on garde la précédente plutôt que planter
        if street == state.street:
            break
    return current


def _compute_equity_section(state: HandState, hero_cards: list[Card], d, pot_type: str,
                             n_opponents_active: int) -> tuple[dict[str, Any], "gates.GateDecision | None"]:
    hero_combo = f"{hero_cards[0]}{hero_cards[1]}"
    villain_seat = _villain_seat_for_equity(state)
    if villain_seat is None:
        wide_range, narrow_range = WIDE_VILLAIN_SEED, NARROW_VILLAIN_SEED
    else:
        wide_range = _narrow_through_history(WIDE_VILLAIN_SEED, state, villain_seat, pot_type, n_opponents_active)
        narrow_range = _narrow_through_history(NARROW_VILLAIN_SEED, state, villain_seat, pot_type, n_opponents_active)

    values: dict[str, float] = {}
    for label, rng in (("wide", wide_range), ("narrow", narrow_range)):
        try:
            values[label] = compute_equity(hero_combo, rng, board=state.board).range1_equity
        except ValueError:
            continue  # range vide une fois narrowée -> exclue des bornes plutôt que de planter

    if not values:
        return {
            "vs_range_wide": wide_range, "vs_range_narrow": narrow_range,
            "note": "les deux ranges narrowées sont vides sur ce board — aucune borne calculable",
        }, None

    lower, upper = min(values.values()), max(values.values())
    section = {
        "vs_range_wide": wide_range, "vs_range_narrow": narrow_range,
        "lower_bound": round(lower, 4), "upper_bound": round(upper, 4),
        "threshold": round(d.pot_odds, 4) if d.pot_odds is not None else None,
        "method": "enumeration_or_monte_carlo",
    }
    g3 = gates.g3_equity_bounds(lower_bound=lower, upper_bound=upper, threshold=d.pot_odds) \
        if d.pot_odds is not None else None
    return section, g3


def _finish(out: dict[str, Any], decision: "gates.GateDecision", *, force_full: bool) -> dict[str, Any]:
    out["gate"] = decision.gate
    out["verdict"] = decision.verdict
    out["confidence"] = decision.confidence
    out["verbosity"] = "full" if force_full else decision.verbosity
    out["escalate_reason"] = decision.escalate_reason
    return out
