"""The people in the market, and what makes them different.

Six agents carry the whole argument, because the contrast the model exists to show is
between an investor exposed to the spot price and one holding a contract. Everything
else about a firm is left out.

What separates them is risk aversion and exposure, not size or cleverness. A retailer
buys cover because it is short energy and long customers; a producer writes cover
because it is long energy; a merchant sits closest to the spot price and therefore
demands the most for going near it.
"""

from __future__ import annotations

from dataclasses import dataclass

PRODUCER = "producer"
RETAILER = "retailer"


@dataclass(frozen=True)
class Agent:
    """One market participant.

    ``risk_aversion`` is the archetype's relative risk aversion, scaled into a CARA
    coefficient where it is used. ``load_share`` is a retailer's share of system
    demand. ``swap_cover`` and ``cap_cover`` are the fractions of its position a
    retailer tries to hedge, which is a policy, not an optimum: real retailers hedge
    to a board mandate rather than to a first-order condition.
    """

    name: str
    kind: str
    risk_aversion: float
    load_share: float = 0.0
    swap_cover: float = 0.0
    cap_cover: float = 0.0
    units: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in (PRODUCER, RETAILER):
            raise ValueError(f"unknown agent kind: {self.kind}")
        if not 0.0 < self.risk_aversion <= 1.0:
            raise ValueError("risk aversion is a fraction of the archetype scale")
        if self.kind == RETAILER and not 0.0 < self.load_share <= 1.0:
            raise ValueError("a retailer must carry some load")


def default_roster() -> tuple[Agent, ...]:
    """The archetypes.

    Risk aversions follow the published evidence the design cites: gentailers, which
    are naturally hedged by owning both load and plant, sit below merchants, which are
    not. The regional merchant is the representative new entrant and is the least risk
    averse of the producers, because it is the one deciding whether to build.
    """
    return (
        Agent("gentailer_a", PRODUCER, 0.50,
              units=("coal_a", "coal_b", "ccgt_a", "wind_a")),
        Agent("gentailer_b", PRODUCER, 0.50,
              units=("coal_c", "coal_d", "solar_a")),
        Agent("merchant", PRODUCER, 0.60,
              units=("ocgt_a", "ocgt_b", "peaker_dist", "phes_a")),
        Agent("regional_merchant", PRODUCER, 0.45,
              units=("hydro_a", "battery_2h", "battery_4h")),
        Agent("retailer_a", RETAILER, 0.50, load_share=0.60,
              swap_cover=0.75, cap_cover=0.20),
        Agent("retailer_b", RETAILER, 0.50, load_share=0.40,
              swap_cover=0.75, cap_cover=0.20),
    )


def check_roster(roster: tuple[Agent, ...], unit_names: set[str]) -> None:
    """Every unit owned once, all load accounted for.

    A unit owned by nobody earns revenue that reaches no balance sheet, and a unit
    owned twice earns it twice. Neither shows up in a price.
    """
    owned: dict[str, str] = {}
    for agent in roster:
        for unit in agent.units:
            if unit in owned:
                raise ValueError(f"{unit} is owned by {owned[unit]} and {agent.name}")
            owned[unit] = agent.name
    missing = unit_names - set(owned)
    if missing:
        raise ValueError(f"unowned units: {', '.join(sorted(missing))}")
    stray = set(owned) - unit_names
    if stray:
        raise ValueError(f"units that do not exist: {', '.join(sorted(stray))}")

    load = sum(a.load_share for a in roster if a.kind == RETAILER)
    if abs(load - 1.0) > 1e-9:
        raise ValueError(f"retailer load shares sum to {load}, not 1")
