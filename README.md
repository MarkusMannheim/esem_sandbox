# ESEM sandbox

An agent-based model of one electricity market region, in which firms that dislike risk decide what to build. It is small enough to execute and analyse results in a very short period. It runs on numpy and matplotlib.

## What this model is for

A least-cost model asks what an electricity system should contain. It minimises the cost of meeting demand and a reliability standard, and whatever plant is cheapest is built, because something is assumed to build it.

This model asks who would build it. Each firm faces an income it cannot predict, values that income below its average because it is uncertain, and commits to an investment only when what it expects to earn covers what the plant costs to own. No one is obliged to build anything, so the answer is what a market delivers rather than what a central planner would order.

The distance between those two answers is what the argument about electricity policy is really about. A gas peaker in this model costs about $136,000 per megawatt-year to own, and the firms want $332,000 to $358,000 before building one. About three-fifths of the bar is caution rather than cost, and a least-cost model cannot see that gap because no one in it is cautious.

That is also why a contract can cause plant to be built. A 12-year contract on all of a plant's output removes uncertainty rather than paying for it, and the bar falls by about a sixth; the three-year swaps that retailers buy on their own account move it by a few per cent. The same money handed over as a subsidy would do less.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/hesitancy_dark.png">
  <img alt="How much of the bar a plant must clear is caution rather than cost" src="outputs/canonical/hesitancy.png">
</picture>

This is a simplified, open version of a larger research model that needs a solver licence for efficiency and is not yet public. It reproduces how that model prices scarcity, settles contracts and decides what to build, and excludes details that add realism but are not essential. The small version exists so the chain of reasoning can be read and explored, and so that it runs in minutes.

## The mechanism it is built around

The Electricity Services Entry Mechanism (ESEM) is a proposed reform to Australia's National Electricity Market. A central body would run auctions and sign long-dated contracts with new generators, on the argument that private contract markets do not offer terms long enough to finance the plant the system needs. It is intended to replace the Capacity Investment Scheme. Policy considerations around the ESEM are about whether it helps, what it costs and who ends up paying.

The model runs 20 annual steps of one region, hour by hour. The scheme can be switched on, and the same 20 years run again beside it on the same weather.

[![Open the walkthrough in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/MarkusMannheim/esem_sandbox/blob/main/notebooks/walkthrough.ipynb)

## Install and run

```bash
pip install git+https://github.com/MarkusMannheim/esem_sandbox.git
esem-sandbox run        # dispatch and price five weather years
esem-sandbox simulate   # run the market forward, 20 years
esem-sandbox compare    # the same 20 years with and without the scheme
esem-sandbox sweep investment.risk_premium 0 0.25 0.5   # one setting at several values, both legs each time
```

There is no solver, no licence key and no data to download. The two runtime dependencies are numpy and matplotlib. Any setting can be changed for one run with `--set section.key=value`, and `--quick` trades the forward view's 45 futures for 18 so a comparison takes seconds; [PARAMETERS.md](PARAMETERS.md) lists every setting, what it does and what it moves.

## How it works

Every hour, the plant available is stacked cheapest first and the price is the offer of the last unit needed; when there is not enough plant the price climbs through the demand-response rungs to the market price cap, so almost all of a peaker's income arrives in a handful of hours. Swaps and caps settle against those hours, and how much cover gets traded comes from inside the model: two retailers hedge to a mandate, four producers write what they have, and what a plant has sold forward is the cover that lowers its own bar. Every year the model dispatches 45 possible futures at three distances and hands each firm a spread of what a megawatt would earn. A firm builds when the certain sum it would swap that spread for covers what the plant costs to own, and the gap between the two is caution; a contract lowers the bar by removing the uncertainty, which is the channel every policy here works through. The scheme sizes what it buys on the projected shortfall against the reliability standard, pays a plant the top-up it bids, awards at final investment decision, sells the cover back to retailers at the market price and charges consumers the rest.

[HOW_IT_WORKS.md](HOW_IT_WORKS.md) follows one year through those steps, with the figures, what to look at in a run and which setting moves each one.

## What the model leaves out, and the costs

| | in this model | what cannot be analysed |
|---|---|---|
| Geography | one region, no interconnectors | anything about where plant sits, or what transmission would unlock |
| Weather | five synthetic years from a fixed seed | anything about a particular historical year |
| Plant | about 16 stylised rows | anything about a named station |
| Dispatch | plants stacked cheapest first, hour by hour | anything needing a unit's start-up costs or minimum run times |
| Storage | fills the day's trough and shaves its peak, on quantities | anything about storage bidding strategically |
| Uncertainty | 45 possible worlds, at odds that never move | anything about investors changing their minds as evidence arrives |

Because of the above list, the model runs on numpy and matplotlib, and a 20-year paired comparison takes minutes rather than days.

Two things are planned and not built: contract volumes that vary by season, and a version that runs in a web browser without installing anything.

## What one run shows, and what it does not

Some quantities the model can only bracket. How much a market builds depends on whether investors can see each other's decisions, and the model's two rules for that differ in nothing else and bracket the amount built; the bracket is wide because reliability is not proportional to capacity, so a small disagreement about what to build becomes a large one about whether the lights stay on. A build ceiling paces construction, and doubling it removes the scheme's whole reliability advantage on every seed tested, so the sensitivity is reported rather than a preferred number.

The scheme's own worth depends on the future the market turns out to be in. Every run draws its weather and its demand growth path from a seed, so one run is one draw. Ten draws of the same comparison show the scheme buying reliability on eight of them and paying for it in real resources on all but one of those, while on two draws the market alone sheds less. Each row below is one draw. It splits the scheme's effect on the total resource cost into the outage it avoided, valued at the price cap, and what it saved or spent on plant and fuel; the diamond is the two together.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="outputs/canonical/ten_seeds_dark.png">
  <img alt="Outage avoided and plant and fuel spent, per weather draw, grouped by growth path" src="outputs/canonical/ten_seeds.png">
</picture>

Read the chain of cause and effect rather than the size of any number. Every figure here is illustrative.

Every number and chart on this page is produced by something you can run. `tools/doc_figures.py` and `tools/ten_seeds_figure.py` draw the charts, and [outputs/canonical/README.md](outputs/canonical/README.md) lists the commands behind the rest.

## Reading it

[HOW_IT_WORKS.md](HOW_IT_WORKS.md) follows one year of the model step by step, with what to look at and what moves it.

[ARCHITECTURE.md](ARCHITECTURE.md) is the map: what each piece does, what a year looks like, and where to start reading.

[PARAMETERS.md](PARAMETERS.md) lists every setting a reader can change, and how.

[GLOSSARY.md](GLOSSARY.md) explains the terms.

[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) says what the model leaves out, what it gets wrong, and which of its results are easy to misread.

[notebooks/walkthrough.ipynb](notebooks/walkthrough.ipynb) runs the model end to end and can be opened in Colab.

## Licence

Code is [MIT](LICENCE). The small data files in `src/esem_sandbox/data/` are not: they are derived from published sources and carry those sources' terms. [DATA_SOURCES.md](DATA_SOURCES.md) names the source, the derivation and the attribution for each.
