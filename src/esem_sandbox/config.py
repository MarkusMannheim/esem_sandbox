"""Settings and the packaged data bundle.

The loader is strict: an unknown key in ``settings.toml`` raises rather than
being ignored, so a typo cannot silently leave a default in place.
"""

from __future__ import annotations

import csv
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

_SECTIONS = {
    "market": {
        "market_price_cap_per_mwh", "administered_price_cap_per_mwh",
        "cumulative_price_threshold", "cumulative_price_window_hours",
        "cumulative_price_threshold_intervals_per_hour",
        "minimum_price_per_mwh",
    },
    "reliability": {"standard_use_fraction", "interim_measure_use_fraction"},
    "dispatch": {
        "must_run_offer_per_mwh", "storage_spread_per_mwh",
    },
    "time": {"block_overnight", "block_morning", "block_solar", "block_peak"},
    "weather": {
        "shape_years", "hours_per_year", "seed", "peak_band_multipliers",
        "peak_band_weights",
    },
    "contracts": {"cap_strike_per_mwh", "swap_tenor_years",
                  "anchor_half_life_years"},
    "forward": {"anchor_offsets", "entry_step_min_mw", "entry_decay"},
    "investment": {
        "risk_premium", "cara_scale", "hedge_fraction_cap",
        "bilateral_contract_years", "merchant_underwrite_years", "discount_rate",
        "build_fraction_of_peak", "candidates_per_producer",
        "concurrent_builds_per_year", "exit_consecutive_negatives",
        "exit_notice_years", "max_exit_notices_per_tick",
    },
}


def _data_dir():
    return resources.files("esem_sandbox") / "data"


def read_csv(name: str) -> list[dict[str, str]]:
    """Read a packaged CSV into a list of row dicts."""
    with (_data_dir() / name).open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _num(row: dict[str, str], key: str, default: float | None = None) -> float | None:
    raw = (row.get(key) or "").strip()
    if raw == "":
        return default
    return float(raw)


@dataclass(frozen=True)
class Unit:
    """One row of the stylised fleet."""

    unit: str
    technology: str
    capacity_mw: float
    availability: float
    srmc_per_mwh: float
    retirement_year: int
    commissioned_year: int
    must_run_mw: float
    energy_budget_gwh: float | None
    duration_h: float | None
    round_trip_efficiency: float | None
    firm_factor: float
    cap_eligible: bool
    fom_per_kw_year: float = 0.0

    @property
    def fixed_cost_per_mw_year(self) -> float:
        """Going-forward fixed cost. Capex is sunk for a plant that exists, so an
        exit decision is about this number and nothing else."""
        return self.fom_per_kw_year * 1000.0

    @property
    def available_mw(self) -> float:
        return self.capacity_mw * self.availability

    def in_service(self, year: int) -> bool:
        """In service means built and not yet retired.

        Testing retirement alone was enough while the fleet was fixed. It stops
        being enough the moment anything is built: a unit whose construction
        starts this year would otherwise generate from the tick it was decided
        rather than from the tick it was finished, and the lead time that drives
        the boom-and-bust exercise would have no effect at all.
        """
        return self.commissioned_year <= year < self.retirement_year


@dataclass(frozen=True)
class TechCost:
    """What it costs to build and keep one MW of a technology.

    This is the candidate side of the model: rows here are things that can be
    built, where ``fleet.csv`` rows are things that exist. The two tables share a
    technology vocabulary but not a schema, because a candidate has a lead time,
    a unit size and a build ceiling, and an existing plant has a must-run band and
    a retirement year.
    """

    technology: str
    capex_per_kw: float
    fom_per_kw_year: float
    srmc_per_mwh: float
    wacc: float
    lead_years: int
    life_years: int
    unit_size_mw: float
    availability: float
    firm_factor: float
    duration_h: float | None
    cap_eligible: bool

    @property
    def crf(self) -> float:
        """Capital recovery factor: the annuity that repays one dollar over the life."""
        r, n = self.wacc, self.life_years
        if r <= 0:
            return 1.0 / n
        return r / (1.0 - (1.0 + r) ** -n)

    @property
    def fixed_cost_per_mw_year(self) -> float:
        """Annualised capital plus fixed operating cost, per MW of capacity.

        Rent is measured on the same basis, so no capacity-factor assumption
        enters the comparison. That is the point of stating both per MW-year: a
        peaker running 2 per cent of the year and a wind farm running 35 per cent
        are tested against their own costs, not against a common denominator that
        would flatter one of them.
        """
        return self.capex_per_kw * 1000.0 * self.crf + self.fom_per_kw_year * 1000.0


@dataclass(frozen=True)
class GrowthPath:
    """One demand trajectory and the prior weight on it."""

    path: str
    weight: float
    annual_growth: float


@dataclass(frozen=True)
class DsrTier:
    tier: str
    price_per_mwh: float
    capacity_mw: float
    call_hours: int


