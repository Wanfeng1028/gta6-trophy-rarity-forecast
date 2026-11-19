"""GTA VI trophy rarity forecaster: honest quantile forecasts of Exophase earn rates.

Design (written in this session, standard library only, offline, deterministic):

Every case gives a history of reads of Exophase's GTA VI PS5 trophy page. A read is a
snapshot: the players tracked and each trophy's earn rate. Between Exophase refreshes the
page is frozen, so the history is a step function; distinct states are the refreshes.

Two regimes, picked by what the history actually shows:

* Flat history (one distinct state, no refresh seen yet, checkpoint within a day of
  release): the page is the frozen launch-night snapshot and the next refresh is coming.
  Early in a launch the tracked base grows several-fold per refresh while most trophies
  gain almost no earners, so rates fall. The prior divides every rate by 5 (trophies
  already at 100% stay there: every new player holds them too) with a 0.75 logit spread
  to cover the refresh landing anywhere from ~2x to ~10x. This is a prior, not a fit:
  it only fires when the history contains no refresh to learn from.
* Trend history (three or more distinct states): fit logit(rate) against
  ln(1 + hours since release) by least squares over the recent window (the last 24
  hours before the checkpoint), read the line at the target, and damp the fitted slope:
  growth early in a launch is steep and saturates, so an undamped straight line read
  4.5 days out overshoots badly. The median blends from persistence toward the trend
  as more refreshes arrive (weight (states - 2) / 3, capped at 1). The spread starts
  from the random-walk base 0.5 * sqrt(horizon in days) and widens with the fit's
  residual, so a trophy whose history wobbles gets a wider band than a steady one.

Story trophies must respect their order (you cannot finish chapter 2 before chapter 1):
the medians of the chapter chain (ids 3, 4, 5, 6, 7, 14, 1) are pooled to be
non-increasing in logit space (pool-adjacent-violators).

Quantiles are median +/- z_tau * spread in logit space, rounded to 4 decimals.
Two runs on the same case write the same bytes: no randomness, no wall-clock use, no
dict-order dependence (trophies are processed in case order, outputs in id order).
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0, 0.674, 1.645]

# Flat-history prior: the next refresh divides rates by about this much.
FLAT_DIVISOR = 5.0
# Flat-history spread, logit units.
FLAT_SPREAD = 0.75
# The dilution prior only applies this soon after release (launch night).
FLAT_WINDOW_HOURS = 24.0
# Spread of a trophy already held by every tracked player.
FULL_SPREAD = 0.15
FULL_MEDIAN = 99.9
# Random-walk spread per square-root day (the persistence baseline's sigma).
BASE_SIGMA = 0.5
# Trend branch: distinct states needed before the fit is trusted at all.
TREND_MIN_STATES = 3
# Spread clamps, logit units.
SPREAD_MIN = 0.6
SPREAD_MAX = 2.0
# The story chain, in play order: chapters 1-4, final mission, 100%, platinum.
STORY_CHAIN = [3, 4, 5, 6, 7, 14, 1]

# Trend-branch tuning (see the local evaluation notes in the repository README):
# fit logit(rate) against ln(1 + hours since release) over a recent window, and damp
# the fitted slope: growth early in a launch is steep and saturates, so a straight
# line read 4.5 days out overshoots. Damping pivots at the window's mean, it does
# not move the fit where the data already is. The window adapts: the last 24 hours
# when they hold enough refreshes, wider when refreshes are sparse (a 24-hour fit on
# one or two refreshes is no fit at all, and the house curve baseline falls back to
# persistence in exactly that case).
PARAMS = {
    "trend_windows": [24.0, 48.0, None],  # widen until enough distinct states
    "trend_min_window_states": 4,
    "slope_damp": 0.7,          # multiply the fitted slope by this (0..1)
    "blend_states": 3.0,        # weight (states - 2) / blend_states, capped at 1
}


def clamp_pct(x):
    return min(99.99, max(0.01, x))


def logit(pct):
    c = clamp_pct(pct)
    return math.log(c / (100.0 - c))


def inv_logit(l):
    return 100.0 / (1.0 + math.exp(-l))


def round4(x):
    """Round to 4 decimals, half up (the same rounding the house baseline uses)."""
    scaled = x * 10000.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000.0
    return int(value) if value == int(value) else value


def parse_time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def least_squares(xs, ys):
    """Least-squares line y = a + b*x; returns (a, b, rms residual)."""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return my, 0.0, 0.0
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    resid = math.sqrt(sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys)) / n)
    return a, b, resid


def distinct_states(history):
    """Collapse consecutive identical reads (same rates and players tracked)."""
    states = []
    prev_key = None
    for read in history:
        key = (tuple(read.get("rates") or []), read.get("players_tracked"))
        if key != prev_key:
            states.append(read)
            prev_key = key
    return states


def quantiles(median, spread):
    lg = logit(median)
    out = []
    for z in Z:
        q = round4(clamp_pct(inv_logit(lg + z * spread)))
        out.append(q)
    # Rounding can only preserve order, but enforce it explicitly.
    for k in range(1, len(out)):
        if out[k] < out[k - 1]:
            out[k] = out[k - 1]
    return out


def pool_adjacent_violators(values):
    """Make `values` non-increasing (logit medians of the story chain) in place."""
    pools = [[v] for v in values]
    i = 0
    while i < len(pools) - 1:
        if sum(pools[i]) / len(pools[i]) < sum(pools[i + 1]) / len(pools[i + 1]):
            pools[i] = pools[i] + pools[i + 1]
            del pools[i + 1]
            if i > 0:
                i -= 1
        else:
            i += 1
    out = []
    for pool in pools:
        out.extend([sum(pool) / len(pool)] * len(pool))
    return out


def forecast_trophy(i, trophy, states, hours, target_x, horizon_days, flat, params):
    """Return (median, spread) for trophy index i.

    `hours` are hours since release per distinct state; `target_x` is
    ln(1 + hours to the target). `flat` selects the dilution prior branch.
    """
    rates = []
    for read in states:
        rs = read.get("rates") or []
        rates.append(rs[i] if i < len(rs) else None)
    known = [(h, r) for h, r in zip(hours, rates) if r is not None]
    last_rate = known[-1][1] if known else None
    if last_rate is None:
        return 1.0, 1.5
    if last_rate >= 99.99:
        return FULL_MEDIAN, FULL_SPREAD
    if last_rate <= 0.01:
        return 0.05, 1.5

    if flat:
        return max(last_rate / FLAT_DIVISOR, 0.01), FLAT_SPREAD

    # Trend branch. Window: the recent states, widened when refreshes are sparse, so
    # a fit is never run on one or two points. The fit is in logit(rate) against
    # ln(1 + hours since release).
    last_h = known[-1][0]
    pts = []
    resid = 0.0
    for window in params["trend_windows"]:
        cand = []
        for h, r in known:
            if window is not None and last_h - h > window:
                continue
            if 0.01 < r < 99.99:
                cand.append((math.log1p(max(h, 0.0)), logit(r)))
        if len(cand) >= params["trend_min_window_states"]:
            pts = cand
            break
        pts = cand  # keep the widest so far; fall back to it below if needed
    if len(pts) < TREND_MIN_STATES:
        # Too little movement to fit: stay near persistence with a wide spread.
        return last_rate, max(FLAT_SPREAD, BASE_SIGMA * math.sqrt(horizon_days))

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    a, b, resid = least_squares(xs, ys)
    # Damp the slope around the window mean: saturating growth must not be read
    # as a straight line to the target.
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    damp = params["slope_damp"]
    trend_logit = my + b * damp * (target_x - mx)
    trend_rate = clamp_pct(inv_logit(trend_logit))

    w = min(1.0, (len(pts) - 2) / params["blend_states"])
    median_logit = (1.0 - w) * logit(last_rate) + w * logit(trend_rate)
    base = BASE_SIGMA * math.sqrt(horizon_days)
    spread = math.sqrt(base * base + resid * resid)
    spread = min(max(spread, SPREAD_MIN), SPREAD_MAX)
    return inv_logit(median_logit), spread


def forecast_case(case, name, params=None):
    if params is None:
        params = PARAMS
    if case.get("levels") != LEVELS:
        raise ValueError(f"{name} asks for levels {case.get('levels')}, not {LEVELS}")
    history = case.get("history") or []
    if not history:
        raise ValueError(f"{name} has no history")
    trophies = case["trophies"]
    game = case.get("game") or {}
    release = None
    rel = game.get("release_date")
    if rel:
        try:
            release = datetime.fromisoformat(rel + "T00:00:00+00:00")
        except ValueError:
            release = None
    if release is None:
        release = parse_time(history[0]["at"])
    target = parse_time(case["target"])
    horizon_days = case["horizon_minutes"] / 1440.0

    states = distinct_states(history)
    hours = []
    for read in states:
        hours.append((parse_time(read["at"]) - release).total_seconds() / 3600.0)
    target_hours = (target - release).total_seconds() / 3600.0
    target_x = math.log1p(max(target_hours, 0.0))

    checkpoint = parse_time(case["at"])
    flat = len(states) == 1 and (checkpoint - release).total_seconds() / 3600.0 <= FLAT_WINDOW_HOURS

    medians = {}
    spreads = {}
    for i, trophy in enumerate(trophies):
        med, spr = forecast_trophy(i, trophy, states, hours, target_x, horizon_days, flat, params)
        medians[trophy["id"]] = med
        spreads[trophy["id"]] = spr

    # Story order: later chapters cannot be more common than earlier ones.
    chain = [tid for tid in STORY_CHAIN if tid in medians]
    if len(chain) > 1:
        pooled = pool_adjacent_violators([logit(medians[tid]) for tid in chain])
        for tid, lg in zip(chain, pooled):
            medians[tid] = inv_logit(lg)

    rows = []
    for trophy in trophies:
        tid = trophy["id"]
        rows.append({"id": tid, "q": quantiles(medians[tid], spreads[tid])})
    return {"trophies": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
