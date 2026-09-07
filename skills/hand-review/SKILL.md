---
name: hand-review
description: Analyse une main réellement jouée par l'utilisateur (décrite manuellement ou collée depuis un hand history), rue par rue, en s'appuyant sur poker-rules, range-notation, equity-engine, decision-factors et gto-glossary. À utiliser quand l'utilisateur veut faire réviser une main qu'il a vraiment jouée — pas une simulation (→ live-session pour ça).
---

# Hand Review

## Dépendances

- `poker-rules` : pour valider la légalité/le déroulé de la main si un doute apparaît.
- `range-notation` : pour exprimer les ranges de chaque joueur à chaque étape.
- `equity-engine` : pour tout calcul d'équité pertinent à un point de décision, **et pour toute affirmation sur le type de main/les outs via `scripts/describe_hand.py` — jamais à l'œil (règle dure, voir `poker-rules`)**. Une revue de main manipule des mains complètes/quasi complètes tout autant qu'une session live : le même risque d'évaluation improvisée s'applique intégralement ici.
- `decision-factors` : position, implied odds, SPR, fold equity, joueurs restants — à croiser systématiquement, pas juste l'équité brute.
- `gto-glossary` : vocabulaire à utiliser partout.
- Le rendu ASCII de `live-session` (`scripts/render_table.py`) est réutilisable ici pour visualiser une main complexe/multiway si ça aide à la clarté — pas obligatoire pour une main simple en heads-up.

## Formats d'entrée supportés

1. **Description manuelle** : l'utilisateur raconte la main (positions, stacks, actions, cartes connues). C'est le format principal pour l'instant.
2. **Hand history collée** : pas de parseur automatique pour l'instant (le format Winamax n'a pas encore été étudié — cf. l'open item noté au tout début du projet). Si l'utilisateur colle un hand history brut, le lire et en extraire manuellement les infos nécessaires plutôt que refuser, mais signaler que ça pourra être industrialisé plus tard si le besoin devient récurrent.

## Méthode

1. **Reconstruire l'état de la main** rue par rue : positions, stacks, actions, montants. Demander ce qui manque plutôt que de deviner (stack depth notamment, souvent omis).
2. **Identifier les points de décision réellement intéressants** — ne pas commenter chaque action de façon égale, se concentrer sur les rues où un choix non trivial a eu lieu (cohérent avec le principe déjà appliqué en `live-session` : ne pas noyer d'information sur les actions évidentes).
3. **Si l'utilisateur n'a pas précisé quelle rue/décision l'intéresse**, demander plutôt que de tout décortiquer par défaut — une revue de main ciblée est plus utile qu'une revue exhaustive mécanique.
4. **Pour chaque décision analysée** : équité pertinente (`equity-engine`) si utile, facteurs qualitatifs (`decision-factors`) qui changent la conclusion, et toujours distinguer explicitement "ligne GTO" vs "ajustement exploitant" comme dans `live-session`.
5. **Repérer les patterns récurrents** si plusieurs mains sont passées en revue dans la même conversation (ex : "c'est la 2e fois que tu sur-call une range de 3bet resserrée") — mais rester factuel, pas de diagnostic caractériel sur l'utilisateur.

## Ce que cette skill NE couvre PAS

Jouer une main simulée en temps réel → `live-session`. La construction de ranges de référence en dehors d'une main précise → `range-builder`. Les questions de théorie pure détachées d'une main → `concept-tutor`.
