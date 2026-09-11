---
name: hand-review
description: Analyse une main réellement jouée par l'utilisateur (décrite manuellement ou collée depuis un hand history), rue par rue, en s'appuyant sur `pc brief`. À utiliser quand l'utilisateur veut faire réviser une main qu'il a vraiment jouée — pas une simulation (→ live-session pour ça).
---

# Hand Review

## Ton rôle : l'expert, c'est toi ; le moteur, c'est ton solveur

Même posture qu'en `live-session` (voir cette skill pour la version détaillée), en trois règles :

1. **Consulter avant de parler.** Force de main, outs, équité, cotes, range adverse, verdict : toujours l'outil (`pc hand`, `pc equity`, `pc narrow`, `pc brief`), jamais une évaluation de tête, même sur un cas « évident ».
2. **Dater chaque affirmation par sa rue.** Décrire la main telle qu'elle était au moment de la décision commentée, jamais telle qu'elle a fini — ne jamais justifier un call préflop par une paire touchée au flop, ni juger une décision par le résultat du showdown. Le `pc brief` qui appuie un commentaire est celui de la rue commentée.
3. **Dévier du moteur : permis, jamais en silence.** Faire calculer d'abord, puis nommer la raison contextuelle (historique, dynamique de table, profil observé, sizing atypique) et annoncer l'écart explicitement : « le moteur dit X avec tel chiffre ; ici je pencherais pour Y parce que… ». Une déviation non annoncée est un bug.

En zone grise (gate `G5`), aller chercher le niveau de précision au-dessus (`pc brief --depth full`, `pc narrow`, `pc equity` contre une range que tu écris) plutôt que de conclure au feeling.

## Un appel par rue, pas une checklist manuelle

Reconstruire l'état de la main en `hand.json` (voir le schéma dans `docs/brief/references/02-architecture-v2.md` — table, seats, streets, to_act ; chemin absolu de `docs/` via `scripts/pc paths`, clé `docs_dir`), puis à chaque point de décision qui intéresse l'utilisateur :

```bash
scripts/pc brief --hand hand.json [--villain-archetype X]
```

`pc brief` enchaîne lui-même range narrowing → équité → classification de main → sizing → gates, dans le bon ordre : ne pas rejouer cette chaîne outil par outil. La verbosité de la réponse suit le gate retourné (`verbosity` dans la sortie) : une ligne si `G0`/`G1`, le chiffre qui tranche si `G3`, l'analyse complète avec `decision-factors` chargé seulement si `G5`. Ne pas produire une analyse en 6 points sur une décision que le moteur a déjà tranchée en G0-G2.

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
