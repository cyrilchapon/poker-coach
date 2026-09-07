"""Point d'entrée `pc` : dispatch des sous-commandes, JSON strict sur stdout.

Contrat (docs/brief/references/02-architecture-v2.md) :
- stdout : uniquement du JSON, jamais de prose.
- stderr : les erreurs.
- code de retour non nul si l'état est invalide.

Sous-commandes disponibles pour l'instant (étape 1 — squelette moteur) :
    pc state --hand hand.json      validation + dérivations (pot, SPR, cotes, MDF, qui parle)

Les autres sous-commandes de l'architecture v2 (hand, texture, line, budget,
equity, narrow, brief, render, glossary, apply) arrivent aux étapes suivantes
du §7 de docs/brief/PROMPT.md et ne sont pas encore implémentées.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .state import StateError, derive, validate_and_load


def _load_hand_json(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as exc:
        raise StateError(f"fichier introuvable : {path}") from exc
    except json.JSONDecodeError as exc:
        raise StateError(f"JSON invalide dans {path} : {exc}") from exc


def cmd_state(args: argparse.Namespace) -> dict[str, Any]:
    raw = _load_hand_json(args.hand)
    state = validate_and_load(raw)
    return derive(state).to_json()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pc", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_state = sub.add_parser("state", help="valide et dérive l'état d'une main")
    p_state.add_argument("--hand", required=True, help="chemin vers hand.json")
    p_state.set_defaults(func=cmd_state)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
    except StateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
