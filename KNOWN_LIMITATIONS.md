# What this model gets wrong

This page says what the model leaves out, what it gets wrong, and which of its results are easy to misread. Each entry says what that costs a reader. The tools in `tools/` measure each of them on the packaged fleet, and the numbers quoted here come from those runs. [GLOSSARY.md](GLOSSARY.md) defines any unfamiliar word.

## What is left out on purpose

One region, so nothing locational: no interconnectors, no transmission build, no regional price divergence. Synthetic weather, so the probability of a drought year is stipulated at one in five rather than measured. A stylised fleet of about 16 rows, so no unit-level commitment, no minimum stable levels and no outage draws. The reliability standard is held flat across the horizon rather than stepped as the published one is.

Every cost is constant over the horizon: one running cost per row, so there is no fuel price path, and one capital cost per technology, so there is no cost decline. Nothing ages. Hydro is one annual energy budget dispatched within the year, so water carries no value between years. The fleet table describes the system to about 2050, when most of the remaining plant leaves at once; a run that reaches further prices a fleet the model has built for itself.

Storage is scheduled on quantities rather than on the price it produces. A store fills the day's trough to a level and shaves its peak to a level, with the levels set so the energy balances across the round trip. That makes four things exact: a store cannot make the peak worse, cannot charge and discharge in the same hour, cannot deliver energy it never stored, and does not chase the price its own schedule moves. What it costs is that a store spreads its discharge across the hours above its threshold rather than concentrating it in the single tightest hour, so an optimiser would do a little better in the worst hours of the worst year.

Cover is shared out by capacity and settled on energy. When retailers buy swaps, the volume is split across producers in proportion to the capacity each has available, and a swap settles on energy. On the packaged fleet those are a long way apart: the owner of the peakers and the pumped hydro holds 12 per cent of the capacity and is a net consumer of energy across a year, yet is handed 12 per cent of every megawatt of fixed-price cover. Splitting by expected energy would be modelling the portfolio, which is left out on purpose, and it would change what every producer builds.

Investors never learn which future they are in. The forward view keeps the same odds on its three demand growth paths whatever the path the run is on has been doing for 15 years, because no one in this model forecasts. A run on the high growth path is therefore one where investors keep building for a slower world than the one they are in. Telling the forward view which path the run is on does not rescue the scheme on the slow draws: it makes the scheme buy less on eight of ten seeds, and the cost line and the outage line improve together on only two.

Caution is priced on the growth path and on nothing else. A run draws its growth path once and its weather and peak afresh every year, so over a plant's life only the path is one future; the other two average out. The year-to-year dispersion a life of annual draws still carries, a drought year being a bad year whether or not the next one is, carries no premium. Priced with the same caution it would add roughly $20,000 to $30,000 per megawatt-year to a four-hour battery's hurdle.

The administrator has no view. It offers its position back at the market price for each delivery and warehouses whatever no one buys. It does not withhold volume to hold a price up, read the market, or trade on its own account. A real administrator would sit somewhere between that and a fire sale, and where it sat would be worth money.

Investors' guess at what everyone else builds never settles. The forward view works out how much plant everyone else will build by trial, one step a year, while the actual fleet moves underneath it, so what the investment rule reads is a half-finished calculation chasing a target that has already moved. Read the assumed entry as a signal with the right sign and the right rough size, and never as a statement of where free entry would land.

Consumers carry the contracted plant's risk for nothing. A plant under a scheme award is financed at a blended rate, cheaper in proportion to the share of its life the contract covers, because the price risk has moved to consumers. The resource cost books that cheaper capital as a real saving, which on the canonical seed comes to $1.38bn over the run. What consumers give up in carrying the risk is priced nowhere, so that figure is the most the omission can be.

## What the model gets wrong

Decisions taken against a shared forecast do not see each other. Every producer prices every candidate as though it were the only thing being added to a market that contains none of the others, and a tick holds 12 such decisions against one forward view. What stops that running away is the annual build ceiling, which is a pacing choice rather than an economic force: on the canonical seed every megawatt of merchant build sits at the ceiling, in every technology-year anything is built, and doubling the ceiling leaves every megawatt at the cap. Price feedback exists and is far too weak to bind inside a year: adding 600 MW of wind to the forecast takes about $65,000 per megawatt-year off what the next block of wind is worth, so shutting wind off would take about 6,000 MW while the ceiling stops at 1,200. The economics decides which technologies get built and whether a year builds at all; the ceiling decides how much. The alternative rule, which reprices the forecast after each producer decides, is runnable (`--scenario repriced_investment`) and is the other end of the bracket described below.

