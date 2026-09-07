# poker-coach v2 — paquet de démarrage

Brief complet pour reprendre le développement du plugin `poker-coach` en v2,
dans Claude Code.

**Point d'entrée : `PROMPT.md`.**

```
PROMPT.md                              le brief de démarrage
references/
  00-lire-en-premier.md                ordre de lecture
  01-pokerskill-analysis.md            analyse du repo + papier PokerSkill
  02-architecture-v2.md                état canonique, API CLI, cascade de gates
  03-multiway-generalization.md        HU -> 8-max : la décision de design clé
  04-current-plugin-audit.md           audit v1 fichier par fichier + tokens
  05-sources.md                        attributions
data/
  hand-classes.yaml                    les 23 classes de main
  att-def-budgets.yaml                 les budgets ATT/DEF (coeur du système)
  pressure-weights.yaml                taille de mise -> pression pondérée
  texture-modifiers.yaml               texture de board + boards spéciaux
  multiway-adjustment.yaml             multiway + gates exploitantes (à calibrer)
  preflop-rfi.yaml                     ranges paramétrées HU -> 8-max
current-plugin/                        les 11 skills de la v1, tels qu'installés
```

## Démarrage suggéré dans Claude Code

```
Lis PROMPT.md puis references/00-lire-en-premier.md, et suis l'ordre de lecture
indiqué. Ne commence à coder qu'après avoir lu 01, 02 et 03.
Puis attaque l'étape 1 du §7 de PROMPT.md.
```
