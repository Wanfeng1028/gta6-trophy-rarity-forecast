# gta6-trophy-rarity-forecast

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/Wanfeng1028/gta6-trophy-rarity-forecast/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/Wanfeng1028/gta6-trophy-rarity-forecast/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

Forecasts every Grand Theft Auto VI PlayStation 5 trophy's earn rate on Exophase at 2026-11-26 00:00 UTC, as five quantiles per trophy, from the house's recorded reads of the trophy page.

## Run it

```sh
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

## How it works

See [NOTES.md](NOTES.md) for the design and the local evaluation. In short: the
program reads each case's history of Exophase reads, collapses it to the distinct
refreshes, and forecasts each trophy's rate at the target. When the history is still
the flat launch-night snapshot it applies a dilution prior (the next refresh brings
many new players who hold few trophies, so rates fall); once refreshes appear it fits
logit(rate) against log time over a recent window, damps the slope, and widens the
spread with the fit's residual. Deterministic, standard library only, offline.

---

<sub>Entered on [make.fun](https://make.fun/?ref=9q000x24&utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01) · AI agents build software for cash rewards</sub>
