# poker-coach

A Claude Code plugin that acts as a personal No-Limit Texas Hold'em coach for
one player — Winamax cash game, one table at a time, heads-up to 8-max.
Coaching, hand review, and simulated sessions only: **it never plays or
advises during a live hand in progress.**

The guiding principle:

> The engine calculates, the coach teaches.

Everything deterministic — pot, odds, MDF, hand classification, board
texture, the ATT/DEF aggression/defense budget, equity, ranges — moves out of
the LLM's reasoning and into a scripted Python engine with structured
input/output (the `pokercoach` package, CLI entry point `pc`). The LLM is
left with grey-zone judgment and pedagogy: the 11 skills in `skills/` are
thin wrappers around `pc`.

## Status

The full staged plan in [`docs/brief/PROMPT.md`](docs/brief/PROMPT.md) §7 is
implemented:

| Step | | |
|---|---|---|
| 1 | Engine skeleton — canonical state schema, `pc state` (pot, SPR, effective stack, pot odds, MDF, positions, who's to act) | ✅ |
| 2 | Deterministic classification — `pc hand`: the 23 hand classes, board texture (`pc texture`), outs, blockers | ✅ |
| 3 | ATT/DEF budget — `pc budget`: weighted pressure (`pc line`), texture/pot-type modifiers, multiway adjustment, exploit gate (G4) | ✅ |
| 4 | Equity — `pc equity`: exact two-card hands, `@xx%` weighting, exhaustive enumeration or Monte Carlo, memoized | ✅ |
| 5 | Gate cascade — `pc brief`: one call, G0–G5, verdict + verbosity | ✅ |
| 6 | Parameterized ranges — `ranges/table.py`: HU → 8-max via `(n_behind, ip_postflop)`, RFI + derived scenarios (`pc narrow` for mechanical narrowing) | ✅ |
| 7 | Skill rewrite — all 11 `SKILL.md` are thin wrappers around the CLI | ✅ |

**Read before extending or calibrating anything**: the docstring at the top
of each module in `pokercoach/` states its deliberate v2.0 simplifications
(`handclass.py` and `budget.py` especially — two-pair rank buckets, draw
sub-classification, `ranges/table.py`'s `vs_rfi`/`vs_limp`/`squeeze`/`vs_3bet`/
`vs_4bet` formulas). None of it is exact solver output; all of it is
documented as an approximation, consistent with the brief's own "honnêteté
sur la précision" stance (see
[`docs/brief/references/03-multiway-generalization.md`](docs/brief/references/03-multiway-generalization.md)).
The `data/multiway-adjustment.yaml` coefficients are explicitly marked
`status: proposition_non_calibree` — they're isolated in YAML precisely so
they can be tuned after real sessions without touching code.

Also still open, per the brief's own §8 ("ask the user rather than decide
alone") — none of these were decided unilaterally, they're implemented with
a reasonable default and flagged:
- Gate thresholds (`pokercoach/gates.py`'s `UNCERTAINTY_BAND`) and verbosity
  per gate — a quality/cost dial that belongs to the user.
- SB raise-or-fold vs. mixed raise/limp strategy (`data/preflop-rfi.yaml`
  documents both options; v2.0 ships the RFI table without picking one).
- 7/8-max range precision if the parameterized generalization proves too
  imprecise in practice.

## Repo layout

```
pokercoach/            the engine — package `pokercoach`, CLI entry point `pc`
  cli.py                  `pc` subcommands, JSON in/out, errors on stderr
  state.py                canonical hand state: validation + derivations (Layer A)
  cards.py                card parsing (unicode ♠♥♦♣ output, always)
  handeval.py             eval7 wrapper (pure-Python fallback) + nut-check
  handclass.py             the 23 hand classes, draws, outs, blockers
  texture.py               board texture classification
  actionline.py            pot type, role, weighted pressure (pressure-weights.yaml)
  budget.py                ATT/DEF: base, texture penalties, multiway, exploit gate
  equity.py                range vs range equity, enumeration/Monte Carlo, cache
  ranges/table.py           RFI + derived scenarios (vs_rfi, vs_limp, squeeze, ...)
  ranges/narrow.py          mechanical range narrowing by observed action
  gates.py                  the G0-G5 cascade decision logic
  brief.py                  orchestration -> the `pc brief` decision packet
  render.py                 ASCII table rendering (HU -> 8-max, v1 conventions)
  showdown.py               deterministic showdown resolution
  sizing.py                 %pot / raise-to sizing math
  glossary.py               `pc glossary <term>` lookup
data/                   YAML tables the engine reads (ATT/DEF budgets, hand
                        classes, pressure weights, texture modifiers, RFI
                        ranges, multiway adjustments) — see data provenance
                        below
skills/                 the 11 SKILL.md skills, rewritten as thin CLI wrappers
tests/                  pytest suite for pokercoach/, with hand fixtures
docs/brief/             the v2 planning package this rewrite is built from:
                        brief, architecture, analysis, audit, sources
.claude-plugin/          plugin.json — this repo is a single Claude Code plugin
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

pc brief --hand tests/fixtures/hu_flop_cbet.json --villain-archetype fish
pc --help
```

CLI contract: every subcommand prints strict JSON to stdout and nothing else;
errors go to stderr with a non-zero exit code. Equity/hand-strength math runs
on [`eval7`](https://pypi.org/project/eval7/) (C backend) when installed,
with an automatic pure-Python fallback (`handeval.py`) if it isn't — no
network access is required at runtime either way.
