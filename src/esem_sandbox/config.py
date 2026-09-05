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
        "must_run_offer_per_mwh", "storage_spread_per_mwh", "max_storage_passes",
        "storage_price_tolerance",
    },
    "time": {"block_overnight", "block_morning", "block_solar", "block_peak"},
    "weather": {
        "shape_years", "hours_per_year", "seed", "peak_band_multipliers",
        "peak_band_weights",
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
    must_run_mw: float
    energy_budget_gwh: float | None
    duration_h: float | None
    round_trip_efficiency: float | None
    firm_factor: float
    cap_eligible: bool

    @property
    def available_mw(self) -> float:
        return self.capacity_mw * self.availability

    def in_service(self, year: int) -> bool:
        return year < self.retirement_year


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
    fleet: tuple[Unit, ...] = field(repr=False, default=())
    dsr: tuple[DsrTier, ...] = field(repr=False, default=())

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
            must_run_mw=_num(r, "must_run_mw", 0.0) or 0.0,
            energy_budget_gwh=_num(r, "energy_budget_gwh"),
            duration_h=_num(r, "duration_h"),
            round_trip_efficiency=_num(r, "round_trip_efficiency"),
            firm_factor=_num(r, "firm_factor", 0.0),
            cap_eligible=bool(int(_num(r, "cap_eligible", 0))),
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
    return Settings(
        market=raw["market"],
        reliability=raw["reliability"],
        dispatch=raw["dispatch"],
        time=raw["time"],
        weather=raw["weather"],
        fleet=fleet,
        dsr=dsr,
    )
