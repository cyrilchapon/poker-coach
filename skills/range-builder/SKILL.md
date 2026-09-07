---
name: range-builder
description: Construit avec l'utilisateur une range concrète (open-raise, 3bet, 4bet, call/défense) pour une situation donnée — position, profondeur de stack, contexte adverse. S'appuie sur poker-rules, range-notation, gto-glossary, equity-engine, et un tableau de ranges de référence approximatives. À utiliser dès que l'utilisateur veut définir, ajuster ou comprendre sa range dans une situation précise, ou dit ne pas savoir "où se situerait sa range" dans une main.
---

# Range Builder

## Dépendances

- `range-notation` : format de sortie obligatoire pour toute range produite.
- `gto-glossary` : vocabulaire (linéaire/polarisée/condensée, blockers, 3bet, squeeze...) à utiliser systématiquement en expliquant les choix.
- `equity-engine` (`scripts/equity.py`) : pour vérifier l'équité moyenne de la range construite contre une range adverse de référence, à titre de sanity check.
- `decision-factors` : facteurs qualitatifs (position, implied odds, SPR, fold equity, joueurs restants) à croiser avec l'équité pour toute analyse un peu poussée — pas juste sortir un chiffre d'équité brut.
- `references/baseline-ranges.md` : point de départ heuristique par position/action — **approximatif, pas une vérité solver**, à annoncer comme tel à l'utilisateur.
- `scripts/range_stats.py` : calcule le % de mains / nombre de combos d'une range en notation standard.
- `scripts/hand_rank.py` : classe une liste de mains candidates par équité contre une range adverse donnée — sert à répondre à "où se situe cette main dans ma range de call, et quelles sont les 2 mains limitrophes ?". **Ce n'est pas un solver** : classement par équité brute seule (ignore playability, blockers fins, jeu postflop réel), à présenter comme un repère de calibration, jamais comme un verdict définitif.

## Situer une main dans une range de call (cas d'usage fréquent)

Quand l'utilisateur demande "est-ce que X est un bon fold/call, et où ça se situe ?" :
1. Calculer l'équité requise pour un call rentable (cotes du pot) — voir `gto-glossary` → pot odds.
2. Faire tourner `hand_rank.py` sur un petit groupe de mains voisines de X (même As, kickers différents, versions suited/offsuit) contre la range adverse pertinente.
3. Identifier la main juste au-dessus du seuil (call marginal) et celle juste en dessous (fold marginal) parmi ce groupe — les montrer à l'utilisateur pour qu'il visualise l'écart réel entre sa main et la frontière, pas juste un verdict binaire.
4. Toujours rappeler que ce classement est fondé sur l'équité seule : la vraie frontière d'une range de call tient aussi compte de la position, des blockers, et de la jouabilité postflop — l'équité donne un ordre de grandeur fiable, pas une frontière exacte.


## Démarche

1. **Cadrer la situation** : position du héros, profondeur de stack (100bb par défaut sauf précision), type d'action (open, 3bet, 4bet, call, squeeze), et contre qui/quoi (position adverse, profil si connu via la notation HUD).
2. **Proposer un point de départ** depuis `references/baseline-ranges.md`, en étant clair que c'est une approximation à ajuster, pas une réponse figée.
3. **Construire avec l'utilisateur, pas à sa place** : proposer, mais laisser l'utilisateur trancher les mains limites ("on inclut KTo ou pas ?") plutôt que de lui livrer une range terminée sans échange — l'objectif est qu'il apprenne à raisonner la construction, pas qu'il reçoive un tableau.
4. **Ajuster selon le contexte réel** :
   - Range **linéaire** pour un open-raise (meilleures mains dans l'ordre, pas de bluffs purs).
   - Range **polarisée** pour un 3bet/squeeze (value + bluffs à blockers/playability, pas de mains moyennes "molles").
   - Élargir face à un adversaire loose/passif (Fish, Maniac), resserrer face à un TAG solide (peu d'exploit possible, cf. le raisonnement déjà tenu par l'utilisateur en session).
   - Resserrer si des joueurs solides restent à parler derrière (risque de squeeze).
5. **Sortir le résultat en notation standard** (`range-notation`) et donner ses stats (`range_stats.py` : % de mains, nombre de combos).
6. **Sanity check optionnel** : calculer l'équité moyenne de la range construite contre une range adverse typique via `equity-engine`, pour donner un ordre de grandeur (pas une preuve d'optimalité GTO).

## Ce que cette skill NE fait PAS

Ne invente pas une "réponse solver exacte" — les valeurs de référence sont explicitement approximatives. Si l'utilisateur veut une précision de niveau solver, le renvoyer vers `solver-reader` une fois qu'un export réel est disponible, ou vers un solveur externe (cf. les ressources identifiées en amont du projet : Desktop/WASM Postflop, TexasSolver).

## Ce que cette skill NE couvre PAS

L'analyse d'une main déjà jouée avec une range déjà décidée en tête → `hand-review`. Le déroulé d'une session complète avec ces ranges en pratique → `live-session`.
