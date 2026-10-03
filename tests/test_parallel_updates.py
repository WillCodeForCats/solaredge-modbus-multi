"""Every platform declares PARALLEL_UPDATES (quality-scale rule parallel-updates)."""

from __future__ import annotations

import importlib

import pytest

# Read-only, coordinator-driven platforms need no throttle; the write-capable
# ones serialise their service calls — the inverter has one Modbus session.
EXPECTED = {
    "sensor": 0,
    "binary_sensor": 0,
    "number": 1,
    "select": 1,
    "switch": 1,
    "button": 1,
}


@pytest.mark.parametrize(("platform", "expected"), sorted(EXPECTED.items()))
def test_platform_declares_parallel_updates(platform: str, expected: int) -> None:
    module = importlib.import_module(
        f"custom_components.solaredge_modbus_multi.{platform}"
    )
    assert module.PARALLEL_UPDATES == expected
