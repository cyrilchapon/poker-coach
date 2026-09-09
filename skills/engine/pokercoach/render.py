"""Couche B — rendu ASCII de la table, généralisé HU -> 8-max.

Reprend les conventions validées de la v1
(``current-plugin/live-session/scripts/render_table.py``), à préserver
explicitement (cf. PROMPT.md §8/§9 et 02-architecture-v2.md "Ce qui vient de
la v1 et ne doit pas être perdu") :

- unité de stack : symbole ``𝄫`` (remplace "bb") ;
- identité + stack de chaque siège À L'EXTÉRIEUR du rectangle ;
- action (sans timer) + montant À L'INTÉRIEUR (« sur la table »), alignés du
  côté du joueur — vrai pour les sièges verticaux ET pour le(s) siège(s)
  horizontaux (top, Héros) : la décision d'un joueur ne s'affiche jamais à
  l'extérieur du rectangle, y compris pour le siège du haut ;
- le timing (snap/tank...) ne s'affiche pas dans la grille, il se raconte en
  prose ailleurs ;
- fold affiche quand même le montant engagé au tour précédent ;
- case vide (pas de "...") si le siège n'a pas encore agi -- mais un siège
  qui n'a PLUS à agir (couché, ou tapis) l'affiche explicitement (``fold``/
  ``allin``) même sans action sur la rue courante, jamais une case vide qui
  laisserait croire à tort qu'il reste à parler ;
- board + pot centrés à l'intérieur, largeur du rectangle invariante (jamais
  de dépassement qui décale le bord) ;
- le Héros est toujours affiché en bas ;
- sièges "horizontaux" (Héros en bas, éventuellement un siège en haut) :
  identité + stack (+ cartes) À L'EXTÉRIEUR du rectangle, action + montant
  sur une ligne dédiée À L'INTÉRIEUR (même convention que le Héros : son
  identité/stack/cartes sont sous le rectangle, sa décision — ou ``?`` tant
  qu'il n'a pas parlé — est la dernière ligne intérieure) ;
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

Largeurs (fixées sur le format de référence 6-max) : ``INNER = 18``,
``SIDE_W = 11``, largeur totale ``TOTAL_W = 42``. Invariantes quel que soit
le nombre de sièges — seule la HAUTEUR du rectangle varie avec le nombre de
paires verticales.

``SIDE_W`` vaut exactement ce qu'il faut pour le PLUS LONG label possible en
colonne latérale (``UTG+1(cst)``, 10 caractères : la position la plus longue
de ``state.POSITION_LABELS`` hors heads-up, plus une abréviation d'archétype
entre parenthèses), plus l'espace qui l'écarte du bord du rectangle. Avec
moins, le label est tronqué silencieusement à gauche (``UTG+1(cst`` -- la
parenthèse fermante saute) et déborde à droite, la ligne dépassant alors
``TOTAL_W`` sur lequel le titre de rue et le pied Héros sont centrés.
``BTN/SB(cst)``, plus long encore, n'entre pas en compte : en heads-up
l'unique siège non-Héros est forcément le siège "top" (1 siège non-Héros =
nombre impair), centré sur ``TOTAL_W``, jamais en colonne latérale.

Ordre des lignes À L'INTÉRIEUR du rectangle (de ``╭`` à ``╰``) :

1. ligne d'action du siège top (contenu vide si pas encore agi) si un siège
   top existe, sinon rien à cette étape ;
2. lignes vides de padding — une seule si un siège top existe (son action
   occupe l'autre "slot"), deux sinon — de sorte que le total padding-ou-
   action-top + padding soit toujours 2 lignes avant la première paire ;
3. paires de sièges "avant pot" (``ceil(n_paires / 2)``), chacune suivie
   d'une ligne vide (y compris la dernière, qui sert de séparateur avant le
   board) ;
4. ligne board, ligne pot ;
5. ligne vide ;
6. paires de sièges "après pot" (``floor(n_paires / 2)``), chacune suivie
   d'une ligne vide SAUF la dernière (aucune ligne vide entre la dernière
   paire et l'action du Héros) ;
7. ligne d'action du Héros (``?`` si pas encore agi).

Quand le nombre de paires est impair, la moitié "avant pot" en reçoit une de
plus que la moitié "après pot" (choix arbitraire, à corriger si une
référence dit le contraire — le board/pot reste malgré tout visuellement
centré puisque l'écart n'est que d'une paire).

Montants (``bb()``) : jamais de ``.0`` superflu — un montant entier
s'affiche sans décimale (``1𝄫``), un montant non entier garde sa décimale
(``21.5𝄫``). Règle uniforme, appliquée aux stacks comme aux montants
d'action.

Stack affiché à côté de chaque siège : stack RESTANT (stack de début de main
moins tout l'investi sur la main entière, cf. ``remaining_stack``), jamais
le stack de début de main brut — c'est la valeur directement lisible sans
calcul mental, cohérente avec le montant d'action affiché à côté.

``post`` (mise obligatoire, cf. ``state.ACTIONS``) est réétiqueté à
l'affichage — jamais dans ``hand.json``, qui reste la source de vérité et ne
distingue pas les postes par un libellé dédié — d'après la position du
siège (déjà connue du schéma, ce n'est PAS une heuristique sur le montant) :
``sb`` pour le siège SB, ``bb`` pour le siège BB, inchangé (``post``) pour
tout autre siège (cas de l'ante "par joueur", cf. ``new_hand.py``, qui n'est
ni SB ni BB).

Exception pour le Héros : un poste n'est pas une décision, donc sa ligne
d'action garde le ``?`` de décision en attente et lui adjoint le montant
posté — ``? · 1𝄫`` en BB, ``? · 0.5𝄫`` en SB. Sans ça le seul marqueur de
décision du dessin disparaissait dès que le Héros était dans les blindes,
au profit d'un libellé (``bb``) que le pied du rectangle donne déjà.

Abréviation d'archétype (3 lettres, table explicite — ne dépend jamais
d'une troncature accidentelle) : ``nit``, ``tag``, ``lag`` inchangés,
``fish`` -> ``fsh``, ``maniac`` -> ``mnc``, ``calling_station`` -> ``cst``
(les 7 valeurs de ``state.ARCHETYPES`` hors ``None``). Un archétype inconnu
retombe sur une troncature à 3 caractères (comportement de secours, pas la
règle) — mais toute valeur du schéma doit avoir une entrée explicite ici.

Fidélité à l'état : chaque fait porté par ``hand.json`` qui a un impact sur
la décision du Héros doit être visible dans le dessin, jamais aplati en
case vide par accident :

- un siège ``folded`` ou ``allin`` qui n'a pas d'action sur la rue courante
  (parce qu'il a couché/fait tapis sur une rue précédente) affiche quand
  même son statut (``fold``/``allin``), Héros compris -- sinon indistingua-
  ble d'un siège actif qui n'a simplement pas encore parlé ;
- l'ordre de placement (``acting_order``) est l'ordre de SIÈGE PHYSIQUE
  clockwise depuis la gauche du Héros -- stable sur toute la main, câblé
  une fois pour toutes par le caller (cf. ``cli.cmd_render``), jamais
  recalculé depuis un ordre de PAROLE (qui change de rue en rue et n'a rien
  à voir avec la disposition autour de la table) ;
- un siège ``out`` (busté, cf. ``new_hand.py``) n'est plus dans la main :
  au caller de le retirer de ``seats``/``acting_order`` avant l'appel --
  ``render()`` n'a pas les moyens de le distinguer d'un siège qui n'a pas
  encore agi.
"""
from __future__ import annotations

