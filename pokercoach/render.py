"""Couche B — rendu ASCII de la table, généralisé HU -> 8-max.

Reprend les conventions validées de la v1
(``current-plugin/live-session/scripts/render_table.py``), à préserver
explicitement (cf. PROMPT.md §8/§9 et 02-architecture-v2.md "Ce qui vient de
la v1 et ne doit pas être perdu") :

- unité de stack : symbole ``𝄫`` (remplace "bb") ;
- identité + stack de chaque siège À L'EXTÉRIEUR du rectangle ;
- action (sans timer) + montant À L'INTÉRIEUR, alignés du côté du joueur ;
- le timing (snap/tank...) ne s'affiche pas dans la grille, il se raconte en
  prose ailleurs ;
- fold affiche quand même le montant engagé au tour précédent ;
- case vide (pas de "...") si le siège n'a pas encore agi ;
- board + pot centrés à l'intérieur, largeur du rectangle invariante (jamais
  de dépassement qui décale le bord) ;
- le Héros est toujours affiché en bas.

Simplification assumée pour la généralisation à N sièges (2 à 8) : la v1
plaçait les 5 non-Héros aux 4 coins + le haut d'une géométrie fixe à 6
sièges. Cette géométrie fixe ne généralise pas proprement à un nombre
variable de sièges ; ici, les sièges non-Héros sont listés à l'extérieur du
rectangle, dans l'ordre de parole réel (clockwise depuis la gauche du
Héros), au-dessus de la boîte. Les conventions listées ci-dessus sont
préservées à l'identique ; seule la disposition géométrique change.
"""
from __future__ import annotations

from typing import Any

BB_UNIT = "𝄫"
INNER = 22
BOX_W = INNER + 2
SIDE_W = 16
TOTAL_W = SIDE_W * 2 + BOX_W


def bb(n: Any) -> str:
    if n is None or n == "":
        return ""
    return f"{n}{BB_UNIT}"


def _c(text: str, width: int) -> str:
    return str(text)[:width].center(width)


def _l(text: str, width: int) -> str:
    return str(text)[:width].ljust(width)


def render(*, seats: dict[str, dict], hero_position: str, hero: dict, board: list[str],
           pot: float, street: str = "", acting_order: list[str] | None = None) -> str:
    """``seats``: {position_label -> {stack, action, amount, cards?, archetype?}}
    pour tous les sièges SAUF le Héros. ``hero``: {stack, cards, action, amount}.
    ``acting_order``: labels non-Héros dans l'ordre de parole clockwise depuis
    la gauche du Héros (défaut : ordre d'insertion de ``seats``)."""
    order = acting_order or list(seats.keys())
    missing = [p for p in order if p not in seats]
    if missing:
        raise ValueError(f"render: sièges absents du dict seats: {missing}")

    lines: list[str] = []
    if street:
        lines.append(_c(f"── {street} ──", TOTAL_W))
    lines.append("")

    for pos in order:
        s = seats[pos]
        cards = s.get("cards")
        if cards:
            lines.append(_c(" ".join(cards), TOTAL_W))
        label = pos
        if s.get("archetype"):
            label = f"{pos}({s['archetype'][:3].lower()})"
        lines.append(_c(f"{label} · {bb(s.get('stack', ''))}", TOTAL_W))
        action, amount = s.get("action", ""), s.get("amount")
        content = f"{action} · {bb(amount)}" if action and amount else (action or "")
        lines.append(_c(content, TOTAL_W))
        lines.append("")

    board_cells = (board + ["--"] * 5)[:5]
    lines.append(" " * SIDE_W + "╭" + "─" * INNER + "╮")
    lines.append(" " * SIDE_W + "│" + _c(" ".join(board_cells), INNER) + "│")
    lines.append(" " * SIDE_W + "│" + _c(f"pot · {bb(pot)}", INNER) + "│")
    hero_action, hero_amount = hero.get("action", "?"), hero.get("amount")
    hero_content = f"{hero_action} · {bb(hero_amount)}" if hero_action and hero_amount else hero_action
    lines.append(" " * SIDE_W + "│" + _c(hero_content, INNER) + "│")
    lines.append(" " * SIDE_W + "╰" + "─" * INNER + "╯")

    lines.append(_c(f"{hero_position} · {bb(hero.get('stack', ''))}", TOTAL_W))
    if hero.get("cards"):
        lines.append(_c(" ".join(hero["cards"]), TOTAL_W))

    return "\n".join(lines)
