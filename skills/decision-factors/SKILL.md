---
name: decision-factors
description: Checklist des facteurs qualitatifs qui complètent l'équité et le budget ATT/DEF (position, implied/reverse implied odds, SPR, fold equity/exploitabilité, joueurs restants à parler) pour une analyse de décision poker plus complète. Chargée automatiquement par le gate G5 de `pc brief`, où ils tranchent ; leur poids sur les gates plus fermes suit le champ `confidence` de la sortie.
---

# Decision Factors

## Ordre obligatoire : narrower la range AVANT de calculer un seuil

Jamais l'inverse — un seuil de rentabilité calculé avant d'avoir vérifié que la range adverse contient encore assez de mains battues ne veut rien dire.

1. `pc narrow --hand hand.json --action <action_observée>` reconstruit la range adverse après filtrage par ce qu'elle a réellement misé/payé.
2. `pc equity` compare le héros à cette range narrowée, jamais à la range de départ.
3. `pc brief` enchaîne les deux dans cet ordre avant de rendre son verdict.

Dans la sortie de `pc narrow`, `retained_pct` est une part de **poids**, pas un compte de combos : un combo dont le budget ne finance pas l'action est retenu au poids plancher, pas supprimé — d'où un `remaining_combos` qui peut rester égal à `original_combos` pendant que `retained_pct` chute. Le champ `note` de la sortie le rappelle à chaque appel ; c'est `retained_pct` qui porte le filtrage.

**Piège cognitif à nommer si l'utilisateur raisonne à voix haute sans passer par le moteur** : un seuil de rentabilité bas (« il suffit de 17% ») est d'autant plus séduisant à énoncer qu'on est déjà engagé dans le coup — du *sunk cost* déguisé en calcul froid.

## Principe

Le moteur (`pc brief`) répond à « qui gagne le plus souvent, et le budget ATT/DEF autorise-t-il encore l'action ». Une vraie décision de poker dépend aussi de facteurs qualitatifs qu'il ne modélise pas complètement. Ces 5 facteurs s'appliquent **en plus** du verdict du moteur, jamais à sa place, et toujours après l'avoir fait calculer.

Leur poids face au verdict n'est pas binaire, et ne se lit pas au numéro du gate mais au champ `confidence` de la sortie :

- `forced` — ils n'ouvrent pas le verdict. Ils servent à l'expliquer ; s'en écarter est rarissime et demande un fait de table dur.
- `strong` — ils peuvent l'infléchir (sizing, ligne, taille du pot visé), et ne le renversent que si l'un d'eux contredit précisément ce qui a tranché.
- `grey` (G5) — ce sont eux qui tranchent, et cette skill est chargée pour ça.

Un gate précoce ne dispense donc jamais de lire la table : il relève la barre de ce qu'il faut pour s'en écarter, il ne la ferme pas. Le détail de cette progression est dans `live-session`, « Dévier du moteur ».

S'ils conduisent à s'écarter du verdict, l'écart doit être dit explicitement, chiffre du moteur à l'appui, avec le facteur qui le motive. Jamais une conclusion qui contredit le moteur sans le dire, ni un de ces facteurs invoqué avant d'avoir le verdict.

## 1. Position (IP / OOP)

En position permet de mieux **réaliser** son équité brute : contrôle de la taille du pot, information supplémentaire, possibilité de checker derrière. `pc state`/`pc brief` donnent `ip_postflop` — ajuster mentalement la conclusion à la hausse si IP, à la baisse si OOP.

## 2. Implied odds / reverse implied odds

Une main qui touche rarement mais gagne gros quand elle touche (suited connectors, petites paires) a de bonnes **implied odds**. Un gros As à kicker faible qui top-paire mais perd contre un meilleur kicker a des **reverse implied odds** défavorables — l'équité brute surestime alors la vraie valeur.

## 3. SPR (Stack-to-Pot Ratio)

`pc state` le calcule (`spr`). Stack profond (SPR élevé) favorise les mains spéculatives à fort potentiel implied odds. Stack court (SPR bas) favorise la force brute immédiate.

## 4. Fold equity / exploitabilité du villain

Déjà branché sur le budget : `pc budget --villain-archetype fish` applique la gate G4 (`bluff_multi_street_blocked`) qui **retire mécaniquement** l'option de bluff plutôt que de la déconseiller — voir `exploit-coach` pour la doctrine complète.

## 5. Joueurs restants à parler derrière

`n_opponents_active` (dans `pc brief`) et `n_behind` (préflop, dans le `range` de `pc brief`) le capturent déjà pour l'ajustement multiway du budget et le narrowing des ranges d'ouverture.

## Comment l'utiliser

Le gate G5 de `pc brief` CHARGE cette skill : ce n'est pas une ressource « disponible si besoin ». Sur un gate G0-G4, ne pas les dérouler point par point — le moteur en a déjà intégré une part (le budget porte la fold equity, l'ajustement multiway porte les joueurs derrière) et il a rendu un verdict.

Les garder en tête reste dû : c'est ce qui permet de repérer qu'un verdict « clair » repose sur une hypothèse que la table contredit. Dans ce cas, la suite n'est pas de conclure contre lui de tête, c'est de reposer la question au moteur au niveau de précision qui répond à l'intuition (`live-session`, « Orienter les appels, pas subir le défaut ») — et, si l'écart survit au recalcul, de l'annoncer selon le barème de `confidence` ci-dessus.

Ne pas transformer chaque analyse en liste exhaustive des 5 points — les mentionner seulement quand ils changent réellement la conclusion.
