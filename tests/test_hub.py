"""Tests for the SolarEdge Modbus Multi hub."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from pymodbus.exceptions import ConnectionException, ModbusIOException

try:
    from pymodbus.pdu.pdu import ExceptionResponse  # noqa: F401
except ImportError:
    pass

from custom_components.solaredge_modbus_multi.const import DOMAIN, ModbusExceptions
from custom_components.solaredge_modbus_multi.hub import (
    DataUpdateFailed,
    DeviceInvalid,
    HubInitFailed,
    ModbusIllegalAddress,
    ModbusIllegalFunction,
    ModbusIllegalValue,
    ModbusIOError,
    ModbusReadError,
    SolarEdgeBattery,
    SolarEdgeInverter,
    SolarEdgeMeter,
    SolarEdgeModbusMultiHub,
)


@pytest.fixture
def mock_hub(hass, mock_config_entry_data, mock_config_entry_options):
    """Create a mock hub instance."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["yaml"] = {}

    hub = SolarEdgeModbusMultiHub(
        hass,
        entry_id="test_entry",
        entry_data=mock_config_entry_data,
        entry_options=mock_config_entry_options,
    )
    return hub


async def test_hub_connect(mock_hub, mock_modbus_client) -> None:
    """Test hub connection."""
    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

    assert mock_hub._client is not None
    mock_modbus_client.return_value.connect.assert_called_once()


async def test_hub_concurrent_connect_is_idempotent(
    mock_hub, mock_modbus_client
) -> None:
    """Concurrent callers share one connection attempt."""
    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await asyncio.gather(mock_hub.connect(), mock_hub.connect())

    mock_modbus_client.assert_called_once()
    mock_modbus_client.return_value.connect.assert_awaited_once()
    assert mock_hub._transport.stats.connects == 1
    assert mock_hub._transport.stats.reconnects == 0


async def test_hub_reconnects_existing_disconnected_client(
    mock_hub, mock_modbus_client
) -> None:
    """A disconnected client still performs a real reconnect."""
    mock_client = mock_modbus_client.return_value

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()
        mock_client.connect.reset_mock()
        mock_client.connected = False
        await mock_hub.connect()

    mock_modbus_client.assert_called_once()
    mock_client.connect.assert_awaited_once()
    assert mock_hub._transport.stats.connects == 1
    assert mock_hub._transport.stats.reconnects == 1


async def test_hub_disconnect(mock_hub, mock_modbus_client) -> None:
    """Test hub disconnection."""
    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()
        await mock_hub.disconnect()

    mock_modbus_client.return_value.close.assert_called_once()


async def test_hub_disconnect_clear_client(mock_hub, mock_modbus_client) -> None:
    """Test hub disconnection with client clearing."""
    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()
        await mock_hub.disconnect(clear_client=True)

    assert mock_hub._client is None


async def test_hub_read_registers(
    mock_hub, mock_modbus_client, mock_inverter_registers
) -> None:
    """Test reading modbus registers."""
    from tests.conftest import create_modbus_response

    mock_client = mock_modbus_client.return_value
    mock_client.read_holding_registers.return_value = create_modbus_response(
        mock_inverter_registers
    )

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()
        result = await mock_hub.modbus_read_holding_registers(
            unit=1, address=40000, rcount=len(mock_inverter_registers)
        )

    assert result.registers == mock_inverter_registers


async def test_hub_read_registers_error(mock_hub, mock_modbus_client) -> None:
    """Test reading modbus registers with error response."""
    mock_client = mock_modbus_client.return_value
    error_response = MagicMock()
    error_response.isError.return_value = True
    mock_client.read_holding_registers.return_value = error_response

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        with pytest.raises(ModbusReadError):
            await mock_hub.modbus_read_holding_registers(
                unit=1, address=40000, rcount=10
            )


async def test_hub_modbus_lock_prevents_race_condition(
    mock_hub, mock_modbus_client, mock_inverter_registers
) -> None:
    """Test that modbus lock prevents race conditions."""
    from tests.conftest import create_modbus_response

    mock_client = mock_modbus_client.return_value
    mock_client.read_holding_registers.return_value = create_modbus_response(
        mock_inverter_registers
    )

    # Track order of operations
    operation_order = []

    original_read = mock_client.read_holding_registers

    async def tracked_read(*args, **kwargs):
        operation_order.append(f"start_{kwargs.get('address', args[0] if args else 0)}")
        await asyncio.sleep(0.01)  # Simulate I/O delay
        result = await original_read(*args, **kwargs)
        operation_order.append(f"end_{kwargs.get('address', args[0] if args else 0)}")
        return result

    mock_client.read_holding_registers = tracked_read

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        # Run two reads concurrently
        task1 = asyncio.create_task(
            mock_hub.modbus_read_holding_registers(
                unit=1, address=40000, rcount=len(mock_inverter_registers)
            )
        )
        task2 = asyncio.create_task(
            mock_hub.modbus_read_holding_registers(
                unit=1, address=40100, rcount=len(mock_inverter_registers)
            )
        )

        await asyncio.gather(task1, task2)

    # With proper locking, operations should complete one at a time
    # (start_X, end_X, start_Y, end_Y) not interleaved
    assert len(operation_order) == 4
    # First operation should complete before second starts
    assert operation_order[1].startswith("end_")
    assert operation_order[2].startswith("start_")


