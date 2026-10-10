"""Tests for entity and scanner logic.

Covers the site limit control switches/select (bit writes and logging), the RRCR
status attributes, the heat sink temperature availability check, and
SolarEdgeDeviceScanner.scan_list's progress reporting.
"""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.solaredge_modbus_multi.const import (
    LIMIT_CONTROL_MODE,
    SunSpecNotImpl,
)
from custom_components.solaredge_modbus_multi.scanner import SolarEdgeDeviceScanner
from custom_components.solaredge_modbus_multi.select import SolaredgeLimitControlMode
from custom_components.solaredge_modbus_multi.sensor import (
    HeatSinkTemperature,
    SolarEdgeRRCR,
)
from custom_components.solaredge_modbus_multi.switch import (
    SolarEdgeExternalProduction,
    SolarEdgeNegativeSiteLimit,
)


def _platform(mode=0):
    data = SimpleNamespace(E_Lim_Ctl_Mode=mode)
    return SimpleNamespace(
        uid_base="inverter_1",
        site_limit_control_data=data,
        write=AsyncMock(),
    )


def _written_bits(platform):
    platform.write.assert_awaited_once()
    data, field, bits = platform.write.await_args.args
    assert data is platform.site_limit_control_data
    assert field == "E_Lim_Ctl_Mode"
    return bits


def _entity(cls, platform):
    entity = cls(platform, None, None)
    entity.async_update = AsyncMock()
    return entity


async def test_external_production_turn_on_sets_bit_10(caplog):
    """Test external production turn on sets bit 10."""
    platform = _platform(mode=0b101)
    entity = _entity(SolarEdgeExternalProduction, platform)

    with caplog.at_level(logging.DEBUG):
        await entity.async_turn_on()

    assert _written_bits(platform) == 0b101 | (1 << 10)
    assert "set inverter_1_external_production bits 0000010000000101" in caplog.text
    entity.async_update.assert_awaited_once()


async def test_external_production_turn_off_clears_bit_10():
    """Test external production turn off clears bit 10."""
    platform = _platform(mode=(1 << 10) | 0b1)
    entity = _entity(SolarEdgeExternalProduction, platform)

    await entity.async_turn_off()

    assert _written_bits(platform) == 0b1
    entity.async_update.assert_awaited_once()


async def test_negative_site_limit_turn_on_sets_bit_11(caplog):
    """Test negative site limit turn on sets bit 11 and keeps other bits."""
    platform = _platform(mode=0b101)
    entity = _entity(SolarEdgeNegativeSiteLimit, platform)

    with caplog.at_level(logging.DEBUG):
        await entity.async_turn_on()

    assert _written_bits(platform) == 0b101 | (1 << 11)
    assert "bits 0000100000000101" in caplog.text
    entity.async_update.assert_awaited_once()


async def test_negative_site_limit_turn_off_clears_bit_11(caplog):
    """Test negative site limit turn off clears bit 11 and keeps other bits."""
    platform = _platform(mode=(1 << 11) | 0b101)
    entity = _entity(SolarEdgeNegativeSiteLimit, platform)

    with caplog.at_level(logging.DEBUG):
        await entity.async_turn_off()

    assert _written_bits(platform) == 0b101
    assert "bits 0000000000000101" in caplog.text
    entity.async_update.assert_awaited_once()


@pytest.mark.parametrize(
    ("mode", "expected_key"),
    [(0b001, 0), (0b010, 1), (0b100, 2), (0b000, None)],
)
def test_limit_control_current_option(mode, expected_key):
    """Test limit control current option."""
    entity = SolaredgeLimitControlMode(_platform(mode), None, None)

    assert entity.current_option == LIMIT_CONTROL_MODE[expected_key]


@pytest.mark.parametrize(
    ("option_key", "start_bits", "expected_bits"),
    [
        (1, 0b100, 0b010),
        (2, 0b001, 0b100),
        (0, 0b110, 0b001),
        (None, 0b111, 0b000),
    ],
)
async def test_limit_control_select_option_writes_mode_bits(
    option_key, start_bits, expected_bits, caplog
):
    """Test limit control select option writes mode bits."""
    platform = _platform(start_bits)
    entity = _entity(SolaredgeLimitControlMode, platform)

    with caplog.at_level(logging.DEBUG):
        await entity.async_select_option(LIMIT_CONTROL_MODE[option_key])

    assert _written_bits(platform) == expected_bits
    assert "set inverter_1_limit_control_mode bits" in caplog.text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0b0000, "[]"),
        (0b0001, "['L4']"),
        (0b1010, "['L3', 'L1']"),
        (0b1111, "['L4', 'L3', 'L2', 'L1']"),
    ],
)
def test_rrcr_extra_state_attributes_list_active_inputs(value, expected):
    """Test rrcr extra state attributes list active inputs."""
    platform = SimpleNamespace(
        uid_base="inverter_1",
        global_power_control_data=SimpleNamespace(I_RRCR=value),
    )
    entity = SolarEdgeRRCR(platform, None, None)

    assert entity.extra_state_attributes == {"inputs": expected}


@pytest.mark.parametrize(
    ("value", "sf", "expected"),
    [
        (25, 0, True),
        (0, 0, False),
        (SunSpecNotImpl.INT16, 0, False),
        (None, 0, False),
        (25, None, False),
        (25, SunSpecNotImpl.INT16, False),
    ],
)
def test_heat_sink_temperature_availability(value, sf, expected):
    """Test heat sink temperature availability."""
    platform = SimpleNamespace(
        uid_base="inverter_1",
        inverter_data=SimpleNamespace(I_Temp_Sink=value, I_Temp_SF=sf),
    )
    entity = HeatSinkTemperature(
        platform, None, SimpleNamespace(last_update_success=True)
    )

    with patch(
        "homeassistant.helpers.update_coordinator.CoordinatorEntity.available",
        new=True,
    ):
        assert entity.available is expected


async def test_scan_list_reports_progress_and_collects_inverters():
    """Test scan list reports progress and collects inverters."""
    scanner = SolarEdgeDeviceScanner("127.0.0.1", 1502)
    progress = AsyncMock()
    results = {1: scanner.FOUND_INV, 2: 0, 3: scanner.FOUND_INV}

    with patch.object(
        scanner, "scan_device_id", new=AsyncMock(side_effect=lambda i, t: results[i])
    ):
        found = await scanner.scan_list([1, 2, 3], progress_callback=progress)

    assert found == [1, 3]
    assert [call.args for call in progress.await_args_list] == [
        (0, 3),
        (1, 3),
        (2, 3),
        (3, 3),
    ]


async def test_scan_list_works_without_progress_callback():
    """Test scan list works without progress callback."""
    scanner = SolarEdgeDeviceScanner("127.0.0.1", 1502)

    with patch.object(
        scanner, "scan_device_id", new=AsyncMock(return_value=scanner.FOUND_INV)
    ):
        assert await scanner.scan_list([5]) == [5]
