"""Tests for the SolarEdge Modbus Multi integration setup."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solaredge_modbus_multi import (
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.solaredge_modbus_multi.const import DOMAIN
from custom_components.solaredge_modbus_multi.hub import HubInitFailed
from tests.conftest import connection_double


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield


@pytest.fixture
def mock_config_entry(hass, mock_config_entry_data, mock_config_entry_options):
    """Create a mock config entry."""
    entry = MockConfigEntry(
        version=2,
        minor_version=1,
        domain=DOMAIN,
        title="Test SolarEdge",
        data=mock_config_entry_data,
        source="user",
        unique_id="192.168.1.100:1502",
        options=mock_config_entry_options,
    )
    entry.add_to_hass(hass)
    return entry


async def test_async_setup(hass: HomeAssistant) -> None:
    """Test async_setup initializes domain data."""
    result = await async_setup(hass, {})
    assert result is True
    assert DOMAIN in hass.data
    assert "yaml" in hass.data[DOMAIN]


async def test_async_setup_with_yaml_config(hass: HomeAssistant) -> None:
    """Test async_setup with YAML configuration."""
    yaml_config = {
        DOMAIN: {
            "retry": {
                "limit": 5,
                "time": 200,
                "ratio": 3,
            },
            "modbus": {
                "timeout": 5,
                "retries": 2,
            },
        }
    }
    result = await async_setup(hass, yaml_config)
    assert result is True
    assert hass.data[DOMAIN]["yaml"] == yaml_config[DOMAIN]


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        # retry.limit <= 0 used to mean an infinite coordinator retry
        # loop with unbounded backoff — now rejected at the schema.
        ("retry", "limit", 0),
        ("retry", "limit", -1),
        ("retry", "limit", 101),
        ("retry", "ratio", 0),
        ("retry", "time", 5),
        ("retry", "time", 60001),
        ("modbus", "timeout", 0),
        ("modbus", "retries", -1),
        ("modbus", "retries", 11),
        ("modbus", "reconnect_delay", -0.1),
        ("modbus", "reconnect_delay_max", 601),
    ],
)
def test_yaml_schema_rejects_out_of_range(section, key, value) -> None:
    """Advanced YAML knobs are bounded; out-of-range values fail validation."""
    import voluptuous as vol

    from custom_components.solaredge_modbus_multi import CONFIG_SCHEMA

    with pytest.raises(vol.Invalid):
        CONFIG_SCHEMA({DOMAIN: {section: {key: value}}})


@pytest.mark.parametrize(
    ("section", "config"),
    [
        ("retry", {"limit": 1, "time": 800, "ratio": 3}),
        ("retry", {"limit": 100}),
        ("modbus", {"timeout": 3, "retries": 0, "reconnect_delay": 0}),
        ("modbus", {"reconnect_delay": 300.0, "reconnect_delay_max": 600.0}),
    ],
)
def test_yaml_schema_accepts_defaults_and_bounds(section, config) -> None:
    """Documented defaults and boundary values remain valid."""
    from custom_components.solaredge_modbus_multi import CONFIG_SCHEMA

    validated = CONFIG_SCHEMA({DOMAIN: {section: config}})
    assert validated[DOMAIN][section] == config


async def test_async_setup_entry_success(
    hass: HomeAssistant,
    mock_config_entry,
    mock_modbus_client,
    mock_inverter_registers,
    mock_inverter_model_registers,
) -> None:
    """Test successful setup of config entry."""
    from tests.conftest import create_modbus_response

    # Initialize domain data via async_setup
    await async_setup(hass, {})

    # Setup mock responses
    mock_client = mock_modbus_client.return_value

    def mock_read(address, count, **kwargs):
        if address == 40000:
            return create_modbus_response(mock_inverter_registers)
        elif address == 40044:
            # Merged read: 8 (version) + 17 (gap) + 40 (model) = 65
            return create_modbus_response(
                [0] * 8 + [0] * 17 + mock_inverter_model_registers
            )
        elif address == 40121:
            # MMPPT common - return not implemented
            return create_modbus_response([0xFFFF] * count)
        else:
            return create_modbus_response([0] * count)

    mock_client.read_holding_registers = AsyncMock(side_effect=mock_read)

    with patch(
        "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection",
        mock_modbus_client,
    ):
        # Use hass.config_entries.async_setup for proper state management
        result = await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert result is True
    assert mock_config_entry.runtime_data is not None


async def test_async_setup_entry_connection_failed(
    hass: HomeAssistant,
    mock_config_entry,
) -> None:
    """Test setup fails with ConfigEntryNotReady on connection error."""
    # Initialize domain data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["yaml"] = {}

    with patch(
        "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection"
    ) as mock_client:
        mock_client.return_value = connection_double()
        mock_instance = mock_client.return_value
        mock_instance.connect = AsyncMock(side_effect=ConnectionError("Failed"))
        mock_instance.connected = False

        with pytest.raises(ConfigEntryNotReady):
            mock_config_entry.mock_state(
                hass, config_entries.ConfigEntryState.SETUP_IN_PROGRESS
            )
            await async_setup_entry(hass, mock_config_entry)


async def test_async_unload_entry(
    hass: HomeAssistant,
    mock_config_entry,
    mock_modbus_client,
    mock_inverter_registers,
    mock_inverter_model_registers,
) -> None:
    """Test unloading a config entry cleans up hub resources."""
    from tests.conftest import create_modbus_response

    # Initialize domain data via async_setup
    await async_setup(hass, {})

    # Setup mock responses
    mock_client = mock_modbus_client.return_value

    def mock_read(address, count, **kwargs):
        if address == 40000:
            return create_modbus_response(mock_inverter_registers)
        elif address == 40044:
            # Merged read: 8 (version) + 17 (gap) + 40 (model) = 65
            return create_modbus_response(
                [0] * 8 + [0] * 17 + mock_inverter_model_registers
            )
        else:
            return create_modbus_response([0] * count)

    mock_client.read_holding_registers = AsyncMock(side_effect=mock_read)

    with patch(
        "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection",
        mock_modbus_client,
    ):
        # Setup the entry using proper state management
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        # Verify entry is loaded and hub exists
        assert mock_config_entry.runtime_data is not None
        hub = mock_config_entry.runtime_data.hub
        coordinator = mock_config_entry.runtime_data.coordinator
        assert hub is not None
        assert coordinator is not None

        # Shutdown coordinator to stop refresh timer before unload
        await coordinator.async_shutdown()

        # Test unload by calling async_unload_entry directly with mocked platforms
        # This tests our cleanup logic without depending on platform unload
        with patch.object(
            hass.config_entries,
            "async_unload_platforms",
            return_value=True,
        ):
            result = await async_unload_entry(hass, mock_config_entry)
            await hass.async_block_till_done()

    # Verify unload succeeded and data was cleaned up
    assert result is True
    # runtime_data is dropped by HA when the entry unloads


async def test_async_setup_entry_hub_init_failed(
    hass: HomeAssistant,
    mock_config_entry,
) -> None:
    """Test setup fails with ConfigEntryNotReady on HubInitFailed."""
    # Initialize domain data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["yaml"] = {}

    with patch(
        "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection"
    ) as mock_client:
        mock_client.return_value = connection_double()
        mock_instance = mock_client.return_value
        mock_instance.connect = AsyncMock(side_effect=HubInitFailed("Hub init error"))
        mock_instance.connected = False

        with pytest.raises(ConfigEntryNotReady):
            mock_config_entry.mock_state(
                hass, config_entries.ConfigEntryState.SETUP_IN_PROGRESS
            )
            await async_setup_entry(hass, mock_config_entry)


async def test_async_setup_entry_data_update_failed(
    hass: HomeAssistant,
    mock_config_entry,
    mock_modbus_client,
) -> None:
    """Test setup fails with ConfigEntryNotReady on DataUpdateFailed."""
    from custom_components.solaredge_modbus_multi.hub import DataUpdateFailed

    # Initialize domain data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["yaml"] = {}

    mock_client = mock_modbus_client.return_value
    mock_client.read_holding_registers = AsyncMock(
        side_effect=DataUpdateFailed("Data update failed")
    )

    with patch(
        "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection",
        mock_modbus_client,
    ):
        with pytest.raises(ConfigEntryNotReady):
            mock_config_entry.mock_state(
                hass, config_entries.ConfigEntryState.SETUP_IN_PROGRESS
            )
            await async_setup_entry(hass, mock_config_entry)


async def test_setup_entry_failure_calls_shutdown(
    hass: HomeAssistant,
    mock_config_entry,
) -> None:
    """A failed first refresh must shut the hub down before the retry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["yaml"] = {}

    with patch(
        "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection"
    ) as mock_client:
        mock_client.return_value = connection_double()
        mock_instance = mock_client.return_value
        mock_instance.connect = AsyncMock(side_effect=HubInitFailed("Hub init error"))
        mock_instance.connected = False

        with patch(
            "custom_components.solaredge_modbus_multi.hub."
            "SolarEdgeModbusMultiHub.shutdown",
            new_callable=AsyncMock,
        ) as mock_shutdown:
            with pytest.raises(ConfigEntryNotReady):
                mock_config_entry.mock_state(
                    hass, config_entries.ConfigEntryState.SETUP_IN_PROGRESS
                )
                await async_setup_entry(hass, mock_config_entry)

            assert mock_shutdown.await_count >= 1


