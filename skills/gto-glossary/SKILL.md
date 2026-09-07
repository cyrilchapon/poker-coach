---
name: gto-glossary
description: Glossaire du jargon standard des solveurs et de la théorie GTO en no-limit hold'em (ranges, EV, SPR, MDF, blockers, polarisation, ICM, etc.). À consulter et citer explicitement chaque fois qu'un concept technique est mentionné dans hand-review, concept-tutor, range-builder ou live-session — l'objectif est d'expliquer AVEC le vocabulaire habituel, pas de le contourner. Utiliser systématiquement : introduire le terme en gras la première fois qu'il apparaît dans une session, avec une définition d'une phrase, puis l'utiliser librement ensuite sans re-expliquer.
---

# Glossaire GTO / jargon solveur

## Règle d'usage

Ce glossaire est la référence terminologique commune. Toutes les autres skills doivent :
1. Utiliser ces termes exacts (pas de paraphrase qui évite le jargon).
2. Définir un terme en une phrase courte la première fois qu'il apparaît dans une session donnée, en gras.
3. Ne pas re-définir un terme déjà introduit dans la même session, sauf si l'utilisateur demande un rappel.

## Échelle de sizing (taille de mise relative au pot)

**Convention canonique — deux formules différentes selon le contexte, à ne jamais confondre :**
- **BET** (première mise sur une rue, rien à caller avant) : %pot = mise ÷ pot **avant** cette mise.
- **RAISE** (relance d'une mise existante) : le %pot s'applique à la **portion au-dessus du call**, rapportée au pot *après avoir callé* — formule standard du "pot raise" : `pot_après_call = pot_avant + mise_adverse + call ; portion_relance = fraction × pot_après_call ; relancer_à(total) = call + portion_relance`.

Une confusion réelle entre ces deux formules a déjà produit deux réponses différentes ("48% du pot" puis "1/4 de pot") pour la même relance en session. **Ne plus jamais calculer un sizing de tête** : utiliser `equity-engine/scripts/sizing.py` (`bet-pct` ou `raise-to`).

Repère qualitatif une fois le montant calculé :
- **< 50% pot** : mise petite/"small" — souvent une range large, peu polarisée.
- **50-75% pot** : standard — la taille la plus courante en cash game, aussi bien pour la value que le bluff.
- **75-100% pot** : grosse mise — commence à polariser la range (plus de value nette et de bluffs, moins de mains moyennes).
- **> 100% pot (overbet)** : au-delà du pot — polarise fortement ; à ce stade la range de mise contient rarement des mains moyennes, plutôt du très fort ou du bluff pur.
Toujours vérifier que le pot de référence utilisé pour ce calcul **inclut déjà toutes les mises de la rue en cours** avant de qualifier une taille (cf. `live-session`).

## Termes fondamentaux

- **Range** : l'ensemble pondéré des mains qu'un joueur peut avoir dans une situation donnée, représenté sur une matrice 13x13 (169 combos de départ).
- **Combo** : une combinaison précise de deux cartes (ex : A♠K♥ est un combo parmi les 16 combos d'AK).
- **Équité** : probabilité de gagner la main si elle allait au tapis immédiatement, compte tenu des ranges/mains en présence.
- **EV (Expected Value)** : gain moyen espéré d'une décision sur un grand nombre de répétitions.
- **Cotes du pot (pot odds)** : rapport entre la mise à payer et la taille du pot après paiement ; détermine l'équité minimale requise pour un call rentable.
- **SPR (Stack-to-Pot Ratio)** : rapport stack effectif / taille du pot ; conditionne l'agressivité et la polarisation des ranges postflop.
- **MDF (Minimum Defense Frequency)** : fréquence minimale à laquelle défendre (ne pas fold) face à une mise pour empêcher l'adversaire de bluffer de façon automatiquement rentable.
- **Fréquence mixte / stratégie mixte** : une solution GTO qui prescrit plusieurs actions différentes avec la même main selon une fréquence donnée (ex : bet 70% / check 30%), plutôt qu'une action pure.
- **Blocker** : carte en main qui réduit la probabilité que l'adversaire détienne certaines combos (utile pour bluffer ou pour évaluer un call).
- **Range polarisée** : range composée de mains très fortes + bluffs, sans mains moyennes (typique des gros overbets/all-in).
- **Range linéaire (ou "merged")** : range composée des meilleures mains dans l'ordre de force, sans bluffs purs (typique d'un raise standard).
- **Range condensée** : range resserrée autour de mains moyennes-fortes, sans les meilleures ni les pires combos.
- **Range advantage** : quand un joueur a, en moyenne, une range plus forte que l'autre sur un board donné.
- **Nut advantage** : quand un joueur a une plus grande proportion des toutes meilleures mains possibles (les "nuts") sur ce board.
- **C-bet (continuation bet)** : mise faite par le dernier agresseur de la rue précédente.
- **3bet / 4bet / 5bet** : deuxième, troisième, quatrième relance d'une même série d'enchères sur une rue.
- **Squeeze** : 3bet après une ouverture ET un ou plusieurs calls, visant les deux ranges à la fois.
- **Isolation raise (iso-raise)** : relance visant à isoler un limpeur (l'affronter en heads-up).
- **GTO (Game Theory Optimal)** : stratégie d'équilibre, inexploitable par définition, indépendante du comportement adverse.
- **Exploit / jeu exploitant** : dévier volontairement du GTO pour maximiser l'EV contre un adversaire dont les tendances ne sont pas équilibrées.
- **ICM (Independent Chip Model)** : modèle convertissant les jetons en valeur monétaire réelle en tournoi, qui rend les jetons non-linéaires en valeur (important pour les décisions en bulle/final table).
- **Bubble factor** : facteur de risque accru en approche de bulle de tournoi (ICM), qui resserre les ranges de call.

## Ce que cette skill NE couvre PAS

Les calculs numériques eux-mêmes (équité exacte, EV chiffrée) → `equity-engine`. La construction concrète d'une range pour une situation donnée → `range-notation` + `range-builder`.
