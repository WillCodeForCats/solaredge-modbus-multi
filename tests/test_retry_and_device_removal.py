"""Tests for the retry helpers and device removal check.

Covers async_update_with_retry/async_write_with_retry in hub.py, and
SolarEdgeCoordinator's refresh retry and async_remove_config_entry_device in
__init__.py.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from modbus_connection.exceptions import ModbusConnectionError, ModbusTimeoutError

from custom_components.solaredge_modbus_multi import (
    SolarEdgeCoordinator,
    async_remove_config_entry_device,
)
from custom_components.solaredge_modbus_multi.const import DOMAIN, RetrySettings
from custom_components.solaredge_modbus_multi.hub import (
    DataUpdateFailed,
    async_update_with_retry,
    async_write_with_retry,
)

ENTRY_DATA = {CONF_NAME: "SolarEdge", CONF_HOST: "127.0.0.1", CONF_PORT: 1502}


def _retries() -> int:
    return int(RetrySettings.RequestRetries)


async def test_update_with_retry_returns_after_one_successful_call():
    """Test update with retry returns after one successful call."""
    component = SimpleNamespace(async_update=AsyncMock())

    assert await async_update_with_retry(component) is None

    component.async_update.assert_awaited_once()


async def test_update_with_retry_recovers_from_transient_errors():
    """Test update with retry recovers from transient errors."""
    component = SimpleNamespace(
        async_update=AsyncMock(
            side_effect=[ModbusTimeoutError(), ModbusConnectionError(), None]
        )
    )

    await async_update_with_retry(component)

    assert component.async_update.await_count == 3


async def test_update_with_retry_raises_last_error_when_exhausted():
    """Test update with retry raises last error when exhausted."""
    component = SimpleNamespace(
        async_update=AsyncMock(side_effect=ModbusTimeoutError())
    )

    with pytest.raises(ModbusTimeoutError):
        await async_update_with_retry(component)

    assert component.async_update.await_count == _retries()


async def test_update_with_retry_does_not_retry_other_errors():
    """Test update with retry does not retry other errors."""
    component = SimpleNamespace(async_update=AsyncMock(side_effect=ValueError()))

    with pytest.raises(ValueError):
        await async_update_with_retry(component)

    component.async_update.assert_awaited_once()


async def test_write_with_retry_returns_after_one_successful_call():
    """Test write with retry returns after one successful call."""
    component = SimpleNamespace(write=AsyncMock())

    assert await async_write_with_retry(component, "field", 5) is None

    component.write.assert_awaited_once_with("field", 5)


async def test_write_with_retry_recovers_from_transient_errors():
    """Test write with retry recovers from transient errors."""
    component = SimpleNamespace(
        write=AsyncMock(side_effect=[ModbusTimeoutError(), None])
    )

    await async_write_with_retry(component, "field", 5)

    assert component.write.await_count == 2


async def test_write_with_retry_raises_last_error_when_exhausted():
    """Test write with retry raises last error when exhausted."""
    component = SimpleNamespace(write=AsyncMock(side_effect=ModbusConnectionError()))

    with pytest.raises(ModbusConnectionError):
        await async_write_with_retry(component, "field", 5)

    assert component.write.await_count == _retries()


def _make_coordinator(hass, refresh):
    hass.data[DOMAIN] = {"yaml": {}}
    hub = SimpleNamespace(async_refresh_modbus_data=refresh)
    return SolarEdgeCoordinator(hass, hub, 30)


async def test_coordinator_retry_returns_first_successful_result(hass):
    """Test coordinator retry returns first successful result."""
    refresh = AsyncMock(return_value=True)
    coordinator = _make_coordinator(hass, refresh)

    assert await coordinator._refresh_modbus_data_with_retry() is True
    refresh.assert_awaited_once()


async def test_coordinator_retry_waits_with_growing_delay_between_attempts(hass):
    """Test coordinator retry waits with growing delay between attempts."""
    refresh = AsyncMock(
        side_effect=[DataUpdateFailed("a"), DataUpdateFailed("b"), True]
    )
    coordinator = _make_coordinator(hass, refresh)

    with patch(
        "custom_components.solaredge_modbus_multi.asyncio.sleep", new=AsyncMock()
    ) as sleep:
        result = await coordinator._refresh_modbus_data_with_retry(
            ex_type=DataUpdateFailed, limit=5, wait_ms=100, wait_ratio=2
        )

    assert result is True
    assert [call.args[0] for call in sleep.await_args_list] == [0.1, 0.2]


async def test_coordinator_retry_reraises_original_error_when_exhausted(hass):
    """Test coordinator retry reraises original error when exhausted."""
    error = DataUpdateFailed("still failing")
    refresh = AsyncMock(side_effect=error)
    coordinator = _make_coordinator(hass, refresh)

    with (
        patch(
            "custom_components.solaredge_modbus_multi.asyncio.sleep", new=AsyncMock()
        ),
        pytest.raises(DataUpdateFailed) as exc_info,
    ):
        await coordinator._refresh_modbus_data_with_retry(
            ex_type=DataUpdateFailed, limit=3
        )

    assert exc_info.value is error
    assert refresh.await_count == 3


async def test_coordinator_retry_does_not_retry_unexpected_error_types(hass):
    """Test coordinator retry does not retry unexpected error types."""
    refresh = AsyncMock(side_effect=KeyError("boom"))
    coordinator = _make_coordinator(hass, refresh)

    with pytest.raises(KeyError):
        await coordinator._refresh_modbus_data_with_retry(
            ex_type=DataUpdateFailed, limit=3
        )

    refresh.assert_awaited_once()


def _device(*identifiers):
    return SimpleNamespace(device_info={"identifiers": set(identifiers)})


def _removal_hass(hass, entry_id="entry1"):
    hub = SimpleNamespace(
        inverters=[_device((DOMAIN, "inverter_1"), ("other", "inverter_1"))],
        meters=[_device((DOMAIN, "inverter_1_meter_1"))],
        batteries=[_device((DOMAIN, "inverter_1_battery_1"))],
    )
    hass.data[DOMAIN] = {entry_id: {"hub": hub}}
    return SimpleNamespace(entry_id=entry_id)


@pytest.mark.parametrize(
    "in_use", ["inverter_1", "inverter_1_meter_1", "inverter_1_battery_1"]
)
async def test_remove_device_refused_when_device_is_in_use(hass, in_use):
    """Test remove device refused when device is in use."""
    config_entry = _removal_hass(hass)
    device_entry = SimpleNamespace(identifiers={(DOMAIN, in_use)})

    assert (
        await async_remove_config_entry_device(hass, config_entry, device_entry)
        is False
    )


async def test_remove_device_allowed_when_device_is_unknown(hass):
    """Test remove device allowed when device is unknown."""
    config_entry = _removal_hass(hass)
    device_entry = SimpleNamespace(
        identifiers={(DOMAIN, "inverter_9"), ("other", "inverter_1")}
    )

    assert (
        await async_remove_config_entry_device(hass, config_entry, device_entry) is True
    )
