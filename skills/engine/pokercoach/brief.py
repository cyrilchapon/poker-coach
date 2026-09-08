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

from . import actionline, budget as budget_mod, gates, handclass, sizing as sizing_mod, texture as texture_mod
from .cards import Card
from .equity import equity as compute_equity, parse_range
from .ranges import narrow as narrow_mod, table as range_table
from .state import STREETS, HandState, StateError, derive, n_behind as derive_n_behind, validate_and_load

WIDE_VILLAIN_SEED = ("22+,A2s+,K2s+,Q4s+,J6s+,T6s+,96s+,86s+,75s+,64s+,53s+,"
                     "A2o+,K8o+,Q9o+,J9o+,T9o")
NARROW_VILLAIN_SEED = "22+,A9s+,KTs+,QTs+,JTs,T9s,98s,ATo+,KQo"


def compute(raw: dict[str, Any], *, villain_archetype: str | None = None,
            force_full: bool = False) -> dict[str, Any]:
    state = validate_and_load(raw)
    # Régression : `hero_seat` et `to_act` étaient mélangés dans cette
    # fonction (le préflop lisait les cartes de `to_act`, le postflop celles
    # de `hero_seat`, la pression toujours celle de `to_act`) -- `pc brief`
    # n'a de sens QUE comme conseil au héros sur SA décision, donc les deux
    # doivent être le même siège. On l'impose explicitement ici plutôt que
    # de laisser les deux lectures diverger silencieusement si jamais un
    # appelant calcule un brief hors du tour du héros.
    hero_seat = state.hero_seat
    _require_hero_to_act(state)

    d = derive(state)

    out: dict[str, Any] = {"state": d.to_json()}
    decision: gates.GateDecision | None = None

    # --- G0 : décision triviale -------------------------------------------
    # validate_and_load garantit déjà seats[to_act].status == "active", et
    # to_act == hero_seat est maintenant garanti ci-dessus -- le héros ne
    # peut donc jamais être "allin" ici (un siège all-in ne peut plus être
    # to_act). Gardé à `False` explicitement plutôt que retiré : documente
    # l'invariant plutôt que de faire disparaître silencieusement le cas.
    only_action = "check_or_forced" if d.players_active <= 1 else None
    decision = gates.g0_forced(hero_is_allin=False, only_action=only_action)

    is_preflop = state.street == "preflop"

    line_json = actionline.to_json(state)
    out["line"] = line_json
    role = line_json["role"]
    pot_type = line_json["pot_type"]

    # --- Préflop : lookup de range -------------------------------------------
    if is_preflop:
        if decision is None:
            key = range_table.derive_key(state, hero_seat)
            in_range: bool | None = None
            verdict_if_in_range = "raise_or_call"
            range_confidence = "high"
            range_json = None
            hero_cards = state.seats[hero_seat].cards
            # Décision d'ouverture (RFI) : personne n'a encore volontairement
            # ouvert le pot (call/raise) — cf. actionline.is_opening_decision,
            # dont dépend aussi `role` désormais (il ne lit plus le `to_call`
            # gonflé par la blind forcée de la BB comme un "je défends").
            if pot_type == "srp" and actionline.is_opening_decision(state):
                entry = range_table.rfi(key)
                range_json = entry.to_json()
                range_confidence = entry.confidence
                if hero_cards:
                    if entry.strategy == "mixed_raise_limp":
                        # Deux buckets disjoints (raise / limp), pas une fréquence par
                        # main — arbitrage utilisateur, cf. data/preflop-rfi.yaml.
                        if _hand_in(hero_cards, entry.raise_range):
                            in_range, verdict_if_in_range = True, "raise"
                        elif _hand_in(hero_cards, entry.limp_range):
                            in_range, verdict_if_in_range = True, "limp"
                        else:
                            in_range = False
                    elif entry.range:
                        in_range = _hand_in(hero_cards, entry.range)
            elif not actionline.is_opening_decision(state):
                # Défense : quelqu'un a déjà volontairement ouvert le pot --
                # jusqu'ici cette branche tombait systématiquement en G5
                # (ranges/table.py's vs_rfi/vs_limp/squeeze/vs_3bet/vs_4bet
                # existaient mais n'étaient appelées de nulle part — code
                # mort, cf. README). Câblées ici via le scénario dérivé le
                # plus proche de ce que le héros affronte réellement.
                entry = _defend_scenario_entry(state, hero_seat, pot_type, key,
                                                villain_archetype=villain_archetype)
                if entry is not None:
                    range_json = entry.to_json()
                    range_confidence = entry.confidence
                    if hero_cards and entry.range:
                        in_range = _hand_in(hero_cards, entry.range)
            out["range"] = range_json
            decision = gates.g1_preflop_range(in_range=in_range, verdict_if_in_range=verdict_if_in_range,
                                               range_confidence=range_confidence)
        if decision is None:
            # Préflop hors G0/G1 : zone grise, pas de moteur de budget préflop en v2.0.
            decision = gates.g5_grey_zone(
                escalate_reason="préflop hors plafond RFI tabulé — jugement du coach requis")
        # Régression : G1 tranchait "raise"/"raise_or_call" sans jamais
        # chiffrer de taille -- ni une RFI classique ni une isolation
        # au-dessus d'un ou plusieurs limps n'ont de gate dédié pour ça
        # (ce n'est pas une décision grise, juste une formule). `n_limpers`
        # compte les calls déjà actés sur cette rue -- toujours 0 en RFI
        # pure (is_opening_decision l'impose), le nombre réel de limpeurs
        # pour une isolation.
        if decision.verdict in ("raise", "raise_or_call"):
            n_limpers = sum(1 for a in state.streets["preflop"]["actions"] if a["action"] == "call")
            out["sizing"] = sizing_mod.preflop_open_to(n_limpers, villain_archetype=villain_archetype)
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
        pressure_spent=replay.spent.get(hero_seat, 0.0),
        pressure_faced=replay.faced.get(hero_seat, 0.0),
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
        elif g3 is not None and g3.verdict is not None and _leans_fold(decision.verdict) != _leans_fold(g3.verdict):
            # G2/G4 avait déjà tranché mais force_full a quand même calculé
            # G3 (le verdict rendu n'est jamais recalculé -- voir docstring
            # du module) : si G3 penche de l'autre côté, l'exposer plutôt que
            # de le laisser invisible dans le seul `out["equity"]` brut.
            out["gate_disagreement"] = {
                "closing_gate": decision.gate, "closing_verdict": decision.verdict,
                "g3_verdict": g3.verdict,
                "note": (f"{decision.gate} a tranché \"{decision.verdict}\" (confidence="
                         f"{decision.confidence!r}) mais l'équité calculée penche pour "
                         f"\"{g3.verdict}\" — le verdict rendu reste celui de {decision.gate}, "
                         "ce flag signale juste le désaccord."),
            }

    if decision is None:
        reason = (f"équité [{out['equity']['lower_bound']:.2f}, {out['equity']['upper_bound']:.2f}] "
                   f"chevauche le seuil {d.pot_odds:.2f}") if d.pot_odds is not None else (
            "pas de mise à comparer (check/bet) — jugement du coach requis")
        decision = gates.g5_grey_zone(escalate_reason=reason)

    return _finish(out, decision, force_full=force_full)