async def test_hub_shutdown(mock_hub, mock_modbus_client) -> None:
    """Test hub shutdown."""
    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()
        await mock_hub.shutdown()

    assert mock_hub.online is False
    assert mock_hub._client is None


async def test_hub_properties(mock_hub) -> None:
    """Test hub property accessors."""
    assert mock_hub.name == "Test SolarEdge"
    assert mock_hub.hub_host == "192.168.1.100"
    assert mock_hub.hub_port == 1502
    assert mock_hub.keep_modbus_open is False
    assert mock_hub.number_of_inverters == 1


# Hub Initialization Error Tests


async def test_hub_init_pymodbus_version_check_fail(
    mock_hub, mock_modbus_client
) -> None:
    """Test hub initialization fails with old pymodbus version."""
    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        with patch.object(mock_hub, "_pymodbus_version", "3.0.0"):
            await mock_hub.connect()
            with pytest.raises(
                HubInitFailed, match="pymodbus version must be at least"
            ):
                await mock_hub._async_init_solaredge()


async def test_hub_init_connection_failed(mock_hub, mock_modbus_client) -> None:
    """Test hub initialization fails when not connected."""
    mock_modbus_client.return_value.connected = False

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()
        mock_hub._client.connected = False

        with pytest.raises(HubInitFailed, match="Modbus/TCP connect"):
            await mock_hub._async_init_solaredge()


async def test_hub_init_inverter_device_invalid(
    mock_hub, mock_modbus_client, mock_inverter_registers
) -> None:
    """Test hub initialization fails with invalid inverter device."""
    from tests.conftest import create_modbus_response

    # Create invalid inverter (wrong SunSpec ID)
    invalid_registers = mock_inverter_registers.copy()
    invalid_registers[0] = 0x0000
    invalid_registers[1] = 0x0000

    mock_client = mock_modbus_client.return_value
    mock_client.read_holding_registers.return_value = create_modbus_response(
        invalid_registers
    )

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        with pytest.raises(HubInitFailed, match="not a SunSpec inverter"):
            await mock_hub._async_init_solaredge()


async def test_hub_init_inverter_modbus_io_error(mock_hub, mock_modbus_client) -> None:
    """Test hub initialization fails with ModbusIOError."""
    mock_client = mock_modbus_client.return_value

    error_response = MagicMock(spec=ModbusIOException)
    error_response.isError.return_value = True
    mock_client.read_holding_registers.return_value = error_response

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        with pytest.raises(HubInitFailed):
            await mock_hub._async_init_solaredge()


async def test_hub_init_inverter_timeout_error(mock_hub, mock_modbus_client) -> None:
    """Test hub initialization fails with TimeoutError."""
    mock_client = mock_modbus_client.return_value
    mock_client.read_holding_registers.side_effect = TimeoutError("Timeout")

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        with pytest.raises(HubInitFailed, match="Timeout"):
            await mock_hub._async_init_solaredge()


@pytest.mark.parametrize("error_type", [ModbusIllegalFunction, ModbusIllegalValue])
async def test_hub_init_illegal_response_is_read_error(
    mock_hub, mock_modbus_client, error_type
) -> None:
    """Illegal function and value responses become initialization read errors."""
    mock_hub._detect_meters = False
    mock_hub._detect_batteries = False

    with (
        patch(
            "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
            mock_modbus_client,
        ),
        patch.object(SolarEdgeInverter, "init_device", new=AsyncMock()),
        patch.object(
            SolarEdgeInverter,
            "read_modbus_data",
            new=AsyncMock(side_effect=error_type("Illegal response")),
        ),
    ):
        await mock_hub.connect()

        with pytest.raises(HubInitFailed, match="Read error"):
            await mock_hub._async_init_solaredge()

    mock_modbus_client.return_value.close.assert_called_once()


# Refresh Modbus Data Tests


async def test_refresh_modbus_data_connection_failed(
    mock_hub, mock_modbus_client
) -> None:
    """Test refresh fails when connection cannot be established."""
    mock_hub._initalized = True
    mock_modbus_client.return_value.connected = False

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        mock_hub._client = mock_modbus_client.return_value

        with pytest.raises(DataUpdateFailed, match="Modbus/TCP connect"):
            await mock_hub.async_refresh_modbus_data()


