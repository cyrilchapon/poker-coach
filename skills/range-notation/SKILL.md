---
name: range-notation
description: Notation standard des ranges en no-limit hold'em (syntaxe type Equilab/solveur — AA, AKs, ATo+, 22-99, JTs-98s) et représentation matrice 13x13. À consulter dès qu'une range doit être écrite, lue, affichée à l'utilisateur, ou transmise à equity-engine. Toujours utiliser cette notation exacte plutôt qu'une description en prose ("les grosses paires et les gros As") — le jargon précis fait partie de l'objectif pédagogique.
---

# Range Notation

## Syntaxe (référence)

| Notation | Signifie |
|---|---|
| `AA` | Une paire précise |
| `AKs` | As-Roi suited (assortis, même couleur) — 4 combos |
| `AKo` | As-Roi offsuit — 12 combos |
| `AK` | AKs + AKo réunis (16 combos) si le suffixe est omis |
| `22+` | Toutes les paires de 22 à AA |
| `22-77` | Les paires de 22 à 77 uniquement |
| `ATs+` | ATs, AJs, AQs, AKs (le second rang monte jusqu'à juste sous le premier) |
| `ATo+` | Idem en offsuit |
| `JTs-98s` | Tous les connecteurs suited entre 98s et JTs inclus (98s, T9s, JTs) |

Notation **non supportée pour l'instant** par `equity-engine` (limitation connue) : pondération explicite type `QQ@50%` (range partielle/mixte), et les ranges "gapped" irrégulières écrites à la main (dans ce cas, lister les combos un par un).

## Matrice 13x13

Représentation canonique d'une range : grille 13x13, rangs de A (haut/gauche) à 2 (bas/droite).
- Diagonale = paires
- Au-dessus de la diagonale = suited
- En dessous de la diagonale = offsuit

Nombre total de combos de départ : 1326 (169 mains distinctes pondérées par leur nombre de combos : 6 par paire, 4 par suited, 12 par offsuit).

Pour calculer le % d'une range donnée : (somme des combos inclus) / 1326.

## Utilisation avec les autres skills

- Toujours écrire une range en notation ci-dessus quand on la présente à l'utilisateur (jamais uniquement "sa range de call standard" sans la lister).
- Passer cette notation telle quelle en argument à `equity-engine` (le script `scripts/equity.py` parse directement cette syntaxe).
- `range-builder` (à venir) utilisera cette notation comme format de sortie standard.

## Ce que cette skill NE couvre PAS

Le calcul d'équité réel → `equity-engine`. La construction stratégique d'une range pour une situation donnée (quelle range ouvrir en CO à 100bb) → `range-builder`.
