# How the model works

This page follows one year of the model from the first hour to the last investment decision, and says at each step what to look at in a run and which setting moves it. The [README](README.md) says what the model is for; this page says what it does. It assumes nothing about agent-based models.

## Two ways of answering the same question

Both a least-cost model and this one are asked what an electricity system will contain in twenty years. They answer differently because they are built around different people.

| | a least-cost model | this model |
|---|---|---|
| The question | what should the system contain | who would build it, and when |
| Who decides | a solver, minimising the cost of the whole system | six firms, each on its own account |
| What the future looks like | one future, or several run one at a time | 45 futures held at once, each with fixed odds |
| What uncertainty does | nothing; the cheapest plan is built regardless | raises the bar every plant must clear, by an amount that depends on who is looking |
| What a contract does | nothing; there is no one to reassure | lowers the bar, by removing the uncertainty a firm was charging for |
| What reliability is | a constraint the plan must satisfy | an outcome, which the market can miss |
| What comes out | a plan | what a market delivers year by year, including the years it falls short and the years it overbuilds |

A least-cost model cannot see the gap between what a plant costs and what a firm needs before building it, because no one in it is cautious. In this model a gas peaker costs about $136,000 per megawatt-year to own and the firms want $332,000 to $358,000 before building one; three-fifths of the bar is caution. Everything a policy does here, it does by moving that bar.

## One year, in order

Every year the model runs eight steps, in this order.

1. Plant decided years ago and finished this year enters service.
2. The year is dispatched and priced, hour by hour.
3. Contracts written earlier settle against those prices.
4. The book ages: what has finished delivering leaves it.
5. The forward view is rebuilt, and the guess at what everyone else builds is revised once.
6. The scheme's administrator offers its position back, then the bilateral market covers the rest.
7. The scheme's auction runs, awarding at final investment decision.
8. Exit notices are given, and then entry is decided.

The order matters. The administrator sells before the bilateral market so a retailer does not hedge one load twice; exit comes before entry so an entrant prices a market without the plant everyone knows is leaving; a contract struck in one year first settles in the next. The sections below take the steps in turn.

## The hour: how a price is made

Every hour, the plant available is stacked cheapest first and the price is the offer of the last unit needed. In most hours that is the running cost of a coal or gas unit, tens of dollars a megawatt hour. When there is not enough plant the price climbs through the demand-response rungs, customers who have agreed to be interrupted at a price, and on to the market price cap of $20,300 a megawatt hour, which is what the market uses as the value of energy no one got.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/price_stack_dark.png">
  <img alt="The offer stack, cheapest first, with the demand-response rungs and the price cap above it" src="outputs/canonical/price_stack.png">
</picture>

Two things are not on the stack. Hydro is spread across the year against its water budget: the model finds the hours it is worth the most in and spends the budget there, and prices the water at what it displaces. Storage fills the day's trough and shaves its peak, on quantities, so it is never bidding a price its own schedule would then move. The real market's safety valve is here too: if the sum of prices over a week passes a published threshold, prices are capped at $600 until the sum falls back, which limits a crisis to about seven and a half hours at the cap.

Almost all of a peaking plant's income arrives in the few hours at the top of the stack. The worst week of the stressed weather year shows why.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/worst_week_dark.png">
  <img alt="Residual demand against the firm capacity available through the worst window of the stressed year" src="outputs/canonical/worst_week.png">
</picture>

What to look at: `esem-sandbox run` prints a calibration report for each of the five weather years, and writes `dispatch_summary.csv`, the price-duration chart and the worst week. What moves it: `dispatch.must_run_offer_per_mwh` sets the price in about a sixth of the year; the import link's rating in `fleet.csv` is the lever that sets how tight the system is; `dsr.csv` is the demand-response ladder.

## The year: settlement, and how much gets traded

A swap fixes the price of an agreed quantity over a block of the day; a cap pays out whenever the price rises above $300 and nothing otherwise. Both settle against all 8,760 hours, never against an average, so a cap's value comes from a handful of hours and a swap's from the whole block.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/cap_payout_dark.png">
  <img alt="Where a cap pays: the hours above the strike in one year" src="outputs/canonical/cap_payout.png">
