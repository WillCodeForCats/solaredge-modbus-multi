"""The SolarEdge Modbus Multi select module."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    LIMIT_CONTROL,
    LIMIT_CONTROL_MODE,
    REACTIVE_POWER_CONFIG,
    STORAGE_AC_CHARGE_POLICY,
    STORAGE_CONTROL_MODE,
    STORAGE_MODE,
    SunSpecNotImpl,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setup entry."""
    hub = hass.data[DOMAIN][config_entry.entry_id]["hub"]
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    entities = []

    for inverter in hub.inverters:
        """Power Control Options: Storage Control"""
        if hub.option_storage_control:
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
        if hub.option_detect_extras:
            entities.append(
                SolarEdgeReactivePowerMode(inverter, config_entry, coordinator)
            )

    if entities:
        async_add_entities(entities)


def get_key(d, search):
    """Return the key."""
    for k, v in d.items():
        if v == search:
            return k
    return None


class SolarEdgeSelectBase(CoordinatorEntity, SelectEntity):
    """Representation of a solar edge select base."""

    should_poll = False
    _attr_has_entity_name = True
    entity_category = EntityCategory.CONFIG

    def __init__(self, platform, config_entry, coordinator):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        """Initialize the sensor."""
        self._platform = platform
        self._config_entry = config_entry

    @property
    def device_info(self):
        """Return the device info."""
        return self._platform.device_info

    @property
    def config_entry_id(self):
        """Return the config entry id."""
        return self._config_entry.entry_id

    @property
    def config_entry_name(self):
        """Return the config entry name."""
        return self._config_entry.data["name"]

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class StorageControlMode(SolarEdgeSelectBase):
    """Representation of a storage control mode."""

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the storage control mode."""
        super().__init__(platform, config_entry, coordinator)
        self._options = STORAGE_CONTROL_MODE
        self._attr_options = list(self._options.values())

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_storage_control_mode"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Storage Control Mode"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return self._platform.has_battery is True

    @property
    def available(self) -> bool:
        """Return the available."""
        control_mode = self._platform.storage_control_data.control_mode
        return (
            super().available
            and self._platform.has_storage_control
            and control_mode != SunSpecNotImpl.UINT16
            and control_mode in self._options
        )

    @property
    def current_option(self) -> str:
        """Return the current option."""
        return self._options[self._platform.storage_control_data.control_mode]

    async def async_select_option(self, option: str) -> None:
        """Select option."""
        _LOGGER.debug("set %s to %s", self.unique_id, option)
        new_mode = get_key(self._options, option)
        await self._platform.write(
            self._platform.storage_control_data, "control_mode", new_mode
        )
        await self.async_update()


class StorageACChargePolicy(SolarEdgeSelectBase):
    """Representation of a storage ac charge policy."""

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the storage ac charge policy."""
        super().__init__(platform, config_entry, coordinator)
        self._options = STORAGE_AC_CHARGE_POLICY
        self._attr_options = list(self._options.values())

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_ac_charge_policy"

    @property
    def name(self) -> str:
        """Return the name."""
        return "AC Charge Policy"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return self._platform.has_battery is True

    @property
    def available(self) -> bool:
        """Return the available."""
        ac_charge_policy = self._platform.storage_control_data.ac_charge_policy
        return (
            super().available
            and self._platform.has_storage_control
            and ac_charge_policy != SunSpecNotImpl.UINT16
            and ac_charge_policy in self._options
        )

    @property
    def current_option(self) -> str:
        """Return the current option."""
        return self._options[self._platform.storage_control_data.ac_charge_policy]

    async def async_select_option(self, option: str) -> None:
        """Select option."""
        _LOGGER.debug("set %s to %s", self.unique_id, option)
        new_mode = get_key(self._options, option)
        await self._platform.write(
            self._platform.storage_control_data, "ac_charge_policy", new_mode
        )
        await self.async_update()


