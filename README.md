# poker-coach

A Claude Code plugin that acts as a personal No-Limit Texas Hold'em coach for
one player — Winamax cash game, one table at a time, heads-up to 8-max.
Coaching, hand review, and simulated sessions only: **it never plays or
advises during a live hand in progress.**

v2 is a rewrite in progress. The guiding principle:

> The engine calculates, the coach teaches.

Everything deterministic — pot, odds, MDF, hand classification, board
texture, the ATT/DEF aggression/defense budget, equity — moves out of the
LLM's reasoning and into a scripted Python engine with structured
input/output. The LLM is left with grey-zone judgment and pedagogy.

## Status

Early v2 development, following the staged plan in
[`docs/brief/PROMPT.md`](docs/brief/PROMPT.md) §7:

| Step | | Status |
|---|---|---|
| 1 | Engine skeleton — `pokercoach/` package, canonical state schema, `pc state` (validates and derives pot, SPR, effective stack, pot odds, MDF, who's to act) | ✅ |
| 2 | Deterministic classification — `pc hand`: the 23 hand classes, board texture, outs, blockers | planned |
| 3 | ATT/DEF budget — `pc budget`: weighted pressure, texture/pot-type modifiers, decrementing by history | planned |
| 4 | Fast equity — enumeration / vectorized Monte Carlo, `eval7`/`phevaluator` backend, cache | planned |
| 5 | Gate cascade — `pc brief`: orchestrates all of the above into one call with an early-exit verdict | planned |
| 6 | Parameterized ranges — HU → 8-max via `(n_behind, ip_postflop)`, not a range table per format | planned |
| 7 | Skill rewrite — the 11 `SKILL.md` files become thin wrappers around the CLI | planned |

`skills/` currently holds the **v1 plugin as-is** — the working product this
rewrite starts from. It keeps functioning skill by skill as pieces of it are
replaced by calls into `pokercoach/` (step 7).

## Repo layout

```
pokercoach/           the engine — package `pokercoach`, CLI entry point `pc`
  cli.py                 `pc` subcommands, JSON in/out
  cards.py                card parsing (unicode ♠♥♦♣ output, always)
  state.py                canonical hand state: validation + derivations
data/                  YAML tables the engine reads (ATT/DEF budgets, hand
                       classes, pressure weights, texture modifiers, RFI
                       ranges, multiway adjustments) — see data provenance
                       below
skills/                the 11 SKILL.md skills (currently v1, unmodified)
tests/                 pytest suite for pokercoach/, with hand fixtures
docs/brief/            the v2 planning package this rewrite is built from:
                       brief, architecture, analysis, audit, sources
.claude-plugin/         plugin.json — this repo is a single Claude Code plugin
```

## Data provenance

`data/att-def-budgets.yaml`, `hand-classes.yaml`, `pressure-weights.yaml`
and `texture-modifiers.yaml` are a structured rewrite of the tables published
in Annexes D–E of:

> Boning Li, Baoxiang Wang, Longbo Huang, *PokerSkill: LLMs Can Play
> Expert-Level Poker without Training or Solvers*, arXiv:2605.30094 [cs.AI].
> https://arxiv.org/abs/2605.30094

`data/preflop-rfi.yaml` and `data/multiway-adjustment.yaml` are **not** from
PokerSkill (which is heads-up only, with no opponent model) — they are
regular-strength reference ranges and an uncalibrated first proposal for
multiway/exploit adjustments, respectively. Both are marked as such in their
own headers. Full attribution: [`docs/brief/references/05-sources.md`](docs/brief/references/05-sources.md).

## Development

```bash
pip install -e ".[dev]"
pytest -q

pc state --hand tests/fixtures/hu_flop_cbet.json
```

CLI contract: every subcommand prints strict JSON to stdout and nothing else;
errors go to stderr with a non-zero exit code.