def _hand_in(hero_cards: list[Card], range_str: str | None) -> bool:
    if not range_str:
        return False
    combos = {frozenset((c.rank, c.suit) for c in wc.combo) for wc in parse_range(range_str)}
    return frozenset((c.rank, c.suit) for c in hero_cards) in combos


def _has_a_call_after_the_last_raise(state: HandState) -> bool:
    """Un call après la dernière relance préflop signale une opportunité de
    squeeze pour le héros (relance + un ou plusieurs callers avant lui),
    par opposition à une défense heads-up simple face à l'ouvreur."""
    actions = state.streets["preflop"]["actions"]
    raise_indices = [i for i, a in enumerate(actions) if a["action"] in ("raise", "allin")]
    if not raise_indices:
        return False
    return any(a["action"] == "call" for a in actions[raise_indices[-1] + 1:])


def _defend_scenario_entry(state: HandState, hero_seat: int, pot_type: str,
                            key: "range_table.RangeKey",
                            villain_archetype: str | None = None) -> "range_table.RangeEntry | None":
    """Choisit et calcule le scénario dérivé (``ranges/table.py``) le plus
    proche de la décision de défense affrontée par le héros.

    Approximation documentée par construction : les scénarios dérivés sont
    des FORMULES (jamais des tables), et deux branches réelles de l'arbre
    de jeu n'ont pas de formule dédiée dans ``ranges/table.py`` -- on
    utilise alors le scénario le plus proche plutôt que de renoncer
    entièrement (ce qui revenait à toujours tomber en G5) :
    - face à un squeeze adverse (``pot_type == "squeeze"``), pas de formule
      "vs_squeeze" -- ``vs_3bet`` sert d'approximation (même niveau
      d'agression que ce que l'ouvreur original affronte).
    - une relance suivie d'un ou plusieurs calls avant le héros
      (opportunité de squeeze POUR le héros) utilise ``squeeze()`` plutôt
      que ``vs_rfi()``, même si ``pot_type()`` classe encore ça comme
      "srp" (une seule relance a eu lieu jusqu'ici).

    ``villain_archetype`` : propagé à ``ranges/table.py`` pour resserrer ou
    élargir la range de l'agresseur adverse selon son profil (régression :
    ``--villain-archetype`` était accepté par ``pc brief`` et affichait bien
    les flags G4, mais n'était JAMAIS transmis au choix de range de défense
    -- un Fish (PFR bas) qui relance était traité comme un ouvreur standard
    à largeur tabulée, alors que sa relance signale une main bien plus
    étroite). ``_is_a_raise_over_a_limp`` détecte en plus le cas où cette
    même relance a été posée par-dessus un limp (isolation) plutôt que dans
    un pot vierge -- un signal de force supplémentaire que ``pot_type()``
    ne distingue pas (une seule relance -> "srp" dans les deux cas)."""
    aggressor = actionline.last_aggressor(state)
    opener_n_behind = derive_n_behind(state, aggressor) if aggressor is not None else 0

    if pot_type == "limp":
        return range_table.vs_limp(key)
    if pot_type == "srp":
        if _has_a_call_after_the_last_raise(state):
            return range_table.squeeze(key, opener_n_behind=opener_n_behind,
                                        villain_archetype=villain_archetype)
        return range_table.vs_rfi(key, opener_n_behind=opener_n_behind,
                                   villain_archetype=villain_archetype,
                                   iso_over_limp=actionline.is_a_raise_over_a_limp(state))
    if pot_type in ("three_bet_pot", "squeeze"):
        return range_table.vs_3bet(key, villain_archetype=villain_archetype)
    if pot_type == "four_bet_pot":
        return range_table.vs_4bet(key, villain_archetype=villain_archetype)
    return None


