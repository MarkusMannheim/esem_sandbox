# The words this model uses

Every term is defined in plain language, in the order a reader meets it rather
than alphabetically. Nothing on this page assumes you have worked in electricity.

If you read one entry, read **the bill and the resource cost**. Confusing those
two is the easiest way to reach a wrong conclusion from this model.

## Keeping the lights on

**Demand.** How much electricity people want in a given hour. It moves with the
weather and the time of day, and the model tracks it hour by hour for a whole
year: 8,760 hours.

**Dispatch.** Deciding which power stations run in each hour. Cheapest first,
until demand is met.

**Merit order.** That cheapest-first ordering. A plant's place in it is set by
what it costs to produce one more unit, not by what it cost to build.

**The price.** In each hour, what the last plant needed to meet demand asked for.
Everybody who ran that hour is paid it, including the plants that would have
accepted less. That is how the real market works, and it is why a few tight hours
matter so much.

**Unserved energy.** Demand that could not be met at all, because there was not
enough plant. It is this model's measure of blackouts.

**The reliability standard.** The most unserved energy considered acceptable. The
standard in force is 0.002 per cent of the year's demand; this model uses 0.003 per
cent, the figure the Reliability Panel recommended for 2028 onward, across the whole
horizon rather than stepping it partway. Results are quoted as a multiple of it, so
"twice the standard" means twice as much unserved energy as the rule allows.

**Firm capacity.** Capacity you can count on at the moment demand peaks. A gas
plant is close to fully firm. A wind farm is not, because the peak may fall on a
still evening.

**Nameplate capacity.** What a plant is rated at, whether or not it can be relied
on when it matters. A gigawatt of solar and a gigawatt of gas are the same
nameplate and very different firm capacity, which is why the two must never be
added together.

**Availability.** The share of the year a plant is not broken or in maintenance.

**Capacity factor.** The share of the year a plant actually produces. A gas
peaker might run two per cent of the year and a wind farm 35.

**Capture price.** The average price a plant is actually paid, which depends on when
it runs. Solar runs in the middle of the day when prices are lowest, so it captures
less than the yearly average; a peaker runs only when prices are high, so it captures
far more. Two plants in the same region can face the same prices and earn very
different amounts per megawatt hour.

**Curtailment.** Generation that was available and deliberately not taken,
usually because there was already more than enough.

**Demand response.** Customers who agree to stop drawing power when the price gets
high enough. The model holds a short list of them at rising prices and puts them in
the same merit order as the generators, so a customer who will stop at $300/MWh is
called before a plant offering at $480. Some demand switches itself off before anybody
is cut off involuntarily.

**Round trip.** The energy a battery or pumped hydro loses between storing power
and giving it back. Here about 15 per cent.

**Residual.** What is left for the rest of the fleet to meet once the sources that
cost nothing to run have been counted: demand, less rooftop solar, less wind and
large-scale solar. It is the quantity everything else is dispatched against, and the
first command prints its peak.

**Water value.** What a hydro station charges for a megawatt hour, given that its
water is limited. It is not a fuel cost. Water spent tonight is water not available
in the worst hour of the year, so the station prices it at what it expects to give
up by using it now.

**Administered pricing.** A safety valve. If the total of prices over the past week
climbs past a published threshold, the market operator caps prices at a much lower
figure until the total falls back. It is a real feature of the market, meant to stop
a sustained crisis transferring unlimited amounts of money, and it releases on its
own once the week's running total drops.

**Calibration.** A short report the first command prints: average price, how often
prices reach $300, hours at the cap, unserved energy. It is reported rather than
tuned, meaning nothing was adjusted to make those numbers come out. It is there so
you can judge whether the stylised system behaves like a plausible one before you
believe anything downstream of it.

**Shape year.** One synthetic year of weather and demand pattern. The model has
five, and one is a hot year with little wind. That is the year that causes
trouble.

**Lead time.** The years between deciding to build something and it producing
power. Two years for a gas peaker, longer for most else. It is the reason a
scheme cannot fix the year it is announced in.

## Money

**The bill.** What electricity costs the people who use it: the wholesale cost of
the energy they were actually delivered, plus any scheme charge, plus the value of
the energy they wanted and did not get. Nobody invoices that last term. It is counted
so that a leg which keeps the lights off cannot look cheap.
Most of the rest is money moving from consumers to generators.

