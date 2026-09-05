# Data sources and licensing

Code is MIT. The files in `src/esem_sandbox/data/` are not: they are stylised
figures derived from published sources, provided under those sources' terms.

Nothing here reproduces a source dataset. Every table is aggregated, rounded or
invented to sit inside a published range, and every row carries a `derivation`
column saying what it came from. The weather is synthetic, generated from a seed
at runtime, so no source trace data ships in this repository at all.

The fleet is a **stylised system of about the size of New South Wales**. It is
not the New South Wales fleet: plant labels are generic, capacities are rounded,
and no row corresponds to a real station's full set of parameters. Every chart
the model produces says so.

## Dollar basis

**All money in this repository is in real 2025-26 Australian dollars**, the year the
market price settings below apply to. Capital and operating costs are rounded into
that basis; no figure is indexed within a run, and the model does not inflate.

This matters more than it looks. The market price cap and the cumulative price
threshold are indexed together each year and published as a pair, and it is their
*ratio* that decides when the market is suspended. Mixing a cap from one year with a
threshold from another silently changes the model's rules rather than just its price
level. The pair here is the one applying from 1 July 2025.

## Permissions relied on

### AEMO

AEMO's copyright permissions are understood to grant a general permission to use
AEMO material for any purpose, with accurate and appropriate attribution of the
material and of AEMO as its author.

> **Not yet transcribed.** The permission page
> (<https://www.aemo.com.au/privacy-and-legal-notices/copyright-permissions>)
> refuses automated retrieval, so the sentence above is a summary corroborated
> from secondary sources, not a verbatim reading. Before anyone relies on this
> file, the clause should be read from the page and quoted here, and checked for
> carve-outs covering logos, trade marks, third-party material and implied
> endorsement.

### CSIRO GenCost

GenCost project data is understood to be released under Creative Commons
Attribution 4.0 International.

> **Not yet transcribed.** The CSIRO collection page also refuses automated
> retrieval. The licence and version shown for the release actually used should
> be confirmed and its attribution statement quoted here.

### AEMC

The market price cap, the cumulative price threshold, the administered price cap
and the reliability standard are set by instrument and are cited by figure in
`settings.toml`, not redistributed. The cap and threshold are the pair applying from
1 July 2025 ($20,300/MWh and $1,823,600/MWh) from the AEMC's schedule of reliability
settings for the 2026-27 financial year, published 27 February 2026. The threshold is
published as a sum of five-minute trading interval prices; this model settles hourly
and divides it by twelve accordingly. The standard is period-dependent: 0.002 per
cent of unserved energy. The Reliability Panel's 2026 Reliability Standard and
Settings Review final report of 23 April 2026 recommends 0.003 per cent for the
period 1 July 2028 to 30 June 2032. This model holds the in-force figure for a
whole run rather than stepping it.

## The files

| File | Contents | Derivation |
|---|---|---|
| `fleet.csv` | Fifteen rows: thermal, hydro, storage, wind, solar, rooftop and one import link | Aggregated to technology from public AEMO generation information and IASR retirement years. Generic labels, rounded capacities. Availability factors are IASR figures by technology. The hydro energy budget and the import link's coincidence derate are illustrative and are documented parameters, not published values |
| `tech_costs.csv` | Entrant capital and operating costs, WACC, lead time, life, unit size, availability, firm factor | Rounded figures lying inside the published GenCost and IASR ranges, never the published point estimates |
| `dsr.csv` | Four demand-response tiers with prices and call-hour budgets | The IASR demand-side participation table for New South Wales, transcribed as **increments** by differencing the published cumulative bands. A test checks the tiers increase with price and that their sum stays in the range an increment basis implies |
| `growth.csv` | Three demand growth paths and their weights | Stylised around the IASR trajectories; stated as stylised wherever it is used |
| `settings.toml` | Market price cap, thresholds, blocks, reliability standard, weather seed | AEMC reliability settings and model parameters, each key carrying its source in a comment |

## Rules for changing anything here

1. A new file needs a row in the table above and a `derivation` column.
2. Public sources only. No unpublished modelling and no third-party material.
3. If a real trace bundle is ever added, the two clauses above must be
   transcribed first, and synthetic weather stays the default regardless.
