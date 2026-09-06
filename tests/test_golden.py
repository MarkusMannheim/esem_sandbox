"""A golden fingerprint: the model's answers, pinned.

Every other test here says a property must hold. This one says the numbers must not
move. Both are needed and they catch different things: a property test passes
through a change that is still internally consistent but no longer the same model,
and this does not.

The point is not that these numbers are right. It is that a change which moves them
should be a change somebody meant to make. When this fails, read what moved: if the
change was deliberate, regenerate with ``tools/write_golden.py`` and put the diff in
the same commit as the change that caused it, so the movement is reviewable. A golden
file regenerated without a reason in the message is a test that has been switched off.
"""

import json
import pathlib

import pytest

from esem_sandbox.config import load_settings
from esem_sandbox.core.forward import cell_plan
from esem_sandbox.core.simulate import ESEM, MERCHANT, run

GOLDEN = pathlib.Path(__file__).resolve().parent / "golden" / "run_fingerprint.json"
TOLERANCE = 1e-6


@pytest.fixture(scope="module")
def golden():
    return json.loads(GOLDEN.read_text())


@pytest.fixture(scope="module")
def actual(golden):
    settings = load_settings()
    fast = tuple(c for c in cell_plan(settings) if c.shape_year == 0)
    assert len(fast) == golden["cells"], (
        "the lattice this was pinned against has changed size"
    )
    return {
        leg: run(settings, ticks=golden["ticks"], seed=golden["seed"], cells=fast,
                 leg=leg)
        for leg in (MERCHANT, ESEM)
    }, settings


def _compare(name, leg, got, want):
    if isinstance(want, list):
        assert len(got) == len(want), f"{leg}.{name}: {len(got)} values, not {len(want)}"
        for i, (a, b) in enumerate(zip(got, want)):
            assert a == pytest.approx(b, abs=TOLERANCE, rel=1e-9), (
                f"{leg}.{name}[{i}] moved from {b} to {a}. If that was meant, "
                "regenerate with tools/write_golden.py in the same commit"
            )
    else:
        assert got == pytest.approx(want, abs=TOLERANCE, rel=1e-9), (
            f"{leg}.{name} moved from {want} to {got}. If that was meant, "
            "regenerate with tools/write_golden.py in the same commit"
        )


@pytest.mark.parametrize("leg", [MERCHANT, ESEM])
def test_the_run_still_gives_the_answers_it_was_pinned_to(golden, actual, leg):
    results, settings = actual
    result = results[leg]
    want = golden[leg]
    assert result.draw.growth_path == want["growth_path"]
    _compare("mean_price", leg, [round(t.mean_price, 6) for t in result.ticks],
             want["mean_price"])
    _compare("unserved_gwh", leg, [round(t.unserved_gwh, 6) for t in result.ticks],
             want["unserved_gwh"])
    _compare("built_mw", leg,
             [round(sum(b.capacity_mw for b in t.builds), 3) for t in result.ticks],
             want["built_mw"])
    _compare("live_contracts", leg, [t.live_contracts for t in result.ticks],
             want["live_contracts"])
    _compare("lane_volume_mw", leg,
             [round(t.lane_volume_mw, 3) for t in result.ticks],
             want["lane_volume_mw"])
    _compare("levy_per_mwh", leg,
             [round(t.levy_per_mwh, 6) for t in result.ticks], want["levy_per_mwh"])
    _compare("bill", leg, round(result.consumer_cost(settings), 3), want["bill"])
    _compare("resource_cost", leg, round(result.resource_cost(settings), 3),
             want["resource_cost"])
    assert {k: round(v, 3) for k, v in sorted(result.built_by_technology().items())} \
        == want["built_by_technology"], (
        f"{leg}: the fleet that got built has changed"
    )


def test_the_two_legs_are_still_different(golden):
    """A golden file that pinned two identical legs would pass for ever and mean
    nothing."""
    assert golden[MERCHANT]["unserved_gwh"] != golden[ESEM]["unserved_gwh"]
    assert golden[ESEM]["lane_volume_mw"] != golden[MERCHANT]["lane_volume_mw"]
    assert any(v > 0 for v in golden[ESEM]["levy_per_mwh"])
    assert all(v == 0 for v in golden[MERCHANT]["levy_per_mwh"]), (
        "the merchant leg must have no scheme in it at all"
    )
