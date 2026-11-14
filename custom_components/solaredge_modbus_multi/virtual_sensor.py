"""The SolarEdge Modbus Multi virtual system sensor module.

Sensors here show values calculated by SolarEdgeSystem from the other devices
on the hub. They never alter or replace the Modbus sensors those values come from.
"""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfPower

from .coordinator import SolarEdgeConfigEntry, SolarEdgeCoordinator
from .entity import SolarEdgeEntity

# sensor key -> name used after "Power - "
SENSOR_NAMES = {
    "solar_generation": "Solar Generation",
    "consumption": "Consumption",
    "grid_load": "Grid - Load",
    "pv_grid": "PV - Grid",
    "pv_load": "PV - Load",
}


def async_virtual_system_entities(
    hub, config_entry: SolarEdgeConfigEntry, coordinator: SolarEdgeCoordinator
) -> list[SensorEntity]:
    """Return the virtual system entities for a hub.

    Systems with batteries are not supported yet, so they get none.
    """
    if not hub.inverters or hub.system.has_storage:
        return []

    entities: list[SensorEntity] = [SolarACPower(hub.system, config_entry, coordinator)]
    entities.extend(
        SystemPower(hub.system, config_entry, coordinator, key)
        for key in hub.system.power_keys
    )
    return entities


class SolarEdgeSystemSensorBase(SolarEdgeEntity, SensorEntity):
    """Representation of a solar edge virtual system sensor base."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 0

    @property
    def _value(self) -> float | None:
        raise NotImplementedError

    @property
    def available(self) -> bool:
        """Return the available."""
        return super().available and self._value is not None

    @property
    def native_value(self) -> float | None:
        """Return the native value."""
        return self._value


class SolarACPower(SolarEdgeSystemSensorBase):
    """Total solar AC power, see SolarEdgeSystem.solar_ac_power."""

    _attr_icon = "mdi:solar-power"
    _attr_name = "Solar AC Power"

    def __init__(self, system, config_entry, coordinator):
        """Initialize the solar AC power."""
        super().__init__(system, config_entry, coordinator)
        self._attr_unique_id = f"{system.uid_base}_solar_ac_power"

    @property
    def _value(self) -> float | None:
        return self._platform.solar_ac_power

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        return {"source": self._platform.solar_ac_source}


class SystemPower(SolarEdgeSystemSensorBase):
    """A calculated system power flow, in the style of the wiki template sensors."""

    def __init__(self, system, config_entry, coordinator, key: str):
        """Initialize the system power."""
        super().__init__(system, config_entry, coordinator)
        self._key = key
        self._attr_unique_id = f"{system.uid_base}_power_{key}"
        self._attr_name = f"Power - {SENSOR_NAMES[key]}"

    @property
    def _value(self) -> float | None:
        return self._platform.power_values.get(self._key)
