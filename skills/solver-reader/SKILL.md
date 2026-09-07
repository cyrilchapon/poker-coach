---
name: solver-reader
description: Lecture et interprétation d'exports de solveur externe (Desktop Postflop, TexasSolver, ou tout export CSV/JSON de fréquences par action) pour en tirer une explication pédagogique — fréquences, EV par ligne, mix de stratégies. À consulter dès que l'utilisateur upload un fichier d'export solveur à analyser ou demande de commenter une solution GTO déjà calculée ailleurs.
---

# Solver Reader

## Principe

Les formats d'export varient selon l'outil et la version (Desktop Postflop, TexasSolver, PioSolver, GTO+ n'ont pas un schéma de colonnes identique). Plutôt que de supposer un format fixe, la démarche est :

1. **Inspecter le fichier réellement fourni** (colonnes, structure JSON) avant toute interprétation — ne jamais deviner un schéma à l'aveugle.
2. Identifier au minimum : la main/combo, l'action (check/bet/raise + taille), la fréquence associée, l'EV si présente.
3. Reformuler le résultat en langage pédagogique en s'appuyant systématiquement sur `pc glossary` (fréquence mixte, EV, blocker, polarisation...) — ne jamais recracher un tableau brut sans l'expliquer.

## Ce qu'il faut mettre en avant à chaque lecture

- **Les lignes à fréquence mixte** (ex : bet 65% / check 35% avec la même main) : les plus instructives pédagogiquement, à toujours signaler explicitement et expliquer pourquoi le solveur mélange.
- **Les écarts entre mains apparemment similaires** (deux top-paires qui ne jouent pas pareil) : révéler la raison (blocker, texture de range, EV en cas de call).
- **Le lien avec `range-notation`** : convertir les combos du solver dans la notation standard pour rester cohérent avec `pc equity`/`pc narrow`.

## Comparer à la référence maison

Une fois une ligne solveur identifiée, la comparer au budget ATT/DEF du moteur (`pc budget --hand hand.json`) sur la même situation reconstruite : un écart notable entre le verdict du solveur et le budget est en soi une donnée pédagogique intéressante (le budget est une heuristique experte, pas une sortie de solveur — `pc hand`/`pc budget` le disent explicitement).

## Limitation actuelle

Pas de parseur automatisé prêt à l'emploi (pas de schéma unique fiable à coder en dur). Premier usage réel = l'occasion de construire un script d'extraction dédié au format que l'utilisateur utilise effectivement (probablement Desktop/WASM Postflop en local, gratuit).

## Ce que cette skill NE couvre PAS

Faire tourner le solveur lui-même (outil local, hors de ce sandbox). Pour un calcul d'équité simple/rapide sans solveur externe → `equity-engine` (`pc equity`).
