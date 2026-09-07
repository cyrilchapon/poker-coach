---
name: poker-rules
description: Référence des règles exactes du No-Limit Texas Hold'em (mains, tours d'enchères, blinds/antes, side pots, showdown, procédures TDA pour les tournois). À consulter dès qu'une question porte sur la légalité d'une action, une procédure de table, un litige de règle, ou pour trancher un cas limite (string bet, all-in incomplet, angle shoot, ordre de parole au showdown). Sert de fondation factuelle aux autres skills du coach — ne jamais improviser une règle sans la vérifier ici.
---

# Règles du No-Limit Texas Hold'em

## Structure de la main

1. **Blinds/Antes** : SB, BB (et éventuellement ante — big blind ante ou ante classique). Le bouton se déplace d'un siège après chaque main.
2. **Preflop** : chaque joueur reçoit 2 cartes fermées. Enchères commencent à gauche de la BB (UTG).
3. **Flop** : 3 cartes communes. Enchères commencent au premier joueur actif à gauche du bouton.
4. **Turn** : 4e carte commune. Même ordre d'enchères que le flop.
5. **River** : 5e carte commune. Même ordre.
6. **Showdown** : le dernier agresseur (dernier à avoir misé/relancé) montre en premier. S'il n'y a pas eu de mise à la dernière rue, le premier joueur actif à gauche du bouton montre en premier.

## Classement des mains (du plus fort au plus faible)

Quinte flush royale > Quinte flush > Carré > Full > Couleur > Suite > Brelan > Deux paires > Paire > Carte haute.
En cas d'égalité de rang, les kickers départagent (les 5 meilleures cartes sur 7 comptent).

## Betting rules (NLHE)

- **Mise minimale d'ouverture** : au moins la taille de la BB.
- **Relance minimale** : au moins la taille de la dernière mise/relance (le "raise increment"), pas seulement le montant total. Ex : BB=2, raise à 6 (increment 4) → la relance suivante doit être d'au moins 10 (6+4).
- **All-in insuffisant pour constituer une relance légale** : ne rouvre pas les enchères pour les joueurs ayant déjà agi, sauf si le all-in est d'au moins 50% d'un raise complet (règle courante, variable selon la salle/le TD).
- **Side pots** : créés dès qu'un joueur est all-in pour moins que la mise en cours ; il ne peut gagner que le pot principal + les side pots auxquels il a contribué.
- **String bet** : interdit — annoncer le montant ou pousser les jetons en un seul mouvement continu.
- **Action out of turn** : peut engager le joueur selon les règles TDA en vigueur (2026 : agir passivement hors tour dans un pot heads-up fait perdre le droit d'agir agressivement quand le tour arrive réellement).

## Cas limites à vérifier via TDA

Pour tout litige non couvert ci-dessus (angle shooting, dealer error, misdeal, joueur absent au moment de l'action, etc.), se référer aux règles officielles TDA : https://www.pokertda.com/poker-tda-rules/ — c'est la norme de facto du circuit live mondial, réactualisée en 2026.

## Vérification obligatoire de toute affirmation sur une main — jamais à l'œil

**Deux erreurs réelles constatées en session de test** : un tirage quinte annoncé avec seulement 4 cartes consécutives (il en faut 5 — impossible avec une seule carte à venir), et une main décrite comme "deux paires aux As" alors que la seule paire venait du board (la vraie main était juste "paire d'As, kickers"). Les deux fois, l'erreur a été commise en évaluant la main de tête.

**Règle dure, sans exception** : toute affirmation sur le type/la force d'une main en cours, ou sur le nombre d'outs disponibles, doit passer par `equity-engine/scripts/describe_hand.py` — jamais une évaluation manuelle, même quand la main semble évidente. Ça s'applique à **chaque rue**, pas seulement au showdown (qui a son propre outil, `showdown.py`, pour départager un abattage complet — `describe_hand.py` sert lui à qualifier une main *en cours de coup*, avant la fin).

```bash
python3 scripts/describe_hand.py "<main>" "<board>"                # type de main exact
python3 scripts/describe_hand.py "<main>" "<board>" --outs          # + les vrais outs (flop ou turn uniquement)
```

Accepte indifféremment la notation lettres (`9d9h`) et Unicode (`9♦9♥`), y compris copiée directement depuis le rendu de `live-session`.

## Ce que cette skill NE couvre PAS

Stratégie (ranges, GTO, exploit) → voir `range-notation`, `gto-glossary`, `equity-engine`. Cette skill est uniquement la couche "règles du jeu", jamais la couche "comment bien jouer".
