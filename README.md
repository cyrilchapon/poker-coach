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
input/output (the `pokercoach` package, CLI entry point `pc`, packaged in
the `engine` skill — see "Engine packaging" below). The LLM is left with
grey-zone judgment and pedagogy: the 11 coaching skills in `skills/` are
thin wrappers around `pc`.

## Status

The full staged plan in [`skills/engine/docs/brief/PROMPT.md`](skills/engine/docs/brief/PROMPT.md) §7 is
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
[`skills/engine/docs/brief/references/03-multiway-generalization.md`](skills/engine/docs/brief/references/03-multiway-generalization.md)).
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
  matching what "outs" means at the table. **Round 2** (caught on
  re-review of the round-1 fix): the category comparison alone still
  counted cards whose entire contribution is pairing an existing board
  rank hero has no stake in (e.g. on `2♠5♠9♦` with A♠K♠, a 2/5/9 changes
  hero's category exactly as much as it would for any random hand — the
  board pairing for everyone isn't a hero-specific out). Fixed by
  requiring hero's resulting category to beat what a *neutral* hand (two
  cards chosen to avoid any rank/suit interaction with hero, the board, or
  the candidate) would get from the same card — deliberately not the
  simpler "exclude any card whose rank is already on the board" rule,
  which would have also excluded a card completing hero's flush merely
  because its rank happens to coincide with an existing board rank.
  Verified identical on both the eval7 and pure-Python fallback backends.
  **Known remaining gap** (round 2 review, not treated as blocking): the
  neutral-hand comparison correctly filters board-pairing cards when hero
  holds no relevant pair yet, but still over-counts them when hero is
  *already* made — e.g. on `K♥7♣2♦` with K♦Q♠ (hero already has top pair
  Kings), a 7 gives hero `Two Pair` (beats the neutral hand's mere `Pair`
  from that same 7) purely because hero's pre-existing pair mechanically
  carries through the comparison, not because the 7 is a hero-specific
  edge — every other King also reaches `KK77`, and anyone actually
  holding a 7 gets `Trips` and beats hero outright. Comparing against a
  same-*class* reference hand instead of a neutral one would fix this,
  but that's a heavier change than this fix; outs counts on already-made
  hands should be read as an upper bound, not exact, until that's done.
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

## Follow-up PR: the residual, non-blocking findings

PR #1's review (13 threads) flagged two things as genuinely blocking (both
fixed before merge) and left a long tail of real findings explicitly marked
non-blocking — either because the reviewer said so directly, or because
they were architecture/feature-sized work the reviewer recommended
splitting into a separate PR. This section is that PR: every one of those
residual findings, addressed in one pass per the user's request ("adresse
tous les points résiduels relevés mais non bloquants").

**`pc brief` now covers preflop defense, not just RFI.** `ranges/table.py`'s
`vs_rfi`/`vs_limp`/`squeeze`/`vs_3bet`/`vs_4bet` existed and were unit-tested
in isolation but were never called from anywhere — every defending decision
(facing an open/limp/3bet/4bet) fell through to G5 (full analysis, no
tabulated verdict). Two things were needed to wire them in for real:
- **A way to test "is hero's hand in this range?"** — the derived scenarios
  only ever produced a percentage + prose (`"~23.5% (top range du héros,
  largeur approximée)"`), not a parseable range, so there was nothing to
  check hand-membership against. Fixed by adding
  [`skills/engine/data/hand-strength-ranking.yaml`](skills/engine/data/hand-strength-ranking.yaml) — the
  169 starting hand types ranked by raw equity vs. a fully random range,
  computed once via the existing equity engine (Monte Carlo, ~40s,
  deterministic seed) and frozen as static data — and
  `ranges.table.top_pct_range(pct)`, which cumulates COMBOS (not types: 6
  per pair, 4 per suited, 12 per offsuit) down that ranking until it covers
  `pct`% of the 1326 total combos, producing a real `equity.parse_range`-
  compatible string. `vs_rfi`/`vs_limp`/`squeeze`/`vs_3bet`/`vs_4bet` now
  populate `.range` with this instead of prose.
