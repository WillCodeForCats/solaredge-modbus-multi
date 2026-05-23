"""Unit tests for SolarEdgeModbusMultiHub."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT

from custom_components.solaredge_modbus_multi.const import DOMAIN, ConfName
from custom_components.solaredge_modbus_multi.exceptions import (
    DataUpdateFailed,
    DeviceInvalid,
    HubInitFailed,
    ModbusIllegalAddress,
    ModbusIllegalFunction,
    ModbusIllegalValue,
    ModbusIOError,
    ModbusReadError,
    ModbusWriteError,
)
from custom_components.solaredge_modbus_multi.hub import SolarEdgeModbusMultiHub
from custom_components.solaredge_modbus_multi.inverter import SolarEdgeInverter

from .fixtures import MockHass, make_response

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hub(inverter_list=None, options=None):
    hass = MockHass()
    entry_data = {
        CONF_NAME: "Test Hub",
        CONF_HOST: "192.168.1.100",
        CONF_PORT: 502,
        ConfName.DEVICE_LIST: inverter_list or [1],
    }
    return SolarEdgeModbusMultiHub(
        hass=hass,
        entry_id="test-entry-id",
        entry_data=entry_data,
        entry_options=options or {},
    )


def _mock_client(registers=None, is_error=False, error_type=None):
    """Build a mock modbus client with a read_holding_registers that uses 'slave'."""
    result = MagicMock()
    result.registers = registers or [0] * 10
    result.isError.return_value = is_error
    if error_type:
        result.__class__ = error_type

    client = MagicMock()
    client.connected = True

    async def mock_read(address, count, slave):
        return result

    client.read_holding_registers = mock_read
    return client, result


def _mock_client_device_id(registers=None, is_error=False):
    """Build a mock modbus client whose read_holding_registers uses 'device_id'."""
    result = MagicMock()
    result.registers = registers or [0] * 10
    result.isError.return_value = is_error

    client = MagicMock()
    client.connected = True

    async def mock_read(address, count, device_id):
        return result

    client.read_holding_registers = mock_read
    return client, result


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestHubProperties:
    def setup_method(self):
        self.hub = _make_hub()

    def test_hub_id_is_lowercased_name(self):
        assert self.hub.hub_id == "test hub"

    def test_name(self):
        assert self.hub.name == "Test Hub"

    def test_hub_host(self):
        assert self.hub.hub_host == "192.168.1.100"

    def test_hub_port(self):
        assert self.hub.hub_port == 502

    def test_number_of_inverters(self):
        hub = _make_hub(inverter_list=[1, 2, 3])
        assert hub.number_of_inverters == 3

    def test_number_of_meters_initially_zero(self):
        assert self.hub.number_of_meters == 0

    def test_number_of_batteries_initially_zero(self):
        assert self.hub.number_of_batteries == 0

    def test_pymodbus_required_version(self):
        assert self.hub.pymodbus_required_version == "3.8.3"

    def test_online_defaults_true(self):
        assert self.hub.online is True

    def test_online_setter(self):
        self.hub.online = False
        assert self.hub.online is False
        self.hub.online = True
        assert self.hub.online is True

    def test_initialized_defaults_false(self):
        assert self.hub.initialized is False

    def test_initialized_setter(self):
        self.hub.initialized = True
        assert self.hub.initialized is True

    def test_is_connected_false_with_no_client(self):
        assert self.hub._client is None
        assert self.hub.is_connected is False

    def test_keep_modbus_open_setter(self):
        self.hub.keep_modbus_open = True
        assert self.hub.keep_modbus_open is True
        self.hub.keep_modbus_open = False
        assert self.hub.keep_modbus_open is False


# ---------------------------------------------------------------------------
# coordinator_timeout
# ---------------------------------------------------------------------------


class TestCoordinatorTimeout:
    def test_uninitialized_timeout_is_positive(self):
        hub = _make_hub(inverter_list=[1])
        timeout = hub.coordinator_timeout
        assert timeout > 0

    def test_uninitialized_scales_with_inverter_count(self):
        hub1 = _make_hub(inverter_list=[1])
        hub3 = _make_hub(inverter_list=[1, 2, 3])
        assert hub3.coordinator_timeout > hub1.coordinator_timeout

    def test_initialized_timeout_is_positive(self):
        hub = _make_hub(inverter_list=[1])
        hub.initialized = True
        timeout = hub.coordinator_timeout
        assert timeout > 0

    def test_initialized_timeout_less_than_uninitialized(self):
        hub = _make_hub(inverter_list=[1])
        uninit_t = hub.coordinator_timeout
        hub.initialized = True
        init_t = hub.coordinator_timeout
        assert init_t < uninit_t


# ---------------------------------------------------------------------------
# _safe_version_tuple
# ---------------------------------------------------------------------------


class TestSafeVersionTuple:
    def test_valid_three_part(self):
        assert SolarEdgeModbusMultiHub._safe_version_tuple("3.8.3") == (3, 8, 3)

    def test_valid_two_part(self):
        assert SolarEdgeModbusMultiHub._safe_version_tuple("3.8") == (3, 8)

    def test_valid_single(self):
        assert SolarEdgeModbusMultiHub._safe_version_tuple("3") == (3,)

    def test_comparison_semantics(self):
        old = SolarEdgeModbusMultiHub._safe_version_tuple("3.7.0")
        new = SolarEdgeModbusMultiHub._safe_version_tuple("3.8.3")
        assert old < new

    def test_invalid_string_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid version"):
            SolarEdgeModbusMultiHub._safe_version_tuple("not.a.version")


# ---------------------------------------------------------------------------
# connect / disconnect
# ---------------------------------------------------------------------------


class TestHubConnectDisconnect:
    async def test_connect_creates_client(self):
        hub = _make_hub()
        with patch("custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient") as MockClient:
            mock_instance = AsyncMock()
            MockClient.return_value = mock_instance
            await hub.connect()
            MockClient.assert_called_once()
            mock_instance.connect.assert_awaited_once()

    async def test_connect_reuses_existing_client(self):
        hub = _make_hub()
        mock_client = AsyncMock()
        hub._client = mock_client
        with patch("custom_components.solaredge_modbus_multi.hub.AsyncModbusTcpClient") as MockClient:
            await hub.connect()
            MockClient.assert_not_called()  # no new client created
            mock_client.connect.assert_awaited_once()

    def test_disconnect_calls_close(self):
        hub = _make_hub()
        mock_client = MagicMock()
        hub._client = mock_client
        hub.disconnect()
        mock_client.close.assert_called_once()

    def test_disconnect_with_clear_client_sets_none(self):
        hub = _make_hub()
        mock_client = MagicMock()
        hub._client = mock_client
        hub.disconnect(clear_client=True)
        mock_client.close.assert_called_once()
        assert hub._client is None

    def test_disconnect_no_client_is_noop(self):
        hub = _make_hub()
        hub.disconnect()  # should not raise


# ---------------------------------------------------------------------------
# modbus_read_holding_registers
# ---------------------------------------------------------------------------


class TestModbusReadHoldingRegisters:
    async def test_happy_path_returns_result(self):
        hub = _make_hub()
        client, result = _mock_client(registers=[1, 2, 3], is_error=False)
        result.registers = [1, 2, 3]
        hub._client = client
        ret = await hub.modbus_read_holding_registers(unit=1, address=40000, rcount=3)
        assert ret.registers == [1, 2, 3]

    async def test_uses_device_id_param_when_available(self):
        hub = _make_hub()
        client, result = _mock_client_device_id(registers=[1, 2], is_error=False)
        result.registers = [1, 2]
        hub._client = client
        ret = await hub.modbus_read_holding_registers(unit=1, address=40000, rcount=2)
        assert ret.registers == [1, 2]

    async def test_wrong_register_count_raises_modbus_read_error(self):
        hub = _make_hub()
        client, result = _mock_client(registers=[1, 2, 3], is_error=False)
        result.registers = [1, 2, 3]
        hub._client = client
        with pytest.raises(ModbusReadError, match="received != requested"):
            await hub.modbus_read_holding_registers(unit=1, address=40000, rcount=10)

    async def test_isError_true_modbus_io_exception_raises_modbus_io_error(self):
        from pymodbus.exceptions import ModbusIOException

        hub = _make_hub()
        # Use a real ModbusIOException so type(result) is ModbusIOException passes
        result = ModbusIOException("timeout")
        client = MagicMock()
        client.connected = True

        async def mock_read(address, count, slave):
            return result

        client.read_holding_registers = mock_read
        hub._client = client
        with pytest.raises(ModbusIOError):
            await hub.modbus_read_holding_registers(unit=1, address=40000, rcount=10)

    async def test_isError_true_illegal_address_raises_modbus_illegal_address(self):
        from custom_components.solaredge_modbus_multi.const import ModbusExceptions

        try:
            from pymodbus.pdu.pdu import ExceptionResponse
        except ImportError:
            from pymodbus.pdu import ExceptionResponse

        hub = _make_hub()
        result = ExceptionResponse(function_code=3, exception_code=ModbusExceptions.IllegalAddress)
        client = MagicMock()
        client.connected = True

        async def mock_read(address, count, slave):
            return result

        client.read_holding_registers = mock_read
        hub._client = client
        with pytest.raises(ModbusIllegalAddress):
            await hub.modbus_read_holding_registers(unit=1, address=40000, rcount=10)

    async def test_isError_true_illegal_function_raises_modbus_illegal_function(self):
        from custom_components.solaredge_modbus_multi.const import ModbusExceptions

        try:
            from pymodbus.pdu.pdu import ExceptionResponse
        except ImportError:
            from pymodbus.pdu import ExceptionResponse

        hub = _make_hub()
        result = ExceptionResponse(function_code=3, exception_code=ModbusExceptions.IllegalFunction)
        client = MagicMock()
        client.connected = True

        async def mock_read(address, count, slave):
            return result

        client.read_holding_registers = mock_read
        hub._client = client
        with pytest.raises(ModbusIllegalFunction):
            await hub.modbus_read_holding_registers(unit=1, address=40000, rcount=10)

    async def test_isError_true_illegal_value_raises_modbus_illegal_value(self):
        from custom_components.solaredge_modbus_multi.const import ModbusExceptions

        try:
            from pymodbus.pdu.pdu import ExceptionResponse
        except ImportError:
            from pymodbus.pdu import ExceptionResponse

        hub = _make_hub()
        result = ExceptionResponse(function_code=3, exception_code=ModbusExceptions.IllegalValue)
        client = MagicMock()
        client.connected = True

        async def mock_read(address, count, slave):
            return result

        client.read_holding_registers = mock_read
        hub._client = client
        with pytest.raises(ModbusIllegalValue):
            await hub.modbus_read_holding_registers(unit=1, address=40000, rcount=10)

    async def test_isError_true_generic_raises_modbus_read_error(self):
        """An unrecognised error result falls through to generic ModbusReadError."""
        hub = _make_hub()
        result = MagicMock()
        result.isError.return_value = True
        # Make it look like neither ModbusIOException nor ExceptionResponse
        client = MagicMock()
        client.connected = True

        async def mock_read(address, count, slave):
            return result

        client.read_holding_registers = mock_read
        hub._client = client
        with pytest.raises(ModbusReadError):
            await hub.modbus_read_holding_registers(unit=1, address=40000, rcount=10)


# ---------------------------------------------------------------------------
# shutdown
# ---------------------------------------------------------------------------


class TestHubShutdown:
    async def test_shutdown_sets_offline_and_clears_client(self):
        hub = _make_hub()
        mock_client = MagicMock()
        hub._client = mock_client
        hub.online = True
        await hub.shutdown()
        assert hub.online is False
        mock_client.close.assert_called_once()
        assert hub._client is None


# ---------------------------------------------------------------------------
# Helpers for integration-level hub tests
# ---------------------------------------------------------------------------


def _connected_hub(options=None):
    """Return a hub with a mock connected client."""
    hub = _make_hub(options=options)
    mock_client = MagicMock()
    mock_client.connected = True
    hub._client = mock_client
    return hub


def _mock_inverter(read_side_effect=None):
    """Return a mock inverter with AsyncMock read_modbus_data."""
    from unittest.mock import MagicMock as MM

    inv = MM(spec=SolarEdgeInverter)
    inv.read_modbus_data = AsyncMock(side_effect=read_side_effect)
    inv.set_last_update = MM()
    return inv


# ---------------------------------------------------------------------------
# _async_init_solaredge
# ---------------------------------------------------------------------------


class TestHubAsyncInit:
    def _no_detect_options(self):
        return {ConfName.DETECT_METERS: False, ConfName.DETECT_BATTERIES: False}

    async def test_pymodbus_version_too_old_raises_hub_init_failed(self):
        hub = _connected_hub(options=self._no_detect_options())
        hub._pymodbus_version = "3.0.0"
        with pytest.raises(HubInitFailed, match="pymodbus version must be at least"):
            await hub._async_init_solaredge()

    async def test_not_connected_raises_hub_init_failed(self):
        hub = _make_hub(options=self._no_detect_options())
        with patch("custom_components.solaredge_modbus_multi.hub.ir") as mock_ir:
            with pytest.raises(HubInitFailed, match="connect"):
                await hub._async_init_solaredge()
        mock_ir.async_create_issue.assert_called_once()

    async def test_happy_path_sets_initialized(self):
        hub = _connected_hub(options=self._no_detect_options())
        with (
            patch.object(SolarEdgeInverter, "init_device", new_callable=AsyncMock),
            patch.object(SolarEdgeInverter, "read_modbus_data", new_callable=AsyncMock),
            patch("custom_components.solaredge_modbus_multi.hub.ir"),
            patch("custom_components.solaredge_modbus_multi.hub.dt"),
        ):
            await hub._async_init_solaredge()
        assert hub.initialized is True
        assert len(hub.inverters) == 1

    async def test_inverter_modbus_read_error_raises_hub_init_failed(self):
        hub = _connected_hub(options=self._no_detect_options())
        with (
            patch.object(SolarEdgeInverter, "init_device", side_effect=ModbusReadError("fail")),
            patch("custom_components.solaredge_modbus_multi.hub.ir"),
        ):
            with pytest.raises(HubInitFailed):
                await hub._async_init_solaredge()

    async def test_inverter_device_invalid_raises_hub_init_failed(self):
        hub = _connected_hub(options=self._no_detect_options())
        with (
            patch.object(SolarEdgeInverter, "init_device", side_effect=DeviceInvalid("bad")),
            patch("custom_components.solaredge_modbus_multi.hub.ir"),
        ):
            with pytest.raises(HubInitFailed):
                await hub._async_init_solaredge()

    async def test_read_modbus_data_error_raises_hub_init_failed(self):
        hub = _connected_hub(options=self._no_detect_options())
        with (
            patch.object(SolarEdgeInverter, "init_device", new_callable=AsyncMock),
            patch.object(SolarEdgeInverter, "read_modbus_data", side_effect=ModbusReadError("read fail")),
            patch("custom_components.solaredge_modbus_multi.hub.ir"),
            patch("custom_components.solaredge_modbus_multi.hub.dt"),
        ):
            with pytest.raises(HubInitFailed, match="Read error"):
                await hub._async_init_solaredge()

    async def test_storage_control_enabled_logs_warning(self):
        options = {**self._no_detect_options(), ConfName.ADV_STORAGE_CONTROL: True}
        hub = _connected_hub(options=options)
        with (
            patch.object(SolarEdgeInverter, "init_device", new_callable=AsyncMock),
            patch.object(SolarEdgeInverter, "read_modbus_data", new_callable=AsyncMock),
            patch("custom_components.solaredge_modbus_multi.hub.ir"),
            patch("custom_components.solaredge_modbus_multi.hub.dt"),
            patch("custom_components.solaredge_modbus_multi.hub._LOGGER") as mock_log,
        ):
            await hub._async_init_solaredge()
        assert any("Storage Control" in str(call) for call in mock_log.warning.call_args_list)

    async def test_site_limit_control_enabled_logs_warning(self):
        options = {**self._no_detect_options(), ConfName.ADV_SITE_LIMIT_CONTROL: True}
        hub = _connected_hub(options=options)
        with (
            patch.object(SolarEdgeInverter, "init_device", new_callable=AsyncMock),
            patch.object(SolarEdgeInverter, "read_modbus_data", new_callable=AsyncMock),
            patch("custom_components.solaredge_modbus_multi.hub.ir"),
            patch("custom_components.solaredge_modbus_multi.hub.dt"),
            patch("custom_components.solaredge_modbus_multi.hub._LOGGER") as mock_log,
        ):
            await hub._async_init_solaredge()
        assert any("Site Limit" in str(call) for call in mock_log.warning.call_args_list)

    async def test_meter_device_invalid_is_skipped(self):
        """Meter DeviceInvalid is caught and not fatal."""
        from custom_components.solaredge_modbus_multi.meter import SolarEdgeMeter

        options = {ConfName.DETECT_METERS: True, ConfName.DETECT_BATTERIES: False}
        hub = _connected_hub(options=options)
        # SolarEdgeInverter.init_device is mocked so we pre-populate what it normally writes
        hub.inverter_common[1] = {"C_Model": "SE5000H", "C_SerialNumber": "SN123456"}
        hub.mmppt_common[1] = None
        with (
            patch.object(SolarEdgeInverter, "init_device", new_callable=AsyncMock),
            patch.object(SolarEdgeInverter, "read_modbus_data", new_callable=AsyncMock),
            patch.object(SolarEdgeMeter, "init_device", side_effect=DeviceInvalid("no meter")),
            patch("custom_components.solaredge_modbus_multi.hub.ir"),
            patch("custom_components.solaredge_modbus_multi.hub.dt"),
        ):
            await hub._async_init_solaredge()
        assert hub.initialized is True
        assert len(hub.meters) == 0

    async def test_meter_modbus_read_error_raises_hub_init_failed(self):
        """Meter ModbusReadError propagates as HubInitFailed."""
        from custom_components.solaredge_modbus_multi.meter import SolarEdgeMeter

        options = {ConfName.DETECT_METERS: True, ConfName.DETECT_BATTERIES: False}
        hub = _connected_hub(options=options)
        hub.inverter_common[1] = {"C_Model": "SE5000H", "C_SerialNumber": "SN123456"}
        hub.mmppt_common[1] = None
        with (
            patch.object(SolarEdgeInverter, "init_device", new_callable=AsyncMock),
            patch.object(SolarEdgeMeter, "init_device", side_effect=ModbusReadError("timeout")),
            patch("custom_components.solaredge_modbus_multi.hub.ir"),
        ):
            with pytest.raises(HubInitFailed):
                await hub._async_init_solaredge()


# ---------------------------------------------------------------------------
# async_refresh_modbus_data
# ---------------------------------------------------------------------------


class TestHubAsyncRefresh:
    def _no_detect_options(self):
        return {ConfName.DETECT_METERS: False, ConfName.DETECT_BATTERIES: False}

    async def test_uninitialized_calls_init_and_returns_true(self):
        hub = _connected_hub(options=self._no_detect_options())
        with (
            patch.object(hub, "_async_init_solaredge", new_callable=AsyncMock) as mock_init,
            patch("custom_components.solaredge_modbus_multi.hub.ir"),
        ):
            result = await hub.async_refresh_modbus_data()
        mock_init.assert_awaited_once()
        assert result is True

    async def test_uninitialized_hub_init_failed_propagates(self):
        hub = _connected_hub(options=self._no_detect_options())
        with (
            patch.object(hub, "_async_init_solaredge", side_effect=HubInitFailed("setup fail")),
            patch("custom_components.solaredge_modbus_multi.hub.ir"),
        ):
            with pytest.raises(HubInitFailed):
                await hub.async_refresh_modbus_data()

    async def test_initialized_reads_devices_returns_true(self):
        hub = _connected_hub(options=self._no_detect_options())
        hub.initialized = True
        inv = _mock_inverter()
        hub.inverters = [inv]
        with patch("custom_components.solaredge_modbus_multi.hub.dt") as mock_dt:
            mock_dt.now.return_value = "ts"
            result = await hub.async_refresh_modbus_data()
        assert result is True
        inv.read_modbus_data.assert_awaited_once()
        inv.set_last_update.assert_called_once_with("ts")

    async def test_initialized_not_connected_raises_data_update_failed(self):
        hub = _make_hub(options=self._no_detect_options())
        hub.initialized = True
        mock_client = MagicMock()
        mock_client.connected = False
        mock_client.connect = AsyncMock()  # connect() is awaited in hub.connect()
        hub._client = mock_client
        with patch("custom_components.solaredge_modbus_multi.hub.ir"):
            with pytest.raises(DataUpdateFailed, match="connect"):
                await hub.async_refresh_modbus_data()

    async def test_initialized_modbus_read_error_raises_data_update_failed(self):
        hub = _connected_hub(options=self._no_detect_options())
        hub.initialized = True
        hub.inverters = [_mock_inverter(read_side_effect=ModbusReadError("fail"))]
        with pytest.raises(DataUpdateFailed, match="Update failed"):
            await hub.async_refresh_modbus_data()

    async def test_timeout_below_limit_increments_counter(self):
        hub = _connected_hub(options=self._no_detect_options())
        hub.initialized = True
        hub.inverters = [_mock_inverter(read_side_effect=TimeoutError())]
        with pytest.raises(DataUpdateFailed, match="Timeout"):
            await hub.async_refresh_modbus_data()
        assert hub._timeout_counter == 1

    async def test_timeout_at_limit_resets_counter_and_raises_timeout_error(self):
        hub = _connected_hub(options=self._no_detect_options())
        hub.initialized = True
        hub._timeout_counter = hub._retry_limit - 1
        hub.inverters = [_mock_inverter(read_side_effect=TimeoutError())]
        with pytest.raises(TimeoutError):
            await hub.async_refresh_modbus_data()
        assert hub._timeout_counter == 0

    async def test_keep_modbus_open_does_not_disconnect(self):
        options = {**self._no_detect_options(), ConfName.KEEP_MODBUS_OPEN: True}
        hub = _connected_hub(options=options)
        hub.initialized = True
        hub.inverters = []
        mock_client = hub._client
        with patch("custom_components.solaredge_modbus_multi.hub.dt"):
            await hub.async_refresh_modbus_data()
        mock_client.close.assert_not_called()

    async def test_disconnects_when_keep_modbus_open_false(self):
        options = {**self._no_detect_options(), ConfName.KEEP_MODBUS_OPEN: False}
        hub = _connected_hub(options=options)
        hub.initialized = True
        hub.inverters = []
        mock_client = hub._client
        with patch("custom_components.solaredge_modbus_multi.hub.dt"):
            await hub.async_refresh_modbus_data()
        mock_client.close.assert_called()


# ---------------------------------------------------------------------------
# write_registers
# ---------------------------------------------------------------------------


def _mock_write_client(is_error=False, param_name="slave"):
    """Return (hub, client, result) ready for write_registers calls."""
    hub = _make_hub()
    result = MagicMock()
    result.isError.return_value = is_error

    client = MagicMock()
    client.connected = True

    if param_name == "device_id":

        async def mock_write(address, values, device_id):
            return result
    else:

        async def mock_write(address, values, slave):
            return result

    client.write_registers = mock_write
    hub._client = client
    return hub, client, result


class TestHubWriteRegisters:
    async def test_happy_path_slave_param(self):
        hub, client, result = _mock_write_client(is_error=False, param_name="slave")
        await hub.write_registers(unit=1, address=40000, payload=[0])
        assert hub.has_write is None

    async def test_happy_path_device_id_param(self):
        hub, client, result = _mock_write_client(is_error=False, param_name="device_id")
        await hub.write_registers(unit=1, address=40000, payload=[0])
        assert hub.has_write is None

    async def test_sleep_after_write_calls_asyncio_sleep(self):
        hub, client, result = _mock_write_client(is_error=False)
        hub._sleep_after_write = 2
        with patch("custom_components.solaredge_modbus_multi.hub.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await hub.write_registers(unit=1, address=40000, payload=[0])
        mock_sleep.assert_awaited_once_with(2)

    async def test_modbus_io_exception_raises_ha_error(self):
        from homeassistant.exceptions import HomeAssistantError
        from pymodbus.exceptions import ModbusIOException as PyModbusIOException

        hub = _make_hub()
        client = MagicMock()
        client.connected = True

        async def mock_write(address, values, slave):
            raise PyModbusIOException("io error")

        client.write_registers = mock_write
        hub._client = client
        with pytest.raises(HomeAssistantError):
            await hub.write_registers(unit=1, address=40000, payload=[0])

    async def test_connection_exception_raises_ha_error(self):
        from homeassistant.exceptions import HomeAssistantError
        from pymodbus.exceptions import ConnectionException

        hub = _make_hub()
        client = MagicMock()
        client.connected = True

        async def mock_write(address, values, slave):
            raise ConnectionException("conn fail")

        client.write_registers = mock_write
        hub._client = client
        with pytest.raises(HomeAssistantError):
            await hub.write_registers(unit=1, address=40000, payload=[0])

    async def test_result_is_error_modbus_io_exception_raises_ha_error(self):
        from homeassistant.exceptions import HomeAssistantError
        from pymodbus.exceptions import ModbusIOException as PyModbusIOException

        hub = _make_hub()
        result = PyModbusIOException("io error")
        client = MagicMock()
        client.connected = True

        async def mock_write(address, values, slave):
            return result

        client.write_registers = mock_write
        hub._client = client
        with pytest.raises(HomeAssistantError):
            await hub.write_registers(unit=1, address=40000, payload=[0])

    async def test_result_is_error_illegal_address_raises_ha_error(self):
        from homeassistant.exceptions import HomeAssistantError

        from custom_components.solaredge_modbus_multi.const import ModbusExceptions

        try:
            from pymodbus.pdu.pdu import ExceptionResponse
        except ImportError:
            from pymodbus.pdu import ExceptionResponse

        hub = _make_hub()
        result = ExceptionResponse(function_code=16, exception_code=ModbusExceptions.IllegalAddress)
        client = MagicMock()
        client.connected = True

        async def mock_write(address, values, slave):
            return result

        client.write_registers = mock_write
        hub._client = client
        with pytest.raises(HomeAssistantError, match="Address not supported"):
            await hub.write_registers(unit=1, address=40000, payload=[0])

    async def test_result_is_error_illegal_function_raises_ha_error(self):
        from homeassistant.exceptions import HomeAssistantError

        from custom_components.solaredge_modbus_multi.const import ModbusExceptions

        try:
            from pymodbus.pdu.pdu import ExceptionResponse
        except ImportError:
            from pymodbus.pdu import ExceptionResponse

        hub = _make_hub()
        result = ExceptionResponse(function_code=16, exception_code=ModbusExceptions.IllegalFunction)
        client = MagicMock()
        client.connected = True

        async def mock_write(address, values, slave):
            return result

        client.write_registers = mock_write
        hub._client = client
        with pytest.raises(HomeAssistantError, match="Function not supported"):
            await hub.write_registers(unit=1, address=40000, payload=[0])

    async def test_result_is_error_illegal_value_raises_ha_error(self):
        from homeassistant.exceptions import HomeAssistantError

        from custom_components.solaredge_modbus_multi.const import ModbusExceptions

        try:
            from pymodbus.pdu.pdu import ExceptionResponse
        except ImportError:
            from pymodbus.pdu import ExceptionResponse

        hub = _make_hub()
        result = ExceptionResponse(function_code=16, exception_code=ModbusExceptions.IllegalValue)
        client = MagicMock()
        client.connected = True

        async def mock_write(address, values, slave):
            return result

        client.write_registers = mock_write
        hub._client = client
        with pytest.raises(HomeAssistantError, match="Value invalid"):
            await hub.write_registers(unit=1, address=40000, payload=[0])

    async def test_result_is_error_generic_raises_modbus_write_error(self):
        hub = _make_hub()
        result = MagicMock()
        result.isError.return_value = True
        client = MagicMock()
        client.connected = True

        async def mock_write(address, values, slave):
            return result

        client.write_registers = mock_write
        hub._client = client
        with pytest.raises(ModbusWriteError):
            await hub.write_registers(unit=1, address=40000, payload=[0])
