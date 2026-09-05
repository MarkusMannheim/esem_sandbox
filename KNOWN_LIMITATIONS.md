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
