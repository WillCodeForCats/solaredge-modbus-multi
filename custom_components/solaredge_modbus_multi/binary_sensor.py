"""Component to interface with binary sensors."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

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
        entities.append(GridStatusOnOff(inverter, config_entry, coordinator))
        if hub.option_detect_extras:
            entities.append(AdvPowerControlEnabled(inverter, config_entry, coordinator))

    if entities:
        async_add_entities(entities)


class SolarEdgeBinarySensorBase(CoordinatorEntity, BinarySensorEntity):
    """Base class for SolarEdge binary sensor entities."""

    should_poll = False
    _attr_has_entity_name = True

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


class AdvPowerControlEnabled(SolarEdgeBinarySensorBase):
    """Grid Control boolean status. This is "AdvancedPwrControlEn" in specs."""

    entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        """Return the available."""
        return (
            super().available
            and self._platform.has_advanced_power_control
            and self._platform.advanced_power_control_data.AdvPwrCtrlEn is not None
        )

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_adv_pwr_ctrl_en"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Advanced Power Control"

    @property
    def is_on(self) -> bool:
        """Return True if on."""
        return self._platform.advanced_power_control_data.AdvPwrCtrlEn == 0x1


class GridStatusOnOff(SolarEdgeBinarySensorBase):
    """Grid Status On Off. This is undocumented from discussions."""

    device_class = BinarySensorDeviceClass.POWER
    icon = "mdi:transmission-tower"

    @property
    def available(self) -> bool:
        """Return the available."""
        return (
            super().available and self._platform.inverter_data.I_Grid_Status is not None
        )

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_grid_status_on_off"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Grid Status"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return self._platform.inverter_data.I_Grid_Status is not None

    @property
    def is_on(self) -> bool:
        """Return True if on."""
        return self._platform.inverter_data.I_Grid_Status == 0x0