**The resource cost.** What the whole thing costs the economy: fuel, the fixed
cost of keeping plant open, the capital spent on new plant, and the value of the
energy nobody got. This is the real cost.

**Transfer.** Money moving between two parties without anything being consumed or
saved. Most of the difference between the two lines above is transfer. **A policy
that pushes the price down cuts the bill enormously and may not save a cent**,
which is why this model always reports both lines and never one.

**Value of lost load.** The dollar figure put on electricity that could not be
supplied, so that a blackout can be compared with the cost of avoiding one. It is a
regulatory number rather than a measurement. Here it is the market price cap,
$20,300/MWh, which is the same convention the market itself uses.

**Fixed cost.** What a plant costs each year whether or not it runs: repayments
on what it cost to build, plus staff and maintenance. Quoted per megawatt of
capacity per year, so that plants running for very different shares of the year
can be compared without first assuming how often each will run.

**Running cost.** What it costs a plant to produce one more megawatt hour, mostly
fuel. It sets the plant's place in the merit order.

**Rent.** What a plant earns above its running cost. It is not profit, because rent
still has to cover the fixed cost before the plant is worth having.

**Basis.** The gap between two prices for the same thing, measured different ways. It
matters here because the scheme buys cover at one price and sells the identical
position at another, and the difference between those two ways of measuring is most of
what the scheme appears to cost.

**Cost of capital.** The return a project has to earn to be worth financing. A
contracted project can borrow more cheaply than an uncontracted one, and that is one
of the three channels through which a scheme reaches the market. The code calls it
WACC, for weighted average cost of capital.

**Present value.** A stream of future money expressed as one number today, by
discounting each year at the cost of capital. Money later is worth less than money
now, and a plant's whole case is a stream of future money. The code calls it NPV, for
net present value.

## Contracts

**Spot price.** The hour-by-hour price described above, also called the pool
price. Nobody has to live on it, because they can contract.

**Swap.** A contract fixing the price for an agreed amount of output over an
agreed stretch of the day. If the spot price comes in higher the seller pays the
difference back, and if lower the buyer tops it up. Either way both sides end up
at the fixed price, which is the point.

**Cap.** Insurance. The seller pays the buyer whenever the spot price rises above
an agreed level, and keeps the fee otherwise. A cap does nothing in an ordinary
hour and everything in a crisis.

**Strike.** The agreed price a swap fixes at, or the level a cap pays out above.

**Tenor.** How many years a contract runs for.

**Tranche.** One delivery year of a contract, offered on its own. A scheme that has
bought cover for 2030 through 2041 can sell the 2030 year separately from the 2031
year, and each of those is a tranche.

**Block.** A stretch of the day contracts are written over. This model uses four:
overnight, morning, the solar middle of the day, and the evening peak.

**Lane.** One thing being traded, so buyers and sellers of the same thing meet in
the same place. There is one lane per block for swaps, plus one for caps.

**The clearing price.** What a lane settles at. Each lane here has a reference
price: for a swap, what that block has recently been worth; for a cap, what it
costs to stand ready plus a charge for carrying the risk. An optional extension
makes the two sides find a price between them instead.

**Exposure.** The share of a project's life still facing the spot price rather
than a fixed contract price. A fully contracted project has an exposure of zero.

## Deciding what to build

**The forward view.** What investors think the future looks like. It is a list of
possible futures with fixed odds on each, and the model works out what a plant would
earn in every one of them. Nobody here forecasts.

**Cell.** One of those possible futures: one weather pattern, one demand growth
path, one peak severity. There are 45.

**The odds on each future.** Every cell carries a fixed probability, and they add to
one. This model sets them at the start and never moves them: after 15 years of
fast growth, investors here still think slow growth is exactly as likely as they
thought at the beginning. That is deliberate, because nobody in this model forecasts,
and it costs something. Statistics calls a probability set before seeing any evidence
a **prior**, and the code and the older notes use that word.

**The lattice.** All 45 of them together, with their odds. Some runs use
a smaller set of nine so a run finishes quickly; totals from a reduced lattice are
not comparable with the full one, and anything using one says so.

**Free entry.** The idea that if something is profitable to build, somebody keeps
building it until it no longer is. The forward view chases that point
without ever arriving: see **assumed entry** above, and note that the model treats
the answer as a signal rather than a settled number.

