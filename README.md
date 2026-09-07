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

Decisions from §8 that were pending have since been made with the user and
implemented:
- **G3 uncertainty band**: kept at ±4 points (`gates.py`'s `UNCERTAINTY_BAND
  = 0.04`) — the default was already right.
- **Verbosity**: minimal everywhere except G3 (shows the deciding number)
  and G5 (full analysis) — also already the default. On top of that,
  `pc brief --depth full` (or `force_full=True` from Python) now escalates
  to full detail **on demand**, on any gate, without ever changing the
  verdict itself: same `gate`/`verdict`/`confidence`, but the equity bounds
  and the narrowed villain ranges get computed and attached regardless, and
  `verbosity` is forced to `"full"`. This is what a live-session coach calls
  when the user asks "on peut voir les ranges exactes ?" after a G0–G2/G4
  verdict.
- **G3 bounds are real** now, not two fixed generic ranges: `pc brief`
  identifies the most relevant villain seat (the last aggressor when the
  hero is defending) and replays their actual in-hand actions street by
  street through `ranges.narrow` — the same mechanism `pc narrow` exposes
  standalone — starting from a wide and a narrow seed range. The seeds
  themselves remain a documented approximation (not yet derived from the
  villain's position/archetype); the narrowing through their real actions
  is no longer approximated.
- **MDF collective vs. individual**: `pc state`/`pc brief` now expose both
  `mdf_collective` (the heads-up-style `pot/(pot+bet)` figure, read as the
  *combined* obligation across every simultaneous defender) and
  `mdf_individual` (`1 - (1 - mdf_collective) ** (1/n_defenders)` — what each
  individual defender may fold, always ≤ what the collective figure alone
  would suggest). `n_defenders` (also exposed) is the count of still-active
  seats facing the current bet without having matched it yet. Applying the
  heads-up figure uncorrected in multiway over-defends — exactly one of the
  user's documented leaks.
- **SB strategy: mixed raise/limp** (chosen over raise-or-fold). Implemented
  as two disjoint buckets rather than a per-hand mixed frequency — simpler
  to code and to teach while keeping the three-way raise/limp/fold structure
  a pure raise-or-fold range can't express. `data/preflop-rfi.yaml`'s SB row
  now carries `raise_range`/`limp_range`; `pc brief` returns `verdict:
  "raise"` / `"limp"` / `"fold"` accordingly at G1.

Fixed along the way (found while wiring the above, not previously caught by
any test): `equity.parse_range`'s `XYs+`/`XYo+` handling (`_plus_connector`)
silently returned a single combo instead of fanning the low card up to the
high card — `"ATs+"` produced just `AT` instead of `AT,AJ,AQ,AK`. This
affected every `+`-suffixed two-card token across `data/preflop-rfi.yaml`
and the G3 seed ranges. Also, `actionline.role()` classified **any**
player's first preflop decision as `"defender"` (the BB's forced post
inflates `to_call` before anyone has voluntarily acted) instead of
`"aggressor"/"probe"` — this silently starved `pc brief`'s G1 range lookup
for realistic opening decisions at every position, not just the SB. Both
are covered by regression tests now (`tests/test_equity.py`,
`tests/test_actionline.py`, `tests/test_brief.py`).

**Played an actual end-to-end session** (6-max, mode 3, real `pc`/script
calls the way `live-session` would make them — not just `pytest`) to check
this all genuinely works together, per the user's request. Found and fixed
three more real bugs this way, none of them caught by the 116 tests passing
at the time — the gap in every case was a code path no test happened to
exercise, not a subtle edge case:
- `budget.compute()` always offered `call`/`fold` regardless of whether
  there was an actual bet to call — a weak hand facing a free check got
  told to "call" (gated by DEF) instead of "check" (always free), and the
  fallback that logic fed into `pc brief`'s G2 gate could return `"call"`
  as a verdict for a check/bet decision. Fixed by threading a `facing_bet`
  flag through `budget.compute()`, `gates.g2_budget_decisive()` (renamed
  from `g2_budget_exhausted`) and `ranges.narrow.narrow()` — the action
  vocabulary is now genuinely `bet`/`check` when nothing's being faced,
  `raise`/`call`/`fold` when something is.
- `actionline.role()`'s fix from the previous round was incomplete: `pc
  brief`'s G1 gate had been patched locally to stop misreading an opening
  decision as "defending", but `line.role` itself — the field a coach
  would actually narrate from — still said `"defender"`. Fixed at the
  source (`actionline.role()` now defers to the same
  `is_opening_decision()` check), and `brief.py`'s local workaround
  removed now that it's no longer needed.
- `state.derive()`'s `pot_odds`/`mdf_collective` computed to `0.0`/`1.0`
  instead of `None` whenever `to_call == 0` but the pot already had
  chips in it (the guard was "pot + call > 0", true on almost every
  street) — a meaningful-*looking* number for a question that doesn't
  apply ("equity needed for a profitable call" when there's nothing to
  call). That fed a live, visible bug: a made hand with unlimited budget
  and no bet facing it got compared against a fabricated `threshold: 0.0`
  in G3 and came back `verdict: "call_or_raise"`, an answer that doesn't
  even make sense for a check/bet decision. Fixing the root cause exposed
  a real gap in the gate cascade itself, not just the number: with
  `pot_odds` correctly `None`, G3 could no longer fire on that decision,
  and nothing else closed it either — a textbook "you have the near-nuts,
  just bet" spot was falling through to G5 (the most expensive, full-analysis
  tier) instead of a one-line forced verdict. `g2_budget_decisive` now
  also closes the decision early when budget is unambiguously abundant
  (`att_remaining == inf`, not facing a bet), symmetric to how it already
  closed it when budget was exhausted.

All three covered by regression tests (`tests/test_budget.py`,
`tests/test_ranges.py`, `tests/test_actionline.py`, `tests/test_brief.py`),
plus a full hand played start to finish through the real CLI/scripts as a
manual check, in addition to the automated suite.

**Found by automated PR review** (13 review threads total; none caught by
the 124 tests passing at the time). The four ⛔ blocking findings in
`handclass.py`/`actionline.py` — all real logic bugs, not nitpicks:
- `handclass._count_outs` compared raw `evaluate()` scores instead of hand
  *category* — adding any 6th known card to a 5-card known set almost
  always improves the best-5-of-6 slightly (it replaces the weakest
  kicker) even when the hand's category doesn't change, so nearly every
  remaining card counted as an "out" (e.g. 47/47 on a flop). Fixed by
  comparing `handtype(evaluate(...))` category instead — an out is now a
  card that changes hand *category* (pair → two pair, draw → made hand),
  matching what "outs" means at the table.
- `_classify_pair_family` indexed into `matched[0]` without sorting it
  first, so on a board already paired (both hole cards each matching a
  different board rank) the classification depended on the *input order*
  of hero's two hole cards — `["7h","5d"]` and `["5d","7h"]` (the same
  hand) landed in different pair buckets (`second_pair` vs `third_pair`).
  Fixed by sorting `matched` by board-rank position before indexing.
- `_classify_draw`'s flush-draw detection counted board cards toward the
  4-of-a-suit threshold with no floor on hero's own contribution — on a
  board that's already a 4-flush, `has_flush_draw` came back `True` with
  `flush_high=None` purely from the board, wrongly granting hero a
  semi-bluff draw budget when he holds no card of that suit at all (he's
  just "playing the board"). Fixed by requiring `flush_high is not None`.
- `actionline.py` — `is_opening_decision`, `pot_type`, `last_aggressor`
  and `replay_pressure` all tested actions against `("bet", "raise")` /
  `("call", "raise")`, missing `"allin"` (a distinct member of
  `state.ACTIONS`, not a synonym). A shove was invisible everywhere: a
  player facing an all-in shove read as `role: "probe"` instead of
  `"defender"`, and `weighted_pressure_faced` stayed `0.0` despite facing
  a full stack. Fixed by adding `"allin"` to all four checks.

A fifth ⛔ finding — `pc apply` writing an unvalidated `hand.json` straight
to disk — was also fixed: `cmd_apply` now validates legality (check/bet
illegal while facing a bet, call/raise illegal without one) *and* amount
(call/check/fold have exactly one legal amount; bet/raise must clear the
minimum-raise increment and can't exceed the seat's stack; `allin` must
equal the full remaining stack) before touching the filesystem at all, sets
`seats[n].status = "allin"` on an all-in action (previously only `"fold"`
updated status), and writes atomically (temp file + `os.replace`) so a
rejected action never leaves a corrupted or partial file on disk.

Six more ⚠️/💡 findings (correctness and one perf issue, not blocking) were
also fixed:
- `state.effective_stack(seat=...)` ignored its `seat` parameter entirely
  (always returned the table-wide min) — the one call site that passes
  `seat=` (`ranges/table.py`'s stack-bucket lookup for `vs_3bet`/`vs_4bet`)
  was silently using the wrong number. Now returns
  `min(that seat's stack, min of opponents still in the hand)`.
- `brief._narrow_through_history` called `ranges.narrow.narrow()` without
  `pressure_spent`/`pressure_faced`, so every street's narrowing restarted
  from a fresh 0.0/0.0 budget — a villain who'd already barrelled twice got
  filtered as if opening the action cold. `actionline.replay_pressure()`
  gained an `upto_street` bound so the real cumulative pressure at each
  street can be passed through.
- `advance_street.py`'s action-closed check only compared *contributions*
  (`[0.0, 0.0]` for two players is trivially "equal" even if only one of
  them actually checked) — now also requires every active seat to have
  taken at least one voluntary action this street, and refuses to open a
  new street at all when only one seat is still contesting the pot (the
  hand is already over; award the pot instead).
- `new_hand.py`: `table.ante` was carried forward into the next hand's
  config but never actually posted (pot under-counted whenever `ante > 0`);
  `--winner`/`--split` accepted any seat number, including one that had
  folded the previous hand; and a dead `remainder` variable implied
  odd-chip handling that the float-division `share` never produces. Fixed
  all three; `remainder` and its docstring line removed.
- `budget.py`'s `elif texture.suit == "three_flush" and not applied_flush`
  guard could never be `False` (the two branches are already
  mutually-exclusive on `texture.suit`) — dead condition, removed.
  `att_after_penalties`/`def_after_penalties` were computed but missing
  from `to_json()`; now exposed for debugging the penalty order.
- `equity._monte_carlo_equity` rebuilt `itertools.accumulate(weights)`
  inside `rng.choices()` on every one of `iterations` draws — now
  precomputed once and passed as `cum_weights`.

All ten fixes covered by regression tests (`tests/test_handclass.py`,
`tests/test_actionline.py`, `tests/test_cli.py`,
`tests/test_live_session_scripts.py`). Two remaining ⚠️ findings —
`pc brief` not covering preflop *defense* spots, and G2/G3 gate-priority —
are architectural/feature-sized rather than local fixes; see "Still open"
below. One low-priority 💡 suggestion (avoid materializing the full
range×range cartesian product for Monte Carlo) and one YAML-indexing
robustness note (`budget.py`'s positional `matrix[0..5]` lookups) are noted
but not acted on.

**Session/multi-hand tooling** is now built, per the direction agreed with
the user: `pokercoach`'s CLI commands stay unitary and standalone (each one
takes a `hand.json`, does one job, and knows nothing about "a session") so
they stay usable outside `live-session` too — e.g. for one-off hand review.
Session bookkeeping lives instead in two scripts local to that skill
(deliberately outside the core engine — see the docstring at the top of
each):
- [`skills/live-session/scripts/advance_street.py`](skills/live-session/scripts/advance_street.py) —
  opens the next street once the current one's action is closed (rejects
  otherwise), deals the new cards, and sets `to_act` per the postflop
  order (`pokercoach.state.postflop_acting_order_offsets`, added for this).
- [`skills/live-session/scripts/new_hand.py`](skills/live-session/scripts/new_hand.py) —
  rotates the button, carries stacks/archetypes forward by physical seat,
  posts blinds, and refuses outright (rather than silently misbehaving) if
  the hero would bust or if a bust shrinks the table past the next hand's
  expected blind seats (dead-button rules are out of scope).

Still open:
- 7/8-max range precision if the parameterized generalization proves too
  imprecise in practice (unchanged — no real usage to calibrate against yet).
- `pc brief` doesn't cover preflop *defense* (vs an open/limp/3bet/4bet) —
  only RFI (G1) is wired in. `ranges/table.py`'s `vs_rfi`/`vs_limp`/
  `squeeze`/`vs_3bet`/`vs_4bet` entries exist and are tested in isolation
  but aren't called from anywhere: every defending decision falls through
  to G5 (full analysis, no tabulated verdict) instead of using them.
  Flagged by automated PR review; deliberately not fixed inline here —
  wiring five more branches into G1 plus a `pc ranges` subcommand is a
  feature addition, not a local bug fix.
- G2 (the ATT/DEF budget heuristic) can render a `confidence: "forced"`
  verdict (typically a fold on an exhausted DEF budget) that a G3 equity
  calculation, if run, would contradict — the cascade currently lets the
  cheaper heuristic close the decision before the more expensive
  calculation ever runs, with no cross-check between the two. Flagged by
  automated PR review, and by the reviewer's own read it's a gate-ordering
  *architecture* question (does G2's "budget exhausted" fold escalate to
  G3 instead of forcing, or does it force but flag disagreement when G3
  is calculable) — worth its own PR rather than a change bundled in here.

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
  live-session/scripts/    session-only helpers (advance_street.py, new_hand.py) —
                           deliberately outside pokercoach/, see above
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
