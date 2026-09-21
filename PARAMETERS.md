# Parameters

Everything the model can be told to do differently is a number or a word in one file, `src/esem_sandbox/data/settings.toml`, or a row in one of the small tables beside it. This page lists every setting, what it does and what it moves, so a reader can change one thing and know what to look at.

## Three ways to change a setting

From the command line, `--set` changes one setting for one run and can be repeated. It applies after a scenario file, and a misspelt name stops the run rather than leaving the default quietly in place.

```bash
esem-sandbox compare --set investment.risk_premium=0.1 --set esem.contract_tenor_years=6
esem-sandbox sweep investment.risk_premium 0 0.125 0.25 0.5     # one setting, several values
esem-sandbox compare --scenario short_tenor --quick               # a packaged scenario, on the quick lattice
```

`sweep` runs both legs at every value on one weather draw and prints one table: unserved energy under each leg, what the scheme does to the bill and to the resource cost, what got built and what the levy came to. `--quick` prices 18 futures in the forward view instead of 45, so a comparison takes seconds rather than minutes; its numbers differ from a full run's and should be read as a first look.

A scenario file is a TOML file with a `[run]` table for how the run is made and any settings section it wants to change. The eight packaged ones are in `src/esem_sandbox/scenarios/` and are the shortest way to see the format.

In Python, and in the notebook, the same overrides are a dictionary:

```python
from esem_sandbox.config import load_settings
from esem_sandbox.explore import run_pair, summarise
settings = load_settings({"investment": {"risk_premium": 0.1}})
legs = run_pair(settings, ticks=8, seed=20260904, quick=True)
summarise(settings, legs)
```

## How a run is made

These are not settings but options of a run, given as flags or in a scenario's `[run]` table.

| option | default | what it does |
|---|---|---|
| `--ticks` | 20 | years to run |
| `--seed` | none | the weather sequence and the demand growth path; the same seed gives the same draw, both legs of a comparison share it |
| `--peak` | 12,500 | system peak demand in the first year, MW |
| `--leg` | merchant | `simulate` only: the market on its own, or with the scheme |
| `--investment` | simultaneous | whether firms see each other's decisions within a year; the two rules bracket how much a market builds |
| `--clearing` | anchor | how the bilateral market prices: at the published anchor, or by crossing the two sides' bid curves |
| `--scheme` | off | switch the state renewable scheme on |
| `--retire unit=year` | none | close a plant early, for example `coal_b=2028` |
| `--quick` | off | the forward prices 18 futures instead of 45 |

## The investor

| setting | default | what it does | what it moves |
|---|---|---|---|
| `investment.risk_premium` | 0.25 | how much a firm dislikes an uncertain income: the weight on the gap between the average of its possible incomes and the certain sum it would swap them for | the bar a plant must clear, and so what gets built; at zero every firm is risk-neutral and builds on expected rent alone |
| `investment.cara_scale` | 0.00004 | the scale that turns a firm's risk aversion into a coefficient over dollars per megawatt-year; one function builds it for the investment rule and the cap lane both | the same bar, and the cap premium; leave it unless you are re-tuning both together |
| `investment.hedge_fraction_cap` | 0.85 | the most of a plant's output any contract can count as covered, because a contract covers a forecast of output and the forecast can be wrong | how far a contract can lower the bar |
| `investment.bilateral_contract_years` | 3 | the tenor a bilateral swap book is taken to cover when an investor counts its cover | how much of a plant's life the retailers' swaps de-risk |
| `investment.merchant_underwrite_years` | 0 | a capacity underwrite for firm technologies, in years; zero is the policy-free market | a scenario raises it to ask what an underwrite would do instead of the scheme |
| `investment.discount_rate` | 0.07 | the rate an existing plant discounts its going-forward position at when deciding whether to stay; a candidate uses its own technology's cost of capital from `tech_costs.csv` | exits |
| `investment.build_fraction_of_peak` | 0.05 | the size of one project, as a share of the system peak | how lumpy building is |
| `investment.candidates_per_producer` | 3 | how many technologies a producer considers in a year | the mix |
| `investment.concurrent_builds_per_year` | 2 | the annual build ceiling, as the number of producers' worth of one technology that can start in a year; a damper, so the bust in a boom-and-bust comes from lead times rather than from no limit at all | every reliability figure: doubling it removes the scheme's whole reliability advantage on every seed tested |
| `investment.exit_consecutive_negatives` | 2 | how many losing years in a row before a plant gives notice; two, because one bad year is weather | exits |
| `investment.exit_notice_years` | 3 | the notice a plant gives before closing, as the market's minimum notice of closure | when capacity leaves |
| `investment.max_exit_notices_per_tick` | 3 | the most plants that can give notice in one year, so a cohort cannot all leave against a forward in which all of them stayed | exits |

