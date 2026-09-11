"""Couche B — budget ATT/DEF : le mécanisme central repris de PokerSkill.

Formule (data/att-def-budgets.yaml) :
    ATT_restant = base(classe, contexte) - pression déjà DÉPENSÉE par le héros
    DEF_restant = base(classe, contexte) - pression déjà SUBIE par le héros

``inf`` (illimité) est représenté par ``float("inf")``.

Ordre d'application des ajustements (celui qui produit le résultat le plus
défendable compte tenu de ce que chaque étage modélise) :
1. Base par classe/contexte (att-def-budgets.yaml).
2. Pénalités de texture (texture-modifiers.yaml, cumulatives sauf les deux
   exceptions documentées).
3. Correction multiway (data/multiway-adjustment.yaml) — calibrée HU 200bb,
   PROPOSITION NON CALIBRÉE pour le multiway, cf. le fichier lui-même.
4. Règles dures multiway (bluff meurt à 3+ adversaires).
5. Gates exploitantes G4 (archétype adverse), si un archétype est connu.
6. Décrément par la pression déjà engagée dans la main.

Limite connue (revue) : aucun étage ci-dessus ne modélise les implied/reverse
implied odds -- le budget DEF d'un tirage reflète la pression déjà subie,
pas ce qu'un tirage touché pourrait extraire ensuite (ou risque de perdre)
sur les tapis restants. C'est le point où un fold "DEF insuffisant" est le
plus susceptible d'être trop prudent en multiway contre des calling
stations ; ``compute()`` l'expose alors comme note plutôt que de prétendre
le corriger ici -- ce facteur reste qualitatif (skill decision-factors,
gate G5), pas chiffré dans ces tables.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .handclass import HandClass
from .texture import Texture

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INF = float("inf")


@lru_cache(maxsize=1)
def _att_def() -> dict:
    with open(DATA_DIR / "att-def-budgets.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def _texture_mods() -> dict:
    with open(DATA_DIR / "texture-modifiers.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def _multiway() -> dict:
    with open(DATA_DIR / "multiway-adjustment.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _as_float(v: Any) -> float:
    if v == "inf" or v is None:
        return INF
    return float(v)


def _leaf(d: dict) -> tuple[float, float]:
    return _as_float(d.get("att", 0.0)), _as_float(d.get("def", 0.0))


def _row_by_when(matrix: list[dict], when: list[str]) -> dict:
    """Cherche dans une ``priority_matrix`` (ex. ``two_pair`` dans
    att-def-budgets.yaml) la ligne dont le champ ``when`` correspond
    EXACTEMENT à ``when`` (comparaison en ensemble, ordre indifférent) —
    plutôt que d'indexer positionnellement (``matrix[N]``), ce qui rendait
    la sémantique du lookup dépendante de l'ordre des lignes dans le YAML
    (réordonner le fichier changeait silencieusement quel budget sortait).
    Lève une erreur claire si la ligne attendue n'existe pas, plutôt qu'un
    ``IndexError``/``KeyError`` sans contexte."""
    when_set = frozenset(when)
    for row in matrix:
        if frozenset(row.get("when", [])) == when_set:
            return row
    raise KeyError(f"priority_matrix : aucune ligne avec when={sorted(when)!r}")


@dataclass
class Budget:
    att_base: float
    def_base: float
    att_after_penalties: float
    def_after_penalties: float
    att_remaining: float
    def_remaining: float
    viable_actions: list[str]
    removed: list[dict[str, str]]
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        def fmt(x: float) -> Any:
            return "inf" if x == INF else round(x, 3)
        return {
            "att_base": fmt(self.att_base), "def_base": fmt(self.def_base),
            "att_after_penalties": fmt(self.att_after_penalties),
            "def_after_penalties": fmt(self.def_after_penalties),
            "att_remaining": fmt(self.att_remaining), "def_remaining": fmt(self.def_remaining),
            "viable_actions": self.viable_actions,
            "removed": self.removed,
            "notes": self.notes,
        }


# --- Base par classe -----------------------------------------------------

# Classes dont la force se lit "une paire + un kicker" : celles qui ont une
# entrée dans `pair_class_penalties` (texture-modifiers.yaml) et dont le
# budget dépend du `pot_type`.
PAIR_FAMILY = ("overpair", "top_pair", "second_pair", "third_pair", "fourth_fifth_pair",
               "weak_showdown", "underpair", "nuts_high", "second_high")


def effective_pair_class(hc: HandClass) -> str | None:
    """Classe de la famille "paire simple" qui porte la force RÉELLE de la
    main, ou ``None`` si la main n'en relève pas.

    Deux cas rendent autre chose que ``hc.made`` :
    - ``two_pair`` dont une moitié vient du board (paire servie + board
      apparié, cf. ``handclass``) : c'est ``made_sub.strength_proxy`` qui
      décide, pas la table ``two_pair`` (calibrée board non apparié) ;
    - toute autre classe hors famille paire : ``None``.

    Utilisé par les trois étages où la classe de paire compte : baseline,
    pénalités de texture, et le test "cette ligne est-elle un bluff ?"."""
    if hc.made == "two_pair" and hc.made_sub.get("includes_board_pair"):
        return hc.made_sub.get("strength_proxy")
    if hc.made in PAIR_FAMILY:
        return hc.made
    return None


def _base_made_hands(hc: HandClass, pot_type: str, texture: Texture) -> tuple[float, float]:
    table = _att_def()["made_hands"]
    made = hc.made

    if made == "nuts":
        return INF, INF

    if made == "flush":
        node = table["flush"]["by_board"]
        bt = hc.made_sub.get("board_type", "three_flush")
        rb = hc.made_sub.get("rank_bucket", "small")
        branch = node.get(bt, node["three_flush"])
        leaf = branch.get(rb) or branch.get("small") or {"att": 0, "def": 1}
        return _leaf(leaf)

    if made == "straight":
        node = table["straight"]
        contribution = hc.made_sub.get("contribution", "two_card")
        flushiness = hc.made_sub.get("board_flushiness", "no_flush")
        branch = node.get(contribution, node["two_card"])
        leaf = branch.get(flushiness, branch.get("no_flush", {"att": 0, "def": 0}))
        att, deff = _leaf(leaf)
        if hc.made_sub.get("paired_board"):
            att += node.get("paired_board_delta", 0.0)
        return att, deff

    if made in ("set", "trips"):
        node = table[made if made == "trips" else "set"]
        flushiness = hc.made_sub.get("board_flushiness", "no_flush")
        straight_poss = hc.made_sub.get("straight_possibility")
        if made == "set":
            if flushiness == "four_plus_flush":
                leaf = node["four_plus_flush_no_ocs"]
            elif straight_poss == "two_possibilities":
                leaf = node["ocs_two_plus"]
            elif straight_poss == "one_possibility":
                leaf = node["ocs_one_type"]
            elif flushiness == "three_flush":
                leaf = node["three_flush_no_ocs"]
            else:
                leaf = node["no_flush_no_straight"]
            return _leaf(leaf)
        else:  # trips (kicker-interpolated)
            frac = hc.made_sub.get("kicker_frac", 0.5)
            if flushiness == "four_plus_flush":
                leaf = node["four_plus_flush_no_ocs"]
                return _leaf(leaf)
            if straight_poss == "two_possibilities":
                branch = node["ocs_two_plus"]
            elif straight_poss == "one_possibility":
                branch = node["ocs_one_type"]
            elif flushiness == "three_flush":
                branch = node["three_flush_no_ocs"]
            else:
                branch = node["dry_board"]
            lo, hi = _as_float(branch["att_min"]), _as_float(branch["att_max"])
            att = lo + frac * (hi - lo)
            return att, _as_float(branch["def"])

    if made == "two_pair" and hc.made_sub.get("includes_board_pair"):
        # La moitié "paire du board" est partagée par tous les joueurs : seule
        # la paire servie départage. `att-def-budgets.yaml` le dit dans ses
        # propres notes two_pair ("force réelle ~ top/middle paire") -- on
        # applique la note plutôt que la table, qui suppose deux paires que
        # l'adversaire n'a pas.
        return _base_pair_family(hc.made_sub.get("strength_proxy") or "underpair",
                                  hc, pot_type, table)

    if made == "two_pair":
        matrix = table["two_pair"]["priority_matrix"]
        suit = texture.suit
        # straight_shape "gutshot"/"open_ended" sert de proxy à ocs_types "one"/"two_plus"
        # (nombre de rangs manquants distincts qui complètent une quinte -- même
        # notion que le nombre de "possibilités" de quinte une-carte).
        ocs_key = {"gutshot": "one", "open_ended": "two_plus"}.get(texture.straight_shape)

        if suit == "four_plus_flush" and ocs_key is not None:
            return _leaf(_row_by_when(matrix, ["four_plus_flush", "one_card_straight"])["value"])
        if suit == "four_plus_flush":
            return _leaf(_row_by_when(matrix, ["four_plus_flush"])["value"])
        if ocs_key is not None and suit == "three_flush":
            return _leaf(_row_by_when(matrix, ["one_card_straight", "three_flush"])["value_by_ocs_types"][ocs_key])
        if ocs_key is not None:
            return _leaf(_row_by_when(matrix, ["one_card_straight"])["value_by_ocs_types"][ocs_key])

        rb = hc.made_sub.get("rank_bucket", "r10")
        idx = int(rb[1:]) if rb.startswith("r") else 10
        if suit == "three_flush":
            by_rank = _row_by_when(matrix, ["three_flush"])["value_by_rank"]
            att = by_rank["att_r1"] + (idx - 1) / 9 * (by_rank["att_r10"] - by_rank["att_r1"])
            deff = by_rank["def_r1"] + (idx - 1) / 9 * (by_rank["def_r10"] - by_rank["def_r1"])
            return att, deff
        by_rank = _row_by_when(matrix, ["dry"])["value_by_rank"]
        return _leaf(by_rank.get(f"r{idx}", by_rank["r10"]))

    if made in PAIR_FAMILY:
        return _base_pair_family(made, hc, pot_type, table)

    if made == "trash":
        node = table["trash"]
        rng = node["att_flop_turn"]
        return (rng["min"] + rng["max"]) / 2, _as_float(node["def"])

    return 0.0, 0.0


def _pair_kicker_keys(cls: str, sub: dict) -> tuple[str, ...]:
    """Colonnes de kicker à essayer, dans l'ordre, pour ``cls``.

    Les tables ne nomment pas cette colonne pareil d'une classe à l'autre :
    ``second_pair`` a ``pocket_or_top_kicker`` en SRP mais ``pocket`` et
    ``top_kicker`` SÉPARÉS en 3BP/4BP, ``third_pair`` a
    ``top_kicker_or_pocket``, et ``fourth_fifth_pair`` n'a pas de colonne de
    kicker du tout mais ``fourth``/``fifth``. Un mapping à une seule
    orthographe (``tptk -> pocket_or_top_kicker``) tombait donc dans le repli
    ``other`` pour third_pair et pour les pots relancés -- et dans RIEN du tout
    pour fourth_fifth_pair, dont le nœud SRP n'a ni cette clé ni ``other``
    (budget att=0/def=0 rendu au lieu de 0.8/1.8). On essaie toutes les
    orthographes, paire servie d'abord quand les deux colonnes coexistent."""
    if cls == "fourth_fifth_pair":
        return ("fifth",) if sub.get("board_ranks_above", 3) >= 4 else ("fourth",)
    kb = sub.get("kicker_bucket", "other")
    if kb == "tptk":
        if sub.get("pocket_pair"):
            return ("pocket", "pocket_or_top_kicker", "top_kicker_or_pocket", "top_kicker")
        return ("top_kicker", "pocket_or_top_kicker", "top_kicker_or_pocket", "pocket")
    return {"tpsk": ("k2",), "k3": ("k3",)}.get(kb, ())


