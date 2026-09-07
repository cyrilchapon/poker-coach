# Audit de la v1

Le plugin complet est dans `current-plugin/` (11 skills, tels qu'installés).
Estimations de tokens à ~4 caractères/token — approximation grossière mais suffisante
pour hiérarchiser.

## Mesures

| Skill | chars | ~tokens | Verdict v2 |
|---|---:|---:|---|
| `live-session` | 18 506 | ~4 630 | **Éclater.** Plus de la moitié est un contrat de script. |
| `decision-factors` | 8 520 | ~2 130 | Charger seulement en G5. Une partie devient du code. |
| `gto-glossary` | 5 895 | ~1 475 | Devient une base de lookup (`pc glossary`). |
| `range-builder` | 5 007 | ~1 250 | Enveloppe mince autour de `pc ranges`. |
| `poker-rules` | 4 440 | ~1 110 | Garder. C'est de la référence factuelle, elle sert. |
| `hand-review` | 3 472 | ~870 | Réécrire autour de `pc brief`. |
| `equity-engine` | 3 023 | ~755 | Réduire à la convention d'appel. |
| `exploit-coach` | 2 757 | ~690 | Garder la doctrine, brancher sur les gates G4. |
| `concept-tutor` | 2 492 | ~625 | Garder tel quel. Pas dans le chemin de décision. |
| `solver-reader` | 2 415 | ~605 | Garder tel quel. Usage ponctuel. |
| `range-notation` | 2 363 | ~590 | Garder. Court et structurant. |
| **Total SKILL.md** | **58 890** | **~14 700** | |

Scripts et références annexes : ~7 300 tokens supplémentaires, chargés à la demande.

### Le vrai coût en session

Une session `live-session` charge en pratique `live-session` + `decision-factors` +
`gto-glossary` + `equity-engine` + `range-notation`, soit **~9 600 tokens de skills**
avant la première main. Puis chaque décision un peu développée déclenche la checklist
en 6 points de `live-session` étape 4, qui appelle 4 à 5 scripts en allers-retours
séparés, chacun avec son tour de raisonnement.

C'est la cible principale. Le poids statique des skills est un problème ; le coût par
décision en est un plus gros.

---

## Fichier par fichier

### `live-session/SKILL.md` — 18,5 ko, le gros morceau

Contenu, par nature :

| Section | Nature | Destination v2 |
|---|---|---|
| Contexte utilisateur fixe | Produit | Reste (condensé) |
| Notation HUD + archétypes | Données | `data/archetypes.yaml` |
| Pondération réaliste des profils | Données | `data/archetypes.yaml` |
| Persistance des identités / rotation du bouton | **Logique** | `state.py` — c'est du code, pas de la prose |
| Bust = fin de session | Produit | Reste |
| Modes 1/2/3 de démarrage | Produit | Reste |
| **Rendu visuel de la table** (~8 ko) | **Contrat de script** | Docstring + `--help` de `render.py` |
| Timing des adversaires | Produit | Reste (condensé) |
| Résolution des showdowns | Contrat de script | `showdown.py` |
| Déroulé d'une main | Produit | Reste, réécrit autour de `pc brief` |

La section de rendu visuel à elle seule pèse plus que la plupart des autres skills
entières. Elle décrit un invariant de largeur de rectangle, l'alignement des cellules,
le placement des identités et des montants, la gestion des folds et des `out`, le
récapitulatif de transition entre rues. **Rien de tout ça n'a besoin d'être dans le
contexte du LLM** : c'est la spécification du comportement de `render_table.py`, qui
l'implémente déjà. Le skill a seulement besoin de savoir *quand* appeler le script et
*quelles données* lui passer.

⚠️ Attention en la déplaçant : ces règles sont le fruit de corrections successives en
session (alignement cassé, blinds qui disparaissaient du pot, joueurs foldés omis du
dessin, timer qui cassait les colonnes). Elles doivent être **préservées à
l'identique** dans le script, pas réinventées. Le fichier v1 est dans
`current-plugin/live-session/SKILL.md`, lis-le avant de toucher au rendu.

La checklist « étape 4 » (range narrowing → équité → describe_hand → sizing →
decision-factors → glossaire) devient un seul `pc brief` plus une consigne de
verbosité indexée sur le gate.

### `decision-factors/SKILL.md` — 8,5 ko

Contient deux choses de nature différente :

1. **De la méthode calculable** — le range narrowing (construire la range de départ
   depuis position + profil, retirer ce que chaque mise a filtré, appliquer l'effet des
   cartes tombées, *puis seulement* comparer au seuil de rentabilité). C'est un
   algorithme. Il va dans `ranges/narrow.py`.
2. **De la doctrine qualitative** — les 5 facteurs (position, implied odds, SPR, fold
   equity, joueurs restants). Reste en prose, chargé en G5 uniquement.

Le fichier contient un constat d'auto-critique important : *« la formulation "à
consulter systématiquement" n'a pas suffi — cette skill n'a été ouverte à aucun moment
sur plusieurs analyses approfondies »*. La leçon vaut pour la v2 : **une description de
déclenchement ne remplace pas un point d'appel explicite dans le flux**. En v2, le
problème disparaît structurellement, parce que `pc brief` calcule les facteurs
calculables et que le gate G5 charge la doctrine — ce n'est plus une ressource
« disponible si besoin ».

Il documente aussi le piège cognitif à préserver absolument : un seuil de rentabilité
bas est **structurellement plus séduisant à énoncer quand on est déjà engagé dans le
coup**. C'est du sunk cost déguisé en calcul froid. En v2, le moteur calcule le seuil
*après* le narrowing, dans cet ordre, mécaniquement — l'ordre de raisonnement devient
un ordre d'exécution.

### `equity-engine/scripts/equity.py` — à réécrire

Limitations documentées dans le skill lui-même, toutes à corriger :

- Pas de main exacte à deux cartes fixées (le parseur travaille par catégories
  abstraites). C'est une vraie gêne : on ne peut pas calculer l'équité de la main
  réelle du héros.
- Pas de pondération `@xx%`.
- Monte-Carlo pur, ±0,5–1 % à 20 000 itérations.
- Implémentation : `random.choice` + `random.shuffle` par itération, en Python pur,
  sur `treys`. C'est le goulot de vitesse.

### `range-builder/references/baseline-ranges.md`

Contient les ranges de référence 6-max de la v1. **À lire avant d'écrire
`data/preflop-rfi.yaml`** — c'est le point de départ et ça donne la convention de
notation déjà utilisée. Ne pas repartir de zéro et créer une incohérence.

### `exploit-coach/references/archetype-adjustments.md`

La doctrine par archétype. Elle devient la source des gates G4. Le passage sur les
calling stations est central pour le leak de l'utilisateur : contre un vrai calling
station, **la fold equity est quasi nulle dès le départ, pas seulement « moins
bonne »**, et miser deux fois en espérant qu'il finisse par folder est une erreur
reconnue, pas une variante légitime. Corollaire à encoder : bluffer une seule fois,
tôt, ou pas du tout.

---

## Cible

| | v1 | Cible v2 |
|---|---:|---|
| Skills chargés au démarrage d'une session | ~9 600 tokens | < 3 000 |
| Appels de script par décision développée | 4–5 | 1 |
| Réponse sur une décision triviale | analyse complète | 1 ligne |
| Équité, 20 000 itérations | ~2–4 s | < 100 ms |

Ces chiffres sont des objectifs de cadrage, à valider par mesure réelle sur un
scénario de référence reproductible (voir `02-architecture-v2.md`, §Stratégie de
réduction de tokens).
