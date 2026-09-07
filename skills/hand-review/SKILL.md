---
name: hand-review
description: Analyse une main réellement jouée par l'utilisateur (décrite manuellement ou collée depuis un hand history), rue par rue, en s'appuyant sur `pc brief`. À utiliser quand l'utilisateur veut faire réviser une main qu'il a vraiment jouée — pas une simulation (→ live-session pour ça).
---

# Hand Review

## v2 : un appel par rue, pas une checklist manuelle de 4-5 outils

Reconstruire l'état de la main en `hand.json` (voir le schéma dans `docs/brief/references/02-architecture-v2.md` — table, seats, streets, to_act ; chemin absolu de `docs/` via `scripts/pc paths`, clé `docs_dir`), puis à chaque point de décision qui intéresse l'utilisateur :

```bash
scripts/pc brief --hand hand.json [--villain-archetype X]
```

Un seul appel remplace toute la checklist v1 (range narrowing → équité → describe_hand → sizing → decision-factors → glossaire). La verbosité de la réponse suit le gate retourné (`verbosity` dans la sortie) : une ligne si `G0`/`G1`, le chiffre qui tranche si `G3`, l'analyse complète avec `decision-factors` chargé seulement si `G5`. Ne pas produire une analyse en 6 points sur une décision que le moteur a déjà tranchée en G0-G2.

## Formats d'entrée supportés

1. **Description manuelle** : l'utilisateur raconte la main (positions, stacks, actions, cartes connues) — traduire en `hand.json` au fil de la reconstruction, demander ce qui manque (stack depth notamment) plutôt que deviner.
2. **Hand history collée** : pas de parseur automatique pour l'instant (format Winamax non étudié). Lire et extraire manuellement plutôt que refuser, signaler que ça pourra être industrialisé si le besoin devient récurrent.

## Méthode

1. **Reconstruire l'état de la main** rue par rue dans `hand.json`.
2. **Identifier les points de décision réellement intéressants** — ne pas commenter chaque action de façon égale, se concentrer sur les rues où un choix non trivial a eu lieu.
3. **Si l'utilisateur n'a pas précisé quelle rue/décision l'intéresse**, demander plutôt que de tout décortiquer par défaut.
4. **Pour chaque décision analysée** : `pc brief`, et toujours distinguer explicitement "ligne du moteur" vs "ajustement exploitant" (`exploit-coach`) quand un `--villain-archetype` change la conclusion.
5. **Pour visualiser une main complexe/multiway** si ça aide à la clarté : `scripts/pc render --hand hand.json` (pas obligatoire pour une main simple en heads-up).
6. **Repérer les patterns récurrents** si plusieurs mains sont passées en revue dans la même conversation — rester factuel, pas de diagnostic caractériel sur l'utilisateur.

## Ce que cette skill NE couvre PAS

Jouer une main simulée en temps réel → `live-session`. La construction de ranges de référence en dehors d'une main précise → `range-builder`. Les questions de théorie pure détachées d'une main → `concept-tutor`.