**Projection years.** The model prices the future at three distances, four,
eight and 12 years out, and fills in between them. Four years is far enough
that a plant decided today is running, and 12 catches most of its life.

*(The code and the working notes call these "anchors", and also use "anchor" for a
contract lane's reference price. They are two different things, and this page
avoids the word for both.)*

**Assumed entry.** How much plant investors assume everybody else will build. It
matters because a project is worth less in a crowded market, and it is how a
market can talk itself out of building as well as into it.

**Hurdle.** What a project must earn each year, per megawatt, to be worth
building: its fixed cost, plus whatever the uncertainty costs the investor. A
contract lowers the hurdle by removing uncertainty, and that is the channel almost
every policy in this model works through.

**Certainty equivalent.** The guaranteed sum an investor would swap an uncertain
one for. Somebody offered an even chance of nothing or two million usually prefers
a sure eight hundred thousand to a sure million, and the certainty equivalent is
that number. The gap between it and the plain average is the price of the risk,
and it is what a contract buys away.

**Risk aversion.** How strongly an investor prefers a sure thing. The model gives
its six firms different amounts of it, and that is most of what separates them.

**CARA.** The particular shape of caution used, short for constant absolute risk
aversion: an investor's appetite for a gamble does not change with how rich it
already is. One function builds it for the whole model, so a firm writing insurance
against a bad hour and a firm building the plant that would relieve that hour are
pricing the same risk the same way. If they did not, the model would invent trades
out of its own inconsistency.

**Build ceiling.** The most of any one technology that can be built in a single
year, standing in for supply chains and construction crews. **Read it carefully:
it is a pacing choice rather than an economic force, and in this model it decides
how much gets built in every year that anything does.**

**Exit.** A plant closing because it no longer covers the cost of staying open.
What it cost to build is already spent and does not enter the decision.

## The procurement scheme

**ESEM.** The Electricity Services Entry Mechanism, a proposed reform to Australia's
National Electricity Market under which a central body runs auctions and signs
long-dated contracts with new generators. It is what this model calls the procurement
scheme, and it is the thing the model exists to put numbers on.

**The two legs.** Every comparison runs twice on identical weather: once with no
scheme at all, and once with the scheme switched on. The no-scheme leg is called
**merchant**. Using the same weather for both is what makes the difference between
them attributable to the scheme rather than to luck.

**What the scheme buys.** Delivered firm megawatts, through an auction, sized on how
far short of the reliability standard the system is projected to fall. What it signs is
the contract the plant can stand behind: a cap for plant that can cover a scarcity
hour, and swaps on the blocks it generates in for everything else.

**Award at final investment decision.** The scheme pays only when a plant actually
commits to being built, rather than paying for a promise.

**Bid.** What a plant still needs on top of what it expects to earn in the market.
A plant that needs nothing bids zero, and the scheme awards it anyway.

**Additionality.** Whether a scheme caused something to happen, or paid for
something that was going to happen regardless. A zero bid is the signature of the
second, and this model shows them rather than hiding them.

**Recycling.** The administrator selling the cover it has bought back to retailers,
so consumers get the benefit of what they funded. It sells at the market price for the
delivery being sold, because nobody buys a hedge above the market. What it does not
recover is the amount the award added on top of that price, which is the bid.

**Warehousing.** Holding on to cover nobody bought, rather than dumping it.

**Counterparty.** The other side of a contract. Every contract here has exactly two
parties and moves money between them without creating any, which is a property the
model tests rather than assumes.

**Levy.** The charge on consumers that balances the administrator's books, collected
in the same year the money moved. It can go either way: the administrator holds hedges
struck on a projection years ahead and sells them at the market price for each
delivery, so consumers pay when prices come in below the projection and are paid when
they come in above it.

**Capacity target.** A different kind of scheme, buying a number of nameplate
megawatts named in a policy. It is here as a contrast: it buys capacity and it
does not buy reliability, and the units it is written in make that impossible to
miss.

## Reading results

**Duration curve.** The year's prices sorted from highest to lowest instead of
left in time order. It shows how concentrated the money is: a handful of hours
carries most of it.

**The worst window.** The worst run of consecutive days in the year. The model
finds it rather than being told where it is.

**Seed.** The number fixing which weather and which growth path a run draws. Same
seed, same run, every time. **A result that changes when the seed changes is a
property of that draw and not of the model**, which is why conclusions here are
quoted across 10 seeds rather than one.
