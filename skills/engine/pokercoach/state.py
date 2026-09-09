"""Couche A — état canonique de la main.

Validation d'un ``hand.json`` (schéma v2, voir docs/brief/references/02-architecture-v2.md)
et dérivation des grandeurs qui ne doivent jamais être stockées : positions,
pot, cotes, MDF, SPR, stack effectif.

Règles dures reprises de l'architecture v2 :

- Les sièges sont physiques et stables sur la session ; seul ``button_seat``
  tourne. Les labels de position (UTG/HJ/CO/BTN/SB/BB) sont toujours dérivés,
  jamais stockés.
- ``amount`` sur une action est le montant TOTAL investi sur la rue par ce
  joueur après l'action, pas l'incrément.
- Tout montant est en big blinds.
- Le pot n'est jamais stocké, toujours dérivé.
- Les cartes sortent en unicode, quelle que soit la notation d'entrée.

Ce module ne fait *pas* la classification de main (``handclass.py``), ni la
lecture de la ligne d'action (``actionline.py``) — seulement l'état brut.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .cards import Card, CardError, parse_card, parse_cards

STREETS = ("preflop", "flop", "turn", "river")
STATUSES = ("active", "folded", "allin", "out")
ARCHETYPES = (None, "nit", "tag", "lag", "fish", "maniac", "calling_station")
ACTIONS = ("post", "fold", "check", "call", "bet", "raise", "allin")

BOARD_SIZE = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}

# Labels de position par nombre de sièges, indexés par écart (offset) au
# bouton en sens horaire : offset 0 = BTN, 1 = SB, 2 = BB, puis les positions
# non-blind dans l'ordre de parole preflop (UTG en premier), jusqu'à CO
# (dernier à parler avant le bouton). Convention standard, cf.
# docs/brief/references/03-multiway-generalization.md.
POSITION_LABELS: dict[int, list[str]] = {
    2: ["BTN/SB", "BB"],
    3: ["BTN", "SB", "BB"],
    4: ["BTN", "SB", "BB", "CO"],
    5: ["BTN", "SB", "BB", "HJ", "CO"],
    6: ["BTN", "SB", "BB", "UTG", "HJ", "CO"],
    7: ["BTN", "SB", "BB", "UTG", "UTG+1", "HJ", "CO"],
    8: ["BTN", "SB", "BB", "UTG", "UTG+1", "MP", "HJ", "CO"],
}

FORMAT_BY_SEAT_COUNT: dict[int, str] = {
    2: "hu",
    3: "6max", 4: "6max", 5: "6max", 6: "6max",
    7: "8max", 8: "8max",
}


class StateError(ValueError):
    """État de main invalide. Le CLI la traduit en sortie stderr + code non nul."""


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise StateError(message)


@dataclass
class Seat:
    seat: int
    is_hero: bool
    stack: float
    status: str
    archetype: str | None = None
    hud: dict[str, Any] | None = None
    cards: list[Card] | None = None


@dataclass
class HandState:
    raw: dict[str, Any]
    seats: list[Seat]
    button_seat: int
    big_blind: float
    ante: float
    hero_seat: int
    # ``None`` : plus aucun siège n'est ``active``, donc plus personne à qui
    # donner la parole — all-in callé (runout) ou tapis couché par tout le
    # monde. Cf. ``is_runout`` et la validation de ``to_act``.
    to_act: int | None
    street: str
    board: list[Card]
    streets: dict[str, dict[str, Any]]

    @property
    def n_seats(self) -> int:
        return len(self.seats)

    @property
    def table_format(self) -> str:
        return FORMAT_BY_SEAT_COUNT[self.n_seats]


def _validate_cards_field(raw_cards: Any, *, context: str) -> list[Card] | None:
    if raw_cards is None:
        return None
    _require(isinstance(raw_cards, list) and len(raw_cards) == 2,
              f"{context} : deux cartes attendues, reçu {raw_cards!r}")
    try:
        return parse_cards(raw_cards)
    except CardError as exc:
        raise StateError(f"{context} : {exc}") from exc


def _validate_seats(raw_seats: Any) -> list[Seat]:
    _require(isinstance(raw_seats, list) and 2 <= len(raw_seats) <= 8,
              "seats : liste de 2 à 8 sièges attendue")

    seats: list[Seat] = []
    hero_count = 0
    for i, raw in enumerate(raw_seats):
        _require(isinstance(raw, dict), f"seats[{i}] : objet attendu")
        _require(raw.get("seat") == i,
                  f"seats[{i}] : siège physique attendu {i}, reçu {raw.get('seat')!r} "
                  "(les sièges doivent être numérotés 0..n-1, sans trou)")

        status = raw.get("status")
        _require(status in STATUSES, f"seats[{i}] : status invalide {status!r}")

        archetype = raw.get("archetype")
        _require(archetype in ARCHETYPES, f"seats[{i}] : archetype invalide {archetype!r}")

        stack = raw.get("stack")
        _require(isinstance(stack, (int, float)) and stack >= 0,
                  f"seats[{i}] : stack invalide {stack!r}")

        is_hero = bool(raw.get("is_hero", False))
        hero_count += int(is_hero)

        cards = _validate_cards_field(raw.get("cards"), context=f"seats[{i}].cards")

        seats.append(Seat(
            seat=i, is_hero=is_hero, stack=float(stack), status=status,
            archetype=archetype, hud=raw.get("hud"), cards=cards,
        ))

    _require(hero_count == 1, f"seats : exactement un siège is_hero attendu, trouvé {hero_count}")
    return seats


def _validate_streets(raw_streets: Any, n_seats: int) -> dict[str, dict[str, Any]]:
    _require(isinstance(raw_streets, dict), "streets : objet attendu")
    _require(raw_streets.get("preflop") is not None, "streets.preflop est obligatoire")

    streets: dict[str, dict[str, Any]] = {}
    prev_board: list[Card] = []
    seen_gap = False
    for name in STREETS:
        node = raw_streets.get(name)
        if node is None:
            _require(name != "preflop", "streets.preflop est obligatoire")
            seen_gap = True
            streets[name] = None
            continue
        # Une fois une rue absente (None) rencontrée, toutes les suivantes
        # doivent l'être aussi -- un "trou" (ex. flop:null puis turn:{...})
        # décrirait une main qui a sauté une rue, ce qui n'existe pas.
        _require(not seen_gap, f"streets.{name} : présente alors qu'une rue précédente est absente "
                                "(trou dans la séquence des rues)")

        _require(isinstance(node, dict), f"streets.{name} : objet attendu")

        board: list[Card] = []
        if name != "preflop":
            raw_board = node.get("board")
            expected = BOARD_SIZE[name]
            _require(isinstance(raw_board, list) and len(raw_board) == expected,
                      f"streets.{name}.board : {expected} cartes attendues")
            try:
                board = parse_cards(raw_board)
            except CardError as exc:
                raise StateError(f"streets.{name}.board : {exc}") from exc
            _require(board[:len(prev_board)] == prev_board,
                      f"streets.{name}.board : incohérent avec le board de la rue précédente")
            prev_board = board

        actions = node.get("actions")
        _require(isinstance(actions, list), f"streets.{name}.actions : liste attendue")
        for j, act in enumerate(actions):
            _require(isinstance(act, dict), f"streets.{name}.actions[{j}] : objet attendu")
            seat = act.get("seat")
            _require(isinstance(seat, int) and 0 <= seat < n_seats,
                      f"streets.{name}.actions[{j}].seat invalide : {seat!r}")
            action = act.get("action")
            _require(action in ACTIONS, f"streets.{name}.actions[{j}].action invalide : {action!r}")
            amount = act.get("amount", 0)
            _require(isinstance(amount, (int, float)) and amount >= 0,
                      f"streets.{name}.actions[{j}].amount invalide : {amount!r}")

        streets[name] = {"board": board, "actions": actions}

    return streets


def validate_and_load(raw: dict[str, Any]) -> HandState:
    """Valide un ``hand.json`` déjà désérialisé et construit l'état typé.

    Lève ``StateError`` sur toute incohérence — jamais de correction silencieuse.
    """
    _require(isinstance(raw, dict), "hand.json : objet JSON attendu à la racine")

    table = raw.get("table")
    _require(isinstance(table, dict), "table : objet attendu")
    big_blind = table.get("big_blind")
    _require(isinstance(big_blind, (int, float)) and big_blind > 0,
              f"table.big_blind invalide : {big_blind!r}")
    ante = table.get("ante", 0.0)
    _require(isinstance(ante, (int, float)) and ante >= 0, f"table.ante invalide : {ante!r}")

    seats = _validate_seats(raw.get("seats"))
    n_seats = len(seats)

    button_seat = table.get("button_seat")
    _require(isinstance(button_seat, int) and 0 <= button_seat < n_seats,
              f"table.button_seat invalide : {button_seat!r}")

    declared_format = table.get("format")
    derived_format = FORMAT_BY_SEAT_COUNT[n_seats]
    if declared_format is not None:
        _require(declared_format == derived_format,
                  f"table.format ({declared_format!r}) incohérent avec {n_seats} sièges "
                  f"(attendu {derived_format!r} — le format est dérivé, jamais stocké)")

    hero_seat = next(s.seat for s in seats if s.is_hero)

    # ``to_act`` : un siège actif, ou ``None`` quand plus AUCUN siège ne peut
    # agir. Deux états terminaux légitimes tombent dans ce cas : le RUNOUT
    # (au moins deux sièges en lice, tous all-in : il ne reste que des cartes
    # à distribuer puis un abattage — cf. ``is_runout``) et la main déjà
    # décidée (un tapis que tout le monde a couché). Sans ce cas, un all-in
    # callé n'avait aucune représentation valide : plus aucun siège n'était
    # 'active', donc tout entier était refusé par le contrôle ci-dessous, et
    # ``to_act: null`` l'était aussi -- ``pc render``/``assert-state``/
    # ``showdown --from-hand`` rejetaient l'état, et la seule issue en
    # session était de remettre des statuts à la main dans hand.json,
    # c-à-d exactement ce que les garde-fous anti-dérive interdisent.
    # Ce qui distingue les deux états terminaux n'est PAS validé ici : c'est
    # ``advance_street.py`` (« la main est déjà décidée, pas de rue suivante »)
    # et ``pc showdown --from-hand`` (« un seul siège en lice, pas
    # d'abattage ») qui refusent le mauvais, avec un message qui dit quoi
    # faire à la place.
    to_act = raw.get("to_act")
    active_seats = [s.seat for s in seats if s.status == "active"]
    if to_act is None:
        _require(not active_seats,
                  f"to_act invalide : null ne vaut que si plus aucun siège ne peut agir, "
                  f"or le(s) siège(s) {active_seats} sont encore 'active'")
    else:
        _require(isinstance(to_act, int) and 0 <= to_act < n_seats,
                  f"to_act invalide : {to_act!r}")
        _require(seats[to_act].status == "active",
                  f"to_act (siège {to_act}) n'est pas 'active' (status={seats[to_act].status!r})"
                  + ("" if active_seats else
                     " — aucun siège n'est 'active' : si tous les sièges en lice sont all-in, "
                     "c'est un runout, et to_act doit valoir null"))

    declared_hero_seat = raw.get("hero_seat")
    if declared_hero_seat is not None:
        _require(declared_hero_seat == hero_seat,
                  f"hero_seat ({declared_hero_seat!r}) incohérent avec seats[].is_hero ({hero_seat})")

    streets = _validate_streets(raw.get("streets"), n_seats)

    # Le statut déclaré d'un siège doit être cohérent avec sa DERNIÈRE action
    # dans l'historique : un siège qui a foldé quelque part ne peut pas être
    # resté "active" (players_active/n_defenders/effective_stack/
    # mdf_individual partiraient tous en vrille), et de même pour un
    # all-in. On ne regarde que la toute dernière action de chaque siège
    # (toutes rues confondues, dans l'ordre) : un siège ne peut plus agir
    # après avoir foldé ou fait tapis, donc c'est forcément son état final.
    last_action_by_seat: dict[int, str] = {}
    for name in STREETS:
        node = streets.get(name)
        if node is None:
            continue
        for act in node["actions"]:
            last_action_by_seat[act["seat"]] = act["action"]
    for seat_idx, last_action in last_action_by_seat.items():
        seat_status = seats[seat_idx].status
        if last_action == "fold":
            _require(seat_status == "folded",
                      f"seats[{seat_idx}].status ({seat_status!r}) incohérent avec son historique "
                      "(a foldé, mais le status déclaré n'est pas 'folded')")
        elif last_action == "allin":
            _require(seat_status == "allin",
                      f"seats[{seat_idx}].status ({seat_status!r}) incohérent avec son historique "
                      "(a fait tapis, mais le status déclaré n'est pas 'allin')")

    # Vérifie l'absence de doublon parmi toutes les cartes connues (héros,
    # villains révélés, board cumulé le plus avancé).
    known: list[Card] = []
    for s in seats:
        if s.cards:
            known.extend(s.cards)
    current_street = next(name for name in reversed(STREETS) if streets[name] is not None)
    known.extend(streets[current_street]["board"])
    seen: set[tuple[str, str]] = set()
    for c in known:
        key = (c.rank, c.suit)
        _require(key not in seen, f"carte en double dans l'état de la main : {c}")
        seen.add(key)

    return HandState(
        raw=raw, seats=seats, button_seat=button_seat, big_blind=float(big_blind),
        ante=float(ante), hero_seat=hero_seat, to_act=to_act, street=current_street,
        board=streets[current_street]["board"], streets=streets,
    )


# --- Dérivations ---------------------------------------------------------

def position_labels(state: HandState) -> dict[int, str]:
    """Label de position par siège physique, dérivé de ``button_seat``."""
    n = state.n_seats
    labels = POSITION_LABELS[n]
    return {
        (state.button_seat + offset) % n: label
        for offset, label in enumerate(labels)
    }


def preflop_acting_order_offsets(n: int) -> list[int]:
    """Ordre de parole préflop, en écarts au bouton (0=BTN). UTG (ou
    équivalent) parle en premier, la BB en dernier — cf.
    docs/brief/references/03-multiway-generalization.md."""
    if n == 2:
        return [0, 1]  # BTN/SB agit en premier en HU, puis BB
    return list(range(3, n)) + [0, 1, 2]


def postflop_acting_order_offsets(n: int) -> list[int]:
    """Ordre de parole postflop, en écarts au bouton (0=BTN). La SB parle en
    premier (ou la BB en heads-up, où offset 1 = BB), le bouton toujours en
    dernier — le bouton est la seule position en position contre tout le
    monde, quel que soit le format."""
    return list(range(1, n)) + [0]


def n_behind(state: HandState, seat: int) -> int:
    """Nombre de joueurs qui doivent encore parler derrière ``seat`` au
    premier tour de parole préflop (mesure STRUCTURELLE, indépendante des
    folds déjà survenus — c'est la clé d'indexation des ranges, pas un
    décompte en direct)."""
    n = state.n_seats
    offset = (seat - state.button_seat) % n
    order = preflop_acting_order_offsets(n)
    return len(order) - 1 - order.index(offset)


def seats_still_to_act(state: HandState, *, seat: int | None = None) -> list[int]:
    """Sièges encore ACTIFS qui doivent encore parler sur la rue courante,
    ``seat`` (``to_act`` par défaut) exclu.

    Un siège doit encore parler tant qu'il n'a pas, DEPUIS la dernière mise
    ou relance de la rue, à la fois agi volontairement ET égalé la mise la
    plus haute. C'est une lecture de l'HISTORIQUE de la rue, jamais une
    position dans l'ordre de parole : dès que l'action a été rouverte
    (check -> bet -> call -> retour au checkeur, ou une relance qui rend la
    parole à des sièges déjà passés), les sièges placés "après" le héros
    dans l'ordre structurel ont justement DÉJÀ parlé — c'est précisément
    pour ça que l'action lui revient.

    Régression (revue de PR #9) : la première version prenait une tranche de
    l'ordre structurel (UTG->BB préflop, SB->BTN postflop) filtrée aux
    sièges actifs. Elle répondait donc 2 — et ``hero_closes_action`` False —
    sur n'importe quelle ligne check->bet->call qui rend la parole au héros,
    alors que payer y clôt la rue. Ces champs étant exposés tels quels dans
    ``pc state``/``pc brief`` comme LA réponse mécanique à "reste-t-il
    quelqu'un à parler derrière moi", c'était exactement l'erreur de
    position (« le coach affirme à tort que le héros ne ferme pas
    l'action ») que ce champ avait été ajouté pour supprimer.

    Un siège all-in ne peut plus agir : il n'est pas compté ici, alors qu'il
    l'est dans ``players_active``/``n_defenders`` (encore en lice pour le
    pot, mais plus dans l'ordre de parole).
    """
    seat = state.to_act if seat is None else seat
    if seat is None:
        return []  # plus aucun siège actif : personne derrière personne
    actions = state.streets[state.street]["actions"]

    max_committed = max(
        (street_contribution(state, state.street, s.seat) for s in state.seats
         if s.status in ("active", "allin")),
        default=0.0,
    )

    # Dernière action agressive de la rue : elle rouvre la parole à tous
    # ceux qui l'avaient déjà prise avant elle. Une action n'est agressive
    # que si elle AUGMENTE réellement le maximum engagé sur la rue -- un
    # tapis pour MOINS que la mise en cours (3 sur une mise à 4) est un
    # call partiel, pas une relance : il ne rouvre rien, et le compter
    # comme tel remettait à tort les sièges déjà couchés sur la mise dans
    # les "encore à parler". Les blindes (``post``) ne sont pas des mises
    # volontaires -- la BB garde son option même sans relance -- donc elles
    # n'ouvrent rien non plus ; c'est la comparaison des contributions qui
    # porte le cas préflop. Sans agression sur la rue (-1), la condition
    # ci-dessous se lit naturellement "a-t-il parlé volontairement, tout
    # court ?".
    #
    # Simplification connue (même famille que les side pots ailleurs dans
    # le moteur) : un tapis qui relance SANS atteindre une relance complète
    # est traité ici comme une relance pleine. Les règles de salle ne
    # rouvrent alors la parole qu'à une partie des joueurs ; ce cas
    # demanderait de suivre l'incrément de la dernière relance complète.
    last_aggression = -1
    running_max = 0.0
    for i, act in enumerate(actions):
        amount = float(act.get("amount", 0.0))
        if act["action"] in ("bet", "raise", "allin") and amount > running_max:
            last_aggression = i
        running_max = max(running_max, amount)

    def has_spoken_since_last_aggression(other: int) -> bool:
        return any(
            i >= last_aggression and act["seat"] == other and act["action"] != "post"
            for i, act in enumerate(actions)
        )

    return [
        s.seat for s in state.seats
        if s.seat != seat and s.status == "active"
        and not (
            has_spoken_since_last_aggression(s.seat)
            and street_contribution(state, state.street, s.seat) >= max_committed
        )
    ]


def players_to_act_behind(state: HandState, *, seat: int | None = None) -> int:
    """Nombre de sièges encore actifs devant parler après ``seat``
    (``to_act`` par défaut) sur la rue courante — ``len`` de
    ``seats_still_to_act``, dont c'est la docstring de référence. 0 signifie
    que ``seat`` clôt l'action sur cette rue si personne ne relance derrière
    lui."""
    return len(seats_still_to_act(state, seat=seat))


def hero_closes_action(state: HandState) -> bool:
    """``True`` si ``to_act`` est le dernier siège encore actif à parler sur
    la rue courante (aucun joueur actif derrière lui) -- dérivé booléen de
    ``players_to_act_behind`` pour simplifier l'usage côté skill.

    ``False`` quand plus personne ne peut agir (runout, ou ``to_act`` à
    ``None`` sur une main déjà décidée) : il n'y a plus d'action du tout,
    donc le héros n'en « ferme » aucune. La lecture mécanique
    (``players_to_act_behind == 0``) y répondrait ``True``, ce qui se lit
    « c'est au héros de conclure la rue » -- l'inverse de la réalité. Le
    champ ``runout`` de ``pc state``/``pc render`` est ce qui distingue les
    deux cas, pas ce booléen.
    """
    if state.to_act is None or is_runout(state):
        return False
    return players_to_act_behind(state) == 0


def ip_postflop(state: HandState, seat: int) -> bool:
    """Le héros sera-t-il en position après le flop contre le caller le plus
    probable ? Simplifié en : ``seat`` est-il le bouton ? (le bouton est
    toujours le dernier à parler postflop, quel que soit le format —
    cf. 03-multiway-generalization.md, tableau de référence)."""
    return seat == state.button_seat


def street_contribution(state: HandState, street: str, seat: int) -> float:
    """Montant total investi par ``seat`` sur ``street`` (0 s'il n'a pas agi)."""
    node = state.streets.get(street)
    if node is None:
        return 0.0
    amount = 0.0
    for act in node["actions"]:
        if act["seat"] == seat:
            amount = float(act.get("amount", 0.0))
    return amount


def total_invested(state: HandState, seat: int) -> float:
    """Montant total investi par ``seat`` sur l'ensemble de la main (toutes rues)."""
    return sum(street_contribution(state, s, seat) for s in STREETS if state.streets.get(s) is not None)


def pot(state: HandState, *, upto_street: str | None = None) -> float:
    """Pot dérivé : somme des contributions de rue de chaque siège, cumulée
    jusqu'à ``upto_street`` inclus (rue courante par défaut)."""
    upto_street = upto_street or state.street
    total = 0.0
    for street in STREETS:
        node = state.streets.get(street)
        if node is None:
            break
        for seat in state.seats:
            total += street_contribution(state, street, seat.seat)
        if street == upto_street:
            break
    return total


def remaining_stack(state: HandState, seat: int) -> float:
    """Stack restant = stack de départ moins tout ce qui a été investi sur la main."""
    s = state.seats[seat]
    return s.stack - total_invested(state, seat)


def to_call(state: HandState, *, seat: int | None = None) -> float:
    """Montant que ``seat`` (par défaut ``to_act``) doit ajouter pour suivre
    la mise la plus haute déjà engagée sur la rue courante.

    ``0.0`` quand ``to_act`` vaut ``None`` (plus aucun siège ne peut agir) :
    personne n'a rien à suivre. Sans ce cas, le siège ``None`` ne
    correspondait à aucune action de la rue -- sa contribution tombait à 0 et
    ``to_call`` renvoyait la mise maximale, un montant « à suivre »
    entièrement fictif.
    """
    if seat is None and state.to_act is None:
        return 0.0
    seat = state.to_act if seat is None else seat
    node = state.streets[state.street]
    max_committed = max(
        (street_contribution(state, state.street, s.seat) for s in state.seats
         if s.status in ("active", "allin")),
        default=0.0,
    )
    return max(0.0, max_committed - street_contribution(state, state.street, seat))


def players_active(state: HandState) -> int:
    """Sièges encore en lice pour le pot (actifs ou all-in), fold/out exclus."""
    return sum(1 for s in state.seats if s.status in ("active", "allin"))


def is_runout(state: HandState) -> bool:
    """La main est-elle en RUNOUT : au moins deux sièges encore en lice, et
    plus aucune décision à prendre ?

    C'est l'état d'un all-in callé : il ne reste que des cartes à distribuer
    (``advance_street.py``) jusqu'à l'abattage (``pc showdown``).

    Deux formes, à ne pas confondre — la seconde est celle qu'on rate :
    - plus AUCUN siège actif (tous les sièges en lice sont all-in) :
      ``to_act`` vaut alors ``None`` ;
    - UN seul siège actif, dont la mise est déjà égalée, face à des tapis :
      il ne peut ni suivre (rien à suivre) ni miser (personne pour payer),
      mais il reste ``active``, donc ``to_act`` pointe encore sur lui. Sans
      ce second cas, ``pc brief`` conseillait volontiers « une décision » au
      héros quand c'est lui le payeur le plus profond -- une décision qui
      n'existe pas.

    Dérivé des statuts et de l'historique, jamais stocké — comme le reste
    ici (positions, format, pot). Un champ ``runout: true`` dans
    ``hand.json`` serait une seconde source de vérité, libre de contredire
    ``seats[].status`` ; ``to_act: null`` en est la conséquence validée,
    pas une donnée indépendante.
    """
    if players_active(state) < 2:
        return False  # main déjà décidée (tapis couché par tout le monde), pas un runout
    active = [s.seat for s in state.seats if s.status == "active"]
    if not active:
        return True
    if len(active) > 1:
        return False  # au moins deux sièges peuvent encore se répondre
    return to_call(state, seat=active[0]) <= 0


def no_decision_left(state: HandState) -> str | None:
    """Pourquoi il n'y a plus aucune décision à prendre sur cette main, en une
    phrase qui dit quoi faire à la place — ou ``None`` s'il en reste une.

    Les deux états terminaux se ressemblent (``to_act`` vaut ``None`` dans un
    cas sur deux) mais n'appellent PAS la même suite : un runout se déroule
    (``advance_street.py``) puis s'abat (``pc showdown``) ; une main que tout
    le monde a couchée n'a ni rue à ouvrir ni abattage, le pot revient tel
    quel. Factorisé ici précisément parce que les trois gardes appelantes
    (``pc apply``, ``pc budget``, ``pc brief``) avaient chacune recopié la
    condition et confondu les deux : elles renvoyaient toutes « runout,
    dérouler le board », y compris sur un tapis que tout le monde avait
    couché -- l'utilisateur qui suivait le conseil se faisait alors
    rattraper par ``advance_street.py`` (« la main est déjà décidée »), un
    détour évitable avec une information déjà sous la main.
    """
    if is_runout(state):
        return ("l'all-in est déjà callé (runout) — dérouler le board avec advance_street.py, "
                "puis résoudre par pc showdown")
    if state.to_act is None:
        return ("la main est déjà décidée (tout le monde a couché) — attribuer le pot "
                "directement, il n'y a ni rue à dérouler ni abattage")
    return None


def n_defenders(state: HandState) -> int:
    """Nombre de sièges encore ACTIFS (peuvent encore agir) qui font face à la
    mise la plus haute de la rue courante sans l'avoir encore égalée —
    ``to_act`` inclus. 1 en heads-up standard ; peut monter en multiway,
    c'est le dénominateur du MDF individuel (voir ``derive``)."""
    max_committed = max(
        (street_contribution(state, state.street, s.seat) for s in state.seats
         if s.status in ("active", "allin")),
        default=0.0,
    )
    return sum(
        1 for s in state.seats
        if s.status == "active" and street_contribution(state, state.street, s.seat) < max_committed
    )


def effective_stack(state: HandState, *, seat: int | None = None) -> float:
    """Stack effectif : le plus petit stack restant parmi les sièges encore en
    lice pour le pot (celui qui plafonne ce qui peut être gagné/perdu).

    Avec ``seat`` : le stack effectif DE CE SIÈGE précisément, c-à-d le
    plafond entre son propre stack et le plus petit stack adverse encore en
    lice (ce que ce siège peut réellement gagner/perdre face à la table).
    Sans ``seat`` (défaut) : le plus petit stack parmi tous les sièges en
    lice, toute la table.
    """
    in_hand = [s.seat for s in state.seats if s.status in ("active", "allin")]
    if seat is None:
        return min(remaining_stack(state, s) for s in in_hand)
    others = [s for s in in_hand if s != seat]
    if not others:
        return remaining_stack(state, seat)
    return min(remaining_stack(state, seat), min(remaining_stack(state, s) for s in others))


@dataclass
class DerivedState:
    schema_version: str
    street: str
    board: list[Card]
    hero_seat: int
    hero_position: str
    to_act: int | None
    to_act_position: str | None
    runout: bool
    pot: float
    to_call: float
    pot_odds: float | None
    mdf_collective: float | None
    mdf_individual: float | None
    spr: float | None
    effective_stack: float
    players_active: int
    n_defenders: int
    players_to_act_behind: int
    hero_closes_action: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "street": self.street,
            # Régression (revue live-session) : ni `pc state` ni `pc brief`
            # n'exposaient le board dans leur en-tête d'état -- seulement
            # `street`. Un coach qui narre une rue à la main (au lieu
            # d'appeler `pc render`/`pc advance_street.py`) peut dériver
            # sans que rien dans la sortie structurée ne le signale : `pc
            # brief`/`pc state` continuent de tourner sur la VRAIE rue en
            # mémoire pendant que le texte affiché au joueur en décrit une
            # autre. Le board explicite ici rend cette dérive visible d'un
            # coup d'œil (et vérifiable mécaniquement, cf. `pc assert-state`).
            "board": [str(c) for c in self.board],
            "hero_seat": self.hero_seat,
            "hero_position": self.hero_position,
            "to_act": self.to_act,
            "to_act_position": self.to_act_position,
            # Plus aucune décision à prendre : all-in callé. `to_act` seul
            # ne suffit pas à le dire -- `null` se lit aussi bien « personne
            # ne parle » que « champ manquant », et il peut même pointer
            # encore sur un siège (le payeur le plus profond, resté
            # `active`). Ce booléen tranche, et c'est lui qui explique
            # pourquoi `hero_closes_action` vaut `false` alors que plus
            # personne n'a à parler derrière le héros.
            "runout": self.runout,
            "pot": round(self.pot, 4),
            "to_call": round(self.to_call, 4),
            "pot_odds": None if self.pot_odds is None else round(self.pot_odds, 4),
            "mdf_collective": None if self.mdf_collective is None else round(self.mdf_collective, 4),
            "mdf_individual": None if self.mdf_individual is None else round(self.mdf_individual, 4),
            "spr": None if self.spr is None else round(self.spr, 4),
            "effective_stack": round(self.effective_stack, 4),
            "players_active": self.players_active,
            "n_defenders": self.n_defenders,
            "players_to_act_behind": self.players_to_act_behind,
            "hero_closes_action": self.hero_closes_action,
        }


def derive(state: HandState) -> DerivedState:
    """Calcule le paquet de dérivations de base : pot, cotes, MDF, SPR, qui parle.

    ``pot_odds`` = to_call / (pot + to_call) — équité requise pour un call rentable.

    MDF — piège théorique documenté dans data/multiway-adjustment.yaml : en
    heads-up un seul joueur porte l'obligation de défense, en multiway elle
    est COLLECTIVE (c'est la fréquence de fold *combinée* qui doit rester
    sous le seuil, donc chaque défenseur individuel peut folder davantage).
    Appliquer le MDF heads-up tel quel en multiway conduit à SUR-défendre —
    exactement un des modes de perte documentés de l'utilisateur.

    ``mdf_collective`` = pot / (pot + to_call) — la formule heads-up
    classique, ici interprétée comme l'obligation COMBINÉE de tous les
    défenseurs encore à agir sur cette mise.
    ``mdf_individual`` = 1 - (1 - mdf_collective) ** (1 / n_defenders) —
    approximation (non un résultat exact, cf. le YAML) dérivée de :
    la mise n'est auto-rentable pour l'agresseur QUE SI tous les défenseurs
    foldent ; avec ``n_defenders`` défenseurs indépendants foldant chacun à
    fréquence ``f``, cet événement a probabilité ``f ** n_defenders`` — on
    résout pour ``f`` en l'égalant à ``1 - mdf_collective``, puis
    ``mdf_individual = 1 - f``. En heads-up (``n_defenders == 1``), les deux
    valeurs coïncident.
    ``spr`` = effective_stack / pot.
    """
    labels = position_labels(state)
    p = pot(state)
    call = to_call(state)
    denom = p + call
    # Les deux ne sont définis QUE s'il y a une vraie mise à suivre (call > 0)
    # — pas seulement un pot non nul. Bug corrigé : avec l'ancienne garde
    # (denom > 0), to_call == 0 donnait pot_odds = 0.0 et mdf = 1.0 au lieu
    # de None dès que le pot était non nul (systématique dès la 2e rue) —
    # des valeurs numériques trompeuses pour "il n'y a rien à comparer", qui
    # ont fait passer une décision check/bet par la logique de bornes
    # d'équité de G3 (pc brief) comme si un seuil de rentabilité existait.
    pot_odds = call / denom if call > 0 else None
    mdf_collective = p / denom if call > 0 else None
    n_def = n_defenders(state)
    mdf_individual = (
        1 - (1 - mdf_collective) ** (1 / n_def)
        if mdf_collective is not None and n_def > 0 else mdf_collective
    )
    eff = effective_stack(state)
    spr = eff / p if p > 0 else None

    return DerivedState(
        schema_version=str(state.raw.get("schema_version", "2.0")),
        street=state.street,
        board=state.board,
        hero_seat=state.hero_seat,
        hero_position=labels[state.hero_seat],
        to_act=state.to_act,
        to_act_position=None if state.to_act is None else labels[state.to_act],
        runout=is_runout(state),
        pot=p,
        to_call=call,
        pot_odds=pot_odds,
        mdf_collective=mdf_collective,
        mdf_individual=mdf_individual,
        spr=spr,
        effective_stack=eff,
        players_active=players_active(state),
        n_defenders=n_def,
        players_to_act_behind=players_to_act_behind(state),
        hero_closes_action=hero_closes_action(state),
    )
