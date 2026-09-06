# How it fits together

The model is meant to be understood in an hour. This is the map: what each piece
does, what it hands to the next one, and where to start reading.

## Start here

Read in this order and each piece only needs the one before it.

1. `core/dispatch.py` — one year, hour by hour. Everything else consumes its output.
2. `core/contracts.py` — what a swap and a cap are, and how they settle.
3. `core/forward.py` — what investors think the next twelve years look like.
4. `core/investment.py` — the four lines that decide whether anything gets built.
5. `core/simulate.py` — the loop that runs those four, twenty times.

The rest is either an input to those (`config.py`, `core/weather.py`), a market they
transact in (`core/clearing.py`, `core/agents.py`), a mechanism switched on top
(`core/esem.py`, `core/scheme.py`), or a way of looking at the result (`core/report.py`,
`plots.py`, `cli.py`).

## What each piece does

| Piece | What it is |
|---|---|
| `config.py` | The settings and the packaged tables. Strict: an unknown key raises rather than leaving a default in place |
| `core/weather.py` | Five synthetic shape-years from one seed, always 8,760 hours |
| `core/dispatch.py` | The merit order, the scarcity ladder, administered pricing, hydro against its budget, and storage shaving quantities |
| `core/windows.py` | Finds the worst contiguous run of days, rather than being told where it is |
| `core/report.py` | Blocks, quarters, duration curves, per-unit revenue, the calibration check |
| `core/contracts.py` | Swaps and caps, settled over the full hourly series and never a sample |
| `core/agents.py` | Six archetypes; what separates them is risk aversion and exposure, not size |
| `core/clearing.py` | Lane anchors, the cap's cost basis, the CARA coefficient every part of the model shares, and the bilateral market |
| `core/crossing.py` | The extension where the two sides have to find a price instead of accepting an anchor |
| `core/forward.py` | Forty-five futures, three anchors, the rent each technology would earn, and the free-entry belief |
| `core/investment.py` | Exposure, the certainty-equivalent hurdle, pacing, and exit |
| `core/esem.py` | The reliability scheme: how much to buy, what it is worth, when it is committed, who pays |
| `core/scheme.py` | A state scheme: a milestone a year, a ceiling, a budget, and why it was missed. Note the units: it buys NAMEPLATE megawatts where the reliability lane buys DELIVERED FIRM ones, and the two are not addable |
| `core/simulate.py` | The tick loop, and the order the eight steps run in |
| `plots.py`, `cli.py` | The dashboard, the worst-week chart, and three commands |

## What a year looks like

1. Plant decided years ago and finished this year enters service.
2. The year is dispatched and priced.
3. Contracts written earlier settle against that price.
4. The book ages: what has finished delivering leaves it.
5. The forward view is rebuilt and the free-entry belief takes one step.
6. The administrator offers its position back, then the bilateral market covers the rest.
7. The scheme's auction runs, awarding at final investment decision.
8. Exit notices are given, and then entry is decided.

Three of those orderings carry weight, and `core/simulate.py` says which and why.

## The three ideas worth carrying away

**Everything is per megawatt-year.** Rent and fixed cost are on the same basis, so no
capacity-factor assumption enters the build decision. A peaker running two per cent of
the year and a wind farm running thirty-five are each tested against their own costs.
It is also what lets the forward view leave the entry it assumes open to technology
rather than naming one in advance: a test that divided a fixed cost by a duty cycle
would have to know the duty cycle first, and so would end up pinned to whichever
technology somebody had measured.

**Risk is priced once.** One function builds every CARA coefficient, and both the cap
lane and the investment rule go through it. A firm that priced the same tail one way
when writing insurance and another when building the plant that covers it could
arbitrage the difference between them.

**Nothing forecasts.** Anchors are weighted averages of prices that have already
happened and the forward view is an enumeration of futures at fixed probabilities.
That is the whole mechanism behind boom and bust: scarcity lifts prices, investors
extrapolate, everybody builds, and the plant arrives together into a market that no
longer needs it.

## What it does not do

[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md), with measurements rather than
assertions.
