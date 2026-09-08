"""Lookup paramétré : RFI tabulée (data/preflop-rfi.yaml) + scénarios dérivés
par transformation (jamais une table par scénario — voir
docs/brief/references/03-multiway-generalization.md, §"Ajustements dérivés").

Les notations de range de ``data/preflop-rfi.yaml`` sont déjà dans la
grammaire acceptée par ``equity.parse_range`` — aucune conversion requise.

Honnêteté sur la précision (reprise telle quelle de 03-multiway-generalization.md) :
les scénarios dérivés (vs_rfi, vs_limp, squeeze, vs_3bet, vs_4bet) sont des
FORMULES D'APPROXIMATION originales, pas des tables tabulées ni des sorties
de solveur. Toujours ``confidence: extrapolated``. Le curseur exact
(facteurs, largeurs) est un candidat de calibration post-usage, pas une
vérité figée — voir data/preflop-rfi.yaml pour l'importeur prévu
(``pc ranges import``, non implémenté en v2.0).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..state import HandState, effective_stack, ip_postflop as derive_ip_postflop, n_behind as derive_n_behind

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# Nombre total de combos de départ dans le deck -- C(52,2), PAS "les combos
# par type de main" (régression revue #2 : le nom précédent, _COMBOS_PER_TYPE,
# disait l'inverse de la ligne). Le nombre de combos par type est 6/4/12
# selon paire/suited/offsuit -- c'est _combo_count() ci-dessous. TOTAL_COMBOS
# sert de dénominateur pour convertir un pourcentage en cible de combos dans
# top_pct_range().
TOTAL_COMBOS = 1326  # C(52,2)


def _combo_count(hand_type: str) -> int:
    if len(hand_type) == 2:  # paire, ex. "AA"
        return 6
    return 4 if hand_type[2] == "s" else 12


@lru_cache(maxsize=1)
def _rfi_doc() -> dict:
    with open(DATA_DIR / "preflop-rfi.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def _strength_ranking() -> list[str]:
    """Les 169 types de main, du plus fort au plus faible par équité brute
    contre une range aléatoire -- cf. data/hand-strength-ranking.yaml pour
    la méthode et les limites documentées de cette approximation."""
    with open(DATA_DIR / "hand-strength-ranking.yaml", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    return [row["hand"] for row in doc["ranking"]]


def top_pct_range(pct: float) -> str:
    """Range parseable (``equity.parse_range``) représentant le TOP ``pct``%
    des combos de départ par équité brute, en cumulant les types du
    classement (data/hand-strength-ranking.yaml) jusqu'à couvrir ce
    pourcentage de combos. Matérialise en notation réelle les scénarios
    dérivés (vs_rfi, squeeze, vs_3bet, vs_4bet) qui ne connaissent qu'un
    pourcentage de continuation, pas une liste de mains -- sans quoi ces
    scénarios restaient du code mort (aucun moyen de tester "la main du
    héros est-elle dans ce X% ?»)."""
    pct = max(0.0, min(100.0, pct))
    target_combos = pct / 100.0 * TOTAL_COMBOS
    included: list[str] = []
    cumulative = 0.0
    for hand_type in _strength_ranking():
        if cumulative >= target_combos:
            break
        count = _combo_count(hand_type)
        # Ce type ferait-il dépasser la cible ? L'ancien code l'incluait
        # alors systématiquement (régression revue #2 : biais permanent vers
        # le haut, ex. top_pct_range(1.0) -> 1,36% au lieu de 1,0% car
        # AA,KK,QQ=18 combos est inclus alors qu'AA,KK=12 combos en est plus
        # proche). On choisit désormais la borne la plus proche de la cible
        # -- sauf pour le tout premier type, toujours inclus (sinon une
        # cible trop petite renverrait une range vide).
        if included and cumulative + count > target_combos:
            distance_without = target_combos - cumulative
            distance_with = cumulative + count - target_combos
            if distance_without < distance_with:
                break
        included.append(hand_type)
        cumulative += count
    return ",".join(included)


@dataclass
class RangeEntry:
    scenario: str
    range: str
    pct: float
    confidence: str
    note: str | None = None
    strategy: str = "pure"          # "pure" | "mixed_raise_limp"
    raise_range: str | None = None  # renseigné seulement si strategy == "mixed_raise_limp"
    limp_range: str | None = None

    def to_json(self) -> dict[str, Any]:
        d = {"scenario": self.scenario, "range": self.range, "pct": round(self.pct, 1),
             "confidence": self.confidence}
        if self.note:
            d["note"] = self.note
        if self.strategy == "mixed_raise_limp":
            d["strategy"] = self.strategy
            d["raise_range"] = self.raise_range
            d["limp_range"] = self.limp_range
        return d


def stack_bucket(bb_stack: float) -> str:
    if bb_stack < 40:
        return "short"
    if bb_stack <= 120:
        return "standard"
    return "deep"


@dataclass
class RangeKey:
    scenario: str
    n_behind: int
    ip_postflop: bool
    n_callers_before: int
    stack_bucket: str


def derive_key(state: HandState, seat: int, *, scenario: str = "rfi", n_callers_before: int = 0) -> RangeKey:
    return RangeKey(
        scenario=scenario,
        n_behind=derive_n_behind(state, seat),
        ip_postflop=derive_ip_postflop(state, seat),
        n_callers_before=n_callers_before,
        stack_bucket=stack_bucket(effective_stack(state, seat=seat)),
    )


def _rfi_row(n_behind: int, ip_postflop: bool) -> dict | None:
    for row in _rfi_doc()["rfi"]:
        if row["n_behind"] == n_behind and row["ip_postflop"] == ip_postflop:
            return row
    return None


def rfi(key: RangeKey) -> RangeEntry:
    row = _rfi_row(key.n_behind, key.ip_postflop)
    if row is None:
        # BB (n_behind=0) n'ouvre pas ; au-delà de 7 n'existe pas en 8-max.
        return RangeEntry(scenario="rfi", range="", pct=0.0, confidence="n/a",
                           note="pas de scénario RFI pour cette position (ex. BB)")
    if row.get("strategy") == "mixed_raise_limp":
        # SB vs BB : deux buckets disjoints (raise / limp), pas une fréquence
        # par main — arbitrage utilisateur, voir data/preflop-rfi.yaml
        # (strategie_sb) et skills/live-session pour la doctrine pédagogique.
        raise_range, limp_range = row["raise_range"], row["limp_range"]
        return RangeEntry(
            scenario="rfi", range=f"{raise_range},{limp_range}", pct=row["pct"],
            confidence=row["confidence"], note=row.get("usual_label"),
            strategy="mixed_raise_limp", raise_range=raise_range, limp_range=limp_range,
        )
    return RangeEntry(scenario="rfi", range=row["range"], pct=row["pct"],
                       confidence=row["confidence"], note=row.get("usual_label"))


def _nearest_rfi_row_for_opener(opener_n_behind: int) -> dict:
    """L'ouvreur adverse n'a pas d'``ip_postflop`` connu depuis le seul
    n_behind du héros ; on privilégie la ligne non-IP (la plus courante pour
    une ouverture), à défaut la plus proche disponible."""
    rows = [r for r in _rfi_doc()["rfi"] if r["n_behind"] == opener_n_behind]
    if not rows:
        rows = sorted(_rfi_doc()["rfi"], key=lambda r: abs(r["n_behind"] - opener_n_behind))
        return rows[0]
    non_ip = [r for r in rows if not r["ip_postflop"]]
    return non_ip[0] if non_ip else rows[0]


def vs_rfi(key: RangeKey, *, opener_n_behind: int, villain_archetype: str | None = None,
           iso_over_limp: bool = False) -> RangeEntry:
    """Défense face à une ouverture. Formule d'approximation (pas une table) :
    la largeur de défense est mise à l'échelle de la force implicite de
    l'ouverture adverse (une ouverture UTG => plus forte => on défend plus
    serré ; une ouverture BTN => plus large => on défend plus large).

    ``range`` est maintenant une vraie notation parseable (top_pct_range),
    pas seulement la prose "~X% (largeur approximée)" — nécessaire pour que
    ``pc brief`` puisse tester "la main du héros est-elle dedans ?" (avant,
    ce champ ne pouvait être qu'affiché, jamais vérifié — code mort).

    ``villain_archetype`` (régression : accepté par ``pc brief`` mais jamais
    transmis jusqu'ici) et ``iso_over_limp`` (relance par-dessus un limp, pas
    dans un pot vierge -- cf. ``brief._is_a_raise_over_a_limp``) resserrent
    ou élargissent le pct d'ouverture supposé de l'agresseur AVANT de le
    comparer à ``reference_widest_pct`` -- voir ``ARCHETYPE_AGGRESSOR_FACTOR``
    / ``ISO_OVER_LIMP_FACTOR`` ci-dessus pour le raisonnement et le statut de
    curseur de ces facteurs."""
    # La BB (n_behind=0) n'ouvre jamais, donc n'a pas de ligne RFI propre —
    # on prend la SB (n_behind=1, non-IP) comme plafond de référence pour
    # tout défenseur sans ligne RFI directe (approximation documentée).
    ceiling = _rfi_row(key.n_behind, key.ip_postflop) or _rfi_row(1, False)
    opener = _nearest_rfi_row_for_opener(opener_n_behind)
    opener_pct = opener["pct"] * _archetype_factor(villain_archetype)
    if iso_over_limp:
        opener_pct *= ISO_OVER_LIMP_FACTOR
    reference_widest_pct = 45.0  # BTN 6-max, l'open le plus large de la table
    factor = min(1.0, opener_pct / reference_widest_pct)
    pct = round(ceiling["pct"] * factor, 1)
    note = f"vs ouverture {opener.get('usual_label', '?')} (pct {opener['pct']}%)"
    if villain_archetype:
        note += f" ; resserré/élargi pour l'archétype {villain_archetype!r}"
    if iso_over_limp:
        note += " ; relance par-dessus un limp (isolation) -- resserré davantage"
    return RangeEntry(scenario="vs_rfi", range=top_pct_range(pct), pct=pct,
                       confidence="extrapolated", note=note)


def vs_limp(key: RangeKey) -> RangeEntry:
    """Isolation face à un limp — scénario exploitant de première classe
    (quasi absent des ressources GTO, très fréquent au niveau de l'utilisateur).
    Élargie par rapport à la RFI standard.

    ``range`` reste ``row.range`` (la range RFI curée à la main), pas
    ``top_pct_range(pct)`` (régression revue #2) : c'est le seul des cinq
    scénarios dérivés qui disposait déjà d'une donnée curée et déjà
    parseable -- la remplacer par une bande synthétique par équité brute
    l'aurait rendue strictement moins fiable sans rien gagner en
    testabilité, contrairement à vs_rfi/squeeze/vs_3bet/vs_4bet qui n'
    avaient qu'un pourcentage de continuation, aucune liste de mains."""
    row = rfi(key)
    if row.pct == 0:
        return row
    pct = round(min(100.0, row.pct * 1.3), 1)
    return RangeEntry(scenario="vs_limp", range=row.range, pct=pct, confidence="extrapolated",
                       note="isolation élargie face à un limp — traiter en scénario exploitant, pas dégénéré")


def squeeze(key: RangeKey, *, opener_n_behind: int, villain_archetype: str | None = None) -> RangeEntry:
    base = vs_rfi(key, opener_n_behind=opener_n_behind, villain_archetype=villain_archetype)
    if base.pct == 0:
        return base
    pct = round(base.pct * 0.6, 1)
    return RangeEntry(scenario="squeeze", range=top_pct_range(pct), pct=pct,
                       confidence="extrapolated",
                       note="squeeze : range de vs_rfi resserrée et polarisée (top-pct%, pas une "
                            "vraie polarisation value/bluff -- top_pct_range() ne sait produire "
                            "qu'un intervalle contigu par force brute, cf. limite documentée)")


_VS_3BET_BASE = {True: 45.0, False: 30.0}    # ip_postflop -> pct de continuation
_VS_4BET_BASE = {True: 15.0, False: 10.0}
_STACK_ADJUST = {"short": 1.15, "standard": 1.0, "deep": 0.9}

# Combien un archétype adverse élargit ou resserre la range qu'on lui prête
# quand IL est l'agresseur (relance/3bet/4bet), multiplicatif sur son pct
# d'ouverture supposé. Curseur qualité/coût (même statut que UNCERTAINTY_BAND
# dans gates.py) -- valeurs de départ, à ajuster après usage réel, pas une
# vérité figée. "fish"/"calling_station" sont volontairement RESSERRÉS malgré
# leur image large : un joueur loose-passif qui choisit quand même de
# relancer le fait rarement en bluff -- l'action elle-même est le signal, pas
# son image de table générale (qui, elle, gouverne plutôt sa largeur de CALL,
# cf. att-def-budgets.yaml/G4). "nit"/"tag" resserrent aussi (peu/prudemment
# agressifs) ; "lag"/"maniac" élargissent (agressent avec beaucoup plus de
# mains). Valeur par défaut (``None`` ou archétype non listé) : 1.0, aucun
# ajustement -- comportement inchangé sans ``--villain-archetype``.
ARCHETYPE_AGGRESSOR_FACTOR: dict[str | None, float] = {
    "nit": 0.6, "tag": 0.9, "lag": 1.3, "fish": 0.5, "maniac": 1.6, "calling_station": 0.5,
}

# Relancer PAR-DESSUS un limp (isolation) signale plus de force que relancer
# dans un pot vierge (RFI) : de l'argent mort est déjà dans le pot et un
# joueur est déjà engagé -- un joueur qui isole le fait typiquement avec une
# range plus étroite que son ouverture standard. Même statut de curseur que
# ci-dessus.
ISO_OVER_LIMP_FACTOR = 0.75


def _archetype_factor(villain_archetype: str | None) -> float:
    return ARCHETYPE_AGGRESSOR_FACTOR.get(villain_archetype, 1.0)


def vs_3bet(key: RangeKey, *, villain_archetype: str | None = None) -> RangeEntry:
    pct = _VS_3BET_BASE[key.ip_postflop] * _STACK_ADJUST[key.stack_bucket]
    pct = round(pct * _archetype_factor(villain_archetype), 1)
    note = "peu sensible au format : pot déjà réduit à 2 joueurs"
    if villain_archetype:
        note += f" ; ajusté pour l'archétype {villain_archetype!r}"
    return RangeEntry(scenario="vs_3bet", range=top_pct_range(pct), pct=pct,
                       confidence="extrapolated", note=note)


def vs_4bet(key: RangeKey, *, villain_archetype: str | None = None) -> RangeEntry:
    pct = _VS_4BET_BASE[key.ip_postflop] * _STACK_ADJUST[key.stack_bucket]
    pct = round(pct * _archetype_factor(villain_archetype), 1)
    note = "peu sensible au format : pot déjà réduit à 2 joueurs"
    if villain_archetype:
        note += f" ; ajusté pour l'archétype {villain_archetype!r}"
    return RangeEntry(scenario="vs_4bet", range=top_pct_range(pct), pct=pct,
                       confidence="extrapolated", note=note)