async def test_unload_entry_platforms_before_shutdown(hass: HomeAssistant) -> None:
    """Platforms unload first; the hub shuts down only on success."""
    order: list[str] = []

    hub = MagicMock()

    async def record_shutdown():
        order.append("shutdown")

    hub.shutdown = record_shutdown
    entry = MagicMock()
    entry.runtime_data = SimpleNamespace(hub=hub)

    async def record_unload(_entry, _platforms):
        order.append("unload_platforms")
        return True

    with patch.object(
        hass.config_entries, "async_unload_platforms", side_effect=record_unload
    ):
        assert await async_unload_entry(hass, entry) is True

    assert order == ["unload_platforms", "shutdown"]


async def test_unload_entry_keeps_hub_when_platform_unload_fails(
    hass: HomeAssistant,
) -> None:
    """A failed platform unload must leave the hub running for its entities."""
    hub = MagicMock()
    hub.shutdown = AsyncMock()
    entry = MagicMock()
    entry.runtime_data = SimpleNamespace(hub=hub)

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        new_callable=AsyncMock,
        return_value=False,
    ):
        assert await async_unload_entry(hass, entry) is False

    hub.shutdown.assert_not_awaited()


async def test_async_migrate_entry_v1_to_v2(hass: HomeAssistant) -> None:
    """Test migration from version 1 to version 2."""
    from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL

    from custom_components.solaredge_modbus_multi import async_migrate_entry
    from custom_components.solaredge_modbus_multi.const import ConfName

    # Create a version 1 config entry
    entry = MockConfigEntry(
        version=1,
        minor_version=0,
        domain=DOMAIN,
        title="Test SolarEdge",
        data={
            CONF_HOST: "192.168.1.100",
            CONF_PORT: 1502,
            CONF_NAME: "Test SolarEdge",
            ConfName.DEVICE_ID: 1,
            ConfName.NUMBER_INVERTERS: 3,
            CONF_SCAN_INTERVAL: 300,
        },
        options={},
        source="user",
    )
    entry.add_to_hass(hass)

    # Run migration
    result = await async_migrate_entry(hass, entry)

    # Verify migration succeeded
    assert result is True
    assert entry.version == 2
    # Migration runs both v1->v2 and v2.0->v2.1, so minor version ends at 1
    assert entry.minor_version == 1

    # Verify data migration
    assert ConfName.DEVICE_LIST in entry.data
    assert entry.data[ConfName.DEVICE_LIST] == [1, 2, 3]
    assert ConfName.DEVICE_ID not in entry.data
    assert ConfName.NUMBER_INVERTERS not in entry.data

    # Verify scan_interval moved to options
    assert CONF_SCAN_INTERVAL not in entry.data
    assert CONF_SCAN_INTERVAL in entry.options
    assert entry.options[CONF_SCAN_INTERVAL] == 300

    # Verify unique_id was also updated (from v2.0->v2.1 migration)
    assert entry.unique_id == "192.168.1.100:1502"


