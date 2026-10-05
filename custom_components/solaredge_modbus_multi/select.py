from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from modbus_connection.encode import encode_int32, encode_uint16

from . import SolarEdgeConfigEntry
from .const import (
    LIMIT_CONTROL,
    LIMIT_CONTROL_MODE,
    REACTIVE_POWER_CONFIG,
    STORAGE_AC_CHARGE_POLICY,
    STORAGE_CONTROL_MODE,
    STORAGE_MODE,
    SunSpecNotImpl,
)
from .entity import SolarEdgeEntityBase

_LOGGER = logging.getLogger(__name__)

# Writes go to an inverter with a single Modbus session; one service call
# at a time per platform (the transport lock is the real guard).
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: SolarEdgeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    hub = config_entry.runtime_data.hub
    coordinator = config_entry.runtime_data.coordinator

    # Every entity on this platform writes to the inverter.
    if not hub.option_allow_hardware_writes:
        return

    entities = []

    for inverter in hub.inverters:
        """Power Control Options: Storage Control"""
        if hub.option_storage_control and inverter.decoded_storage_control:
            entities.append(StorageControlMode(inverter, config_entry, coordinator))
            entities.append(StorageACChargePolicy(inverter, config_entry, coordinator))
            entities.append(StorageDefaultMode(inverter, config_entry, coordinator))
            entities.append(StorageCommandMode(inverter, config_entry, coordinator))

        """ Power Control Options: Site Limit Control """
        if hub.option_site_limit_control:
            entities.append(
                SolaredgeLimitControlMode(inverter, config_entry, coordinator)
            )
            entities.append(SolaredgeLimitControl(inverter, config_entry, coordinator))

        """ Power Control Block """
        if inverter.apc_may_be_supported:
            entities.append(
                SolarEdgeReactivePowerMode(inverter, config_entry, coordinator)
            )

    if entities:
        async_add_entities(entities)


def get_key(d, search):
    for k, v in d.items():
        if v == search:
            return k
    return None


