"""Change one thing and compare: the functions behind ``--set``, ``sweep`` and
the notebook.

Everything a reader can move lives in ``settings.toml`` and the scenario files.
This module turns a string like ``investment.risk_premium=0.1`` into the override
the strict loader accepts, runs both legs of a comparison on one weather draw, and
reduces a pair of legs to the handful of numbers a comparison turns on. The command
line and the notebook both call these, so a number printed in one place is the same
number drawn in the other.
"""

from __future__ import annotations

import tomllib
from typing import Any

from .config import Settings, load_settings
from .core.forward import Cell, cell_plan
from .core.simulate import ESEM, MERCHANT, RunResult, run

# The notebook's lattice: a mild weather year and the lull-on-heat year, so an
# investor sees both a quiet future and a stressed one, at a fraction of the
# cost of the full five. Results differ from the full lattice, and anything
# quoted from a quick run should say so.
QUICK_SHAPE_YEARS = (0, 4)


def parse_value(text: str) -> Any:
    """Read a value the way TOML would, so ``6`` is an integer, ``0.1`` a float,
    ``true`` a boolean, ``[4, 8]`` a list and ``"warehouse"`` a string.

    Bare words that are not TOML literals are taken as strings, because
    ``esem.recycling_conduct=warehouse`` is what someone types and demanding the
    quotes would be pedantry the loader does not need.
    """
    try:
        return tomllib.loads(f"v = {text}")["v"]
    except (tomllib.TOMLDecodeError, ValueError):
        return text


def overrides_from(pairs: list[str] | None,
                   base: dict[str, dict[str, Any]] | None = None
                   ) -> dict[str, dict[str, Any]]:
    """``section.key=value`` strings into the nested mapping ``load_settings``
    takes, on top of whatever a scenario already set.

    The loader validates section and key names, so nothing is checked here beyond
    the shape of the string: a typo in a key fails loudly there, as a typo in a
    scenario file does, rather than leaving a default quietly in place.
    """
    out: dict[str, dict[str, Any]] = {k: dict(v) for k, v in (base or {}).items()}
    for pair in pairs or ():
        if "=" not in pair or "." not in pair.split("=", 1)[0]:
            raise ValueError(
                f"expected section.key=value, got {pair!r}"
            )
        dotted, text = pair.split("=", 1)
        section, key = dotted.split(".", 1)
        out.setdefault(section, {})[key] = parse_value(text)
    return out


def quick_cells(settings: Settings) -> tuple[Cell, ...]:
    """The reduced lattice, for iterating: 18 futures in place of 45."""
    return tuple(c for c in cell_plan(settings)
                 if c.shape_year in QUICK_SHAPE_YEARS)


def run_pair(settings: Settings, *, ticks: int = 20, start_year: int = 2026,
             peak_mw: float = 12_500.0, seed: int | None = None,
             quick: bool = False, retire: dict[str, int] | None = None,
             clearing: str = "anchor", scheme: bool = False,
             investment: str = "simultaneous",
             progress=None) -> dict[str, RunResult]:
    """Both legs on one weather draw.

    The two legs draw one weather sequence from one seed, so the difference
    between them is the mechanism and nothing else. A leg that drew its own
    weather would report the difference between two climates as the effect of a
    policy, and the check at the end is there so that can never happen quietly.
    """
    cells = quick_cells(settings) if quick else None
    legs: dict[str, RunResult] = {}
    for i, leg in enumerate((MERCHANT, ESEM), start=1):
        if progress is not None:
            progress(f"running the {leg} leg, {ticks} years ({i} of 2)...")
        legs[leg] = run(settings, ticks=ticks, start_year=start_year,
                        peak_mw=peak_mw, seed=seed, cells=cells, leg=leg,
                        retire=retire, clearing=clearing, scheme=scheme,
                        investment=investment)
    if legs[MERCHANT].draw != legs[ESEM].draw:
        raise AssertionError(
            "the two legs saw different weather; a comparison between them would "
            "be a comparison of climates rather than of mechanisms"
        )
    return legs


def summarise(settings: Settings, legs: dict[str, RunResult]) -> dict[str, float]:
    """A pair of legs reduced to what a comparison turns on.

    Signed differences are merchant less scheme, so a positive bill move means
    consumers pay less with the scheme and a positive resource move means the
    economy gives up less. The transfer is the part of the bill move that no
    resource was saved for: capacity pushes the pool price down, which moves money
    from producers to consumers without saving any of it.
    """
    m, e = legs[MERCHANT], legs[ESEM]
    built = lambda r: sum(b.capacity_mw for t in r.ticks for b in t.builds)
    awarded = sum(a.capacity_mw for t in e.ticks for a in t.awards)
    bill = m.consumer_cost(settings) - e.consumer_cost(settings)
    real = m.resource_cost(settings) - e.resource_cost(settings)
    outage = (m.unserved_valued_at_the_cap(settings)
              - e.unserved_valued_at_the_cap(settings))
    return {
        "merchant_unserved_gwh": m.total_unserved_gwh,
        "esem_unserved_gwh": e.total_unserved_gwh,
        "merchant_mean_price": sum(t.mean_price for t in m.ticks) / len(m.ticks),
        "esem_mean_price": sum(t.mean_price for t in e.ticks) / len(e.ticks),
        "merchant_bill": m.consumer_cost(settings),
        "esem_bill": e.consumer_cost(settings),
        "bill_move": bill,
        "resource_cost_move": real,
        "transfer": bill - real,
        "outage_avoided": outage,
        "plant_and_fuel_saved": real - outage,
        "merchant_built_mw": built(m),
        "esem_built_mw": built(e),
        "awarded_mw": awarded,
        "levy": e.total_levy,
    }


def sweep(parameter: str, values: list[Any], *,
          base: dict[str, dict[str, Any]] | None = None,
          progress=None, **run_options) -> list[dict[str, Any]]:
    """One parameter over several values, both legs each time, one draw throughout.

    ``parameter`` is ``section.key``. Every value is run on top of the same base
    overrides and the same seed, so the rows differ in that one number and in
    nothing else. Each row is the summary for one value, with the value in front.
    """
    if "." not in parameter:
        raise ValueError(f"expected section.key, got {parameter!r}")
    section, key = parameter.split(".", 1)
    rows: list[dict[str, Any]] = []
    for value in values:
        overrides = overrides_from([], base)
        overrides.setdefault(section, {})[key] = value
        settings = load_settings(overrides)
        if progress is not None:
            progress(f"{parameter} = {value!r}")
        legs = run_pair(settings, progress=progress, **run_options)
        rows.append({"parameter": parameter, "value": value,
                     **summarise(settings, legs)})
    return rows
