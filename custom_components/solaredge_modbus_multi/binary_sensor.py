"""Component to interface with binary sensors."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SolarEdgeConfigEntry
from .entity import SolarEdgeEntityBase

_LOGGER = logging.getLogger(__name__)

# Coordinator-driven, read-only: HA need not throttle entity updates.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: SolarEdgeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    hub = config_entry.runtime_data.hub
    coordinator = config_entry.runtime_data.coordinator

    entities = []

    for inverter in hub.inverters:
        if inverter.apc_may_be_supported:
            entities.append(AdvPowerControlEnabled(inverter, config_entry, coordinator))

        entities.append(GridStatusOnOff(inverter, config_entry, coordinator))

    if entities:
        async_add_entities(entities)


class SolarEdgeBinarySensorBase(SolarEdgeEntityBase, BinarySensorEntity):
    """Base class for SolarEdge binary sensor entities."""

    uid_suffix: str | None = None

    def __init__(self, platform, config_entry, coordinator) -> None:
        super().__init__(platform, config_entry, coordinator)
        if self.uid_suffix is not None:
            self._attr_unique_id = f"{platform.uid_base}_{self.uid_suffix}"


class AdvPowerControlEnabled(SolarEdgeBinarySensorBase):
    """Grid Control boolean status. This is "AdvancedPwrControlEn" in specs."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Advanced Power Control"
    uid_suffix = "adv_pwr_ctrl_en"

    @property
    def available(self) -> bool:
        return (
            super().available
            and self._platform.advanced_power_control is True
            and "AdvPwrCtrlEn" in self._platform.decoded_model.keys()
        )

    @property
    def is_on(self) -> bool:
        return self._platform.decoded_model["AdvPwrCtrlEn"] == 0x1


class GridStatusOnOff(SolarEdgeBinarySensorBase):
    """Grid Status On Off. This is undocumented from discussions."""

    _attr_device_class = BinarySensorDeviceClass.POWER
    _attr_icon = "mdi:transmission-tower"
    _attr_name = "Grid Status"
    uid_suffix = "grid_status_on_off"

    @property
    def available(self) -> bool:
        return (
            super().available and "I_Grid_Status" in self._platform.decoded_model.keys()
        )

    @property
    def entity_registry_enabled_default(self) -> bool:
        return "I_Grid_Status" in self._platform.decoded_model.keys()

    @property
    def is_on(self) -> bool:
        return not self._platform.decoded_model["I_Grid_Status"]
