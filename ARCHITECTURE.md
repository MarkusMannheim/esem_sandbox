# How the model fits together

The model is a loop over one year at a time. Each year is dispatched hour by hour, contracts settle on those prices, investors rebuild their view of the future and decide what to build, and plant retires or arrives. This page says what each part of the code does and in what order to read it.

## Where to start

`core/dispatch.py` runs one year, hour by hour, and everything else consumes its output. `core/contracts.py` says what a swap and a cap are and how they settle on those hours. `core/forward.py` builds what investors think the next 4, 8 and 12 years look like. `core/investment.py` decides whether anything gets built. `core/simulate.py` runs those four in order, 20 times. Read them in that order; each needs only the one before it.

The rest is an input to those (`config.py`, `core/weather.py`), a market they trade in (`core/clearing.py`, `core/agents.py`, `core/crossing.py`), a mechanism switched on top (`core/esem.py`, `core/scheme.py`), or a way of looking at the result (`core/report.py`, `plots.py`, `cli.py`).

## What each piece does

| Piece | What it does |
|---|---|
| `config.py` | Loads the settings and the packaged tables. An unknown key raises an error rather than leaving a default in place |
| `core/weather.py` | Generates five synthetic shape-years from one seed, always 8,760 hours |
| `core/dispatch.py` | Stacks the offers and prices each hour: a coal unit's must-run band below its running cost, the demand-response ladder, administered pricing, hydro against its annual budget, storage scheduled on quantities |
| `core/windows.py` | Finds the worst contiguous run of days in a year |
| `core/report.py` | Blocks, quarters, duration curves, revenue per unit, the calibration check |
| `core/contracts.py` | Swaps and caps, settled over the full hourly series |
| `core/agents.py` | Six archetypes, separated by risk aversion and exposure |
| `core/clearing.py` | What each contract lane clears at, what it costs a peaker to stand ready, the one measure of caution the whole model shares, and the market where retailers and producers trade |
| `core/crossing.py` | The option where buyers and sellers find a price between them instead of both accepting the reference price |
| `core/forward.py` | 45 possible futures, priced at 4, 8 and 12 years out; what each technology would earn in each; and how much plant investors assume everyone else builds |
| `core/investment.py` | How much of a project is still exposed to the spot price, what it has to earn to be built, how fast the fleet may change, and when a plant closes |
| `core/esem.py` | The reliability scheme: how much to buy, what it is worth, when it is committed, who pays |
| `core/scheme.py` | A state scheme: a milestone a year, a ceiling, a budget, and why a milestone was missed. It buys nameplate megawatts where the reliability lane buys delivered firm ones, and the two are not addable |
| `core/simulate.py` | The year loop, and the order its eight steps run in |
| `plots.py`, `cli.py` | The dashboard, the worst-week and price-duration charts, and three commands |
| `tools/` | The scripts that produce the numbers and charts in the documents |

## What a year looks like

1. Plant decided years ago and finished this year enters service.
2. The year is dispatched and priced.
3. Contracts written earlier settle against that price.
4. The book ages: what has finished delivering leaves it.
5. The forward view is rebuilt, and the guess at what everyone else builds is revised once.
6. The administrator offers its position back, then the bilateral market covers the rest.
7. The scheme's auction runs, awarding at final investment decision.
8. Exit notices are given, and then entry is decided.

The order matters in three places, and `core/simulate.py` says why: the administrator sells before the bilateral market, so a retailer does not hedge one load twice; exit comes before entry, so an entrant prices a market without the plant everyone knows is leaving; and a contract struck in one year first settles in the next.

## The forward view

`core/forward.py` is where most of the computing goes. Every year it enumerates 45 possible futures, five weather patterns by three growth paths by three peak severities, and dispatches each of them in full at 4, 8 and 12 years ahead. That is 135 dispatched years behind every investment decision, and at least 2,700 over a 20-year run: one view a year, a second in any year the scheme awards plant, and under the sequential investment rule one more after each producer that builds, which is why that rule costs about twice the run time.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/forward_view_dark.png">
  <img alt="45 futures priced at three distances, and what they pay a peaker" src="outputs/canonical/forward_view.png">
</picture>

Because the futures are enumerated rather than sampled, the same settings always give the same picture and no seed enters here. What comes out is a distribution, and the investment rule works on its spread. The odds are fixed at the start and never revised, so no one in the model learns which future they are in; that is deliberate, and [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) says what it costs.

The spread an investor is charged for is the one across the three growth paths. A run keeps its growth path for life and draws the weather and the peak afresh every year, so over a plant's life those two average out; the 45 futures are collapsed to the three paths, each at the mean of its weather and peak cells, before caution is priced. The expectation is the same either way. Everything that reads caution, the hurdle, the lane's bid and the state scheme's bid, reads that one distribution. The investor's own tolerance for the spread then decides most of what it demands.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/hesitancy_dark.png">
  <img alt="How much of the bar a plant must clear is caution rather than cost" src="outputs/canonical/hesitancy.png">
</picture>

The code calls the three distances anchors, a word it also uses for the reference price a contract lane clears at. [GLOSSARY.md](GLOSSARY.md) calls the distances projection years.

## What the model holds to

Everything is per megawatt-year. Rent and fixed cost are on the same basis, so no capacity-factor assumption enters the build decision: a peaker running two per cent of the year and a wind farm running 35 per cent are each tested against their own costs. It is also what lets the forward view leave the entry it assumes open to technology rather than naming one in advance, because a test that divided a fixed cost by a duty cycle would have to know the duty cycle first, and so would be pinned to whichever technology someone had measured.

Risk is priced once. One function decides how cautious a firm is, and both the cap lane and the investment rule go through it. A firm that priced the same tail one way when writing insurance and another when building the plant that covers it could arbitrage the difference between them.

Nothing forecasts. The bilateral market's contract prices are weighted averages of prices that have already happened, a scheme award's strike is the forward view's expectation for its delivery years, and the forward view is a list of possible futures at fixed odds. That is the whole mechanism behind boom and bust: scarcity lifts prices, investors extrapolate, everyone builds, and the plant arrives together into a market that no longer needs it.

## What the model does not do

[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) says what the model leaves out, what it gets wrong, and which of its results are easy to misread.
