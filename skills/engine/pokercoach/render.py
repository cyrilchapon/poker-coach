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
- blind postée (SB/BB) : affichée comme "sb"/"bb", pas "post" ;
- case vide (pas de "...") si le siège n'a pas encore agi ;
- board + pot centrés à l'intérieur (à mi-hauteur du rectangle, pas collés à
  un bord), largeur du rectangle invariante (jamais de dépassement qui
  décale le bord) ;
- le Héros est toujours affiché en bas, son action/montant colle au bord
  inférieur (pas de ligne vide avant la bordure) ;
- siège "top" (s'il y en a un) : identité + stack DEHORS (au-dessus de la
  bordure), action + montant DEDANS (première ligne intérieure, sous la
  bordure — jamais dehors, sinon une ligne vide parasite apparaît sous son
  bloc extérieur) ;
- sièges "verticaux" (colonnes gauche/droite, de part et d'autre du
  rectangle) : identité puis stack (2 lignes) dehors, action puis montant
  (2 lignes séparées) dedans, alignées du côté du joueur.

Généralisation à N sièges (2 à 8) de la géométrie fixe 6-max de la v1 (4
coins + 1 haut) : les sièges non-Héros, dans l'ordre de parole réel
(clockwise depuis la gauche du Héros), sont répartis en :

- un siège "top" (horizontal, au-dessus du rectangle) SEULEMENT si le
  nombre de sièges non-Héros est impair (le siège du milieu de la liste) ;
- le reste, à parts égales, dans une colonne gauche et une colonne droite,
  disposées verticalement de part et d'autre du rectangle — la colonne
  gauche prend les sièges les plus proches du Héros (bas -> haut), la
  colonne droite prend les sièges les plus proches du haut (haut -> bas) ;
  ce qui reproduit exactement le placement 4-coins + top de la v1 quand il
  y a 5 sièges non-Héros (6-max).

Les paires gauche/droite qui en résultent sont elles-mêmes réparties pour
moitié au-dessus du board/pot, pour moitié en dessous (comme les 2 rangées
de coins de la v1), afin que le board/pot reste au centre du rectangle au
lieu de s'entasser sous tous les sièges.
"""
from __future__ import annotations

from typing import Any

BB_UNIT = "𝄫"
INNER = 22
BOX_W = INNER + 2
SIDE_W = 16
HALF = INNER // 2
TOTAL_W = SIDE_W * 2 + BOX_W


def bb(n: Any) -> str:
    if n is None or n == "":
        return ""
    return f"{n}{BB_UNIT}"


def _c(text: str, width: int) -> str:
    return str(text)[:width].center(width)


def _l(text: str, width: int) -> str:
    return str(text)[:width].ljust(width)


def _r(text: str, width: int) -> str:
    return str(text)[:width].rjust(width)


def _action_text(pos: str | None, action: str) -> str:
    """"post" (blind) devient "sb"/"bb" pour le siège concerné — plus lisible
    que le nom générique de l'action."""
    if pos in ("SB", "BB") and action == "post":
        return pos.lower()
    return action