Exit cannot see a contract, and entry can. Entry reads the contract book and lowers the hurdle for cover already held. Exit reads nothing, so a plant whose price is fixed for 12 years by an award is tested for retirement against the spot prices the award insulates it from. On the packaged fleet this is latent, because the economic exit rule never fires: no plant reaches two consecutive loss-making years in a 20-year run, and the plants nearest to it are the old open-cycle units in the final year. It becomes live the moment someone changes the cost table or brings a retirement forward.

No one pays for the state scheme. The state capacity target writes real contracts that settle real money every year, and nothing charges it to anyone: the levy is computed only from the reliability administrator's position, and the target runs on the other leg against a different counterparty. A reader comparing a capacity target with a reliability lane on what they cost cannot do it here. Who should pay is a policy question with more than one defensible answer, so nothing has been made to charge it.

Demand response costs nothing, and someone is paying. The four tiers of customers who agree to stop drawing power at rising prices set the price when they are called and supply energy in the model's own balance identity, and they are paid nothing: over ten years on the canonical seed the ladder supplies energy the market values at $0.39bn on the merchant leg and $0.23bn on the scheme leg, and neither figure reaches any account. Read the ladder as a price-setting mechanism rather than as a participant with a balance sheet.

## What is easy to misread

A cap contract here is almost purely a tail instrument. A $300 cap pays $107,000 per megawatt-year averaged across the five weather years, and 99 per cent of it comes from the 35 hours at or above $7,500. Expect the payout to be lumpy across weather years, a spread of more than four to one between the mildest and the worst, because that is what insurance against extremes looks like.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/cap_payout_dark.png">
  <img alt="Where a cap's money is" src="outputs/canonical/cap_payout.png">
</picture>

A modest gap in building is a huge gap in blackouts. Scale the packaged fleet's firm plant down and dispatch the same weather year: take three per cent away and the lights go out twice as often, take 15 per cent away and it is 14 times as often. Reliability lives in the worst few hours of a year, and the load in those hours is steep, so each megawatt removed exposes many more hours than the one before it. This is why capacity adequacy is argued about at all: a disagreement about whether a market builds slightly too much or slightly too little is a disagreement about whether the lights stay on.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/reliability_curve_dark.png">
  <img alt="Unserved energy against firm capacity" src="outputs/canonical/reliability_curve.png">
</picture>

The model brackets how much a market builds, and the verdict on the scheme does not survive the bracket. Under the default rule the two legs of the canonical comparison shed 174 and 30 GWh on a reduced lattice; under the repriced rule, 844 and 140. The scheme cuts unserved energy by a factor of about six at either end, so the direction of its reliability effect travels. Its cost does not: it costs $1.88bn of resources under one rule and saves $8.24bn under the other, because a market that under-builds badly leaves far more outage for a scheme to avoid. The verdict on a procurement scheme turns on how badly you think a merchant market under-builds, which the model brackets rather than determines.

A lower hurdle changes what gets built, not only how much. A contract, a longer underwrite or a lower risk premium all lower the bar a project must clear. What that does to firm capacity depends on which technology clears the lowered bar first, and the technologies differ by a factor of 17 in how much firm capacity a megawatt of nameplate carries. What it does to reliability depends on when the plant arrives, which a count of firm megawatts does not record: a ten-year underwrite raises firm capacity on three of four weather seeds and lowers it on the fourth, and on two of those seeds unserved energy holds exactly whichever way the megawatts went. Read a capacity number and a reliability number as two separate answers.

The scheme can buy plant that would have been built anyway. A bid is what a plant still needs after the certainty equivalent of what it expects to earn in the pool. Where that comes out at zero the plant needed nothing, and the lane awards it anyway at a cost of nothing. A zero-priced award is the signature of additionality failing, and it shows up on the first tick of a run where the near future looks short enough to make everything look profitable. Read it as a finding rather than as capacity the scheme delivered.

Part of the scheme's effect is reallocation, not addition. The auction runs before the investment step and draws on the same annual build ceiling, so an award consumes room the market would otherwise have used. On the canonical seed 17,600 MW of merchant build makes way for 13,750 MW of awards, and the scheme leg ends with 3,850 MW less plant and 2,132 MW less firm capacity on the table than the market alone, while shedding a third as much energy: 11.0 GWh against 32.6. What the awards displace is the firm plant the market would have built later. More than half of the merchant leg's firm capacity is commissioned from 2040 on, after the years it was short in, and some of it after the run ends; the scheme leg's arrives in the years the market sheds in. What the scheme buys is plant standing in the right years, at the cost of the plant the market would have built later.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/arrival_dark.png">
  <img alt="Firm capacity commissioned so far on each leg, and the energy each shed by year" src="outputs/canonical/arrival.png">
