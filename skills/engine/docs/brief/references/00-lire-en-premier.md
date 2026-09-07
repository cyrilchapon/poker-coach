# Ordre de lecture

| # | Fichier | Quand |
|---|---|---|
| 0 | `../PROMPT.md` | Le cadrage. À lire en entier avant tout. |
| 1 | `01-pokerskill-analysis.md` | Avant de toucher à `data/`. Explique d'où viennent les tables et ce qui est fiable dedans. |
| 2 | `02-architecture-v2.md` | Avant d'écrire du code. Schéma d'état, API CLI, cascade de gates. |
| 3 | `03-multiway-generalization.md` | Avant d'écrire quoi que ce soit dans `ranges/`. Décisif. |
| 4 | `04-current-plugin-audit.md` | Avant de refondre les SKILL.md. Contient la mesure de tokens de la v1. |
| 5 | `05-sources.md` | Références et attributions. |

## Contenu du paquet

```
PROMPT.md                    brief de démarrage
references/                  analyse, architecture, audit
data/                        tables ATT/DEF et classification, en YAML
current-plugin/              les 11 skills de la v1, tels qu'installés
```

## Statut des données de `data/`

Les fichiers YAML sont une **réécriture structurée** des tables publiées en annexe E
du papier PokerSkill. Elles n'ont pas été extraites du code compilé (voir
`01-pokerskill-analysis.md`, §Portabilité).

Elles sont **calibrées pour du heads-up 200bb**. Ne les applique pas telles quelles
en multiway sans le facteur d'ajustement décrit dans `03-multiway-generalization.md`.
Chaque fichier porte un champ `calibration:` qui le rappelle.