async def test_refresh_modbus_data_timeout_with_retries(
    mock_hub, mock_modbus_client
) -> None:
    """Test refresh handles timeout with retry logic."""

    mock_hub._initalized = True
    mock_hub._retry_limit = 3

    # Create a mock inverter
    inverter = MagicMock()
    inverter.read_modbus_data = AsyncMock(side_effect=TimeoutError("Timeout"))
    mock_hub.inverters = [inverter]

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        # First timeout should increment counter and raise DataUpdateFailed
        with pytest.raises(DataUpdateFailed, match="Timeout"):
            await mock_hub.async_refresh_modbus_data()

        assert mock_hub._timeout_counter == 1

        # After retry_limit, should raise TimeoutError
        mock_hub._timeout_counter = mock_hub._retry_limit - 1

        with pytest.raises(TimeoutError):
            await mock_hub.async_refresh_modbus_data()

        assert mock_hub._timeout_counter == 0


async def test_refresh_modbus_data_modbus_read_error(
    mock_hub, mock_modbus_client
) -> None:
    """Test refresh fails with ModbusReadError."""
    mock_hub._initalized = True

    inverter = MagicMock()
    inverter.read_modbus_data = AsyncMock(side_effect=ModbusReadError("Read error"))
    mock_hub.inverters = [inverter]

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        with pytest.raises(DataUpdateFailed, match="Update failed"):
            await mock_hub.async_refresh_modbus_data()


@pytest.mark.parametrize("error_type", [ModbusIllegalFunction, ModbusIllegalValue])
async def test_refresh_illegal_response_is_update_error(
    mock_hub, mock_modbus_client, error_type
) -> None:
    """Illegal function and value responses become update read errors."""
    mock_hub._initalized = True

    inverter = MagicMock()
    inverter.read_modbus_data = AsyncMock(side_effect=error_type("Illegal response"))
    mock_hub.inverters = [inverter]

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        with pytest.raises(DataUpdateFailed, match="Update failed"):
            await mock_hub.async_refresh_modbus_data()

    mock_modbus_client.return_value.close.assert_called_once()


async def test_refresh_modbus_data_connection_exception(
    mock_hub, mock_modbus_client
) -> None:
    """Test refresh fails with ConnectionException."""
    mock_hub._initalized = True

    inverter = MagicMock()
    inverter.read_modbus_data = AsyncMock(
        side_effect=ConnectionException("Connection failed")
    )
    mock_hub.inverters = [inverter]

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        with pytest.raises(DataUpdateFailed, match="Connection failed"):
            await mock_hub.async_refresh_modbus_data()


# Write Register Tests


async def test_write_registers_success(mock_hub, mock_modbus_client) -> None:
    """Test successful register write."""
    mock_client = mock_modbus_client.return_value

    success_response = MagicMock()
    success_response.isError.return_value = False
    mock_client.write_registers.return_value = success_response

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()
        await mock_hub.write_registers(unit=1, address=40000, payload=[100, 200])

        mock_client.write_registers.assert_called_once()


async def test_write_registers_modbus_io_exception(
    mock_hub, mock_modbus_client
) -> None:
    """Test write fails with ModbusIOException."""
    mock_client = mock_modbus_client.return_value
    mock_client.write_registers.side_effect = ModbusIOException("IO Error")

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        with pytest.raises(HomeAssistantError, match="Error sending command"):
            await mock_hub.write_registers(unit=1, address=40000, payload=[100])


async def test_write_registers_connection_exception(
    mock_hub, mock_modbus_client
) -> None:
    """Test write fails with ConnectionException."""
    mock_client = mock_modbus_client.return_value
    mock_client.write_registers.side_effect = ConnectionException("Connection failed")

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        with pytest.raises(HomeAssistantError, match="Connection to inverter"):
            await mock_hub.write_registers(unit=1, address=40000, payload=[100])


async def test_write_registers_error_response_io_exception(
    mock_hub, mock_modbus_client
) -> None:
    """Test write fails with error response of type ModbusIOException."""
    from tests.conftest import create_io_exception_response

    mock_client = mock_modbus_client.return_value
    mock_client.write_registers.return_value = create_io_exception_response()

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        with pytest.raises(HomeAssistantError, match="No response from inverter"):
            await mock_hub.write_registers(unit=1, address=40000, payload=[100])


async def test_write_registers_illegal_address(mock_hub, mock_modbus_client) -> None:
    """Test write fails with IllegalAddress exception."""
    from tests.conftest import create_exception_response

    mock_client = mock_modbus_client.return_value
    mock_client.write_registers.return_value = create_exception_response(
        ModbusExceptions.IllegalAddress
    )

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        with pytest.raises(HomeAssistantError, match="Address not supported"):
            await mock_hub.write_registers(unit=1, address=40000, payload=[100])


