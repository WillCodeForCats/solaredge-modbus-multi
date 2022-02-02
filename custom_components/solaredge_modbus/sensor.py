import logging
import re

from typing import Optional, Dict, Any
from datetime import datetime

from homeassistant.core import callback
from homeassistant.const import (
    CONF_NAME,
    ENERGY_KILO_WATT_HOUR,
    POWER_WATT, POWER_KILO_WATT, POWER_VOLT_AMPERE,
    ELECTRIC_CURRENT_AMPERE, ELECTRIC_POTENTIAL_VOLT,
    PERCENTAGE, TEMP_CELSIUS, FREQUENCY_HERTZ,
)
from homeassistant.components.sensor import (
    STATE_CLASS_TOTAL_INCREASING,
    STATE_CLASS_MEASUREMENT,
    SensorDeviceClass,
    SensorEntity,
)
from .const import (
    DOMAIN,
    SENSOR_TYPES, METER_SENSOR_TYPES,
    ATTR_DESCRIPTION, ATTR_MANUFACTURER,
    SE_DEVICE_STATUS, SUNSPEC_DID, SE_METER_EVENTS,
    POWER_VOLT_AMPERE_REACTIVE,
    ENERGY_VOLT_AMPERE_HOUR, ENERGY_VOLT_AMPERE_REACTIVE_HOUR,
)

async def async_setup_entry(hass, entry, async_add_entities):
    hub_name = entry.data[CONF_NAME]
    hub = hass.data[DOMAIN][hub_name]["hub"]

    device_info = {
        "identifiers": {(DOMAIN, hub_name)},
        "name": hub_name,
        "manufacturer": ATTR_MANUFACTURER,
    }

    entities = []

    for inverter_index in range(hub.number_of_inverters):
         inverter_variable_prefix = "i" + str(inverter_index + 1) + "_"
         inverter_title_prefix = "I" + str(inverter_index + 1) + " "
         for sensor_info in SENSOR_TYPES.values():
             sensor = SolarEdgeSensor(
                 hub_name,
                 hub,
                 device_info,
                 inverter_title_prefix + sensor_info[0],
                 inverter_variable_prefix + sensor_info[1],
                 sensor_info[2],
                 sensor_info[3],
                 sensor_info[4],
             )
             entities.append(sensor)

    if hub.read_meter1 == True:
        for meter_sensor_info in METER_SENSOR_TYPES.values():
            sensor = SolarEdgeSensor(
                hub_name,
                hub,
                device_info,
                "M1 " + meter_sensor_info[0],
                "m1_" + meter_sensor_info[1],
                meter_sensor_info[2],
                meter_sensor_info[3],
                meter_sensor_info[4],
            )
            entities.append(sensor)

    if hub.read_meter2 == True:
        for meter_sensor_info in METER_SENSOR_TYPES.values():
            sensor = SolarEdgeSensor(
                hub_name,
                hub,
                device_info,
                "M2 " + meter_sensor_info[0],
                "m2_" + meter_sensor_info[1],
                meter_sensor_info[2],
                meter_sensor_info[3],
                meter_sensor_info[4],
            )
            entities.append(sensor)

    if hub.read_meter3 == True:
        for meter_sensor_info in METER_SENSOR_TYPES.values():
            sensor = SolarEdgeSensor(
                hub_name,
                hub,
                device_info,
                "M3 " + meter_sensor_info[0],
                "m3_" + meter_sensor_info[1],
                meter_sensor_info[2],
                meter_sensor_info[3],
                meter_sensor_info[4],
            )
            entities.append(sensor)

    async_add_entities(entities)
    return True


