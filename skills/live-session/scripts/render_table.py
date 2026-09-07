"""
Rendu ASCII d'une table 6-max vue de dessus.
Généralisé pour un Héros à N'IMPORTE QUELLE position (pas seulement BTN) :
la table tourne autour du Héros, toujours affiché en bas, dans l'ordre réel de parole (clockwise).

Règles (validées avec l'utilisateur) :
- Unité de stack : symbole 𝄫 (1 seul caractère, remplace "bb").
- Identité + stack de chaque joueur EN DEHORS de la table, avec un espace de respiration avant le bord
  (pas totalement collé) pour les positions verticales (BB/SB/HJ/CO).
- Décision (action, SANS timer) À L'INTÉRIEUR de la table, alignée du côté de son joueur. Le timer
  ne s'affiche plus dans le dessin — un timing notable (snap/quasi-snap/tank léger/tank lourd) se
  décrit en prose dans le récit de la rue, pas dans la grille.
- Fold affiche quand même le montant engagé au tour précédent.
- Pas de "..." : case vide si pas encore agi.
- Positions "horizontales" (slot du haut, slot du bas/Héros) : ligne combinée centrée à l'intérieur.
- Positions "verticales" (les 4 coins) : identité puis stack (2 lignes) dehors ; action puis montant
  (2 lignes) dedans.
- Board + pot centrés à l'intérieur. Le pot affiché inclut TOUJOURS toutes les mises de la rue en cours.
- Main révélée : au-dessus de l'identité (slot horizontal) ou en 3e ligne sous le stack (slot vertical).
- Le rectangle de la table est un invariant structurel : toute cellule intérieure est tronquée/complétée
  à largeur fixe, jamais de dépassement qui décale le bord — même si le contenu est trop long.
"""

ORDER = ["UTG", "HJ", "CO", "BTN", "SB", "BB"]  # ordre réel de parole (clockwise)

ARCHETYPE_CODE = {"Fish": "fsh", "LAG": "lag", "TAG": "tag", "Nit": "nit", "Maniac": "man"}

LEFT_W = 10    # largeur totale de la colonne extérieure gauche (texte + 1 espace de respiration)
INNER = 18     # largeur intérieure de la boîte
HALF = INNER // 2
BOX_W = INNER + 2
TOTAL_W = LEFT_W + BOX_W + LEFT_W
BB_UNIT = "𝄫"


def bb(n):
    if n is None or n == "":
        return ""
    return f"{n}{BB_UNIT}"


def _c(text, width):
    """Centre le texte, en le tronquant s'il dépasse — garantit toujours exactement `width`."""
    return str(text)[:width].center(width)


def _fit_l(text, width):
    """Aligné à gauche, tronqué/complété à largeur exacte."""
    return str(text)[:width].ljust(width)


def _fit_r(text, width):
    """Aligné à droite, tronqué/complété à largeur exacte."""
    return str(text)[:width].rjust(width)


def _slots_for_hero(hero_pos):
    i = ORDER.index(hero_pos)
    clockwise = [ORDER[(i + k) % 6] for k in range(6)]
    bottom, lower_left, upper_left, top, upper_right, lower_right = clockwise
    return {
        "bottom": bottom, "lower_left": lower_left, "upper_left": upper_left,
        "top": top, "upper_right": upper_right, "lower_right": lower_right,
    }