async def test_write_registers_illegal_function(mock_hub, mock_modbus_client) -> None:
    """Test write fails with IllegalFunction exception."""
    from tests.conftest import create_exception_response

    mock_client = mock_modbus_client.return_value
    mock_client.write_registers.return_value = create_exception_response(
        ModbusExceptions.IllegalFunction
    )

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        with pytest.raises(HomeAssistantError, match="Function not supported"):
            await mock_hub.write_registers(unit=1, address=40000, payload=[100])


async def test_write_registers_illegal_value(mock_hub, mock_modbus_client) -> None:
    """Test write fails with IllegalValue exception."""
    from tests.conftest import create_exception_response

    mock_client = mock_modbus_client.return_value
    mock_client.write_registers.return_value = create_exception_response(
        ModbusExceptions.IllegalValue
    )

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        with pytest.raises(HomeAssistantError, match="Value invalid"):
            await mock_hub.write_registers(unit=1, address=40000, payload=[100])


async def test_write_registers_sleep_after_write(mock_hub, mock_modbus_client) -> None:
    """Test write includes sleep delay when configured."""
    mock_hub._sleep_after_write = 1
    mock_client = mock_modbus_client.return_value

    success_response = MagicMock()
    success_response.isError.return_value = False
    mock_client.write_registers.return_value = success_response

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await mock_hub.connect()
            await mock_hub.write_registers(unit=1, address=40000, payload=[100])

            mock_sleep.assert_called_once_with(1)


async def test_write_registers_cancelled_during_sleep(
    mock_hub, mock_modbus_client
) -> None:
    """A write cancelled mid-sleep must clear has_write, not leave it stuck."""
    import asyncio as aio

    mock_hub._sleep_after_write = 1
    mock_client = mock_modbus_client.return_value

    success_response = MagicMock()
    success_response.isError.return_value = False
    mock_client.write_registers.return_value = success_response

    sleeping = aio.Event()

    async def hanging_sleep(_delay):
        sleeping.set()
        await aio.Future()  # sleeps until cancelled

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        with patch(
            "custom_components.solaredge_modbus_multi.hub.asyncio.sleep",
            side_effect=hanging_sleep,
        ):
            write_task = aio.create_task(
                mock_hub.write_registers(unit=1, address=57348, payload=[1])
            )
            await sleeping.wait()
            assert mock_hub.has_write == 57348

            write_task.cancel()
            with pytest.raises(aio.CancelledError):
                await write_task

    assert mock_hub.has_write is None
    assert mock_hub._slow_poll_requests == 1


# Modbus Read Holding Registers Error Tests


async def test_modbus_read_illegal_address(mock_hub, mock_modbus_client) -> None:
    """Test modbus read with IllegalAddress exception."""
    from tests.conftest import create_exception_response

    mock_client = mock_modbus_client.return_value
    mock_client.read_holding_registers.return_value = create_exception_response(
        ModbusExceptions.IllegalAddress
    )

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        with pytest.raises(ModbusIllegalAddress):
            await mock_hub.modbus_read_holding_registers(
                unit=1, address=40000, rcount=10
            )


async def test_modbus_read_illegal_function(mock_hub, mock_modbus_client) -> None:
    """Test modbus read with IllegalFunction exception."""
    from tests.conftest import create_exception_response

    mock_client = mock_modbus_client.return_value
    mock_client.read_holding_registers.return_value = create_exception_response(
        ModbusExceptions.IllegalFunction
    )

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        with pytest.raises(ModbusIllegalFunction):
            await mock_hub.modbus_read_holding_registers(
                unit=1, address=40000, rcount=10
            )


async def test_modbus_read_illegal_value(mock_hub, mock_modbus_client) -> None:
    """Test modbus read with IllegalValue exception."""
    from tests.conftest import create_exception_response

    mock_client = mock_modbus_client.return_value
    mock_client.read_holding_registers.return_value = create_exception_response(
        ModbusExceptions.IllegalValue
    )

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        with pytest.raises(ModbusIllegalValue):
            await mock_hub.modbus_read_holding_registers(
                unit=1, address=40000, rcount=10
            )


async def test_modbus_read_io_exception(mock_hub, mock_modbus_client) -> None:
    """Test modbus read with ModbusIOException."""
    from tests.conftest import create_io_exception_response

    mock_client = mock_modbus_client.return_value
    mock_client.read_holding_registers.return_value = create_io_exception_response()

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        with pytest.raises(ModbusIOError):
            await mock_hub.modbus_read_holding_registers(
                unit=1, address=40000, rcount=10
            )


async def test_modbus_read_register_count_mismatch(
    mock_hub, mock_modbus_client
) -> None:
    """Test modbus read fails when register count doesn't match."""
    from tests.conftest import create_modbus_response

    mock_client = mock_modbus_client.return_value
    # Return only 5 registers when 10 were requested
    mock_client.read_holding_registers.return_value = create_modbus_response(
        [1, 2, 3, 4, 5]
    )

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        with pytest.raises(ModbusReadError, match="Registers received != requested"):
            await mock_hub.modbus_read_holding_registers(
                unit=1, address=40000, rcount=10
            )


