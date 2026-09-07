---
name: range-builder
description: Construit avec l'utilisateur une range concrète (open-raise, 3bet, 4bet, call/défense) pour une situation donnée — position, profondeur de stack, contexte adverse. S'appuie sur le lookup paramétré du moteur (HU → 8-max, indexé par n_behind/ip_postflop, pas par label de position) et sur equity-engine. À utiliser dès que l'utilisateur veut définir, ajuster ou comprendre sa range dans une situation précise.
---

# Range Builder

## v2 : lookup paramétré, plus une table par position/format

Le point de départ n'est plus `references/baseline-ranges.md` seul : `pc brief --hand hand.json` en préflop renvoie un champ `range` avec le pourcentage/la notation de référence pour la situation exacte (scénario, `n_behind`, `ip_postflop`, profondeur), et un `confidence` (`high` / `medium` / `extrapolated`). **Toujours dire la confidence à l'utilisateur** — HU et 6-max sont `high`, 7/8-max s'appuie sur une extrapolation explicite (`extrapolated`), pas des charts vérifiés. Voir `docs/brief/references/03-multiway-generalization.md` pour le raisonnement complet (chemin absolu via `scripts/pc paths`, clé `docs_dir`) ; `references/baseline-ranges.md` (v1) reste la référence de notation 6-max d'origine si un recoupement est utile.

Scénarios dérivés (pas des tables séparées, des transformations depuis la RFI — `pokercoach/ranges/table.py`) : `vs_rfi`, `vs_limp` (élargi, traité en scénario exploitant de première classe, pas dégénéré), `squeeze`, `vs_3bet`, `vs_4bet`. Toujours `confidence: extrapolated` — ce sont des formules d'approximation documentées, pas des sorties de solveur. `pc brief` les câble automatiquement dès que le héros défend (préflop hors ouverture) ; pour un lookup direct indépendant d'une main de héros donnée, `pc ranges --hand hand.json --scenario {rfi,vs_rfi,vs_limp,squeeze,vs_3bet,vs_4bet} [--seat N] [--opener-seat N]`.

## Dépendances

- `range-notation` : format de sortie obligatoire pour toute range produite.
- `pc glossary` : vocabulaire (linéaire/polarisée/condensée, blockers, 3bet, squeeze...).
- `pc equity` : pour vérifier l'équité moyenne de la range construite contre une range adverse de référence, à titre de sanity check.
- `decision-factors` : facteurs qualitatifs à croiser, en G5 seulement (`pc brief` charge cette skill lui-même le cas échéant).
- `references/baseline-ranges.md` : ranges 6-max v1, gardées pour la convention de notation d'origine.
- `scripts/range_stats.py`, `scripts/hand_rank.py` (v1, conservés) : % de mains/combos d'une range, et classement de mains candidates par équité contre une range adverse — utiles pour situer une main proche d'une frontière (voir ci-dessous). Ce ne sont pas des solveurs : classement par équité brute seule.

## Situer une main dans une range de call (cas d'usage fréquent)

1. `pc state`/`pc brief` donnent l'équité requise (`pot_odds`) pour un call rentable.
2. `scripts/hand_rank.py` sur un petit groupe de mains voisines de X contre la range adverse narrowée (`pc narrow`) pertinente.
3. Identifier la main juste au-dessus/en dessous du seuil parmi ce groupe — montrer l'écart réel, pas un verdict binaire.
4. Rappeler que ce classement se fonde sur l'équité seule : la vraie frontière tient aussi compte de la position, des blockers, de la jouabilité postflop.

## Démarche

1. **Cadrer la situation** : position (dérivée en `n_behind`/`ip_postflop`), profondeur de stack (100bb par défaut), type d'action, contexte adverse.
2. **Proposer le point de départ** de `pc brief`, avec sa `confidence` explicite.
3. **Construire avec l'utilisateur, pas à sa place** : proposer, laisser trancher les mains limites.
4. **Ajuster** : linéaire pour un open-raise, polarisée pour un 3bet/squeeze ; élargir face à Fish/Maniac, resserrer face à un TAG solide ou si des joueurs solides restent à parler derrière (`n_behind` élevé).
5. **Sortir en notation standard** (`range-notation`) avec ses stats (`range_stats.py`).
6. **Sanity check optionnel** : `pc equity` de la range construite contre une range adverse typique.

## Ce que cette skill NE fait PAS

N'invente pas une "réponse solver exacte" — les valeurs de référence sont explicitement approximatives, marquées `confidence`. Pour une précision de niveau solveur → `solver-reader` avec un export réel.

## Ce que cette skill NE couvre PAS

L'analyse d'une main déjà jouée avec une range déjà décidée en tête → `hand-review`. Le déroulé d'une session complète avec ces ranges en pratique → `live-session`.
