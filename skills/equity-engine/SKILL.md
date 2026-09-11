---
name: equity-engine
description: Calcul d'équité main vs range ou range vs range, exécuté via `pc equity` (backend eval7/pure-Python, énumération exhaustive ou Monte-Carlo). À consulter dès qu'un calcul d'équité, de cotes d'appel, ou d'EV chiffrée est nécessaire — jamais estimer une équité "à l'oeil" quand cette commande peut donner un chiffre exact.
---

# Equity Engine

## Invocation

Sous-programme du CLI `pc`, invoqué via `scripts/pc` (à la racine de cette skill) : rien à installer, il se localise lui-même (voir `engine`).

```bash
scripts/pc equity --hand hand.json --vs "<range>"                       # cartes exactes du héros vs une range
scripts/pc equity --range1 "<range1>" --vs "<range2>" --board "..." --dead "..." --iterations 20000
```

- `--range1` / `--vs` : notation `range-notation` (ex `"QQ+,AKs"`), y compris une main exacte (`AsKd`) et la pondération `@xx%`.
- `--board` / `--dead` : cartes séparées par des virgules (ex `"Ah,7c,2d"`), vides si non pertinent.
- `--iterations` : Monte-Carlo seulement (voir méthode ci-dessous), 20000 par défaut.

Sortie : `{"range1_equity": ..., "range2_equity": ..., "method": "enumeration"|"monte_carlo", "iterations": ..., "combos_used": ...}`.

**Pour qualifier la main en cours** (type de main exact, outs réels) plutôt que comparer deux ranges, utiliser `pc hand` — voir `poker-rules` pour la règle d'usage obligatoire.

## Méthode (transparente, pas besoin de la choisir)

Énumération exhaustive quand le volume (combos × runouts restants) reste dans un budget raisonnable — résultat exact, pas d'itérations. Sinon Monte-Carlo (graine fixe, résultat reproductible) sur le nombre d'itérations demandé. Le champ `method` de la sortie dit laquelle a été utilisée.

## Cas d'usage typiques

- Cotes d'un call : comparer `range1_equity` au seuil `to_call / (pot + to_call)` (déjà fourni par `pc state`/`pc brief` sous `pot_odds`).
- Main précise vs range adverse narrowée (`pc narrow`) : décision de call/fold la plus fréquente en session.
- Range vs range : sanity check d'une range construite (`range-builder`).

## Sizing (%pot / montant de relance)

```bash
scripts/pc sizing bet-pct --bet 10 --pot-before 15.5
scripts/pc sizing raise-to --pot-before-bet 6.5 --bet-to-call 3.5 --fraction 1.0
```

Jamais de calcul de tête — voir `pc glossary` pour la convention bet vs raise.

## Ce que cette skill NE couvre PAS

La classification de la main en cours (type, outs, blockers) → `pc hand`. La construction/le narrowing d'une range → `range-notation`, `range-builder`, `pc narrow`.