class SolarEdgeSelectBase(SolarEdgeEntityBase, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG
    uid_suffix: str | None = None

    def __init__(self, platform, config_entry, coordinator) -> None:
        super().__init__(platform, config_entry, coordinator)
        if self.uid_suffix is not None:
            self._attr_unique_id = f"{platform.uid_base}_{self.uid_suffix}"


class StorageControlMode(SolarEdgeSelectBase):
    _attr_name = "Storage Control Mode"
    uid_suffix = "storage_control_mode"

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        self._options = STORAGE_CONTROL_MODE
        self._attr_options = list(self._options.values())

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self._platform.has_battery is True

    @property
    def available(self) -> bool:
        try:
            if (
                self._platform.decoded_storage_control is False
                or self._platform.decoded_storage_control["control_mode"]
                == SunSpecNotImpl.UINT16
                or self._platform.decoded_storage_control["control_mode"]
                not in self._options
            ):
                return False

            return super().available

        except KeyError:
            return False

    @property
    def current_option(self) -> str:
        return self._options[self._platform.decoded_storage_control["control_mode"]]

    async def async_select_option(self, option: str) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {option}")
        new_mode = get_key(self._options, option)
        await self._platform.write_registers(
            address=57348,
            payload=encode_uint16(new_mode),
        )
        await self.async_update()


class StorageACChargePolicy(SolarEdgeSelectBase):
    _attr_name = "AC Charge Policy"
    uid_suffix = "ac_charge_policy"

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        self._options = STORAGE_AC_CHARGE_POLICY
        self._attr_options = list(self._options.values())

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self._platform.has_battery is True

    @property
    def available(self) -> bool:
        try:
            if (
                self._platform.decoded_storage_control is False
                or self._platform.decoded_storage_control["ac_charge_policy"]
                == SunSpecNotImpl.UINT16
                or self._platform.decoded_storage_control["ac_charge_policy"]
                not in self._options
            ):
                return False

            return super().available

        except KeyError:
            return False

    @property
    def current_option(self) -> str:
        return self._options[self._platform.decoded_storage_control["ac_charge_policy"]]

    async def async_select_option(self, option: str) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {option}")
        new_mode = get_key(self._options, option)
        await self._platform.write_registers(
            address=57349,
            payload=encode_uint16(new_mode),
        )
        await self.async_update()


class StorageDefaultMode(SolarEdgeSelectBase):
    _attr_name = "Storage Default Mode"
    uid_suffix = "storage_default_mode"

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        self._options = STORAGE_MODE
        self._attr_options = list(self._options.values())

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self._platform.has_battery is True

    @property
    def available(self) -> bool:
        try:
            if (
                self._platform.decoded_storage_control is False
                or self._platform.decoded_storage_control["default_mode"]
                == SunSpecNotImpl.UINT16
                or self._platform.decoded_storage_control["default_mode"]
                not in self._options
            ):
                return False

            # Available only in remote control mode
            return (
                super().available
                and self._platform.decoded_storage_control["control_mode"] == 4
            )

        except KeyError:
            return False

    @property
    def current_option(self) -> str:
        return self._options[self._platform.decoded_storage_control["default_mode"]]

    async def async_select_option(self, option: str) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {option}")
        new_mode = get_key(self._options, option)
        await self._platform.write_registers(
            address=57354,
            payload=encode_uint16(new_mode),
        )
        await self.async_update()


class StorageCommandMode(SolarEdgeSelectBase):
    _attr_name = "Storage Command Mode"
    uid_suffix = "storage_command_mode"

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        self._options = STORAGE_MODE
        self._attr_options = list(self._options.values())

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self._platform.has_battery is True

    @property
    def available(self) -> bool:
        try:
            if (
                self._platform.decoded_storage_control is False
                or self._platform.decoded_storage_control["command_mode"]
                == SunSpecNotImpl.UINT16
                or self._platform.decoded_storage_control["command_mode"]
                not in self._options
            ):
                return False

            # Available only in remote control mode
            return (
                super().available
                and self._platform.decoded_storage_control["control_mode"] == 4
            )

        except KeyError:
            return False

    @property
    def current_option(self) -> str:
        return self._options[self._platform.decoded_storage_control["command_mode"]]

    async def async_select_option(self, option: str) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {option}")
        new_mode = get_key(self._options, option)
        await self._platform.write_registers(
            address=57357,
            payload=encode_uint16(new_mode),
        )
        await self.async_update()


class SolaredgeLimitControlMode(SolarEdgeSelectBase):
    _attr_name = "Limit Control Mode"
    uid_suffix = "limit_control_mode"

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        self._options = LIMIT_CONTROL_MODE
        self._attr_options = list(self._options.values())

    @property
    def available(self) -> bool:
        try:
            if self._platform.decoded_model["E_Lim_Ctl_Mode"] == SunSpecNotImpl.UINT16:
                return False

            return super().available

        except KeyError:
            return False

    @property
    def current_option(self) -> str:
        if (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 0) & 1:
            return self._options[0]

        elif (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 1) & 1:
            return self._options[1]

        elif (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 2) & 1:
            return self._options[2]

        else:
            return self._options[None]

    async def async_select_option(self, option: str) -> None:
        set_bits = int(self._platform.decoded_model["E_Lim_Ctl_Mode"])
        new_mode = get_key(self._options, option)

        set_bits = set_bits & ~(1 << 0)
        set_bits = set_bits & ~(1 << 1)
        set_bits = set_bits & ~(1 << 2)

        if new_mode is not None:
            set_bits = set_bits | (1 << int(new_mode))

        _LOGGER.debug(f"set {self.unique_id} bits {set_bits:016b}")
        await self._platform.write_registers(
            address=57344,
            payload=encode_uint16(set_bits),
        )
        await self.async_update()


class SolaredgeLimitControl(SolarEdgeSelectBase):
    _attr_name = "Limit Control"
    uid_suffix = "limit_control"

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        self._options = LIMIT_CONTROL
        self._attr_options = list(self._options.values())

    @property
    def available(self) -> bool:
        try:
            if self._platform.decoded_model["E_Lim_Ctl"] == SunSpecNotImpl.UINT16:
                return False

            return super().available

        except KeyError:
            return False

    @property
    def current_option(self) -> str:
        return self._options[self._platform.decoded_model["E_Lim_Ctl"]]

    async def async_select_option(self, option: str) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {option}")
        new_mode = get_key(self._options, option)
        await self._platform.write_registers(
            address=57345,
            payload=encode_uint16(new_mode),
        )
        await self.async_update()


class SolarEdgeReactivePowerMode(SolarEdgeSelectBase):
    _attr_name = "Reactive Power Mode"
    uid_suffix = "reactive_power_mode"

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        self._options = REACTIVE_POWER_CONFIG
        self._attr_options = list(self._options.values())

    @property
    def available(self) -> bool:
        try:
            if (
                self._platform.decoded_model["ReactivePwrConfig"]
                == SunSpecNotImpl.INT32
                or self._platform.decoded_model["ReactivePwrConfig"]
                not in self._options
            ):
                return False

            return super().available

        except KeyError:
            return False

    @property
    def current_option(self) -> str:
        return self._options[self._platform.decoded_model["ReactivePwrConfig"]]

    async def async_select_option(self, option: str) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {option}")
        new_mode = get_key(self._options, option)
        await self._platform.write_registers(
            address=61700,
            payload=encode_int32(new_mode, word_order="little"),
        )
        await self.async_update()
