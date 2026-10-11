"""The SolarEdge Modbus Multi virtual system sensor module.

Sensors here are calculated from the values of the other devices on the hub.
They never alter or replace the Modbus sensors those values come from.

The power sensors follow the template sensors for a system without batteries from
https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki/Template-Sensors-for-Power-and-Energy
with the inputs summed across all inverters.

Sign conventions of the inputs:
    inverter DC power: positive is flowing from the DC bus to the inverter
    inverter AC power: positive is flowing from the inverter to the site
    meter AC power: positive is exported to the grid
"""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfPower
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import SUNSPEC_SF_RANGE, MeterRole, SunSpecNotImpl

# sensor key -> name used after "Power - "
SENSOR_NAMES = {
    "solar_generation": "Solar Generation",
    "consumption": "Consumption",
    "grid_load": "Grid - Load",
    "pv_grid": "PV - Grid",
    "pv_load": "PV - Load",
}


def _scaled(value, sf) -> float | None:
    """Return a SunSpec value with its scale factor applied, or None if invalid."""
    if (
        value is None
        or value == SunSpecNotImpl.INT16
        or sf is None
        or sf == SunSpecNotImpl.INT16
        or sf not in SUNSPEC_SF_RANGE
    ):
        return None
    return value * (10**sf)


def _inverter_ac_power(inverter) -> float | None:
    """Return the inverter AC power, or None if invalid."""
    return _scaled(inverter.inverter_data.AC_Power, inverter.inverter_data.AC_Power_SF)


def _inverter_dc_power(inverter) -> float | None:
    """Return the inverter DC power, or None if invalid."""
    return _scaled(
        inverter.inverter_data.I_DC_Power, inverter.inverter_data.I_DC_Power_SF
    )


def _meter_ac_power(meter) -> float | None:
    """Return the meter AC power, or None if invalid."""
    return _scaled(meter.meter_data.AC_Power, meter.meter_data.AC_Power_SF)


def _sum_all(values) -> float | None:
    """Return the sum of values, or None if any value is None or there are none."""
    values = list(values)
    if not values or any(value is None for value in values):
        return None
    return sum(values)


def _calc(fn, *args) -> float | None:
    """Return fn(*args), or None if any argument is None."""
    if any(arg is None for arg in args):
        return None
    return fn(*args)


def _export_import_meters(hub) -> list:
    return [m for m in hub.meters if m.meter_role == MeterRole.EXPORT_IMPORT]


def calculate_power(hub) -> dict[str, float | None]:
    """Return the system power values in watts, None where an input is invalid.

    Only valid for a system without batteries.
    """
    solar = _sum_all(_inverter_dc_power(i) for i in hub.inverters)
    iac = _sum_all(_inverter_ac_power(i) for i in hub.inverters)
    m = _sum_all(_meter_ac_power(x) for x in _export_import_meters(hub))

    pv_grid = _calc(lambda m: max(m, 0), m)
    return {
        "solar_generation": solar,
        "consumption": _calc(lambda iac, m: iac - m, iac, m),
        "grid_load": _calc(lambda m: abs(min(m, 0)), m),
        "pv_grid": pv_grid,
        "pv_load": _calc(lambda s, g: max(s - g, 0), solar, pv_grid),
    }


def _power_keys(hub) -> list[str]:
    """Return the power sensor keys that apply to this hub."""
    if hub.batteries:
        return []

    keys = ["solar_generation"]
    if _export_import_meters(hub):
        keys += ["consumption", "grid_load", "pv_grid", "pv_load"]
    return keys


def async_virtual_system_entities(hub, config_entry, coordinator) -> list:
    """Return the virtual system entities for a hub."""
    if not hub.inverters:
        return []

    entities = [SolarACPower(hub.system, config_entry, coordinator)]
    entities.extend(
        SystemPower(hub.system, config_entry, coordinator, key)
        for key in _power_keys(hub)
    )
    return entities


class SolarEdgeSystemSensorBase(CoordinatorEntity, SensorEntity):
    """Representation of a solar edge virtual system sensor base."""

    should_poll = False
    _attr_has_entity_name = True
    suggested_display_precision = None

    def __init__(self, system, config_entry, coordinator):
        """Initialize the solar edge virtual system sensor base."""
        super().__init__(coordinator)

        self._system = system
        self._config_entry = config_entry

    @property
    def device_info(self):
        """Return the device info."""
        return self._system.device_info

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class SolarACPower(SolarEdgeSystemSensorBase):
    """Total solar AC power.

    Uses the Production meters if there are any, otherwise the inverters.
    An inverter charging batteries from the grid is not solar production, so
    each inverter is limited to zero or more.
    """

    device_class = SensorDeviceClass.POWER
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfPower.WATT
    suggested_display_precision = 0
    icon = "mdi:solar-power"

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._system.uid_base}_solar_ac_power"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Solar AC Power"

    @property
    def _production_meters(self) -> list:
        return [
            meter
            for meter in self._system.hub.meters
            if meter.meter_role == MeterRole.PRODUCTION
        ]

    @property
    def _value(self) -> float | None:
        if self._production_meters:
            return _sum_all(_meter_ac_power(m) for m in self._production_meters)
        return _sum_all(
            _calc(lambda v: max(v, 0), _inverter_ac_power(i))
            for i in self._system.hub.inverters
        )

    @property
    def available(self) -> bool:
        """Return the available."""
        return super().available and self._value is not None

    @property
    def native_value(self):
        """Return the native value."""
        return self._value

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        return {"source": "meter" if self._production_meters else "inverter"}


class SystemPower(SolarEdgeSystemSensorBase):
    """A calculated system power flow, in the style of the wiki template sensors."""

    device_class = SensorDeviceClass.POWER
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfPower.WATT
    suggested_display_precision = 0

    def __init__(self, system, config_entry, coordinator, key: str):
        """Initialize the system power."""
        super().__init__(system, config_entry, coordinator)

        self._key = key

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._system.uid_base}_power_{self._key}"

    @property
    def name(self) -> str:
        """Return the name."""
        return f"Power - {SENSOR_NAMES[self._key]}"

    @property
    def _value(self) -> float | None:
        return calculate_power(self._system.hub).get(self._key)

    @property
    def available(self) -> bool:
        """Return the available."""
        return super().available and self._value is not None

    @property
    def native_value(self):
        """Return the native value."""
        return self._value