## The forward view

| setting | default | what it does | what it moves |
|---|---|---|---|
| `forward.anchor_offsets` | [4, 8, 12] | how many years ahead the model dispatches its 45 futures; a plant decided today commissions inside the first and lives past the last | what an investor sees, and the run time: each anchor is 45 more years of hourly dispatch a year |
| `forward.risk_premium_worlds` | growth | what a plant's lifetime rent is risk-priced over: the three growth paths (`growth`), growth and peak band (`growth_band`), or every cell as its own world (`all`); the expectation is the same under all three | how much caution the same spread of futures produces |
| `forward.entry_step_min_mw` | 250 | the smallest step by which the forward's assumed entry moves in a year | how fast the forward's view of new entry settles |
| `forward.entry_decay` | 0.5 | how much of last year's assumed entry carries into this year's starting point | the same |

## The market

| setting | default | what it does | what it moves |
|---|---|---|---|
| `market.market_price_cap_per_mwh` | 20,300 | the price in an hour with not enough plant, and the value unserved energy is costed at | almost all of a peaker's income, and the outage line in every cost comparison |
| `market.administered_price_cap_per_mwh` | 600 | the price cap once the market has been suspended | how much scarcity rent survives a long tight spell |
| `market.cumulative_price_threshold` | 1,823,600 | the sum of prices over a week that suspends the market, as published for five-minute intervals; the hourly model divides it by the intervals an hour holds | how many hours at the cap a year allows: about seven and a half |
| `market.cumulative_price_threshold_intervals_per_hour` | 12 | the market's intervals in one of this model's hours | a definition, not a lever |
| `market.cumulative_price_window_hours` | 168 | the window the threshold is summed over | a definition |
| `market.minimum_price_per_mwh` | -1,000 | the price floor | inert unless something offers below it |
| `dispatch.must_run_offer_per_mwh` | -60 | what a coal band offers to avoid shutting down, about the cost of a stop and restart spread over the hours off | the annual average price, more than any other single number: this band sets the price in about a sixth of the year |
| `dispatch.storage_spread_per_mwh` | 8 | the day's spread between trough and peak a store needs before it cycles | how often storage runs |
| `contracts.cap_strike_per_mwh` | 300 | the strike every cap is written at; above every running cost but the peaking tier's, so a cap pays only when the system is tight | what a cap is worth, and so the cap premium |
| `contracts.swap_tenor_years` | 3 | the bilateral tenor; retailers write a strip this long every year, sized at a third of their target, so three overlapping strips carry the target | how far ahead the bilateral book reaches |
| `contracts.anchor_half_life_years` | 2 | the memory of the swap anchor, an exponentially weighted average of realised block prices; no one here forecasts, they extrapolate | how fast contract prices follow the pool, which is what makes a boom-and-bust |
| `contracts.crossing_steps` | 5 | under `--clearing crossing`, how many slices each side steps away from the anchor in | the volume traded when the two sides have to find each other |
| `contracts.crossing_spread` | 0.25 | how far from the anchor those steps reach, as a fraction | the same |

## The scheme

