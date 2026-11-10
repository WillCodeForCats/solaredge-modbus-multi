"""Component to interface with binary sensors."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_STATUS, VENDOR4_STATUS, VENDOR_STATUS, SunSpecNotImpl
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

    for inverter in hub.inverters:
        entities.append(InverterProblem(inverter, config_entry, coordinator))
        entities.append(GridStatusOnOff(inverter, config_entry, coordinator))
        if hub.option_detect_extras:
            entities.append(AdvPowerControlEnabled(inverter, config_entry, coordinator))

    if entities:
        async_add_entities(entities)


class SolarEdgeBinarySensorBase(SolarEdgeEntity, BinarySensorEntity):
    """Base class for SolarEdge binary sensor entities."""


class AdvPowerControlEnabled(SolarEdgeBinarySensorBase):
    """Grid Control boolean status. This is "AdvancedPwrControlEn" in specs."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Advanced Power Control"

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the entity."""
        super().__init__(platform, config_entry, coordinator)
        self._attr_unique_id = f"{platform.uid_base}_adv_pwr_ctrl_en"

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


class GridStatusOnOff(SolarEdgeBinarySensorBase):
    """Grid Status On Off. This is undocumented from discussions."""

    _attr_device_class = BinarySensorDeviceClass.POWER
    _attr_icon = "mdi:transmission-tower"
    _attr_name = "Grid Status"

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the entity."""
        super().__init__(platform, config_entry, coordinator)
        self._attr_unique_id = f"{platform.uid_base}_grid_status_on_off"

    @property
    def available(self) -> bool:
        """Return the available."""
        return (
            super().available
            and self._platform.inverter_data.I_Grid_Status is not None
            and self._platform.inverter_data.I_Grid_Status != SunSpecNotImpl.UINT32
        )

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return self._platform.inverter_data.I_Grid_Status is not None

    @property
    def is_on(self) -> bool:
        """Return True if on."""
        return self._platform.inverter_data.I_Grid_Status == 0x0


class InverterProblem(SolarEdgeBinarySensorBase):
    """On when the inverter status reports a fault."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_name = "Problem"

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the entity."""
        super().__init__(platform, config_entry, coordinator)
        self._attr_unique_id = f"{platform.uid_base}_problem"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.inverter_data.I_Status
        return (
            super().available
            and value is not None
            and value != SunSpecNotImpl.UINT16
            and value in DEVICE_STATUS
        )

    @property
    def is_on(self) -> bool:
        """Return True if the inverter status is fault."""
        return DEVICE_STATUS[self._platform.inverter_data.I_Status] == "I_STATUS_FAULT"

    @property
    def extra_state_attributes(self):
        """Return the vendor status value and text."""
        data = self._platform.inverter_data
        attrs = {}

        if self._platform.use_status_vendor4:
            value = data.I_Status_Vendor4
            if value is not None and value != SunSpecNotImpl.UINT32:
                controller = (value >> 24) & 0xFF
                error = value & 0xFFFF
                attrs["status_value"] = f"{controller:X}x{error:X}"
                if controller in VENDOR4_STATUS and error in VENDOR4_STATUS[controller]:
                    attrs["status_text"] = VENDOR4_STATUS[controller][error]
        else:
            value = data.I_Status_Vendor
            if value is not None and value != SunSpecNotImpl.UINT16:
                attrs["status_value"] = value
                if value in VENDOR_STATUS:
                    attrs["status_text"] = VENDOR_STATUS[value]

        return attrs