# SolarEdgeInverter Tests


async def test_inverter_init_device_success(
    mock_hub, mock_modbus_client, mock_inverter_registers
) -> None:
    """Test successful inverter device initialization."""
    from tests.conftest import create_exception_response, create_modbus_response

    mock_client = mock_modbus_client.return_value

    def read_side_effect(*args, **kwargs):
        address = kwargs.get("address", args[0] if args else 0)
        if address == 40000:
            return create_modbus_response(mock_inverter_registers)
        elif address == 40121:
            # No MMPPT - return illegal address error
            return create_exception_response(ModbusExceptions.IllegalAddress)
        return create_modbus_response([0] * 10)

    mock_client.read_holding_registers.side_effect = read_side_effect

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        inverter = SolarEdgeInverter(device_id=1, hub=mock_hub)
        await inverter.init_device()

        assert inverter.manufacturer == "SolarEdge"
        assert inverter.model == "SE10K"
        assert inverter.serial == "123456789"


async def test_inverter_init_device_modbus_io_error(
    mock_hub, mock_modbus_client
) -> None:
    """Test inverter init fails with ModbusIOError."""
    from tests.conftest import create_io_exception_response

    mock_client = mock_modbus_client.return_value
    mock_client.read_holding_registers.return_value = create_io_exception_response()

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        inverter = SolarEdgeInverter(device_id=1, hub=mock_hub)

        with pytest.raises(DeviceInvalid, match="No response from inverter"):
            await inverter.init_device()


async def test_inverter_init_device_illegal_address(
    mock_hub, mock_modbus_client
) -> None:
    """Test inverter init fails with illegal address."""
    from tests.conftest import create_exception_response

    mock_client = mock_modbus_client.return_value
    mock_client.read_holding_registers.return_value = create_exception_response(
        ModbusExceptions.IllegalAddress
    )

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        inverter = SolarEdgeInverter(device_id=1, hub=mock_hub)

        with pytest.raises(DeviceInvalid, match="not a SunSpec inverter"):
            await inverter.init_device()


async def test_inverter_init_device_invalid_sunspec_id(
    mock_hub, mock_modbus_client, mock_inverter_registers
) -> None:
    """Test inverter init fails with invalid SunSpec ID."""
    from tests.conftest import create_modbus_response

    # Create invalid SunSpec ID
    invalid_registers = mock_inverter_registers.copy()
    invalid_registers[0] = 0x1234
    invalid_registers[1] = 0x5678

    mock_client = mock_modbus_client.return_value
    mock_client.read_holding_registers.return_value = create_modbus_response(
        invalid_registers
    )

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        inverter = SolarEdgeInverter(device_id=1, hub=mock_hub)

        with pytest.raises(DeviceInvalid, match="not a SunSpec inverter"):
            await inverter.init_device()


async def test_inverter_read_modbus_data_success(
    mock_hub, mock_modbus_client, mock_inverter_registers, mock_inverter_model_registers
) -> None:
    """Test successful inverter modbus data read."""
    from tests.conftest import create_exception_response, create_modbus_response

    mock_client = mock_modbus_client.return_value

    def read_side_effect(*args, **kwargs):
        address = kwargs.get("address", args[0] if args else 0)
        count = kwargs.get("count", args[1] if len(args) > 1 else 10)
        if address == 40000:
            return create_modbus_response(mock_inverter_registers)
        elif address == 40044:
            # Merged read: 8 (version) + 17 (gap) + 40 (model) = 65
            return create_modbus_response(
                [0] * 8 + [0] * 17 + mock_inverter_model_registers
            )
        elif address == 40113:
            # Grid status
            return create_modbus_response([0] * 2)
        elif address == 40121:
            # No MMPPT - return illegal address error
            return create_exception_response(ModbusExceptions.IllegalAddress)
        return create_modbus_response([0] * count)

    mock_client.read_holding_registers.side_effect = read_side_effect

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        inverter = SolarEdgeInverter(device_id=1, hub=mock_hub)
        await inverter.init_device()
        await inverter.read_modbus_data()

        assert "AC_Power" in inverter.decoded_model
        assert inverter.decoded_model["C_SunSpec_DID"] == 101


async def test_inverter_read_modbus_data_invalid_device(
    mock_hub, mock_modbus_client, mock_inverter_registers
) -> None:
    """Test inverter read fails with invalid device."""
    from tests.conftest import create_exception_response, create_modbus_response

    mock_client = mock_modbus_client.return_value

    def read_side_effect(*args, **kwargs):
        address = kwargs.get("address", args[0] if args else 0)
        if address == 40000:
            return create_modbus_response(mock_inverter_registers)
        elif address == 40044:
            # Merged read: 8 (version) + 17 (gap) + invalid DID model
            invalid_model = [999, 50] + [0] * 38
            return create_modbus_response([0] * 8 + [0] * 17 + invalid_model)
        elif address == 40121:
            return create_exception_response(ModbusExceptions.IllegalAddress)
        return create_modbus_response([0] * 10)

    mock_client.read_holding_registers.side_effect = read_side_effect

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        inverter = SolarEdgeInverter(device_id=1, hub=mock_hub)
        await inverter.init_device()

        with pytest.raises(DeviceInvalid, match="not usable"):
            await inverter.read_modbus_data()


