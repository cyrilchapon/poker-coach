---
name: gto-glossary
description: Glossaire du jargon standard des solveurs et de la théorie GTO en no-limit hold'em (ranges, EV, SPR, MDF, blockers, polarisation, ICM, etc.), servi par lookup au lieu d'être préchargé en entier. À consulter et citer explicitement chaque fois qu'un concept technique est mentionné dans hand-review, concept-tutor, range-builder ou live-session — l'objectif est d'expliquer AVEC le vocabulaire habituel, pas de le contourner.
---

# Glossaire GTO / jargon solveur

## v2 : lookup, pas préchargement

En v1 ce fichier faisait ~5,9 ko et était chargé en entier dans le contexte, que la décision soit triviale ou non. En v2, le glossaire vit dans `pokercoach/glossary.py` et se consulte terme par terme :

```bash
scripts/pc glossary MDF
scripts/pc glossary "pot odds"
scripts/pc glossary blocker
```

Retourne une définition d'une phrase (quarante caractères, pas 5,9 ko). Termes disponibles : range, combo, équité, EV, pot odds, SPR, MDF, blocker, range polarisée/linéaire/condensée, range advantage, nut advantage, c-bet, 3bet, 4bet, squeeze, iso-raise, GTO, exploit, ICM, bubble factor, n_behind, ip_postflop, ATT, DEF, TPTK, gate.

## Règle d'usage (inchangée)

1. Utiliser ces termes exacts (pas de paraphrase qui évite le jargon).
2. Définir un terme en une phrase courte, en gras, la première fois qu'il apparaît dans une session donnée.
3. Ne pas re-définir un terme déjà introduit dans la même session, sauf rappel demandé.

## Échelle de sizing (taille de mise relative au pot)

**Convention canonique — deux formules différentes selon le contexte, à ne jamais confondre :**
- **BET** (première mise sur une rue) : %pot = mise ÷ pot **avant** cette mise.
- **RAISE** (relance d'une mise existante) : le %pot s'applique à la **portion au-dessus du call**, rapportée au pot *après avoir callé*.

Repère qualitatif une fois le montant calculé : < 50% pot = small (range large, peu polarisée) ; 50-75% = standard ; 75-100% = grosse mise (polarise) ; > 100% (overbet) = fortement polarisée.

## Ce que cette skill NE couvre PAS

Les calculs numériques eux-mêmes (équité exacte, EV chiffrée, budget ATT/DEF) → `pc equity`, `pc budget`, `pc brief`. La construction concrète d'une range → `range-notation` + `range-builder`.
