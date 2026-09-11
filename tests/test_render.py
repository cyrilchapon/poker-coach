"""Tests golden pour `pokercoach.render` -- ce fichier a déjà régressé
plusieurs fois sur l'alignement (cf. render.py docstring) : comparaison
exacte de chaîne sur HU / 6-max / 8-max pour que la prochaine modification
casse bruyamment plutôt que de dériver silencieusement."""
from pokercoach import render as r


def test_render_heads_up_golden():
    seats = {"BTN": {"stack": 100.0, "action": "raise", "amount": 2.5, "archetype": "maniac"}}
    hero = {"stack": 97.5, "cards": ["A♠", "K♥"], "action": "", "amount": None}
    out = r.render(seats=seats, hero_position="BB", hero=hero, board=[], pot=3.5,
                    street="preflop", acting_order=["BTN"])
    assert out == "\n".join([
        "             ── preflop ──              ",
        "",
        "            BTN(mnc) · 100bb            ",
        "          ╭──────────────────╮",
        "          │  raise · 2.5bb   │",
        "          │                  │",
        "          │  -- -- -- -- --  │",
        "          │   pot · 3.5bb    │",
        "          │                  │",
        "          │        ?         │",
        "          ╰──────────────────╯",
        "              BB · 97.5bb               ",
        "                 A♠ K♥                  ",
    ])


def test_render_six_max_golden():
    # Héros UTG, ordre de parole clockwise depuis sa gauche : HJ, CO, BTN, SB, BB.
    seats = {
        "HJ": {"stack": 21.0, "action": "", "amount": None, "archetype": "tag"},
        "CO": {"stack": 21.5, "action": "", "amount": None, "archetype": "lag"},
        "BTN": {"stack": 21.5, "action": "", "amount": None, "archetype": "fish"},
        "SB": {"stack": 212.0, "action": "post", "amount": 0.5, "archetype": "fish"},
        "BB": {"stack": 261.0, "action": "post", "amount": 1.0, "archetype": "fish"},
    }
    hero = {"stack": 257.0, "cards": ["9♠", "7♥"], "action": "", "amount": None}
    out = r.render(seats=seats, hero_position="UTG", hero=hero, board=[], pot=1.5,
                    street="preflop", acting_order=["HJ", "CO", "BTN", "SB", "BB"])
    assert out == "\n".join([
        "             ── preflop ──              ",
        "",
        "           BTN(fsh) · 21.5bb            ",
        "          ╭──────────────────╮",
        "          │                  │",
        "          │                  │",
        "  CO(lag) │                sb│ SB(fsh)",
        "   21.5bb │             0.5bb│ 212bb",
        "          │                  │",
        "          │  -- -- -- -- --  │",
        "          │   pot · 1.5bb    │",
        "          │                  │",
        "  HJ(tag) │                bb│ BB(fsh)",
        "     21bb │               1bb│ 261bb",
        "          │        ?         │",
        "          ╰──────────────────╯",
        "              UTG · 257bb               ",
        "                 9♠ 7♥                  ",
    ])


def test_render_eight_max_golden():
    seats = {
        "UTG1": {"stack": 100.0, "action": "call", "amount": 2.0, "archetype": "tag"},
        "MP": {"stack": 100.0, "action": "fold", "amount": None, "archetype": "lag"},
        "HJ": {"stack": 100.0, "action": "raise", "amount": 8.0, "archetype": "fish"},
        "CO": {"stack": 100.0, "action": "fold", "amount": None, "archetype": "maniac"},
        "BTN": {"stack": 100.0, "action": "call", "amount": 8.0, "archetype": "tag"},
        "SB": {"stack": 99.5, "action": "post", "amount": 0.5, "archetype": "fish"},
        "UTG": {"stack": 100.0, "action": "fold", "amount": None, "archetype": "nit"},
    }
    hero = {"stack": 99.0, "cards": ["Q♠", "Q♥"], "action": "post", "amount": 1.0}
    order = ["UTG1", "MP", "HJ", "CO", "BTN", "SB", "UTG"]
    out = r.render(seats=seats, hero_position="BB", hero=hero, board=[], pot=20.5,
                    street="preflop", acting_order=order)
    assert out == "\n".join([
        "             ── preflop ──              ",
        "",
        "            CO(mnc) · 100bb             ",
        "          ╭──────────────────╮",
        "          │       fold       │",
        "          │                  │",
        "  HJ(fsh) │raise         call│ BTN(tag)",
        "    100bb │8bb            8bb│ 100bb",
        "          │                  │",
        "  MP(lag) │fold            sb│ SB(fsh)",
        "    100bb │             0.5bb│ 99.5bb",
        "          │                  │",
        "          │  -- -- -- -- --  │",
        "          │   pot · 20.5bb   │",
        "          │                  │",
        "UTG1(tag) │call          fold│ UTG(nit)",
        "    100bb │2bb               │ 100bb",
        "          │     bb · 1bb     │",
        "          ╰──────────────────╯",
        "               BB · 99bb                ",
        "                 Q♠ Q♥                  ",
    ])


