# Known limitations

Things this model gets wrong on purpose, or cannot get right in its current form.
They are listed because a teaching model that hides its own limits teaches the wrong
lesson. Each one is measured, not asserted.

## Storage: a defect this file used to describe, and what replaced it

**This section used to describe a limitation. It described the small half of one.**

Storage was scheduled by ranking prices: each unit charged in its day's cheapest
hours and discharged into its dearest. The documented cost was an inversion, about
32 per cent of discharged energy landing in an hour priced below an hour the same
store charged in, with roughly 300 MW of rated power sitting idle in load-shedding
hours. The undocumented cost was much larger. Every unit saw the same price series,
so every unit picked the same cheap hours and charged at full power in all of them,
and nothing anywhere asked whether the system could serve that load. Ten gigawatts
of four-hour batteries added to the packaged fleet lifted peak net load from
9,605 MW to 20,880 and took unserved energy from 0.005 per cent of demand to 22.8
per cent. **Storage was manufacturing the scarcity it exists to relieve**, and the
investment rule downstream then read the resulting prices as a reason to build more
of it.

Storage now shaves quantities, which is what this file already said the fix would
be and what the hydro schedule already did. A store fills the trough up to a level
and shaves the peak down to a level, with the levels set so the energy balances
across the round trip. Four properties follow from the shape of the rule rather
than from any tuning:

- **A store cannot make the peak worse.** Charging fills to a level at or below the
  discharge level, so the post-storage residual never exceeds the pre-storage peak.
  Adding storage to this fleet now lowers peak net load monotonically, from 9,300 MW
  through 8,320, 7,340 and 6,533 to a floor of 6,290 MW where the day is flat and
  more storage changes nothing.
- **A store cannot charge and discharge in the same hour.** The two levels are
  ordered, so the hours they select are disjoint. This was a defect fixed by hand in
  week one; it is now ruled out by the shape of the rule.
- **A store cannot deliver energy it never stored.** The state of charge is checked
  hour by hour inside each day, not on the day's totals: a day whose trough falls
  after its peak would otherwise let a store deliver in the evening energy it does
  not store until that night. The worst hourly excess of energy drawn over energy
  stored is zero.
- **The schedule does not depend on the price it produces.** Quantities are a
  function of the residual and the unit. The only thing price decides is whether a
  day's spread covers the round trip, and each unit judges that against the residual
  the units before it have left, never against the answer it is about to produce.

That last one removed the dispatch's whole fixed-point apparatus: the re-stack loop,
its damping, its pass ceiling and its convergence flag all existed to chase a
cobweb, and there is no longer a cobweb to chase. A dispatched year went from about
40 milliseconds to about 22.

**What it cost.** The fleet's import capability was re-tuned from 1,450 MW to
1,000 MW. With its own storage no longer making the system tighter than the fleet
warranted, every shape-year sat comfortably inside the reliability standard and
there was no contrast left to teach. The four mild shape-years now sit between a
fifth and four fifths of the standard and the lull-on-heat year at 2.3 times it.

**What is still approximate.** A store spreads its discharge across the hours above
its threshold rather than concentrating power in the single tightest hour. In the
nine load-shedding hours of the drought shape-year the fleet's stores deliver 97 per
cent of their rated power, against the roughly two thirds the ranking rule managed,
so what remains of this is small. An optimiser would still do better by moving
energy out of a merely expensive hour and into a shedding one.

## A cap contract here is almost purely a tail instrument

The ladder's two cheapest tiers are 1.0 MW at $300/MWh and 20.8 MW at $500/MWh,
transcribed as increments from the published demand-side participation table. They are
so small against a 12 GW system that any hour reaching them is short by far more, so
both are exhausted inside the same hour and the price lands on the tier above. Neither
ever sets a price.

The fleet originally stopped at gas peakers around $190/MWh, which left **no hour able
to settle anywhere between $190 and $7,500**: the price duration curve had a hole
exactly where a $300 cap contract lives. A stylised high-cost peaking tier, 500 MW at
$480/MWh, now fills it, and hours do settle in the band.