</picture>

Nobody is given a contract position. The volumes traded come from inside the model, from who needs cover and who has it to sell, and they change as the fleet changes.

Two retailers carry all of the load, 60 and 40 per cent. Each hedges to a mandate: three-quarters of its average load in every block of the day under swaps, and a fifth of its share of the peak under caps. It buys on a ladder, writing a three-year strip each year sized at a third of the target, so three overlapping strips carry the target in steady state and the book ages rather than lurching. A retailer that took a recycled contract from the scheme's administrator this year needs that much less from producers.

Four producers own the fleet and write the cover, pro rata to what each has to sell: available capacity for swaps, and cap-eligible firm capacity for caps, because a plant that cannot be relied on in a scarce hour cannot write insurance against one. What each producer has sold forward is its cover, and cover is what lowers its bar in the decision below. A market that builds more plant spreads the same retail demand for hedges over more capacity, so each plant is less covered and the bar rises; that feedback is inside the model, not a setting.

Prices in the bilateral market are not forecasts. A swap lane clears at what its block has recently been worth, an exponentially weighted average of realised block prices with a two-year half-life. A cap lane clears at the larger of what a peaker needs per firm megawatt-hour to exist and what the cap has lately paid out, plus a loading for the risk the writer carries. The loading is priced with the same measure of caution the investment rule uses, so a firm cannot value the same bad hour one way when writing insurance and another when deciding whether to build the plant that would relieve it.

What to look at: `run_summary.csv` counts the live contracts each year; the notebook prints each producer's contracted share of its output. What moves it: the retailers' `swap_cover` and `cap_cover` in `core/agents.py`, `contracts.swap_tenor_years`, `contracts.anchor_half_life_years`, and `--clearing crossing`, which makes the two sides find a price between them instead of both accepting the anchor, and trades about half the volume.

## The forward view: 45 futures at three distances

No one in the model forecasts a price. Every year, the model writes down 45 possible futures, five weather years by three demand growth paths by three peak severities, each with fixed odds, and dispatches every one of them in full at four, eight and twelve years ahead. That is 135 dispatched years behind every investment decision.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/forward_view_dark.png">
  <img alt="45 futures priced at three distances, and what they pay a peaker" src="outputs/canonical/forward_view.png">
</picture>

The odds never move. After fifteen years of fast growth, the firms still think slow growth is as likely as they did at the start. That is deliberate, and [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) says what it costs.

The view includes a guess at what everyone else will build, because a project is worth less in a crowded market. The guess moves one step a year: the technology that pays best and can still grow is assumed to grow, and when nothing pays the one furthest under water shrinks. What is assumed built by four years out is carried to eight and twelve. It is a signal rather than a settled number, and the two investment rules below bracket what the market does with it.

What comes out is a spread rather than a number: what a megawatt of each technology would earn above its running cost in each of the 45 futures, per year. The decision works on that spread.

What to look at: `run_summary.csv` carries the forward's expected unserved energy four years ahead and the assumed entry at each distance. What moves it: `forward.anchor_offsets`, the peak bands in `weather`, the growth paths in `growth.csv`, and `--quick`, which prices 18 of the 45 and runs in seconds.

## The decision: why a firm hesitates

A plant is built when what it expects to earn, per megawatt per year, covers what it costs to own, per megawatt per year. Both sides are on that same basis, so no assumption about how often the plant runs enters the comparison, and a peaker running two per cent of the year and a wind farm running 35 per cent are each tested against their own costs.

The firm is cautious rather than neutral. It does not compare the average of its 45 incomes with its cost; it compares the certain sum it would swap that spread for, the certainty equivalent, and that sum is below the average by an amount that grows with the spread and with the firm's own dislike of risk. The shape of the caution is the standard one from economics, constant absolute risk aversion, and it is exact rather than an approximation: a firm's demand for a premium saturates at the worst future it can see, so a scarcity windfall reads as upside rather than as symmetric risk, and the model never prices out the very plant that would relieve a scarcity.

