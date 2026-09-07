# Architecture v2

## Principe directeur

> Le moteur calcule, le coach enseigne.

Tout ce qui est déterministe sort du raisonnement du LLM. Ce qui reste au LLM :
le jugement en zone grise, l'explication pédagogique, la conduite de la session.

Trois raisons, dans cet ordre d'importance :

1. **Justesse.** Le papier PokerSkill documente que les LLM échouent d'abord sur la
   *lecture d'état*, pas sur le raisonnement. La v1 du plugin en a fait l'expérience :
   ses propres SKILL.md documentent une erreur de session où un seuil de rentabilité a
   été énoncé avant vérification de la range, et une confusion sur un pot affiché lu
   comme un overbet.
2. **Coût.** Un calcul fait en Python coûte ~0 token. Le même raisonné en prose coûte
   des centaines de tokens et doit être refait à chaque rue.
3. **Vitesse.** Un appel CLI est un aller-retour. Cinq appels, c'est cinq tours de
   raisonnement intercalés.

---

## Couche A — l'état canonique

Fichier unique par main, `~/.poker-coach/hand.json`, mis à jour incrémentalement.
Source de vérité unique. Rien ne se re-narre en prose entre les rues.

### Schéma

```jsonc
{
  "schema_version": "2.0",
  "session_id": "s-20260907-01",
  "hand_id": 12,

  "table": {
    "format": "6max",              // "hu" | "6max" | "8max" — dérivé de seats
    "big_blind": 1.0,
    "ante": 0.0,
    "button_seat": 3               // siège physique, tourne d'une main à l'autre
  },

  // Les sièges sont PHYSIQUES et stables sur toute la session.
  // Le label de position se dérive de button_seat. Ne jamais stocker
  // l'archétype sur la position — c'est le bug que la v1 a explicitement corrigé.
  "seats": [
    {
      "seat": 0,
      "is_hero": true,
      "stack": 100.0,
      "archetype": null,
      "hud": null,
      "cards": ["A♠", "K♦"],
      "status": "active"           // active | folded | allin | out
    },
    {
      "seat": 1,
      "is_hero": false,
      "stack": 87.5,
      "archetype": "fish",         // nit | tag | lag | fish | maniac
      "hud": { "vpip": 46, "pfr": 7, "three_bet": 2, "af": 0.9 },
      "cards": null,               // renseigné seulement si révélé
      "status": "active"
    }
    // ...
  ],

  "streets": {
    "preflop": {
      "actions": [
        { "seat": 4, "action": "post", "amount": 0.5 },
        { "seat": 5, "action": "post", "amount": 1.0 },
        { "seat": 1, "action": "raise", "amount": 3.0, "timing": "snap" },
        { "seat": 0, "action": "call",  "amount": 3.0 }
      ]
    },
    "flop":  { "board": ["T♠", "9♥", "2♣"], "actions": [] },
    "turn":  null,
    "river": null
  },

  "to_act": 0,                     // siège dont c'est le tour
  "hero_seat": 0
}
```

**Règles dures :**

- `seats` est ordonné par siège physique et ne change jamais de composition au cours
  d'une session. Seul `button_seat` tourne. Les labels `UTG/HJ/CO/BTN/SB/BB` sont
  toujours **dérivés**, jamais stockés. (Comportement déjà spécifié en v1 et à
  préserver.)
- `amount` est le **montant total investi sur la rue par ce joueur après l'action**,
  pas l'incrément. Ça élimine une classe entière d'erreurs de calcul de pot.
- Tout montant est en **big blinds**, jamais en euros.
- Le pot n'est **jamais stocké**, toujours dérivé. La v1 a documenté une confusion en
  session sur un pot affiché mal interprété ; un champ dérivé ne peut pas diverger.
- Les cartes sont en unicode `♠♥♦♣`, comme demandé par l'utilisateur. Le moteur
  accepte les deux notations en entrée et normalise ; il ne sort que de l'unicode.