def _pocket_pair_special(cls: str, hc: HandClass, pot_type: str, table: dict) -> tuple[float, float] | None:
    """Ligne ``three_bet_plus_special.pocket_pair`` de ``third_pair`` /
    ``fourth_fifth_pair`` : la paire SERVIE surclassée en 3BP/4BP ("paire
    servie surclassée, seulement 2 outs"). Plus basse que la ligne générique
    de la classe, et pour cause -- une paire servie n'a que 2 outs pour
    s'améliorer, là où une paire qui touche le board peut encore toucher son
    kicker. Jamais atteinte tant que ces mains sortaient en ``underpair``."""
    if not hc.made_sub.get("pocket_pair"):
        return None
    special = table[cls].get("three_bet_plus_special", {}).get("pocket_pair")
    if special is None:
        return None
    key = {"three_bet_pot": "def_3bp", "four_bet_pot": "def_4bp"}.get(pot_type)
    if key is None:
        return None
    return _as_float(special.get("att", 0.0)), _as_float(special.get(key, 0.0))


def _base_pair_family(cls: str, hc: HandClass, pot_type: str, table: dict) -> tuple[float, float]:
    """Baseline d'une classe de la famille "paire simple". ``cls`` est passé
    explicitement (et non lu dans ``hc.made``) pour que la double paire dont
    une moitié vient du board puisse emprunter la ligne de son proxy de
    force -- cf. ``effective_pair_class``."""
    if cls == "overpair":
        node = table["overpair"]["by_pot_type"].get(pot_type, table["overpair"]["by_pot_type"]["srp_limp"])
        pocket = hc.made_sub.get("pocket_rank", "other")
        leaf = node.get(pocket, node["other"])
        return _leaf(leaf)

    if cls == "top_pair":
        node = table["top_pair"]["by_pot_type"].get(pot_type, table["top_pair"]["by_pot_type"]["srp"])
        kb = hc.made_sub.get("kicker_bucket", "other")
        leaf = node.get(kb, node["other"])
        return _leaf(leaf)

    if cls in ("second_pair", "third_pair", "fourth_fifth_pair"):
        special = _pocket_pair_special(cls, hc, pot_type, table)
        if special is not None:
            return special
        node = table[cls]["by_pot_type"].get(pot_type)
        if node is None:
            node = table[cls]["by_pot_type"].get("srp") or table[cls]["by_pot_type"].get("srp_limp", {})
        leaf = None
        for key in _pair_kicker_keys(cls, hc.made_sub):
            if isinstance(node.get(key), dict):
                leaf = node[key]
                break
        if leaf is None and isinstance(node.get("other"), dict):
            leaf = node["other"]
        if leaf is None:
            # Table sans colonne de kicker (3BP/4BP de third/fourth_fifth :
            # un `def` nu, pas d'ATT) -- pas un défaut, la forme du YAML.
            return 0.0, _as_float(node.get("def", 0.0))
        return _leaf(leaf)

    if cls in ("nuts_high", "second_high"):
        node = table[cls]
        pt_key = {"limp": "limp", "srp": "srp", "three_bet_pot": "three_bet_pot",
                  "four_bet_pot": "four_bet_pot"}.get(pot_type, "srp")
        rng = node["def_by_pot_type"].get(pt_key, node["def_by_pot_type"]["srp"])
        deff = (rng["min"] + rng["max"]) / 2
        return _as_float(node.get("att", 0.0)), deff

    # `underpair` (paire de poche sous tout le board) réutilise la baseline de
    # `weak_showdown` -- même profil de showdown marginal, aucune calibration
    # dédiée dans l'annexe E source (curseur, pas une vérité figée).
    node = table["weak_showdown"]["by_pot_type"]
    key = "three_bet_pot" if pot_type == "three_bet_pot" else ("four_bet_pot" if pot_type == "four_bet_pot" else "limp_srp")
    return _leaf(node[key])


