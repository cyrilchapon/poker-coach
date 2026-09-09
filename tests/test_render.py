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
        "              ── preflop ──               ",
        "",
        "             BTN(mnc) · 100𝄫              ",
        "           ╭──────────────────╮",
        "           │   raise · 2.5𝄫   │",
        "           │                  │",
        "           │  -- -- -- -- --  │",
        "           │    pot · 3.5𝄫    │",
        "           │                  │",
        "           │        ?         │",
        "           ╰──────────────────╯",
        "                BB · 97.5𝄫                ",
        "                  A♠ K♥                   ",
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
        "              ── preflop ──               ",
        "",
        "             BTN(fsh) · 21.5𝄫             ",
        "           ╭──────────────────╮",
        "           │                  │",
        "           │                  │",
        "   CO(lag) │                sb│ SB(fsh)",
        "     21.5𝄫 │              0.5𝄫│ 212𝄫",
        "           │                  │",
        "           │  -- -- -- -- --  │",
        "           │    pot · 1.5𝄫    │",
        "           │                  │",
        "   HJ(tag) │                bb│ BB(fsh)",
        "       21𝄫 │                1𝄫│ 261𝄫",
        "           │        ?         │",
        "           ╰──────────────────╯",
        "                UTG · 257𝄫                ",
        "                  9♠ 7♥                   ",
    ])