def _split_layout(order: list[str]) -> tuple[list[str], str | None, list[str]]:
    """Répartit ``order`` (clockwise depuis la gauche du Héros) en
    (colonne_gauche bas->haut, siège_top ou None, colonne_droite haut->bas)."""
    n = len(order)
    top_seats = 1 if n % 2 == 1 else 0
    side_total = n - top_seats
    left_count = side_total // 2
    left_labels = order[:left_count]
    top_label = order[left_count] if top_seats else None
    right_labels = order[left_count + top_seats:]
    return left_labels, top_label, right_labels


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

    def s(pos: str | None, key: str, default: Any = "") -> Any:
        if pos is None:
            return default
        return seats[pos].get(key, default)

    def label(pos: str | None) -> str:
        if pos is None:
            return ""
        if s(pos, "archetype"):
            return f"{pos}({s(pos, 'archetype')[:3].lower()})"
        return pos

    left_labels, top_label, right_labels = _split_layout(order)
    left_col = list(reversed(left_labels))  # rendu haut -> bas
    right_col = right_labels                # déjà haut -> bas

    # Les paires (gauche, droite) sont réparties pour moitié au-dessus du
    # board/pot, pour moitié en dessous (le board/pot reste au centre).
    n_pairs = max(len(left_col), len(right_col))
    pairs = [
        (left_col[i] if i < len(left_col) else None, right_col[i] if i < len(right_col) else None)
        for i in range(n_pairs)
    ]
    n_above = n_pairs // 2
    pairs_above, pairs_below = pairs[:n_above], pairs[n_above:]

    lines: list[str] = []
    if street:
        lines.append(_c(f"── {street} ──", TOTAL_W))
    lines.append("")

    if top_label:
        if s(top_label, "cards"):
            lines.append(_c(" ".join(s(top_label, "cards")), TOTAL_W))
        lines.append(_c(f"{label(top_label)} · {bb(s(top_label, 'stack', ''))}", TOTAL_W))

    lines.append(" " * SIDE_W + "╭" + "─" * INNER + "╮")

    def vertical_row(pos_l: str | None, pos_r: str | None) -> list[str]:
        left_label = _r(label(pos_l), SIDE_W - 1) + " │"
        right_label = "│ " + label(pos_r)
        act_l = _l(_action_text(pos_l, s(pos_l, "action", "")), HALF)
        act_r = _r(_action_text(pos_r, s(pos_r, "action", "")), HALF)
        row1 = left_label + act_l + act_r + right_label

        left_stack = _r(bb(s(pos_l, "stack", "")), SIDE_W - 1) + " │"
        right_stack = "│ " + bb(s(pos_r, "stack", ""))
        amt_l = _l(bb(s(pos_l, "amount")), HALF)
        amt_r = _r(bb(s(pos_r, "amount")), HALF)
        row2 = left_stack + amt_l + amt_r + right_stack

        rows = [row1, row2]
        cards_l, cards_r = s(pos_l, "cards"), s(pos_r, "cards")
        if cards_l or cards_r:
            l_c = " ".join(cards_l or [])
            r_c = " ".join(cards_r or [])
            left_cards = _r(l_c, SIDE_W - 1) + " │"
            right_cards = "│ " + r_c
            rows.append(left_cards + " " * INNER + right_cards)
        return rows

    blank = " " * SIDE_W + "│" + " " * INNER + "│"

    # Sections empilées à l'intérieur du rectangle, séparées par une ligne
    # vide (jamais de ligne vide avant le Héros, qui colle à la bordure).
    sections: list[list[str]] = []
    if top_label:
        action, amount = s(top_label, "action", ""), s(top_label, "amount")
        action = _action_text(top_label, action)
        top_content = f"{action} · {bb(amount)}" if action and amount else (action or "")
        sections.append([" " * SIDE_W + "│" + _c(top_content, INNER) + "│"])
    for pos_l, pos_r in pairs_above:
        sections.append(vertical_row(pos_l, pos_r))
    board_cells = (board + ["--"] * 5)[:5]
    sections.append([
        " " * SIDE_W + "│" + _c(" ".join(board_cells), INNER) + "│",
        " " * SIDE_W + "│" + _c(f"pot · {bb(pot)}", INNER) + "│",
    ])
    for pos_l, pos_r in pairs_below:
        sections.append(vertical_row(pos_l, pos_r))

    for section in sections:
        lines.extend(section)
        lines.append(blank)
    lines.pop()  # pas de ligne vide entre la dernière section et le Héros

    hero_action = _action_text(hero_position, hero.get("action", "?"))
    hero_amount = hero.get("amount")
    hero_content = f"{hero_action} · {bb(hero_amount)}" if hero_action and hero_amount else hero_action
    lines.append(" " * SIDE_W + "│" + _c(hero_content, INNER) + "│")
    lines.append(" " * SIDE_W + "╰" + "─" * INNER + "╯")

    lines.append(_c(f"{hero_position} · {bb(hero.get('stack', ''))}", TOTAL_W))
    if hero.get("cards"):
        lines.append(_c(" ".join(hero["cards"]), TOTAL_W))

    return "\n".join(lines)
