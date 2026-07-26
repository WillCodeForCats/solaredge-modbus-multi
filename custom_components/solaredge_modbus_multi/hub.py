"""SolarEdge Modbus Multi hub: session orchestration and polling.

Device classes, decode helpers and the exception hierarchy moved to
devices.py / exceptions.py (with the repair-issue id helpers in
const.py); everything remains importable from this module.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import logging

from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ConnectionException, ModbusIOException

try:  # pymodbus 3.11.1+
    from pymodbus.pdu.pdu import ExceptionResponse
except ImportError:  # older pymodbus
    from pymodbus.pdu import ExceptionResponse

from .const import (
    BATTERY_REG_BASE,
    DOMAIN,
    LEGACY_ISSUE_IDS,
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
    check_config_issue_id,
    detect_timeout_issue_id,
)
from .devices import (
    APC_BLOCK1_FLOAT32_FIELDS,
    APC_BLOCK2_FLOAT32_FIELDS,
    APC_DECODED_KEYS,
    APC_INT32_FIELDS,
    APC_UINT32_FIELDS,
    GPC_DECODED_KEYS,
    GRID_STATUS_DECODED_KEYS,
    SITE_LIMIT_DECODED_KEYS,
    SolarEdgeBattery,
    SolarEdgeEVSE,
    SolarEdgeInverter,
    SolarEdgeMeter,
    SolarEdgeMMPPTUnit,
    decode_sunspec_common_block,
    decode_sunspec_string,
    drop_decoded,
    log_decoded,
)
from .exceptions import (
    DataUpdateFailed,
    DeviceInitFailed,
    DeviceInvalid,
    DeviceIsEVSE,
    HubInitFailed,
    ModbusIllegalAddress,
    ModbusIllegalFunction,
    ModbusIllegalValue,
    ModbusIOError,
    ModbusReadError,
    ModbusWriteError,
    SolarEdgeException,
)
from .modbus_transport import ModbusTransport

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "APC_BLOCK1_FLOAT32_FIELDS",
    "APC_BLOCK2_FLOAT32_FIELDS",
    "APC_DECODED_KEYS",
    "APC_INT32_FIELDS",
    "APC_UINT32_FIELDS",
    "GPC_DECODED_KEYS",
    "GRID_STATUS_DECODED_KEYS",
    "LEGACY_ISSUE_IDS",
    "SITE_LIMIT_DECODED_KEYS",
    "DataUpdateFailed",
    "DeviceInitFailed",
    "DeviceInvalid",
    "DeviceIsEVSE",
    "HubInitFailed",
    "ModbusIllegalAddress",
    "ModbusIllegalFunction",
    "ModbusIllegalValue",
    "ModbusIOError",
    "ModbusReadError",
    "ModbusWriteError",
    "SolarEdgeBattery",
    "SolarEdgeEVSE",
    "SolarEdgeException",
    "SolarEdgeInverter",
    "SolarEdgeMeter",
    "SolarEdgeMMPPTUnit",
    "SolarEdgeModbusMultiHub",
    "async_delete_entry_issues",
    "check_config_issue_id",
    "decode_sunspec_common_block",
    "decode_sunspec_string",
    "detect_timeout_issue_id",
    "drop_decoded",
    "log_decoded",
]


def async_delete_entry_issues(hass, entry) -> None:
    """Remove every repair issue belonging to a config entry.

    Scans the issue registry by the entry-scoped id prefixes instead of
    deriving ids from the entry's device list: a reconfigure rewrites
    entry.data before the reload, so a removed inverter's issues would
    otherwise be undiscoverable and orphan until the next restart.
    """
    per_unit_prefixes = tuple(
        f"detect_timeout_{kind}_{entry.entry_id}_" for kind in ("gpc", "apc")
    )
    check_config_id = check_config_issue_id(entry.entry_id)

    registry = ir.async_get(hass)
    for domain, issue_id in list(registry.issues):
        if domain != DOMAIN:
            continue
        if issue_id == check_config_id or issue_id.startswith(per_unit_prefixes):
            ir.async_delete_issue(hass, DOMAIN, issue_id)


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
        self._inverter_list = entry_data.get(
            ConfName.DEVICE_LIST, [ConfDefaultStr.DEVICE_LIST]
        )
        self._detect_meters = entry_options.get(
            ConfName.DETECT_METERS, bool(ConfDefaultFlag.DETECT_METERS)
        )
        self._detect_batteries = entry_options.get(
            ConfName.DETECT_BATTERIES, bool(ConfDefaultFlag.DETECT_BATTERIES)
        )
        self._detect_extras = entry_options.get(
            ConfName.DETECT_EXTRAS, bool(ConfDefaultFlag.DETECT_EXTRAS)
        )
        self._keep_modbus_open = entry_options.get(
            ConfName.KEEP_MODBUS_OPEN, bool(ConfDefaultFlag.KEEP_MODBUS_OPEN)
        )
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
        self._sleep_after_write = entry_options.get(
            ConfName.SLEEP_AFTER_WRITE, ConfDefaultInt.SLEEP_AFTER_WRITE
        )
        self._battery_rating_adjust = entry_options.get(
            ConfName.BATTERY_RATING_ADJUST, ConfDefaultInt.BATTERY_RATING_ADJUST
        )
        self._battery_energy_reset_cycles = entry_options.get(
            ConfName.BATTERY_ENERGY_RESET_CYCLES,
            ConfDefaultInt.BATTERY_ENERGY_RESET_CYCLES,
        )
        self._slow_poll_multiplier = max(
            1,
            int(
                entry_options.get(
                    ConfName.SLOW_POLL_MULTIPLIER,
                    ConfDefaultInt.SLOW_POLL_MULTIPLIER,
                )
            ),
        )
        self._poll_cycle = -1
        self._slow_poll_requests = 0
        self.slow_poll_due = True
        self._retry_limit = self._yaml_config.get("retry", {}).get(
            "limit", RetrySettings.Limit
        )
        self._mb_reconnect_delay = self._yaml_config.get("modbus", {}).get(
            "reconnect_delay", ModbusDefaults.ReconnectDelay
        )
        self._mb_reconnect_delay_max = self._yaml_config.get("modbus", {}).get(
            "reconnect_delay_max", ModbusDefaults.ReconnectDelayMax
        )
        self._mb_timeout = self._yaml_config.get("modbus", {}).get(
            "timeout", ModbusDefaults.Timeout
        )
        self._mb_retries = self._yaml_config.get("modbus", {}).get(
            "retries", ModbusDefaults.Retries
        )
        self._id = entry_data[CONF_NAME].lower()
        self.inverters = []
        self.meters = []
        self.batteries = []
        self.evses = []
        self.inverter_common = {}
        self.mmppt_common = {}
        self.has_write = None

        self._initalized = False
        self._online = True
        self._timeout_counter = 0
        self._uncommitted_power_settings: set[int] = set()
        self._uncommitted_warned = False

        # The factory resolves this module's AsyncModbusTcpClient at call
        # time, so tests patching hub.AsyncModbusTcpClient keep working.
        self._transport = ModbusTransport(
            host=self._host,
            port=self._port,
            timeout=self._mb_timeout,
            retries=self._mb_retries,
            reconnect_delay=self._mb_reconnect_delay,
            reconnect_delay_max=self._mb_reconnect_delay_max,
            client_factory=lambda **kwargs: AsyncModbusTcpClient(**kwargs),
        )

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
        required_version_tuple = self._safe_version_tuple(
            self.pymodbus_required_version
        )

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
                check_config_issue_id(self._entry_id),
                is_fixable=True,
                severity=ir.IssueSeverity.ERROR,
                translation_key="check_configuration",
                data={"entry_id": self._entry_id},
            )
            raise HubInitFailed(
                f"Modbus/TCP connect to {self.hub_host}:{self.hub_port} failed."
            )

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
                _LOGGER.debug(
                    f"Looking for inverter at {self.hub_host} ID {inverter_unit_id}"
                )
                new_inverter = SolarEdgeInverter(inverter_unit_id, self)
                await new_inverter.init_device()
                self.inverters.append(new_inverter)

            except (ModbusReadError, TimeoutError) as e:
                await self.disconnect()
                raise HubInitFailed(f"{e}")

            except DeviceInvalid as e:
                # Inverters are mandatory
                _LOGGER.error(f"Inverter at {self.hub_host} ID {inverter_unit_id}: {e}")
                raise HubInitFailed(f"{e}")

            except DeviceIsEVSE as e:
                _LOGGER.debug(
                    f"Device model matches EVSE at {self.hub_host} ID {inverter_unit_id}: {e}"
                )
                try:
                    new_evse = SolarEdgeEVSE(inverter_unit_id, self)
                    await new_evse.init_device()
                    self.evses.append(new_evse)

                except (ModbusReadError, TimeoutError) as e:
                    await self.disconnect()
                    raise HubInitFailed(f"{e}")

                except DeviceInvalid as e:
                    # EVSEs are optional
                    _LOGGER.error(f"EVSE at {self.hub_host} ID {inverter_unit_id}: {e}")

                # Skip meter and battery detection if DeviceIsEVSE
                continue

            if self._detect_meters:
                for meter_id in METER_REG_BASE:
                    try:
                        _LOGGER.debug(
                            f"Looking for meter I{inverter_unit_id}M{meter_id}"
                        )
                        new_meter = SolarEdgeMeter(inverter_unit_id, meter_id, self)
                        await new_meter.init_device()

                        for meter in self.meters:
                            # Allow duplicate serial number on meters PR#412
                            if new_meter.serial == meter.serial:
                                _LOGGER.warning(
                                    (
                                        f"Duplicate serial {new_meter.serial} "
                                        f"on I{inverter_unit_id}M{meter_id}"
                                    ),
                                )

                        new_meter.via_device = new_inverter.uid_base
                        self.meters.append(new_meter)
                        _LOGGER.debug(f"Found I{inverter_unit_id}M{meter_id}")

                    except (ModbusReadError, TimeoutError) as e:
                        await self.disconnect()
                        raise HubInitFailed(f"{e}")

                    except DeviceInvalid as e:
                        _LOGGER.debug(f"I{inverter_unit_id}M{meter_id}: {e}")
                        pass

            if self._detect_batteries:
                for battery_id in BATTERY_REG_BASE:
                    try:
                        _LOGGER.debug(
                            f"Looking for battery I{inverter_unit_id}B{battery_id}"
                        )
                        new_battery = SolarEdgeBattery(
                            inverter_unit_id, battery_id, self
                        )
                        await new_battery.init_device()

                        for battery in self.batteries:
                            if new_battery.serial == battery.serial:
                                _LOGGER.warning(
                                    (
                                        f"Duplicate serial {new_battery.serial} "
                                        f"on I{inverter_unit_id}B{battery_id}"
                                    ),
                                )
                                raise DeviceInvalid(
                                    f"Duplicate B{battery_id} serial "
                                    f"{new_battery.serial}"
                                )

                        new_battery.via_device = new_inverter.uid_base
                        self.batteries.append(new_battery)
                        _LOGGER.debug(f"Found I{inverter_unit_id}B{battery_id}")

                    except (ModbusReadError, TimeoutError) as e:
                        await self.disconnect()
                        raise HubInitFailed(f"{e}")

                    except DeviceInvalid as e:
                        _LOGGER.debug(f"I{inverter_unit_id}B{battery_id}: {e}")
                        pass

        try:
            # Read all devices sequentially with batch lock per device
            for inv in self.inverters:
                await self._poll_device_with_lock(inv)
            for meter in self.meters:
                await self._poll_device_with_lock(meter)
            for bat in self.batteries:
                await self._poll_device_with_lock(bat)
            for evse in self.evses:
                await self._poll_device_with_lock(evse)

            timestamp = dt.now()
            for inverter in self.inverters:
                inverter.set_last_update(timestamp)
            for meter in self.meters:
                meter.set_last_update(timestamp)
            for battery in self.batteries:
                battery.set_last_update(timestamp)

        except (
            ModbusReadError,
            ModbusIllegalFunction,
            ModbusIllegalValue,
            DeviceInvalid,
            ConnectionException,
            ModbusIOException,
            TimeoutError,
        ) as e:
            await self.disconnect()
            if isinstance(
                e, (ModbusReadError, ModbusIllegalFunction, ModbusIllegalValue)
            ):
                raise HubInitFailed(f"Read error: {e}")
            if isinstance(e, DeviceInvalid):
                raise HubInitFailed(f"Invalid device: {e}")
            if isinstance(e, ConnectionException):
                raise HubInitFailed(f"Connection failed: {e}")
            if isinstance(e, ModbusIOException):
                raise HubInitFailed(f"Modbus error: {e}")
            raise HubInitFailed(f"Timeout error: {e}")

        self.initalized = True

    async def async_refresh_modbus_data(self) -> bool:
        """Refresh modbus data from inverters."""

        await self.connect()

        if not self.initalized:
            try:
                async with asyncio.timeout(self.coordinator_timeout):
                    await self._async_init_solaredge()

            except (ConnectionException, ModbusIOException, TimeoutError) as e:
                await self.disconnect()
                ir.async_create_issue(
                    self._hass,
                    DOMAIN,
                    check_config_issue_id(self._entry_id),
                    is_fixable=True,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key="check_configuration",
                    data={"entry_id": self._entry_id},
                )
                raise HubInitFailed(f"Setup failed: {e}")

            ir.async_delete_issue(
                self._hass, DOMAIN, check_config_issue_id(self._entry_id)
            )

            if not self.keep_modbus_open:
                await self.disconnect()

            return True

        if not self.is_connected:
            self.online = False
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                check_config_issue_id(self._entry_id),
                is_fixable=True,
                severity=ir.IssueSeverity.ERROR,
                translation_key="check_configuration",
                data={"entry_id": self._entry_id},
            )
            raise DataUpdateFailed(
                f"Modbus/TCP connect to {self.hub_host}:{self.hub_port} failed."
            )

        if not self.online:
            ir.async_delete_issue(
                self._hass, DOMAIN, check_config_issue_id(self._entry_id)
            )

        self.online = True

        # Decide the tier for this attempt, but only commit the cycle state
        # after a successful poll: a failed attempt must not consume a due
        # (or write-forced) slow poll. Write-forced polls are counted, not
        # flagged, so a write landing mid-refresh keeps its request pending
        # instead of being cleared by this refresh's completion.
        next_cycle = self._poll_cycle + 1
        served_slow_poll_requests = self._slow_poll_requests
        self.slow_poll_due = (
            served_slow_poll_requests > 0
            or next_cycle % self._slow_poll_multiplier == 0
        )

        try:
            async with asyncio.timeout(self.coordinator_timeout):
                # Read all devices sequentially with batch lock per device
                for inv in self.inverters:
                    await self._poll_device_with_lock(inv)
                for meter in self.meters:
                    await self._poll_device_with_lock(meter)
                for bat in self.batteries:
                    await self._poll_device_with_lock(bat)
                for evse in self.evses:
                    await self._poll_device_with_lock(evse)

        except (
            ModbusReadError,
            ModbusIllegalFunction,
            ModbusIllegalValue,
            DeviceInvalid,
            ConnectionException,
            ModbusIOException,
        ) as e:
            await self.disconnect()
            if isinstance(
                e, (ModbusReadError, ModbusIllegalFunction, ModbusIllegalValue)
            ):
                raise DataUpdateFailed(f"Update failed: {e}")
            if isinstance(e, DeviceInvalid):
                raise DataUpdateFailed(f"Invalid device: {e}")
            if isinstance(e, ConnectionException):
                raise DataUpdateFailed(f"Connection failed: {e}")
            raise DataUpdateFailed(f"Modbus error: {e}")

        except TimeoutError as e:
            await self.disconnect(clear_client=True)
            self._timeout_counter += 1

            _LOGGER.debug(
                f"Refresh timeout {self._timeout_counter} limit {self._retry_limit}"
            )

            if self._timeout_counter >= self._retry_limit:
                self._timeout_counter = 0
                raise TimeoutError

            raise DataUpdateFailed(f"Timeout error: {e}")

        self._poll_cycle = next_cycle
        # Consume only the requests this poll actually served; requests from
        # writes that landed during the refresh stay pending for the next one.
        self._slow_poll_requests -= served_slow_poll_requests

        # SolarEdge requires an explicit commit for static power-control
        # settings to survive an inverter restart. Warn once per batch,
        # after a slow poll has re-read the control blocks post-write.
        if (
            self.slow_poll_due
            and self._uncommitted_power_settings
            and not self._uncommitted_warned
        ):
            _LOGGER.warning(
                "Power control settings at register(s) %s were written without "
                "a commit; they will not persist across an inverter restart. "
                "Press the Commit Power Settings button to persist them.",
                sorted(self._uncommitted_power_settings),
            )
            self._uncommitted_warned = True

        if self._timeout_counter > 0:
            _LOGGER.debug(
                f"Timeout count {self._timeout_counter} limit {self._retry_limit}"
            )
            self._timeout_counter = 0

        if not self.keep_modbus_open:
            await self.disconnect()

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
        await self._transport.connect()

    async def disconnect(self, clear_client: bool = False) -> None:
        """Disconnect from inverter."""
        await self._transport.disconnect(clear_client)

    async def shutdown(self) -> None:
        """Shut down the hub and disconnect."""

        self.online = False
        await self.disconnect(clear_client=True)

    def _validate_read_result(self, unit, address, rcount, result):
        """Map error responses to exceptions and enforce the register count."""

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(f"I{unit}: result is error: {result.isError()} ")

        if result.isError():
            _LOGGER.debug(f"I{unit}: error result: {type(result)} ")

            # Sanitized: type/code only, never payload or host details.
            if type(result) is ExceptionResponse:
                self._transport.stats.last_error = (
                    f"read unit {unit}: ExceptionResponse"
                    f"(code={result.exception_code})"
                )
            else:
                self._transport.stats.last_error = (
                    f"read unit {unit}: {type(result).__name__}"
                )

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

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                f"I{unit}: Registers received={len(result.registers)} "
                f"requested={rcount} address={address} "
                f"result={result}"
            )

        if len(result.registers) != rcount:
            raise ModbusReadError(
                f"I{unit}: Registers received != requested : "
                f"{len(result.registers)} != {rcount} at {address}"
            )

        return result

    async def modbus_read_holding_registers(self, unit, address, rcount):
        """Read modbus registers from inverter."""

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                f"I{unit}: modbus_read_holding_registers "
                f"address={address} count={rcount}"
            )

        result = await self._transport.read_holding_registers_raw(unit, address, rcount)
        return self._validate_read_result(unit, address, rcount, result)

    async def _poll_device_with_lock(self, device) -> None:
        """Poll a single device while holding the modbus session.

        Holds the session for the entire device read cycle, ensuring all
        registers for one unit_id are read atomically before moving to
        the next device. This prevents Modbus transaction ID confusion
        when SolarEdge firmware returns incorrect unit_id in responses.
        """
        async with self._transport.hold_session():
            await device.read_modbus_data()

    async def write_registers(self, unit: int, address: int, payload) -> None:
        """Write modbus registers to inverter."""

        try:
            result = await self._transport.write_registers_raw(unit, address, payload)

        except ModbusIOException as e:
            await self.disconnect()

            raise HomeAssistantError(
                f"Error sending command to inverter ID {unit}: {e}."
            )

        except ConnectionException as e:
            await self.disconnect()

            _LOGGER.error(f"Connection failed: {e}")
            raise HomeAssistantError(f"Connection to inverter ID {unit} failed.")

        if result.isError():
            if type(result) is ModbusIOException:
                await self.disconnect()
                _LOGGER.error(f"Write failed: No response from inverter ID {unit}.")
                raise HomeAssistantError(f"No response from inverter ID {unit}.")

            if type(result) is ExceptionResponse:
                if result.exception_code == ModbusExceptions.IllegalAddress:
                    _LOGGER.debug(f"Unit {unit} Write IllegalAddress: {result}")
                    raise HomeAssistantError(
                        f"Address not supported at device at ID {unit}."
                    )

                if result.exception_code == ModbusExceptions.IllegalFunction:
                    _LOGGER.debug(f"Unit {unit} Write IllegalFunction: {result}")
                    raise HomeAssistantError(
                        f"Function not supported by device at ID {unit}."
                    )

                if result.exception_code == ModbusExceptions.IllegalValue:
                    _LOGGER.debug(f"Unit {unit} Write IllegalValue: {result}")
                    raise HomeAssistantError(f"Value invalid for device at ID {unit}.")

            await self.disconnect()
            raise ModbusWriteError(result)

        self.has_write = address
        # Control registers changed: request a slow-block re-read. A counter
        # (not a flag) so an in-flight refresh can't consume this request.
        # Kept outside the try: it must run exactly once per write.
        self._slow_poll_requests += 1

        # Track APC static settings pending an explicit commit (61696) or
        # restore-defaults (61697); blocks span 61696-61781 and 61782-61865.
        if address in (61696, 61697):
            if self._uncommitted_power_settings:
                _LOGGER.debug(
                    "Power control settings %s committed/restored.",
                    sorted(self._uncommitted_power_settings),
                )
            self._uncommitted_power_settings.clear()
            self._uncommitted_warned = False
        elif 61698 <= address <= 61865:
            self._uncommitted_power_settings.add(address)

        try:
            if self.sleep_after_write > 0:
                _LOGGER.debug(
                    f"Sleep {self.sleep_after_write} seconds after write {address}."
                )
                await asyncio.sleep(self.sleep_after_write)
        finally:
            # Cancellation during the sleep must not leave has_write stuck,
            # or every poll would wait out the coordinator's bounded clear.
            self.has_write = None

        _LOGGER.debug(f"Finished with write {address}.")

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
        self._online = bool(value)

    @property
    def initalized(self):
        return self._initalized

    @initalized.setter
    def initalized(self, value: bool) -> None:
        self._initalized = bool(value)

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
        self._keep_modbus_open = bool(value)

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
        """Calculate coordinator timeout for sequential polling with batch lock.

        Devices are polled sequentially, each holding the lock for their
        entire read cycle. Timeout is the sum of per-device budgets:
        - SolarEdgeTimeouts.Inverter (3s) base for first inverter
        - SolarEdgeTimeouts.Device (0.5s) per additional device
        - SolarEdgeTimeouts.Init (0.8s) per device during discovery
        - SolarEdgeTimeouts.Read (2s) per extra read block
        """
        if not self.initalized:
            # Init: need time for discovery of all devices
            # Base timeout + increment per device being discovered
            this_timeout = SolarEdgeTimeouts.Inverter  # Base for first inverter
            this_timeout += SolarEdgeTimeouts.Init * self.number_of_inverters
            this_timeout += (SolarEdgeTimeouts.Device * 2) * 3  # max 3 meters
            this_timeout += (SolarEdgeTimeouts.Device * 2) * 2  # max 2 batteries
            if self.option_detect_extras:
                this_timeout += SolarEdgeTimeouts.Read * 3 * self.number_of_inverters

        else:
            # Normal polling: lock serializes but typical ops are fast
            # Use base + actual device counts
            this_timeout = SolarEdgeTimeouts.Inverter  # Base timeout
            # Add smaller increment for additional inverters (not full timeout each)
            this_timeout += SolarEdgeTimeouts.Device * (self.number_of_inverters - 1)
            this_timeout += SolarEdgeTimeouts.Device * self.number_of_meters
            this_timeout += SolarEdgeTimeouts.Device * self.number_of_batteries
            if self.option_detect_extras:
                this_timeout += SolarEdgeTimeouts.Read * 3

        this_timeout = this_timeout / 1000

        _LOGGER.debug(f"coordinator timeout is {this_timeout}")
        return this_timeout

    @property
    def is_connected(self) -> bool:
        """Check modbus client connection status."""
        return self._transport.connected

    @property
    def uncommitted_power_settings(self) -> list[int]:
        """APC static-setting registers written since the last commit."""
        return sorted(self._uncommitted_power_settings)

    @property
    def transport_stats(self):
        """Diagnostics-only transport counters."""
        return self._transport.stats

    # Compatibility passthroughs: the client and session lock live in the
    # transport now, but tests (and any external code) still reach them
    # through the hub.
    @property
    def _client(self):
        return self._transport._client

    @_client.setter
    def _client(self, value) -> None:
        self._transport._client = value

    @property
    def _modbus_lock(self) -> asyncio.Lock:
        return self._transport._lock

    @property
    def _lock_holder(self):
        return self._transport._lock_holder

    @_lock_holder.setter
    def _lock_holder(self, value) -> None:
        self._transport._lock_holder = value