---

## Couche B — le moteur

### Arborescence

```
pokercoach/
  __init__.py
  cli.py                  point d'entrée `pc`, dispatch, JSON in/out
  state.py                validation, normalisation, dérivations
  cards.py                parsing unicode/lettres, deck, utilitaires
  handclass.py            les 23 classes de main + outs + blockers
  texture.py              classification de board + boards spéciaux
  actionline.py           grammaire de scénarios, rôle, pression pondérée
  budget.py               ATT/DEF, modificateurs, décrémentation
  equity.py               énumération / Monte-Carlo vectorisé + cache
  ranges/
    __init__.py
    table.py              lookup paramétré (voir 03-multiway-generalization.md)
    narrow.py             range narrowing mécanique
  gates.py                la cascade
  brief.py                orchestration → le paquet de décision
  render.py               le rendu ASCII de la table (repris de la v1)
  showdown.py             évaluation de showdown (repris de la v1)
data/                     les YAML, chargés une fois, mis en cache module
tests/
  fixtures/               mains de référence, y compris les traces du papier
```

### API du CLI

Toutes les commandes : JSON sur stdout, rien d'autre. Erreurs sur stderr, code retour
non nul si l'état est invalide.

```bash
pc state   --hand hand.json                  # validation + dérivations
pc hand    --hand hand.json [--seat N]       # classe de main, outs, blockers
pc texture --hand hand.json                  # labels de texture
pc line    --hand hand.json                  # scénario d'action-line + pression
pc budget  --hand hand.json                  # ATT/DEF restants + options viables
pc equity  --hand hand.json --vs "<range>"   # équité, avec bornes
pc narrow  --hand hand.json --seat N         # range adverse après filtrage
pc brief   --hand hand.json                  # ⭐ tout ce qui précède, en un appel
pc render  --hand hand.json                  # le dessin ASCII
pc glossary <terme>                          # une définition, pas 6 ko
pc apply   --hand hand.json --action "b 5.5" # applique une action, réécrit l'état
```

`pc brief` est **l'appel normal**. Les sous-commandes individuelles existent pour le
débogage et pour les cas où le coach a besoin d'un seul élément.

### Sortie de `pc brief`

```jsonc
{
  "gate": "G3",                    // le niveau qui a tranché
  "verdict": "call",               // action recommandée, ou null si zone grise
  "confidence": "forced",          // forced | strong | grey
  "verbosity": "short",            // pilote la longueur de réponse du coach

  "state": {
    "street": "turn",
    "hero_position": "BTN",
    "pot": 34.0,
    "to_call": 12.0,
    "pot_odds": 0.261,             // équité requise pour un call rentable
    "mdf": 0.739,
    "spr": 2.1,
    "effective_stack": 71.5,
    "players_active": 2,
    "players_to_act_behind": 0
  },

  "hand": {
    "class": "top_pair",
    "kicker_rank": 2,              // TPSK
    "distance_to_boundary": 0.15,  // proximité de la classe voisine → escalade
    "outs": 5,
    "blockers": ["bloque le tirage couleur nut"]
  },

  "texture": {
    "labels": ["two_tone", "straight_possible_single", "unpaired"],
    "wetness": "slightly_wet",
    "special": null
  },

  "line": {
    "scenario": "T-D1",
    "role": "defender",
    "pot_type": "srp",
    "weighted_pressure_faced": 1.55,
    "hero_pressure_spent": 0.70
  },

  "budget": {
    "att_base": 2.8, "att_remaining": 0.35,
    "def_base": 3.8, "def_remaining": 2.25,
    "viable_actions": ["call", "fold"],
    "removed": [
      { "action": "raise", "reason": "budget ATT insuffisant (0.35 < 1.0)" }
    ]
  },

  "equity": {
    "vs_range": "villain_narrowed",
    "point": 0.412,
    "lower_bound": 0.36,           // vs la range adverse la plus étroite plausible
    "upper_bound": 0.47,           // vs la plus large plausible
    "method": "enumeration",
    "iterations": null
  },

  "exploit": {
    "archetype": "fish",
    "fold_equity": "near_zero",
    "flags": ["bluff_multi_street_blocked"]
  },

  "escalate_reason": null          // rempli si gate == G5
}
```