def test_render_post_maps_to_sb_bb_by_position_not_by_amount():
    # Régression : ne jamais déduire sb/bb du montant posté (ambigu avec un
    # ante/straddle) -- toujours de la position, seule source de vérité.
    seats = {
        "SB": {"stack": 10.0, "action": "post", "amount": 0.5},
        "BB": {"stack": 10.0, "action": "post", "amount": 1.0},
    }
    hero = {"stack": 10.0, "action": "", "amount": None}
    out = r.render(seats=seats, hero_position="BTN", hero=hero, board=[], pot=1.5,
                    acting_order=["SB", "BB"])
    # Sièges verticaux : l'action et le montant sont sur deux lignes. On
    # vise la ligne d'action elle-même, pas un `"bb" in out` devenu trivial
    # depuis que l'unité de stack est ASCII "bb".
    assert "       SB │sb              bb│ BB" in out
    assert "     10bb │0.5bb          1bb│ 10bb" in out
    assert "post" not in out


def test_render_post_for_a_non_blind_seat_keeps_the_generic_label():
    # Cas de l'ante "par joueur" (cf. new_hand.py) : un siège qui n'est ni
    # SB ni BB peut aussi avoir action == "post" -- pas de sb/bb à tort.
    seats = {"UTG": {"stack": 10.0, "action": "post", "amount": 0.25}}
    hero = {"stack": 10.0, "action": "", "amount": None}
    out = r.render(seats=seats, hero_position="BB", hero=hero, board=[], pot=0.25,
                    acting_order=["UTG"])
    assert "post" in out


def test_render_archetype_abbreviations_use_explicit_table():
    assert r._abbr("fish") == "fsh"
    assert r._abbr("maniac") == "mnc"
    assert r._abbr("nit") == "nit"
    assert r._abbr("tag") == "tag"
    assert r._abbr("lag") == "lag"


def test_bb_drops_superfluous_trailing_zero_everywhere():
    assert r.bb(1.0) == "1bb"
    assert r.bb(21.0) == "21bb"
    assert r.bb(21.5) == "21.5bb"
    assert r.bb(0.5) == "0.5bb"
    assert r.bb(None) == ""


def test_bb_unit_is_plain_ascii():
    # Régression d'alignement : l'unité était le symbole musical ``𝄫``
    # (U+1D12B), hors plan multilingue de base -- absent de la plupart des
    # polices monospace, donc rendu par une police de substitution de chasse
    # arbitraire. Comme il n'apparaît que sur les lignes portant un montant,
    # le décalage n'était pas uniforme : exactement le pire cas pour un
    # dessin en colonnes. L'unité doit rester ASCII pur.
    assert r.BB_UNIT.isascii()
    assert r.display_width(r.bb(1.0)) == len(r.bb(1.0))


def test_render_archetype_abbreviations_cover_the_full_schema():
    # Régression : `calling_station` (une des 7 valeurs de state.ARCHETYPES)
    # n'avait pas d'entrée dans ARCHETYPE_ABBR -- retombait sur une
    # troncature accidentelle ("cal"), exactement ce que la table explicite
    # est censée éviter pour fish/maniac.
    assert r._abbr("calling_station") == "cst"