class SolarEdgeSensor(SensorEntity):
    """Representation of an SolarEdge Modbus sensor."""

    def __init__(self, platform_name, hub, device_info, name, key, unit, icon, category):
        """Initialize the sensor."""
        self._platform_name = platform_name
        self._hub = hub
        self._key = key
        self._name = name
        self._unit_of_measurement = unit
        self._icon = icon
        self._device_info = device_info
        self._attr_entity_category = category

        if self._unit_of_measurement in [
            POWER_VOLT_AMPERE, POWER_VOLT_AMPERE_REACTIVE,
            ENERGY_VOLT_AMPERE_HOUR, ENERGY_VOLT_AMPERE_REACTIVE_HOUR,
        ]:
            self._attr_state_class = STATE_CLASS_MEASUREMENT
        
        elif self._unit_of_measurement in [
            POWER_WATT, POWER_KILO_WATT
        ]:
            self._attr_state_class = STATE_CLASS_MEASUREMENT
            self._attr_device_class = SensorDeviceClass.POWER
            
        elif self._unit_of_measurement == PERCENTAGE:
            self._attr_state_class = STATE_CLASS_MEASUREMENT
            self._attr_device_class = SensorDeviceClass.POWER_FACTOR

        elif self._unit_of_measurement == ELECTRIC_POTENTIAL_VOLT:
            self._attr_state_class = STATE_CLASS_MEASUREMENT
            self._attr_device_class = SensorDeviceClass.VOLTAGE

        elif self._unit_of_measurement == ELECTRIC_CURRENT_AMPERE:
            self._attr_state_class = STATE_CLASS_MEASUREMENT
            self._attr_device_class = SensorDeviceClass.CURRENT

        elif self._unit_of_measurement == TEMP_CELSIUS:
            self._attr_state_class = STATE_CLASS_MEASUREMENT
            self._attr_device_class = SensorDeviceClass.TEMPERATURE

        elif self._unit_of_measurement == FREQUENCY_HERTZ:
            self._attr_state_class = STATE_CLASS_MEASUREMENT
            self._attr_device_class = SensorDeviceClass.FREQUENCY
            
        elif self._unit_of_measurement == ENERGY_KILO_WATT_HOUR:
            self._attr_state_class = STATE_CLASS_TOTAL_INCREASING
            self._attr_device_class = SensorDeviceClass.ENERGY

    async def async_added_to_hass(self):
        """Register callbacks."""
        self._hub.async_add_solaredge_sensor(self._modbus_data_updated)

    async def async_will_remove_from_hass(self) -> None:
        self._hub.async_remove_solaredge_sensor(self._modbus_data_updated)

    @callback
    def _modbus_data_updated(self):
        self.async_write_ha_state()

    @callback
    def _update_state(self):
        if self._key in self._hub.data:
            self._state = self._hub.data[self._key]

    @property
    def name(self):
        """Return the name."""
        return f"{self._platform_name} ({self._name})"

    @property
    def unique_id(self) -> Optional[str]:
        return f"{self._platform_name}_{self._key}"

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit_of_measurement

    @property
    def icon(self):
        """Return the sensor icon."""
        return self._icon

    @property
    def state(self):
        """Return the state of the sensor."""
        if self._key in self._hub.data:
            return self._hub.data[self._key]

    @property
    def available(self) -> bool:
        if self._key in self._hub.data:
            if self._hub.data[self._key] is None:
                return False
            else:
                return True
    
    @property
    def entity_registry_enabled_default(self) -> bool:
        if self._unit_of_measurement in [
            POWER_VOLT_AMPERE, POWER_VOLT_AMPERE_REACTIVE,
            ENERGY_VOLT_AMPERE_HOUR, ENERGY_VOLT_AMPERE_REACTIVE_HOUR
        ]:
            return False
        else:
            return True

    @property
    def extra_state_attributes(self):
        if re.match('(i|m)[0-9]_sunspecdid', self._key):
            if self.state in SUNSPEC_DID:
                return {ATTR_DESCRIPTION: SUNSPEC_DID[self.state]}
        
        elif re.match('i[0-9]_status', self._key):
            if self.state in SE_DEVICE_STATUS:
                return {ATTR_DESCRIPTION: SE_DEVICE_STATUS[self.state]}
        
        elif re.match('m[1-3]_meterevents', self._key):
            if isinstance(self.state, str):
                m_events_active = []
                if int(self.state,16) == 0x0:
                    return {ATTR_DESCRIPTION: str(m_events_active)}
                else:
                    for i in range(0,32):
                        if (int(self.state,16) & (1 << i)):
                            m_events_active.append(SE_METER_EVENTS[i])
                    return {ATTR_DESCRIPTION: str(m_events_active)}
        
        else:
            return None

    @property
    def should_poll(self) -> bool:
        """Data is delivered by the hub"""
        return False

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        return self._device_info