from typing import Any

BB_UNIT = "𝄫"
INNER = 18
BOX_W = INNER + 2
SIDE_W = 11
HALF = INNER // 2
TOTAL_W = SIDE_W * 2 + BOX_W

ARCHETYPE_ABBR = {
    "nit": "nit",
    "tag": "tag",
    "lag": "lag",
    "fish": "fsh",
    "maniac": "mnc",
    "calling_station": "cst",
}


def _fmt_num(n: float) -> str:
    f = float(n)
    if f == int(f):
        return str(int(f))
    return str(n)


def bb(n: Any) -> str:
    if n is None or n == "":
        return ""
    return f"{_fmt_num(n)}{BB_UNIT}"


def _abbr(archetype: str) -> str:
    return ARCHETYPE_ABBR.get(archetype.lower(), archetype[:3].lower())


def _c(text: str, width: int) -> str:
    return str(text)[:width].center(width)


def _l(text: str, width: int) -> str:
    return str(text)[:width].ljust(width)


def _r(text: str, width: int) -> str:
    return str(text)[:width].rjust(width)


def _split_layout(order: list[str]) -> tuple[list[str], str | None, list[str]]:
    """Répartit ``order`` (clockwise depuis la gauche du Héros) en
    (colonne_gauche bas->haut, siège_top ou None, colonne_droite haut->bas)."""
    n = len(order)
    if n % 2 == 1:
        top_seats = 1
    else:
        top_seats = 0
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
        if key == "action":
            # Régression : un siège couché ou tapis sur une rue PRÉCÉDENTE
            # n'a aucune action sur la rue COURANTE (``node["actions"]`` ne
            # couvre que la rue affichée) -- sans ce repli sur ``status``, la
            # case redevenait vide au changement de rue, indistincte d'un
            # siège actif qui n'a simplement pas encore parlé (pour un
            # tapis, c'est pire : la case vide laisse croire qu'il reste à
            # agir, ce qui est faux -- l'état affiché mentirait).
            action = seats[pos].get("action", "")
            status = seats[pos].get("status")
            if not action and status == "folded":
                return "fold"
            if not action and status == "allin":
                return "allin"
            if action == "post":
                return "sb" if pos == "SB" else "bb" if pos == "BB" else "post"
            return action
        return seats[pos].get(key, default)

    def label(pos: str | None) -> str:
        if pos is None:
            return ""
        if s(pos, "archetype"):
            return f"{pos}({_abbr(s(pos, 'archetype'))})"
        return pos

    def action_content(pos: str | None) -> str:
        action, amount = s(pos, "action", ""), s(pos, "amount")
        # `amount and` (plutôt que `amount is not None and amount != ""`)
        # faisait disparaître le "· 0𝄫" d'un montant nul (ex. fold à 0, ou un
        # check explicitement à 0) -- 0 est un montant réel, pas une absence
        # de montant (cf. `bb()`, qui SAIT afficher "0𝄫").
        return f"{action} · {bb(amount)}" if action and amount not in (None, "") else (action or "")

    left_labels, top_label, right_labels = _split_layout(order)
    left_col = list(reversed(left_labels))  # rendu haut -> bas
    right_col = right_labels                # déjà haut -> bas

    lines: list[str] = []
    if street:
        lines.append(_c(f"── {street} ──", TOTAL_W))
    lines.append("")

    if top_label:
        if s(top_label, "cards"):
            lines.append(_c(" ".join(s(top_label, "cards")), TOTAL_W))
        lines.append(_c(f"{label(top_label)} · {bb(s(top_label, 'stack', ''))}", TOTAL_W))

    lines.append(" " * SIDE_W + "╭" + "─" * INNER + "╮")

    if top_label:
        lines.append(" " * SIDE_W + "│" + _c(action_content(top_label), INNER) + "│")
        lines.append(" " * SIDE_W + "│" + " " * INNER + "│")
    else:
        lines.append(" " * SIDE_W + "│" + " " * INNER + "│")
        lines.append(" " * SIDE_W + "│" + " " * INNER + "│")

    def vertical_row(pos_l: str | None, pos_r: str | None) -> list[str]:
        left_label = _r(label(pos_l), SIDE_W - 1) + " │"
        right_label = "│ " + label(pos_r)
        act_l = _l(s(pos_l, "action", ""), HALF)
        act_r = _r(s(pos_r, "action", ""), HALF)
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

    max_rows = max(len(left_col), len(right_col))
    row_indices = list(range(max_rows))
    n_before = (max_rows + 1) // 2  # moitié "avant pot" reçoit la paire en trop si impair
    before_idx, after_idx = row_indices[:n_before], row_indices[n_before:]

    def seat_row(i: int) -> list[str]:
        pos_l = left_col[i] if i < len(left_col) else None
        pos_r = right_col[i] if i < len(right_col) else None
        return vertical_row(pos_l, pos_r)

    for i in before_idx:
        lines.extend(seat_row(i))
        lines.append(" " * SIDE_W + "│" + " " * INNER + "│")

    board_cells = (board + ["--"] * 5)[:5]
    lines.append(" " * SIDE_W + "│" + _c(" ".join(board_cells), INNER) + "│")
    lines.append(" " * SIDE_W + "│" + _c(f"pot · {bb(pot)}", INNER) + "│")
    lines.append(" " * SIDE_W + "│" + " " * INNER + "│")

    for n, i in enumerate(after_idx):
        lines.extend(seat_row(i))
        if n != len(after_idx) - 1:
            lines.append(" " * SIDE_W + "│" + " " * INNER + "│")

    # Même repli que pour les autres sièges (cf. s() ci-dessus) : un Héros
    # tapis sur une rue précédente n'a plus d'action à afficher ici -- ``?``
    # (case réservée à une décision réellement en attente) mentirait autant
    # qu'une case vide.
    hero_status = hero.get("status")
    hero_action = hero.get("action") or (
        "fold" if hero_status == "folded" else "allin" if hero_status == "allin" else "?"
    )
    # Une blinde (ou un ante) n'est pas une DÉCISION : le Héros qui n'a fait
    # que poster a toujours sa décision devant lui, exactement comme s'il
    # n'avait rien mis. Afficher "bb"/"sb" à la place du ``?`` faisait
    # disparaître le seul marqueur de décision en attente du dessin -- et
    # redisait ce que le pied du rectangle indique déjà (``BB · 99𝄫``). On
    # garde donc le ``?`` ET le montant déjà engagé, qui lui n'est pas
    # redondant (il fixe le to-call réel) : ``? · 1𝄫``.
    #
    # Côté sièges non-Héros, ``post`` reste relabellisé en ``sb``/``bb`` :
    # là, la case vide signifie "n'a pas encore parlé" et il n'existe aucun
    # ``?`` à préserver -- c'est le libellé qui porte l'information.
    if hero_action == "post":
        hero_action = "?"
    hero_amount = hero.get("amount")
    # Même correctif que `action_content` ci-dessus : un montant à 0 ne doit
    # pas faire disparaître le "· 0𝄫".
    hero_content = (f"{hero_action} · {bb(hero_amount)}"
                    if hero_action and hero_amount not in (None, "") else hero_action)
    lines.append(" " * SIDE_W + "│" + _c(hero_content, INNER) + "│")
    lines.append(" " * SIDE_W + "╰" + "─" * INNER + "╯")

    lines.append(_c(f"{hero_position} · {bb(hero.get('stack', ''))}", TOTAL_W))
    if hero.get("cards"):
        lines.append(_c(" ".join(hero["cards"]), TOTAL_W))

    return "\n".join(lines)
