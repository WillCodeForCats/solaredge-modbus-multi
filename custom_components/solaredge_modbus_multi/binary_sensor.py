"""Component to interface with binary sensors."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_EVENTS,
    ATTR_EVENTS_TEXT,
    BATTERY_STATUS,
    CAUSE_GROUP_INVERTER_FAULT,
    DEVICE_STATUS,
    EVENT_PROBLEM,
    METER_PROBLEM_EVENTS,
    SunSpecNotImpl,
)
from .coordinator import SolarEdgeConfigEntry
from .entity import SolarEdgeCauseEntity, SolarEdgeEntity
from .helpers import inverter_vendor_status, meter_event_names, meter_event_texts

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


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

    for meter in hub.meters:
        entities.append(MeterProblem(meter, config_entry, coordinator))  # noqa: PERF401

    for battery in hub.batteries:
        entities.append(BatteryProblem(battery, config_entry, coordinator))
        entities.append(BatteryCharging(battery, config_entry, coordinator))

    if entities:
        async_add_entities(entities)


class SolarEdgeBinarySensorBase(SolarEdgeEntity, BinarySensorEntity):
    """Base class for SolarEdge binary sensor entities."""


class SolarEdgeProblemBinarySensor(SolarEdgeCauseEntity, SolarEdgeBinarySensorBase):
    """Base for problem sensors that record a cause in the logbook.

    An EVENT_PROBLEM event is recorded when the problem turns on.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_name = "Problem"
    _cause_event = EVENT_PROBLEM

    def _problem_cause(self) -> dict[str, Any]:
        """Return event data describing the current cause."""
        return {}

    def _cause_value(self) -> bool:
        """Return the problem state."""
        return self.is_on

    def _cause_data(self, value: bool, last_value: bool | None) -> dict | None:
        """Return the cause when the problem turns on.

        Turning off is not recorded; the state going off is the indication.
        """
        return self._problem_cause() if value else None


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


class InverterProblem(SolarEdgeProblemBinarySensor):
    """On when the inverter status reports a fault.

    Shares its cause event with the inverter Status sensor.
    """

    _cause_group = CAUSE_GROUP_INVERTER_FAULT

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
        return inverter_vendor_status(
            self._platform.inverter_data, self._platform.use_status_vendor4
        )

    def _problem_cause(self) -> dict[str, Any]:
        """Return the vendor status as the cause."""
        return self.extra_state_attributes


class MeterProblem(SolarEdgeProblemBinarySensor):
    """On when the meter reports a power quality or sensor event."""

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the entity."""
        super().__init__(platform, config_entry, coordinator)
        self._attr_unique_id = f"{platform.uid_base}_problem"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.meter_data.M_Events
        return (
            super().available and value is not None and value != SunSpecNotImpl.UINT32
        )

    @property
    def is_on(self) -> bool:
        """Return True if any defined meter event bit is set."""
        return bool(self._platform.meter_data.M_Events & METER_PROBLEM_EVENTS)

    def _problem_cause(self) -> dict[str, Any]:
        """Return the active problem events as the cause."""
        value = self._platform.meter_data.M_Events & METER_PROBLEM_EVENTS
        return {
            ATTR_EVENTS: meter_event_names(value),
            ATTR_EVENTS_TEXT: meter_event_texts(value),
        }


class SolarEdgeBatteryStatusBinarySensor(SolarEdgeBinarySensorBase):
    """Base for battery binary sensors derived from the battery status."""

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.battery_data.B_Status
        return (
            super().available
            and value is not None
            and value != SunSpecNotImpl.UINT32
            and value in BATTERY_STATUS
        )

    @property
    def battery_status(self) -> str:
        """Return the battery status name."""
        return BATTERY_STATUS[self._platform.battery_data.B_Status]


class BatteryProblem(SolarEdgeBatteryStatusBinarySensor):
    """On when the battery status reports a fault."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_name = "Problem"

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the entity."""
        super().__init__(platform, config_entry, coordinator)
        self._attr_unique_id = f"{platform.uid_base}_problem"

    @property
    def is_on(self) -> bool:
        """Return True if the battery status is fault."""
        return self.battery_status == "B_STATUS_FAULT"


class BatteryCharging(SolarEdgeBatteryStatusBinarySensor):
    """On when the battery status reports charging."""

    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
    _attr_name = "Charging"

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the entity."""
        super().__init__(platform, config_entry, coordinator)
        self._attr_unique_id = f"{platform.uid_base}_charging"

    @property
    def is_on(self) -> bool:
        """Return True if the battery status is charge."""
        return self.battery_status == "B_STATUS_CHARGE"
