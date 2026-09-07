"""Bootstrap partagé : rend `pokercoach` importable sans installation pip.

Copie identique dans le dossier ``scripts/`` de chaque skill du plugin
poker-coach qui a besoin du moteur (source canonique : ce fichier, dans la
skill ``engine`` -- resynchronisé ailleurs par
``scripts/sync_engine_bootstrap.py`` à la racine du repo ; lancer ce script
en mode ``--check`` en CI pour détecter une copie désynchronisée).

Nécessaire parce que claude.ai déploie chaque skill comme un dossier
isolé (``/mnt/skills/plugins/<plugin>:<skill>/``), sans la racine du repo ni
un ``pip install -e .`` qui rendrait `pokercoach` importable -- alors qu'en
développement, ou sous Claude Code (repo complet, `pip install -e .` fait),
``import pokercoach`` marche déjà tout seul.

Stratégie, dans l'ordre, la première qui marche gagne :
1. `pokercoach` déjà importable (dev, Claude Code après `pip install -e .`,
   ou ce fichier lui-même situé dans la skill `engine`) -> rien à faire.
2. Repo source complet à proximité : un ancêtre de ce fichier contient
   directement `skills/engine/pokercoach/`.
3. Skills sœurs (déploiement claude.ai) : le dossier de CETTE skill
   s'appelle `<plugin>:<ce-skill>` -- chercher la skill sœur `<plugin>:engine`
   au même niveau, qui contient `pokercoach/` à sa racine.
4. Repli générique : remonter les ancêtres de ce fichier et regarder, à
   chaque niveau, tous les dossiers frères pour un `pokercoach/__init__.py`
   -- couvre tout layout de déploiement pas anticipé ci-dessus.

Lève RuntimeError avec un diagnostic actionnable si aucune stratégie ne
trouve l'engine, plutôt que de laisser un `import pokercoach` échouer plus
loin avec un ModuleNotFoundError sans contexte.
"""
from __future__ import annotations

import sys
from pathlib import Path

_MAX_ANCESTOR_LEVELS = 6


def _has_pokercoach(directory: Path) -> bool:
    return (directory / "pokercoach" / "__init__.py").is_file()


def _iterdir_safe(directory: Path) -> list[Path]:
    try:
        return [p for p in directory.iterdir() if p.is_dir()]
    except OSError:
        return []


def _candidate_dirs(start: Path) -> list[Path]:
    """Dossiers susceptibles de contenir `pokercoach/` à leur racine,
    du plus probable au moins probable, sans doublon."""
    seen: set[Path] = set()
    candidates: list[Path] = []

    def add(directory: Path) -> None:
        if directory not in seen:
            seen.add(directory)
            candidates.append(directory)

    here = start.resolve()
    ancestors = [here, *here.parents][:_MAX_ANCESTOR_LEVELS]
    for ancestor in ancestors:
        add(ancestor / "skills" / "engine")  # 2. repo source complet
        if ancestor.parent != ancestor:
            for sibling in _iterdir_safe(ancestor.parent):  # 3./4. dossiers frères
                add(sibling)
    return candidates


def ensure_pokercoach_on_path() -> Path:
    """Rend `import pokercoach` possible ; retourne le dossier engine utilisé
    (celui qui contient `pokercoach/` et `data/` comme frères)."""
    try:
        import pokercoach

        return Path(pokercoach.__file__).resolve().parent.parent
    except ImportError:
        pass

    for candidate in _candidate_dirs(Path(__file__).parent):
        if _has_pokercoach(candidate):
            sys.path.insert(0, str(candidate))
            return candidate

    raise RuntimeError(
        "impossible de localiser le package `pokercoach` (ni installé via pip, "
        "ni trouvé comme skill sœur `*:engine`, ni sous skills/engine/ d'un repo "
        "complet) -- si tu es dans le plugin poker-coach sur claude.ai, vérifie "
        "que la skill `engine` est bien installée à côté de celle-ci ; en "
        "développement, lance `pip install -e .` depuis la racine du repo."
    )


if __name__ == "__main__":
    print(ensure_pokercoach_on_path())