async def test_inverter_read_modbus_data_with_mmppt(
    mock_hub, mock_modbus_client, mock_inverter_registers, mock_inverter_model_registers
) -> None:
    """Test inverter read with MMPPT units."""
    from tests.conftest import create_modbus_response

    mock_client = mock_modbus_client.return_value

    def read_side_effect(*args, **kwargs):
        address = kwargs.get("address", args[0] if args else 0)
        count = kwargs.get("count", args[1] if len(args) > 1 else 0)

        if address == 40000:
            return create_modbus_response(mock_inverter_registers)
        elif address == 40044:
            # Merged read: 8 (version) + 17 (gap) + 40 (model) = 65
            return create_modbus_response(
                [0] * 8 + [0] * 17 + mock_inverter_model_registers
            )
        elif address == 40121 and count == 9:
            # MMPPT common block - return valid MMPPT data
            return create_modbus_response(
                [160, 5, 0, 0, 0, 0, 0, 0, 2]
            )  # 2 MMPPT units
        elif address == 40123:
            # MMPPT data for 2 units (48 registers)
            return create_modbus_response([0] * 48)
        return create_modbus_response([0] * count)

    mock_client.read_holding_registers.side_effect = read_side_effect

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        inverter = SolarEdgeInverter(device_id=1, hub=mock_hub)
        await inverter.init_device()

        assert inverter.decoded_mmppt is not None
        assert inverter.decoded_mmppt["mmppt_Units"] == 2
        assert len(inverter.mmppt_units) == 2

        await inverter.read_modbus_data()

        assert "mmppt_0" in inverter.decoded_model
        assert "mmppt_1" in inverter.decoded_model


# SolarEdgeMeter Tests


async def test_meter_init_device_success(
    mock_hub, mock_modbus_client, mock_inverter_registers
) -> None:
    """Test successful meter device initialization."""
    from tests.conftest import create_modbus_response

    mock_hub.inverter_common[1] = {
        "C_Model": "SE10K",
        "C_SerialNumber": "123456789",
    }
    mock_hub.mmppt_common[1] = None

    # Create meter common register data
    meter_registers = [1, 65]  # DID=1, Length=65
    # Manufacturer
    manufacturer = "SolarEdge".ljust(32, "\x00")
    meter_registers.extend(
        [ord(manufacturer[i]) << 8 | ord(manufacturer[i + 1]) for i in range(0, 32, 2)]
    )
    # Model
    model = "METER1".ljust(32, "\x00")
    meter_registers.extend(
        [ord(model[i]) << 8 | ord(model[i + 1]) for i in range(0, 32, 2)]
    )
    # Option
    option = "".ljust(16, "\x00")
    meter_registers.extend(
        [ord(option[i]) << 8 | ord(option[i + 1]) for i in range(0, 16, 2)]
    )
    # Version
    version = "1.0".ljust(16, "\x00")
    meter_registers.extend(
        [ord(version[i]) << 8 | ord(version[i + 1]) for i in range(0, 16, 2)]
    )
    # Serial
    serial = "M123456".ljust(32, "\x00")
    meter_registers.extend(
        [ord(serial[i]) << 8 | ord(serial[i + 1]) for i in range(0, 32, 2)]
    )
    # Device address
    meter_registers.append(1)

    mock_client = mock_modbus_client.return_value
    mock_client.read_holding_registers.return_value = create_modbus_response(
        meter_registers
    )

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        meter = SolarEdgeMeter(device_id=1, meter_id=1, hub=mock_hub)
        await meter.init_device()

        assert meter.manufacturer == "SolarEdge"
        assert meter.model == "METER1"
        assert meter.serial == "M123456"


async def test_meter_init_device_invalid_did(mock_hub, mock_modbus_client) -> None:
    """Test meter init fails with invalid DID."""
    from tests.conftest import create_modbus_response

    mock_hub.inverter_common[1] = {
        "C_Model": "SE10K",
        "C_SerialNumber": "123456789",
    }
    mock_hub.mmppt_common[1] = None

    # Create meter with invalid DID
    meter_registers = [999, 65] + [0] * 65

    mock_client = mock_modbus_client.return_value
    mock_client.read_holding_registers.return_value = create_modbus_response(
        meter_registers
    )

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        meter = SolarEdgeMeter(device_id=1, meter_id=1, hub=mock_hub)

        with pytest.raises(DeviceInvalid, match="ident incorrect or not installed"):
            await meter.init_device()