</picture>

A scheme cannot fix a year that arrives before its plant does. The first two or three years of a paired run are identical on both legs, because the plant awarded in year one has not been built yet, and on the packaged fleet the second year, at five times the reliability standard, is the worst year the scheme leg has. That is the lead time, and it is the reason a procurement scheme is an instrument about the future rather than a response to the present.

The levy can run either way. The administrator buys a hedge from each awarded plant at the price the auction struck and sells it on to retailers at the market price. What it never recovers is the top-up that carried the bid, which is the scheme's cost. It also holds the position for as long as no one has bought it, so when prices come in above the projection the levy is a rebate and when they come in below, consumers pay. Over a 20-year run it changes sign; the cost of the capacity is the bids, which `compare` reports separately.

A capacity target buys capacity, and the model will not let it buy reliability. The reliability lane buys delivered firm megawatts, sized on the projected shortfall. A state target buys nameplate megawatts against a number in a policy. On the packaged fleet it contracts 6,900 MW of wind and solar over 20 years, the market builds 7,200 MW less of its own through the shared ceiling, and unserved energy moves from 32.6 GWh to 33.2. Every milestone is missed, because no one could build it that fast, and most of what it buys costs almost nothing, because wind and solar already clear their own hurdles here. Adding the two instruments' megawatts together is the mistake this arrangement exists to make impossible.

The scheme's worth depends on which future the market turned out to be in. Across ten seeds the scheme improves reliability on seven and worsens it on three, and lowers the total resource cost on three. Where it avoids outage it usually spends more on plant and fuel than the outage was worth; on the three seeds where it sheds more than the market alone, all low or central growth, the two legs come level once the build ceiling is doubled. What the scheme buys on most draws is reliability, at a price in real resources, and whether the price is worth paying turns on the value of lost load, which is a regulatory figure here and not a measurement.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/ten_seeds_dark.png">
  <img alt="Outage avoided and plant and fuel spent, per draw, grouped by growth path" src="outputs/canonical/ten_seeds.png">
</picture>

The build ceiling bounds every reliability claim above. Run the same comparison at twice the annual ceiling and the scheme's whole effect disappears on every seed tested: the three it harmed come level and the one it helped most goes from a 28.5 GWh gain to none. The merchant leg gains far more from the extra room than the scheme leg does, which is what to expect if a large part of what the scheme provides is permission to build sooner. The reliability comparison is substantially a statement about a pacing parameter, and four is no more correct than two. A reader who takes one number from this page should take that one.

When buyers and sellers negotiate, both start from the same number. The option that makes the two sides of the contract market find a price, rather than both accepting a reference price, builds each side's curve by stepping away from that same reference in equal slices. Mirror images cross at the reference whatever their shape, and the volume traded depends on how finely the curves are cut and on whether that number is odd. The direction is real: assuming both sides accept the reference buys more cover, which flows into every producer's exposure and hurdle. The size is a setting, and not a magnitude to quote at a room.

The economic exit rule never fires on this fleet. Every retirement in a packaged run is the date written in the fleet table, or the one a scenario forces. That is a legitimate answer for a fleet in which nothing is losing money, and it means the careful staggering of exit notices is code these runs never execute. Check this again before believing any claim about retirement on a changed fleet or cost table.

## What is deliberately exact

The energy balance closes to the floating-point limit in every hour of every packaged run: generation net of curtailment, plus the demand-response ladder, plus unserved energy, equals operational demand. Hydro delivers its stated annual budget exactly. No unit generates at a price below its own offer. These are tested, and they are the properties the conclusions rest on.

The balance has one boundary, reachable from the command line. Rooftop solar is a fixed 5,200 MW netted off demand and never curtailed, because it sits behind the meter and does not bid. Take the system peak below about 9,000 MW with `--peak` and there are hours when rooftop alone exceeds demand by more than the utility wind and solar can absorb; the surplus is silently dropped and nothing warns you. At a peak of 7,000 MW that is 77 GWh a year reported nowhere. The guarantee holds for the packaged system and anything near it, and not for a system small enough that its own rooftop overwhelms it.
