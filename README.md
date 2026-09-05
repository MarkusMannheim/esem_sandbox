# esem-sandbox

A small electricity market model built to be understood in an hour and run in a
workshop.

It simulates one region hour by hour: plant is dispatched, and the price is set
by the last unit needed to meet demand. That much runs today. The rest of the
design, where investors decide whether to build, contracts move risk between
them, and a procurement scheme can be switched on and off, is not built yet.

It is a teaching model. Every chart it produces is illustrative, and it is not a
forecast of anything.

## Install and run

```bash
pip install esem-sandbox
esem-sandbox run
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

Early. The dispatch, pricing and reporting layer is built. Contracts, the
forward view, investment and the procurement scheme are not yet.

## Known limitations

[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) lists what this model gets wrong, with
measurements. The largest is that storage is scheduled against a price its own
schedule then moves.

## Licence

Code is [MIT](LICENSE). The small data files in `src/esem_sandbox/data/` are
not: they are derived from published sources and carry those sources' terms.
[DATA_SOURCES.md](DATA_SOURCES.md) names the source and the derivation for each,
and [NOTICE](NOTICE) carries the attributions.