async def test_async_migrate_entry_v2_0_to_v2_1(hass: HomeAssistant) -> None:
    """Test migration from version 2.0 to version 2.1."""
    from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT

    from custom_components.solaredge_modbus_multi import async_migrate_entry
    from custom_components.solaredge_modbus_multi.const import ConfName

    # Create a version 2.0 config entry
    entry = MockConfigEntry(
        version=2,
        minor_version=0,
        domain=DOMAIN,
        title="Test SolarEdge",
        data={
            CONF_HOST: "192.168.1.100",
            CONF_PORT: 1502,
            CONF_NAME: "Test SolarEdge",
            ConfName.DEVICE_LIST: [1, 2],
        },
        options={},
        source="user",
        unique_id="old_unique_id",
    )
    entry.add_to_hass(hass)

    # Run migration
    result = await async_migrate_entry(hass, entry)

    # Verify migration succeeded
    assert result is True
    assert entry.version == 2
    assert entry.minor_version == 1

    # Verify unique_id was updated to host:port format
    assert entry.unique_id == "192.168.1.100:1502"


async def test_async_migrate_entry_unsupported_version(hass: HomeAssistant) -> None:
    """Test migration fails for unsupported version."""
    from homeassistant.const import CONF_HOST, CONF_PORT

    from custom_components.solaredge_modbus_multi import async_migrate_entry

    # Create a version 3 config entry (unsupported)
    entry = MockConfigEntry(
        version=3,
        minor_version=0,
        domain=DOMAIN,
        title="Test SolarEdge",
        data={
            CONF_HOST: "192.168.1.100",
            CONF_PORT: 1502,
        },
        options={},
        source="user",
    )
    entry.add_to_hass(hass)

    # Run migration
    result = await async_migrate_entry(hass, entry)

    # Verify migration failed
    assert result is False


