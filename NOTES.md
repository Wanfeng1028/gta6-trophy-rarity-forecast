# Design and local evaluation notes

## The entry

`main.py` (Python 3.13, standard library only) reads every `*.in` case in
`$MAKEFUN_INPUT_DIR` (default `/input`) and writes `/output/<id>.out`:
`{"trophies": [{"id": n, "q": [q05, q25, q50, q75, q95]}, ...]}`. No network, no
randomness, no wall-clock use; two runs on the same case write identical bytes
(verified). Runs in ~0.06 s on the practice cases, far under the 8 s cap.

## Design

Exophase refreshes a game's counts on its own schedule, hours apart, so a case's
history is a step function. The program collapses it to distinct states (the
refreshes) and picks one of two regimes by what the history shows:

1. **Flat history** (one distinct state, checkpoint within 24 h of release): the page
   is the frozen launch-night snapshot and the next refresh is coming. Early in a
   launch the tracked base grows several-fold per refresh while most trophies gain
   almost no earners, so rates fall. Prior: divide every rate by 5 (trophies already
   at 100% stay there), spread 0.75 logit units.
2. **Trend history** (three or more distinct states): least-squares fit of
   logit(rate) on ln(1 + hours since release) over a recent window — 24 h when it
   holds at least 4 refreshes, widened to 48 h, then all history, when refreshes are
   sparse — read at the target, with the slope damped by 0.7 (launch growth is steep
   and saturates; an undamped line read 4.5 days out overshoots). The median blends
   from persistence toward the trend as refreshes accumulate. The spread is the
   random-walk base 0.5 * sqrt(horizon in days) combined with the fit residual.
   Story trophies are pooled to respect their play order (chapter 1 >= chapter 2 >=
   ... >= final mission >= 100% >= platinum).

## Local evaluation (no local grade exists for this competition)

`grade-local` refuses this kit: "its scorer and reference data are not published
in the kit, so it is graded on the server only" (RULES.txt says the same). Instead
the pinball loss was re-implemented exactly as RULES.txt specifies (logit scale,
clamp [0.01, 99.99], levels 0.05/0.25/0.5/0.75/0.95) and run locally.

Practice answers are not in the kit, so they were reconstructed from the facts the
competition publishes: launch night 638 players / 943 trophies earned, the 04:30Z
refresh 3,868 players / 4,276 trophies earned, every rate but the 100% one falling.
Old counts follow from the printed rates (they sum to exactly 943); the refresh's
3,230 new players all hold the 100% trophy, leaving 103 new earners spread over the
other 54 trophies. The reconstruction is validated against the house's own published
practice numbers for the persistence baseline: typical miss 0.677 pp (house: ~0.68),
90% coverage 0.00 (house: ~0), loss 1.40-1.53 across distribution variants (house:
~1.51).

Results on the practice cases (7 answer variants: proportional / top-12 /
high-count / single-trophy / 3 random distributions of the 103 earners):

| forecast | mean loss | worst variant |
|---|---|---|
| persistence baseline | 1.47 | 1.66 |
| this entry | 0.23 | 0.25 |

The final case cannot be validated against real data (its answer does not exist
yet), so the trend branch was also tested on synthetic final cases: a plausible
f00 built from logistic-in-log-time truth under 8 scenarios (base / slow / fast
progression, heavy dilution, stale answering read, power-law growth, sharp
saturation, mid-week dilution dip). Mean loss: this entry 0.264, persistence 0.282,
house curve baseline 0.249. The synthetic suite is the curve baseline's home turf
(its model class), so near-parity there is the honest expectation; the entry's
edges are the dilution prior, the adaptive window (the curve baseline falls back
to persistence when the last 24 h hold too few refreshes), slope damping for
saturation, and the story-chain constraint.

## Revisions

- v1: counts model (separate ln E / ln N fits). Practice 0.21-0.25, but synthetic
  final 0.51-0.65: undamped log-log extrapolation overshoots badly.
- v2: logit fit, recent window, damped slope. Practice unchanged (flat branch),
  synthetic final 0.26-0.29.
- v3 (this commit): adaptive window (24 h -> 48 h -> all), damp 0.7, curve-style
  spread. Practice 0.23, synthetic final mean 0.264 / worst 0.292.