def render_table(seats, hero_pos, pot, board, hero, street="", show_archetype=True):
    """
    seats: dict position réelle (UTG/HJ/CO/BTN/SB/BB, sauf hero_pos) -> dict
        stack, action (SANS timer), amount, cards(optionnel), archetype (optionnel)
    hero_pos: la position réelle du Héros (ex "CO")
    hero: dict stack, cards, action ("?" par défaut)
    show_archetype: si True, affiche "(xxx)" à 3 lettres à côté du nom de position (configurable)
    """
    missing = [p for p in ORDER if p != hero_pos and p not in seats]
    if missing:
        raise ValueError(
            f"render_table: sièges absents du dict seats: {missing}. "
            f"Tous les sièges non-Héros doivent être passés à chaque rendu (même juste avec stack + action='out'), "
            f"sinon le rendu se dégrade silencieusement (stacks manquants, pas de marqueur out)."
        )
    slots = _slots_for_hero(hero_pos)

    def s(pos, key, default=""):
        return seats.get(pos, {}).get(key, default)

    def label(pos):
        if pos == hero_pos:
            return pos
        if show_archetype:
            code = ARCHETYPE_CODE.get(s(pos, "archetype"), "")
            if code:
                return f"{pos}({code})"
        return pos

    top = slots["top"]
    ul, ur = slots["upper_left"], slots["upper_right"]
    ll, lr = slots["lower_left"], slots["lower_right"]

    board_cells = (board + ["--"] * 5)[:5]
    board_str = " ".join(board_cells)

    lines = []
    if street:
        lines.append(_c(f"── {street} ──", TOTAL_W))
    lines.append("")

    if s(top, "cards"):
        lines.append(_c(" ".join(s(top, "cards")), TOTAL_W))
    lines.append(_c(f"{label(top)} · {s(top,'stack','')}", TOTAL_W))

    lines.append(" " * LEFT_W + "╭" + "─" * INNER + "╮")
    top_inline = s(top, "action", "")
    top_amt = s(top, "amount")
    if top_inline and top_amt:
        top_content = f"{top_inline} · {top_amt}"
    elif top_amt:
        top_content = top_amt
    else:
        top_content = top_inline
    lines.append(" " * LEFT_W + "│" + _c(top_content, INNER) + "│")
    lines.append(" " * LEFT_W + "│" + " " * INNER + "│")

    def vertical_row(pos_l, pos_r):
        left_label = _fit_r(label(pos_l), LEFT_W - 1) + " │"
        right_label = "│ " + label(pos_r)
        act_l = _fit_l(s(pos_l, "action", ""), HALF)
        act_r = _fit_r(s(pos_r, "action", ""), HALF)
        row1 = left_label + act_l + act_r + right_label

        left_stack = _fit_r(s(pos_l, "stack", ""), LEFT_W - 1) + " │"
        right_stack = "│ " + s(pos_r, "stack", "")
        amt_l = _fit_l(s(pos_l, "amount", ""), HALF)
        amt_r = _fit_r(s(pos_r, "amount", ""), HALF)
        row2 = left_stack + amt_l + amt_r + right_stack

        rows = [row1, row2]
        if s(pos_l, "cards") or s(pos_r, "cards"):
            l_c = " ".join(s(pos_l, "cards", []))
            r_c = " ".join(s(pos_r, "cards", []))
            left_cards = _fit_r(l_c, LEFT_W - 1) + " │"
            right_cards = "│ " + r_c
            rows.append(left_cards + " " * INNER + right_cards)
        return rows

    lines.extend(vertical_row(ul, ur))
    lines.append(" " * LEFT_W + "│" + " " * INNER + "│")
    lines.append(" " * LEFT_W + "│" + _c(board_str, INNER) + "│")
    lines.append(" " * LEFT_W + "│" + _c(f"pot · {pot}", INNER) + "│")
    lines.append(" " * LEFT_W + "│" + " " * INNER + "│")
    lines.extend(vertical_row(ll, lr))

    hero_act = hero.get("action", "?")
    hero_amt = hero.get("amount", "")
    hero_content = f"{hero_act} · {hero_amt}" if hero_amt else hero_act
    lines.append(" " * LEFT_W + "│" + _c(hero_content, INNER) + "│")
    lines.append(" " * LEFT_W + "╰" + "─" * INNER + "╯")
    lines.append(_c(f"{hero_pos} · {hero.get('stack','')}", TOTAL_W))
    lines.append(_c(" ".join(hero.get("cards", [])), TOTAL_W))

    return "\n".join(lines)


if __name__ == "__main__":
    seats = {
        "HJ": {"stack": bb(43.5), "action": "all-in", "amount": bb(21.0), "archetype": "TAG"},
        "CO": {"stack": bb(0.5), "action": "call", "amount": bb(21.5), "archetype": "LAG", "cards": ["8♥", "6♥"]},
        "BTN": {"stack": bb(21.5), "action": "out", "archetype": "Fish"},
        "SB": {"stack": bb(212.0), "action": "out", "archetype": "Fish"},
        "BB": {"stack": bb(261.0), "action": "out", "archetype": "Fish"},
    }
    hero = {"stack": bb(257.0), "cards": ["7♦", "K♣"], "action": "fold", "amount": bb(0)}
    print(render_table(seats, hero_pos="UTG", pot=bb(43.5), board=["Q♦", "K♥", "6♣", "2♠", "9♦"], hero=hero, street="RIVER (showdown)"))