What that did not change is the cap's character. Of the $93,400 per MW-year a $300 cap
pays across the five shape-years, 99 per cent still comes from the 31 hours above
$7,500. That is not a defect. A cap is insurance against extremes and its value in the
real market is likewise concentrated in a handful of intervals. But a workshop exercise
should expect the payout to be lumpy across weather years rather than smooth: the five
shape-years pay $29,700, $49,700, $76,300, $93,800 and $208,500.

## Decisions taken against a shared forecast do not see each other

This model has three places where several decisions are taken in the same year
against one forecast, and none of them sees the others. They are the same failure
in three costumes, and it is worth naming as a family because each was found
separately and none of them looks like the others until it is.

**Entry**, in the forward view: every candidate technology answers "would I be
worth building?" about a market none of the others has entered. Letting all seven
move in one pass gave fifteen gigawatts of assumed entry on a twelve gigawatt
system. Fixed by moving one marginal entrant a tick.

**Exit**: every plant's going-forward position is evaluated against a fleet in
which none of the others has left. Fixed by capping notices per year and firing
them worst-first, so the forward reprices between cohorts.

**Investment**: every producer prices every candidate as a marginal addition to a
market that does not contain it. That is the right assumption for one small entrant and the wrong one for twelve
decisions taken in the same year against the same forward view, which is what a
tick here contains: four producers considering three candidates each, none of them
seeing the others.

This third one is NOT fixed, and that is the honest position: what stops it running
away is the annual build ceiling, which is a pacing choice rather than an economic
force. So the size of a year's build is set by the ceiling whenever the forward is
enthusiastic, and by the economics only when it is not. The
sequence still shows the boom and the bust the exercise is for - on the packaged
fleet the market builds hard for six years, stops completely in two, and starts
again - but the amplitude of the boom is a parameter, not a result.

The ceiling is shared, so whoever is asked first gets it. Producers are taken in an
order that rotates with the year, which stops the same firm capturing it every time.
Rotating is not an answer to who should win; it stops the order of a tuple being one.

## The free-entry belief is a fixed point that a run never sits at

The forward view carries a belief about how much plant somebody else builds, and
that belief is the solution to a fixed point: entry grows until no technology has a
surplus left. Reaching it takes iteration. A run does not iterate. It takes one step
a tick, and the fleet moves underneath it every tick, so what the investment step
reads is a partly converged belief chasing a target that has already moved.

Measured, against a frozen fleet and with the risk loading off, all three anchors do
settle exactly: the four year anchor at 6,496 MW, the eight at 11,519 and the twelve
at 15,510, unmoved for the last fifteen of forty passes. But the twelve year anchor
is the slow one, still shedding six per cent of itself between the fourteenth pass
and the nineteenth, and a twenty year run gives each anchor twenty steps in total
while the thing it is chasing changes at every one of them.

The projection is also not held to the annual build ceiling that holds the market,
so in principle it can assume plant that could not physically arrive in time. On the
packaged fleet it does not: the ceiling allows 8,200 MW a year across all seven
technologies, and the four year anchor assumes 6,496 MW in total. Worth re-checking
if either the ceiling or the cost table moves.

So read the belief as a signal and not as an equilibrium. It is enough to make the
market respond to scarcity with the right sign and the right rough size, which is
what the exercise needs. It is not a statement about where free entry would land,
and the megawatt figures above should not be quoted as one.

## Investors never learn which future they are in

The forward view weights its three demand growth paths at the priors it started
with, whatever the realised path has been doing for fifteen years. That is
deliberate - the design's rule is that the forward stays an honest distribution and
nobody in this model forecasts - but it means a run on the high growth path is one
where investors are persistently building for a slower world than the one they are
in, and the reliability outcome carries that.

It is tempting to reach for this to explain why the scheme costs more on some draws
than others. It does not: that was tested and the answer is below, under what the
scheme's worth depends on. Fixing the priors makes the scheme cheaper on a slow path
and dearer on a fast one, so it moves the problem rather than removing it.

## The scheme can buy plant that would have been built anyway