def _require_hero_to_act(state: HandState) -> None:
    """``pc brief`` n'a de sens que comme conseil au héros sur SA décision —
    lève une erreur claire plutôt que de laisser `hero_seat`/`to_act`
    diverger silencieusement (régression corrigée : le code lisait tantôt
    l'un, tantôt l'autre, produisant un brief incohérent -- cartes du héros
    mélangées avec le pot/to_call/budget de qui que ce soit d'autre -- si
    jamais un appelant calculait un brief hors du tour du héros)."""
    if state.to_act != state.hero_seat:
        raise StateError(
            f"pc brief ne peut conseiller que la décision du héros : to_act (siège {state.to_act}) "
            f"n'est pas hero_seat (siège {state.hero_seat}) — ce n'est pas au héros de parler ici"
        )


def _villain_seat_for_equity(state: HandState, hero_seat: int) -> int | None:
    """Le siège adverse le plus pertinent pour les bornes d'équité — délègue
    à ``actionline.most_relevant_villain_seat`` (même logique qu'expose
    ``pc narrow`` pour choisir le villain à narrower)."""
    return actionline.most_relevant_villain_seat(state, from_seat=hero_seat)


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
                # Régression : sans ce rejeu de pression, chaque rue repartait
                # d'un budget ATT/DEF neuf (0.0/0.0) -- un villain qui a déjà
                # barrelé deux fois était filtré comme s'il ouvrait l'action
                # à froid. `replay_pressure(upto_street=...)` donne la
                # pression RÉELLEMENT accumulée par ce siège jusqu'à cette
                # rue incluse.
                replay = actionline.replay_pressure(state, upto_street=street)
                try:
                    result = narrow_mod.narrow(
                        current, node["board"], last_action, pot_type=pot_type, street=street,
                        n_opponents_active=n_opponents_active,
                        pressure_spent=replay.spent.get(villain_seat, 0.0),
                        pressure_faced=replay.faced.get(villain_seat, 0.0),
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
    villain_seat = _villain_seat_for_equity(state, state.hero_seat)
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


def _leans_fold(verdict: str | None) -> bool:
    """Bucket grossier pour détecter un désaccord ENTRE GATES (fold vs.
    tout le reste) -- pas une comparaison exacte de verdict à verdict, G2
    et G3 n'emploient pas le même vocabulaire ("fold"/"call" contre "fold"/
    "call_or_raise")."""
    return verdict == "fold"


def _finish(out: dict[str, Any], decision: "gates.GateDecision", *, force_full: bool) -> dict[str, Any]:
    out["gate"] = decision.gate
    out["verdict"] = decision.verdict
    out["confidence"] = decision.confidence
    out["verbosity"] = "full" if force_full else decision.verbosity
    out["escalate_reason"] = decision.escalate_reason
    return out
