import logging
import re

from typing import Optional, Dict, Any
from datetime import datetime

from homeassistant.core import HomeAssistant

from homeassistant.core import callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import EntityCategory
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
    DEVICE_STATUS_DESC, SUNSPEC_DID, METER_EVENTS,
    POWER_VOLT_AMPERE_REACTIVE,
    ENERGY_VOLT_AMPERE_HOUR, ENERGY_VOLT_AMPERE_REACTIVE_HOUR,
)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:

    hub = hass.data[DOMAIN][config_entry.entry_id]

    entities = []
        
    for inverter in hub.inverters:
        entities.append(SerialNumber(inverter, config_entry))
        entities.append(DeviceID(inverter, config_entry))
        
    #for inverter_index in range(hub.se_inverters):
        #"C_Model": ["Model", "model", None, None, EntityCategory.DIAGNOSTIC],
        #"C_Sunspec_DID": ["Sunspec Device ID", "sunspecdid", None, None, EntityCategory.DIAGNOSTIC],
        #"AC_Current": ["AC Current", "accurrent", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac", None],
        #"AC_CurrentA": ["AC Current A", "accurrenta", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac", None],
        #"AC_CurrentB": ["AC Current B", "accurrentb", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac", None],
        #"AC_CurrentC": ["AC Current C", "accurrentc", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac", None],
        #"AC_VoltageAB": ["AC Voltage AB", "acvoltageab", ELECTRIC_POTENTIAL_VOLT, None, None],
        #"AC_VoltageBC": ["AC Voltage BC", "acvoltagebc", ELECTRIC_POTENTIAL_VOLT, None, None],
        #"AC_VoltageCA": ["AC Voltage CA", "acvoltageca", ELECTRIC_POTENTIAL_VOLT, None, None],
        #"AC_VoltageAN": ["AC Voltage AN", "acvoltagean", ELECTRIC_POTENTIAL_VOLT, None, None],
        #"AC_VoltageBN": ["AC Voltage BN", "acvoltagebn", ELECTRIC_POTENTIAL_VOLT, None, None],
        #"AC_VoltageCN": ["AC Voltage CN", "acvoltagecn", ELECTRIC_POTENTIAL_VOLT, None, None],
        #"AC_Power": ["AC Power", "acpower", POWER_WATT, "mdi:solar-power", None],
        #"AC_Frequency": ["AC Frequency", "acfreq", FREQUENCY_HERTZ, None, None],
        #"AC_VA": ["AC VA", "acva", POWER_VOLT_AMPERE, None, None],
        #"AC_VAR": ["AC var", "acvar", POWER_VOLT_AMPERE_REACTIVE, None, None],
        #"AC_PF": ["AC PF", "acpf", PERCENTAGE, None, None],
        #"AC_Energy_kWh": ["AC Energy kWh", "acenergy", ENERGY_KILO_WATT_HOUR, "mdi:solar-power", None],
        #"DC_Current": ["DC Current", "dccurrent", ELECTRIC_CURRENT_AMPERE, "mdi:current-dc", None],
        #"DC_Voltage": ["DC Voltage", "dcvoltage", ELECTRIC_POTENTIAL_VOLT, None, None],
        #"DC_Power": ["DC Power", "dcpower", POWER_WATT, "mdi:solar-power", None],
        #"Temp_Sink": ["Temp Sink", "tempsink", TEMP_CELSIUS, None, EntityCategory.DIAGNOSTIC],
        #"Status": ["Status", "status", None, None, EntityCategory.DIAGNOSTIC],
        #"Status_Text": ["Status Text", "status_text", None, None, None],
        #"Status_Vendor": ["Status Vendor", "statusvendor", None, None, EntityCategory.DIAGNOSTIC],
        #"Status_Vendor_Text": ["Status Vendor Text", "statusvendor_text", None, None, None],

    for meter in hub.meters:
        entities.append(SerialNumber(meter, config_entry))
        entities.append(DeviceID(meter, config_entry))
        entities.append(ParentDeviceID(meter, config_entry))

    #for meter_index in range(hub.se_meters):
        #"C_Model": ["Model", "model", None, None, EntityCategory.DIAGNOSTIC],
        #"C_Option": ["Option", "option", None, None, EntityCategory.DIAGNOSTIC],
        #"C_Sunspec_DID": ["Sunspec Device ID", "sunspecdid", None, None, EntityCategory.DIAGNOSTIC],
        #"AC_Current": ["AC Current", "accurrent", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac", None],
        #"AC_Current_A": ["AC Current_A", "accurrenta", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac", None],
        #"AC_Current_B": ["AC Current_B", "accurrentb", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac", None],
        #"AC_Current_C": ["AC Current_C", "accurrentc", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac", None],
        #"AC_Voltage_LN": ["AC Voltage LN", "acvoltageln", ELECTRIC_POTENTIAL_VOLT, None, None],
        #"AC_Voltage_AN": ["AC Voltage AN", "acvoltagean", ELECTRIC_POTENTIAL_VOLT, None, None],
        #"AC_Voltage_BN": ["AC Voltage BN", "acvoltagebn", ELECTRIC_POTENTIAL_VOLT, None, None],
        #"AC_Voltage_CN": ["AC Voltage CN", "acvoltagecn", ELECTRIC_POTENTIAL_VOLT, None, None],
        #"AC_Voltage_LL": ["AC Voltage LL", "acvoltagell", ELECTRIC_POTENTIAL_VOLT, None, None],
        #"AC_Voltage_AB": ["AC Voltage AB", "acvoltageab", ELECTRIC_POTENTIAL_VOLT, None, None],
        #"AC_Voltage_BC": ["AC Voltage BC", "acvoltagebc", ELECTRIC_POTENTIAL_VOLT, None, None],
        #"AC_Voltage_CA": ["AC Voltage CA", "acvoltageca", ELECTRIC_POTENTIAL_VOLT, None, None],
        #"AC_Frequency": ["AC Frequency", "acfreq", FREQUENCY_HERTZ, None, None],
        #"AC_Power": ["AC Power", "acpower", POWER_WATT, None, None],
        #"AC_Power_A": ["AC Power A", "acpowera", POWER_WATT, None, None],
        #"AC_Power_B": ["AC Power B", "acpowerb", POWER_WATT, None, None],
        #"AC_Power_C": ["AC Power C", "acpowerc", POWER_WATT, None, None],
        #"AC_VA": ["AC VA", "acva", POWER_VOLT_AMPERE, None, None],
        #"AC_VA_A": ["AC VA A", "acvaa", POWER_VOLT_AMPERE, None, None],
        #"AC_VA_B": ["AC VA B", "acvab", POWER_VOLT_AMPERE, None, None],
        #"AC_VA_C": ["AC VA C", "acvac", POWER_VOLT_AMPERE, None, None],
        #"AC_VAR": ["AC var", "acvar", POWER_VOLT_AMPERE_REACTIVE, None, None],
        #"AC_VAR_A": ["AC var A", "acvara", POWER_VOLT_AMPERE_REACTIVE, None, None],
        #"AC_VAR_B": ["AC var B", "acvarb", POWER_VOLT_AMPERE_REACTIVE, None, None],
        #"AC_VAR_C": ["AC var C", "acvarc", POWER_VOLT_AMPERE_REACTIVE, None, None],
        #"AC_PF": ["AC PF", "acpf", PERCENTAGE, None, None],
        #"AC_PF_A": ["AC PF A", "acpfa", PERCENTAGE, None, None],
        #"AC_PF_B": ["AC PF B", "acpfb", PERCENTAGE, None, None],
        #"AC_PF_C": ["AC PF C", "acpfc", PERCENTAGE, None, None],
        #"EXPORTED_KWH": ["Exported kWh", "exported", ENERGY_KILO_WATT_HOUR, 'mdi:transmission-tower-import', None],
        #"EXPORTED_KWH_A": ["Exported A kWh", "exporteda", ENERGY_KILO_WATT_HOUR, 'mdi:transmission-tower-import', None],
        #"EXPORTED_KWH_B": ["Exported B kWh", "exportedb", ENERGY_KILO_WATT_HOUR, 'mdi:transmission-tower-import', None],
        #"EXPORTED_KWH_C": ["Exported C kWh", "exportedc", ENERGY_KILO_WATT_HOUR, 'mdi:transmission-tower-import', None],
        #"IMPORTED_KWH": ["Imported kWh", "imported", ENERGY_KILO_WATT_HOUR, 'mdi:transmission-tower-export', None],
        #"IMPORTED_KWH_A": ["Imported A kWh", "importeda", ENERGY_KILO_WATT_HOUR, 'mdi:transmission-tower-export', None],
        #"IMPORTED_KWH_B": ["Imported B kWh", "importedb", ENERGY_KILO_WATT_HOUR, 'mdi:transmission-tower-export', None],
        #"IMPORTED_KWH_C": ["Imported C kWh", "importedc", ENERGY_KILO_WATT_HOUR, 'mdi:transmission-tower-export', None],
        #"EXPORTED_VA": ["Exported VAh", "exportedva", ENERGY_VOLT_AMPERE_HOUR, None, None],
        #"EXPORTED_VA_A": ["Exported A VAh", "exportedvaa", ENERGY_VOLT_AMPERE_HOUR, None, None],
        #"EXPORTED_VA_B": ["Exported B VAh", "exportedvab", ENERGY_VOLT_AMPERE_HOUR, None, None],
        #"EXPORTED_VA_C": ["Exported C VAh", "exportedvac", ENERGY_VOLT_AMPERE_HOUR, None, None],
        #"IMPORTED_VA": ["Imported VAh", "importedva", ENERGY_VOLT_AMPERE_HOUR, None, None],
        #"IMPORTED_VA_A": ["Imported A VAh", "importedvaa", ENERGY_VOLT_AMPERE_HOUR, None, None],
        #"IMPORTED_VA_B": ["Imported B VAh", "importedvab", ENERGY_VOLT_AMPERE_HOUR, None, None],
        #"IMPORTED_VA_C": ["Imported C VAh", "importedvac", ENERGY_VOLT_AMPERE_HOUR, None, None],
        #"IMPORT_VARH_Q1": ["Import varh Q1", "importvarhq1", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
        #"IMPORT_VARH_Q1_A": ["Import varh Q1 A", "importvarhq1a", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
        #"IMPORT_VARH_Q1_B": ["Import varh Q1 B", "importvarhq1b", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
        #"IMPORT_VARH_Q1_C": ["Import varh Q1 C", "importvarhq1c", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
        #"IMPORT_VARH_Q2": ["Import varh Q2", "importvarhq2", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
        #"IMPORT_VARH_Q2_A": ["Import varh Q2 A", "importvarhq2a", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
        #"IMPORT_VARH_Q2_B": ["Import varh Q2 B", "importvarhq2b", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
        #"IMPORT_VARH_Q2_C": ["Import varh Q2 C", "importvarhq2c", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
        #"IMPORT_VARH_Q3": ["Import varh Q3", "importvarhq3", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
        #"IMPORT_VARH_Q3_A": ["Import varh Q3 A", "importvarhq3a", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
        #"IMPORT_VARH_Q3_B": ["Import varh Q3 B", "importvarhq3b", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
        #"IMPORT_VARH_Q3_C": ["Import varh Q3 C", "importvarhq3c", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
        #"IMPORT_VARH_Q4": ["Import varh Q4", "importvarhq4", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
        #"IMPORT_VARH_Q4_A": ["Import varh Q4 A", "importvarhq4a", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
        #"IMPORT_VARH_Q4_B": ["Import varh Q4 B", "importvarhq4b", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
        #"IMPORT_VARH_Q4_C": ["Import varh Q4 C", "importvarhq4c", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
        #"M_Events": ["Meter Events", "meterevents", None, None, EntityCategory.DIAGNOSTIC],

    for battery in hub.batteries:
        entities.append(SerialNumber(battery, config_entry))
        entities.append(DeviceID(battery, config_entry))
        entities.append(ParentDeviceID(battery, config_entry))

    if entities:
        async_add_entities(entities)


class SolarEdgeSensorBase(SensorEntity):

    should_poll = False

    def __init__(self, platform, config_entry):
        """Initialize the sensor."""
        self._platform = platform
        self._config_entry = config_entry

    @property
    def device_info(self):
        return self._platform.device_info

    @property
    def config_entry_id(self):
        return self._config_entry.entry_id

    @property
    def config_entry_name(self):
        return self._config_entry.data['name']

    #async def async_added_to_hass(self):
    #    self._platform.async_add_solaredge_sensor(self._platform._modbus_data_updated)

    #async def async_will_remove_from_hass(self) -> None:
    #    self._platform.async_remove_solaredge_sensor(self._platform._modbus_data_updated)


class SerialNumber(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC
    
    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""
        
    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_serial_number"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Serial Number"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self):
        return self._platform.serial

class DeviceID(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC
    
    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""
        
    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_device_id"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Device ID"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self):
        return self._platform.device_address

class ParentDeviceID(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC
    
    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""
        
    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_parent_device_id"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Parent Device ID"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self):
        return self._platform.inverter_unit_id

class VoltageSensor(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.VOLTAGE
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT

    def __init__(self, platform, name, key, config_entry):
        super().__init__(platform, name, key, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_voltage"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Voltage"

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