class StorageDefaultMode(SolarEdgeSelectBase):
    """Representation of a storage default mode."""

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the storage default mode."""
        super().__init__(platform, config_entry, coordinator)
        self._options = STORAGE_MODE
        self._attr_options = list(self._options.values())

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_storage_default_mode"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Storage Default Mode"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return self._platform.has_battery is True

    @property
    def available(self) -> bool:
        """Return the available."""
        default_mode = self._platform.storage_control_data.default_mode
        return (
            super().available
            and self._platform.has_storage_control
            and default_mode != SunSpecNotImpl.UINT16
            and default_mode in self._options
            # Available only in remote control mode
            and self._platform.storage_control_data.control_mode == 4
        )

    @property
    def current_option(self) -> str:
        """Return the current option."""
        return self._options[self._platform.storage_control_data.default_mode]

    async def async_select_option(self, option: str) -> None:
        """Select option."""
        _LOGGER.debug("set %s to %s", self.unique_id, option)
        new_mode = get_key(self._options, option)
        await self._platform.write(
            self._platform.storage_control_data, "default_mode", new_mode
        )
        await self.async_update()


class StorageCommandMode(SolarEdgeSelectBase):
    """Representation of a storage command mode."""

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the storage command mode."""
        super().__init__(platform, config_entry, coordinator)
        self._options = STORAGE_MODE
        self._attr_options = list(self._options.values())

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_storage_command_mode"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Storage Command Mode"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return self._platform.has_battery is True

    @property
    def available(self) -> bool:
        """Return the available."""
        command_mode = self._platform.storage_control_data.command_mode
        return (
            super().available
            and self._platform.has_storage_control
            and command_mode != SunSpecNotImpl.UINT16
            and command_mode in self._options
            # Available only in remote control mode
            and self._platform.storage_control_data.control_mode == 4
        )

    @property
    def current_option(self) -> str:
        """Return the current option."""
        return self._options[self._platform.storage_control_data.command_mode]

    async def async_select_option(self, option: str) -> None:
        """Select option."""
        _LOGGER.debug("set %s to %s", self.unique_id, option)
        new_mode = get_key(self._options, option)
        await self._platform.write(
            self._platform.storage_control_data, "command_mode", new_mode
        )
        await self.async_update()


class SolaredgeLimitControlMode(SolarEdgeSelectBase):
    """Representation of a solaredge limit control mode."""

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the solaredge limit control mode."""
        super().__init__(platform, config_entry, coordinator)
        self._options = LIMIT_CONTROL_MODE
        self._attr_options = list(self._options.values())

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.site_limit_control_data.E_Lim_Ctl_Mode
        return (
            super().available
            and self._platform.has_site_limit_control
            and value is not None
            and value != SunSpecNotImpl.UINT16
        )

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_limit_control_mode"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Limit Control Mode"

    @property
    def current_option(self) -> str:
        """Return the current option."""
        value = self._platform.site_limit_control_data.E_Lim_Ctl_Mode

        if (value >> 0) & 1:
            return self._options[0]

        if (value >> 1) & 1:
            return self._options[1]

        if (value >> 2) & 1:
            return self._options[2]

        return self._options[None]

    async def async_select_option(self, option: str) -> None:
        """Select option."""
        set_bits = self._platform.site_limit_control_data.E_Lim_Ctl_Mode
        new_mode = get_key(self._options, option)

        set_bits = set_bits & ~(1 << 0)
        set_bits = set_bits & ~(1 << 1)
        set_bits = set_bits & ~(1 << 2)

        if new_mode is not None:
            set_bits = set_bits | (1 << int(new_mode))

        _LOGGER.debug("set %s bits %s", self.unique_id, format(set_bits, "016b"))
        await self._platform.write(
            self._platform.site_limit_control_data, "E_Lim_Ctl_Mode", set_bits
        )
        await self.async_update()


class SolaredgeLimitControl(SolarEdgeSelectBase):
    """Representation of a solaredge limit control."""

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the solaredge limit control."""
        super().__init__(platform, config_entry, coordinator)
        self._options = LIMIT_CONTROL
        self._attr_options = list(self._options.values())

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.site_limit_control_data.E_Lim_Ctl
        return (
            super().available
            and self._platform.has_site_limit_control
            and value is not None
            and value != SunSpecNotImpl.UINT16
        )

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_limit_control"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Limit Control"

    @property
    def current_option(self) -> str:
        """Return the current option."""
        return self._options[self._platform.site_limit_control_data.E_Lim_Ctl]

    async def async_select_option(self, option: str) -> None:
        """Select option."""
        _LOGGER.debug("set %s to %s", self.unique_id, option)
        new_mode = get_key(self._options, option)
        await self._platform.write(
            self._platform.site_limit_control_data, "E_Lim_Ctl", new_mode
        )
        await self.async_update()


class SolarEdgeReactivePowerMode(SolarEdgeSelectBase):
    """Representation of a solar edge reactive power mode."""

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the solar edge reactive power mode."""
        super().__init__(platform, config_entry, coordinator)
        self._options = REACTIVE_POWER_CONFIG
        self._attr_options = list(self._options.values())

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.advanced_power_control_data.ReactivePwrConfig
        return (
            super().available
            and self._platform.has_advanced_power_control
            and value is not None
            and value != SunSpecNotImpl.INT32
            and value in self._options
        )

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_reactive_power_mode"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Reactive Power Mode"

    @property
    def current_option(self) -> str:
        """Return the current option."""
        return self._options[
            self._platform.advanced_power_control_data.ReactivePwrConfig
        ]

    async def async_select_option(self, option: str) -> None:
        """Select option."""
        _LOGGER.debug("set %s to %s", self.unique_id, option)
        new_mode = get_key(self._options, option)
        await self._platform.write(
            self._platform.advanced_power_control_data, "ReactivePwrConfig", new_mode
        )
        await self.async_update()
