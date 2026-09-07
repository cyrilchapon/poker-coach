"""Tests pour `pc_bootstrap.ensure_pokercoach_on_path` (skills/engine/scripts/),
copié tel quel dans le dossier scripts/ de chaque skill qui invoque `pc` (voir
scripts/sync_engine_bootstrap.py). Exercé ici directement sur les deux layouts
de déploiement réels :

- claude.ai : chaque skill est un dossier isolé, sœur des autres skills du
  même plugin (`<plugin>:<skill>/`) -- aucune racine de repo commune.
- Claude Code / dev : repo source complet, `skills/engine/pokercoach/` visible
  depuis n'importe quel ancêtre.

`import pokercoach` réussit déjà dans ce process de test (pip install -e .
fait pour la suite), donc ces tests exercent `_candidate_dirs`/`_has_pokercoach`
directement plutôt que `ensure_pokercoach_on_path` en entier -- le test
d'intégration en subprocess (sans pokercoach installé) est dans
test_live_session_scripts.py.
"""
import importlib.util
import sys
from pathlib import Path

BOOTSTRAP_PATH = Path(__file__).parent.parent / "skills" / "engine" / "scripts" / "pc_bootstrap.py"


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location("pc_bootstrap_under_test", BOOTSTRAP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pc_bootstrap = _load_bootstrap()


def _make_engine(root: Path) -> Path:
    engine = root / "pokercoach"
    engine.mkdir(parents=True)
    (engine / "__init__.py").write_text("", encoding="utf-8")
    (root / "data").mkdir()
    return root


def test_has_pokercoach_true_only_with_init_file(tmp_path):
    assert not pc_bootstrap._has_pokercoach(tmp_path)
    (tmp_path / "pokercoach").mkdir()
    assert not pc_bootstrap._has_pokercoach(tmp_path)  # dossier vide, pas un package
    (tmp_path / "pokercoach" / "__init__.py").write_text("", encoding="utf-8")
    assert pc_bootstrap._has_pokercoach(tmp_path)


def test_finds_repo_layout(tmp_path):
    # repo/skills/engine/{pokercoach,data}/, script sous repo/skills/other-skill/scripts/
    engine_dir = _make_engine(tmp_path / "skills" / "engine")
    script_dir = tmp_path / "skills" / "other-skill" / "scripts"
    script_dir.mkdir(parents=True)

    candidates = pc_bootstrap._candidate_dirs(script_dir)
    assert engine_dir in candidates
    assert pc_bootstrap._has_pokercoach(engine_dir)


def test_finds_sibling_skill_layout(tmp_path):
    # claude.ai : /.../plugins/poker-coach:engine/{pokercoach,data}/ sœur de
    # /.../plugins/poker-coach:equity-engine/scripts/<script>.
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    engine_dir = _make_engine(plugins_dir / "poker-coach:engine")
    script_dir = plugins_dir / "poker-coach:equity-engine" / "scripts"
    script_dir.mkdir(parents=True)

    candidates = pc_bootstrap._candidate_dirs(script_dir)
    assert engine_dir in candidates


def test_ensure_pokercoach_on_path_inserts_sys_path_for_sibling_layout(tmp_path, monkeypatch):
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    engine_dir = _make_engine(plugins_dir / "poker-coach:engine")
    script_dir = plugins_dir / "poker-coach:equity-engine" / "scripts"
    script_dir.mkdir(parents=True)

    # Force la branche "pas déjà importable" même si le vrai pokercoach est
    # installé dans ce process de test.
    monkeypatch.setitem(sys.modules, "pokercoach", None)
    monkeypatch.setattr(pc_bootstrap, "__file__", str(script_dir / "pc_bootstrap.py"))

    original_sys_path = list(sys.path)
    try:
        found = pc_bootstrap.ensure_pokercoach_on_path()
        assert found == engine_dir
        assert str(engine_dir) in sys.path
    finally:
        sys.path[:] = original_sys_path