Caution is scaled by exposure, the share of the plant's life still facing the spot price. A plant with every year of its output sold forward has an exposure of zero and is judged on its expected rent alone; a plant with none has an exposure of one. Cover can never reach one, because a contract covers a forecast of output and the forecast can be wrong.

The hurdle is the plant's fixed cost plus what its caution costs it. The figure below splits the bar a peaker must clear into the two parts, for each of the market's firms.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/hesitancy_dark.png">
  <img alt="How much of the bar a plant must clear is caution rather than cost" src="outputs/canonical/hesitancy.png">
</picture>

The six firms differ almost only in how much they dislike risk. The two firms that own both plant and customers sit lowest, because the pairing hedges them; the merchant that owns only peakers sits highest; the regional merchant, the representative new entrant, sits between. Those levels are a chosen ordering rather than a measurement, and the ordering is what carries the results.

What to look at: every build in `run_summary.csv`, with the hurdle it cleared and the rent it expected; the dashboard's "every build, and the test it passed" panel. What moves it: `investment.risk_premium` (zero makes every firm risk-neutral), `investment.hedge_fraction_cap`, `investment.bilateral_contract_years`, and each technology's cost of capital in `tech_costs.csv`.

## What lowers the bar: contracts, and the scheme's award

Three kinds of cover can lower a plant's exposure. The retailers' swap book reaches three years into a twenty-five-year life, so it moves the bar by a few per cent. A capacity underwrite is off in the market on its own, so that leg stays policy-free. The scheme's award is the third, and the one the model exists to measure: a contract covering the plant's fourth to fifteenth years removes uncertainty rather than paying for it, and the bar falls by about a sixth. The same money handed over as a subsidy would do less, because a subsidy lifts the expected income and leaves the spread alone.

The scheme buys firm capacity that the market on its own would not build. Four quantities decide whether that is worth doing.

How much to buy. The lane volume is the delivered firm capacity that brings expected unserved energy, four years out, down to the reliability standard, computed on each future's hourly shortfall. A reserve margin is a rule of thumb about that quantity; the model reports one beside the lane and never sizes by it.

What it is worth. A plant bids the top-up it still needs, on top of what it expects to earn in the market, to be worth building, priced with the same caution as its own decision and financed at the cheaper cost of capital a contracted plant can borrow at. Bids clear pay-as-bid in merit order until the gap is closed. A plant that needs nothing bids zero, and the scheme awards it anyway; a zero bid is the signature of paying for something that would have happened regardless, and the model reports them.

When it is committed. At award, which is the plant's final investment decision, so the plant arrives after its lead time rather than in the year the scheme wanted it. The contract is the one the plant can back: a cap on firm megawatts for plant that can cover a scarcity hour, a contract for difference on metered output for a wind or solar farm, a swap on the peak block for a store. It starts in the plant's fourth year and runs for twelve; the first three years are hedged in the bilateral market like any other plant's.

Who pays. The administrator offers the contracts it holds back to retailers at the market price for each delivery year, because no one buys a hedge above the market, and so recovers everything but the top-up. What it cannot recover, plus its running costs, divided by the energy consumers took that year, is the levy. There is no fund and no smoothing: the levy lands in the year the money moved.

A state scheme is the other buyer in the model. It buys nameplate megawatts of a named technology against a milestone in a policy, under a price ceiling and an annual budget, and its contract starts when its plant does. Nameplate and firm megawatts are different products, and a gigawatt of wind at a firm factor of a tenth is a hundred megawatts of the thing the reliability lane buys, so the model never adds the two.

What to look at: `comparison.csv` carries the lane volume, the reserve-margin gap, the megawatts awarded, the scheme's cost and the levy per megawatt hour, year by year; the dashboard's lane and levy panels draw them. What moves it: `esem.contract_tenor_years`, `esem.contract_start_year_of_plant`, `esem.contracted_wacc`, `esem.recycling_conduct`, and `--scheme` for the state scheme, whose milestones are in `scheme.csv`.

