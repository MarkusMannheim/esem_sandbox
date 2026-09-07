# ESEM sandbox

An agent-based model of one electricity market region, in which firms that dislike
risk decide what to build. It is small enough to read in an afternoon and it runs on
numpy and matplotlib.

## What it is for

A least-cost model asks what a system should contain. It minimises the cost of
meeting demand and a reliability standard, and whatever plant is cheapest is built,
because something is assumed to build it.

This model asks who would build it. Each firm faces an income it cannot predict,
values that income below its average because it is uncertain, and commits only when
what it expects to earn covers what the plant costs to own. Nobody here is obliged to
build anything, so the answer is what a market delivers rather than what a planner
would order.

The distance between those two answers is what the argument about electricity policy
is actually about. A peaker in this model costs about $136,000 per megawatt-year to
own, and the firms want $386,000 to $425,000 before building one. About two thirds of
the bar is caution rather than cost, and a least-cost model cannot see that gap
because it has nobody in it who could be cautious.

That is also why a contract can cause plant to be built. Selling 60 per cent of the
output forward removes the uncertainty rather than paying for it, and the bar falls by
about a third. The same money handed over as a subsidy would do less.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/hesitancy_dark.png">
  <img alt="How much of the bar a plant must clear is caution rather than cost" src="outputs/canonical/hesitancy.png">
</picture>

This is a simplified, open version of a larger research model that needs a solver
licence and is not public. It reproduces how that model prices scarcity, settles
contracts and decides what to build, and drops the detail that only adds realism.
The small version exists so that the whole chain of reasoning can be read, and so
that it runs in minutes.

## The mechanism it is built around

The Electricity Services Entry Mechanism is a proposed reform to Australia's National
Electricity Market. A central body would run auctions and sign long-dated contracts
with new generators, on the argument that private contract markets do not offer terms
long enough to finance the plant the system needs. It is intended to replace the
Capacity Investment Scheme, and the arguments about it are about whether it helps,
what it costs and who ends up paying.

The model runs 20 annual steps of one region, hour by hour. The scheme can be
switched on, and the same 20 years run again beside it on the same weather.

[![Open the walkthrough in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/MarkusMannheim/esem_sandbox/blob/main/notebooks/walkthrough.ipynb)

## Install and run

```bash
pip install git+https://github.com/MarkusMannheim/esem_sandbox.git
esem-sandbox run        # dispatch and price five weather years
esem-sandbox simulate   # run the market forward, 20 years
esem-sandbox compare    # the same 20 years with and without the scheme
```

There is no solver, no licence key and no data to download. The two runtime
dependencies are numpy and matplotlib.

## What the model does

**Scarcity pricing.** In most hours the price is the running cost of the last plant
needed, which is tens of dollars. When there is not enough, the price climbs through
customers who agree to be interrupted and on to the market price cap of $20,300/MWh.
Almost all of a peaking plant's income arrives in those few hours, so it is modelled
hour by hour, all 8,760 of them, with the cumulative price threshold and the
administered cap that follow it in the real market. Plant and interruptible demand
sit in one merit order, so a customer who will stop at $300/MWh is called before a
generator offering at $480.

**Contract settlement.** Swaps and caps settle against every one of those 8,760
hours, never against an average. A cap written at $300/MWh pays on the hours above
$300 and on no others, so its value comes almost entirely from a handful of
intervals. Averaging first would price it at nearly nothing.

**The forward view, rebuilt every year.** Nobody here forecasts a price. Every year
of the run the model writes down 45 possible futures, five weather patterns by three
demand growth paths by three peak severities, each with fixed odds, and dispatches
every one of them in full at 4, 8 and 12 years ahead. That is 135 whole years of
hourly dispatch behind every investment decision, and 2,700 over a 20-year run.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/forward_view_dark.png">
  <img alt="45 futures priced at three distances, and what they pay a peaker" src="outputs/canonical/forward_view.png">
</picture>

What comes out is a spread rather than a number: what a megawatt of each technology
would earn in each of those futures. The investment rule works on the spread.

**The investment rule.** A plant is built when what it expects to earn, per megawatt
per year, covers what it costs to own, per megawatt per year. Both sides are on that
same basis, so no assumption about how often a plant runs enters the comparison. The
investor is cautious rather than neutral: it values an uncertain income at less than
its average, by an amount that shrinks as more of the plant's output is sold forward.

**What the scheme writes.** An award is the contract the plant could actually back.
Plant that can stand behind a scarcity hour writes a cap on its firm megawatts;
wind, solar and storage write swaps on the blocks they generate in. The administrator
holds those positions and offers them back to retailers at the market price for each
delivery, because nobody buys a hedge above the market. What it never recovers is the
uplift that carried the bid, so the levy measures the cost of the capacity rather than
the gap between two price bases.

## What it leaves out, and what that costs

| | in this model | what that means you cannot ask |
|---|---|---|
| Geography | one region, no interconnectors | anything about where plant sits, or what transmission would unlock |
| Weather | five synthetic years from a fixed seed | anything about a particular historical year |
| Plant | about 16 stylised rows | anything about a named station |
| Dispatch | plants stacked cheapest first, hour by hour | anything needing a unit's start-up costs or minimum run times |
| Storage | fills the day's trough and shaves its peak, on quantities | anything about storage bidding strategically |
| Uncertainty | 45 possible worlds, at odds that never move | anything about investors changing their minds as evidence arrives |

Because of that list it runs on numpy and matplotlib, and a 20-year paired comparison
takes minutes rather than hours.

What is not built is seasonal contract volumes and a browser build.

## What it brackets rather than settles

How much a market builds depends on whether investors can see each other, and the
model has two rules that differ in nothing else. Under one, nobody observes anybody
and everyone builds to the annual limit. Under the other, everyone observes everyone
instantly, so the first decision of a year removes the scarcity rent the rest were
counting on. Real investors are neither. The two rules bracket the amount built, the
bracket is wide, and this is the reason capacity adequacy is argued about.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/reliability_curve_dark.png">
  <img alt="Unserved energy against firm capacity" src="outputs/canonical/reliability_curve.png">
</picture>

Take a few per cent of firm plant away and blackouts multiply, so a small
disagreement about what to build becomes a large one about whether the lights stay
on.

A second bracket sits underneath every reliability figure here. The model paces
construction with an annual limit on how many projects of one technology can start at
once, and that limit is a choice rather than a measurement. Doubling it removes the
procurement scheme's whole reliability advantage on every seed tested. Neither value
is more correct than the other, which is why the sensitivity is reported rather than
a preferred number.

Read the chain of cause and effect rather than the size of any number. Every figure
here is illustrative.

Every number and chart on this page is produced by something you can run.
`tools/doc_figures.py` draws the charts, and
[outputs/canonical/README.md](outputs/canonical/README.md) lists the commands behind
the rest.

## Reading it

[ARCHITECTURE.md](ARCHITECTURE.md) is the map: what each piece does, what a year
looks like, and where to start reading.

[GLOSSARY.md](GLOSSARY.md) explains the terms, for a reader who knows the NEM but
does not build models.

[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) lists what this model gets wrong, with
the measurement behind each entry.

[notebooks/walkthrough.ipynb](notebooks/walkthrough.ipynb) runs the model end to end
and can be opened in Colab.

## Licence

Code is [MIT](LICENSE). The small data files in `src/esem_sandbox/data/` are
not: they are derived from published sources and carry those sources' terms.
[DATA_SOURCES.md](DATA_SOURCES.md) names the source and the derivation for each,
and [NOTICE](NOTICE) carries the attributions.
