import logging
import re

from typing import Optional, Dict, Any
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:

    hub = hass.data[DOMAIN][entry.entry_id]
    config_name = entry.data[CONF_NAME]  

    entities = []
    
    #for inverter_index in range(hub.se_inverters):
    #    pass

    #for meter_index in range(hub.se_meters):
    #    pass


    async_add_entities(entities)



class SolarEdgeSensorBase(SensorEntity):

    should_poll = False

    def __init__(self, platform_name, hub, name, key):
        """Initialize the sensor."""
        self._platform_name = platform_name
        self._hub = hub
        self._key = key
        self._name = name

    @property
    def device_info(self):
        return self.device_info

    @property
    def config_entry_id(self):
        return self._config_entry.entry_id

    @property
    def config_entry_name(self):
        return self._config_entry.data['name']

    async def async_added_to_hass(self):
        self._hub.async_add_solaredge_sensor(self._hub._modbus_data_updated)

    async def async_will_remove_from_hass(self) -> None:
        self._hub.async_remove_solaredge_sensor(self._hub._modbus_data_updated)


class SolarEdgeVoltageSensor(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.VOLTAGE
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT
    #entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, platform_name, hub, name, key):
        super().__init__(platform_name, hub, name, key)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f""

    @property
    def name(self) -> str:
        return f""

    @property
    def available(self) -> bool:
        return False

    @property
    def native_value(self):
        return None


class SolarEdgeSensor(SensorEntity):
    """Representation of an SolarEdge Modbus sensor."""

    def __init__(self, platform_name, hub, name, key, unit, icon, category):
        """Initialize the sensor."""

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
        return f"{self._platform_name.capitalize()} ({self._name})"

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
        try:
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
                
        except KeyError:
            return None

    @property
    def should_poll(self) -> bool:
        """Data is delivered by the hub"""
        return False

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        return self._device_info