## Pacing, the bracket and exit

Building is paced. One project is a twentieth of the system peak, rounded to whole units, and each technology can start at most two producers' worth of projects in a year. That ceiling stands in for supply chains and crews; it is a choice, and doubling it removes the scheme's whole reliability advantage on every weather draw tested, so it is reported as a sensitivity rather than hidden as a number.

How much a market builds depends on whether its investors can see each other, and the model has two rules that differ in nothing else. Under the first, each firm prices its project against a forward view that contains none of the other firms' projects, so no one sees anyone and everyone builds up to the ceiling. Under the second, the view is redrawn after each firm decides, so the first decision of a year removes the scarcity rent the rest were counting on. Real investors are neither, and the two rules bracket the amount built. The bracket matters because reliability is not proportional to capacity: take firm plant away in small steps and each megawatt removed exposes more hours than the last.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/reliability_curve_dark.png">
  <img alt="Unserved energy against firm capacity" src="outputs/canonical/reliability_curve.png">
</picture>

Plant leaves as well as arrives. A coal or gas plant that has failed to cover the cost of staying open for two years running gives three years' notice, which mirrors the market's minimum notice of closure, and at most three plants can give notice in one year, so a whole cohort cannot leave against a forward view in which all of them stayed. What a plant cost to build is already spent and plays no part.

What moves it: `investment.concurrent_builds_per_year`, `--investment sequential` for the second rule, `investment.exit_consecutive_negatives`, `investment.exit_notice_years`.

## Boom and bust, and what a comparison means

Nothing in the model forecasts. Contract prices are averages of prices that have happened, an award's strike is the forward view's expectation, and the view is a list of futures at odds that never move. That is the whole mechanism behind boom and bust: scarcity lifts prices, investors extrapolate, everyone builds, and the plant arrives together into a market that no longer needs it.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/arrival_dark.png">
  <img alt="When each leg's firm capacity arrives, against the years the market is short in" src="outputs/canonical/arrival.png">
</picture>

A comparison runs the same twenty years twice on the same weather, once with the market on its own and once with the scheme. The difference between the two legs is the mechanism and nothing else. It is reported on two lines that must never be read as one: the bill, which is what consumers pay, and the resource cost, which is what the economy gives up in fuel, plant, capital and energy no one got. Most of the gap between them is transfer, money moving from producers to consumers because more capacity pushed the pool price down. A policy that cuts the bill by billions may not save a cent.

One run is one weather draw. Ten draws of the same comparison show the scheme buying reliability on eight and paying for it in real resources on all but one of those, while on two draws the market alone sheds less. The sign of a single run is a property of the draw, and what travels is the sort: the outage avoided is largest on fast-growing draws and smallest on slow ones, where the scheme buys capacity that has little to do.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/ten_seeds_dark.png">
  <img alt="Outage avoided and plant and fuel spent, per weather draw, grouped by growth path" src="outputs/canonical/ten_seeds.png">
</picture>

What to look at: `comparison.txt` is the full account of one pair, and `ten_seeds.csv` the envelope. `esem-sandbox sweep` runs both legs at several values of one setting and puts the results side by side.

## Reading a run

`esem-sandbox compare` writes `comparison.csv`, one row a year with both legs' unserved energy, the lane, the awards and the levy, and `dashboard.png`, eight panels in the order the year runs: capacity by technology, unserved energy against the standard, the price-duration curve of the year the legs differ most in, every build against its hurdle, the two cost lines, the lane against the shortfall it was sized on, the levy, and the cap premium. `esem-sandbox simulate` writes `run_summary.csv` for one leg, with a row a year: prices by block, unserved energy, the forward's expectation, the assumed entry, firm capacity, what was built, exit notices and the peaker's missing money.

The [notebook](notebooks/walkthrough.ipynb) runs all of this live, section by section, and ends with a comparison you can change one setting at a time. [PARAMETERS.md](PARAMETERS.md) lists every setting; [GLOSSARY.md](GLOSSARY.md) explains the terms; [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) says what the model leaves out and which of its results are easy to misread.