def _base_draw(hc: HandClass) -> tuple[float, float | None]:
    """ATT du tirage (utile en combo avec une main faible) et combo_bonus_def
    (à additionner à la baseline DEF de la main faite, pas un DEF cumulé)."""
    if hc.draw is None:
        return 0.0, None
    node = _att_def()["draws"][hc.draw]
    att = node["att"]
    att = (att["min"] + att["max"]) / 2 if isinstance(att, dict) else _as_float(att)
    return att, node.get("combo_bonus_def", 0.0)


# --- Pénalités de texture --------------------------------------------------

def _apply_texture_penalties(att: float, deff: float, made: str, texture: Texture, street: str) -> tuple[float, float, list[str]]:
    """``made`` est la classe EFFECTIVE (cf. ``effective_pair_class``), pas
    forcément ``hc.made`` : une double paire dont une moitié vient du board
    doit encaisser les mêmes pénalités de texture que la paire simple dont
    elle emprunte la force -- à commencer par le malus "board apparié", qui
    la concerne par construction."""
    mods = _texture_mods()["pair_class_penalties"]
    notes: list[str] = []
    if made not in PAIR_FAMILY:
        return att, deff, notes

    if texture.suit == "four_plus_flush":
        node = mods["one_card_flush"]
        if made in ("nuts_high", "second_high"):
            deff = 0.0
        elif made == "overpair":
            att, deff = 0.0, min(deff, node["overpair"]["def_cap"])
        else:
            entry = node.get(made)
            if entry and "levels" in entry:
                deff = max(0.0, deff + entry["levels"])
                att = max(0.0, att + entry["levels"])
        notes.append("board 4+ couleur, hors couleur : pénalité sévère")
    elif texture.suit == "three_flush":
        node = mods["flush_possible_three_flush"]
        key = "high_card_classes_by_street" if made in ("nuts_high", "second_high") else "by_street"
        delta = node[key].get(street, 0.0)
        att += delta
        deff += delta

    if texture.straight_shape == "open_ended":
        if made in ("nuts_high", "second_high"):
            deff = 0.0
        else:
            deff += mods["one_card_straight_open_ended"]["default"]["levels"]
            att += mods["one_card_straight_open_ended"]["default"]["levels"]
    elif texture.straight_shape == "gutshot":
        deff += mods["one_card_straight_gutshot"]["default"]["levels"]
        att += mods["one_card_straight_gutshot"]["default"]["levels"]

    if texture.rank_labels[0] in ("paired", "double_paired", "trips", "quads"):
        pb = mods["paired_board"]
        if made in ("nuts_high", "second_high"):
            deff *= pb["high_card_multiplier"]
        elif made in ("overpair", "top_pair"):
            deff += pb["pairs_delta"]
        elif made == "second_pair":
            deff += pb["mid_low_pairs_delta"]
        else:
            deff += pb["low_pairs_delta"]

    return max(0.0, att), max(0.0, deff), notes