A bid is what a plant still needs after the certainty equivalent of what it expects
to earn in the pool. Where that comes out at zero the plant needed nothing, and the
lane awards it anyway, at a strike equal to the expected price and a cost of nothing.
The lane closes, the reliability standard is met on paper, and the scheme has bought
something the market was going to deliver on its own.

That is not a defect to fix; it is the additionality problem, and it is real. What
this model does is make it visible: a zero-priced award is exactly the signature of
it, and it shows up on the first tick of a run where the near anchor is short enough
to make everything look profitable. It should be read as a finding rather than as
capacity the scheme delivered.

## Part of the scheme's effect is reallocation, not addition

The auction runs before the investment step, which is the design's own tick order and
matters physically: one supply chain builds both. So an award consumes annual build
room that the merchant rule would otherwise have used, and the scheme leg builds
noticeably less unsubsidised plant than the merchant leg does. Over twenty years on
the packaged fleet the scheme leg awarded 11,100 MW and built 55,900 MW where the
merchant leg built 77,900 MW.

The mix moves toward firm capacity, which is what the lane is buying, and the
reliability outcome improves. But the size of the improvement is partly a
reallocation of a fixed annual build rate rather than an increase in it, and the
annual build rate is a pacing choice rather than an economic force. That makes the
DIRECTION of the comparison meaningful and its MAGNITUDE softer than it looks.

## A scheme cannot fix a year that arrives before its plant does

Worth stating because it is the most easily misread result in a paired run. The
scheme leg is not better than the merchant leg in the first two or three years of a
run, because the plant it awarded in year one has not been built yet. On the packaged
fleet the worst year of the whole horizon, at nineteen times the reliability
standard, is identical on both legs. That is the lead time, and it is the reason a
procurement scheme is an instrument about the future rather than a response to the
present.

## The administrator never has a view

It recycles at the lane anchor and warehouses whatever nobody buys. It does not
withhold volume to hold a price up, does not read the market, and does not trade on
its own account. The conduct lever offers a fire sale as the alternative, which is
the other end of the same absence of judgement. A real administrator would sit
somewhere between, and where it sat would be worth money.

## Both sides of the bid-curve market step away from the same anchor

The extension that makes the two sides of the contract market find each other,
rather than both accepting an anchor, builds each curve by stepping away from that
same anchor in equal slices. That makes them mirror images, and mirror images have a
property worth knowing before reading anything into a run made this way: the price
comes back at the anchor whatever the curves are shaped like, and the volume is
decided by how finely they are cut rather than by how steep they are.

The elasticity lever does work where the two sides value the block differently, which
is what elasticity should mean. It does nothing where they agree. Giving the two
sides genuinely different valuations would need a model of what each of them thinks
the block is worth, which is a bigger thing than this extension is.

What the extension does show is real in DIRECTION and parametric in SIZE. Assuming
both sides accept the anchor buys more cover than making them find each other, and
that flows straight into every producer's exposure and so into every hurdle. But how
much more is set by how many slices each curve is cut into, and by whether that
number is odd. Three slices trade two thirds, five trade three fifths, and any even
number trades exactly one half: with an odd count one slice sits on the anchor and
crosses with its mirror, and with an even count none does. The two fifths quoted
elsewhere is five slices, and five is a setting rather than a finding. A magnitude
that turns on the parity of a parameter is not a magnitude to quote at a room.

## A capacity target buys capacity, and the model will not let it buy reliability

This is a result rather than a limitation, and it is here because it is the easiest
thing in the model to misread.

The reliability lane buys delivered firm megawatts, sized on the projected shortfall,
and the reliability outcome moves. The state scheme buys nameplate megawatts against
a number in a policy. On the packaged fleet it adds 2,350 MW of wind and solar,
displaces 1,600 MW of merchant wind through the shared annual build ceiling, spends
about five million dollars, and changes unserved energy by nothing at all.

That is what firm factors of a tenth and a twentieth mean, and a model that could not
show it would be one in which any megawatt was as good as any other. The two
instruments are not comparable in the units they are written in, and adding their
megawatts together is the mistake this arrangement exists to make impossible.

