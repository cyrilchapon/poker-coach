#!/usr/bin/env python3
"""Resynchronise le bootstrap partagé (`pc`, `pc_bootstrap.py`) depuis la
skill `engine` vers le dossier `scripts/` de chaque skill qui invoque `pc`.

Pourquoi une copie par skill plutôt qu'un import partagé : claude.ai déploie
chaque skill comme un dossier isolé (voir README, section "Installing" /
skills/engine/SKILL.md) -- rien en dehors du dossier d'une skill n'est
garanti accessible depuis cette skill. `pokercoach/` + `data/` + `docs/`
n'ont donc qu'un seul exemplaire (dans `skills/engine/`, cf. `pyproject.toml`),
mais le petit bootstrap qui les *localise* doit, lui, exister physiquement
dans chaque skill qui en a besoin.

Ce script est la source de vérité du *mécanisme* de sync (pas du contenu :
le contenu vient de skills/engine/scripts/). Lancer sans argument pour
réécrire les copies ; `--check` pour vérifier qu'elles sont à jour (utilisé
en CI) sans rien modifier -- code de retour non nul si une copie diverge ou
manque.

Usage :
    python3 scripts/sync_engine_bootstrap.py            # écrit les copies
    python3 scripts/sync_engine_bootstrap.py --check     # vérifie seulement
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_SCRIPTS = REPO_ROOT / "skills" / "engine" / "scripts"
SYNCED_FILES = ["pc", "pc_bootstrap.py"]

# Toute skill du plugin dont le SKILL.md invoque `pc` a besoin de sa propre
# copie -- seule `engine` (la source) en est exemptée. Liste explicite (pas
# un glob sur skills/*) pour qu'ajouter une skill qui n'a pas besoin du
# moteur (texte pur) n'oblige pas à y penser ici.
SKILLS_NEEDING_ENGINE = [
    "concept-tutor",
    "decision-factors",
    "equity-engine",
    "exploit-coach",
    "gto-glossary",
    "hand-review",
    "live-session",
    "poker-rules",
    "range-builder",
    "range-notation",
    "solver-reader",
]


def sync(check: bool) -> bool:
    ok = True
    for skill in SKILLS_NEEDING_ENGINE:
        dest_dir = REPO_ROOT / "skills" / skill / "scripts"
        for filename in SYNCED_FILES:
            src = ENGINE_SCRIPTS / filename
            dest = dest_dir / filename
            content = src.read_bytes()
            if check:
                if not dest.is_file() or dest.read_bytes() != content:
                    print(f"désynchronisé (ou manquant) : {dest.relative_to(REPO_ROOT)}", file=sys.stderr)
                    ok = False
                continue
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            dest.chmod(src.stat().st_mode)
    return ok


def main() -> int:
    check = "--check" in sys.argv[1:]
    ok = sync(check=check)
    if check and not ok:
        print(
            "\ncopies désynchronisées -- lancer `python3 scripts/sync_engine_bootstrap.py` "
            "(sans --check) et commiter le résultat.",
            file=sys.stderr,
        )
        return 1
    if not check:
        print(f"synchronisé : {', '.join(SYNCED_FILES)} -> {len(SKILLS_NEEDING_ENGINE)} skill(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