# --- Multiway ---------------------------------------------------------------

def _apply_multiway(att: float, deff: float, made: str, draw: str | None, n_opponents_active: int) -> tuple[float, float, list[dict]]:
    removed: list[dict] = []
    if n_opponents_active <= 1:
        return att, deff, removed
    mw = _multiway()["multiway_adjustment"]
    extra = n_opponents_active - 1
    if att != INF:
        att *= mw["att_multiplier_per_extra_opponent"] ** extra
    if deff != INF:
        deff = max(0.0, deff + mw["def_delta_per_extra_opponent"] * extra)

    if n_opponents_active >= 3 and (draw is not None or made == "trash"):
        if att > 0:
            removed.append({"action": "bet/raise (bluff/tirage)",
                             "reason": "bluff_dies_multiway : ATT=0 dès 3+ adversaires actifs"})
        att = 0.0
    return att, deff, removed


# --- Gate exploitante G4 -----------------------------------------------------

def _apply_exploit_gate(att: float, made: str, draw: str | None, villain_archetype: str | None,
                         is_bluff_line: bool, street_index: int) -> tuple[float, list[dict], list[str]]:
    removed: list[dict] = []
    notes: list[str] = []
    if villain_archetype in ("fish", "calling_station") and is_bluff_line and street_index >= 2:
        if att > 0:
            removed.append({"action": "bet/raise (bluff)",
                             "reason": "bluff_multi_street_blocked : fold equity quasi nulle contre un calling station"})
        att = 0.0
        notes.append("G4 : bluff_multi_street_blocked appliqué")
    return att, removed, notes


