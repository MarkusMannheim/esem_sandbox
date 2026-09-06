"""Every declared setting must be consumed, or explicitly declared as not yet.

The larger model this one simplifies had a critical defect of exactly this shape:
the forward lattice computed probability weights for each cell and every consumer
outside one function then reduced the cells with a plain arithmetic mean, so a
one-in-ten-year scenario entered at one in three. The weights were declared, and
silently never applied.

A setting that nothing reads is a claim the model does not honour. This test makes
that impossible to introduce by accident: a key must be listed as consumed, with
where, or listed as staged, with why.
"""

import tomllib
from importlib import resources

import pytest

from esem_sandbox.config import load_settings

# Keys the model actually reads, and where.
CONSUMED = {
    "market_price_cap_per_mwh": "dispatch._apply_ladder, as the price of unserved energy",
    "administered_price_cap_per_mwh": "dispatch._apply_ladder, once the threshold is breached",
    "cumulative_price_threshold": "config.hourly_price_threshold",
    "cumulative_price_threshold_intervals_per_hour": "config.hourly_price_threshold",
    "cumulative_price_window_hours": "dispatch._apply_ladder, the rolling window",
    "minimum_price_per_mwh": "dispatch.dispatch_year, enforced on the settled series",
    "standard_use_fraction": "cli, to say whether a year sits inside the standard",
    "must_run_offer_per_mwh": "dispatch._offer_stack, the price of a coal must-run band",
    "storage_spread_per_mwh": "dispatch._run_storage, the round-trip viability test",
    "block_overnight": "config.blocks, then report.block_mask",
    "block_morning": "config.blocks, then report.block_mask",
    "block_solar": "config.blocks, then report.block_mask",
    "block_peak": "config.blocks, then report.block_mask",
    "shape_years": "cli, the number of years dispatched",
    "hours_per_year": "cli, passed to the weather generator which validates it",
    "seed": "cli, the weather bundle",
    "peak_band_multipliers": "forward.cell_plan, the peak axis of the lattice",
    "peak_band_weights": "forward.cell_plan, the probability on each peak band",
    "anchor_offsets": "forward.forward_view, the years the lattice is dispatched at",
    "entry_step_min_mw": "forward.update_projected_entry, the floor on a step",
    "entry_decay": "forward.update_projected_entry, the unbracketed retreat",
    "risk_premium": "investment.cara_coefficient, lambda = risk aversion x this",
    "cara_scale": "investment.cara_coefficient, the coefficient over $/MW-year",
    "hedge_fraction_cap": "investment.residual_exposure, the ceiling on cover",
    "bilateral_contract_years": "investment.residual_exposure, the swap book channel",
    "merchant_underwrite_years": "investment.residual_exposure, the underwrite channel",
    "discount_rate": "investment.going_forward_npv_per_mw, the incumbent's rate",
    "build_fraction_of_peak": "investment.build_size_mw",
    "candidates_per_producer": "investment.rank_candidates, decisions taken a tick",
    "concurrent_builds_per_year": "investment.build_ceiling_mw",
    "exit_consecutive_negatives": "investment.exit_notices, the run-length trigger",
    "exit_notice_years": "investment.exit_notices, and the notice it writes",
    "max_exit_notices_per_tick": "investment.exit_notices, the stagger",
    "cap_strike_per_mwh": "simulate, the strike every cap in the model is written at",
    "swap_tenor_years": "simulate.run, the length of each rung of the hedge ladder",
    "anchor_half_life_years": "clearing.clear_bilateral, the lane anchor's memory",
    "crossing_steps": "clearing._crossed, how finely each side's curve is cut",
    "crossing_spread": "clearing._crossed, how far each curve reaches from the anchor",
    "contract_tenor_years": "simulate._auction, the tenor an award is written for",
    "contracted_wacc": "esem.blended_wacc, what a contracted megawatt is financed at",
    "screen_multiple_of_spot": "esem.screen, the sanity ceiling",
    "screen_floor_per_mwh": "esem.screen, its floor in a cheap year",
    "recycling_window_years": "esem.recycle, how many delivery years are offered",
    "recycling_conduct": "esem.recycle, what happens to volume nobody buys",
    "fire_sale_fraction": "esem.recycle, the price under fire-sale conduct",
    "overhead_per_year": "esem.levy_per_mwh, what the administrator costs to run",
    "reserve_margin": "simulate.run, the reported margin gap (never the volume)",
    "technologies": "scheme.load_scheme, what the scheme may buy",
    "ceiling_per_mw_year": "scheme.clear_scheme, the most it will pay",
    "budget_per_year": "scheme.clear_scheme, the most it will spend in a year",
    "tenor_years": "scheme.load_scheme, how long an award is contracted for",
}

# Keys committed ahead of the code that will read them. Each needs a reason, and
# each is a promise that the value has not been quietly relied on in the meantime.
STAGED = {
    "interim_measure_use_fraction":
        "the interim reliability measure becomes a lever when the reliability view "
        "is built; nothing reads it today and no result depends on it",
}


def _declared_keys() -> set[str]:
    with (resources.files("esem_sandbox") / "data" / "settings.toml").open("rb") as fh:
        raw = tomllib.load(fh)
    return {k for section in raw.values() for k in section}


def test_every_declared_setting_is_consumed_or_explicitly_staged():
    declared = _declared_keys()
    accounted = set(CONSUMED) | set(STAGED)
    unaccounted = declared - accounted
    assert not unaccounted, (
        f"settings declared but neither consumed nor staged: {sorted(unaccounted)}. "
        "Wire it up, or add it to STAGED with a reason."
    )
    stale = accounted - declared
    assert not stale, f"listed here but no longer declared: {sorted(stale)}"


def test_staged_settings_carry_a_reason():
    for key, reason in STAGED.items():
        assert len(reason) > 40, f"{key} needs a real reason, not a placeholder"


def test_the_market_price_floor_is_actually_enforced():
    """It was declared for a while and never applied; the binding floor was the VRE
    offer instead, which is a different number and a different rule."""
    import numpy as np
    from esem_sandbox.core.dispatch import dispatch_year
    from esem_sandbox.core.weather import generate_bundle

    s = load_settings({"dispatch": {"must_run_offer_per_mwh": -5000.0}})
    b = generate_bundle(s.weather["seed"], 1)
    shape = b["demand_shape"][0]
    res = dispatch_year(s, 2026, shape * (12500.0 / shape.max()),
                        b["wind_cf"][0], b["solar_cf"][0])
    floor = s.market["minimum_price_per_mwh"]
    assert res.price.min() >= floor, (
        "an offer below the market price floor must be clipped to it"
    )
    assert np.isclose(res.price.min(), floor), (
        "with a -$5,000 offer the floor should bind at exactly the floor"
    )
