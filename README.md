# esem-sandbox

A small electricity market model built to be understood in an hour and run in a
workshop.

It simulates one region hour by hour: plant is dispatched, and the price is set
by the last unit needed to meet demand. Over twenty annual steps, contracts move
risk between the firms in it and investors decide what to build, against a view
of the future they extrapolate rather than forecast. A procurement scheme can be
switched on, and the same twenty years run again beside it on the same weather.

It is a teaching model. Every chart it produces is illustrative, and it is not a
forecast of anything.

[![Open the exercises in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/MarkusMannheim/esem_sandbox/blob/main/notebooks/exercises.ipynb)

## Install and run

```bash
pip install esem-sandbox
esem-sandbox run        # dispatch and price five weather years
esem-sandbox simulate   # run the market forward, twenty years
esem-sandbox compare    # the same twenty years with and without the scheme
```

There is no solver, no licence key and no data to download. The two runtime
dependencies are numpy and matplotlib.

## The exercises

[notebooks/exercises.ipynb](notebooks/exercises.ipynb) is three exercises of about
ten minutes each. Each says what should move and what should not, so a reader can
tell a result from a hope.

1. **The same weather, with and without the scheme.** What it buys, what it costs,
   and why the first years of a run are identical however much it bought.
2. **The decomposition dial.** Three switches, so the effect can be split between
   the risk a contract removes, the capital it cheapens, and the plant it buys.
   With all three off the two legs coincide exactly.
3. **Why the hourly series.** What averaging does to a cap payout, the worst week
   with the stores draining, and what the batteries actually delivered in the hours
   load was shed.

## Scenarios

[src/esem_sandbox/scenarios/](src/esem_sandbox/scenarios/) holds the runs the
exercises use. Each is a small file naming a leg, a horizon and anything it changes.
They ship inside the package, so they can be named rather than found:

```bash
esem-sandbox simulate --scenario early_coal_exit
esem-sandbox compare  --scenario short_tenor
esem-sandbox simulate --scenario my_own_file.toml
```

A scenario can close a plant early, shorten the scheme's contracts, change what the
administrator does with volume nobody buys, run a state capacity target beside the
market, or make the contract market clear by crossing curves instead of at an
anchor. Anything it names wrongly fails loudly rather than falling back to a
default.

## What it is not

A simplified version of a larger research model, which keeps that model's
scarcity pricing, contract settlement and investment rule, and drops everything
locational: no sub-regions, no interconnectors, no transmission build. Weather
is synthetic by default. The point is the chain of cause and effect, not the
size of any number.

## Status

Everything the design describes is built: dispatch and pricing, contracts and
settlement, the forward view, the investment and exit rules, the procurement scheme
with its auction, recycling and levy, a state scheme beside it, and the bid-curve
market as an alternative to clearing at an anchor. What is not built is seasonal
contract volumes and a browser build.

## How it works

[ARCHITECTURE.md](ARCHITECTURE.md) is the map: what each piece does, what a year
looks like, and where to start reading.

## Known limitations

[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) lists what this model gets wrong, with
measurements rather than assertions, and records what it used to get wrong and no
longer does. The one most easily misread is not a limitation at all: a capacity
target buys capacity and does not buy reliability, and the model will not let the
two be added together.

## Licence

Code is [MIT](LICENSE). The small data files in `src/esem_sandbox/data/` are
not: they are derived from published sources and carry those sources' terms.
[DATA_SOURCES.md](DATA_SOURCES.md) names the source and the derivation for each,
and [NOTICE](NOTICE) carries the attributions.