- **Scenario selection logic in `brief.py`'s G1 preflop branch** —
  `_defend_scenario_entry()` picks the closest derived scenario to what
  hero is actually facing from `pot_type` and the action history: `limp` →
  `vs_limp`, a single raise → `vs_rfi` (or `squeeze` if there's already a
  call behind the raiser — a squeeze opportunity for hero, which `pot_type`
  alone can't distinguish from a plain heads-up defend), `three_bet_pot`/
  `squeeze` (facing one) → `vs_3bet` (no dedicated "vs a squeeze" formula
  exists, so this is a documented approximation), `four_bet_pot` →
  `vs_4bet`. Also added `pc ranges --hand hand.json --scenario {rfi,vs_rfi,
  vs_limp,squeeze,vs_3bet,vs_4bet} [--seat N] [--opener-seat N]` for a
  standalone lookup independent of any specific hero hand.
  `top_pct_range()` only produces a contiguous top-X% slice by raw
  strength, though — `squeeze`'s real-poker meaning (a polarized value+bluff
  mix, not a strength interval) isn't actually representable this way; the
  scenario's `.range` is honest about being an approximation of that, not a
  real polarized range.

**G2's confidence, and a disagreement flag instead of a silent contradiction.**
G2's budget-exhausted fallback (facing a bet, ATT/DEF ran out) rendered
`confidence: "forced"` — the same certainty as a deterministic G0/G1
lookup — even though it's a tabulated heuristic a genuinely calculated G3
equity CAN contradict (the reviewer's reproduction: this fallback said
`fold` on a spot where equity was 52-64% against a 30% threshold). Fixed in
two parts:
- `gates.g2_budget_decisive`'s facing-a-bet fallback now renders
  `confidence: "strong"`, not `"forced"` — honest about its epistemic
  status without changing verbosity or forcing an extra G3 computation on
  every close (which would defeat the point of the gate cascade). The
  "check" fallback (nothing to call) stays `"forced"`, correctly: without a
  bet to call there's no pot-odds threshold, so G3 can never even run there
  to contradict it.
- When `--depth full` computes G3 anyway (already existing behavior — the
  verdict is never recalculated, only detailed) and it leans the opposite
  way from what already closed the decision, `pc brief` now surfaces
  `out["gate_disagreement"]` (`closing_gate`, `closing_verdict`,
  `g3_verdict`, a human-readable note) instead of leaving the contradiction
  only visible by manually diffing two JSON fields. The closing gate's
  verdict is still never overridden.

