# What this model gets wrong

Each entry is labelled with one of five kinds. A defect that is still there and a simplification made on purpose call for very different reactions.

If a word here is unfamiliar, [GLOSSARY.md](GLOSSARY.md) defines it in plain language.

| | what it is | how to read it |
|---|---|---|
| [Storage is scheduled on quantities](#storage-is-scheduled-on-quantities-not-on-the-price-it-produces) | guarantee | four properties that follow from the rule's shape |
| [A cap is a tail instrument](#a-cap-contract-here-is-almost-purely-a-tail-instrument) | result | expect lumpy payouts across weather years |
| [Decisions cannot see each other](#decisions-taken-against-a-shared-forecast-do-not-see-each-other) | **defect** | it sets how much gets built |
| [The lane's screen does not bind](#the-lanes-sanity-screen-does-not-bind) | simplification | a guard against nonsense, sitting clear of real bids |
| [Cover is shared out by capacity](#cover-is-shared-out-by-capacity-and-settled-on-energy) | simplification | exposure carries the leg difference, not portfolio shape |
| [Exit cannot see a contract](#exit-cannot-see-a-contract-and-entry-can) | **defect** | latent here, because the rule below never fires |
| [Economic exit never fires](#the-economic-exit-rule-never-fires-on-this-fleet) | result | every retirement here is the one written in fleet.csv |
| [Nobody pays for the state scheme](#nobody-pays-for-the-state-scheme) | **defect** | its contracts settle real money that no cost line carries |
| [Consumers carry contract risk for nothing](#consumers-carry-the-contracted-plants-risk-for-nothing) | simplification | the financing saving is counted; its price to consumers is not |
| [Demand response is free](#demand-response-costs-nothing-and-somebody-is-paying) | **defect** | it sets prices, supplies energy, and costs no line anything |
| [Small in megawatts, huge in blackouts](#why-a-modest-gap-in-building-is-a-huge-gap-in-blackouts) | result | why capacity adequacy is argued about at all |
| [What the bracket does to the scheme](#what-the-bracket-does-to-the-schemes-result) | bracket | the reliability direction travels; the cost verdict does not |
| [A lower hurdle moves the mix](#a-lower-hurdle-changes-what-gets-built-not-only-how-much) | result | reliability does not follow firm capacity |
| [The guess at what others build never settles](#investors-guess-at-what-everyone-else-builds-never-settles) | simplification | read it as a signal, not as a settled answer |
| [Investors never learn their future](#investors-never-learn-which-future-they-are-in) | simplification | no one in this model forecasts, and it costs something |
| [Caution is priced on the growth path](#caution-is-priced-on-the-growth-path-and-on-nothing-else) | simplification | a year's weather carries no premium, by ruling |
| [The scheme buys plant built anyway](#the-scheme-can-buy-plant-that-would-have-been-built-anyway) | result | additionality, made visible rather than hidden |
| [Part of the effect is reallocation](#part-of-the-schemes-effect-is-reallocation-not-addition) | result | what the awards displace matters as much as what they add |
| [A scheme cannot fix an early year](#a-scheme-cannot-fix-a-year-that-arrives-before-its-plant-does) | result | the most misread rows in a paired run |
| [The levy can be a rebate](#the-levy-can-run-either-way) | result | the administrator holds a position and prices move |
| [The administrator has no view](#the-administrator-never-has-a-view) | simplification | it never withholds, reads the market or trades |
| [Negotiating starts from one number](#when-buyers-and-sellers-negotiate-both-start-from-the-same-number) | bracket | the direction is real; the size is a setting |
| [A capacity target is not reliability](#a-capacity-target-buys-capacity-and-the-model-will-not-let-it-buy-reliability) | result | the easiest thing here to misread |
| [Which future the market was in](#the-schemes-worth-depends-on-which-future-the-market-turned-out-to-be-in) | bracket | no single run is a property of the scheme |
| [What the simplification costs](#what-the-simplification-costs-elsewhere) | simplification | one region, synthetic weather, a stylised fleet |
| [What is deliberately exact](#what-is-deliberately-exact) | guarantee | the properties the conclusions actually rest on |

Five kinds, and the label is the first thing to read:

- **defect** means the model gets this wrong.
- **simplification** means it was left out on purpose, and says what that costs.
- **result** means it is not a limitation at all. These are here because readers reliably mistake them for faults.
- **bracket** means the model can show a range and cannot say where in it the truth sits. Quoting either end as the answer is the mistake.
- **guarantee** means something the model holds exactly, and that its conclusions rest on.


## Storage is scheduled on quantities, not on the price it produces

A store fills the trough up to a level and shaves the peak down to a level, with the levels set so the energy balances across the round trip. Four properties follow from the shape of that rule rather than from any tuning.

A store cannot make the peak worse. Charging fills to a level at or below the discharge level, so the post-storage residual never exceeds the pre-storage peak. Adding four-hour storage to this fleet lowers peak net load monotonically, from 9,300 MW through 8,320 and 7,340 to a floor of 7,074 MW, where the day is flat enough that more storage changes nothing.

A store cannot charge and discharge in the same hour. The two levels are ordered, so the hours they select are disjoint.

A store cannot deliver energy it never stored. The state of charge is tracked hour by hour through the day, and an hour that asks for more than the store holds is capped at what it holds. Checking the day's totals instead would let a store whose trough falls after its peak deliver in the evening energy it does not store until that night.

The schedule does not chase the price it produces. Quantities are a function of the residual and the unit. Price decides only whether a day's spread covers the round trip, and each unit judges that against the residual the units before it have left. Measured by doubling every thermal running cost with hydro removed, so the residual storage sees cannot move, the schedule changes in 49 hours of 8,760 and by up to 490 MW. That is the spread gate turning whole days on and off, which is what it is for, rather than quantities being read off the price.

Because the residual does not depend on the price, there is no fixed point to chase and dispatch runs in one pass.

What it costs. The fleet's import capability is set at 1,000 MW, which is the lever that decides how tight the system is. The four mild shape-years sit between a fifth and four fifths of the reliability standard and the lull-on-heat year at 2.3 times it.

What is still approximate. A store spreads its discharge across the hours above its threshold rather than concentrating power in the single tightest hour. In the load shedding hours of the drought shape-year the fleet's stores deliver most of their rated power, so what remains of this is small. An optimiser would still do better by moving energy out of a merely expensive hour and into a shedding one.


## A cap contract here is almost purely a tail instrument

The ladder's two cheapest tiers are 1.0 MW at $300/MWh and 20.8 MW at $500/MWh, transcribed as increments from the published demand-side participation table. They are so small against a 12 GW system that any hour reaching them is short by far more, so both are exhausted inside the same hour and the price lands on the tier above. Neither ever sets a price.

A fleet that stopped at gas peakers around $190/MWh would leave no hour able to settle anywhere between $190 and $7,500, a hole in the price duration curve exactly where a $300 cap contract lives. A stylised high-cost peaking tier, 500 MW at $480/MWh, fills it, and hours do settle in the band.

That does not change the cap's character. A $300 cap pays $107,368 per MW-year averaged across the five shape-years, and 99 per cent of it comes from the 35 hours at or above $7,500. Only 56 hours in the whole set reach the strike at all. That is not a defect. A cap is insurance against extremes, and its value in the real market is likewise concentrated in a handful of intervals. A reader should expect the payout to be lumpy across weather years rather than smooth: the five shape-years pay $50,080, $74,760, $87,080, $100,300 and $224,620, a spread of more than four to one between the mildest and the worst.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/cap_payout_dark.png">
  <img alt="Where a cap's money is" src="outputs/canonical/cap_payout.png">
</picture>

The shaded area is the payout in the worst of the five years. Averaging that year's prices before asking how much sat above the strike gives zero, because the average is below $300.

## Decisions taken against a shared forecast do not see each other

This model has three places where several decisions are taken in the same year against one forecast, and none of them sees the others. They are the same failure in three costumes, and they are grouped here because none of them looks like the others until it is.

Entry, in the forward view: every candidate technology asks whether it would be worth building in a market none of the others has entered. One marginal entrant moves a tick, because letting all seven move in one pass assumes 15 gigawatts of entry on a 12 gigawatt system.

Exit: every plant's going-forward position is evaluated against a fleet in which none of the others has left. Notices are capped per year and fired worst-first, so the forward reprices between cohorts.

Investment: every producer prices every candidate as though it were the only thing being added to a market that contains none of the others. That is the right assumption for one small entrant and the wrong one for 12 decisions taken in the same year against the same forward view, which is what a tick here contains: four producers considering three candidates each, none of them seeing the others.

This third one is untreated, and it is the most consequential of the three. What stops it running away is the annual build ceiling, which is a pacing choice rather than an economic force.

Measured on the canonical seed, over 20 years, every megawatt of merchant build is placed at the ceiling: 56,800 of 56,800 MW, in all 34 of the technology-years in which anything was built. Doubling the ceiling does not relieve it: the market builds more, 73,400 MW, and every megawatt of it at the cap. The scheme leg behaves the same way, every megawatt at the tight ceiling and 98 per cent at the loose one.

The reason is the failure named above, and the loose version of it is wrong: price feedback does exist. Measured on this fleet, adding 600 MW of wind to the forecast takes about $65,000 per MW-year off what the next block of wind is worth and adds about $11,000 to the hurdle it has to clear (`tools/marginal_feedback.py`):

| wind already added | hurdle | what it is worth | clears it? | among the few it picks? |
|---|---|---|---|---|
| none | $354,701 | $1,123,000 | yes | no |
| 600 MW | $362,996 | $1,055,669 | yes | no |
| 1,200 MW | $389,653 | $978,417 | yes | no |
| 1,800 MW | $405,026 | $905,134 | yes | no |
| 2,400 MW | $410,972 | $851,305 | yes | no |
| 3,000 MW | $410,713 | $797,660 | yes | no |

The discipline is real and far too weak to bind inside one year: the gap opens at $767,000 and closes at roughly $76,000 a block, so shutting wind off would take about 6,000 MW while the annual ceiling stops at 1,200, and the ceiling always bites first.

The last column matters. Wind clears its own hurdle three times over at every step and is never among the handful of candidates a producer actually takes to a decision, because others rank above it on surplus. Clearing a hurdle and being chosen are different questions here, and only the second one builds anything.

What fills the ceiling is not one investor wanting an unlimited amount. Each producer commits at most one block of each technology that passes its test, and only the best three candidates are put to the test at all, so a technology's ceiling is filled by four producers picking the same winner against a ceiling that allows two blocks: the first two get theirs and the other two are shut out. The economics therefore decides which technologies get built and whether a year builds at all. It never decides how much.

The annual build volume in this model is a parameter, not a result, and it is not a parameter that only bites when the forward is enthusiastic - it binds in every year anything is built. Read every quantity that depends on the pace of build with that in front of it, including the reliability comparison, whose ceiling sensitivity is measured further down.

The treatment the other two costumes have is available: decide sequentially and reprice in between, so the second block is offered a market that contains the first. It is built and it is runnable both ways: `run(investment="sequential")` from Python, and `--scenario repriced_investment` from the command line. It is not the default, and the measurement below says why.

| | build | at the ceiling | firm at the end | unserved |
|---|---|---|---|---|
| simultaneous (default) | 52,700 MW | 100% | 13,789 MW | 174.2 GWh |
| sequential | 40,250 MW | 44% | 10,554 MW | 844.2 GWh |

*(Run over nine possible futures rather than the full 45, so these are not comparable with the headline figures; the two rows are comparable with each other.)*

The repair reaches what it was aimed at: the share of build sitting on the ceiling falls from all of it to under a half, so the economics starts deciding how much, and it is still not an improvement. Unserved energy rises nearly fivefold.

The repriced rule builds less: 40,250 MW against 52,700, which is 24 per cent less, and it ends with 10,554 MW of firm capacity against 13,789, which is 23 per cent less. Offering each producer a market that already contains the last one's plant makes the next block look less necessary, and under this rule fewer blocks clear.

The two rules are two answers to how much a market builds, and the one that sees more clearly builds less and is worse at the peak. Real investors observe each other slowly and partially, and the truth sits between the two rows above.

The honest reading is that this model brackets the annual build volume rather than determining it, and both bounds are runnable (`--scenario repriced_investment` from the command line). That is a better thing to know than either number alone, and it is more informative than either. What it is not is a defect with a fix waiting to be applied.

Two things the repair still does not do. It reprices between producers and not between the candidates of one producer, which is why over two-fifths of build still lands on the ceiling. It also costs about twice the run time, because rebuilding the forward is the expensive call in a tick.

### Why a modest gap in building is a huge gap in blackouts

Over 20 years the repriced rule ends with 23 per cent less firm capacity than the default and sheds nearly five times the energy. A gap in megawatts turning into a much larger gap in blackouts is a property of reliability rather than a quirk of the repair, and it can be measured on its own with no investment rule involved at all: scale the dispatchable fleet down and dispatch the same weather year (`tools/reliability_convexity.py`).

| firm capacity | change | unserved | times the base |
|---|---|---|---|
| 8,121 MW | - | 3.36 GWh | 1.0x |
| 7,877 MW | -3% | 6.94 GWh | 2.1x |
| 7,633 MW | -6% | 12.30 GWh | 3.7x |
| 7,390 MW | -9% | 20.76 GWh | 6.2x |
| 7,227 MW | -11% | 27.41 GWh | 8.2x |
| 6,903 MW | -15% | 47.06 GWh | 14.0x |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/reliability_curve_dark.png">
  <img alt="Unserved energy against firm capacity" src="outputs/canonical/reliability_curve.png">
</picture>

*(Firm capacity here is the dispatch's own figure. A second sum over the fleet gives about 3,000 MW more, because hydro is scheduled against its annual budget and netted out of the residual, so adding its nameplate back counts it twice. Both numbers were in these documents under the same name.)*

Take three per cent of the firm plant away and the lights go out twice as often; take 15 and it is 14 times as often. The repriced rule's 23 per cent sits past the last row, on a fleet 20 years on from the one the table scales, and the run shows 4.8 times. The direction is the table's; the size cannot be read off it, because the two are different fleets.

Nothing is broken here. Reliability lives in the worst few hours of a year, and the load in those hours is steep, so each megawatt removed exposes many more hours than the one before it. It is also the reason capacity adequacy is argued about at all: a disagreement about whether a market builds slightly too much or slightly too little is a disagreement about whether the lights stay on.

### What the bracket does to the scheme's result

Both legs always use the same rule, so each comparison is internally consistent. The comparison is not the same at the two ends, and a reader has to be told which part of it travels. Run at both ends on a reduced lattice, so these figures are not comparable with the 10-seed table above (`tools/bracket_check.py`):

| rule | merchant | with the scheme | unserved moves | resource cost | awarded |
|---|---|---|---|---|---|
| simultaneous (default) | 174.2 GWh | 29.7 GWh | -144.5 GWh | scheme costs $1.88bn | 13,900 MW |
| sequential | 844.2 GWh | 139.6 GWh | -704.6 GWh | scheme saves $8.24bn | 20,300 MW |

The reliability direction survives and is the robust half. The scheme reduces unserved energy at both ends, by a factor of about six at either.

The size of the effect does not survive, and neither does the cost verdict. At the pessimistic end the merchant market leaves nearly five times as much outage on the table, so the same scheme has far more to avoid: it costs $1.88bn of resources under the default rule and saves $8.24bn under the repriced one. The sign of the cost verdict turns on the investment rule, and no single figure should be quoted as the scheme's cost.

The verdict on a procurement scheme in this model turns on how badly you think a merchant market under-builds, which is a quantity the model brackets rather than determines. That is close to the actual policy argument.

The ceiling is shared, so whoever is asked first gets it. Producers are taken in an order that rotates with the year, which stops the same firm capturing it every time. Rotating is not an answer to who should win; it stops the order of a tuple being one.

## The lane's sanity screen does not bind

The auction screens bids against a ceiling before clearing them. settings.toml describes it as a guard against nonsense rather than a price cap, and it has never rejected anything on this fleet, which is what a guard against nonsense should do.

The two settings are in dollars per megawatt hour and a bid is per megawatt year, so the ceiling is converted over the year's hours, which is the basis a bid covers.

The dearest bid the model can construct is a plant earning nothing at all in the pool:

| technology | long-run cost per MW-year, earning nothing |
|---|---|
| eight-hour battery | $306,517 |
| wind | $282,143 |
| combined cycle gas | $203,621 |
| four-hour battery | $178,529 |
| solar | $142,163 |
| open cycle gas | $136,135 |
| two-hour battery | $107,718 |

A real bid is net of what the plant expects to earn and so lower again, well clear of the $500/MWh floor the ceiling starts from.

Where it would bind is a design question and has not been touched. Making the ceiling tight enough to reject an expensive but honest bid would change which bids clear, and choosing that level is a decision rather than a measurement.


## Cover is shared out by capacity and settled on energy

This is a simplification rather than an oversight. The design's own scope rule is that exposure, and not the shape of a producer's portfolio, carries the difference between the two legs. Splitting cover by expected energy instead of by capacity would be modelling the portfolio, which is one of the things left out on purpose. What follows is what that costs, so a reader knows the size of it.

When retailers buy swaps, the volume is split across producers in proportion to the capacity each has available. What a swap settles on is energy. Those are not the same split, and on the packaged fleet they are a long way apart:

| producer | what it owns | share of capacity | share of energy |
|---|---|---|---|
| gentailer_a | coal, gas, wind | 42.1% | 68.0% |
| gentailer_b | coal, solar | 29.6% | 24.0% |
| regional_merchant | hydro and batteries | 16.6% | 8.8% |
| merchant | peakers and pumped hydro | 11.6% | -0.8% |

The peaker owner is the clearest case. Its plant runs a couple of per cent of the year and its pumped hydro consumes more than it returns, so across a whole year it is a net consumer of energy. The allocation still hands it 11.6 per cent of every megawatt of fixed-price cover the market writes.

The evidence is then clipped away. `achieved_swap_cover` divides cover by expected output and caps the answer at one, so a producer sold forward well beyond anything it can generate reports as fully hedged rather than as impossible. Its exposure goes to the floor, its hurdle drops, and nothing anywhere says why.

Weighting the split by expected energy rather than by capacity is the obvious repair. It is not applied here, because it changes which producers carry which risk and so what every one of them builds, and that is a design decision rather than a measurement.

## Exit cannot see a contract, and entry can

Entry reads the contract book. `residual_exposure` takes the swap cover a producer has already written and the award it may hold, and lowers the hurdle accordingly.

Exit reads nothing. `going_forward_npv_per_mw` is handed the plant, the forward view, the settings and the year, and no book at all. A plant whose price is fixed for 12 years by a scheme award is tested for retirement against the spot prices that award exists to insulate it from, and can be retired on a run of years in which its actual revenue never moved.

The asymmetry is the point. The same model says a contract makes a project worth building and then forgets the contract when asking whether to keep it open. Netting the plant's in-force settlement into the going-forward test is the repair, and it is not applied here because it changes the retirement schedule, which changes everything downstream of it.

On the packaged fleet this is latent rather than active, because the exit rule never fires at all: see [the section below](#the-economic-exit-rule-never-fires-on-this-fleet). It is written down because it is a property of the rule and not of the fleet, so it becomes live the moment anybody changes the cost table, brings a retirement forward, or runs a scenario in which plant does start losing money.

## The economic exit rule never fires on this fleet

Measured over a 20-year canonical run and a 10-year one: not a single exit notice is issued. Every retirement in this model is the date written in `fleet.csv`, or the one a scenario forces.

Two separate things stop it, and they cover the whole fleet between them.

Nothing stays unviable. The worst going-forward position any plant reaches over 10 years, on the merchant leg, from `tools/exit_table.py`:

| plant | worst going-forward value, $/MW | in |
|---|---|---|
| open cycle gas | +$173,122 | 2035 |
| combined cycle gas | +$21,918 | 2030 |
| the high-cost peaking tier | +$198,923 | 2035 |
| the youngest coal | +$720,257 | 2035 |

A notice needs two consecutive negative years. Over 10 years nothing is negative even once. Over 20 the merchant leg's two incumbent open-cycle units and the peaking tier go below zero in the final year only (minus $69,800 to $69,945 per MW in 2045), the open-cycle plant it built in 2026 dips to minus $25,934 in 2039 and is back above zero the next year, and on the scheme leg the old combined-cycle unit dips to minus $48,013 in 2030 and recovers, so the rule does not fire. It is close to firing late in a run, and a fleet or a cost table a little different from this one would tip it.

The rent the test reads is booked on what each plant generated in the projection's dispatch, at the price it settled at. A coal unit keeps its must-run band running through hours priced below its running cost, and those hours count against it here as they do in the resource cost. On this fleet that lowers a coal station's measured rent by $45,000 to $49,000 per MW-year, against a going-forward fixed cost of $65,000.

A plant close to retiring cannot be measured at all. The test values a plant by looking it up in each projection year. A plant that has already retired by the nearest projection is absent from all of them, the lookup finds nothing, and the function returns zero with the comment "not measurable: never a reason to exit". The nearest projection is four years out, so any plant within four years of its scheduled retirement is structurally invisible to the exit rule, which is when a real one would be deciding whether to go early. Two of the coal stations sit in that blind spot for the whole period they are eligible.

None of this is broken. A fleet in which nothing is losing money is a legitimate answer, and forced retirement is how a boom-and-bust run is meant to be driven anyway. It has three consequences:

- the careful staggering repair described further up this file, capping notices per year and firing them worst-first, is real code that this fleet never executes;
- the tick order's "exit, then entry" does no work here, because there are no notices for entry to see; and
- if you change the fleet or the cost table, check this again before believing any claim about retirement, because the rule is closer to dormant than to tuned.

Past the last projection year the exit test reads the same terminal the build test does: the cost of new entry for the plant's technology plus the loading the market's own most cautious investor demands before entering, which is the price at which the forward's guess at everybody else's entry stops assuming more, and so what a market of these investors pays any plant of that kind in the long run. One consequence is deliberate. Against that rent a plant pays only its own operating cost, so a gas plant with about fifteen years or more left is kept whatever the near years say: the far years pay it the entrant's margin, and at the market rate they outweigh a run of empty ones. A young plant in a glut therefore never gives notice here. Coal, hydro and pumped hydro have no cost row and no entrant to price a tail on, so they read their own operating cost past the horizon, which is why the three coal stations are the plants that can fire on a poor view and the gas plants are not.

## Nobody pays for the state scheme

The state capacity target writes real contracts. A generator sells, a counterparty holds, and money settles between them every year of the contract's life, exactly as it does for a reliability-scheme award.

The difference is that nothing charges it to anyone. The levy is computed only from the reliability administrator's position and only on the scheme leg, and the state target runs on the merchant leg against a different counterparty. Measured over 20 years with the target switched on: 28 contracts written, levy $0.00/MWh in every year, administrator net $0, reported scheme cost $0.

Excluding a contract settlement from the resource cost is right, because it is a transfer and moves no real resources. Excluding it from the bill is not. The whole discipline this model teaches is to read the two cost lines together, and here is an instrument whose cost appears in neither, so a reader comparing a capacity target with a reliability lane on what they cost cannot do it.

The megawatts and the milestone are reported and are the point of the contrast; the money is not. Who should pay for a state scheme is a policy question with more than one defensible answer - consumers through a levy, as the reliability lane assumes, or taxpayers, or retailers - so nothing here has been made to charge it.

## Consumers carry the contracted plant's risk for nothing

A plant under a scheme award is financed at a blended rate, cheaper in proportion to the share of its life the contract covers, because the price risk its financiers were charging for has moved to consumers. The bid is priced on that rate and the resource cost books the plant's capital at it, so the cheaper capital counts as a real saving to the economy, which is the standard case for long-dated contracts. What consumers give up in carrying that risk is priced nowhere: they are a pass-through, and the levy moves money without anybody being charged for the uncertainty it now carries. Read the resource-cost line with that in front of it. On the canonical seed the financing saving on the awarded plant comes to $1.38bn over the run, which is the most the omission can be.

## Demand response costs nothing, and somebody is paying

The scarcity ladder is real machinery. Four tiers of customers agree to stop drawing power at rising prices, from 1 MW at $300/MWh to 364 MW at $10,000, and when a tier is called it sets the price for that hour. It supplies energy in the model's own balance identity, on the same footing as a generator.

It is paid nothing. `ladder_mw` reaches no cashflow, no cost line and no chart anywhere in the model. Measured over 10 years on the canonical seed, the ladder supplies energy the market values at $0.394bn on the merchant leg and $0.228bn on the scheme leg, and neither figure appears in anybody's accounts.

Two things follow.

The resource cost is missing a real cost. A customer who agrees to go without electricity gives something up, and the tier price is this model's own estimate of what: that is what the number in `dsr.csv` means. Leaving it out makes shedding load through the ladder free, when it is merely cheaper than the alternative.

Consumers are not charged for it. The wholesale line is the price times the energy actually delivered, rather than the whole of operational demand, which would include the megawatt hours the ladder shed. What remains is that nobody is paid for shedding: paying the ladder means deciding who pays and at what price, which is a design question rather than an arithmetic one.

Read the ladder, for now, as a price-setting mechanism rather than as a participant with a balance sheet.

## Investors' guess at what everyone else builds never settles

When an investor here works out what a project would earn, it has to assume something about how much plant everybody else will build, because a crowded market pays less. The model works that assumption out by trial: assume some entry, see which technologies would still be worth building, assume a bit more of the best of those, and repeat. One technology moves a step; when none that pays can grow, the one furthest under water gives some back; when nothing can grow and nothing is under water, the guess is at rest. What is assumed built by four years out is carried into the eight and 12-year projections, since every plant on the cost table outlives that span.

A run does not take many steps. It takes one a year, and the actual fleet changes underneath it every year, so what the investment rule reads is a half-finished calculation chasing a target that has already moved. Plant that actually gets built joins the fleet the projection is dispatched on, and a guess it has overtaken is unwound by the step, one move a year. Subtracting real plant from the guess as it is decided would leave the projection's total supply the same whatever gets built, so the projection would never register the market catching up. Measured that way on a merchant market facing certain high growth, the market talked itself out of building for a decade.

Measured against a frozen fleet, with the risk loading off, over 40 passes on the full lattice (`tools/belief_table.py`); the surplus is the most any candidate at that projection year still earns over its fixed cost, in dollars per megawatt-year:

| pass | four years | at rest | surplus | eight years | at rest | surplus | 12 years | at rest | surplus |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 1,935 MW | no | +2,272,258 | 3,839 MW | no | +4,543,569 | 5,145 MW | no | +4,526,793 |
| 10 | 3,782 MW | no | -6,389 | 7,067 MW | no | +10,714 | 5,352 MW | no | +55,268 |
| 20 | 3,565 MW | no | -5,271 | 8,485 MW | no | +4,799 | 7,883 MW | no | -20,081 |
| 30 | 3,452 MW | no | +2,398 | 9,221 MW | no | +524 | 8,615 MW | no | +28,993 |
| 40 | 3,117 MW | yes | +18,247 | 8,193 MW | no | +3,061 | 6,608 MW | no | +26,989 |

The four-year projection comes to rest at the fortieth pass. Rest means the step has nothing left it may do: every candidate that pays is settled to within one generating unit, and nothing assumed is under water. A surplus can remain at rest, because a settled candidate's last unit is the one that did not pay, and because a bracket measured while other technologies held more of the market is not re-measured when they give it back. The eight and 12-year projections are still moving at 40 passes, the 12-year surplus changing sign between passes, and nothing here says where they would stop. A 20-year run gives each projection 20 steps in total, and the fleet it is chasing moves at every one of them, so a run sees far less settling than even this. Every run writes, for each year and projection, whether the guess was at rest and the largest surplus left at it, so a guess that did not move can be read as rest or as stall.

The projection is also not held to the annual build ceiling that holds the market, so in principle it can assume plant that could not physically arrive in time. On the packaged fleet the near one does not: the ceiling allows 8,200 MW a year across all seven technologies and the four-year projection assumes 3,117 MW. The eight-year projection carries 11,309 MW in service by then, four years' ceiling at most, and the 12-year one 17,917 MW. Re-check this whenever the ceiling or the cost table moves.

Read the belief as a signal and not as an equilibrium. It is enough to make the market respond to scarcity with the right sign and the right rough size, which is what the comparison needs. It is not a statement about where free entry would land, and the megawatt figures above should not be quoted as one.

## Investors never learn which future they are in

The forward view keeps the same odds on its three demand growth paths that it started with, a third each, whatever the path the world has actually taken has been doing for 15 years. That is deliberate: the forward stays an honest distribution and no one in this model forecasts - but it means a run on the high growth path is one where investors are persistently building for a slower world than the one they are in, and the reliability outcome carries that.

It is tempting to reach for this to explain why the scheme costs more on some draws than others. It does not: that was tested and the answer is below, under what the scheme's worth depends on. Telling the forward view which path the world is on makes the scheme cheaper on a slow one and dearer on a fast one, so it moves the problem rather than removing it.

## The scheme can buy plant that would have been built anyway

A bid is what a plant still needs after the certainty equivalent of what it expects to earn in the pool. Where that comes out at zero the plant needed nothing, and the lane awards it anyway, at a strike equal to the expected price and a cost of nothing. The lane closes, the reliability standard is met on paper, and the scheme has bought something the market was going to deliver on its own.

This is the additionality problem, and it is real rather than a defect to fix. What this model does is make it visible: a zero-priced award is exactly the signature of it, and it shows up on the first tick of a run where the near anchor is short enough to make everything look profitable. It should be read as a finding rather than as capacity the scheme delivered.

## Part of the scheme's effect is reallocation, not addition

The auction runs before the investment step, which matters physically: one supply chain builds both. An award consumes annual build room that the merchant rule would otherwise have used, and the scheme leg builds much less unsubsidised plant than the merchant leg does. Counted off the fleet at the end of 20 years on the canonical seed, rather than inferred:

| | merchant | with the scheme |
|---|---|---|
| unsubsidised build | 56,800 MW | 39,200 MW |
| awarded | nil | 13,750 MW |
| new plant in total | 56,800 MW | 52,950 MW |
| the same plant as firm MW, on the table | 25,400 MW | 23,268 MW |
| of which the lane bought, on its own credit | nil | 10,285 MW |
| unserved energy | 32.6 GWh | 11.0 GWh |

So 17,600 MW of unsubsidised build makes way for 13,750 MW of awards. The scheme leg ends with 3,850 MW less plant and, on the firm-factor table, 2,132 MW less firm capacity than the merchant leg, and it sheds a third as much energy.

What the awards displace is the firm plant the merchant leg would have built: every megawatt of merchant open-cycle gas (6,400 MW) and eight-hour battery (3,800 MW), 4,500 MW of combined cycle, 3,000 MW of four-hour battery and 2,700 MW of solar, with the room going to 7,600 MW of open-cycle gas, 4,250 MW of combined cycle and 1,900 MW of eight-hour battery under contract, and 1,200 MW more wind and 1,600 MW more two-hour battery built on the market's own account. The difference is when it arrives. The merchant leg's firm capacity comes late: more than half of it, 13,585 MW on the table, is commissioned from 2040 on, after the years it was short in (2029, 2030, 2033 to 2036 and 2039), and 2,630 MW of it after the run's last year, so it serves no year the comparison counts. The scheme leg has 1,930 MW of firm capacity commissioning in 2029 against the merchant leg's 910, and 1,012 MW in 2034 against 75, which are the years the merchant leg sheds in. Within the 20 years the two legs end almost level, 22.8 GW commissioned against 23.1, and the scheme leg is ahead in every year between (`tools/arrival_figure.py`):

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/arrival_dark.png">
  <img alt="Firm capacity commissioned so far on each leg, and the energy each shed by year" src="outputs/canonical/arrival.png">
</picture>

Two firm figures appear for the scheme leg and they are not addable. The table figure counts every megawatt either leg added at the factor its technology carries in `tech_costs.csv`, awarded plant included, which is the only basis on which the two columns can be read against each other. The lane's own figure is what it contracted, measured against the shortfall it was buying for (a gas turbine at its availability, a store for as long as its energy lasts against the gap).

What the scheme buys, then, is plant contracted to stand behind a scarcity hour, arriving in the years the shortfall falls in, at the cost of the plant the market would have built later, and it is less plant in total. A static firm-capacity count records the smaller fleet and cannot see the timing, and the outcome is the one the model dispatches.

Read as a limitation, that means the annual build rate is a pacing choice rather than an economic force, and it is doing real work in the comparison, measurably so: see the ceiling table in the section on which future the market turned out to be in. Read as a result, it is the half that matters: less on the table bought a two-thirds fall in the energy shed, which is a statement about where the plant stands in the years rather than how much of it there is.

## A scheme cannot fix a year that arrives before its plant does

This is the most easily misread result in a paired run. The scheme leg is not better than the merchant leg in the first two or three years of a run, because the plant it awarded in year one has not been built yet. On the packaged fleet the first two years are identical on both legs, and the second of them, at five times the reliability standard, is the worst year the scheme leg has. That is the lead time, and it is the reason a procurement scheme is an instrument about the future rather than a response to the present.

## The levy can run either way

The administrator buys a hedge from each awarded plant and sells it on to retailers. It buys at the price the auction struck, which is the forward view's expectation for the plant's delivery years plus the uplift that carries the bid. It sells at the market price for each delivery, because nobody buys a hedge above the market.

Two things follow. What it never recovers is the uplift, which is the bid, and that is the scheme's cost. It also holds the position for as long as nobody has bought it, which is a long spot position struck on a projection. When prices come in above that projection the administrator is in pocket and the levy is a rebate; when they come in below, consumers pay.

The levy is therefore not a fee. Over a 20-year run it changes sign, and reading any one year's figure as the price of the scheme's capacity will mislead in both directions. The cost of the capacity is the bids, which `compare` reports separately.

## A lower hurdle changes what gets built, not only how much

A contract, a longer underwrite or a lower risk premium all lower the bar a project must clear. What that does to firm capacity depends on which technology clears the lowered bar first, and the technologies differ by a factor of 17 in how much firm capacity a megawatt of nameplate carries. What it does to reliability depends on when the plant arrives, which a count of firm megawatts does not record.

Measured three ways. A 10-year underwrite raises firm capacity on three of four weather seeds, by 1,965 to 3,475 MW, and lowers it on the fourth by 530 MW, while unserved energy falls on two seeds and holds on two: the seed that gains 1,965 MW of firm capacity sheds exactly what it shed before, and so does the seed that loses 530. A state capacity target leaves the market's own firm capacity unchanged to the megawatt, because the combined cycle gas it crowds in offsets on the table the storage and wind it crowds out, and still moves unserved energy through what its awards displace. The procurement scheme on the canonical seed ends with 2,132 MW less firm capacity on the table than the market alone and sheds a third as much.

Read a capacity number and a reliability number as two separate answers. In this model the first does not determine the second.

## The administrator never has a view

It offers its position back at the market price for the delivery being sold and warehouses whatever nobody buys. It does not withhold volume to hold a price up, does not read the market, and does not trade on its own account. The conduct lever offers a fire sale as the alternative, every strip at a discount to the market whoever is buying, which is the other end of the same absence of judgement. A real administrator would sit somewhere between, and where it sat would be worth money.

## When buyers and sellers negotiate, both start from the same number

The extension that makes the two sides of the contract market find each other, rather than both accepting an anchor, builds each curve by stepping away from that same anchor in equal slices. That makes them mirror images, and mirror images have a property to know before reading anything into a run made this way: the price comes back at the anchor whatever the curves are shaped like, and the volume is decided by how finely they are cut rather than by how steep they are.

The elasticity lever does work where the two sides value the block differently, which is what elasticity should mean. It does nothing where they agree. Giving the two sides genuinely different valuations would need a model of what each of them thinks the block is worth, which is a bigger thing than this extension is.

What the extension does show is real in direction and parametric in size. Assuming both sides accept the anchor buys more cover than making them find each other, and that flows straight into every producer's exposure and so into every hurdle. How much more is set by how many slices each curve is cut into, and by whether that number is odd. Three slices trade two-thirds, five trade three-fifths, and any even number trades exactly one half: with an odd count one slice sits on the anchor and crosses with its mirror, and with an even count none does. The two-fifths quoted elsewhere is five slices, and five is a setting rather than a finding. A magnitude that turns on the parity of a parameter is not a magnitude to quote at a room.

## A capacity target buys capacity, and the model will not let it buy reliability

This is a result rather than a limitation, and it is here because it is the easiest thing in the model to misread.

The reliability lane buys delivered firm megawatts, sized on the projected shortfall, and the reliability outcome moves. The state scheme buys nameplate megawatts against a number in a policy. On the packaged fleet it contracts 6,900 MW of wind and solar over 20 years; through the shared annual build ceiling the market builds 1,200 MW less wind, 5,400 MW less solar and 3,100 MW less storage of its own and 2,500 MW more combined cycle gas; the target spends $37 million over the run; and unserved energy moves from 32.6 GWh to 33.2.

That is what firm factors of a tenth and a twentieth mean, and a model that could not show it would be one in which any megawatt was as good as any other. The two instruments are not comparable in the units they are written in, and adding their megawatts together is the mistake this arrangement exists to make impossible.

Two things follow. Every milestone is missed on this fleet, from 1,600 MW awarded against 2,000 sought in 2030 to 2,000 against 4,100 in 2040, and the reason is named: nobody could build it that fast. What it buys costs a few thousand dollars a megawatt, because wind and solar already clear their own hurdles here, so the scheme is largely paying for plant the market was building anyway. Both are findings rather than defects, and both would be invisible in a model that reported only megawatts procured.

## The scheme's worth depends on which future the market turned out to be in

Ten seeds, 20 years each, both legs on each seed's own shared weather. The scheme improves reliability on seven of the 10 and worsens it on three. It lowers the total resource cost on three.

Splitting each seed's resource-cost difference into the outage the scheme avoided and everything else, since unserved energy priced at the value of lost load is one of the four terms and subtracting it leaves fuel, fixed costs and capital together:

| | across 10 seeds |
|---|---|
| outage avoided | -$0.04bn to +$0.58bn, positive on seven, negative on three |
| fuel, fixed and capital | -$5.51bn to +$1.08bn, negative on seven, positive on three |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/ten_seeds_dark.png">
  <img alt="Outage avoided and plant and fuel spent, per draw, grouped by growth path" src="outputs/canonical/ten_seeds.png">
</picture>

Each row is one seed: a paired 20-year run on one weather sequence and one growth path. The rows are numbered in the order drawn, slow growth first and the largest outage avoided first within each band; `tools/ten_seeds_figure.py` prints which seed each is. Positive is money the scheme saved.

Which of the two is larger decides the total. On six of the seven seeds where the scheme avoids outage it spends more on plant and fuel than the outage was worth, $0.97bn to $5.51bn against $0.10bn to $0.58bn, so the total goes against it. On 424242 it avoids $0.08bn of outage and spends $0.59bn less, and wins on both counts. On the three seeds where it sheds more energy than the merchant leg (20260101, 1.2 GWh to 1.7; 20301231, 12.2 to 13.4; 111, 6.8 to 8.7) it spends less on two of them and the total goes with it, and on 20260101 it spends $4.42bn more and loses on both counts. On all three the two legs are level once the build ceiling is doubled, which the sensitivity below shows; what the ceiling does to those seeds is measured there and not explained here.

On most draws, then, what the scheme buys is reliability, at a price in real resources, and whether the price is worth paying turns on the value of lost load, which is a regulatory figure here and not a measurement. On three draws it buys none, and on one of those it pays for none.

The sort is the finding, and it is monotone in growth. Taken by the demand growth path each run drew:

| path | seeds | outage avoided | awarded |
|---|---|---|---|
| low | 3 | -$0.04bn to +$0.10bn | 4,950 to 5,500 MW |
| central | 5 | -$0.02bn to +$0.25bn | 6,900 to 10,600 MW |
| high | 2 | +$0.44bn to +$0.58bn | 9,150 to 13,750 MW |

On a slow-growing system the scheme buys capacity that has almost nothing to do, and on two of the three slow draws the market alone sheds less. On a fast-growing one it avoids an outage bill worth about half a billion dollars, and on neither of the two draws does that cover what it spent. The megawatts it buys rise with the growth path, so it responds to the future it is in, and it responds to a future it only half knows.

Part of the reliability effect is the pacing parameter. The auction runs before the investment step, so an award consumes build room the merchant rule would otherwise have used. Running the same comparison at twice the annual ceiling measures how much of the difference between the legs that is, which is what `tools/ceiling_sensitivity.py` does. It takes the seeds where the scheme made reliability worse, plus the one where it helped most as a control:

| seed | esem - merchant at ceiling 2 | at ceiling 4 |
|---|---|---|
| 111 (scheme made it worse) | +1.9 GWh | 0.0 GWh |
| 20301231 (scheme made it worse) | +1.2 GWh | 0.0 GWh |
| 20260101 (scheme made it worse) | +0.5 GWh | 0.0 GWh |
| 31415926 (control, scheme helped most) | -28.5 GWh | 0.0 GWh |

Doubling the ceiling removes the whole of the scheme's effect on all four: the three seeds it harmed are level, and on the control 28.5 GWh of advantage becomes nothing. The merchant leg gains far more from the extra room than the scheme leg does, which is what to expect if a large part of what the scheme provides is permission to build sooner.

The reliability comparison is therefore substantially a statement about a pacing parameter, and four is no more correct than two: the finding is the sensitivity, not a better value. A reader who takes one number from this file should take that one, because it bounds every reliability claim above it.

What the extra room does not do is relieve the ceiling itself. At either value almost every megawatt is still built at the cap: all of both legs' build at a ceiling of two, and all of the merchant leg's and 98 per cent of the scheme leg's at four. Raising the limit raises what gets built and leaves the limit binding, which is the section on decisions that cannot see each other, measured from the other side.

### A scheme that knew which future it was in

The tempting explanation for the scheme costing more on slow-growing draws is that the lane is sized from a forward view that keeps the same odds on all three growth paths whatever the world has been doing, so a scheme that cannot learn which future it is in keeps buying for the average of them.

That can be tested without a design change. Put all the odds on the path each run actually drew, so the forward view knows what the run knows, and hold the realised weather and the realised path identical, which `tools/knowing_the_path.py` asserts rather than assumes. Caution is priced over the growth paths, so a market that knows its path would carry no premium at all and the comparison would be between a cautious market and a risk-neutral one; both arms of this experiment therefore price caution over every cell of the lattice, so that only the odds move between them. Run over nine possible futures rather than 45, so these figures are not comparable with the 10-seed table above:

| | across 10 seeds |
|---|---|
| buys less | 8 |
| resource cost improves | 5 |
| outage avoided improves | 7 |
| both improve | 2 |
| neither improves | 0 |

The negative result holds. Knowing the path makes the scheme buy less on 8 of the 10 seeds, which is what the story predicts. It does not follow through: the cost line improves on 5, the outage line on 7, and both together on 2.

Two seeds show why the intuition is unreliable. On seed 7 the scheme buys 4,450 MW less and the outage it avoids goes from -$0.89bn to +$1.25bn, which looks like the story working, except that the cost line goes from +$2.44bn to -$0.18bn: it bought less, avoided more outage, and spent more doing it. On 19990101 it buys 450 MW less and everything improves at once, which is the story working exactly as told. The same change does different things on two draws from the same model.

Whatever makes the scheme expensive on a slow path, not knowing which path it is on is not it. The question is closed, and the explanation it closes is an easy one to reach for.

## Caution is priced on the growth path, and on nothing else

A run draws its growth path once and keeps it, and draws the weather shape and the peak band afresh every year. Over a plant's life, then, only the growth path is one future; the other two are a long run of annual draws that average toward their means. The hurdle prices caution over the three growth paths, each at the mean of its weather and peak cells, and every reader of caution reads that one distribution.

What that drops is the year-to-year dispersion a life of annual draws still carries: a drought year is a bad year whether or not the next one is. Priced with the same caution, that residual would add roughly $20,000 to $30,000 per megawatt-year to a four-hour battery's hurdle. It is dropped by ruling rather than measured as zero, because the alternative, holding one weather year and one peak band for 25 years, charges for a lifetime no one in this model can have. On the packaged fleet that reading puts three-quarters of a peaker's premium and almost all of a battery's on the two axes the run redraws every year, and a four-hour battery's naked hurdle at $479,879 per megawatt-year against $179,652 on the growth path.

## What the simplification costs elsewhere

One region, so nothing locational: no interconnectors, no transmission build, no regional price divergence. Synthetic weather, so the probability of the drought year is stipulated at one in five rather than measured. A stylised fleet of about 15 rows, so no unit-level commitment, no minimum stable levels and no outage draws. The reliability standard is held flat across the whole horizon rather than stepped.

Every cost is constant over the horizon: one running cost per row, so there is no fuel price path, and one capital cost per technology, so there is no cost decline. Nothing ages, so a plant's availability and operating cost are the same in its last year as in its first. Hydro is one annual energy budget dispatched within the year, so water carries no value between years and no wet or dry inflow year enters the forward's cells. A plant the forward assumes will be built carries its technology's cost row, its availability and its weather shape, and nothing else about it. The fleet table describes the system to about 2050, when most of the remaining plant leaves at once; a run that reaches further, or starts later, prices a fleet the model has built for itself.

## What is deliberately exact

The energy balance closes to the floating-point limit in every hour of every packaged run: generation net of curtailment, plus the demand-response ladder, plus unserved energy, equals operational demand.

With one boundary, and it is reachable from the command line. Rooftop solar is a fixed 5,200 MW that is netted off demand and never curtailed, because it sits behind the meter and does not bid. Take the system peak far enough below its packaged 12,500 MW and there are hours when rooftop alone exceeds demand by more than the utility wind and solar fleet can be cut back to absorb. The surplus then has nowhere to go and is silently dropped:

| `--peak` | worst hourly imbalance | hours | energy unaccounted for |
|---|---|---|---|
| 12,500 (packaged) | 0 | 0 | 0 |
| 10,000 | 0 | 0 | 0 |
| 9,000 | 0 | 0 | 0 |
| 8,900 | 14.3 MW | 2 | 16 MWh |
| 8,500 | 255.6 MW | 8 | 1,055 MWh |
| 8,000 | 469.5 MW | 28 | 5,263 MWh |
| 7,000 | 1,082.8 MW | 369 | 77,066 MWh |

Nothing warns you. `esem-sandbox run --peak 7000` reports every shape-year inside the reliability standard with no unserved energy at all, while discarding 77 GWh that should have shown up somewhere. The guarantee above holds for the packaged system and for anything near it; it does not hold for a system small enough that its own rooftop overwhelms it, and the model does not currently say so at the point of use. Hydro delivers its stated annual budget exactly. No unit generates at a price below its own offer. These are tested, and they are the properties the model's conclusions actually rest on.
