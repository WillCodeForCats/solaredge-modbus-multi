from __future__ import annotations

import asyncio
import importlib.metadata
import inspect
import logging

from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ConnectionException, ModbusIOException

try:
    # for pymodbus 3.11.1 and newer
    from pymodbus.pdu.pdu import ExceptionResponse
except ImportError:
    # or backwards compatibility
    from pymodbus.pdu import ExceptionResponse

from .battery import SolarEdgeBattery
from .const import (
    BATTERY_REG_BASE,
    DOMAIN,
    METER_REG_BASE,
    PYMODBUS_REQUIRED_VERSION,
    ConfDefaultFlag,
    ConfDefaultInt,
    ConfDefaultStr,
    ConfName,
    ModbusDefaults,
    ModbusExceptions,
    RetrySettings,
    SolarEdgeTimeouts,
)
from .exceptions import (
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
from .inverter import SolarEdgeInverter
from .meter import SolarEdgeMeter

_LOGGER = logging.getLogger(__name__)
pymodbus_version = importlib.metadata.version("pymodbus")


class SolarEdgeModbusMultiHub:
    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        entry_data,
        entry_options,
    ):
        """Initialize the Modbus hub."""
        self._hass = hass
        self._yaml_config = hass.data[DOMAIN]["yaml"]
        self._name = entry_data[CONF_NAME]
        self._host = entry_data[CONF_HOST]
        self._port = entry_data[CONF_PORT]
        self._entry_id = entry_id
        self._inverter_list = entry_data.get(ConfName.DEVICE_LIST, [ConfDefaultStr.DEVICE_LIST])
        self._detect_meters = entry_options.get(ConfName.DETECT_METERS, bool(ConfDefaultFlag.DETECT_METERS))
        self._detect_batteries = entry_options.get(ConfName.DETECT_BATTERIES, bool(ConfDefaultFlag.DETECT_BATTERIES))
        self._detect_extras = entry_options.get(ConfName.DETECT_EXTRAS, bool(ConfDefaultFlag.DETECT_EXTRAS))
        self._keep_modbus_open = entry_options.get(ConfName.KEEP_MODBUS_OPEN, bool(ConfDefaultFlag.KEEP_MODBUS_OPEN))
        self._adv_storage_control = entry_options.get(
            ConfName.ADV_STORAGE_CONTROL, bool(ConfDefaultFlag.ADV_STORAGE_CONTROL)
        )
        self._adv_site_limit_control = entry_options.get(
            ConfName.ADV_SITE_LIMIT_CONTROL,
            bool(ConfDefaultFlag.ADV_SITE_LIMIT_CONTROL),
        )
        self._allow_battery_energy_reset = entry_options.get(
            ConfName.ALLOW_BATTERY_ENERGY_RESET,
            bool(ConfDefaultFlag.ALLOW_BATTERY_ENERGY_RESET),
        )
        self._sleep_after_write = entry_options.get(ConfName.SLEEP_AFTER_WRITE, ConfDefaultInt.SLEEP_AFTER_WRITE)
        self._battery_rating_adjust = entry_options.get(
            ConfName.BATTERY_RATING_ADJUST, ConfDefaultInt.BATTERY_RATING_ADJUST
        )
        self._battery_energy_reset_cycles = entry_options.get(
            ConfName.BATTERY_ENERGY_RESET_CYCLES,
            ConfDefaultInt.BATTERY_ENERGY_RESET_CYCLES,
        )
        self._retry_limit = self._yaml_config.get("retry", {}).get("limit", RetrySettings.Limit)
        self._mb_reconnect_delay = self._yaml_config.get("modbus", {}).get(
            "reconnect_delay", ModbusDefaults.ReconnectDelay
        )
        self._mb_reconnect_delay_max = self._yaml_config.get("modbus", {}).get(
            "reconnect_delay_max", ModbusDefaults.ReconnectDelayMax
        )
        self._mb_timeout = self._yaml_config.get("modbus", {}).get("timeout", ModbusDefaults.Timeout)
        self._mb_retries = self._yaml_config.get("modbus", {}).get("retries", ModbusDefaults.Retries)
        self._id = entry_data[CONF_NAME].lower()
        self.inverters = []
        self.meters = []
        self.batteries = []
        self.inverter_common = {}
        self.mmppt_common = {}
        self.has_write = None

        self._initialized = False
        self._online = True
        self._timeout_counter = 0

        self._client = None

        self._pymodbus_version = pymodbus_version

        _LOGGER.debug(
            (
                f"{DOMAIN} configuration: "
                f"inverter_list={self._inverter_list}, "
                f"detect_meters={self._detect_meters}, "
                f"detect_batteries={self._detect_batteries}, "
                f"detect_extras={self._detect_extras}, "
                f"keep_modbus_open={self._keep_modbus_open}, "
                f"adv_storage_control={self._adv_storage_control}, "
                f"adv_site_limit_control={self._adv_site_limit_control}, "
                f"allow_battery_energy_reset={self._allow_battery_energy_reset}, "
                f"sleep_after_write={self._sleep_after_write}, "
                f"battery_rating_adjust={self._battery_rating_adjust}, "
            ),
        )

        _LOGGER.debug(f"pymodbus version {self.pymodbus_version}")

    async def _async_init_solaredge(self) -> None:
        """Detect devices and load initial modbus data from inverters."""

        pymodbus_version_tuple = self._safe_version_tuple(self.pymodbus_version)
        required_version_tuple = self._safe_version_tuple(self.pymodbus_required_version)

        if pymodbus_version_tuple < required_version_tuple:
            raise HubInitFailed(
                f"pymodbus version must be at least {self.pymodbus_required_version}, "
                f"but {self.pymodbus_version} is installed. Please remove other custom "
                "integrations that depend on an older version of pymodbus and restart."
            )

        if not self.is_connected:
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                "check_configuration",
                is_fixable=True,
                severity=ir.IssueSeverity.ERROR,
                translation_key="check_configuration",
                data={"entry_id": self._entry_id},
            )
            raise HubInitFailed(f"Modbus/TCP connect to {self.hub_host}:{self.hub_port} failed.")

        if self.option_storage_control:
            _LOGGER.warning(
                (
                    "Power Control Options: Storage Control is enabled. "
                    "Use at your own risk! "
                    "Adjustable parameters in Modbus registers are intended for "
                    "long-term storage. Periodic changes may damage the flash memory."
                ),
            )

        if self.option_site_limit_control:
            _LOGGER.warning(
                (
                    "Power Control Options: Site Limit Control is enabled. "
                    "Use at your own risk! "
                    "Adjustable parameters in Modbus registers are intended for "
                    "long-term storage. Periodic changes may damage the flash memory."
                ),
            )

        for inverter_unit_id in self._inverter_list:
            try:
                _LOGGER.debug(f"Looking for inverter at {self.hub_host} ID {inverter_unit_id}")
                new_inverter = SolarEdgeInverter(inverter_unit_id, self)
                await new_inverter.init_device()
                self.inverters.append(new_inverter)

            except (ModbusReadError, TimeoutError) as e:
                self.disconnect()
                raise HubInitFailed(f"{e}")

            except DeviceInvalid as e:
                # Inverters are mandatory
                _LOGGER.error(f"Inverter at {self.hub_host} ID {inverter_unit_id}: {e}")
                raise HubInitFailed(f"{e}")

            if self._detect_meters:
                for meter_id in METER_REG_BASE:
                    try:
                        _LOGGER.debug(f"Looking for meter I{inverter_unit_id}M{meter_id}")
                        new_meter = SolarEdgeMeter(inverter_unit_id, meter_id, self)
                        await new_meter.init_device()

                        for meter in self.meters:
                            # Allow duplicate serial number on meters PR#412
                            if new_meter.serial == meter.serial:
                                _LOGGER.warning(
                                    (f"Duplicate serial {new_meter.serial} on I{inverter_unit_id}M{meter_id}"),
                                )

                        new_meter.via_device = new_inverter.uid_base
                        self.meters.append(new_meter)
                        _LOGGER.debug(f"Found I{inverter_unit_id}M{meter_id}")

                    except (ModbusReadError, TimeoutError) as e:
                        self.disconnect()
                        raise HubInitFailed(f"{e}")

                    except DeviceInvalid as e:
                        _LOGGER.debug(f"I{inverter_unit_id}M{meter_id}: {e}")
                        pass

            if self._detect_batteries:
                for battery_id in BATTERY_REG_BASE:
                    try:
                        _LOGGER.debug(f"Looking for battery I{inverter_unit_id}B{battery_id}")
                        new_battery = SolarEdgeBattery(inverter_unit_id, battery_id, self)
                        await new_battery.init_device()

                        for battery in self.batteries:
                            if new_battery.serial == battery.serial:
                                _LOGGER.warning(
                                    (f"Duplicate serial {new_battery.serial} on I{inverter_unit_id}B{battery_id}"),
                                )
                                raise DeviceInvalid(f"Duplicate B{battery_id} serial {new_battery.serial}")

                        new_battery.via_device = new_inverter.uid_base
                        self.batteries.append(new_battery)
                        _LOGGER.debug(f"Found I{inverter_unit_id}B{battery_id}")

                    except (ModbusReadError, TimeoutError) as e:
                        self.disconnect()
                        raise HubInitFailed(f"{e}")

                    except DeviceInvalid as e:
                        _LOGGER.debug(f"I{inverter_unit_id}B{battery_id}: {e}")
                        pass

        try:
            for inverter in self.inverters:
                await inverter.read_modbus_data()
            for meter in self.meters:
                await meter.read_modbus_data()
            for battery in self.batteries:
                await battery.read_modbus_data()

            timestamp = dt.now()
            for inverter in self.inverters:
                inverter.set_last_update(timestamp)
            for meter in self.meters:
                meter.set_last_update(timestamp)
            for battery in self.batteries:
                battery.set_last_update(timestamp)

        except ModbusReadError as e:
            self.disconnect()
            raise HubInitFailed(f"Read error: {e}")

        except DeviceInvalid as e:
            self.disconnect()
            raise HubInitFailed(f"Invalid device: {e}")

        except ConnectionException as e:
            self.disconnect()
            raise HubInitFailed(f"Connection failed: {e}")

        except ModbusIOException as e:
            self.disconnect()
            raise HubInitFailed(f"Modbus error: {e}")

        except TimeoutError as e:
            self.disconnect()
            raise HubInitFailed(f"Timeout error: {e}")

        self.initialized = True

    async def async_refresh_modbus_data(self) -> bool:
        """Refresh modbus data from inverters."""

        if not self.is_connected:
            await self.connect()

        if not self.initialized:
            try:
                async with asyncio.timeout(self.coordinator_timeout):
                    await self._async_init_solaredge()

            except (ConnectionException, ModbusIOException, TimeoutError) as e:
                self.disconnect()
                ir.async_create_issue(
                    self._hass,
                    DOMAIN,
                    "check_configuration",
                    is_fixable=True,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key="check_configuration",
                    data={"entry_id": self._entry_id},
                )
                raise HubInitFailed(f"Setup failed: {e}")

            ir.async_delete_issue(self._hass, DOMAIN, "check_configuration")

            if not self.keep_modbus_open:
                self.disconnect()

            return True

        if not self.is_connected:
            self.online = False
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                "check_configuration",
                is_fixable=True,
                severity=ir.IssueSeverity.ERROR,
                translation_key="check_configuration",
                data={"entry_id": self._entry_id},
            )
            raise DataUpdateFailed(f"Modbus/TCP connect to {self.hub_host}:{self.hub_port} failed.")

        if not self.online:
            ir.async_delete_issue(self._hass, DOMAIN, "check_configuration")

        self.online = True

        try:
            async with asyncio.timeout(self.coordinator_timeout):
                for inverter in self.inverters:
                    await inverter.read_modbus_data()
                for meter in self.meters:
                    await meter.read_modbus_data()
                for battery in self.batteries:
                    await battery.read_modbus_data()

        except ModbusReadError as e:
            self.disconnect()
            raise DataUpdateFailed(f"Update failed: {e}")

        except DeviceInvalid as e:
            self.disconnect()
            raise DataUpdateFailed(f"Invalid device: {e}")

        except ConnectionException as e:
            self.disconnect()
            raise DataUpdateFailed(f"Connection failed: {e}")

        except ModbusIOException as e:
            self.disconnect()
            raise DataUpdateFailed(f"Modbus error: {e}")

        except TimeoutError as e:
            self.disconnect(clear_client=True)
            self._timeout_counter += 1

            _LOGGER.debug(f"Refresh timeout {self._timeout_counter} limit {self._retry_limit}")

            if self._timeout_counter >= self._retry_limit:
                self._timeout_counter = 0
                raise TimeoutError

            raise DataUpdateFailed(f"Timeout error: {e}")

        if self._timeout_counter > 0:
            _LOGGER.debug(f"Timeout count {self._timeout_counter} limit {self._retry_limit}")
            self._timeout_counter = 0

        if not self.keep_modbus_open:
            self.disconnect()

        timestamp = dt.now()
        for inverter in self.inverters:
            inverter.set_last_update(timestamp)
        for meter in self.meters:
            meter.set_last_update(timestamp)
        for battery in self.batteries:
            battery.set_last_update(timestamp)

        return True

    async def connect(self) -> None:
        """Connect to inverter."""

        if self._client is None:
            _LOGGER.debug(
                "New AsyncModbusTcpClient: "
                f"reconnect_delay={self._mb_reconnect_delay} "
                f"reconnect_delay_max={self._mb_reconnect_delay_max} "
                f"timeout={self._mb_timeout} "
                f"retries={self._mb_retries}"
            )
            self._client = AsyncModbusTcpClient(
                host=self._host,
                port=self._port,
                reconnect_delay=self._mb_reconnect_delay,
                reconnect_delay_max=self._mb_reconnect_delay_max,
                timeout=self._mb_timeout,
                retries=self._mb_retries,
            )

        _LOGGER.debug(f"Connecting to {self._host}:{self._port} ...")
        await self._client.connect()

    def disconnect(self, clear_client: bool = False) -> None:
        """Disconnect from inverter."""

        if self._client is not None:
            _LOGGER.debug(f"Disconnecting from {self._host}:{self._port} (clear_client={clear_client}).")
            self._client.close()

            if clear_client:
                self._client = None

    async def shutdown(self) -> None:
        """Shut down the hub and disconnect."""

        self.online = False
        self.disconnect(clear_client=True)

    async def modbus_read_holding_registers(self, unit, address, rcount):
        """Read modbus registers from inverter."""

        self._rr_unit = unit
        self._rr_address = address
        self._rr_count = rcount

        sig = inspect.signature(self._client.read_holding_registers)

        _LOGGER.debug(
            f"I{self._rr_unit}: modbus_read_holding_registers address={self._rr_address} count={self._rr_count}"
        )

        if "device_id" in sig.parameters:
            result = await self._client.read_holding_registers(
                address=self._rr_address, count=self._rr_count, device_id=self._rr_unit
            )
        else:
            result = await self._client.read_holding_registers(
                address=self._rr_address, count=self._rr_count, slave=self._rr_unit
            )

        _LOGGER.debug(f"I{self._rr_unit}: result is error: {result.isError()} ")

        if result.isError():
            _LOGGER.debug(f"I{self._rr_unit}: error result: {type(result)} ")

            if type(result) is ModbusIOException:
                raise ModbusIOError(result)

            if type(result) is ExceptionResponse:
                if result.exception_code == ModbusExceptions.IllegalAddress:
                    _LOGGER.debug(f"I{unit} Read IllegalAddress: {result}")
                    raise ModbusIllegalAddress(result)

                if result.exception_code == ModbusExceptions.IllegalFunction:
                    _LOGGER.debug(f"I{unit} Read IllegalFunction: {result}")
                    raise ModbusIllegalFunction(result)

                if result.exception_code == ModbusExceptions.IllegalValue:
                    _LOGGER.debug(f"I{unit} Read IllegalValue: {result}")
                    raise ModbusIllegalValue(result)

            raise ModbusReadError(result)

        _LOGGER.debug(
            f"I{self._rr_unit}: Registers received={len(result.registers)} "
            f"requested={self._rr_count} address={self._rr_address} "
            f"result={result}"
        )

        if len(result.registers) != rcount:
            raise ModbusReadError(
                f"I{self._rr_unit}: Registers received != requested : "
                f"{len(result.registers)} != {self._rr_count} at {self._rr_address}"
            )

        return result

    async def write_registers(self, unit: int, address: int, payload) -> None:
        """Write modbus registers to inverter."""

        self._wr_unit = unit
        self._wr_address = address
        self._wr_payload = payload

        try:
            if not self.is_connected:
                await self.connect()

            sig = inspect.signature(self._client.write_registers)

            if "device_id" in sig.parameters:
                result = await self._client.write_registers(
                    address=self._wr_address,
                    values=self._wr_payload,
                    device_id=self._wr_unit,
                )
            else:
                result = await self._client.write_registers(
                    address=self._wr_address,
                    values=self._wr_payload,
                    slave=self._wr_unit,
                )

            self.has_write = address

            if self.sleep_after_write > 0:
                _LOGGER.debug(f"Sleep {self.sleep_after_write} seconds after write {address}.")
                await asyncio.sleep(self.sleep_after_write)

            self.has_write = None
            _LOGGER.debug(f"Finished with write {address}.")

        except ModbusIOException as e:
            self.disconnect()

            raise HomeAssistantError(f"Error sending command to inverter ID {self._wr_unit}: {e}.")

        except ConnectionException as e:
            self.disconnect()

            _LOGGER.error(f"Connection failed: {e}")
            raise HomeAssistantError(f"Connection to inverter ID {self._wr_unit} failed.")

        if result.isError():
            if type(result) is ModbusIOException:
                self.disconnect()
                _LOGGER.error(f"Write failed: No response from inverter ID {self._wr_unit}.")
                raise HomeAssistantError(f"No response from inverter ID {self._wr_unit}.")

            if type(result) is ExceptionResponse:
                if result.exception_code == ModbusExceptions.IllegalAddress:
                    _LOGGER.debug(f"Unit {self._wr_unit} Write IllegalAddress: {result}")
                    raise HomeAssistantError(f"Address not supported at device at ID {self._wr_unit}.")

                if result.exception_code == ModbusExceptions.IllegalFunction:
                    _LOGGER.debug(f"Unit {self._wr_unit} Write IllegalFunction: {result}")
                    raise HomeAssistantError(f"Function not supported by device at ID {self._wr_unit}.")

                if result.exception_code == ModbusExceptions.IllegalValue:
                    _LOGGER.debug(f"Unit {self._wr_unit} Write IllegalValue: {result}")
                    raise HomeAssistantError(f"Value invalid for device at ID {self._wr_unit}.")

            self.disconnect()
            raise ModbusWriteError(result)

    @staticmethod
    def _safe_version_tuple(version_str: str) -> tuple[int, ...]:
        try:
            version_parts = version_str.split(".")
            version_tuple = tuple(int(part) for part in version_parts)
            return version_tuple
        except ValueError:
            raise ValueError(f"Invalid version string: {version_str}")

    @property
    def online(self):
        return self._online

    @online.setter
    def online(self, value: bool) -> None:
        if value is True:
            self._online = True
        else:
            self._online = False

    @property
    def initialized(self):
        return self._initialized

    @initialized.setter
    def initialized(self, value: bool) -> None:
        if value is True:
            self._initialized = True
        else:
            self._initialized = False

    @property
    def name(self):
        """Return the name of this hub."""
        return self._name

    @property
    def hub_id(self) -> str:
        """Return the ID of this hub."""
        return self._id

    @property
    def hub_host(self) -> str:
        """Return the modbus client host."""
        return self._host

    @property
    def hub_port(self) -> int:
        """Return the modbus client port."""
        return self._port

    @property
    def option_storage_control(self) -> bool:
        return self._adv_storage_control

    @property
    def option_site_limit_control(self) -> bool:
        return self._adv_site_limit_control

    @property
    def option_detect_extras(self) -> bool:
        return self._detect_extras

    @property
    def keep_modbus_open(self) -> bool:
        return self._keep_modbus_open

    @keep_modbus_open.setter
    def keep_modbus_open(self, value: bool) -> None:
        if value is True:
            self._keep_modbus_open = True
        else:
            self._keep_modbus_open = False

        _LOGGER.debug(f"keep_modbus_open={self._keep_modbus_open}")

    @property
    def allow_battery_energy_reset(self) -> bool:
        return self._allow_battery_energy_reset

    @property
    def battery_rating_adjust(self) -> int:
        return (self._battery_rating_adjust + 100) / 100

    @property
    def battery_energy_reset_cycles(self) -> int:
        return self._battery_energy_reset_cycles

    @property
    def number_of_meters(self) -> int:
        return len(self.meters)

    @property
    def number_of_batteries(self) -> int:
        return len(self.batteries)

    @property
    def number_of_inverters(self) -> int:
        return len(self._inverter_list)

    @property
    def sleep_after_write(self) -> int:
        return self._sleep_after_write

    @property
    def pymodbus_required_version(self) -> str:
        return PYMODBUS_REQUIRED_VERSION

    @property
    def pymodbus_version(self) -> str:
        return self._pymodbus_version

    @property
    def coordinator_timeout(self) -> int:
        if not self.initialized:
            this_timeout = SolarEdgeTimeouts.Inverter * self.number_of_inverters
            this_timeout += SolarEdgeTimeouts.Init * self.number_of_inverters
            this_timeout += (SolarEdgeTimeouts.Device * 2) * 3  # max 3 per inverter
            this_timeout += (SolarEdgeTimeouts.Device * 2) * 2  # max 2 per inverter
            if self.option_detect_extras:
                this_timeout += (SolarEdgeTimeouts.Read * 3) * self.number_of_inverters

        else:
            this_timeout = SolarEdgeTimeouts.Inverter * self.number_of_inverters
            this_timeout += SolarEdgeTimeouts.Device * self.number_of_meters
            this_timeout += SolarEdgeTimeouts.Device * self.number_of_batteries
            if self.option_detect_extras:
                this_timeout += (SolarEdgeTimeouts.Read * 3) * self.number_of_inverters

        this_timeout = this_timeout / 1000

        _LOGGER.debug(f"coordinator timeout is {this_timeout}")
        return this_timeout

    @property
    def is_connected(self) -> bool:
        """Check modbus client connection status."""
        if self._client is None:
            return False

        return self._client.connected