def test_render_allin_seat_with_no_current_street_action_shows_allin_not_blank():
    # Régression, même famille que le repli "fold" déjà en place : un siège
    # tapis sur une rue PRÉCÉDENTE n'a pas d'entrée dans les actions de la
    # rue courante -- une case vide serait indiscernable d'un siège actif
    # qui n'a simplement pas encore parlé, alors qu'un tapis ne peut plus
    # agir du tout.
    seats = {"BTN": {"stack": 0.0, "action": "", "amount": None, "status": "allin"}}
    hero = {"stack": 50.0, "action": "", "amount": None}
    out = r.render(seats=seats, hero_position="BB", hero=hero, board=[], pot=100.0,
                    acting_order=["BTN"])
    # Pas de case vide en lieu et place -- l'action du siège top est la
    # première ligne intérieure du rectangle.
    assert out.split("\n")[3] == "          │      allin       │"


def test_render_hero_allin_with_no_current_action_shows_allin_not_a_pending_decision_mark():
    # Même repli côté Héros : "?" est réservé à une décision réellement en
    # attente -- un Héros tapis n'a plus de décision à prendre.
    seats = {"BTN": {"stack": 50.0, "action": "", "amount": None}}
    hero = {"stack": 0.0, "action": "", "amount": None, "status": "allin"}
    out = r.render(seats=seats, hero_position="BB", hero=hero, board=[], pot=100.0,
                    acting_order=["BTN"])
    assert "allin" in out
    assert "?" not in out


def test_display_width_is_columns_not_code_points():
    # Le décalage inconsistant des colonnes vient de là : `len()` compte des
    # points de code. Une marque combinante en occupe 0, un idéogramme 2.
    assert r.display_width("abc") == 3
    assert r.display_width("é") == 1      # e + accent combinant
    assert r.display_width("Ａ") == 2       # A pleine chasse
    assert r.display_width("A♠ K♥") == 5        # symboles de couleur : 1 colonne


def test_padding_helpers_pad_to_display_width():
    for pad in (r._c, r._l, r._r):
        assert r.display_width(pad("A♠", 10)) == 10
        assert r.display_width(pad("échec", 10)) == 10
        assert r.display_width(pad("ＡＡ", 10)) == 10


def test_padding_helpers_never_truncate_mid_character():
    # Tronquer à la largeur, pas au point de code : un caractère de 2
    # colonnes qui ne tient pas est écarté entier, il ne déborde pas la case.
    assert r._l("ＡＡ", 3) == "Ａ "
    assert r.display_width(r._l("ＡＡ", 3)) == 3


def test_rectangle_width_is_invariant_across_rows():
    # Le symptôme rapporté : des colonnes qui se décalent selon les cartes et
    # les montants présents sur chaque ligne. Toutes les lignes d'un même
    # rendu doivent avoir la même largeur d'affichage (hors lignes vides).
    seats = {
        "HJ": {"stack": 21.0, "action": "call", "amount": 2.0, "archetype": "tag"},
        "CO": {"stack": 212.5, "action": "raise", "amount": 8.5, "archetype": "lag"},
        "BTN": {"stack": 21.5, "action": "fold", "amount": None, "archetype": "fish",
                 "cards": ["A♦", "Q♣"]},
        "SB": {"stack": 212.0, "action": "post", "amount": 0.5, "archetype": "fish"},
        "BB": {"stack": 261.0, "action": "post", "amount": 1.0, "archetype": "fish"},
    }
    hero = {"stack": 257.0, "cards": ["9♠", "7♥"], "action": "call", "amount": 8.5}
    out = r.render(seats=seats, hero_position="UTG", hero=hero,
                    board=["A♠", "K♦", "7♣", "2♥"], pot=27.5, street="turn",
                    acting_order=["HJ", "CO", "BTN", "SB", "BB"])
    # Les bords du rectangle doivent tomber sur la MÊME colonne d'affichage
    # à chaque ligne, quelles que soient les cartes et les montants portés
    # par cette ligne-là (les libellés de siège à droite débordent librement,
    # ils n'ont pas de bord derrière eux).
    for line in out.split("\n"):
        if "│" not in line:
            continue
        left, _, rest = line.partition("│")
        assert r.display_width(left) == r.SIDE_W, repr(line)
        inner, sep, _ = rest.partition("│")
        assert sep == "│", repr(line)
        assert r.display_width(inner) == r.INNER, repr(line)
    # Les lignes hors rectangle sont centrées sur la largeur totale.
    for line in out.split("\n"):
        if line.strip() and "│" not in line and "╭" not in line and "╰" not in line:
            assert r.display_width(line) == r.TOTAL_W, repr(line)
