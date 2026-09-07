---
name: engine
description: Le moteur partagé du plugin poker-coach — package `pokercoach`, tables `data/*.yaml`, doc `docs/brief/`. Skill interne : les 11 autres skills l'utilisent automatiquement via `scripts/pc` (copié dans leur propre dossier), tu n'as normalement pas besoin de lire ceci directement. À consulter seulement si une autre skill échoue à invoquer `pc` (erreur "impossible de localiser pokercoach"), ou si on te demande d'expliquer/diagnostiquer l'installation du plugin.
---

# Engine (skill interne, partagée)

## Pourquoi cette skill existe

Sur claude.ai, chaque skill d'un plugin est déployée comme un dossier
isolé (`/mnt/skills/plugins/<plugin>:<skill>/`) — rien qui vit à la racine
du repo (le package `pokercoach/`, `data/`, `docs/`) n'est automatiquement
accessible depuis les 11 autres skills. Sous Claude Code, à l'inverse, le
plugin est un checkout complet du repo, et `pokercoach` devient importable
partout après `pip install -e .`.

Cette skill résout les deux cas à la fois : elle est le seul endroit où
`pokercoach/`, `data/` et `docs/` existent réellement (un seul exemplaire,
voir `pyproject.toml`). Chaque autre skill embarque dans son propre
`scripts/` une copie de `pc` et `pc_bootstrap.py` (identiques aux fichiers
de ce dossier — voir `scripts/sync_engine_bootstrap.py` à la racine du
repo) qui *localisent* cette skill au lieu de dupliquer son contenu :

1. `pokercoach` déjà importable (dev, ou Claude Code après `pip install -e .`) → rien à faire.
2. Repo source complet à proximité → trouvé sous `skills/engine/`.
3. Sur claude.ai : cette skill est une sœur des autres (`<plugin>:engine`,
   au même niveau que `<plugin>:equity-engine`, etc.) → trouvée par son nom.
4. Repli générique : recherche parmi tous les dossiers frères des ancêtres
   du script appelant.

## Ce que les autres skills utilisent

- `scripts/pc` — CLI complet (`pc state`, `pc hand`, `pc brief`, ... voir
  `pokercoach/cli.py` pour la liste). Invoqué `python3 scripts/pc <sous-commande> ...`
  depuis le dossier de N'IMPORTE QUELLE skill (pas seulement celle-ci).
- `pc paths` — retourne les chemins absolus resolus de `pokercoach/`,
  `data/` et `docs/` pour CE déploiement (utile quand une skill doit lire un
  fichier `data/*.yaml` ou `docs/...` directement plutôt que via une
  sous-commande `pc`).
- Import direct (`from pokercoach.state import ...`, etc.) pour les scripts
  qui vont plus loin que le CLI (ex. `live-session/scripts/new_hand.py`,
  `range-builder/scripts/hand_rank.py`) — toujours précédé de
  `pc_bootstrap.ensure_pokercoach_on_path()`.

## Si une skill échoue à invoquer `pc`

L'erreur explicite ("impossible de localiser le package `pokercoach`...")
vient de `pc_bootstrap.py`. Vérifier dans l'ordre :

1. Cette skill (`engine`) est-elle bien installée dans le même plugin ? Sur
   claude.ai, une skill peut en théorie être désinstallée indépendamment des
   autres (cf. README, "Installing" — attention, chaque surface a son
   propre état d'installation).
2. En dev / Claude Code : `pip install -e ".[dev]"` a-t-il été fait depuis
   la racine du repo ?
3. `python3 scripts/sync_engine_bootstrap.py --check` (racine du repo) —
   confirme que la copie de `pc`/`pc_bootstrap.py` dans la skill en échec
   n'a pas divergé de celle-ci.

## Maintenance (pour qui modifie le plugin, pas pour une session de coaching)

Ne jamais éditer `pc`/`pc_bootstrap.py` dans une autre skill que celle-ci —
ce sont des copies générées. Éditer ici, puis lancer
`python3 scripts/sync_engine_bootstrap.py` à la racine du repo (une CI le
vérifie en mode `--check`).
