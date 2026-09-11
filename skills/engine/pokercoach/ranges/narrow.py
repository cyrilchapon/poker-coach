"""Range narrowing mécanique : filtre une range adverse aux combos dont le
budget ATT/DEF rend l'action observée viable, plutôt que de la resserrer "à
l'oeil". C'est le même moteur (handclass + texture + budget) qui juge le
héros, appliqué à chaque combo adverse hypothétique.

Mécanisme de rétention des bluffs (ajouté suite à une revue) : un filtre
purement binaire (combo gardé à 100% si viable, jeté à 0% sinon) fait
converger la range vers "100% mains faites, 0% bluff" dès que la pression
accumulée épuise le budget ATT de toutes les classes faibles/tirages — sur
un spot 3-barrels rivière mesuré, `vs_range_wide`/`vs_range_narrow`
tombaient toutes deux à des mains faites uniquement (sets/two pair), avec
des bornes d'équité G3 dégénérées à exactement [0.0, 0.0] : plus une
mesure d'incertitude, un artefact. Un villain réel n'est pas parfaitement
polarisé à ce point. Les combos dont le budget est épuisé PAR LA PRESSION
(pas par une règle structurelle comme "bluff_dies_multiway" ou
"bluff_multi_street_blocked", qui représentent "cette ligne n'a
structurellement aucun sens" et restent donc à zéro) sont retenus à un
poids plancher plutôt que rejetés entièrement — encodé dans le
``range_str`` de sortie via la notation ``combo@xx%`` déjà supportée par
``equity.parse_range``, pour que ce poids réduit se propage réellement
(et pas seulement "ce combo existe encore dans la liste, à 100%").

``MIN_BLUFF_FLOOR_WEIGHT`` n'est PAS calibré sur des données réelles (cf.
README, section calibration) — un plancher modeste et délibérément rond,
suffisant pour que les bornes G3 restent informatives plutôt qu'un
artefact à équité nulle, pas une fréquence de bluff précise.

Plancher FIXE, pas multiplicatif (régression revue #2) : un combo reçoit le
poids CONSTANT ``MIN_BLUFF_FLOOR_WEIGHT`` quand il est floored, jamais
``wc.weight * MIN_BLUFF_FLOOR_WEIGHT``. Comme ``brief._narrow_through_history``
rejoue le narrowing rue par rue en réinjectant le ``range_str`` de sortie
dans l'entrée de la rue suivante, un poids multiplicatif se compose à
chaque rue où le combo reste floored (0.08 -> 0.0064 -> 0.000512 mesuré sur
trois rues) : les bornes G3 redeviennent quasi dégénérées (largeur ~0.0005
contre un ``UNCERTAINTY_BAND`` de 0.04) — exactement l'artefact que ce
mécanisme existe pour éviter. Un plancher, par définition, ne doit pas
s'éroder rue après rue.

Conséquence sur les compteurs de sortie, à lire attentivement (rapport de
bug : `remaining_combos` restait égal à `original_combos` sur check/bet/call
alors que `retained_pct` variait) : le plancher RETIENT un combo non viable,
il ne le SUPPRIME pas. Un combo ne disparaît de la range de sortie que s'il
est bloqué par le board ou coupé par une règle structurelle. `to_json()`
sépare donc explicitement les trois populations — `combos_kept_full_weight`,
`combos_kept_at_bluff_floor`, `combos_removed` — et dit dans `note` que
`retained_pct` est une part de POIDS, jamais un compte de combos. Les deux
chiffres ne sont pas incohérents : ils ne mesurent simplement pas la même
chose, et c'est `retained_pct` qui porte le filtrage.

Ce qui N'EST PAS corrigé ici (cause distincte, toujours ouverte, cf.
README) : le critère de viabilité lui-même (``action in b.viable_actions``)
reste lâche à budget FRAIS -- une main `trash` a un ATT de base non nul,
donc peu de combos sont exclus au tout début d'une main (avant que la
pression n'ait eu le temps de s'accumuler). C'est une question de
calibration des seuils de base (``data/att-def-budgets.yaml``), pas de
mécanisme -- corriger le mécanisme de rétention ci-dessus ne la résout pas.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..budget import Budget, compute as compute_budget
from ..cards import Card
from ..equity import WeightedCombo, parse_range
from ..handclass import classify
from ..texture import classify as classify_texture

FACING_BET_ACTIONS = ("call", "raise")     # une mise existe déjà, l'adversaire y répond
NOT_FACING_BET_ACTIONS = ("check", "bet")  # rien à suivre, l'adversaire ouvre l'action
ALL_ACTIONS = FACING_BET_ACTIONS + NOT_FACING_BET_ACTIONS + ("fold",)

MIN_BLUFF_FLOOR_WEIGHT = 0.08


@dataclass
class NarrowResult:
    """Résultat d'un narrowing. Trois compteurs de combos SÉPARÉS, parce que
    "combo présent dans la range de sortie" et "combo qui joue vraiment cette
    action" ne sont pas la même chose ici (cf. le mécanisme de plancher
    ci-dessus) — les confondre a produit un `remaining_combos` égal à
    `original_combos` quelle que soit l'action, à côté d'un `retained_pct`
    qui, lui, variait : incohérent à la lecture."""

    action: str
    filters_combos: bool
    original_combos: int
    kept_full_weight: int
    kept_at_floor: int
    removed_combos: int
    remaining_weight: float
    original_weight: float
    range_str: str

    @property
    def remaining_combos(self) -> int:
        """Combos encore présents (poids > 0) dans ``range_str``."""
        return self.kept_full_weight + self.kept_at_floor

    @property
    def retained_pct(self) -> float:
        """Part de la range CONSERVÉE, en POIDS (combos × poids), pas en
        nombre de combos : c'est cette grandeur-là qui porte le filtrage,
        puisqu'un combo non viable est déprécié au plancher plutôt que
        supprimé."""
        if not self.original_weight:
            return 0.0
        return round(100 * self.remaining_weight / self.original_weight, 1)

    def _note(self) -> str:
        if not self.filters_combos:
            return (f"action={self.action!r} : AUCUN filtrage (un fold ne dit rien de positif sur "
                    "la range restante ; un check est un signal trop faible pour filtrer). La range "
                    "de sortie est la range d'entrée moins les combos bloqués par le board, et "
                    "retained_pct vaut 100% par construction — ce n'est pas une mesure de lecture.")
        if self.kept_at_floor:
            return (f"retained_pct est PONDÉRÉ, pas un compte de combos : {self.kept_at_floor} combo(s) "
                    f"dont le budget ATT/DEF ne justifie pas {self.action!r} sont RETENUS au poids "
                    f"plancher de {MIN_BLUFF_FLOOR_WEIGHT:.0%} (anti-polarisation, cf. docstring du "
                    "module), pas supprimés — d'où un remaining_combos proche (voire égal) à "
                    "original_combos alors que retained_pct chute. Seuls les combos coupés par une "
                    "règle structurelle (multiway, gate exploitante) disparaissent vraiment.")
        return (f"retained_pct est PONDÉRÉ (combos × poids). Aucun combo n'a été retenu au plancher : "
                f"les {self.removed_combos} combo(s) écarté(s) l'ont été par une règle structurelle "
                "(multiway, gate exploitante) et sont réellement absents de la range de sortie.")

    def to_json(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "filters_combos": self.filters_combos,
            "original_combos": self.original_combos,
            "remaining_combos": self.remaining_combos,
            "combos_kept_full_weight": self.kept_full_weight,
            "combos_kept_at_bluff_floor": self.kept_at_floor,
            "combos_removed": self.removed_combos,
            "bluff_floor_weight": MIN_BLUFF_FLOOR_WEIGHT,
            "retained_pct": self.retained_pct,
            "retained_pct_basis": "poids (combos × poids), pas nombre de combos",
            "range": self.range_str,
            "note": self._note(),
        }


_STRUCTURAL_ZERO_MARKERS = ("bluff_dies_multiway", "bluff_multi_street_blocked")


def _pressure_exhausted(b: Budget, action: str) -> bool:
    """True si ``action`` est absente de ``b.viable_actions`` UNIQUEMENT
    parce que le budget ATT a été épuisé par la pression déjà dépensée --
    False si elle a été coupée par une règle structurelle (multiway,
    exploit gate), qui doit rester un vrai zéro plutôt que de recevoir le
    plancher de rétention.

    Piège évité ici : ``budget.compute()`` ajoute TOUJOURS une entrée
    générique "budget ATT insuffisant" dès que ``att_remaining <= 0``, que
    ce zéro vienne de la pression OU d'une règle structurelle qui a déjà
    remis ``att`` à 0 en amont -- les deux entrées coexistent alors dans
    ``removed``. Ne se fier qu'au message générique aurait donc flooré à
    tort des combos coupés par une règle structurelle (ex. `bluff_dies_
    multiway` à 3+ adversaires) ; on vérifie donc d'abord qu'aucun marqueur
    structurel n'est présent pour le côté agressif avant de considérer
    l'épuisement par pression. Les règles structurelles ne portent que sur
    ATT (bet/raise), jamais sur DEF (call) -- restreint donc aux deux."""
    if action in ("bet", "raise") and any(
        marker in r["reason"] for r in b.removed for marker in _STRUCTURAL_ZERO_MARKERS
    ):
        return False
    return any(
        r["action"] == action and "insuffisant" in r["reason"]
        for r in b.removed
    )


def _combo_token(wc: WeightedCombo) -> str:
    base = f"{wc.combo[0]}{wc.combo[1]}"
    if wc.weight >= 1.0 - 1e-9:
        return base
    pct = wc.weight * 100
    # Fragilité latente (revue #2) : un ``.2f`` fixe sérialise tout poids
    # positif sous 0.00005 en "0.00%" -> reparsé comme un poids nul ->
    # ZeroDivisionError dans equity._enumerate_equity si ça arrive à TOUS
    # les combos gardés. Avec le plancher fixe actuel (MIN_BLUFF_FLOOR_WEIGHT
    # = 8%) ça ne se produit pas, mais rien ne le garantit si ce plancher
    # est recalibré plus bas -- on élargit donc la précision plutôt que de
    # supposer que le poids sérialisé restera toujours assez grand.
    decimals = 2
    while round(pct, decimals) == 0 and decimals < 10:
        decimals += 1
    return f"{base}@{pct:.{decimals}f}%"


def narrow(range_str: str, board: list[Card], action: str, *, pot_type: str, street: str,
           n_opponents_active: int = 1, pressure_spent: float = 0.0, pressure_faced: float = 0.0,
           villain_archetype: str | None = None) -> NarrowResult:
    """``action`` : "fold"/"check"/"call"/"bet"/"raise" — l'action réellement
    observée. "fold" et "check" ne filtrent pas (un fold ne dit rien de
    positif sur la range restante ; un check est un signal trop faible,
    presque toute main peut checker — approximation documentée, pas un
    modèle de fréquence de check par classe)."""
    if action not in ALL_ACTIONS:
        raise ValueError(f"action inconnue pour le narrowing : {action!r}")
    facing_bet = action in FACING_BET_ACTIONS
    no_filter = action in ("fold", "check")

    board_set = set(board)
    combos = [wc for wc in parse_range(range_str) if not (set(wc.combo) & board_set)]
    texture = classify_texture(board)

    kept: list[WeightedCombo] = []
    kept_full_weight = 0
    kept_at_floor = 0
    for wc in combos:
        if no_filter:
            kept.append(wc)
            kept_full_weight += 1
            continue
        hc = classify(list(wc.combo), board)
        b = compute_budget(
            hc, texture, pot_type=pot_type, street=street, n_opponents_active=n_opponents_active,
            pressure_spent=pressure_spent, pressure_faced=pressure_faced,
            villain_archetype=villain_archetype, facing_bet=facing_bet,
        )
        if action in b.viable_actions:
            kept.append(wc)
            kept_full_weight += 1
        elif _pressure_exhausted(b, action):
            # Poids plancher CONSTANT, pas `wc.weight * MIN_BLUFF_FLOOR_WEIGHT`
            # (régression revue #2, cf. docstring du module) : sinon un combo
            # floored sur plusieurs rues consécutives voit son poids s'éroder
            # multiplicativement au lieu de rester à un plancher stable.
            kept.append(WeightedCombo(combo=wc.combo, weight=MIN_BLUFF_FLOOR_WEIGHT))
            kept_at_floor += 1
        # sinon : coupé par une règle structurelle (multiway/exploit) -- rejeté entièrement

    original_weight = sum(c.weight for c in combos)
    remaining_weight = sum(c.weight for c in kept)
    kept_str = ",".join(_combo_token(c) for c in kept)

    return NarrowResult(
        action=action, filters_combos=not no_filter,
        original_combos=len(combos),
        kept_full_weight=kept_full_weight, kept_at_floor=kept_at_floor,
        removed_combos=len(combos) - len(kept),
        remaining_weight=remaining_weight, original_weight=original_weight,
        range_str=kept_str,
    )