Le coach lit ce paquet et **explique**. Il ne recalcule rien.

---

## Couche C — la cascade de gates

Chaque niveau peut clore la décision. Le coût monte à chaque étage ; l'immense
majorité des décisions ne dépasse pas G3.

| Gate | Test | Coût | Sortie |
|---|---|---|---|
| **G0** | Une seule action légale ; hero déjà all-in ; fold devant 0 mise | µs | Verdict, aucun raisonnement |
| **G1** | Lookup range préflop : main franchement dans ou franchement hors range pour le scénario | ms | Verdict + une ligne |
| **G2** | Budget ATT/DEF restant ≤ 0 pour l'action envisagée | ms | L'action est retirée, pas discutée |
| **G3** | **Bornes d'équité** : borne haute et borne basse du même côté du seuil de rentabilité | ~50 ms | Verdict chiffré |
| **G4** | Gates exploitantes (archétype × ligne) | lookup | Stop net |
| **G5** | Zone grise | — | Brief complet, `decision-factors` chargé, raisonnement LLM |

### G3 en détail — le branch-and-bound

C'est le cœur de la demande « discriminants early ».

Tu n'as pas besoin de l'équité exacte. Tu as besoin de savoir **de quel côté du seuil**
elle tombe. Donc :

1. Construis deux ranges adverses plausibles : la plus **étroite** défendable et la
   plus **large** défendable, compte tenu de la position, de l'archétype et du
   narrowing déjà appliqué.