def test_render_eight_max_golden():
    seats = {
        # Label RÉEL de state.POSITION_LABELS (et non "UTG1") : c'est le plus
        # long qui puisse tomber en colonne latérale, donc le seul qui teste
        # vraiment la largeur SIDE_W.
        "UTG+1": {"stack": 100.0, "action": "call", "amount": 2.0, "archetype": "tag"},
        "MP": {"stack": 100.0, "action": "fold", "amount": None, "archetype": "lag"},
        "HJ": {"stack": 100.0, "action": "raise", "amount": 8.0, "archetype": "fish"},
        "CO": {"stack": 100.0, "action": "fold", "amount": None, "archetype": "maniac"},
        "BTN": {"stack": 100.0, "action": "call", "amount": 8.0, "archetype": "tag"},
        "SB": {"stack": 99.5, "action": "post", "amount": 0.5, "archetype": "fish"},
        "UTG": {"stack": 100.0, "action": "fold", "amount": None, "archetype": "nit"},
    }
    hero = {"stack": 99.0, "cards": ["Q♠", "Q♥"], "action": "post", "amount": 1.0}
    order = ["UTG+1", "MP", "HJ", "CO", "BTN", "SB", "UTG"]
    out = r.render(seats=seats, hero_position="BB", hero=hero, board=[], pot=20.5,
                    street="preflop", acting_order=order)
    assert out == "\n".join([
        "              ── preflop ──               ",
        "",
        "              CO(mnc) · 100𝄫              ",
        "           ╭──────────────────╮",
        "           │       fold       │",
        "           │                  │",
        "   HJ(fsh) │raise         call│ BTN(tag)",
        "      100𝄫 │8𝄫              8𝄫│ 100𝄫",
        "           │                  │",
        "   MP(lag) │fold            sb│ SB(fsh)",
        "      100𝄫 │              0.5𝄫│ 99.5𝄫",
        "           │                  │",
        "           │  -- -- -- -- --  │",
        "           │   pot · 20.5𝄫    │",
        "           │                  │",
        "UTG+1(tag) │call          fold│ UTG(nit)",
        "      100𝄫 │2𝄫                │ 100𝄫",
        "           │      ? · 1𝄫      │",
        "           ╰──────────────────╯",
        "                 BB · 99𝄫                 ",
        "                  Q♠ Q♥                   ",
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
    assert "sb" in out
    assert "bb" in out
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
    assert r.bb(1.0) == "1𝄫"
    assert r.bb(21.0) == "21𝄫"
    assert r.bb(21.5) == "21.5𝄫"
    assert r.bb(0.5) == "0.5𝄫"
    assert r.bb(None) == ""


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
    assert out.split("\n")[3] == "           │      allin       │"


def test_render_hero_allin_with_no_current_action_shows_allin_not_a_pending_decision_mark():
    # Même repli côté Héros : "?" est réservé à une décision réellement en
    # attente -- un Héros tapis n'a plus de décision à prendre.
    seats = {"BTN": {"stack": 50.0, "action": "", "amount": None}}
    hero = {"stack": 0.0, "action": "", "amount": None, "status": "allin"}
    out = r.render(seats=seats, hero_position="BB", hero=hero, board=[], pot=100.0,
                    acting_order=["BTN"])
    assert "allin" in out
    assert "?" not in out


def test_render_longest_side_label_is_neither_truncated_nor_overflowing():
    # Régression : SIDE_W = 10 laissait 9 caractères au label de la colonne
    # GAUCHE -- "UTG+1(cst)" en fait 10, donc la parenthèse fermante sautait
    # silencieusement ("UTG+1(cst"), et le même label à DROITE, jamais
    # tronqué lui, poussait la ligne au-delà de TOTAL_W sur lequel le titre
    # de rue et le pied Héros sont centrés. "UTG+1" est la position la plus
    # longue de state.POSITION_LABELS hors heads-up : c'est donc le pire cas
    # possible en colonne latérale, et il doit tenir exactement.
    seats = {
        "UTG+1": {"stack": 100.0, "action": "fold", "amount": None,
                  "archetype": "calling_station"},
        "MP": {"stack": 100.0, "action": "fold", "amount": None, "archetype": "lag"},
        "HJ": {"stack": 100.0, "action": "fold", "amount": None, "archetype": "fish"},
        "CO": {"stack": 100.0, "action": "fold", "amount": None, "archetype": "maniac"},
        "BTN": {"stack": 100.0, "action": "raise", "amount": 8.0, "archetype": "tag"},
        "SB": {"stack": 99.5, "action": "post", "amount": 0.5, "archetype": "fish"},
        "UTG": {"stack": 100.0, "action": "fold", "amount": None,
                "archetype": "calling_station"},
    }
    hero = {"stack": 99.0, "cards": ["Q♠", "Q♥"], "action": "post", "amount": 1.0}
    # UTG+1 tombe en colonne gauche, UTG en colonne droite : les deux côtés
    # sont couverts par le même rendu.
    out = r.render(seats=seats, hero_position="BB", hero=hero, board=[], pot=10.5,
                    street="preflop",
                    acting_order=["UTG+1", "MP", "HJ", "CO", "BTN", "SB", "UTG"])
    assert "UTG+1(cst)" in out          # colonne gauche, non tronquée
    assert "UTG(cst)" in out            # colonne droite
    assert "UTG+1(cst " not in out
    assert max(len(line) for line in out.split("\n")) == r.TOTAL_W


def test_render_hero_blind_post_keeps_the_pending_decision_mark_with_its_amount():
    # Le Héros qui n'a fait que poster n'a rien décidé : "bb"/"sb" à la
    # place du "?" faisait disparaître le seul marqueur de décision en
    # attente du dessin, et redisait ce que le pied du rectangle affiche
    # déjà (BB · 99𝄫). On garde les deux : "? · 1𝄫".
    seats = {"BTN": {"stack": 100.0, "action": "raise", "amount": 2.5, "archetype": "lag"}}
    hero = {"stack": 99.0, "action": "post", "amount": 1.0}
    out = r.render(seats=seats, hero_position="BB", hero=hero, board=[], pot=3.5,
                    acting_order=["BTN"])
    assert "? · 1𝄫" in out
    assert "bb · 1𝄫" not in out

    hero = {"stack": 99.5, "action": "post", "amount": 0.5}
    out = r.render(seats=seats, hero_position="SB", hero=hero, board=[], pot=3.5,
                    acting_order=["BTN"])
    assert "? · 0.5𝄫" in out
    assert "sb · 0.5𝄫" not in out


def test_render_villain_blind_post_still_shows_sb_bb():
    # L'exception ci-dessus ne vaut QUE pour le Héros : côté villain, la case
    # vide veut dire "n'a pas encore parlé" et il n'y a aucun "?" à
    # préserver -- c'est le libellé sb/bb qui porte l'information.
    seats = {
        "SB": {"stack": 99.5, "action": "post", "amount": 0.5},
        "BB": {"stack": 99.0, "action": "post", "amount": 1.0},
    }
    hero = {"stack": 100.0, "action": "", "amount": None}
    out = r.render(seats=seats, hero_position="BTN", hero=hero, board=[], pot=1.5,
                    acting_order=["SB", "BB"])
    assert "sb" in out
    assert "bb" in out
