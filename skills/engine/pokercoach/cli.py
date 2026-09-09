"""Point d'entrée `pc` : dispatch des sous-commandes, JSON strict sur stdout.

Contrat (docs/brief/references/02-architecture-v2.md) :
- stdout : uniquement du JSON, jamais de prose.
- stderr : les erreurs.
- code de retour non nul si l'état est invalide.

Sous-commandes :
    pc state    --hand hand.json                  validation + dérivations
    pc hand     --hand hand.json [--seat N]        classe de main, outs, blockers
    pc texture  --hand hand.json                   labels de texture du board
    pc line     --hand hand.json                   scénario de ligne d'action + pression
    pc budget   --hand hand.json [--villain-archetype X]   ATT/DEF restants
    pc equity   --range1 R1 --vs R2 [--board ...] [--dead ...] [--iterations N]
                (ou --hand hand.json pour utiliser les cartes du héros + le board de la main)
    pc narrow   --hand hand.json --action ACTION [--range R] [--villain-archetype X]
    pc ranges   --hand hand.json --scenario {rfi,vs_rfi,vs_limp,squeeze,vs_3bet,vs_4bet}
                [--seat N] [--opener-seat N]    lookup direct d'un scénario dérivé
    pc brief    --hand hand.json [--villain-archetype X]    ⭐ tout en un appel
    pc render   --hand hand.json [--expect-street S] [--expect-board ...]
                --expect-* : tripwire d'état inline (même vérification que `pc assert-state`,
                mais dans l'appel déjà fait avant chaque décision) — échoue sans rien dessiner
                si la rue/le board réels divergent de ce que le coach croit être vrai
    pc showdown --from-hand hand.json [--hand POSITION:C1,C2 ...]     ⭐ en session
                board et cartes connues repris de l'état canonique ; échoue si l'état n'est
                pas à la river, si un argument le contredit, ou s'il manque un joueur encore
                en lice — sans --from-hand, pc showdown ne lit PAS hand.json et résoudra
                volontiers un board qui n'a jamais existé
    pc showdown --board B --hand NAME:C1,C2 [--hand NAME:C1,C2 ...]   (calculatrice libre)
    pc glossary <terme>
    pc apply    --hand hand.json --action "b 5.5"  applique une action, réécrit l'état
                renvoie l'état résultant + `applied_to` (siège, position, action, montant
                auxquels l'action vient d'être appliquée) -- l'état seul ne dit que qui
                parle ENSUITE, jamais qui vient de parler
    pc assert-state --hand hand.json [--street S] [--board ...] [--to-act N]
                vérifie que l'état réel correspond à ce que le coach CROIT être vrai --
                échoue bruyamment (code non nul) en cas de dérive, plutôt que de laisser
                le coach narrer une rue qui n'est pas celle réellement en mémoire
    pc paths    chemins absolus resolus de pokercoach/, data/, docs/ (utile hors dev :
                claude.ai déploie chaque skill isolée, sans racine de repo commune)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from . import actionline, brief as brief_mod, budget as budget_mod, glossary, handclass
from . import render as render_mod, showdown as showdown_mod, sizing as sizing_mod, texture as texture_mod
from .cards import Card, CardError, parse_card, parse_cards
from .equity import equity as compute_equity
from .state import (
    STREETS, StateError, derive, is_runout, n_behind as derive_n_behind_state, no_decision_left,
    position_labels, remaining_stack, validate_and_load,
)


def _load_hand_json(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise StateError(f"fichier introuvable : {path}") from exc
    except json.JSONDecodeError as exc:
        raise StateError(f"JSON invalide dans {path} : {exc}") from exc


def _load_state(path: str):
    return validate_and_load(_load_hand_json(path))


# --- state / hand / texture / line -----------------------------------------

def cmd_state(args: argparse.Namespace) -> dict[str, Any]:
    return derive(_load_state(args.hand)).to_json()


def cmd_hand(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state(args.hand)
    seat = args.seat if args.seat is not None else state.hero_seat
    cards = state.seats[seat].cards
    if cards is None:
        raise StateError(f"seats[{seat}].cards inconnu — impossible de classifier")
    return handclass.classify(cards, state.board).to_json()


def cmd_texture(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state(args.hand)
    return texture_mod.classify(state.board).to_json()


def cmd_line(args: argparse.Namespace) -> dict[str, Any]:
    return actionline.to_json(_load_state(args.hand))


def cmd_budget(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state(args.hand)
    no_decision = no_decision_left(state)
    if no_decision is not None:
        raise StateError(
            f"pc budget évalue une décision à prendre, or il n'y en a plus : {no_decision}"
        )
    # Régression : lisait les cartes du siège au trait (`to_act`) mais la
    # pression de ce même `to_act` -- cohérent entre les deux, mais divergent
    # de `cmd_hand` (qui utilise `hero_seat` par défaut) si jamais `pc budget`
    # est appelé hors du tour du héros, où `to_act` n'a de toute façon pas de
    # cartes connues. `pc budget` n'a de sens que pour évaluer LE HÉROS.
    if state.to_act != state.hero_seat:
        raise StateError(
            f"pc budget ne peut évaluer que le budget du héros : to_act (siège {state.to_act}) "
            f"n'est pas hero_seat (siège {state.hero_seat})"
        )
    hero_cards = state.seats[state.hero_seat].cards
    if hero_cards is None or len(state.board) < 3:
        raise StateError("budget nécessite un flop et les cartes du siège au trait")
    hc = handclass.classify(hero_cards, state.board)
    texture = texture_mod.classify(state.board)
    line = actionline.to_json(state)
    replay = actionline.replay_pressure(state)
    d = derive(state)
    b = budget_mod.compute(
        hc, texture, pot_type=line["pot_type"], street=state.street,
        n_opponents_active=max(0, d.players_active - 1),
        pressure_spent=replay.spent.get(state.hero_seat, 0.0),
        pressure_faced=replay.faced.get(state.hero_seat, 0.0),
        villain_archetype=args.villain_archetype, facing_bet=d.to_call > 0,
    )
    return b.to_json()


# --- equity / narrow ---------------------------------------------------------

def _split_card_tokens(s: str) -> list[str]:
    """Découpe une liste de cartes séparées par des virgules -- et tolère
    aussi l'espace comme séparateur (rapport de bug live-session #5b :
    ``--hand "SB:7♣ 5♠"`` échouait avec un message trompeur, "carte invalide
    (2 caractères attendus) : '7♣ 5♠'", qui parle d'UNE carte alors que le
    vrai problème est le séparateur d'une LISTE de cartes -- accepter
    l'espace en plus de la virgule règle le cas d'usage sans avoir à
    apprendre une convention de saisie supplémentaire)."""
    return [t for t in re.split(r"[,\s]+", s.strip()) if t]


def _parse_card_list(s: str | None) -> list[Card]:
    if not s:
        return []
    return parse_cards(_split_card_tokens(s))


def cmd_equity(args: argparse.Namespace) -> dict[str, Any]:
    board = _parse_card_list(args.board)
    dead = _parse_card_list(args.dead)
    range1 = args.range1
    if args.hand:
        state = _load_state(args.hand)
        board = state.board
        hero_cards = state.seats[state.hero_seat].cards
        if range1 is None and hero_cards:
            range1 = f"{hero_cards[0]}{hero_cards[1]}"
    if range1 is None:
        raise StateError("fournir --range1 ou --hand (avec les cartes du héros connues)")
    result = compute_equity(range1, args.vs, board=board, dead=dead, iterations=args.iterations)
    return result.to_json()


def cmd_narrow(args: argparse.Namespace) -> dict[str, Any]:
    from .ranges import narrow as narrow_mod

    state = _load_state(args.hand)
    if len(state.board) < 3:
        raise StateError("narrow nécessite au moins un flop")
    line = actionline.to_json(state)
    replay = actionline.replay_pressure(state)
    d = derive(state)
    # Régression : la pression rejouée était toujours celle de `to_act` (le
    # héros, la plupart du temps) alors que `--action` décrit l'action d'un
    # VILLAIN dont on narrowe la range -- la pression passée à narrow() doit
    # être celle de CE siège-là, pas celle du héros. `--seat` permet de le
    # préciser explicitement ; à défaut, le même choix de "villain le plus
    # pertinent" qu'utilise `pc brief` pour ses bornes G3.
    villain_seat = args.seat
    if villain_seat is None:
        villain_seat = actionline.most_relevant_villain_seat(state, from_seat=state.hero_seat)
    if villain_seat is not None and not (0 <= villain_seat < state.n_seats):
        raise StateError(f"--seat invalide : {villain_seat!r}")
    range_str = args.range or ",".join([
        "22+", "A2s+", "K2s+", "Q4s+", "J6s+", "T6s+", "96s+", "86s+", "75s+", "64s+", "53s+",
        "A2o+", "K8o+", "Q9o+", "J9o+", "T9o",
    ])
    result = narrow_mod.narrow(
        range_str, state.board, args.action, pot_type=line["pot_type"], street=state.street,
        n_opponents_active=max(0, d.players_active - 1),
        pressure_spent=replay.spent.get(villain_seat, 0.0) if villain_seat is not None else 0.0,
        pressure_faced=replay.faced.get(villain_seat, 0.0) if villain_seat is not None else 0.0,
        villain_archetype=args.villain_archetype,
    )
    return result.to_json()


def cmd_ranges(args: argparse.Namespace) -> dict[str, Any]:
    """Lookup direct d'un scénario de range dérivé (``ranges/table.py``),
    sans passer par ``pc brief`` — utile en session pour "que dit la range
    théorique ici ?" indépendamment de la main du héros. Jusqu'ici
    ``vs_rfi``/``vs_limp``/``squeeze``/``vs_3bet``/``vs_4bet`` n'étaient
    appelées que par les tests, aucune sous-commande ne les exposait."""
    from .ranges import table as range_table

    state = _load_state(args.hand)
    seat = args.seat if args.seat is not None else state.hero_seat
    if not (0 <= seat < state.n_seats):
        raise StateError(f"--seat invalide : {seat!r}")
    key = range_table.derive_key(state, seat)

    scenario = args.scenario
    needs_opener = scenario in ("vs_rfi", "squeeze")
    opener_seat = args.opener_seat
    if needs_opener and opener_seat is None:
        opener_seat = actionline.last_aggressor(state)
        if opener_seat is None:
            raise StateError(f"--opener-seat requis pour {scenario!r} (aucun agresseur détectable "
                              "dans l'historique de la main)")
    if opener_seat is not None and not (0 <= opener_seat < state.n_seats):
        raise StateError(f"--opener-seat invalide : {opener_seat!r}")

    if scenario == "rfi":
        entry = range_table.rfi(key)
    elif scenario == "vs_rfi":
        entry = range_table.vs_rfi(key, opener_n_behind=derive_n_behind_state(state, opener_seat),
                                    villain_archetype=args.villain_archetype,
                                    iso_over_limp=actionline.is_a_raise_over_a_limp(state))
    elif scenario == "vs_limp":
        entry = range_table.vs_limp(key)
    elif scenario == "squeeze":
        entry = range_table.squeeze(key, opener_n_behind=derive_n_behind_state(state, opener_seat),
                                     villain_archetype=args.villain_archetype)
    elif scenario == "vs_3bet":
        entry = range_table.vs_3bet(key, villain_archetype=args.villain_archetype)
    elif scenario == "vs_4bet":
        entry = range_table.vs_4bet(key, villain_archetype=args.villain_archetype)
    else:
        raise StateError(f"scénario inconnu : {scenario!r}")
    return entry.to_json()


# --- brief -------------------------------------------------------------------

def cmd_brief(args: argparse.Namespace) -> dict[str, Any]:
    raw = _load_hand_json(args.hand)
    try:
        return brief_mod.compute(raw, villain_archetype=args.villain_archetype,
                                  force_full=(args.depth == "full"))
    except StateError:
        raise
    except ValueError as exc:
        raise StateError(str(exc)) from exc


# --- render / showdown / glossary --------------------------------------------

def cmd_render(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_state(args.hand)

    # Tripwire optionnel, dans l'appel que le coach fait DÉJÀ avant chaque
    # décision (revue live-session #6) : `pc assert-state` offre la même
    # vérification, mais en tant qu'étape séparée -- donc à ne pas oublier,
    # c-à-d exactement le genre de discipline d'appelant qui a déjà lâché
    # (une rue narrée sans advance_street.py, un advance_street.py en échec
    # dont le code retour n'a pas été lu). Ici, annoncer la rue attendue
    # fait échouer le rendu lui-même plutôt que dessiner une table périmée
    # que le récit contredit.
    errors = _state_divergences(state, street=args.expect_street, board=args.expect_board)
    if errors:
        raise StateError(
            "pc render : l'état réel diverge de ce qui était attendu (" + " ; ".join(errors)
            + ") — rien n'a été dessiné. Cause typique : une transition de rue narrée sans "
              "advance_street.py, ou un advance_street.py resté en échec dont le code retour "
              "n'a pas été vérifié."
        )

    labels = position_labels(state)
    node = state.streets[state.street]

    def seat_dict(seat) -> dict[str, Any]:
        action, amount = "", None
        for act in node["actions"]:
            if act["seat"] == seat.seat:
                action, amount = act["action"], act.get("amount")
        # Régression (revue live-session #5a) : un siège couché/tapis sur une
        # rue PRÉCÉDENTE n'a par définition aucune entrée dans les actions de
        # la rue COURANTE -- `amount` restait à `None` (rendu vide par
        # render.py) alors que le docstring de render.py promet que "fold
        # affiche quand même le montant engagé" ; ``action`` bénéficiait déjà
        # d'un repli sur ``status`` (cf. ``render.s()``), mais rien
        # n'existait côté ``amount``. On relit ici le montant de sa toute
        # DERNIÈRE action connue (n'importe quelle rue, jusqu'à la rue
        # courante incluse) -- c'est nécessairement son montant final, un
        # siège couché/tapis ne pouvant plus agir ensuite.
        if not action and seat.status in ("folded", "allin"):
            for street in STREETS:
                street_node = state.streets.get(street)
                if street_node is None:
                    break
                for act in street_node["actions"]:
                    if act["seat"] == seat.seat:
                        amount = act.get("amount")
                if street == state.street:
                    break
        # Régression : ``seat.stack`` est le stack de DÉBUT DE MAIN, jamais
        # débité par `pc apply`/`advance_street.py` en cours de main (seul
        # `new_hand.py` réconcilie, en fin de main) -- l'afficher tel quel
        # rendait un stack périmé pendant toute la main, en désaccord avec
        # `effective_stack` de `pc state`/`pc brief` (qui, lui, dérive déjà
        # correctement via `remaining_stack`). Même source ici.
        d: dict[str, Any] = {"stack": round(remaining_stack(state, seat.seat), 2),
                              "action": action, "amount": amount, "status": seat.status}
        if seat.archetype:
            d["archetype"] = seat.archetype
        if seat.cards:
            d["cards"] = [str(c) for c in seat.cards]
        return d

    # Régression : ``render()`` exige un ``acting_order`` = sièges non-Héros
    # dans l'ordre de SIÈGE PHYSIQUE clockwise depuis la gauche du Héros
    # (cf. render.py docstring) -- sans le passer explicitement, il retombe
    # sur l'ordre d'insertion de ``seats_out``, lui-même construit ici en
    # itérant les sièges physiques 0..n-1 (Héros exclu) : une rotation
    # différente dès que le Héros n'est pas le dernier siège physique. Les
    # bonnes données (stack/action) s'affichaient alors au mauvais endroit
    # autour de la table -- un désaccord invisible tant que le Héros
    # n'était pas au dernier siège (cas fréquent des fixtures de test, d'où
    # le passage inaperçu). Un siège ``out`` (busté, cf. new_hand.py) n'est
    # plus dans la main : on le retire ici, ``render()`` n'a pas de quoi le
    # distinguer d'un siège qui n'a pas encore agi.
    clockwise_from_hero = [
        state.seats[(state.hero_seat + offset) % state.n_seats]
        for offset in range(1, state.n_seats)
    ]
    seated = [seat for seat in clockwise_from_hero if seat.status != "out"]
    seats_out = {labels[seat.seat]: seat_dict(seat) for seat in seated}
    acting_order = [labels[seat.seat] for seat in seated]
    hero = state.seats[state.hero_seat]
    d = derive(state)
    ascii_art = render_mod.render(
        seats=seats_out, hero_position=labels[state.hero_seat], hero=seat_dict(hero),
        board=[str(c) for c in state.board], pot=round(d.pot, 2), street=state.street,
        acting_order=acting_order,
    )
    # En-tête d'état structuré, en plus de l'ASCII (revue live-session) :
    # un rendu écrit à la main plutôt que produit par cette commande, ou un
    # `pc brief` appelé sur la mauvaise rue après une transition oubliée,
    # ne laissait rien à vérifier mécaniquement -- seul le dessin ASCII (du
    # texte à comparer à l'œil) portait street/board/to_act/pot. Repris de
    # `derive().to_json()`, la même source que `pc state`/`pc brief`, pour
    # qu'un désaccord entre ce que le coach affiche et ce que le moteur
    # pense être vrai soit visible sans avoir à parser le dessin.
    return {"ascii": ascii_art, "state": d.to_json()}


def _parse_showdown_entry(entry: str) -> tuple[str, list[Card]]:
    if ":" not in entry:
        raise StateError(
            f"entrée de showdown invalide : {entry!r} — format attendu NOM:CARTES "
            "(ex. \"CO:K♦,T♦\")"
        )
    name, cards_str = entry.split(":", 1)
    cards = parse_cards(_split_card_tokens(cards_str))
    if len(cards) != 2:
        raise StateError(f"{name} : 2 cartes attendues, reçu {len(cards)}")
    return name.strip(), cards


def _seat_by_showdown_name(state, name: str) -> int | None:
    """Résout un nom d'entrée de showdown en siège physique : label de
    position (BTN/SB/BB/UTG/…, insensible à la casse), ``hero``, ou l'index
    de siège brut. ``None`` si le nom ne désigne aucun siège."""
    labels = position_labels(state)
    wanted = name.strip().lower()
    if wanted == "hero":
        return state.hero_seat
    for seat, label in labels.items():
        if label.lower() == wanted:
            return seat
    if wanted.isdigit() and int(wanted) < state.n_seats:
        return int(wanted)
    return None


def _showdown_from_state(args: argparse.Namespace) -> dict[str, Any]:
    """``pc showdown --from-hand hand.json`` : le board et les cartes connues
    viennent de l'ÉTAT CANONIQUE, pas d'arguments libres.

    Garde-fou mécanique (revue live-session #6). Sans ``--from-hand``,
    ``pc showdown`` ne lit pas ``hand.json`` du tout : c'est une calculatrice
    à arguments libres, qui résout aussi volontiers un board qui n'a jamais
    existé dans l'état. Constat de session : après un ``advance_street.py``
    resté EN ÉCHEC (code retour non nul, ignoré), un showdown de river
    complet et cohérent en apparence a été produit alors que ``hand.json``
    était toujours au préflop — la classe de bug « ne jamais halluciner la
    table » (cf. skills/live-session/SKILL.md), mais côté outillage : rien
    ne pouvait la détecter, puisque rien ne comparait quoi que ce soit.

    Avec ``--from-hand``, ce chemin devient impossible :
    - l'état doit RÉELLEMENT être à la river (board complet) — un showdown
      sur un état préflop/flop/turn échoue bruyamment, ce qui est exactement
      le repro ci-dessus ;
    - un ``--board`` explicite doit correspondre au board de l'état ;
    - les cartes déjà connues dans ``hand.json`` priment, et toute entrée
      ``--hand`` qui les contredit échoue ;
    - tous les sièges encore en lice doivent être renseignés — sinon un
      showdown à 3 serait résolu comme un heads-up sans que rien ne le dise.
    """
    state = _load_state(args.from_hand)
    labels = position_labels(state)

    if state.street != "river":
        raise StateError(
            f"pas de showdown possible : l'état réel est à {state.street!r}, pas à la river "
            f"(board {[str(c) for c in state.board]}). Un abattage suppose un board complet — "
            "dérouler les rues manquantes avec advance_street.py (et VÉRIFIER son code retour) "
            "avant d'appeler pc showdown."
        )

    if args.board is not None:
        expected = parse_cards(_split_card_tokens(args.board))
        if expected != state.board:
            raise StateError(
                f"--board {[str(c) for c in expected]} contredit le board de l'état "
                f"{[str(c) for c in state.board]} — l'état canonique fait foi ; ne pas passer "
                "--board avec --from-hand, ou corriger hand.json."
            )

    contesting = [s for s in state.seats if s.status in ("active", "allin")]
    if len(contesting) < 2:
        raise StateError(
            f"un seul siège encore en lice ({[labels[s.seat] for s in contesting]}) — "
            "le pot lui revient sans abattage, il n'y a pas de showdown à résoudre."
        )

    cards_by_seat: dict[int, list[Card]] = {s.seat: s.cards for s in contesting if s.cards}
    named_on_cli: set[int] = set()

    for entry in args.hand_entry or []:
        name, cards = _parse_showdown_entry(entry)
        seat = _seat_by_showdown_name(state, name)
        if seat is None:
            raise StateError(
                f"{name!r} ne désigne aucun siège de cette main — noms acceptés : "
                f"{sorted(labels.values())}, \"Hero\", ou un index de siège 0..{state.n_seats - 1}."
            )
        if state.seats[seat].status not in ("active", "allin"):
            raise StateError(
                f"{name!r} (siège {seat}) n'est plus en lice (status "
                f"{state.seats[seat].status!r}) — une main couchée ne va pas à l'abattage."
            )
        if seat in named_on_cli:
            # Sans ça, la seconde entrée écrasait silencieusement la première
            # (dernier arrivé gagne) : deux mains contradictoires passées pour
            # le même siège donnaient un résultat parfaitement cohérent... sur
            # une seule des deux.
            raise StateError(
                f"siège {labels[seat]!r} renseigné deux fois — une seule entrée --hand par siège."
            )
        named_on_cli.add(seat)
        known = state.seats[seat].cards
        if known and known != cards:
            raise StateError(
                f"{name!r} : cartes {[str(c) for c in cards]} contredisent celles déjà connues "
                f"dans hand.json {[str(c) for c in known]} — l'état canonique fait foi."
            )
        cards_by_seat[seat] = cards

    # Un deck n'a qu'un exemplaire de chaque carte : `validate_and_load` le
    # vérifie déjà pour tout ce qui est STOCKÉ dans hand.json, mais les cartes
    # passées en argument échappent à cette validation -- deux joueurs à qui
    # on prête le même as produiraient un abattage impeccablement résolu et
    # matériellement impossible (même classe de bug que le board fantôme
    # ci-dessus). Le chemin libre (sans --from-hand) reste une calculatrice
    # brute et n'est volontairement pas touché.
    seen: dict[tuple[str, str], str] = {(c.rank, c.suit): "board" for c in state.board}
    for seat, cards in cards_by_seat.items():
        for c in cards:
            key = (c.rank, c.suit)
            if key in seen:
                raise StateError(
                    f"carte {c} en double : déjà présente ({seen[key]}) — un abattage ne peut "
                    "pas distribuer deux fois la même carte."
                )
            seen[key] = f"siège {labels[seat]}"

    missing = [labels[s.seat] for s in contesting if s.seat not in cards_by_seat]
    if missing:
        raise StateError(
            f"cartes inconnues pour {missing} — tous les sièges encore en lice doivent être "
            "renseignés (dans hand.json, ou via --hand \"POSITION:C1,C2\"), sinon l'abattage "
            "serait résolu entre une partie seulement des joueurs."
        )

    hands = [(labels[s.seat], cards_by_seat[s.seat]) for s in contesting]
    seat_by_label = {labels[s.seat]: s.seat for s in contesting}
    out = []
    for r in showdown_mod.resolve(state.board, hands):
        d = r.to_json()
        d["seat"] = seat_by_label[r.name]
        d["is_hero"] = seat_by_label[r.name] == state.hero_seat
        out.append(d)

    return {
        "results": out,
        # Le board réellement utilisé, repris de l'état : c'est CE champ qui
        # rend une dérive visible dans la sortie elle-même, pas seulement
        # dans le code retour.
        "board": [str(c) for c in state.board],
        "street": state.street,
        "source": "hand.json",
    }


def cmd_showdown(args: argparse.Namespace) -> dict[str, Any]:
    if args.from_hand is not None:
        return _showdown_from_state(args)

    if args.board is None:
        raise StateError("--board est requis sans --from-hand (avec --from-hand, le board vient "
                          "de l'état canonique)")
    if not args.hand_entry:
        raise StateError("au moins un --hand NOM:CARTES est requis")

    board = parse_cards(_split_card_tokens(args.board))
    hands = [_parse_showdown_entry(h) for h in args.hand_entry]
    return {"results": [r.to_json() for r in showdown_mod.resolve(board, hands)],
            "board": [str(c) for c in board], "source": "arguments"}


def cmd_sizing(args: argparse.Namespace) -> dict[str, Any]:
    if args.sizing_cmd == "bet-pct":
        return {"bet_pct": sizing_mod.bet_pct(args.bet, args.pot_before)}
    if args.sizing_cmd == "preflop-open-to":
        return sizing_mod.preflop_open_to(args.limpers, villain_archetype=args.villain_archetype)
    return sizing_mod.raise_to(args.pot_before_bet, args.bet_to_call, args.fraction)


def cmd_glossary(args: argparse.Namespace) -> dict[str, Any]:
    definition = glossary.lookup(args.term)
    if definition is None:
        raise StateError(f"terme inconnu du glossaire : {args.term!r}")
    return {"term": args.term, "definition": definition}


def cmd_paths(_args: argparse.Namespace) -> dict[str, Any]:
    """Chemins absolus de ce déploiement de l'engine : ``pokercoach/`` (ce
    package), ``data/`` (tables YAML) et ``docs/`` (références), tous trois
    frères dans la skill ``engine`` (cf. ``skills/engine/``). Existe parce
    que les autres skills n'ont, sur claude.ai, aucune racine de repo
    commune à partir de laquelle deviner ces chemins par eux-mêmes -- voir
    ``scripts/pc_bootstrap.py`` dans chaque skill, qui les localise avant
    même que cette commande soit utilisable."""
    engine_dir = Path(__file__).resolve().parent.parent
    return {
        "pokercoach_dir": str(engine_dir / "pokercoach"),
        "data_dir": str(engine_dir / "data"),
        "docs_dir": str(engine_dir / "docs"),
    }


# --- apply ---------------------------------------------------------------

_SHORTHAND = {"f": "fold", "x": "check", "c": "call", "b": "bet", "r": "raise", "a": "allin"}
_EPS = 1e-6


def _min_raise_increment(state) -> float:
    """Incrément minimal d'une mise/relance sur la rue courante : au moins
    la BB (mise d'ouverture minimale), ou l'incrément de la dernière
    mise/relance déjà posée sur cette rue si plus grand (règle NLHE
    standard — une relance doit au moins égaler la taille de la
    précédente)."""
    node = state.streets[state.street]
    contributed: dict[int, float] = {}
    max_increment = 0.0
    for act in node["actions"]:
        seat, a, amt = act["seat"], act["action"], float(act.get("amount", 0.0))
        if a in ("bet", "raise", "allin"):
            inc = amt - contributed.get(seat, 0.0)
            max_increment = max(max_increment, inc)
        contributed[seat] = amt
    return max(state.big_blind, max_increment)


def _validate_apply_action(state, action: str, amount: float, *, already_in: float,
                            to_call_amt: float, stack_cap: float) -> None:
    """Contrôle de légalité ET de montant AVANT toute écriture — le contrat
    de ``state.py`` est "jamais de correction silencieuse". Lève
    ``StateError`` (jamais n'écrit un état incohérent sur disque)."""
    if action == "check" and to_call_amt > _EPS:
        raise StateError(f'"check" illégal : {to_call_amt:g} à suivre — utiliser "call"/"c" ou "fold"/"f"')
    if action == "call" and to_call_amt <= _EPS:
        raise StateError('"call" illégal : rien à suivre — utiliser "check"/"x"')
    if action == "bet" and to_call_amt > _EPS:
        raise StateError(f'"bet" illégal : {to_call_amt:g} à suivre déjà — utiliser "raise"/"r"')
    if action == "raise" and to_call_amt <= _EPS:
        raise StateError('"raise" illégal : rien à suivre — utiliser "bet"/"b"')

    if action in ("check", "call", "fold"):
        expected = already_in if action != "call" else already_in + to_call_amt
        if abs(amount - expected) > _EPS:
            raise StateError(
                f'montant incohérent pour "{action}" : {amount:g} donné, {expected:g} attendu '
                "(ces actions ont un montant déterminé par l'état, pas un choix libre)"
            )
    elif action == "allin":
        expected = already_in + stack_cap
        if abs(amount - expected) > _EPS:
            raise StateError(
                f'montant incohérent pour "allin" : {amount:g} donné, {expected:g} attendu '
                "(le tapis complet du siège, pas un choix libre)"
            )
    elif action in ("bet", "raise"):
        min_amount = already_in + (to_call_amt if action == "raise" else 0.0) + _min_raise_increment(state)
        max_amount = already_in + stack_cap
        if amount > max_amount + _EPS:
            raise StateError(
                f'montant "{action}" {amount:g} dépasse le tapis disponible ({max_amount:g}) — '
                'utiliser "allin"/"a" pour miser tout le tapis'
            )
        if amount < min_amount - _EPS:
            raise StateError(
                f'montant "{action}" {amount:g} sous le minimum légal ({min_amount:g})'
            )


def cmd_apply(args: argparse.Namespace) -> dict[str, Any]:
    from .state import remaining_stack, street_contribution, to_call as compute_to_call

    raw = _load_hand_json(args.hand)
    state = validate_and_load(raw)
    parts = args.action.strip().split()
    code = parts[0].lower()
    action = _SHORTHAND.get(code, code)
    if action not in _SHORTHAND.values():
        raise StateError(f'action inconnue : {code!r} (attendu f/x/c/b/r/a ou leur forme longue)')

    # Écarte du même coup `to_act is None` : ce cas est toujours l'un des deux
    # états terminaux, donc `acting_seat` est un siège réel en dessous.
    no_decision = no_decision_left(state)
    if no_decision is not None:
        raise StateError(f"aucune action légale : {no_decision}")
    acting_seat = state.to_act
    acting_position = position_labels(state)[acting_seat]
    already_in = street_contribution(state, state.street, acting_seat)
    to_call_amt = compute_to_call(state)
    stack_cap = remaining_stack(state, acting_seat)

    if len(parts) > 1:
        amount = float(parts[1])
    elif action == "call":
        amount = already_in + to_call_amt
    elif action in ("check", "fold"):
        amount = already_in
    elif action == "allin":
        amount = already_in + stack_cap
    else:
        raise StateError(f'montant requis pour "{action}" : ex "b 5.5", "r 12"')

    _validate_apply_action(state, action, amount, already_in=already_in,
                            to_call_amt=to_call_amt, stack_cap=stack_cap)

    node = raw["streets"][state.street]
    node["actions"].append({"seat": acting_seat, "action": action, "amount": amount})

    if action == "fold":
        raw["seats"][acting_seat]["status"] = "folded"
    elif action == "allin":
        raw["seats"][acting_seat]["status"] = "allin"
    n = state.n_seats
    order = [(acting_seat + i) % n for i in range(1, n + 1)]
    # ``None`` quand plus aucun siège ne peut agir : all-in callé (runout,
    # cf. ``state.is_runout``) ou tapis que tout le monde a couché. L'ancien
    # `if next_seat is not None` laissait alors `to_act` pointer sur le siège
    # qui venait de faire tapis ou de se coucher — un état que
    # `validate_and_load` refuse (« to_act n'est pas 'active' »), donc un
    # `pc apply` qui échouait SANS écrire le call all-in qu'on venait de lui
    # demander d'appliquer.
    raw["to_act"] = next((s for s in order if raw["seats"][s]["status"] == "active"), None)

    # Valider AVANT d'écrire : si le nouvel état est incohérent, l'erreur
    # remonte sans qu'aucun octet n'ait touché le disque. Écriture atomique
    # (fichier temporaire + os.replace) pour ne jamais laisser un fichier
    # tronqué en cas d'interruption pendant l'écriture elle-même.
    result = derive(validate_and_load(raw)).to_json()
    # Écho de l'action qui vient d'être appliquée -- l'état résultant seul ne
    # dit QUE qui parle ensuite, jamais qui vient de parler. Sans ce champ,
    # rien dans la sortie de `pc apply` ne permet de vérifier après coup
    # l'ordre réel des actions adverses : c'est ce trou qui a laissé passer
    # une narration de session dans un ordre différent de celui réellement
    # appliqué au moteur (le coach relisant l'ordre du rendu ASCII -- un plan
    # de table -- au lieu de la séquence de parole). Siège ET label de
    # position, parce que le siège seul ne se relit pas et que le label seul
    # est dérivé (il tourne avec `button_seat` d'une main à l'autre).
    result["applied_to"] = {
        "seat": acting_seat,
        "position": acting_position,
        "action": action,
        "amount": round(amount, 4),
    }

    import os
    import tempfile

    dir_ = os.path.dirname(os.path.abspath(args.hand)) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_, prefix=".hand-", suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, args.hand)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    return result


# --- assert-state ----------------------------------------------------------

def _state_divergences(state, *, street: str | None = None, board: str | None = None,
                        to_act: int | None = None) -> list[str]:
    """Compare l'état réel à ce que l'appelant CROIT être vrai et retourne la
    liste des désaccords (vide si tout concorde). Factorisé entre
    ``pc assert-state`` (tripwire dédié) et ``pc render --expect-*`` (même
    tripwire, mais dans l'appel que le coach fait DÉJÀ avant chaque décision
    -- cf. la note de ``cmd_render``)."""
    errors: list[str] = []

    if street is not None and state.street != street:
        errors.append(f"street attendue {street!r}, état réel {state.street!r}")

    if board is not None:
        try:
            expected_board = parse_cards(_split_card_tokens(board))
        except CardError as exc:
            raise StateError(f"board attendu invalide : {exc}") from exc
        if expected_board != state.board:
            errors.append(
                f"board attendu {[str(c) for c in expected_board]}, "
                f"état réel {[str(c) for c in state.board]}"
            )

    if to_act is not None and state.to_act != to_act:
        errors.append(f"to_act attendu {to_act}, état réel {state.to_act}")

    return errors


def cmd_assert_state(args: argparse.Namespace) -> dict[str, Any]:
    """Tripwire mécanique contre la dérive coach/état (revue live-session) :
    le coach affiche parfois une table écrite à la main au lieu d'appeler
    `pc render`, ou narre une rue sans avoir réellement appelé
    `advance_street.py` -- `hand.json` reste alors bloqué sur la rue
    précédente pendant que le texte affiché au joueur en décrit une autre,
    et les `pc brief`/`pc budget` suivants tournent silencieusement sur le
    mauvais état. Rien dans l'ancien contrat CLI ne pouvait détecter ça
    avant que ses conséquences (une décision prise sur un état fictif) ne
    soient déjà actées. À appeler juste avant d'annoncer une nouvelle rue
    ou de reprendre une main après une pause : échoue bruyamment (code non
    nul, `StateError`) au moindre désaccord plutôt que de laisser la
    session continuer sur une hypothèse fausse."""
    state = _load_state(args.hand)
    errors = _state_divergences(state, street=args.street, board=args.board, to_act=args.to_act)

    if errors:
        raise StateError("assert-state a échoué (l'état réel diverge de ce qui était attendu) : "
                          + " ; ".join(errors))

    return {
        "ok": True,
        "street": state.street,
        "board": [str(c) for c in state.board],
        "to_act": state.to_act,
        # `to_act: null` seul se lit aussi bien « personne ne parle » que
        # « champ absent » -- le booléen dit lequel des deux (cf.
        # `DerivedState.to_json`).
        "runout": is_runout(state),
    }


# --- dispatch ------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pc", description="Moteur déterministe poker-coach v2")
    sub = parser.add_subparsers(dest="command", required=True)

    def hand_arg(p):
        p.add_argument("--hand", required=True, help="chemin vers hand.json")

    p = sub.add_parser("state", help="valide et dérive l'état d'une main")
    hand_arg(p); p.set_defaults(func=cmd_state)

    p = sub.add_parser("hand", help="classe de main, tirage, outs, blockers")
    hand_arg(p)
    p.add_argument("--seat", type=int, default=None)
    p.set_defaults(func=cmd_hand)

    p = sub.add_parser("texture", help="labels de texture du board")
    hand_arg(p); p.set_defaults(func=cmd_texture)

    p = sub.add_parser("line", help="type de pot, rôle, pression pondérée")
    hand_arg(p); p.set_defaults(func=cmd_line)

    p = sub.add_parser("budget", help="ATT/DEF restants + options viables")
    hand_arg(p)
    p.add_argument("--villain-archetype", default=None, choices=["nit", "tag", "lag", "fish", "maniac", "calling_station"])
    p.set_defaults(func=cmd_budget)

    p = sub.add_parser("equity", help="équité range vs range")
    p.add_argument("--hand", default=None, help="hand.json (cartes héros + board), optionnel")
    p.add_argument("--range1", default=None, help="range/main du héros (omis si --hand fournit les cartes)")
    p.add_argument("--vs", required=True, help="range adverse")
    p.add_argument("--board", default=None, help="cartes communes séparées par des virgules")
    p.add_argument("--dead", default=None, help="cartes mortes séparées par des virgules")
    p.add_argument("--iterations", type=int, default=20000)
    p.set_defaults(func=cmd_equity)

    p = sub.add_parser("narrow", help="range adverse après filtrage par action observée")
    hand_arg(p)
    p.add_argument("--action", required=True, choices=["fold", "check", "call", "bet", "raise"])
    p.add_argument("--range", default=None, help="range de départ (défaut : range générique large)")
    p.add_argument("--seat", type=int, default=None,
                    help="siège du villain dont on narrowe la range (défaut : le plus pertinent "
                         "-- dernier agresseur encore en lice, sinon premier autre siège actif)")
    p.add_argument("--villain-archetype", default=None, choices=["nit", "tag", "lag", "fish", "maniac", "calling_station"])
    p.set_defaults(func=cmd_narrow)

    p = sub.add_parser("ranges", help="lookup direct d'un scénario de range dérivé (rfi/vs_rfi/vs_limp/squeeze/vs_3bet/vs_4bet)")
    hand_arg(p)
    p.add_argument("--scenario", required=True,
                    choices=["rfi", "vs_rfi", "vs_limp", "squeeze", "vs_3bet", "vs_4bet"])
    p.add_argument("--seat", type=int, default=None, help="défaut : hero_seat")
    p.add_argument("--opener-seat", type=int, default=None,
                    help="siège de l'ouvreur/agresseur adverse -- requis pour vs_rfi/squeeze si "
                         "aucun agresseur n'est détectable dans l'historique de la main")
    p.add_argument("--villain-archetype", default=None, choices=["nit", "tag", "lag", "fish", "maniac", "calling_station"])
    p.set_defaults(func=cmd_ranges)

    p = sub.add_parser("brief", help="⭐ tout ce qui précède, en un appel")
    hand_arg(p)
    p.add_argument("--villain-archetype", default=None, choices=["nit", "tag", "lag", "fish", "maniac", "calling_station"])
    p.add_argument("--depth", default="gate", choices=["gate", "full"],
                    help="gate (défaut) : verbosité pilotée par le gate qui tranche. "
                         "full : détail complet (ranges narrowées, bornes d'équité) même si un "
                         "gate précoce a déjà tranché — sur demande explicite en session ('on peut "
                         "voir les ranges exactes ?'), le verdict n'est jamais recalculé.")
    p.set_defaults(func=cmd_brief)

    p = sub.add_parser("render", help="dessin ASCII de la table")
    hand_arg(p)
    p.add_argument("--expect-street", default=None, choices=list(STREETS),
                    help="échoue (code non nul) si l'état réel n'est pas sur cette rue — même "
                         "tripwire que pc assert-state, mais dans l'appel déjà fait avant chaque "
                         "décision, donc sans étape supplémentaire à ne pas oublier")
    p.add_argument("--expect-board", default=None,
                    help="échoue si le board réel diffère (cartes séparées par des virgules)")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("showdown", help="résolution déterministe d'un abattage")
    p.add_argument("--from-hand", default=None, metavar="HAND.JSON",
                    help="résout l'abattage DEPUIS l'état canonique : board et cartes connues "
                         "repris de hand.json, échec bruyant si l'état n'est pas à la river ou "
                         "si un argument le contredit. À privilégier en session — sans lui, "
                         "pc showdown ne lit pas hand.json et résoudra un board qui n'a jamais "
                         "existé (cf. cmd_showdown/_showdown_from_state)")
    p.add_argument("--board", default=None,
                    help="requis SANS --from-hand ; avec --from-hand, doit correspondre au board "
                         "de l'état (sinon échec)")
    p.add_argument("--hand", dest="hand_entry", action="append", default=None,
                    metavar="NOM:CARTES", help="ex --hand Hero:Ac,6h --hand HJ:Kd,Td")
    p.set_defaults(func=cmd_showdown)

    p = sub.add_parser("sizing", help="calcul déterministe de %%pot / montant de relance")
    sizing_sub = p.add_subparsers(dest="sizing_cmd", required=True)
    p1 = sizing_sub.add_parser("bet-pct")
    p1.add_argument("--bet", type=float, required=True)
    p1.add_argument("--pot-before", type=float, required=True)
    p2 = sizing_sub.add_parser("raise-to")
    p2.add_argument("--pot-before-bet", type=float, required=True)
    p2.add_argument("--bet-to-call", type=float, required=True)
    p2.add_argument("--fraction", type=float, required=True)
    p3 = sizing_sub.add_parser("preflop-open-to", help="taille d'ouverture/isolation preflop, en bb")
    p3.add_argument("--limpers", type=int, default=0, help="nombre de limpeurs déjà dans le pot (0 = RFI)")
    p3.add_argument("--villain-archetype", default=None,
                     choices=["nit", "tag", "lag", "fish", "maniac", "calling_station"])
    p.set_defaults(func=cmd_sizing)

    p = sub.add_parser("glossary", help="une définition de terme GTO")
    p.add_argument("term")
    p.set_defaults(func=cmd_glossary)

    p = sub.add_parser("apply", help="applique une action et réécrit hand.json")
    hand_arg(p)
    p.add_argument("--action", required=True, help='ex "b 5.5", "c", "x", "f", "r 12"')
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("assert-state", help="vérifie street/board/to_act réels vs attendus -- échoue si divergence")
    hand_arg(p)
    p.add_argument("--street", default=None, choices=list(STREETS))
    p.add_argument("--board", default=None, help="cartes attendues séparées par des virgules")
    p.add_argument("--to-act", type=int, default=None)
    p.set_defaults(func=cmd_assert_state)

    p = sub.add_parser("paths", help="chemins absolus de pokercoach/, data/, docs/ pour ce déploiement")
    p.set_defaults(func=cmd_paths)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
    except (StateError, CardError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
