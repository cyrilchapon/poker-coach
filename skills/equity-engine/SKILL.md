---
name: equity-engine
description: Calcul d'équité main vs range ou range vs range (Monte-Carlo), exécuté via le script Python fourni (scripts/equity.py, basé sur treys) dans le sandbox. À consulter dès qu'un calcul d'équité, de cotes d'appel, ou d'EV chiffrée est nécessaire — jamais estimer une équité "à l'oeil" quand ce script peut donner un chiffre exact.
---

# Equity Engine

## Prérequis (une fois par session sandbox)

```bash
pip install treys --break-system-packages -q
```

## Usage

```bash
python3 scripts/equity.py "<range1>" "<range2>" --board "<board>" --dead "<dead>" --iters 20000
```

**Pour qualifier une main en cours (type de main, outs réels) plutôt que comparer deux ranges**, utiliser `scripts/describe_hand.py` — voir `poker-rules` pour la règle d'usage obligatoire (jamais évaluer une main "à l'œil").

- `range1` / `range2` : notation `range-notation` (ex : `"QQ+,AKs,AKo"`)
- `--board` : cartes communes déjà tombées, format concaténé sans espace (ex : `"Ah7c2d"`), vide si preflop
- `--dead` : cartes mortes/connues à exclure (ex : la main du héros si on calcule deux ranges adverses)
- `--iters` : nombre de simulations (20000 = bon compromis précision/vitesse, monter à 50000+ pour un board serré avec peu de combos restants)

Sortie : `{"range1_equity": ..., "range2_equity": ..., "iterations_used": ...}` (equity en fraction, ex 0.75 = 75%).

## Cas d'usage typiques

- **Main vs range** : passer `range1` comme une notation à un seul combo (ex : `"AsKh"` n'est pas supporté tel quel par le parseur actuel — utiliser la forme abstraite la plus proche, ex `"AKs"` si suited, en notant que ça inclut les 4 combos et pas seulement celui du héros ; limitation connue, voir ci-dessous).
- **Range vs range preflop** : `--board ""`.
- **Range vs range postflop** : renseigner `--board`.
- **Cotes du pot vs équité** : calculer l'équité requise pour un call = mise / (pot + 2×mise), puis comparer au résultat du script pour statuer sur la rentabilité — toujours faire ce lien explicitement avec le glossaire (`gto-glossary` → pot odds).

## Limitations connues (à corriger si besoin)

- Pas de calcul exact pour une main précise à deux cartes fixées **dans `equity.py`** (le parseur travaille par catégories abstraites : paire/suited/offsuit) — mais `describe_hand.py`, lui, prend des cartes précises et donne un type de main/des outs exacts, pas une catégorie. Utiliser `describe_hand.py` pour qualifier une main exacte, `equity.py` pour comparer des ranges.
- Pas de pondération `@xx%` (range partielle).
- Simulation Monte-Carlo, pas énumération exhaustive : fiable à ±0.5-1% avec 20000 itérations, mais pas un chiffre à la décimale près comme un vrai solver.

## Ce que cette skill NE couvre PAS

La stratégie de mise (fréquences GTO, mix) → `solver-reader` pour des solutions exportées, ou raisonnement qualitatif via `gto-glossary`. La construction de la range elle-même → `range-notation` / `range-builder`.
