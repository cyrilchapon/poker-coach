# Généralisation HU → 8-max

**Lis ce document avant d'écrire quoi que ce soit dans `ranges/`.** C'est la décision
de design qui rend le projet faisable ou non.

---

## Le piège à éviter

L'approche naïve est une table de ranges par format. Elle échoue par explosion
combinatoire :

```
3 formats × jusqu'à 8 positions × 6 types de pot × 3 profondeurs ≈ 430 cellules
```

Chaque cellule étant une range de 169 mains avec fréquences. C'est infaisable à
produire correctement, impossible à maintenir, et surtout **redondant** : la range
d'ouverture d'UTG en 8-max et celle d'UTG en 6-max sont quasi identiques, parce que
ce qui les gouverne n'est pas le label de position.

## Ce qui gouverne réellement une range préflop

Deux variables, pas huit :

1. **`n_behind`** — le nombre de joueurs qui doivent encore parler derrière toi.
   C'est le risque d'être 3-bet ou squeezé. Plus il est élevé, plus la range se
   resserre. Monotone.
2. **`ip_postflop`** — seras-tu en position après le flop contre le caller le plus
   probable ? Booléen.

Ces deux variables suffisent à expliquer les écarts que le label de position ne peut
pas expliquer. Exemple qui le prouve :

| Situation | `n_behind` | `ip_postflop` | RFI approx. |
|---|---|---|---|
| SB en 6-max | 1 | non | ~40 % |
| BTN/SB en heads-up | 1 | **oui** | ~85 % |

Même `n_behind`, ranges radicalement différentes. Le discriminant est la position
postflop, pas le nom du siège. Un modèle indexé sur `(n_behind, ip_postflop)`
capture ça ; un modèle indexé sur le label de position ne le peut pas sans dupliquer
la table par format.

## Le schéma d'indexation imposé

```python
RangeKey = (
    scenario,          # "rfi" | "vs_rfi" | "vs_3bet" | "vs_4bet" | "squeeze" | "vs_limp" | "blind_vs_blind"
    n_behind,          # 0..7
    ip_postflop,       # bool
    n_callers_before,  # 0..N — nombre de joueurs déjà entrés (limp/call)
    stack_bucket,      # "short" (<40bb) | "standard" (40-120bb) | "deep" (>120bb)
)
```

`format` (HU / 6-max / 8-max) **n'apparaît pas dans la clé**. Il n'est utilisé que par
le dériveur qui, à partir de `button_seat` et du nombre de sièges, calcule `n_behind`
et `ip_postflop` pour le héros. HU, 6-max et 8-max deviennent trois vues d'une seule
table.

### Dérivation

```python
def derive_key(state, hero_seat):
    order = seating_order(state)              # ordre de parole depuis le BTN
    n_behind = count_yet_to_act(order, hero_seat)
    ip_postflop = is_last_to_act_postflop(order, hero_seat, still_in)
    # ...
```

Cette fonction est la **seule** chose à écrire par format. Le reste est commun.

## La table de référence RFI

À encoder dans `data/preflop-rfi.yaml`. Valeurs de départ, à 100bb, sans ante,
`n_callers_before = 0` :

| `n_behind` | `ip_postflop` | Équivalent usuel | RFI % | Range approximative |
|---|---|---|---|---|
| 7 | non | UTG 8-max | ~12 % | 66+, AJs+, KQs, AQo+ |
| 6 | non | UTG+1 8-max | ~13 % | 55+, ATs+, KQs, AQo+ |
| 5 | non | UTG 6-max | ~16 % | 44+, A9s+, KTs+, QTs+, JTs, AJo+, KQo |
| 4 | non | HJ 6-max | ~20 % | 33+, A7s+, K9s+, Q9s+, J9s+, T9s, ATo+, KJo+ |
| 3 | non | CO 6-max | ~27 % | 22+, A2s+, K7s+, Q8s+, J8s+, T8s+, 97s+, A9o+, KTo+, QJo |
| 2 | oui | BTN 6-max | ~45 % | 22+, A2s+, K2s+, Q4s+, J6s+, T6s+, 95s+, 85s+, 75s+, 64s+, 54s, A2o+, K8o+, Q9o+, J9o+, T9o |
| 1 | non | SB (vs BB) | ~40 % raise | stratégie raise/limp mixte — voir note |
| 1 | oui | BTN/SB heads-up | ~85 % | tout sauf les pires offsuit déconnectées |

**Ces valeurs sont des ranges de référence de bon régulier, pas des sorties de
solveur.** Elles sont cohérentes entre elles et suffisantes pour du coaching. Elles ne
sont pas exactes à la fréquence près. Voir §« Honnêteté sur la précision » ci-dessous.

Note SB : la stratégie mixte raise/limp du SB en 6-max est un sujet à part entière
et une source classique d'erreur. Deux options : implémenter le mix, ou implémenter
une stratégie raise-or-fold pure (plus simple, légèrement moins EV, beaucoup plus
enseignable). **Demander l'arbitrage à l'utilisateur** — c'est un choix pédagogique
autant que technique.

### Ajustements dérivés, pas tabulés

Les autres scénarios se dérivent de la RFI par transformation plutôt que par nouvelle
table :

- **`vs_rfi` (défense face à une ouverture)** : fonction de `n_behind` (risque de
  squeeze derrière), de `ip_postflop`, et de la position de l'ouvreur (une ouverture
  UTG est plus forte qu'une ouverture BTN, donc on défend plus serré).
