---
name: decision-factors
description: Checklist des facteurs qualitatifs qui complètent l'équité et le budget ATT/DEF (position, implied/reverse implied odds, SPR, fold equity/exploitabilité, joueurs restants à parler) pour une analyse de décision poker plus complète. Chargée automatiquement par le gate G5 de `pc brief` — seules les décisions qui atteignent la zone grise en ont besoin, les autres sont déjà tranchées par le moteur.
---

# Decision Factors

## v2 : le range narrowing est du code, pas de la prose

**Erreur constatée en v1** : calculer le seuil de rentabilité arithmétique *avant* d'avoir vérifié que la range adverse contenait encore assez de mains battues pour le justifier. En v2, l'ordre est **mécanique**, pas un rappel méthodologique à appliquer soi-même :

1. `pc narrow --hand hand.json --action <action_observée>` reconstruit la range adverse après filtrage par ce qu'elle a réellement misé/payé.
2. `pc equity` compare le héros à cette range narrowée, jamais à la range de départ non filtrée.
3. `pc brief` fait les deux dans cet ordre avant de rendre son verdict — le raisonnement biaisé n'est plus possible parce que le seuil n'est calculé qu'après le narrowing, par construction.

**Piège cognitif que ça neutralise, mais qu'il faut savoir nommer si l'utilisateur raisonne à voix haute sans passer par le moteur** : un seuil de rentabilité bas ("il suffit de 17%") est structurellement plus séduisant à énoncer quand on est déjà engagé dans le coup — une forme de *sunk cost* déguisée en calcul froid.

## Principe

Le moteur (`pc brief`) répond à "qui gagne le plus souvent, et le budget ATT/DEF autorise-t-il encore l'action". Une vraie décision de poker dépend aussi de facteurs qualitatifs que le moteur ne modélise pas complètement. Ces 5 facteurs s'appliquent en plus du verdict du moteur, jamais à sa place, et seulement en G5 (zone grise) — sur G0-G4, le moteur a déjà tranché.

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

**Constat de v1 à ne pas répéter** : "à consulter systématiquement" n'a pas suffi tant que ce n'était qu'une convention de skill. En v2 le problème disparaît structurellement — le gate G5 de `pc brief` CHARGE cette skill, ce n'est plus une ressource "disponible si besoin". Si `pc brief` renvoie un gate G0-G4, ces 5 facteurs ne sont pas nécessaires à la réponse (le moteur les a déjà pris en compte via le budget/multiway) ; seul G5 justifie de les dérouler.

Ne pas transformer chaque analyse en liste exhaustive des 5 points — les mentionner seulement quand ils changent réellement la conclusion.