2. Calcule l'équité du héros contre chacune → `[lower_bound, upper_bound]`.
3. Compare au seuil (`pot_odds` pour un call, seuil d'EV pour une relance).
   - Les deux bornes **au-dessus** → la décision est forcée dans un sens.
   - Les deux bornes **en dessous** → forcée dans l'autre.
   - Le seuil **entre les deux** → et seulement là, calcule l'équité précise, puis
     escalade en G5 si elle reste dans une bande d'incertitude.

Les deux calculs de bornes se font en Monte-Carlo grossier (2000 itérations suffisent
pour trancher un écart de bornes large). Le calcul précis n'arrive qu'en cas de
recouvrement. Gain typique attendu : la majorité des spots tranchés pour le coût de
deux simulations rapides au lieu d'une simulation précise plus un raisonnement.

**Curseur à faire valider par l'utilisateur** : la largeur de la bande d'incertitude
sous laquelle on escalade. Trop étroite → on tranche des spots qui méritaient une
discussion. Trop large → on ne coupe plus rien.

### G4 en détail — les gates exploitantes

Elles branchent le modèle adverse (que PokerSkill n'a pas) sur le budget.

| Condition | Effet |
|---|---|
| Archétype `fish`/calling station **et** ligne de bluff sur rue ≥ 2 | Budget ATT forcé à 0. Motif : `bluff_multi_street_blocked`. |
| Archétype `nit` **et** il mise fort sur une rue tardive | Budget DEF réduit d'un cran sur les mains de force moyenne. |
| Archétype `maniac` **et** hero a de la valeur | Budget DEF élargi ; retirer le fold des options avec top paire+. |
| Plusieurs `fish` à la table | Doctrine `exploit-coach` appliquée par défaut sur toute la session. |

La première ligne est **la traduction directe du leak documenté de l'utilisateur en
contrainte machine**. Ce n'est plus « attention, il ne foldera pas », c'est « l'action
n'est pas dans la liste ».

Note importante : la doctrine à double face contre un loose-passif, déjà écrite dans
`decision-factors` v1, doit être préservée — élargir la range d'entrée et le premier
call/mise, **mais resserrer franchement** l'évaluation de sa range de continuation
après qu'il a payé un ou plusieurs gros calls. « Il paie tout » devient faux dès qu'il
a filtré sa propre range par des mises coûteuses. C'est du narrowing, ça se calcule.

### Verbosité pilotée par le gate

| Gate | Réponse du coach |
|---|---|
| G0 | Une ligne, sans justification |
| G1–G2 | Verdict + le motif en une phrase |
| G3 | Verdict + le chiffre qui tranche + une phrase |
| G4 | Verdict + le motif exploitant, une à deux phrases |
| G5 | Analyse complète, checklist `decision-factors`, glossaire |

C'est le levier de tokens le plus rentable après le découpage des SKILL.md : en v1,
chaque décision reçoit le traitement complet en 6 points, indépendamment de sa
difficulté.

---

## Stratégie de réduction de tokens

Par ordre de rendement décroissant. Chiffres de base dans `04-current-plugin-audit.md`.

1. **Sortir les contrats de script des SKILL.md.** `live-session/SKILL.md` fait 18,5 ko
   dont une grosse moitié est une spécification du rendu ASCII. Ça descend dans le
   docstring et le `--help` de `render.py`. Le SKILL.md garde une convention d'appel
   de dix lignes.
2. **Chargement conditionnel par gate.** En v1, `decision-factors` (8,5 ko) et
   `gto-glossary` (5,9 ko) sont en contexte que la décision soit triviale ou non.
   En v2, seul G5 les charge.
3. **Un appel `pc brief` au lieu de 4–5 allers-retours.** Chaque appel bash coûte la
   commande, la sortie, et un tour de raisonnement intercalé.
4. **Verbosité indexée sur le gate** (ci-dessus).
5. **Glossaire en lookup.** `pc glossary MDF` retourne une définition. Le coach lit
   quarante caractères au lieu de 5,9 ko préchargés.
6. **État persistant.** L'historique ne se re-raconte plus entre les rues ; il est dans
   le fichier.

**Méthode de mesure imposée.** Après chaque étape, rejoue un scénario de référence
identique (à définir : une session de 10 mains scriptées, mêmes cartes, mêmes actions
adverses) et compte les tokens. Un chiffre avant/après, pas une impression.

## Stratégie de vitesse

- `equity.py` v1 est du Monte-Carlo Python pur avec un `random.choice` et un
  `random.shuffle` par itération. C'est le goulot.
- Remplacer par : énumération exhaustive quand le produit des combos le permet
  (typiquement turn et river), Monte-Carlo vectorisé numpy sinon, évaluateur backend C
  (`eval7` ou `phevaluator`) dans les deux cas.
- Cache mémoïsé par `(range1_hash, range2_hash, board, dead)` sur la durée de la
  session. Les mêmes confrontations reviennent constamment.
- Charger les YAML une fois au niveau module, pas par appel.
- Précalculer la table de ranges en structure statique indexée ; aucun calcul de range
  à l'exécution.

## Ce qui vient de la v1 et ne doit pas être perdu

Ces éléments sont des décisions produit déjà prises et validées en session. Ils sont
dans `current-plugin/` :

- Rendu ASCII de la table avec rectangle à largeur invariante, unité `𝄫`, identités à
  l'extérieur, actions à l'intérieur, récapitulatif de transition entre rues.
- Persistance des archétypes sur les sièges physiques pour toute la session.
- Bust du héros = fin de session, pas de rechargement silencieux.
- Résolution de showdown **obligatoirement** par script, jamais à l'œil.
- Question ouverte au héros avant chaque décision, jamais de suggestion préalable.
- Poursuite de la simulation après un fold du héros, jusqu'au pot remporté ou au
  showdown, pour permettre de valider la lecture des profils.
- Timing adverse raconté en prose, seulement quand il sort de l'ordinaire.
