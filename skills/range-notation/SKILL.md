---
name: range-notation
description: Notation standard des ranges en no-limit hold'em (syntaxe type Equilab/solveur — AA, AKs, ATo+, 22-99, JTs-98s, AsKd, QQ@50%) et représentation matrice 13x13. À consulter dès qu'une range doit être écrite, lue, affichée à l'utilisateur, ou transmise à pc equity/pc narrow. Toujours utiliser cette notation exacte plutôt qu'une description en prose ("les grosses paires et les gros As") — le jargon précis fait partie de l'objectif pédagogique.
---

# Range Notation

## Syntaxe (référence — implémentée par `pokercoach.equity.parse_range`, consommée par `pc equity` et `pc narrow`)

| Notation | Signifie |
|---|---|
| `AA` | Une paire précise |
| `AKs` | As-Roi suited — 4 combos |
| `AKo` | As-Roi offsuit — 12 combos |
| `AK` | AKs + AKo réunis (16 combos) si le suffixe est omis |
| `22+` | Toutes les paires de 22 à AA |
| `22-77` | Les paires de 22 à 77 uniquement |
| `ATs+` | ATs, AJs, AQs, AKs |
| `ATo+` | Idem en offsuit |
| `JTs-98s` | Tous les connecteurs suited entre 98s et JTs inclus |
| `AsKd` (ou `A♠K♦`) | **Une main exacte à deux cartes** — levée en v2 de la limitation v1 |
| `QQ@50%` | **Pondération explicite** — nouveau en v2, sur n'importe quel token (`77-99@30%`, `AJs+@60%`) |

Séparateur entre tokens : la virgule. Espaces ignorés.

## Matrice 13x13

Représentation canonique d'une range : grille 13x13, rangs de A (haut/gauche) à 2 (bas/droite). Diagonale = paires, au-dessus = suited, en dessous = offsuit. 1326 combos de départ (169 mains distinctes : 6 par paire, 4 par suited, 12 par offsuit). % d'une range = (combos inclus) / 1326.

## Utilisation avec le moteur

```bash
pc equity --range1 "QQ+,AKs" --vs "22+,A2s+,K7s+,Q9s+" --board "9d,6c,2h"
pc narrow --hand hand.json --action call --range "22+,A2s+,K7s+"
```

`pc equity` accepte aussi `--hand hand.json` pour utiliser directement les deux cartes exactes du héros comme `range1`.

## Ce que cette skill NE couvre PAS

Le calcul d'équité réel → `pc equity`. La construction stratégique d'une range pour une situation donnée → `range-builder`.
