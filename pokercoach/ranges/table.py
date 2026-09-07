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


@lru_cache(maxsize=1)
def _rfi_doc() -> dict:
    with open(DATA_DIR / "preflop-rfi.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


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


def vs_rfi(key: RangeKey, *, opener_n_behind: int) -> RangeEntry:
    """Défense face à une ouverture. Formule d'approximation (pas une table) :
    la largeur de défense est mise à l'échelle de la force implicite de
    l'ouverture adverse (une ouverture UTG => plus forte => on défend plus
    serré ; une ouverture BTN => plus large => on défend plus large)."""
    # La BB (n_behind=0) n'ouvre jamais, donc n'a pas de ligne RFI propre —
    # on prend la SB (n_behind=1, non-IP) comme plafond de référence pour
    # tout défenseur sans ligne RFI directe (approximation documentée).
    ceiling = _rfi_row(key.n_behind, key.ip_postflop) or _rfi_row(1, False)
    opener = _nearest_rfi_row_for_opener(opener_n_behind)
    reference_widest_pct = 45.0  # BTN 6-max, l'open le plus large de la table
    factor = min(1.0, opener["pct"] / reference_widest_pct)
    pct = round(ceiling["pct"] * factor, 1)
    return RangeEntry(
        scenario="vs_rfi", range=f"~{pct}% (top range du héros, largeur approximée)",
        pct=pct, confidence="extrapolated",
        note=f"vs ouverture {opener.get('usual_label', '?')} (pct {opener['pct']}%)",
    )


def vs_limp(key: RangeKey) -> RangeEntry:
    """Isolation face à un limp — scénario exploitant de première classe
    (quasi absent des ressources GTO, très fréquent au niveau de l'utilisateur).
    Élargie par rapport à la RFI standard."""
    row = rfi(key)
    if row.pct == 0:
        return row
    pct = round(min(100.0, row.pct * 1.3), 1)
    return RangeEntry(scenario="vs_limp", range=row.range, pct=pct, confidence="extrapolated",
                       note="isolation élargie face à un limp — traiter en scénario exploitant, pas dégénéré")


def squeeze(key: RangeKey, *, opener_n_behind: int) -> RangeEntry:
    base = vs_rfi(key, opener_n_behind=opener_n_behind)
    if base.pct == 0:
        return base
    pct = round(base.pct * 0.6, 1)
    return RangeEntry(scenario="squeeze", range=f"~{pct}% (polarisée, resserrée depuis vs_rfi)",
                       pct=pct, confidence="extrapolated",
                       note="squeeze : range de vs_rfi resserrée et polarisée")


_VS_3BET_BASE = {True: 45.0, False: 30.0}    # ip_postflop -> pct de continuation
_VS_4BET_BASE = {True: 15.0, False: 10.0}
_STACK_ADJUST = {"short": 1.15, "standard": 1.0, "deep": 0.9}


def vs_3bet(key: RangeKey) -> RangeEntry:
    pct = round(_VS_3BET_BASE[key.ip_postflop] * _STACK_ADJUST[key.stack_bucket], 1)
    return RangeEntry(scenario="vs_3bet", range=f"~{pct}% de continuation", pct=pct,
                       confidence="extrapolated", note="peu sensible au format : pot déjà réduit à 2 joueurs")


def vs_4bet(key: RangeKey) -> RangeEntry:
    pct = round(_VS_4BET_BASE[key.ip_postflop] * _STACK_ADJUST[key.stack_bucket], 1)
    return RangeEntry(scenario="vs_4bet", range=f"~{pct}% de continuation", pct=pct,
                       confidence="extrapolated", note="peu sensible au format : pot déjà réduit à 2 joueurs")