# --- Orchestration ------------------------------------------------------------

STREET_INDEX = {"preflop": 0, "flop": 1, "turn": 2, "river": 3}


def compute(hc: HandClass, texture: Texture, *, pot_type: str, street: str,
            n_opponents_active: int, pressure_spent: float, pressure_faced: float,
            villain_archetype: str | None = None, facing_bet: bool = True) -> Budget:
    """``facing_bet`` distingue les deux binômes d'options réels : face à une
    mise, c'est raise/call/fold (DEF gate le call) ; sans mise à suivre,
    c'est bet/check/fold — le check est TOUJOURS gratuit et viable, ce n'est
    plus DEF qui le gate (bug corrigé : avant, "call" restait proposé même
    à to_call == 0, et le fallback de la gate G2 pouvait rendre "call" sur
    une décision de check/bet)."""
    att_base, def_base = _base_made_hands(hc, pot_type, texture)
    draw_att, combo_bonus_def = _base_draw(hc)
    # Classe de paire effective : `hc.made` sauf pour une double paire dont
    # une moitié vient du board, qui emprunte la force de son proxy.
    pair_class = effective_pair_class(hc) or hc.made

    # Une main faible + un tirage : l'ATT du tirage gouverne (semi-bluff),
    # et le bonus de combo s'ajoute à la baseline DEF de la main faite.
    att = max(att_base, draw_att) if hc.draw else att_base
    deff = def_base + (combo_bonus_def or 0.0) if hc.draw and combo_bonus_def else def_base

    att, deff, tex_notes = _apply_texture_penalties(att, deff, pair_class, texture, street)
    att_after_pen, def_after_pen = att, deff

    att, deff, mw_removed = _apply_multiway(att, deff, hc.made, hc.draw, n_opponents_active)

    # Une paire servie surclassée par 2+ rangs du board (le set-mining raté)
    # reste une ligne de bluff pour la gate G4, même maintenant qu'elle est
    # classée `third_pair`/`fourth_fifth_pair` plutôt qu'`underpair` : c'est
    # exactement le leak documenté (s'acharner à bluffer en se sentant
    # "commité"), la reclassification ne doit pas le décoiffer.
    pocket_outranked = (hc.made_sub.get("pocket_pair")
                        and hc.made_sub.get("board_ranks_above", 0) >= 2)
    is_bluff_line = (pair_class in ("trash", "weak_showdown", "underpair")
                     or hc.draw is not None or bool(pocket_outranked))
    street_index = STREET_INDEX.get(street, 0)
    att, exploit_removed, exploit_notes = _apply_exploit_gate(
        att, hc.made, hc.draw, villain_archetype, is_bluff_line, street_index)

    att_remaining = INF if att == INF else max(0.0, att - pressure_spent)
    def_remaining = INF if deff == INF else max(0.0, deff - pressure_faced)

    aggressive_label = "raise" if facing_bet else "bet"

    viable = []
    removed = list(mw_removed) + list(exploit_removed)
    budget_notes: list[str] = []
    if att_remaining > 0:
        viable.append(aggressive_label)
    else:
        removed.append({"action": aggressive_label,
                         "reason": f"budget ATT insuffisant ({round(att_remaining, 2)} <= 0)"})
    if facing_bet:
        if def_remaining > 0:
            viable.append("call")
        else:
            removed.append({"action": "call", "reason": f"budget DEF insuffisant ({round(def_remaining, 2)} <= 0)"})
            # Limite connue (revue) : att-def-budgets.yaml ne modélise AUCUNE
            # implied odds -- le "def" d'un tirage n'est qu'une pression déjà
            # subie, pas ce qu'un tirage touché pourrait encore extraire des
            # tapis adverses. C'est exactement le cas où ce repli DEF-épuisé
            # est le plus susceptible de sous-évaluer un call : un tirage,
            # multiway, contre des adversaires qui paient large. Le signaler
            # ici plutôt que de prétendre trancher -- l'ajustement chiffré
            # appartient au skill decision-factors (gate G5), pas à ce module
            # mécanique.
            if hc.draw is not None and n_opponents_active >= 2:
                budget_notes.append(
                    "implied odds non modélisées : ce fold DEF-épuisé porte sur un tirage en "
                    f"multiway ({n_opponents_active} adversaires actifs) -- si un ou plusieurs "
                    "adversaires paient large (calling station), la vraie valeur du call peut "
                    "être supérieure au DEF chiffré ici ; cf. glossaire 'implied odds' / skill "
                    "decision-factors."
                )
        viable.append("fold")
    else:
        viable.append("check")  # toujours gratuit, jamais gaté par DEF

    return Budget(
        att_base=att_base, def_base=def_base,
        att_after_penalties=att_after_pen, def_after_penalties=def_after_pen,
        att_remaining=att_remaining, def_remaining=def_remaining,
        viable_actions=viable, removed=removed, notes=tex_notes + exploit_notes + budget_notes,
    )
