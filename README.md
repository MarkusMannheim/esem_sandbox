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

## Install and run

```bash
pip install esem-sandbox
esem-sandbox run        # dispatch and price five weather years
esem-sandbox simulate   # run the market forward, twenty years
esem-sandbox compare    # the same twenty years with and without the scheme
```

There is no solver, no licence key and no data to download. The two runtime
dependencies are numpy and matplotlib.

## What it is not

A simplified version of a larger research model, which keeps that model's
scarcity pricing, contract settlement and investment rule, and drops everything
locational: no sub-regions, no interconnectors, no transmission build. Weather
is synthetic by default. The point is the chain of cause and effect, not the
size of any number.

## Status

Everything the design describes is built: dispatch and pricing, contracts and
settlement, the forward view, the investment and exit rules, and the procurement
scheme with its auction, its recycling and its levy. What is not built is the
state scheme lane, seasonal contract volumes, and the notebook of exercises.

## Known limitations

[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) lists what this model gets wrong, with
measurements. The largest is that storage is scheduled against a price its own
schedule then moves.

## Licence

Code is [MIT](LICENSE). The small data files in `src/esem_sandbox/data/` are
not: they are derived from published sources and carry those sources' terms.
[DATA_SOURCES.md](DATA_SOURCES.md) names the source and the derivation for each,
and [NOTICE](NOTICE) carries the attributions.
