"""Tests for the GPC/APC optional-feature probe leeway logic in hub.py."""

from types import SimpleNamespace

import pytest
from homeassistant.helpers import issue_registry as ir
from modbus_connection.exceptions import (
    IllegalDataAddressError,
    IllegalFunctionError,
    ModbusConnectionError,
    ModbusExceptionError,
    ModbusTimeoutError,
)
from modbus_connection.mock import MockModbusConnection

from custom_components.solaredge_modbus_multi.const import DOMAIN, RetrySettings
from custom_components.solaredge_modbus_multi.hub import SolarEdgeInverter

GPC_ADDRESS = 61440  # GlobalDynamicPowerControl.I_RRCR
APC_ADDRESS = 61696  # AdvancedPowerControl.CommitPwrCtlSettings

TRANSIENT_ERRORS = [
    ModbusTimeoutError("no response"),
    ModbusConnectionError("link down"),
    ModbusExceptionError(6, "device busy"),
]


def _make_inverter(hass):
    connection = MockModbusConnection()

    async def component_update(unit_id, component):
        await component.async_update()

    stub_hub = SimpleNamespace(
        connection=connection,
        component_update=component_update,
        option_detect_extras=True,
        option_storage_control=False,
        option_site_limit_control=False,
        _hass=hass,
        _entry_id="test_entry",
        hub_host="127.0.0.1",
    )
    inverter = SolarEdgeInverter(1, stub_hub)

    mock_unit = connection.for_unit(1)
    mock_unit.holding[40069] = 101  # InverterData.C_SunSpec_DID
    mock_unit.holding[40070] = 50  # InverterData.C_SunSpec_Length

    return inverter, mock_unit


@pytest.mark.parametrize("error", TRANSIENT_ERRORS)
async def test_gpc_never_detected_transient_failure_is_tolerated(hass, error):
    inverter, mock_unit = _make_inverter(hass)
    mock_unit.fail_read(GPC_ADDRESS, error)

    for expected_count in range(1, RetrySettings.FeatureProbeTimeouts):
        await inverter.read_modbus_data()
        assert inverter.global_power_control is None
        assert inverter._gpc_timeouts_count == expected_count

    await inverter.read_modbus_data()
    assert inverter.global_power_control is False
    assert inverter._gpc_timeouts_count == 0


@pytest.mark.parametrize("error_cls", [IllegalDataAddressError, IllegalFunctionError])
async def test_gpc_illegal_rejection_disables_immediately_even_if_working(
    hass, error_cls
):
    inverter, mock_unit = _make_inverter(hass)
    await inverter.read_modbus_data()
    assert inverter.global_power_control is True

    mock_unit.fail_read(GPC_ADDRESS, error_cls())
    await inverter.read_modbus_data()

    assert inverter.global_power_control is False
    assert inverter._gpc_timeouts_count == 0


@pytest.mark.parametrize("error", TRANSIENT_ERRORS)
async def test_gpc_transient_failure_after_success_is_tolerated(hass, error):
    inverter, mock_unit = _make_inverter(hass)
    await inverter.read_modbus_data()
    assert inverter.global_power_control is True

    mock_unit.fail_read(GPC_ADDRESS, error)
    for expected_count in range(1, RetrySettings.FeatureProbeTimeouts):
        await inverter.read_modbus_data()
        assert inverter.global_power_control is True
        assert inverter._gpc_timeouts_count == expected_count

    await inverter.read_modbus_data()
    assert inverter.global_power_control is False
    assert inverter._gpc_timeouts_count == 0


async def test_gpc_success_resets_failure_counter_mid_window(hass):
    inverter, mock_unit = _make_inverter(hass)
    await inverter.read_modbus_data()

    mock_unit.fail_read(GPC_ADDRESS, ModbusTimeoutError("no response"))
    await inverter.read_modbus_data()
    assert inverter._gpc_timeouts_count == 1

    mock_unit.fail_read(GPC_ADDRESS, None)
    await inverter.read_modbus_data()

    assert inverter.global_power_control is True
    assert inverter._gpc_timeouts_count == 0


async def test_gpc_repair_flow_reset_gets_the_same_leeway_as_a_fresh_probe(hass):
    inverter, mock_unit = _make_inverter(hass)
    mock_unit.fail_read(GPC_ADDRESS, ModbusTimeoutError("no response"))

    for _ in range(RetrySettings.FeatureProbeTimeouts):
        await inverter.read_modbus_data()
    assert inverter.global_power_control is False

    inverter.global_power_control = None

    await inverter.read_modbus_data()
    assert inverter.global_power_control is None
    assert inverter._gpc_timeouts_count == 1


async def test_gpc_give_up_creates_fixable_issue_then_clears_on_recovery(hass):
    inverter, mock_unit = _make_inverter(hass)
    mock_unit.fail_read(GPC_ADDRESS, ModbusTimeoutError("no response"))

    for _ in range(RetrySettings.FeatureProbeTimeouts):
        await inverter.read_modbus_data()
    assert inverter.global_power_control is False

    issue_id = inverter._feature_timeout_issue_id("gpc")
    registry = ir.async_get(hass)
    issue = registry.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.is_fixable is True

    mock_unit.fail_read(GPC_ADDRESS, None)
    await inverter.read_modbus_data()

    assert registry.async_get_issue(DOMAIN, issue_id) is None


async def test_gpc_illegal_rejection_does_not_create_an_issue(hass):
    inverter, mock_unit = _make_inverter(hass)
    mock_unit.fail_read(GPC_ADDRESS, IllegalDataAddressError())

    await inverter.read_modbus_data()

    assert inverter.global_power_control is False
    issue_id = inverter._feature_timeout_issue_id("gpc")
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_apc_illegal_rejection_disables_immediately_even_if_working(hass):
    inverter, mock_unit = _make_inverter(hass)
    await inverter.read_modbus_data()
    assert inverter.advanced_power_control is True

    mock_unit.fail_read(APC_ADDRESS, IllegalFunctionError())
    await inverter.read_modbus_data()

    assert inverter.advanced_power_control is False
    assert inverter._apc_timeouts_count == 0


async def test_apc_never_detected_transient_failure_is_tolerated(hass):
    inverter, mock_unit = _make_inverter(hass)
    mock_unit.fail_read(APC_ADDRESS, ModbusTimeoutError("no response"))

    for expected_count in range(1, RetrySettings.FeatureProbeTimeouts):
        await inverter.read_modbus_data()
        assert inverter.advanced_power_control is None
        assert inverter._apc_timeouts_count == expected_count

    await inverter.read_modbus_data()
    assert inverter.advanced_power_control is False
    assert inverter._apc_timeouts_count == 0


async def test_apc_transient_failure_after_success_is_tolerated_then_gives_up(hass):
    inverter, mock_unit = _make_inverter(hass)
    await inverter.read_modbus_data()
    assert inverter.advanced_power_control is True

    mock_unit.fail_read(APC_ADDRESS, ModbusTimeoutError("no response"))
    for expected_count in range(1, RetrySettings.FeatureProbeTimeouts):
        await inverter.read_modbus_data()
        assert inverter.advanced_power_control is True
        assert inverter._apc_timeouts_count == expected_count

    await inverter.read_modbus_data()
    assert inverter.advanced_power_control is False
    assert inverter._apc_timeouts_count == 0
