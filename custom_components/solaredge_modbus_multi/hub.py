"""SolarEdge Modbus Multi hub: session orchestration and polling.

Device classes live in devices.py, the exception hierarchy in exceptions.py
and the repair-issue id helpers in const.py. The names re-exported below are
the ones the platforms and tests still import from here; import anything
else from its own module.
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

from .const import (
    BATTERY_REG_BASE,
    DOMAIN,
    METER_REG_BASE,
    ConfDefaultFlag,
    ConfDefaultInt,
    ConfDefaultStr,
    ConfName,
    ModbusDefaults,
    PollGroup,
    RetrySettings,
    SolarEdgeTimeouts,
    check_config_issue_id,
    detect_timeout_issue_id,
)
from .devices import (
    SolarEdgeBattery,
    SolarEdgeEVSE,
    SolarEdgeInverter,
    SolarEdgeMeter,
)
from .exceptions import (
    DataUpdateFailed,
    DeviceInvalid,
    DeviceIsEVSE,
    HubInitFailed,
    ModbusIllegalAddress,
    ModbusIllegalFunction,
    ModbusIllegalValue,
    ModbusIOError,
    ModbusReadError,
    ModbusWriteError,
)
from .helpers import async_delete_entry_issues
from .modbus_transport import ModbusTransport

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "DataUpdateFailed",
    "DeviceInvalid",
    "DeviceIsEVSE",
    "HubInitFailed",
    "ModbusIllegalAddress",
    "ModbusIllegalFunction",
    "ModbusIllegalValue",
    "ModbusIOError",
    "ModbusReadError",
    "SolarEdgeBattery",
    "SolarEdgeEVSE",
    "SolarEdgeInverter",
    "SolarEdgeMeter",
    "SolarEdgeModbusMultiHub",
    "async_delete_entry_issues",
    "check_config_issue_id",
    "detect_timeout_issue_id",
]


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
        self._allow_hardware_writes = entry_options.get(
            ConfName.ALLOW_HARDWARE_WRITES,
            bool(ConfDefaultFlag.ALLOW_HARDWARE_WRITES),
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
        self._poll_multipliers = self._build_poll_multipliers(entry_options)
        self._poll_cycle = -1
        self._slow_poll_requests = 0
        # Everything is due until the first refresh decides otherwise, so
        # discovery and cycle 0 always see a complete picture.
        self._due_groups: set[PollGroup] = set(PollGroup)
        self._group_last_cycle: dict[PollGroup, int | None] = dict.fromkeys(PollGroup)
        self._groups_read: set[PollGroup] = set()
        self._settings_read_incomplete = False
        self._retry_limit = self._yaml_config.get("retry", {}).get(
            "limit", RetrySettings.Limit
        )
        # Of the YAML `modbus:` options only `timeout` still reaches the
        # transport: modbus-connection issues each request once and reconnects
        # on demand, so retries and reconnect delays are no longer ours to
        # set. The keys stay accepted for configuration compatibility.
        self._mb_timeout = self._yaml_config.get("modbus", {}).get(
            "timeout", ModbusDefaults.Timeout
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

        self._transport = ModbusTransport(
            host=self._host,
            port=self._port,
            timeout=self._mb_timeout,
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
                f"allow_hardware_writes={self._allow_hardware_writes}, "
                f"sleep_after_write={self._sleep_after_write}, "
                f"battery_rating_adjust={self._battery_rating_adjust}, "
            ),
        )

        _LOGGER.debug(f"pymodbus version {self.pymodbus_version}")
        _LOGGER.debug(f"poll multipliers: {dict(self._poll_multipliers)}")

    def _build_poll_multipliers(self, entry_options) -> dict[PollGroup, int]:
        """Resolve each group's cadence from options then advanced YAML.

        Defaults reproduce the pre-poll-group behaviour exactly: everything
        every cycle except the settings blocks, which keep the existing
        slow_poll_multiplier option. A YAML `poll:` entry overrides it.
        """
        multipliers = dict.fromkeys(PollGroup, 1)
        multipliers[PollGroup.SETTINGS] = max(
            1,
            int(
                entry_options.get(
                    ConfName.SLOW_POLL_MULTIPLIER,
                    ConfDefaultInt.SLOW_POLL_MULTIPLIER,
                )
            ),
        )

        for name, multiplier in self._yaml_config.get("poll", {}).items():
            group = PollGroup(name)
            if group is PollGroup.CORE:
                continue
            multipliers[group] = max(1, int(multiplier))

        return multipliers

    def poll_due(self, group: PollGroup) -> bool:
        """Whether this refresh reads the blocks belonging to `group`."""
        return group in self._due_groups

    def note_group_read(self, group: PollGroup) -> None:
        """Record that a block belonging to `group` was actually read.

        Being due is not evidence of anything: a group whose blocks are
        disabled by options, or whose device list is empty, would otherwise
        report a cadence it never performed.
        """
        self._groups_read.add(group)

    def note_settings_read_incomplete(self) -> None:
        """Record that a settings block did not answer this refresh.

        Detect-probe timeouts are handled inside the device read, so the
        refresh still completes. The settings data is stale, though, so this
        poll must not count as having served a write-forced re-read.
        """
        self._settings_read_incomplete = True

    async def _async_init_solaredge(self) -> None:
        """Detect devices and load initial modbus data from inverters."""

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

                        new_meter.inverter = new_inverter
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

                        new_battery.inverter = new_inverter
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
            ModbusIOError,
            TimeoutError,
        ) as e:
            await self.disconnect()
            if isinstance(
                e, (ModbusReadError, ModbusIllegalFunction, ModbusIllegalValue)
            ):
                raise HubInitFailed(f"Read error: {e}")
            if isinstance(e, DeviceInvalid):
                raise HubInitFailed(f"Invalid device: {e}")
            if isinstance(e, ModbusIOError):
                raise HubInitFailed(f"Connection failed: {e}")
            raise HubInitFailed(f"Timeout error: {e}")

        self.initalized = True

    async def async_refresh_modbus_data(self) -> bool:
        """Refresh modbus data from inverters."""

        try:
            await self.connect()
        except ModbusIOError as e:
            # A refused connection must reach the coordinator as one of our
            # failure types with its repair issue raised, not as a bare
            # transport error that bypasses both.
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
            if not self.initalized:
                raise HubInitFailed(f"Setup failed: {e}")
            raise DataUpdateFailed(f"Connection failed: {e}")

        if not self.initalized:
            try:
                async with asyncio.timeout(self.coordinator_timeout):
                    await self._async_init_solaredge()

            except (ModbusIOError, TimeoutError) as e:
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
        self._due_groups = {
            group
            for group, multiplier in self._poll_multipliers.items()
            if next_cycle % multiplier == 0
        }
        if served_slow_poll_requests > 0:
            self._due_groups.add(PollGroup.SETTINGS)
        self._settings_read_incomplete = False
        self._groups_read = set()

        # CORE's multiplier is pinned to 1, so its poll_due is always true.
        device_groups = (
            (PollGroup.CORE, self.inverters),
            (PollGroup.METER, self.meters),
            (PollGroup.BATTERY, self.batteries),
            (PollGroup.EVSE, self.evses),
        )

        try:
            async with asyncio.timeout(self.coordinator_timeout):
                # Read all devices sequentially with batch lock per device
                for group, devices in device_groups:
                    if not self.poll_due(group):
                        continue
                    for device in devices:
                        await self._poll_device_with_lock(device)
                    if devices:
                        self.note_group_read(group)

        except (
            ModbusReadError,
            ModbusIllegalFunction,
            ModbusIllegalValue,
            DeviceInvalid,
            ModbusIOError,
        ) as e:
            await self.disconnect()
            if isinstance(
                e, (ModbusReadError, ModbusIllegalFunction, ModbusIllegalValue)
            ):
                raise DataUpdateFailed(f"Update failed: {e}")
            if isinstance(e, DeviceInvalid):
                raise DataUpdateFailed(f"Invalid device: {e}")
            raise DataUpdateFailed(f"Connection failed: {e}")

        except TimeoutError as e:
            await self.disconnect()
            self._timeout_counter += 1

            _LOGGER.debug(
                f"Refresh timeout {self._timeout_counter} limit {self._retry_limit}"
            )

            if self._timeout_counter >= self._retry_limit:
                self._timeout_counter = 0
                raise TimeoutError

            # asyncio.timeout() raises a bare TimeoutError whose str() is empty,
            # which rendered as "Timeout error: " with nothing after the colon.
            raise DataUpdateFailed(f"Timeout error: {e}" if str(e) else "Timeout error")

        self._poll_cycle = next_cycle

        # The forced-request accounting asks "did the settings poll run to
        # completion" — which is true even where no settings block exists,
        # otherwise a write on such a hub would leave the request pending
        # forever. `last_served_cycle` asks the stricter question of whether
        # anything was physically read, so it keys off _groups_read instead.
        settings_complete = (
            self.poll_due(PollGroup.SETTINGS) and not self._settings_read_incomplete
        )
        for group in self._groups_read:
            if group is PollGroup.SETTINGS and self._settings_read_incomplete:
                continue
            self._group_last_cycle[group] = next_cycle

        # Consume only the requests this poll actually served; requests from
        # writes that landed during the refresh stay pending for the next one.
        # A settings block whose detect probe timed out is handled inside the
        # device read, so the refresh still "succeeds" — but it did not verify
        # the write, so the forced request must survive to the next cycle.
        if settings_complete:
            self._slow_poll_requests -= served_slow_poll_requests

        # SolarEdge requires an explicit commit for static power-control
        # settings to survive an inverter restart. Warn once per batch,
        # after a slow poll has re-read the control blocks post-write.
        if (
            settings_complete
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

        # Timestamps follow physical reads: a device whose group was skipped
        # must not claim a refresh it never got. EVSE devices do not track a
        # last-update timestamp.
        timestamp = dt.now()
        for group, devices in device_groups:
            if group is PollGroup.EVSE or not self.poll_due(group):
                continue
            for device in devices:
                device.set_last_update(timestamp)

        return True

    async def connect(self) -> None:
        """Connect to inverter."""
        await self._transport.connect()

    async def disconnect(self) -> None:
        """Disconnect from inverter, retiring the connection generation."""
        await self._transport.recycle()

    async def shutdown(self) -> None:
        """Shut down the hub and disconnect."""

        self.online = False
        await self.disconnect()

    async def modbus_read_holding_registers(
        self, unit, address, rcount, group: PollGroup | None = None
    ):
        """Read modbus registers from inverter.

        Error responses are already mapped to our exception hierarchy by the
        transport, which is where the library's types stop. When `group` is
        given, a validated response records a served read for that poll
        group, so cadence evidence stays keyed to physical reads.
        """

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                f"I{unit}: modbus_read_holding_registers "
                f"address={address} count={rcount}"
            )

        result = await self._transport.read_holding_registers_raw(unit, address, rcount)

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

        if group is not None:
            self.note_group_read(group)

        return result

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

        # Central refusal, not just entity suppression: a stale entity, a
        # restored service call or a future caller must not reach the
        # transport while hardware writes are disabled.
        if not self._allow_hardware_writes:
            raise HomeAssistantError(
                "Hardware writes are disabled for this SolarEdge hub. Enable "
                '"Allow Hardware Writes" in the integration options to permit '
                f"writing to device ID {unit}."
            )

        try:
            await self._transport.write_registers_raw(unit, address, payload)

        except ModbusIllegalAddress:
            raise HomeAssistantError(f"Address not supported at device at ID {unit}.")

        except ModbusIllegalFunction:
            raise HomeAssistantError(f"Function not supported by device at ID {unit}.")

        except ModbusIllegalValue:
            raise HomeAssistantError(f"Value invalid for device at ID {unit}.")

        except ModbusIOError as e:
            # Outcome unknown: the frame may have been applied before the
            # response was lost. The transport has already retired the
            # connection; never re-send a power-control write on its own.
            # Do request the re-read though — it is what turns "may or may
            # not have been applied" into an answer one poll later, instead
            # of leaving stale entity state until the settings cadence comes
            # round, which can be minutes.
            self._note_write_pending_verification(address, confirmed=False)
            _LOGGER.error(f"Write to inverter ID {unit} had no response: {e}")
            raise HomeAssistantError(
                f"No response from inverter ID {unit}; the write at address "
                f"{address} may or may not have been applied."
            )

        except ModbusWriteError as e:
            raise HomeAssistantError(
                f"Error sending command to inverter ID {unit}: {e}."
            )

        except asyncio.CancelledError:
            # The frame may have reached the inverter before the cancellation
            # landed, so the outcome is as uncertain as a lost response.
            self._note_write_pending_verification(address, confirmed=False)
            raise

        self.has_write = address
        self._note_write_pending_verification(address, confirmed=True)

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

    def _note_write_pending_verification(
        self, address: int, *, confirmed: bool
    ) -> None:
        """Book a write for re-reading, whether or not it was confirmed.

        A confirmed write, one whose response was lost, and one cancelled
        mid-flight all leave the settings blocks possibly changed and the
        entities possibly stale, so all three force the re-read.

        `confirmed` decides only what may be *forgotten*. Both directions err
        the same way — toward warning rather than silence: an unconfirmed
        setting is still tracked, because prompting a harmless commit beats
        losing it at the next inverter restart; and an unconfirmed commit does
        not clear that tracking, because a commit that never landed would
        otherwise take the warning away with it.
        """
        # A counter, not a flag, so an in-flight refresh cannot consume this
        # request; it must be recorded exactly once per write.
        self._slow_poll_requests += 1

        # Track APC static settings pending an explicit commit (61696) or
        # restore-defaults (61697); blocks span 61696-61781 and 61782-61865.
        if address in (61696, 61697):
            if not confirmed:
                _LOGGER.debug(
                    "Commit/restore at %s was not confirmed; keeping %s pending.",
                    address,
                    sorted(self._uncommitted_power_settings),
                )
                return

            if self._uncommitted_power_settings:
                _LOGGER.debug(
                    "Power control settings %s committed/restored.",
                    sorted(self._uncommitted_power_settings),
                )
            self._uncommitted_power_settings.clear()
            self._uncommitted_warned = False
        elif 61698 <= address <= 61865:
            self._uncommitted_power_settings.add(address)

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
    def poll_groups(self) -> dict[str, dict[str, int | bool | None]]:
        """Per-group cadence, current due state, and last cycle actually served.

        `last_served_cycle` is what proves the configured cadence is really
        happening — `multiplier` and `due` only describe intent. A settings
        poll whose detect probe timed out does not advance it.
        """
        return {
            f"{group}": {
                "multiplier": self._poll_multipliers[group],
                "due": group in self._due_groups,
                "last_served_cycle": self._group_last_cycle[group],
            }
            for group in PollGroup
        }

    @property
    def slow_poll_due(self) -> bool:
        """Alias kept so the settings-tier guards read unchanged."""
        return PollGroup.SETTINGS in self._due_groups

    @slow_poll_due.setter
    def slow_poll_due(self, value: bool) -> None:
        if value:
            self._due_groups.add(PollGroup.SETTINGS)
        else:
            self._due_groups.discard(PollGroup.SETTINGS)

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
    def option_allow_hardware_writes(self) -> bool:
        return self._allow_hardware_writes

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
        return self._transport._connection

    @_client.setter
    def _client(self, value) -> None:
        self._transport._connection = value

    @property
    def _modbus_lock(self) -> asyncio.Lock:
        return self._transport._lock

    @property
    def _lock_holder(self):
        return self._transport._lock_holder

    @_lock_holder.setter
    def _lock_holder(self, value) -> None:
        self._transport._lock_holder = value
