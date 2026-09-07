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

AEMO's copyright permissions page grants a general permission to use AEMO material
for any purpose, with accurate and appropriate attribution of the material and of
AEMO as its author. As reported by two independent search indexes, the page reads:

> AEMO Material comprises documents, reports, sound and video recordings and any
> other material created by or on behalf of AEMO and made publicly available by
> AEMO. All AEMO Material is protected by copyright under Australian law.
>
> AEMO confirms its general permission for anyone to use AEMO Material for any
> purpose, but only with accurate and appropriate attribution of the relevant AEMO
> Material and AEMO as its author. You do not need to obtain specific permission to
> use AEMO Material in this way.

AEMO's own publications point at that page rather than restating it. The WEM market
design summary, for instance, carries only: "© 2023 Australian Energy Market Operator
Limited. The material in this publication may be used in accordance with the
copyright permissions on AEMO's website."

The permission text above is quoted from AEMO's copyright permissions page
(<https://www.aemo.com.au/privacy-and-legal-notices/copyright-permissions>), read
through the Internet Archive's capture of 29 July 2026. The page states one
exclusion: confidential documents, and reports commissioned by another party who may
own the copyright, are not AEMO Material and the permission does not reach them.
Nothing this repository uses falls into either.

### CSIRO GenCost

**The GenCost report is not open-licensed**, and the cost ranges used here come from
the report. Its copyright page reads, verbatim, from the published PDF:

> © Commonwealth Scientific and Industrial Research Organisation 2024. To the extent
> permitted by law, all rights are reserved and no part of this publication covered
> by copyright may be reproduced or copied in any form or by any means except with
> the written permission of CSIRO.

The report's own citation form is:

> Graham, P., Hayward, J. and Foster J. 2024, GenCost 2024-25: Consultation draft,
> CSIRO, Australia.

Nothing in this repository reproduces or copies any part of that publication. The
cost table here carries figures rounded to sit inside published ranges, with a
derivation on every row, and a range read from a report is a fact rather than a
reproduction of it. The reliance is therefore on facts, not on a licence.

The GenCost data tables on the CSIRO Data Access Portal are a different artefact from
the report and may carry a Creative Commons licence of their own. Nothing here is
derived from them: the figures used come from ranges printed in the report, so the
reliance is on facts rather than on a licence. Anything taken from the portal tables
would need that collection's licence and version quoted here first.

### AEMC

The market price cap, the cumulative price threshold, the administered price cap
and the reliability standard are set by instrument and are cited by figure in
`settings.toml`, not redistributed. The cap and threshold are the pair applying from
1 July 2025 ($20,300/MWh and $1,823,600/MWh) from the AEMC's schedule of reliability
settings for the 2026-27 financial year, published 27 February 2026. The threshold is
published as a sum of five-minute trading interval prices; this model settles hourly
and divides it by 12 accordingly. The standard is period-dependent: 0.002 per
cent of unserved energy. The Reliability Panel's 2026 Reliability Standard and
Settings Review final report of 23 April 2026 recommends 0.003 per cent for the
period 1 July 2028 to 30 June 2032. This model uses the recommended 0.003 per cent
for a whole run rather than stepping it at 2028.

## The files

| File | Contents | Derivation |
|---|---|---|
| `fleet.csv` | Sixteen rows: thermal, hydro, storage, wind, solar, rooftop and one import link, each with a going-forward fixed operating cost | Aggregated to technology from public AEMO generation information and IASR retirement years. Generic labels, rounded capacities. Availability factors for coal, gas, hydro and pumped hydro are IASR figures by technology; the battery, wind, solar and rooftop rows carry nominal values, and wind and solar are dispatched from their traces rather than an availability. Fixed operating costs are rounded inside the published GenCost ranges for the technology, and are what the exit rule tests a plant's rent against, since capital is sunk for a plant that exists. The hydro energy budget and the import link's coincidence derate are illustrative and are documented parameters, not published values. The derate is the system's calibration lever: it is set so the four mild shape-years sit inside the reliability standard and the lull-on-heat year breaches it |
| `tech_costs.csv` | Entrant capital and operating costs, WACC, lead time, life, unit size, availability, firm factor | Rounded figures lying inside the published GenCost and IASR ranges, never the published point estimates. The pace at which plant can be delivered is deliberately NOT here: it has no published source, and stating it per technology in megawatts would be seven invented numbers that do not scale with the system. It is one concurrency setting in `settings.toml` instead |
| `dsr.csv` | Four demand-response tiers with prices and call-hour budgets | The IASR demand-side participation table for New South Wales, transcribed as **increments** by differencing the published cumulative bands. A test checks the tiers increase with price and that their sum stays in the range an increment basis implies |
| `growth.csv` | Three demand growth paths and their weights | Stylised around the IASR trajectories; stated as stylised wherever it is used |
| `scheme.csv` | One state scheme's milestone trajectory: a service, a year and a nameplate megawatt figure | No published source and none implied. It is a stylised ramp with round numbers, not any jurisdiction's target, and it is here so that a milestone binding, a ceiling binding and a budget binding are things the model can show rather than assume. The policy parameters that go with it - what may bid, the price ceiling, the annual budget and the tenor - are in `settings.toml` |
| `settings.toml` | Market price cap, thresholds, blocks, reliability standard, weather seed, contract, forward, investment and scheme parameters | AEMC reliability settings and model parameters. The market and reliability keys carry their source in a comment; the dispatch, time, weather, contracts, forward, investment and esem keys are model parameters with no external source and are documented as such, each with a comment saying what it does and why it is a choice. A test requires every declared key to be read somewhere, or listed as staged with a reason |

## What is committed under `outputs/canonical/`

Model output: tables and charts produced by running the model, committed so that a
talk never depends on live compute or a conference wifi connection. They are
generated from synthetic weather and the stylised tables above and reproduce no
source dataset, so they carry the same terms as the tables they came from. Every
chart says on its face that it is illustrative and not a forecast.

## Rules for changing anything here

1. A new file needs a row in the table above and a `derivation` column, with a
   value on every row. A test enforces both, because a rule that lives only in a
   document is a rule that lasts until the next person in a hurry.
2. Public sources only. No unpublished modelling and no third-party material.
3. If a real trace bundle is ever added, the two clauses above must be
   transcribed first, and synthetic weather stays the default regardless.
