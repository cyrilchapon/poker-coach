---
name: concept-tutor
description: Répond à une question sur un concept de théorie du poker détachée d'une main précise (ex "c'est quoi le MDF", "pourquoi on polarise en 3bet", "explique-moi l'ICM"), en creusant le pourquoi et en donnant si possible un exemple chiffré calculé en direct. À utiliser dès que l'utilisateur pose une question de compréhension pure, par opposition à une question liée à une main en cours (→ live-session/hand-review).
---

# Concept Tutor

## Dépendances

- `gto-glossary` : point d'ancrage terminologique — la définition courte du terme y existe déjà, ne pas la dupliquer, s'appuyer dessus.
- `decision-factors` : pour les concepts déjà couverts là-bas (position, SPR, implied odds, fold equity) — creuser depuis cette base plutôt que de réécrire une explication parallèle.
- `equity-engine` / `range-notation` : pour tout exemple chiffré — toujours préférer un calcul réel (via `scripts/equity.py`) à un chiffre inventé.

## Méthode

1. **Ne jamais supposer de prérequis acquis.** L'utilisateur connaît les concepts "de loin" mais n'en maîtrise aucun en profondeur — reconstruire depuis la base à chaque fois, même si le concept semble élémentaire.
2. **Expliquer le pourquoi, pas juste répéter la définition.** `gto-glossary` donne le "quoi" en une phrase ; cette skill doit répondre à "pourquoi c'est comme ça" et "qu'est-ce que ça change en pratique".
3. **Préférer un exemple chiffré calculé en direct** à un exemple abstrait ou inventé, quand c'est pertinent : construire une range concrète (`range-notation`), calculer son équité ou ses stats (`equity-engine`, `range_stats.py` de `range-builder`), et commenter le résultat réel plutôt qu'un chiffre generique de manuel.
4. **Format libre, pas de structure imposée** : c'est du Q&A pur, pas une revue de main. Répondre directement, avec un exemple seulement s'il clarifie vraiment (pas systématiquement).
5. **Ne pas dupliquer** : si la question touche un concept déjà couvert par `decision-factors` (position, SPR, implied/reverse implied odds, fold equity) ou par les tableaux de `range-builder`, s'appuyer dessus explicitement plutôt que de refaire une explication parallèle qui risque de diverger.

## Ce que cette skill NE couvre PAS

L'application d'un concept à une main précise en cours ou déjà jouée → `live-session` / `hand-review`. La construction concrète d'une range pour une situation → `range-builder`.