| setting | default | what it does | what it moves |
|---|---|---|---|
| `esem.contract_tenor_years` | 12 | how long an award's contract runs | how far the award lowers the bar, and how much the levy pays for |
| `esem.contract_start_year_of_plant` | 4 | the year of the plant's life the award starts paying in; the first three are hedged bilaterally like any other plant's | when the levy starts, and how much of a life the award covers |
| `esem.contracted_wacc` | 0.055 | the cost of capital a fully contracted megawatt is financed at, against the technology's own rate for an uncontracted one | the bid a plant needs, and the capital line of the resource cost |
| `esem.screen_multiple_of_spot` | 5 | a sanity screen on bids, as a multiple of the spot price | measured, it cannot bind on this fleet |
| `esem.screen_floor_per_mwh` | 500 | the screen's floor | the same |
| `esem.recycling_window_years` | 3 | how many delivery years ahead the administrator offers its contracts back to retailers | how much of the scheme's cost comes back |
| `esem.recycling_conduct` | warehouse | how it offers them: at the market price and holding what no one buys (`warehouse`), or at a discount (`fire_sale`) | the levy |
| `esem.fire_sale_fraction` | 0.5 | the discount under a fire sale | the levy, under that conduct |
| `esem.overhead_per_year` | 25,000,000 | the administrator's running cost, a stylised figure for a small statutory body | the levy, by that much |
| `esem.reserve_margin` | 0.15 | a reserve margin, reported beside the lane's own sizing and never used to size it | a line in the output |
| `scheme.technologies` | [wind, solar] | what the state scheme buys; each must be a row of `tech_costs.csv` and none may be a cap-eligible technology | which plant the state scheme's contract for difference can go to |
| `scheme.ceiling_per_mw_year` | 120,000 | the most the state scheme pays per megawatt-year of nameplate, net of what the plant expects to earn in the pool | whether a target is met or missed on price |
| `scheme.budget_per_year` | 250,000,000 | the most it spends in a year | whether a target is met or missed on money |
| `scheme.tenor_years` | 15 | how long its contract runs | the same bar-lowering channel as the award's tenor |

## Reliability and weather

| setting | default | what it does | what it moves |
|---|---|---|---|
| `reliability.standard_use_fraction` | 0.00003 | the reliability standard, 0.003 per cent of energy unserved, as the Reliability Panel recommends from 2028; used for the whole horizon | what every unserved figure is measured against, and the shortfall the lane buys to |
| `reliability.interim_measure_use_fraction` | 0.000006 | the tighter interim measure | not read by the model yet; it is declared so the reliability view can use it |
| `weather.shape_years` | 5 | how many synthetic weather years the run draws from; one of them is the lull-on-heat year | the spread of futures |
| `weather.seed` | 20260904 | the seed the five weather years are generated from, and the draw a run uses when it is given no `--seed` | the shape of every weather year |
| `weather.peak_band_multipliers` | [1.08, 1.00, 0.95] | how much a severe, normal or mild peak scales the year's peak | the tails |
| `weather.peak_band_weights` | [0.1, 0.8, 0.1] | the odds of each | the same |
| `weather.hours_per_year` | 8760 | a definition | nothing you would change |
| `time.block_overnight`, `time.block_morning`, `time.block_solar`, `time.block_peak` | 22 to 6, 6 to 10, 10 to 16, 16 to 22 | the four time-of-day blocks swaps are written on, start hour to end hour | what a block swap covers |

## The tables

Four small tables beside the settings file hold the fleet and the choices the market can make. Each is a plain CSV a reader can edit; [DATA_SOURCES.md](DATA_SOURCES.md) says where every number comes from.

| file | what it holds | what to try |
|---|---|---|
| `fleet.csv` | the starting fleet, about 16 rows: capacity, availability, running cost, retirement year, and for hydro its water budget | retire a plant early with `--retire`, or lower the import derate to tighten the system |
| `tech_costs.csv` | what can be built: cost to build and to own, life, cost of capital, firm factor, and whether the technology can write a cap | a cheaper peaker, a dearer battery |
| `dsr.csv` | the demand-response rungs: how much load stops at what price | more or dearer interruptible load |
| `growth.csv` | the three demand growth paths and their odds | a faster central path |
| `scheme.csv` | the state scheme's milestones: how much renewable capacity by which year | a steeper ramp, or a later one |

Every figure in this repository comes from a run with these defaults. Change one and the figures change, which is what the model is for.