@dataclass(frozen=True)
class Settings:
    market: dict[str, Any]
    reliability: dict[str, Any]
    dispatch: dict[str, Any]
    time: dict[str, Any]
    weather: dict[str, Any]
    contracts: dict[str, Any] = field(default_factory=dict)
    forward: dict[str, Any] = field(default_factory=dict)
    investment: dict[str, Any] = field(default_factory=dict)
    fleet: tuple[Unit, ...] = field(repr=False, default=())
    dsr: tuple[DsrTier, ...] = field(repr=False, default=())
    tech_costs: tuple[TechCost, ...] = field(repr=False, default=())
    growth: tuple[GrowthPath, ...] = field(repr=False, default=())

    def tech(self, technology: str) -> TechCost:
        for t in self.tech_costs:
            if t.technology == technology:
                return t
        raise KeyError(f"no cost row for technology {technology!r}")

    @property
    def hourly_price_threshold(self) -> float:
        """The published threshold restated for a model that settles hourly.

        The threshold is a sum of trading-interval prices and a trading interval is
        five minutes, so one hourly interval here stands for twelve of the market's.
        """
        per_hour = self.market["cumulative_price_threshold_intervals_per_hour"]
        if per_hour <= 0:
            raise ValueError(
                "cumulative_price_threshold_intervals_per_hour must be positive: it "
                "is how many market trading intervals one modelled hour stands for, "
                "not a free parameter"
            )
        return self.market["cumulative_price_threshold"] / per_hour

    def blocks(self) -> dict[str, tuple[int, int]]:
        return {
            "overnight": tuple(self.time["block_overnight"]),
            "morning": tuple(self.time["block_morning"]),
            "solar": tuple(self.time["block_solar"]),
            "peak": tuple(self.time["block_peak"]),
        }


def load_settings(overrides: dict[str, dict[str, Any]] | None = None) -> Settings:
    """Load ``settings.toml``, the fleet and the demand-response ladder.

    ``overrides`` is a nested mapping of section to key, applied after the file
    and validated the same way, so an exercise can change one number without
    editing the package.
    """
    with (_data_dir() / "settings.toml").open("rb") as fh:
        raw = tomllib.load(fh)

    for section, keys in _SECTIONS.items():
        if section not in raw:
            raise ValueError(f"settings.toml is missing the [{section}] section")
        unknown = set(raw[section]) - keys
        if unknown:
            raise ValueError(
                f"unknown key(s) in [{section}]: {', '.join(sorted(unknown))}"
            )
        missing = keys - set(raw[section])
        if missing:
            raise ValueError(
                f"missing key(s) in [{section}]: {', '.join(sorted(missing))}"
            )
    unknown_sections = set(raw) - set(_SECTIONS)
    if unknown_sections:
        raise ValueError(
            f"unknown section(s): {', '.join(sorted(unknown_sections))}"
        )

    for section, values in (overrides or {}).items():
        if section not in _SECTIONS:
            raise ValueError(f"unknown settings section: {section}")
        bad = set(values) - _SECTIONS[section]
        if bad:
            raise ValueError(
                f"unknown key(s) in [{section}]: {', '.join(sorted(bad))}"
            )
        raw[section] = {**raw[section], **values}

    fleet = tuple(
        Unit(
            unit=r["unit"],
            technology=r["technology"],
            capacity_mw=_num(r, "capacity_mw", 0.0),
            availability=_num(r, "availability", 1.0),
            srmc_per_mwh=_num(r, "srmc_per_mwh", 0.0),
            retirement_year=int(_num(r, "retirement_year", 9999)),
            commissioned_year=int(_num(r, "commissioned_year", 0)),
            must_run_mw=_num(r, "must_run_mw", 0.0) or 0.0,
            energy_budget_gwh=_num(r, "energy_budget_gwh"),
            duration_h=_num(r, "duration_h"),
            round_trip_efficiency=_num(r, "round_trip_efficiency"),
            firm_factor=_num(r, "firm_factor", 0.0),
            cap_eligible=bool(int(_num(r, "cap_eligible", 0))),
            fom_per_kw_year=_num(r, "fom_per_kw_year", 0.0),
        )
        for r in read_csv("fleet.csv")
    )
    dsr = tuple(
        DsrTier(
            tier=r["tier"],
            price_per_mwh=float(r["price_per_mwh"]),
            capacity_mw=float(r["capacity_mw"]),
            call_hours=int(r["call_hours"]),
        )
        for r in read_csv("dsr.csv")
    )
    tech_costs = tuple(
        TechCost(
            technology=r["technology"],
            capex_per_kw=_num(r, "capex_per_kw", 0.0),
            fom_per_kw_year=_num(r, "fom_per_kw_year", 0.0),
            srmc_per_mwh=_num(r, "srmc_per_mwh", 0.0),
            wacc=_num(r, "wacc", 0.07),
            lead_years=int(_num(r, "lead_years", 2)),
            life_years=int(_num(r, "life_years", 25)),
            unit_size_mw=_num(r, "unit_size_mw", 100.0),
            availability=_num(r, "availability", 1.0),
            firm_factor=_num(r, "firm_factor", 0.0),
            duration_h=_num(r, "duration_h"),
            cap_eligible=bool(int(_num(r, "cap_eligible", 0))),
        )
        for r in read_csv("tech_costs.csv")
    )
    growth = tuple(
        GrowthPath(
            path=r["path"],
            weight=float(r["weight"]),
            annual_growth=float(r["annual_growth"]),
        )
        for r in read_csv("growth.csv")
    )
    weight_total = sum(g.weight for g in growth)
    if abs(weight_total - 1.0) > 1e-3:
        raise ValueError(
            f"growth path weights sum to {weight_total}, not 1. They are the prior "
            "over demand trajectories and the lattice multiplies them by the other "
            "axes' weights, so an axis that does not sum to one silently reweights "
            "every cell in the forward view."
        )
    return Settings(
        market=raw["market"],
        reliability=raw["reliability"],
        dispatch=raw["dispatch"],
        time=raw["time"],
        weather=raw["weather"],
        contracts=raw["contracts"],
        forward=raw["forward"],
        investment=raw["investment"],
        fleet=fleet,
        dsr=dsr,
        tech_costs=tech_costs,
        growth=growth,
    )
