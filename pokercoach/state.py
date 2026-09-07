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
ARCHETYPES = (None, "nit", "tag", "lag", "fish", "maniac")
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
    to_act: int
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
    for name in STREETS:
        node = raw_streets.get(name)
        if node is None:
            _require(name != "preflop", "streets.preflop est obligatoire")
            streets[name] = None
            continue

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

    to_act = raw.get("to_act")
    _require(isinstance(to_act, int) and 0 <= to_act < n_seats,
              f"to_act invalide : {to_act!r}")
    _require(seats[to_act].status == "active",
              f"to_act (siège {to_act}) n'est pas 'active' (status={seats[to_act].status!r})")

    declared_hero_seat = raw.get("hero_seat")
    if declared_hero_seat is not None:
        _require(declared_hero_seat == hero_seat,
                  f"hero_seat ({declared_hero_seat!r}) incohérent avec seats[].is_hero ({hero_seat})")

    streets = _validate_streets(raw.get("streets"), n_seats)

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
    la mise la plus haute déjà engagée sur la rue courante."""
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
    lice pour le pot (celui qui plafonne ce qui peut être gagné/perdu)."""
    return min(remaining_stack(state, s.seat) for s in state.seats if s.status in ("active", "allin"))


@dataclass
class DerivedState:
    schema_version: str
    street: str
    hero_seat: int
    hero_position: str
    to_act: int
    to_act_position: str
    pot: float
    to_call: float
    pot_odds: float | None
    mdf_collective: float | None
    mdf_individual: float | None
    spr: float | None
    effective_stack: float
    players_active: int
    n_defenders: int

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "street": self.street,
            "hero_seat": self.hero_seat,
            "hero_position": self.hero_position,
            "to_act": self.to_act,
            "to_act_position": self.to_act_position,
            "pot": round(self.pot, 4),
            "to_call": round(self.to_call, 4),
            "pot_odds": None if self.pot_odds is None else round(self.pot_odds, 4),
            "mdf_collective": None if self.mdf_collective is None else round(self.mdf_collective, 4),
            "mdf_individual": None if self.mdf_individual is None else round(self.mdf_individual, 4),
            "spr": None if self.spr is None else round(self.spr, 4),
            "effective_stack": round(self.effective_stack, 4),
            "players_active": self.players_active,
            "n_defenders": self.n_defenders,
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
    pot_odds = call / denom if denom > 0 else None
    mdf_collective = p / denom if denom > 0 else None
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
        hero_seat=state.hero_seat,
        hero_position=labels[state.hero_seat],
        to_act=state.to_act,
        to_act_position=labels[state.to_act],
        pot=p,
        to_call=call,
        pot_odds=pot_odds,
        mdf_collective=mdf_collective,
        mdf_individual=mdf_individual,
        spr=spr,
        effective_stack=eff,
        players_active=players_active(state),
        n_defenders=n_def,
    )