**`ranges/narrow.py` gets a bluff-retention floor.** Binary keep/drop
filtering (`action in b.viable_actions`) made villain ranges collapse to
"100% value, 0% bluffs" once accumulated pressure exhausted every weak
class's ATT budget — a 3-barrel river spot the reviewer measured had both
`vs_range_wide` and `vs_range_narrow` narrow down to sets/two-pair only,
producing G3 equity bounds of exactly `[0.0, 0.0]`: not a measurement, an
artefact (verified fixed: same spot now gives real bounds, e.g. `[0.40,
0.48]` on a moderate case, `[0.07, 0.13]` on a much heavier-pressure one —
never `[0.0, 0.0]`). Fixed with `MIN_BLUFF_FLOOR_WEIGHT` (0.08, **not**
calibrated against real data — a deliberately modest, round placeholder):
a combo whose budget is exhausted *by pressure* is now retained at that
floor weight instead of dropped, encoded in the output range string via
the already-supported `combo@xx%` notation so the reduced weight actually
propagates to downstream equity calculations. Combos cut by a *structural*
rule (`bluff_dies_multiway`, `bluff_multi_street_blocked` — "this line
makes no sense", not "the budget ran dry") are carefully excluded from the
floor and stay a hard zero, verified by a dedicated test — otherwise the
fix would have silently walked back those gates' own deliberate rulings.
The other, distinct cause the reviewer identified — the base viability
criterion being too loose at *fresh* budget (a `trash`-classified combo
still has nonzero base ATT, so ~97% of combos survive a flop `call` in one
measurement) — is **not** fixed here: it's a calibration question about
`data/att-def-budgets.yaml`'s base thresholds, not a mechanism gap, and
this project's standing policy is not to retune those numbers without real
session data. Documented in both the module docstring and here so it isn't
lost.

**The outs over-count on already-made hands (round 3 of that fix).** The
round-2 neutral-hand comparison correctly filtered pure board-pairing cards
for hands with no pair yet, but still over-counted them once hero already
holds a made pair-family hand: hero's *pre-existing* pair mechanically
carries through the "beats a neutral hand" comparison even when the card
isn't a hero-specific edge (a 7 on `K♥7♣2♦` gives a `K♦Q♠` hero `KK77`, Two
Pair, which does beat a neutral hand's mere `Pair(7)` — but gives that same
Two Pair to literally any other King holder too, since the improvement
comes entirely from pairing the board's own existing card). An initial
attempt at comparing to a "same class, different kicker" reference hand
turned out to over-correct — it also excluded the *last remaining King*,
even though tripping up on hero's own hole card is a genuinely
hero-specific improvement regardless of kicker. The actual fix is simpler:
once hero already has a made pair, exclude a candidate only if it pairs an
*existing board rank that doesn't touch either of hero's hole cards* —
letting through anything that pairs one of his own cards. Verified against
the reviewer's own worked example: `K♦Q♠`/`K♥7♣2♦` now gives exactly 5 outs
(3 Qs + 2 Ks), matching their manual count precisely; the other three
reference hands from the review (15, 14, 6) are unaffected, since none of
them have a made pair yet at the point of counting.

**Everything else from the review's "noted, not commented inline"
list** — all fixed:
- `state.py`: `validate_and_load` now cross-checks a seat's declared
  `status` against its own action history (a seat that folded/shoved
  somewhere in the record must be `"folded"`/`"allin"`, not left
  `"active"` — this was silently breaking
  `players_active`/`n_defenders`/`effective_stack`/`mdf_individual`), and
  rejects a street-sequence gap (`flop: null` followed by `turn: {...}`).
- `actionline.replay_pressure`: `still_in`/`folded_or_out` used to reset
  every street, forgetting earlier folds — a seat folded preflop kept
  accumulating `faced` pressure for flop/turn/river bets it was no longer
  exposed to. Now tracked cumulatively across the whole replay.
- `brief.py`: `hero_seat` and `to_act` were read inconsistently (preflop
  read `to_act`'s cards, postflop read `hero_seat`'s, pressure always
  `to_act`'s) — `pc brief`/`pc budget` now both require `to_act ==
  hero_seat` up front (a clear error otherwise) and use `hero_seat`
  throughout; the now-provably-dead `hero_is_allin` branch in
  `g0_forced()`'s call site is kept but pinned to `False` with a comment
  explaining why, rather than silently removed.
- `cli.cmd_narrow` passed the *hero's* replayed pressure into `narrow()`
  when `--action` describes a *villain's* action — fixed by adding
  `actionline.most_relevant_villain_seat()` (shared with `pc brief`'s own
  villain-seat selection for G3) and a `--seat` override.
- `state.ARCHETYPES` was missing `"calling_station"`, even though
  `budget.py` and `--villain-archetype` on `pc budget`/`pc brief` already
  treat it as a real archetype — added; `pc narrow --villain-archetype`
  also gained the `choices=` validation the other subcommands already had.
- `equity._range_between`: inverted bounds (`"77-22"`, `"98s-JTs"`) used to
  return an empty combo list with no error — now raises a clear
  `ValueError`.
- `data/preflop-rfi.yaml`: the HU BTN/SB row's comment claimed 11 excluded
  offsuit combos; the range notation (`74o+` fans from 4 up to 6, so it
  excludes both `72o` *and* `73o`) actually excludes 12 — `73o` was
  missing from the documented list. Comment corrected; verified
  programmatically against the full 78-type offsuit set.
- `tests/test_live_session_scripts.py` only ever loaded the session
  scripts via `importlib.spec_from_file_location`, so the suite never
  exercised the invocation `SKILL.md` actually documents (`python3
  skills/live-session/scripts/advance_street.py ...`, a real subprocess,
  which depends on `pokercoach` actually being `pip install -e .`'d) —
  added a subprocess-based test for that exact invocation.
- `budget.py`'s `two_pair` lookup indexed its YAML `priority_matrix`
  positionally (`matrix[0]`...`matrix[5]`) — reordering the YAML would've
  silently changed which row a given board/hand matched. Each row already
  carried a `when: [...]` tag describing its own condition; added
  `_row_by_when()` to look up by that content instead of list position
  (verified: reversing the YAML list gives identical results before/after,
  and breaks the old positional code outright).

Still open:
- 7/8-max range precision if the parameterized generalization proves too
  imprecise in practice (unchanged — no real usage to calibrate against yet).
- `ranges/narrow.py`'s base viability criterion being too loose at fresh
  budget (see above) — a calibration question, needs real session data.
- `data/hand-strength-ranking.yaml`'s ranking is raw equity vs. a fully
  random range — it ignores position, table format, and postflop
  playability (a suited connector can be worth more than its raw equity
  suggests). Fine as the basis for `top_pct_range()`'s approximate slicing,
  not a substitute for real range construction.

## Live-session test report v1: findings and fixes

A quick real-session test surfaced four issues. Two were clear bugs, fixed
and covered by a new regression test each; two were genuine gaps in what
the engine models, documented rather than papered over with an unreviewed
threshold:

- **`pc render` dropped `seat.status`, so a folded seat became invisible
  once play moved to the next street.** `cmd_render`'s `seat_dict()` never
  passed `status` through at all, and a seat's `action` only ever reflects
  the CURRENT street's actions — a seat that folded on the flop has no
  action to show on the turn, making it indistinguishable from a seat that
  simply hasn't acted yet. Fixed: `seat_dict()` now includes `status`, and
  `render()` falls back to `"fold"` for a seat with no action on the street
  being drawn but `status == "folded"`.
- **The GTO glossary had no entry for implied odds or reverse implied
  odds**, despite both terms being used directly by the `decision-factors`
  skill (loaded by gate G5). Added both definitions to `glossary.py` and to
  the term list in `gto-glossary/SKILL.md`.
- **`att-def-budgets.yaml` has no implied-odds term at all** — the DEF
  budget of a draw is only ever the pressure already faced, never what a
  completed draw could still extract from (or lose to) the remaining
  stacks. This is exactly where a DEF-exhausted fold is most likely to be
  too conservative: a draw, multiway, against opponents who pay wide. The
  gate threshold itself is a user-owned cursor (see `gates.py`'s own
  docstring on this) and wasn't changed without real session data to
  calibrate it — but `budget.compute()` now attaches a note to exactly this
  situation (draw + DEF-exhausted fold + 2+ active opponents) so the coach
  surfaces the gap instead of handing back a bare "budget insuffisant".
- **`hand.outs` counts real category-jumping cards, not equity-weighted
  ones — it has no notion of a dead or poisoned out.** On the reported
  spot (an open-ended draw plus a pairing card on a three-flush board,
  multiway) the count included cards that also complete a made hand for an
  opponent's range, or that pair a rank without actually giving the best
  hand. Distinguishing those requires reasoning about the opponents'
  ranges, which is out of scope for a mechanical count over the known
  cards alone — `handclass.py`'s docstring now says so explicitly, so
  `outs` isn't mistaken for an equity-adjusted number. Judging live-outs
  quality stays a G5/`decision-factors` job.

## Live-session test report v2: findings and fixes

A second real-session test (4 hands, `live-session` on claude.ai) surfaced
six more issues, ranked by the report itself from most to least severe:

- **Stacks were never debited mid-hand.** `pc apply`/`advance_street.py`
  never touched `seats[].stack` — only `new_hand.py` reconciles it, at the
  end of a hand. `pc render` read that raw, stale field directly, so it
  kept showing pre-hand stacks (e.g. 100.0bb/100.0bb) through a 46bb pot,
  while `pc state`/`pc brief`'s `effective_stack` (correctly derived via
  `remaining_stack`) disagreed with it. Fixed by making `cmd_render` derive
  the same way instead of debiting the stored field — one source of truth,
  not two mechanisms that have to be kept in sync by hand.
- **No sizing on preflop decisions.** G1 could render `verdict:
  raise_or_call, confidence: strong` on an opening or isolation decision
  with nothing chiffré — sizing had no gate of its own to live in; it isn't
  a grey-zone judgment call, just a formula nobody had wired up yet. Added
  `sizing.preflop_open_to()` (3bb base + 1bb/limper, plus an exploit bump
  vs. calling stations/fish — same cursor status as the codebase's other
  documented factors), wired into `pc brief`'s preflop branch whenever the
  closing verdict includes a raise, and exposed standalone as
  `pc sizing preflop-open-to`.
- **The exploit adjustment never reached `vs_rfi`.** `--villain-archetype`
  was accepted by `pc brief`, correctly drove the G4 exploit flags, but was
  never threaded into the defend-range lookup at all — a Fish (low PFR)
  who raises got treated as a standard-width opener from their position,
  and a raise made *over a limp* (isolation: dead money, an already-
  committed player) was scored identically to a raise into an empty pot.
  Both signal a tighter range than a plain tabulated open. Added
  `ARCHETYPE_AGGRESSOR_FACTOR` and `ISO_OVER_LIMP_FACTOR` to
  `ranges/table.py` (documented cursors, same status as `UNCERTAINTY_BAND`
  in `gates.py`), a new `actionline.is_a_raise_over_a_limp()` to detect the
  isolation case (`pot_type()` alone can't — one raise reads as `"srp"`
  either way), and threaded `villain_archetype` through `vs_rfi`/`squeeze`/
  `vs_3bet`/`vs_4bet` end to end (`brief.py`'s defend-scenario selection,
  and `pc ranges` standalone).
- **`pc_bootstrap.py` had no escape hatch once `scripts/` was copied
  outside its plugin layout** (e.g. to work around read-only skill
  mounts) — none of its ancestor/sibling-search strategies can find
  anything from an unrelated location, and the obvious workaround
  (`PYTHONPATH=.../poker-coach:engine`) is broken by the `:` in the
  directory name being `PATH`'s own separator (it silently becomes *two*
  path entries, neither valid). Added a `POKERCOACH_ENGINE_DIR` environment
  variable, checked first and given a clear error if it doesn't actually
  contain `pokercoach/`; the fallback error message now also calls out the
  `:`-in-`PYTHONPATH` trap and the symlink workaround.
- **Glossary alias gaps.** `pc glossary isolation` failed even though
  `iso-raise` already covered it, and `fold_equity`/`multiway`/
  `equity_realization`/`realisation_equite` were missing outright despite
  being used constantly in session. Added `multiway`, `stab`, `calling
  station`, `fold equity`, and `réalisation d'équité` as new terms, plus an
  `ALIASES` table (`isolation` → `iso-raise`, `equity_realization`/
  `realisation_equite` → `réalisation d'équité`) and snake_case
  normalization (`fold_equity` → `fold equity`) that doesn't touch the
  engine's own underscored identifiers (`n_behind`, `ip_postflop`).
- **Nothing stopped the coach from hallucinating state — the most
  important finding.** The reporting session hand-wrote table renders
  instead of calling `pc render`, and narrated a full turn and river while
  `hand.json` stayed stuck on the flop; the `pc brief` calls that followed
  silently ran on the wrong street. Not an engine bug — a workflow gap the
  engine could still guard against. Three changes: `DerivedState.to_json()`
  (so `pc state`/`pc brief`) and `cmd_render`'s JSON both now carry a
  `board` field (the derived header had `street` but not what's actually on
  it); added `pc assert-state --hand hand.json [--street S] [--board ...]
  [--to-act N]`, a tripwire that fails loudly (non-zero exit) the moment
  the real state disagrees with what's expected, meant to be called before
  announcing a new street or resuming a session; and `live-session/SKILL.md`
  now states the rule explicitly — no hand-written table renders, ever, and
  `advance_street.py` runs before any narration of the street it opens, not
  after.

## Repo layout

```
skills/                 the 12 skills (11 coaching skills + `engine`)
  engine/                 the shared engine skill — see "Engine packaging" below
    pokercoach/             the engine package, CLI entry point `pc`
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
    docs/brief/             the v2 planning package this rewrite is built from:
                            brief, architecture, analysis, audit, sources
    scripts/pc, pc_bootstrap.py   canonical copies (see below)
  <other-skill>/scripts/pc, pc_bootstrap.py   synced copies, see "Engine packaging"
  live-session/scripts/    session-only helpers (advance_street.py, new_hand.py) —
                           deliberately outside pokercoach/, see above
tests/                  pytest suite for pokercoach/, with hand fixtures
scripts/sync_engine_bootstrap.py   (re)syncs scripts/pc + pc_bootstrap.py into
                                    every skill that invokes `pc` — see below
.claude-plugin/          plugin.json + marketplace.json — this repo is a single
                        Claude Code plugin that also serves as its own
                        marketplace (source: "./"), see Installing below
```

## Engine packaging: one repo, two deployment shapes

`pokercoach/`, `data/` and `docs/` live in a single place — the `engine`
skill (`skills/engine/`) — not at the repo root. This matters because the
two surfaces this plugin installs on don't give the same filesystem to a
skill's scripts:

- **Claude Code**: a plugin install is a full checkout of this repo. Once
  `pip install -e .` has been run (see Development below), `pokercoach` is
  importable from anywhere, `pc` is on PATH, and every skill can reach
  `skills/engine/{pokercoach,data,docs}` directly.
- **claude.ai**: each skill is deployed as its *own isolated directory*
  (`/mnt/skills/plugins/<plugin>:<skill>/`) — there is no shared repo root,
  no `pip install`, and nothing outside a skill's own directory is
  guaranteed to exist. A skill that assumed `pokercoach` was globally
  importable (as every skill here did, until this was diagnosed as a bug)
  simply crashes there: `pc` doesn't exist, `import pokercoach` raises
  `ModuleNotFoundError`.

Every other skill carries a tiny, identical bootstrap (`scripts/pc`,
`scripts/pc_bootstrap.py`) instead of its own copy of the engine. At
runtime it locates the real engine — tries a plain `import pokercoach`
first (Claude Code, or dev), then a full repo checkout nearby, then a
sibling skill directory named `<plugin>:engine` (the claude.ai case) — and
only then dispatches into `pokercoach.cli`. `pc paths` (a `pc` subcommand)
resolves the absolute `pokercoach_dir`/`data_dir`/`docs_dir` for whichever
deployment is currently running, for the few places a skill needs to read
a YAML table or a doc directly rather than through a `pc` subcommand.

The bootstrap files are generated, not hand-edited: change them only under
`skills/engine/scripts/`, then run `python3 scripts/sync_engine_bootstrap.py`
from the repo root and commit the result (`--check` mode, run in CI, fails
the build if a copy has drifted).

## Installing

### Claude Code

```
/plugin marketplace add cyrilchapon/poker-skills
/plugin install poker-coach
```

### claude.ai

Customize (sidebar) → Plugins → **+** (Personal plugins) → **Add
marketplace** → point it at `https://github.com/cyrilchapon/poker-skills` →
Browse plugins → Install.

Note: claude.ai, Claude Code, and the API each maintain independent
skill/plugin state — installing here on one surface doesn't install it on
the others. On claude.ai specifically, installing the plugin must bring in
all 12 skills including `engine` — if a skill later reports it can't find
`pokercoach`, check first that `engine` is still installed alongside it
(see "Engine packaging" above, and `skills/engine/SKILL.md`).

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
own headers. Full attribution: [`skills/engine/docs/brief/references/05-sources.md`](skills/engine/docs/brief/references/05-sources.md).

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
