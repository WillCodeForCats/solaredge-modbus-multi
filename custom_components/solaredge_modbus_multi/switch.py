"""Switch platform for SolarEdge Modbus Multi."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SunSpecNotImpl
from .coordinator import SolarEdgeConfigEntry
from .entity import SolarEdgeEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: SolarEdgeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setup entry."""
    hub = config_entry.runtime_data.hub
    coordinator = config_entry.runtime_data.coordinator

    entities = []

    """ Power Control Options: Site Limit Control """
    for inverter in hub.inverters:
        if hub.option_site_limit_control is True:
            entities.append(
                SolarEdgeExternalProduction(inverter, config_entry, coordinator)
            )
            entities.append(
                SolarEdgeNegativeSiteLimit(inverter, config_entry, coordinator)
            )

        if hub.option_detect_extras:
            entities.append(SolarEdgeGridControl(inverter, config_entry, coordinator))

    if entities:
        async_add_entities(entities)


class SolarEdgeSwitchBase(SolarEdgeEntity, SwitchEntity):
    """Representation of a solar edge switch base."""


class SolarEdgeExternalProduction(SolarEdgeSwitchBase):
    """External Production switch. Indicates a non-SolarEdge power sorce in system."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "External Production"
    _attr_entity_registry_enabled_default = False

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the entity."""
        super().__init__(platform, config_entry, coordinator)
        self._attr_unique_id = f"{platform.uid_base}_external_production"

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
    def is_on(self) -> bool:
        """Return True if on."""
        return (self._platform.site_limit_control_data.E_Lim_Ctl_Mode >> 10) & 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        set_bits = self._platform.site_limit_control_data.E_Lim_Ctl_Mode
        set_bits = set_bits | (1 << 10)

        _LOGGER.debug("set %s bits %s", self.unique_id, format(set_bits, "016b"))

        await self._platform.write(
            self._platform.site_limit_control_data, "E_Lim_Ctl_Mode", set_bits
        )
        await self.async_update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        set_bits = self._platform.site_limit_control_data.E_Lim_Ctl_Mode
        set_bits = set_bits & ~(1 << 10)

        _LOGGER.debug("set %s bits %s", self.unique_id, format(set_bits, "016b"))

        await self._platform.write(
            self._platform.site_limit_control_data, "E_Lim_Ctl_Mode", set_bits
        )
        await self.async_update()


class SolarEdgeNegativeSiteLimit(SolarEdgeSwitchBase):
    """Negative Site Limit switch. Sets minimum import power when enabled."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Negative Site Limit"

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the entity."""
        super().__init__(platform, config_entry, coordinator)
        self._attr_unique_id = f"{platform.uid_base}_negative_site_limit"

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
    def is_on(self) -> bool:
        """Return True if on."""
        return (self._platform.site_limit_control_data.E_Lim_Ctl_Mode >> 11) & 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        set_bits = self._platform.site_limit_control_data.E_Lim_Ctl_Mode
        set_bits = set_bits | (1 << 11)

        _LOGGER.debug("set %s bits %s", self.unique_id, format(set_bits, "016b"))

        await self._platform.write(
            self._platform.site_limit_control_data, "E_Lim_Ctl_Mode", set_bits
        )
        await self.async_update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        set_bits = self._platform.site_limit_control_data.E_Lim_Ctl_Mode
        set_bits = set_bits & ~(1 << 11)

        _LOGGER.debug("set %s bits %s", self.unique_id, format(set_bits, "016b"))

        await self._platform.write(
            self._platform.site_limit_control_data, "E_Lim_Ctl_Mode", set_bits
        )
        await self.async_update()


class SolarEdgeGridControl(SolarEdgeSwitchBase):
    """Grid Control boolean switch. This is "AdvancedPwrControlEn" in specs."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Advanced Power Control"

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the entity."""
        super().__init__(platform, config_entry, coordinator)
        self._attr_unique_id = f"{platform.uid_base}_adv_pwr_ctrl"

    @property
    def available(self) -> bool:
        """Return the available."""
        return (
            super().available
            and self._platform.has_advanced_power_control
            and self._platform.advanced_power_control_data.AdvPwrCtrlEn is not None
        )

    @property
    def is_on(self) -> bool:
        """Return True if on."""
        return self._platform.advanced_power_control_data.AdvPwrCtrlEn == 0x1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on."""
        _LOGGER.debug("set %s to 0x1", self.unique_id)

        await self._platform.write(
            self._platform.advanced_power_control_data, "AdvPwrCtrlEn", 0x1
        )
        await self.async_update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        _LOGGER.debug("set %s to 0x0", self.unique_id)

        await self._platform.write(
            self._platform.advanced_power_control_data, "AdvPwrCtrlEn", 0x0
        )
        await self.async_update()