async def test_setup_entry_registers_no_update_listener(
    hass: HomeAssistant,
    mock_config_entry,
    mock_modbus_client,
    mock_inverter_registers,
    mock_inverter_model_registers,
) -> None:
    """No config-entry update listener: reloads belong to the flows.

    A listener combined with OptionsFlowWithReload raises ValueError in
    the options-flow manager, and combined with flow reload helpers it
    double-reloads (an error from HA 2026.12).
    """
    from tests.conftest import create_modbus_response

    await async_setup(hass, {})

    mock_client = mock_modbus_client.return_value

    def mock_read(address, count, **kwargs):
        if address == 40000:
            return create_modbus_response(mock_inverter_registers)
        elif address == 40044:
            return create_modbus_response(
                [0] * 8 + [0] * 17 + mock_inverter_model_registers
            )
        else:
            return create_modbus_response([0] * count)

    mock_client.read_holding_registers = AsyncMock(side_effect=mock_read)

    with patch(
        "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection",
        mock_modbus_client,
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.update_listeners == []

    await mock_config_entry.runtime_data.coordinator.async_shutdown()


async def test_async_remove_config_entry_device_in_use(
    hass: HomeAssistant,
    mock_config_entry,
    mock_modbus_client,
    mock_inverter_registers,
    mock_inverter_model_registers,
) -> None:
    """Test device removal fails if device is in use."""
    from homeassistant.helpers import device_registry as dr

    from custom_components.solaredge_modbus_multi import (
        async_remove_config_entry_device,
    )
    from tests.conftest import create_modbus_response

    # Initialize domain data via async_setup
    await async_setup(hass, {})

    # Setup mock responses
    mock_client = mock_modbus_client.return_value

    def mock_read(address, count, **kwargs):
        if address == 40000:
            return create_modbus_response(mock_inverter_registers)
        elif address == 40044:
            # Merged read: 8 (version) + 17 (gap) + 40 (model) = 65
            return create_modbus_response(
                [0] * 8 + [0] * 17 + mock_inverter_model_registers
            )
        else:
            return create_modbus_response([0] * count)

    mock_client.read_holding_registers = AsyncMock(side_effect=mock_read)

    with patch(
        "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection",
        mock_modbus_client,
    ):
        # Setup the entry using proper state management
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        # Get the hub to find device identifiers
        hub = mock_config_entry.runtime_data.hub

        # Create a device entry for an inverter
        device_registry = dr.async_get(hass)
        device_entry = device_registry.async_get_or_create(
            config_entry_id=mock_config_entry.entry_id,
            identifiers={(DOMAIN, hub.inverters[0].uid_base)},
            name="Test Inverter",
        )

        # Try to remove device
        result = await async_remove_config_entry_device(
            hass, mock_config_entry, device_entry
        )

        # Should fail because device is in use
        assert result is False


async def test_async_remove_config_entry_device_not_in_use(
    hass: HomeAssistant,
    mock_config_entry,
    mock_modbus_client,
    mock_inverter_registers,
    mock_inverter_model_registers,
) -> None:
    """Test device removal succeeds if device is not in use."""
    from homeassistant.helpers import device_registry as dr

    from custom_components.solaredge_modbus_multi import (
        async_remove_config_entry_device,
    )
    from tests.conftest import create_modbus_response

    # Initialize domain data via async_setup
    await async_setup(hass, {})

    # Setup mock responses
    mock_client = mock_modbus_client.return_value

    def mock_read(address, count, **kwargs):
        if address == 40000:
            return create_modbus_response(mock_inverter_registers)
        elif address == 40044:
            # Merged read: 8 (version) + 17 (gap) + 40 (model) = 65
            return create_modbus_response(
                [0] * 8 + [0] * 17 + mock_inverter_model_registers
            )
        else:
            return create_modbus_response([0] * count)

    mock_client.read_holding_registers = AsyncMock(side_effect=mock_read)

    with patch(
        "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection",
        mock_modbus_client,
    ):
        # Setup the entry using proper state management
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        # Create a device entry with an unknown identifier
        device_registry = dr.async_get(hass)
        device_entry = device_registry.async_get_or_create(
            config_entry_id=mock_config_entry.entry_id,
            identifiers={(DOMAIN, "unknown_device")},
            name="Unknown Device",
        )

        # Try to remove device
        result = await async_remove_config_entry_device(
            hass, mock_config_entry, device_entry
        )

        # Should succeed because device is not in use
        assert result is True


async def test_coordinator_update_with_pending_writes(
    hass: HomeAssistant,
    mock_config_entry,
    mock_modbus_client,
    mock_inverter_registers,
    mock_inverter_model_registers,
) -> None:
    """Test coordinator waits for pending writes before updating."""
    from tests.conftest import create_modbus_response

    # Initialize domain data via async_setup
    await async_setup(hass, {})

    # Setup mock responses
    mock_client = mock_modbus_client.return_value

    def mock_read(address, count, **kwargs):
        if address == 40000:
            return create_modbus_response(mock_inverter_registers)
        elif address == 40044:
            # Merged read: 8 (version) + 17 (gap) + 40 (model) = 65
            return create_modbus_response(
                [0] * 8 + [0] * 17 + mock_inverter_model_registers
            )
        else:
            return create_modbus_response([0] * count)

    mock_client.read_holding_registers = AsyncMock(side_effect=mock_read)

    with patch(
        "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection",
        mock_modbus_client,
    ):
        # Setup the entry using proper state management
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        hub = mock_config_entry.runtime_data.hub
        coordinator = mock_config_entry.runtime_data.coordinator

        # Simulate pending write
        hub._has_write = True

        # Create a task to clear the write flag after a short delay
        async def clear_write():
            await asyncio.sleep(0.2)
            hub._has_write = False

        task = asyncio.create_task(clear_write())

        # Run update (should wait for write to complete)
        await coordinator.async_refresh()

        # Wait for background task to complete
        await task

        # Verify update completed after write cleared
        assert hub._has_write is False


async def test_coordinator_retry_logic_success_on_retry(
    hass: HomeAssistant,
    mock_config_entry,
    mock_modbus_client,
    mock_inverter_registers,
    mock_inverter_model_registers,
) -> None:
    """Test coordinator retry logic succeeds on retry."""
    from custom_components.solaredge_modbus_multi.hub import DataUpdateFailed
    from tests.conftest import create_modbus_response

    # Initialize domain data with retry settings via async_setup
    await async_setup(
        hass,
        {
            DOMAIN: {
                "retry": {
                    "limit": 3,
                    "time": 10,
                    "ratio": 2,
                }
            }
        },
    )

    # Setup mock responses - fail once, then succeed
    mock_client = mock_modbus_client.return_value
    call_count = 0

    def mock_read(address, count, **kwargs):
        nonlocal call_count
        call_count += 1

        # Fail on first call
        if call_count == 1:
            raise DataUpdateFailed("First attempt failed")

        # Succeed on subsequent calls
        if address == 40000:
            return create_modbus_response(mock_inverter_registers)
        elif address == 40044:
            # Merged read: 8 (version) + 17 (gap) + 40 (model) = 65
            return create_modbus_response(
                [0] * 8 + [0] * 17 + mock_inverter_model_registers
            )
        else:
            return create_modbus_response([0] * count)

    mock_client.read_holding_registers = AsyncMock(side_effect=mock_read)

    with patch(
        "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection",
        mock_modbus_client,
    ):
        # Setup the entry using proper state management
        result = await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        # Verify setup succeeded after retry
        assert result is True


async def test_coordinator_retry_logic_exhausted(
    hass: HomeAssistant,
    mock_config_entry,
    mock_modbus_client,
) -> None:
    """Test coordinator retry logic fails after exhausting retries."""
    from custom_components.solaredge_modbus_multi.hub import DataUpdateFailed

    # Initialize domain data with limited retries
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["yaml"] = {
        "retry": {
            "limit": 2,
            "time": 5,
            "ratio": 1,
        }
    }

    # Setup mock to always fail
    mock_client = mock_modbus_client.return_value
    mock_client.read_holding_registers = AsyncMock(
        side_effect=DataUpdateFailed("Always fails")
    )

    with patch(
        "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection",
        mock_modbus_client,
    ):
        # Setup should fail after retries exhausted
        with pytest.raises(ConfigEntryNotReady):
            mock_config_entry.mock_state(
                hass, config_entries.ConfigEntryState.SETUP_IN_PROGRESS
            )
            await async_setup_entry(hass, mock_config_entry)


async def test_coordinator_update_raises_update_failed_on_hub_init_failed(
    hass: HomeAssistant,
    mock_config_entry,
    mock_modbus_client,
    mock_inverter_registers,
    mock_inverter_model_registers,
) -> None:
    """Test coordinator converts HubInitFailed to UpdateFailed."""
    from homeassistant.helpers.update_coordinator import UpdateFailed

    from tests.conftest import create_modbus_response

    # Initialize domain data via async_setup
    await async_setup(hass, {})

    # Setup mock responses for initial setup
    mock_client = mock_modbus_client.return_value

    def mock_read(address, count, **kwargs):
        if address == 40000:
            return create_modbus_response(mock_inverter_registers)
        elif address == 40044:
            # Merged read: 8 (version) + 17 (gap) + 40 (model) = 65
            return create_modbus_response(
                [0] * 8 + [0] * 17 + mock_inverter_model_registers
            )
        else:
            return create_modbus_response([0] * count)

    mock_client.read_holding_registers = AsyncMock(side_effect=mock_read)

    with patch(
        "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection",
        mock_modbus_client,
    ):
        # Setup the entry using proper state management
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        coordinator = mock_config_entry.runtime_data.coordinator

        # Mock hub to raise HubInitFailed on next refresh
        with patch.object(
            coordinator._hub,
            "async_refresh_modbus_data",
            side_effect=HubInitFailed("Connection lost"),
        ):
            # Call _async_update_data directly to test exception conversion
            with pytest.raises(UpdateFailed):
                await coordinator._async_update_data()


async def test_coordinator_update_raises_update_failed_on_data_update_failed(
    hass: HomeAssistant,
    mock_config_entry,
    mock_modbus_client,
    mock_inverter_registers,
    mock_inverter_model_registers,
) -> None:
    """Test coordinator converts DataUpdateFailed to UpdateFailed."""
    from homeassistant.helpers.update_coordinator import UpdateFailed

    from custom_components.solaredge_modbus_multi.hub import DataUpdateFailed
    from tests.conftest import create_modbus_response

    # Initialize domain data via async_setup
    await async_setup(hass, {})

    # Setup mock responses for initial setup
    mock_client = mock_modbus_client.return_value

    def mock_read(address, count, **kwargs):
        if address == 40000:
            return create_modbus_response(mock_inverter_registers)
        elif address == 40044:
            # Merged read: 8 (version) + 17 (gap) + 40 (model) = 65
            return create_modbus_response(
                [0] * 8 + [0] * 17 + mock_inverter_model_registers
            )
        else:
            return create_modbus_response([0] * count)

    mock_client.read_holding_registers = AsyncMock(side_effect=mock_read)

    with patch(
        "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection",
        mock_modbus_client,
    ):
        # Setup the entry using proper config entry lifecycle
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        coordinator = mock_config_entry.runtime_data.coordinator

        # Mock hub to raise DataUpdateFailed on next refresh
        with patch.object(
            coordinator._hub,
            "async_refresh_modbus_data",
            side_effect=DataUpdateFailed("Data read failed"),
        ):
            # Call _async_update_data directly to test exception conversion
            with pytest.raises(UpdateFailed):
                await coordinator._async_update_data()


async def test_setup_entry_platform_failure_shuts_hub_down(
    hass: HomeAssistant,
    mock_config_entry,
    mock_modbus_client,
    mock_inverter_registers,
    mock_inverter_model_registers,
) -> None:
    """A failed platform forward must not leak the connected modbus session."""
    from tests.conftest import create_modbus_response

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["yaml"] = {}

    mock_client = mock_modbus_client.return_value

    def mock_read(address, count, **kwargs):
        if address == 40000:
            return create_modbus_response(mock_inverter_registers)
        elif address == 40044:
            return create_modbus_response(
                [0] * 8 + [0] * 17 + mock_inverter_model_registers
            )
        else:
            return create_modbus_response([0] * count)

    mock_client.read_holding_registers = AsyncMock(side_effect=mock_read)

    with patch(
        "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection",
        mock_modbus_client,
    ):
        with (
            patch.object(
                hass.config_entries,
                "async_forward_entry_setups",
                new_callable=AsyncMock,
                side_effect=ImportError("broken platform"),
            ),
            patch(
                "custom_components.solaredge_modbus_multi.hub."
                "SolarEdgeModbusMultiHub.shutdown",
                new_callable=AsyncMock,
            ) as mock_shutdown,
        ):
            mock_config_entry.mock_state(
                hass, config_entries.ConfigEntryState.SETUP_IN_PROGRESS
            )
            with pytest.raises(ImportError):
                await async_setup_entry(hass, mock_config_entry)

            assert mock_shutdown.await_count >= 1


async def test_setup_entry_registers_inverters_before_platforms(
    hass: HomeAssistant,
    mock_config_entry,
    mock_modbus_client,
    mock_inverter_registers,
    mock_inverter_model_registers,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Children link by registry id, so inverters are registered before any entity."""
    from tests.conftest import create_modbus_response

    await async_setup(hass, {})

    mock_client = mock_modbus_client.return_value

    def mock_read(address, count, **kwargs):
        if address == 40000:
            return create_modbus_response(mock_inverter_registers)
        elif address == 40044:
            return create_modbus_response(
                [0] * 8 + [0] * 17 + mock_inverter_model_registers
            )
        elif address == 40121:
            return create_modbus_response([0xFFFF] * count)
        else:
            return create_modbus_response([0] * count)

    mock_client.read_holding_registers = AsyncMock(side_effect=mock_read)

    # What the inverters carried at the moment platforms were forwarded
    ids_at_forward: dict[str, str | None] = {}
    original_forward = hass.config_entries.async_forward_entry_setups

    async def capture_forward(entry, platforms):
        hub = entry.runtime_data.hub
        ids_at_forward.update(
            {inv.uid_base: inv.registry_device_id for inv in hub.inverters}
        )
        await original_forward(entry, platforms)

    with (
        patch(
            "custom_components.solaredge_modbus_multi.modbus_transport."
            "ModbusConnection",
            mock_modbus_client,
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            side_effect=capture_forward,
        ),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    registry = dr.async_get(hass)
    assert ids_at_forward
    for uid_base, registry_id in ids_at_forward.items():
        assert registry_id is not None
        device = registry.async_get(registry_id)
        assert device is not None
        assert (DOMAIN, uid_base) in device.identifiers
        assert device.config_entry_id == mock_config_entry.entry_id

    assert "via_device" not in caplog.text
    assert "deprecated" not in caplog.text


async def test_setup_entry_registration_failure_shuts_hub_down(
    hass: HomeAssistant,
    mock_config_entry,
    mock_modbus_client,
    mock_inverter_registers,
    mock_inverter_model_registers,
) -> None:
    """A registry error before platform forward must not leak the session either."""
    from tests.conftest import create_modbus_response

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["yaml"] = {}

    mock_client = mock_modbus_client.return_value

    def mock_read(address, count, **kwargs):
        if address == 40000:
            return create_modbus_response(mock_inverter_registers)
        elif address == 40044:
            return create_modbus_response(
                [0] * 8 + [0] * 17 + mock_inverter_model_registers
            )
        else:
            return create_modbus_response([0] * count)

    mock_client.read_holding_registers = AsyncMock(side_effect=mock_read)

    with patch(
        "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection",
        mock_modbus_client,
    ):
        with (
            patch.object(
                dr.DeviceRegistry,
                "async_get_or_create",
                side_effect=HomeAssistantError("registry refused the inverter"),
            ),
            patch.object(
                hass.config_entries,
                "async_forward_entry_setups",
                new_callable=AsyncMock,
            ) as mock_forward,
            patch(
                "custom_components.solaredge_modbus_multi.hub."
                "SolarEdgeModbusMultiHub.shutdown",
                new_callable=AsyncMock,
            ) as mock_shutdown,
        ):
            mock_config_entry.mock_state(
                hass, config_entries.ConfigEntryState.SETUP_IN_PROGRESS
            )
            with pytest.raises(HomeAssistantError):
                await async_setup_entry(hass, mock_config_entry)

            mock_forward.assert_not_awaited()
            assert mock_shutdown.await_count >= 1