Two things follow that are worth stating. The scheme's milestone is missed on this
fleet, and the reason is named: nobody could build it that fast. And most of what it
buys costs nothing, because wind already clears its own hurdle here, so the scheme is
paying for plant the market was building anyway. Both are findings rather than
defects, and both would be invisible in a model that reported only megawatts
procured.

## The scheme's worth depends on which future the market turned out to be in

Ten seeds, twenty years each, both legs on each seed's own shared weather. The
scheme improves reliability in eight of the ten and lowers the total resource cost
in four.

Splitting each seed's resource-cost difference into the outage the scheme avoided
and everything else - unserved energy priced at the value of lost load is one of the
four terms, so subtracting it leaves fuel, fixed costs and capital together:

| | across ten seeds |
|---|---|
| outage avoided | -$0.02bn to +$0.73bn, positive in eight |
| fuel, fixed and capital | -$4.35bn to +$2.19bn, positive in three |

The outage line is small, positive and steady. The other line is four times larger,
swings both ways, and decides the sign of the total. **Quote the outage avoided. Do
not quote the total.**

**And the swing is not random.** Sorted by the demand growth path each run drew:

- **low growth** (three seeds): resource cost worse by $2.0bn to $4.4bn every time,
  and the outage avoided is nil, between minus $0.02bn and plus $0.01bn;
- **high growth** (two seeds): resource cost better both times, and the two largest
  outage savings in the set;
- **central growth** (five seeds): two better, three worse.

So on a slow-growing system the scheme procures capacity that has nothing to do, and
on a fast-growing one it earns its keep. That is a result about the instrument rather
than about the weather, and it is the one worth taking away.

**The obvious mechanism was tested and is wrong.** The tempting explanation is that
the lane is sized from a forward view that keeps its growth priors whatever the
realised path has been doing, so a scheme that cannot learn which future it is in
keeps buying for the average of them. That can be tested without a design change:
collapse the priors onto the path each run actually drew and see what happens. On a
reduced lattice, so these figures are not comparable with the ten-seed table above:

| seed | path | | awarded | resource cost | outage avoided |
|---|---|---|---|---|---|
| 20260101 | low | priors as they are | 4,950 MW | -$2.83bn | -$0.02bn |
| | | knowing the path | 4,400 MW | -$0.08bn | +$0.00bn |
| 111 | low | priors as they are | 5,950 MW | -$2.64bn | +$0.01bn |
| | | knowing the path | 3,250 MW | +$0.47bn | +$0.09bn |
| 20260904 | high | priors as they are | 9,350 MW | -$3.26bn | +$0.67bn |
| | | knowing the path | 11,200 MW | -$7.50bn | +$0.14bn |

On the low path the explanation holds: knowing where demand is going nearly halves
what the scheme buys and turns a two-and-a-half billion dollar penalty into a gain.

**On the high path it reverses.** Knowing the path makes the scheme procure MORE,
cost MORE, and avoid LESS outage, because the market is better informed too and
builds more of the answer itself, leaving the scheme less to fix.

So the mechanism is not that the scheme cannot learn. It is that the scheme's penalty
tracks how much it procures that the market would have covered anyway, and better
information does not fix that: on a fast path it sharpens the market's own response
and makes the redundancy worse. A procurement scheme is expensive exactly where it is
least needed, and knowing more about the future moves where that is rather than
removing it.

## What the simplification costs elsewhere

One region, so nothing locational: no interconnectors, no transmission build, no
regional price divergence. Synthetic weather, so the probability of the drought year
is stipulated at one in five rather than measured. A stylised fleet of about fifteen
rows, so no unit-level commitment, no minimum stable levels and no outage draws. The
reliability standard is held flat across the whole horizon rather than stepped.

## What is deliberately exact

The energy balance closes to the floating-point limit in every hour: generation net
of curtailment, plus the demand-response ladder, plus unserved energy, equals
operational demand. Hydro delivers its stated annual budget exactly. No unit
generates at a price below its own offer. These are tested, and they are the
properties the model's conclusions actually rest on.