async def test_meter_read_modbus_data_did_201(mock_hub, mock_modbus_client) -> None:
    """Test meter read with DID 201."""
    from tests.conftest import create_modbus_response

    mock_hub.inverter_common[1] = {
        "C_Model": "SE10K",
        "C_SerialNumber": "123456789",
    }
    mock_hub.mmppt_common[1] = None

    # Create valid meter init data
    meter_init_registers = [1, 65] + [0] * 65

    # Create meter model data with DID 201
    meter_model_registers = [201, 105] + [0] * 105

    mock_client = mock_modbus_client.return_value

    def read_side_effect(*args, **kwargs):
        _address = kwargs.get("address", args[0] if args else 0)  # noqa: F841
        count = kwargs.get("count", args[1] if len(args) > 1 else 0)

        if count == 67:
            return create_modbus_response(meter_init_registers)
        elif count == 107:
            return create_modbus_response(meter_model_registers)
        return create_modbus_response([0] * count)

    mock_client.read_holding_registers.side_effect = read_side_effect

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        meter = SolarEdgeMeter(device_id=1, meter_id=1, hub=mock_hub)
        await meter.init_device()
        await meter.read_modbus_data()

        assert meter.decoded_model["C_SunSpec_DID"] == 201


async def test_meter_read_modbus_data_did_203(mock_hub, mock_modbus_client) -> None:
    """Test meter read with DID 203."""
    from tests.conftest import create_modbus_response

    mock_hub.inverter_common[1] = {
        "C_Model": "SE10K",
        "C_SerialNumber": "123456789",
    }
    mock_hub.mmppt_common[1] = None

    meter_init_registers = [1, 65] + [0] * 65
    meter_model_registers = [203, 105] + [0] * 105

    mock_client = mock_modbus_client.return_value

    def read_side_effect(*args, **kwargs):
        count = kwargs.get("count", args[1] if len(args) > 1 else 0)

        if count == 67:
            return create_modbus_response(meter_init_registers)
        elif count == 107:
            return create_modbus_response(meter_model_registers)
        return create_modbus_response([0] * count)

    mock_client.read_holding_registers.side_effect = read_side_effect

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        meter = SolarEdgeMeter(device_id=1, meter_id=1, hub=mock_hub)
        await meter.init_device()
        await meter.read_modbus_data()

        assert meter.decoded_model["C_SunSpec_DID"] == 203


# SolarEdgeBattery Tests


async def test_battery_init_device_success(mock_hub, mock_modbus_client) -> None:
    """Test successful battery device initialization."""
    from tests.conftest import create_modbus_response

    mock_hub.inverter_common[1] = {
        "C_Model": "SE10K",
        "C_SerialNumber": "123456789",
    }

    # Create battery info registers
    battery_registers = []

    # Manufacturer
    manufacturer = "LG".ljust(32, "\x00")
    battery_registers.extend(
        [ord(manufacturer[i]) << 8 | ord(manufacturer[i + 1]) for i in range(0, 32, 2)]
    )
    # Model
    model = "RESU10".ljust(32, "\x00")
    battery_registers.extend(
        [ord(model[i]) << 8 | ord(model[i + 1]) for i in range(0, 32, 2)]
    )
    # Version
    version = "1.0".ljust(32, "\x00")
    battery_registers.extend(
        [ord(version[i]) << 8 | ord(version[i + 1]) for i in range(0, 32, 2)]
    )
    # Serial
    serial = "BAT123".ljust(32, "\x00")
    battery_registers.extend(
        [ord(serial[i]) << 8 | ord(serial[i + 1]) for i in range(0, 32, 2)]
    )
    # Device address
    battery_registers.append(1)
    battery_registers.append(0)  # padding
    # Rated energy (10000 Wh as FLOAT32 in little endian)
    battery_registers.extend([0x461C, 0x4000])

    mock_client = mock_modbus_client.return_value
    mock_client.read_holding_registers.return_value = create_modbus_response(
        battery_registers
    )

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        battery = SolarEdgeBattery(device_id=1, battery_id=1, hub=mock_hub)
        await battery.init_device()

        assert battery.manufacturer == "LG"
        assert battery.model == "RESU10"
        assert "BAT123" in battery.serial


async def test_battery_init_device_invalid_rating(mock_hub, mock_modbus_client) -> None:
    """Test battery init fails with invalid rating."""
    from tests.conftest import create_modbus_response

    mock_hub.inverter_common[1] = {
        "C_Model": "SE10K",
        "C_SerialNumber": "123456789",
    }

    # Create battery with zero rated energy - need 68 registers total
    battery_registers = [0] * 68
    # Set rated energy to 0.0 (which will fail the <= 0 check)
    battery_registers[66] = 0x0000
    battery_registers[67] = 0x0000

    mock_client = mock_modbus_client.return_value
    mock_client.read_holding_registers.return_value = create_modbus_response(
        battery_registers
    )

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        battery = SolarEdgeBattery(device_id=1, battery_id=1, hub=mock_hub)

        with pytest.raises(DeviceInvalid, match="not usable"):
            await battery.init_device()