- **`squeeze`** : `vs_rfi` resserrée et polarisée, avec `n_callers_before > 0`.
- **`vs_limp`** : élargir l'isolation, resserrer l'over-limp. Ce scénario est
  quasi-absent des ressources GTO (les solveurs ne modélisent pas les limps) mais très
  fréquent au niveau où joue l'utilisateur, contre des `fish`. **À traiter comme un
  scénario exploitant de première classe**, pas comme un cas dégénéré.
- **`vs_3bet` / `vs_4bet`** : les moins sensibles au format, parce que le pot est déjà
  réduit à deux joueurs. Une seule table, indexée sur `ip_postflop` et
  `stack_bucket`.

## Postflop multiway — l'ajustement des budgets

Les tables ATT/DEF de `data/` sont calibrées **heads-up 200bb**. Deux corrections
nécessaires, dans cet ordre.

### 1. Correction de profondeur (100bb au lieu de 200bb)

Le SPR de départ est deux fois plus bas. Les seuils de commitment se déclenchent plus
tôt. Proposition : conserver les budgets, mais abaisser les seuils de SPR
(`SPR ≤ 1.5` devient `SPR ≤ 2.0` pour la logique commit-or-fold) et vérifier sur des
fixtures.

### 2. Correction multiway

Pour `n_opponents_active` adversaires encore dans le coup :

```
ATT_multiway = ATT_base × 0.75^(n_opponents_active − 1)
DEF_multiway = DEF_base − 0.3 × (n_opponents_active − 1)
```

Avec deux règles dures par-dessus :

- **Les classes de tirage et de bluff pur voient leur ATT tomber à 0 dès
  `n_opponents_active ≥ 3`.** Bluffer trois joueurs, c'est demander à trois personnes
  de folder ; la fold equity s'effondre multiplicativement.
- **Les seuils de value se resserrent** : une main qui vaut trois barrels en HU en vaut
  au plus deux à trois joueurs. C'est déjà l'effet du facteur 0.75, mais il faut
  l'expliciter au coach.

⚠️ **Ces coefficients sont une proposition de départ, pas une vérité.** Ils sont
plausibles et directionnellement corrects, mais ils n'ont pas été calibrés. Ils sont
placés dans `data/multiway-adjustment.yaml` précisément pour être ajustables sans
toucher au code. Prévois de les faire valider par l'utilisateur après quelques
sessions de test.

### 3. Le MDF multiway — piège théorique à ne pas rater

En heads-up, `MDF = pot / (pot + bet)` et un seul joueur porte l'obligation de défense.

En multiway, l'obligation est **collective**. Si trois joueurs font face à une mise, ce
n'est pas chacun qui doit défendre au MDF heads-up — c'est la fréquence de fold
*combinée* qui doit rester sous le seuil. Chaque défenseur individuel peut donc folder
davantage.

Appliquer naïvement le MDF heads-up en multiway conduit à sur-défendre, ce qui est
exactement un des modes de perte de l'utilisateur (continuer une ligne trop loin). Le
moteur doit exposer un `mdf_individual` distinct du `mdf_collective` et le coach doit
enseigner la différence.

## Honnêteté sur la précision — à lire

**Ce que je peux produire avec confiance :**

- La structure paramétrée ci-dessus, qui est le vrai travail de design.
- Des ranges de référence cohérentes, du niveau d'un bon régulier, pour HU et 6-max.
  Ces formats sont massivement documentés publiquement et les ranges sont stables et
  consensuelles.
- Les transformations dérivées (vs_rfi, squeeze, vs_limp) au même niveau.
- Les ajustements multiway comme des paramètres explicites, ajustables.

**Ce que je ne peux pas produire :**

- Des fréquences exactes au point de mixage près. Ce sont des sorties de solveur ; je
  ne les ai pas et je ne dois pas prétendre les avoir.
- Des ranges 7-max et 8-max au même niveau de fiabilité que HU et 6-max. Le format
  full-ring moderne est bien moins documenté en cash game online, et l'essentiel de la
  littérature 8-max/9-max vient du tournoi, où l'ICM change les ranges. Pour 7 et 8-max,
  la table ci-dessus **extrapole** la tendance de resserrement plutôt qu'elle ne
  reproduit des charts vérifiés.

**Recommandation** : oui, vise HU → 8-max, la structure le permet sans surcoût. Mais :

1. Marque chaque entrée de range d'un champ `confidence: high | medium | extrapolated`.
   `n_behind ≥ 6` sera `extrapolated`. Le coach doit le dire quand il s'appuie dessus.
2. Rends la table **remplaçable** : un importeur (`pc ranges import <fichier>`) qui
   accepte un export de charts (GTO Wizard, Pio, format texte de range) et écrase les
   entrées correspondantes. L'utilisateur pourra ainsi injecter des ranges exactes
   quand il en a, sans réécrire le moteur.
3. Traite la précision des ranges comme un axe d'amélioration continue, pas comme un
   prérequis de la v2. Le budget ATT/DEF apporte plus de valeur immédiate que trois
   points de pourcentage sur une range d'ouverture UTG.

**Si l'utilisateur veut réduire le risque** : livrer HU + 6-max en `confidence: high`
et 7/8-max en `extrapolated` explicite est plus honnête et pas plus coûteux que de
prétendre couvrir 8-max au même niveau. La structure paramétrée fait que passer
`extrapolated` → `high` plus tard est un remplacement de données, pas une refonte.
