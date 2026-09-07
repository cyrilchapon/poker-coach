# Ranges de référence — 6-max, 100bb effectif

**Avertissement important** : ce sont des **approximations heuristiques** issues de la théorie standard largement diffusée (pas une sortie de solver vérifiée sur ce setup précis). Objectif : donner un point de départ raisonnable à ajuster avec l'utilisateur, pas une vérité absolue. Dès qu'un vrai export solveur est disponible (`solver-reader`), le préférer à ces valeurs pour toute réponse précise.

## Open-raise (RFI — Raise First In), 100bb, pas d'ante

| Position | % de mains (approx) | Exemple de range |
|---|---|---|
| UTG | ~15% | 77+, ATs+, AQo+, KQs |
| HJ | ~18% | 55+, A9s+, ATo+, KJs+, KQo |
| CO | ~24% | 22+, A2s+, A9o+, K9s+, K9o+, QTs+, QTo+, JTs, JTo, J9s, T9s, T8s, 98s, 87s, 76s
| BTN | ~45-48% | quasi tout sauf les mains les plus faibles (72o, 82o, etc.) |
| SB (raise-or-fold, sans limp) | ~40% | proche de la range BTN mais un peu resserrée (pas de squeeze derrière soi à exploiter) |

Élargissement quasi-linéaire par position : chaque position en descendant vers le bouton ajoute des mains par le bas de la range (petites paires, connecteurs suited, Ax suited faibles) plutôt que de changer la structure — ranges d'ouverture = **linéaires** (pas de bluffs purs, on ouvre les meilleures mains disponibles dans l'ordre).

## 3bet (contre un open-raise adverse, 100bb)

Les ranges de 3bet sont généralement **polarisées** (value + bluffs), pas linéaires — contrairement aux ranges d'ouverture.

| Contexte | % de 3bet (approx) | Structure |
|---|---|---|
| BTN vs CO open | ~9-11% | value (TT+, AQs+, AQo+) + bluffs (A5s-A2s, suited connectors bas comme 76s) |
| BB vs BTN open | ~12-14% | plus large, value + bluffs incluant des mains suited moyennes |
| CO vs UTG open | ~6-8% | plus resserré côté bluffs (position moins favorable, range UTG plus forte) |

## Ranges de call (flat) preflop

Plus dépendantes du contexte (profil adverse, joueurs encore à parler derrière) que d'une formule fixe — c'est le point où `range-builder` doit interroger l'utilisateur plutôt que sortir un chiffre tout fait. Repère général : caller plus large en position (BTN/CO) que hors position (blinds), et resserrer face à un raiser tight (UTG) par rapport à un raiser loose (BTN/CO).

## Utilisation

Ces valeurs servent de **point de départ conversationnel**, pas de réponse finale à donner telle quelle. `range-builder` doit toujours :
1. Proposer un point de départ à partir de ce tableau.
2. Ajuster avec l'utilisateur selon le contexte réel (profils adverses, joueurs restants à parler, stack depth si différent de 100bb).
3. Sortir le résultat en notation standard (`range-notation`) et donner ses stats via `scripts/range_stats.py`.