async def test_battery_read_modbus_data_success(mock_hub, mock_modbus_client) -> None:
    """Test successful battery modbus data read."""
    from tests.conftest import create_modbus_response

    mock_hub.inverter_common[1] = {
        "C_Model": "SE10K",
        "C_SerialNumber": "123456789",
    }

    # Valid battery init data
    battery_init_registers = [0] * 66 + [0x461C, 0x4000]

    # Battery model data
    battery_model_registers = [0] * 86

    mock_client = mock_modbus_client.return_value

    def read_side_effect(*args, **kwargs):
        count = kwargs.get("count", args[1] if len(args) > 1 else 0)

        if count == 68:
            return create_modbus_response(battery_init_registers)
        elif count == 86:
            return create_modbus_response(battery_model_registers)
        return create_modbus_response([0] * count)

    mock_client.read_holding_registers.side_effect = read_side_effect

    with patch(
        "custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient",
        mock_modbus_client,
    ):
        await mock_hub.connect()

        battery = SolarEdgeBattery(device_id=1, battery_id=1, hub=mock_hub)
        await battery.init_device()
        await battery.read_modbus_data()

        assert "B_DC_Power" in battery.decoded_model
        assert "B_Status" in battery.decoded_model


async def test_battery_invalid_id(mock_hub) -> None:
    """Test battery with invalid battery_id."""
    mock_hub.inverter_common[1] = {
        "C_Model": "SE10K",
        "C_SerialNumber": "123456789",
    }

    with pytest.raises(DeviceInvalid, match="Invalid battery_id"):
        SolarEdgeBattery(device_id=1, battery_id=99, hub=mock_hub)


# Hub Property and Utility Tests


async def test_hub_safe_version_tuple_valid(mock_hub) -> None:
    """Test version tuple parsing with valid version."""
    result = mock_hub._safe_version_tuple("3.8.3")
    assert result == (3, 8, 3)


async def test_hub_safe_version_tuple_invalid(mock_hub) -> None:
    """Test version tuple parsing with invalid version."""
    with pytest.raises(ValueError, match="Invalid version string"):
        mock_hub._safe_version_tuple("invalid.version.x")


async def test_hub_coordinator_timeout_not_initialized(mock_hub) -> None:
    """Test coordinator timeout calculation when not initialized."""
    mock_hub._initalized = False
    mock_hub._detect_extras = False

    timeout = mock_hub.coordinator_timeout
    assert timeout > 0


async def test_hub_coordinator_timeout_initialized(mock_hub) -> None:
    """Test coordinator timeout calculation when initialized."""
    mock_hub._initalized = True
    mock_hub._detect_extras = False
    mock_hub.meters = []
    mock_hub.batteries = []

    timeout = mock_hub.coordinator_timeout
    assert timeout > 0


async def test_hub_online_property_setter(mock_hub) -> None:
    """Test hub online property setter."""
    mock_hub.online = True
    assert mock_hub.online is True

    mock_hub.online = False
    assert mock_hub.online is False


async def test_hub_keep_modbus_open_property_setter(mock_hub) -> None:
    """Test hub keep_modbus_open property setter."""
    mock_hub.keep_modbus_open = True
    assert mock_hub.keep_modbus_open is True

    mock_hub.keep_modbus_open = False
    assert mock_hub.keep_modbus_open is False


async def test_inverter_properties(mock_hub) -> None:
    """Test inverter property accessors."""
    inverter = SolarEdgeInverter(device_id=1, hub=mock_hub)
    inverter.decoded_common = {"C_Version": "1.2.3"}

    assert inverter.fw_version == "1.2.3"
    assert inverter.online == mock_hub.online


async def test_meter_via_device_property(mock_hub) -> None:
    """Test meter via_device property."""
    mock_hub.inverter_common[1] = {
        "C_Model": "SE10K",
        "C_SerialNumber": "123456789",
    }
    mock_hub.mmppt_common[1] = None

    meter = SolarEdgeMeter(device_id=1, meter_id=1, hub=mock_hub)
    meter.via_device = "test_device"

    assert meter.via_device == (DOMAIN, "test_device")


async def test_battery_properties(mock_hub) -> None:
    """Test battery property accessors."""
    mock_hub.inverter_common[1] = {
        "C_Model": "SE10K",
        "C_SerialNumber": "123456789",
    }

    battery = SolarEdgeBattery(device_id=1, battery_id=1, hub=mock_hub)

    assert battery.allow_battery_energy_reset == mock_hub.allow_battery_energy_reset
    assert battery.battery_rating_adjust == mock_hub.battery_rating_adjust
    assert battery.battery_energy_reset_cycles == mock_hub.battery_energy_reset_cycles
