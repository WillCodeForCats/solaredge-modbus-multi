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
    SUNSPEC_NOT_IMPL_UINT16, SUNSPEC_NOT_IMPL_INT16,
    SUNSPEC_NOT_ACCUM_ACC32, SUNSPEC_ACCUM_LIMIT,
    DEVICE_STATUS, DEVICE_STATUS_DESC,
    VENDOR_STATUS, SUNSPEC_DID, METER_EVENTS,
    POWER_VOLT_AMPERE_REACTIVE,
    ENERGY_VOLT_AMPERE_HOUR, ENERGY_VOLT_AMPERE_REACTIVE_HOUR,
)

from .helpers import (
    update_accum,
    scale_factor,
    watts_to_kilowatts
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:

    hub = hass.data[DOMAIN][config_entry.entry_id]

    entities = []
        
    for inverter in hub.inverters:
        entities.append(Manufacturer(inverter, config_entry))
        entities.append(Model(inverter, config_entry))
        entities.append(Option(inverter, config_entry))
        entities.append(Version(inverter, config_entry))
        entities.append(SerialNumber(inverter, config_entry))
        entities.append(DeviceAddress(inverter, config_entry))
        entities.append(SunspecDID(inverter, config_entry))
        entities.append(ACCurrentSensor(inverter, config_entry))
        entities.append(ACCurrentSensorA(inverter, config_entry))
        entities.append(ACCurrentSensorB(inverter, config_entry))
        entities.append(ACCurrentSensorC(inverter, config_entry))
        entities.append(VoltageSensorAB(inverter, config_entry))
        entities.append(VoltageSensorBC(inverter, config_entry))
        entities.append(VoltageSensorCA(inverter, config_entry))
        entities.append(VoltageSensorAN(inverter, config_entry))
        entities.append(VoltageSensorBN(inverter, config_entry))
        entities.append(VoltageSensorCN(inverter, config_entry))
        entities.append(ACPower(inverter, config_entry))
        entities.append(ACFrequency(inverter, config_entry))
        entities.append(ACVoltAmp(inverter, config_entry))
        entities.append(ACVoltAmpReactive(inverter, config_entry))
        entities.append(ACPowerFactor(inverter, config_entry))
        entities.append(ACEnergy(inverter, config_entry))
        entities.append(DCCurrent(inverter, config_entry))
        entities.append(DCVoltage(inverter, config_entry))
        entities.append(DCPower(inverter, config_entry))
        entities.append(HeatSinkTemperature(inverter, config_entry))
        entities.append(Status(inverter,config_entry))
        entities.append(StatusText(inverter,config_entry))
        entities.append(StatusVendor(inverter, config_entry))

    for meter in hub.meters:
        entities.append(Manufacturer(meter, config_entry))
        entities.append(Model(meter, config_entry))
        entities.append(Option(meter, config_entry))
        entities.append(Version(meter, config_entry))
        entities.append(SerialNumber(meter, config_entry))
        entities.append(DeviceAddress(meter, config_entry))
        entities.append(DeviceAddressParent(meter, config_entry))

    #for meter_index in range(hub.se_meters):
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
        entities.append(Manufacturer(battery, config_entry))
        entities.append(Model(battery, config_entry))
        entities.append(Version(battery, config_entry))
        entities.append(SerialNumber(battery, config_entry))
        entities.append(DeviceAddress(battery, config_entry))
        entities.append(DeviceAddressParent(battery, config_entry))

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

    @property
    def available(self) -> bool:
        return self._platform.online

    async def async_added_to_hass(self):
        self._platform.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self):
        self._platform.remove_callback(self.async_write_ha_state)


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
    def native_value(self):
        return self._platform.serial

class Manufacturer(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC
    
    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""
        
    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_manufacturer"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Manufacturer"

    @property
    def native_value(self):
        return self._platform.manufacturer

class Model(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC
    
    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""
        
    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_model"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Model"

    @property
    def native_value(self):
        return self._platform.model

class Option(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC
    
    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""
        
    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_option"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Option"

    @property
    def available(self) -> bool:
        if len(self._platform.option) > 0:
            return self._platform.online
        else:
            return False
            
    @property
    def entity_registry_enabled_default(self) -> bool:
        if len(self._platform.option) == 0:
            return False
        else:
            return True

    @property
    def native_value(self):
        return self._platform.option

class Version(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC
    
    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""
        
    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_version"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Version"

    @property
    def native_value(self):
        return self._platform.fw_version

class DeviceAddress(SolarEdgeSensorBase):
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
    def native_value(self):
        return self._platform.device_address

class DeviceAddressParent(SolarEdgeSensorBase):
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
    def native_value(self):
        return self._platform.inverter_unit_id

class SunspecDID(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC
    
    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""
        
    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_sunspec_device_id"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Sunspec Device ID"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['C_SunSpec_DID'] == SUNSPEC_NOT_IMPL_UINT16):
                return None
            
            else:
                return self._platform.decoded_model['C_SunSpec_DID']
        
        except TypeError:
            return None
                
    @property
    def extra_state_attributes(self):
        try:
            if self._platform.decoded_model['C_SunSpec_DID'] in SUNSPEC_DID:
                return {"description": SUNSPEC_DID[self._platform.decoded_model['C_SunSpec_DID']]}
            
            else:
                return None
        
        except KeyError:
            return None

class ACCurrentSensor(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.CURRENT
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = ELECTRIC_CURRENT_AMPERE

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_ac_current"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} AC Current"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_AC_Current'] == SUNSPEC_NOT_IMPL_UINT16 or
                self._platform.decoded_model['I_AC_Current_SF'] == SUNSPEC_NOT_IMPL_INT16
            ):
                return None
            
            else:
                return scale_factor(self._platform.decoded_model['I_AC_Current'], self._platform.decoded_model['I_AC_Current_SF'])
        
        except TypeError:
            return None

class ACCurrentSensorA(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.CURRENT
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = ELECTRIC_CURRENT_AMPERE

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_ac_current_a"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} AC Current A"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_AC_CurrentA'] == SUNSPEC_NOT_IMPL_UINT16 or
                self._platform.decoded_model['I_AC_Current_SF'] == SUNSPEC_NOT_IMPL_INT16
            ):
                return None
            
            else:
                return scale_factor(self._platform.decoded_model['I_AC_CurrentA'], self._platform.decoded_model['I_AC_Current_SF'])
        
        except TypeError:
            return None

class ACCurrentSensorB(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.CURRENT
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = ELECTRIC_CURRENT_AMPERE

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_ac_current_b"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} AC Current B"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_AC_CurrentB'] == SUNSPEC_NOT_IMPL_UINT16 or
                self._platform.decoded_model['I_AC_Current_SF'] == SUNSPEC_NOT_IMPL_INT16
            ):
                return None
            
            else:
                return scale_factor(self._platform.decoded_model['I_AC_CurrentB'], self._platform.decoded_model['I_AC_Current_SF'])
        
        except TypeError:
            return None

class ACCurrentSensorC(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.CURRENT
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = ELECTRIC_CURRENT_AMPERE

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_ac_current_c"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} AC Current C"
    
    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_AC_CurrentC'] == SUNSPEC_NOT_IMPL_UINT16 or
                self._platform.decoded_model['I_AC_Current_SF'] == SUNSPEC_NOT_IMPL_INT16
            ):
                return None
            
            else:
                return scale_factor(self._platform.decoded_model['I_AC_CurrentC'], self._platform.decoded_model['I_AC_Current_SF'])
        
        except TypeError:
            return None

class VoltageSensorAB(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.VOLTAGE
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_ac_voltage_ab"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} AC Voltage AB"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_AC_VoltageAB'] == SUNSPEC_NOT_IMPL_UINT16 or
                self._platform.decoded_model['I_AC_Voltage_SF'] == SUNSPEC_NOT_IMPL_INT16
            ):
                return None
            
            else:
                value = scale_factor(self._platform.decoded_model['I_AC_VoltageAB'], self._platform.decoded_model['I_AC_Voltage_SF'])
                return round(value, abs(self._platform.decoded_model['I_AC_Voltage_SF']))
        
        except TypeError:
            return None

class VoltageSensorBC(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.VOLTAGE
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_ac_voltage_bc"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} AC Voltage BC"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_AC_VoltageBC'] == SUNSPEC_NOT_IMPL_UINT16 or
                self._platform.decoded_model['I_AC_Voltage_SF'] == SUNSPEC_NOT_IMPL_INT16
            ):
                return False
            
            else:
                value = scale_factor(self._platform.decoded_model['I_AC_VoltageBC'], self._platform.decoded_model['I_AC_Voltage_SF'])
                return round(value, abs(self._platform.decoded_model['I_AC_Voltage_SF']))
        
        except TypeError:
            return False

class VoltageSensorCA(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.VOLTAGE
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_ac_voltage_ca"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} AC Voltage CA"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_AC_VoltageCA'] == SUNSPEC_NOT_IMPL_UINT16 or
                self._platform.decoded_model['I_AC_Voltage_SF'] == SUNSPEC_NOT_IMPL_INT16
            ):
                return None
            
            else:
                value = scale_factor(self._platform.decoded_model['I_AC_VoltageCA'], self._platform.decoded_model['I_AC_Voltage_SF'])
                return round(value, abs(self._platform.decoded_model['I_AC_Voltage_SF']))
        
        except TypeError:
            return None

class VoltageSensorAN(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.VOLTAGE
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_ac_voltage_an"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} AC Voltage AN"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_AC_VoltageAN'] == SUNSPEC_NOT_IMPL_UINT16 or
                self._platform.decoded_model['I_AC_Voltage_SF'] == SUNSPEC_NOT_IMPL_INT16
            ):
                return None
            
            else:
                value = scale_factor(self._platform.decoded_model['I_AC_VoltageAN'], self._platform.decoded_model['I_AC_Voltage_SF'])
                return round(value, abs(self._platform.decoded_model['I_AC_Voltage_SF']))
        
        except TypeError:
            return None

class VoltageSensorBN(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.VOLTAGE
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_ac_voltage_bn"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} AC Voltage BN"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_AC_VoltageBN'] == SUNSPEC_NOT_IMPL_UINT16 or
                self._platform.decoded_model['I_AC_Voltage_SF'] == SUNSPEC_NOT_IMPL_INT16
            ):
                return None
            
            else:
                value = scale_factor(self._platform.decoded_model['I_AC_VoltageBN'], self._platform.decoded_model['I_AC_Voltage_SF'])
                return round(value, abs(self._platform.decoded_model['I_AC_Voltage_SF']))
        
        except TypeError:
            return None
        
class VoltageSensorCN(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.VOLTAGE
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_ac_voltage_cn"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} AC Voltage CN"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_AC_VoltageCN'] == SUNSPEC_NOT_IMPL_UINT16 or
                self._platform.decoded_model['I_AC_Voltage_SF'] == SUNSPEC_NOT_IMPL_INT16
            ):
                return None
            
            else:
                value = scale_factor(self._platform.decoded_model['I_AC_VoltageCN'], self._platform.decoded_model['I_AC_Voltage_SF'])
                return round(value, abs(self._platform.decoded_model['I_AC_Voltage_SF']))
        
        except TypeError:
            return None

class ACPower(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.POWER
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = POWER_WATT
    icon = 'mdi:solar-power'

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_ac_power"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} AC Power"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_AC_Power'] == SUNSPEC_NOT_IMPL_INT16 or
                self._platform.decoded_model['I_AC_Power_SF'] == SUNSPEC_NOT_IMPL_INT16
            ):
                return None
    
            else:
                value = scale_factor(self._platform.decoded_model['I_AC_Power'], self._platform.decoded_model['I_AC_Power_SF'])
                return round(value, abs(self._platform.decoded_model['I_AC_Power_SF']))
                
        except TypeError:
            return None

class ACFrequency(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.FREQUENCY
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = FREQUENCY_HERTZ

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_ac_frequency"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} AC Frequency"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_AC_Frequency'] == SUNSPEC_NOT_IMPL_UINT16 or
                self._platform.decoded_model['I_AC_Frequency_SF'] == SUNSPEC_NOT_IMPL_INT16
            ):
                return None
    
            else:
                value = scale_factor(self._platform.decoded_model['I_AC_Frequency'], self._platform.decoded_model['I_AC_Frequency_SF'])
                return round(value, abs(self._platform.decoded_model['I_AC_Frequency_SF']))
                
        except TypeError:
            return None

class ACVoltAmp(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.APPARENT_POWER
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = POWER_VOLT_AMPERE

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_ac_va"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} AC VA"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_AC_VA'] == SUNSPEC_NOT_IMPL_INT16 or
                self._platform.decoded_model['I_AC_VA_SF'] == SUNSPEC_NOT_IMPL_INT16
            ):
                return None
    
            else:
                value = scale_factor(self._platform.decoded_model['I_AC_VA'], self._platform.decoded_model['I_AC_VA_SF'])
                return round(value, abs(self._platform.decoded_model['I_AC_VA_SF']))
                
        except TypeError:
            return None

class ACVoltAmpReactive(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.APPARENT_POWER
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = POWER_VOLT_AMPERE_REACTIVE

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_ac_var"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} AC var"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_AC_VAR'] == SUNSPEC_NOT_IMPL_INT16 or
                self._platform.decoded_model['I_AC_VAR_SF'] == SUNSPEC_NOT_IMPL_INT16
            ):
                return None
    
            else:
                value = scale_factor(self._platform.decoded_model['I_AC_VAR'], self._platform.decoded_model['I_AC_VAR_SF'])
                return round(value, abs(self._platform.decoded_model['I_AC_VAR_SF']))
                
        except TypeError:
            return None

class ACPowerFactor(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.POWER_FACTOR
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = PERCENTAGE

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_ac_pf"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} AC PF"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_AC_PF'] == SUNSPEC_NOT_IMPL_INT16 or
                self._platform.decoded_model['I_AC_PF_SF'] == SUNSPEC_NOT_IMPL_INT16
            ):
                return None
    
            else:
                value = scale_factor(self._platform.decoded_model['I_AC_PF'], self._platform.decoded_model['I_AC_PF_SF'])
                return round(value, abs(self._platform.decoded_model['I_AC_PF_SF']))
                
        except TypeError:
            return None

class ACEnergy(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.ENERGY
    state_class = STATE_CLASS_TOTAL_INCREASING
    native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""
        
        self.last = None

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_ac_energy_kwh"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} AC Energy kWh"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_AC_Energy_WH'] == SUNSPEC_NOT_ACCUM_ACC32 or
                self._platform.decoded_model['I_AC_Energy_WH'] > SUNSPEC_ACCUM_LIMIT or
                self._platform.decoded_model['I_AC_Energy_WH_SF'] == SUNSPEC_NOT_IMPL_UINT16
            ):
                return None
    
            else:
                value = scale_factor(self._platform.decoded_model['I_AC_Energy_WH'], self._platform.decoded_model['I_AC_Energy_WH_SF'])
                value_kw = watts_to_kilowatts(value)
                
                try:
                    return update_accum(self, value, value_kw)
                except:
                    return None
                
        except TypeError:
            return None

class DCCurrent(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.CURRENT
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = ELECTRIC_CURRENT_AMPERE
    icon = 'mdi:current-dc'

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_dc_current"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} DC Current"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_DC_Current'] == SUNSPEC_NOT_IMPL_UINT16 or
                self._platform.decoded_model['I_DC_Current_SF'] == SUNSPEC_NOT_IMPL_INT16
            ):
                return None
    
            else:
                value = scale_factor(self._platform.decoded_model['I_DC_Current'], self._platform.decoded_model['I_DC_Current_SF'])
                return round(value, abs(self._platform.decoded_model['I_DC_Current_SF']))
        
        except TypeError:
            return None  

class DCVoltage(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.VOLTAGE
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_dc_voltage"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} DC Voltage"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_DC_Voltage'] == SUNSPEC_NOT_IMPL_UINT16 or
                self._platform.decoded_model['I_DC_Voltage_SF'] == SUNSPEC_NOT_IMPL_INT16
            ):
                return None
    
            else:
                value = scale_factor(self._platform.decoded_model['I_DC_Voltage'], self._platform.decoded_model['I_DC_Voltage_SF'])
                return round(value, abs(self._platform.decoded_model['I_DC_Voltage_SF']))
        
        except TypeError:
            return None  

class DCPower(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.POWER
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = POWER_WATT
    icon = 'mdi:solar-power'

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_dc_power"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} DC Power"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_DC_Power'] == SUNSPEC_NOT_IMPL_INT16 or
                self._platform.decoded_model['I_DC_Power_SF'] == SUNSPEC_NOT_IMPL_INT16
            ):
                return None
    
            else:
                value = scale_factor(self._platform.decoded_model['I_DC_Power'], self._platform.decoded_model['I_DC_Power_SF'])
                return round(value, abs(self._platform.decoded_model['I_DC_Power_SF']))
        
        except TypeError:
            return None  

class HeatSinkTemperature(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.TEMPERATURE
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = TEMP_CELSIUS

    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_temp_sink"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Temp Sink"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_Temp_Sink'] == SUNSPEC_NOT_IMPL_INT16 or
                self._platform.decoded_model['I_Temp_SF'] == SUNSPEC_NOT_IMPL_INT16
            ):
                return None
    
            else:
                value = scale_factor(self._platform.decoded_model['I_Temp_Sink'], self._platform.decoded_model['I_Temp_SF'])
                return round(value, abs(self._platform.decoded_model['I_Temp_SF']))
        
        except TypeError:
            return None  

class Status(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC
    
    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""
        
    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_status"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Status"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_Status'] == SUNSPEC_NOT_IMPL_INT16):
                return None
            
            else:
                return self._platform.decoded_model['I_Status']
        
        except TypeError:
            return None
                
    @property
    def extra_state_attributes(self):
        try:
            if self._platform.decoded_model['I_Status'] in DEVICE_STATUS_DESC:
                return {"description": DEVICE_STATUS_DESC[self._platform.decoded_model['I_Status']]}
            
            else:
                return None
        
        except KeyError:
            return None

class StatusText(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC
    
    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""
        
    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_status_text"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Status Text"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_Status'] == SUNSPEC_NOT_IMPL_INT16):
                return None
            
            else:
                return DEVICE_STATUS[self._platform.decoded_model['I_Status']]
        
        except TypeError:
            return None
        
        except KeyError:
            return None

class StatusVendor(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC
    
    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""
        
    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_status_vendor"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Status Vendor"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_Status_Vendor'] == SUNSPEC_NOT_IMPL_INT16):
                return None
            
            else:
                return self._platform.decoded_model['I_Status_Vendor']
        
        except TypeError:
            return None
                
    @property
    def extra_state_attributes(self):
        try:
            if self._platform.decoded_model['I_Status_Vendor'] in VENDOR_STATUS:
                return {"description": VENDOR_STATUS[self._platform.decoded_model['I_Status_Vendor']]}
            
            else:
                return None
        
        except KeyError:
            return None

class StatusVendorText(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC
    
    def __init__(self, platform, config_entry):
        super().__init__(platform, config_entry)
        """Initialize the sensor."""
        
    @property
    def unique_id(self) -> str:
        return f"{self._platform.model}_{self._platform.serial}_status_vendor"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Status Vendor"

    @property
    def native_value(self):
        try:
            if (self._platform.decoded_model['I_Status_Vendor'] == SUNSPEC_NOT_IMPL_INT16):
                return None
            
            else:
                return self._platform.decoded_model['I_Status_Vendor']
        
        except TypeError:
            return None
                
    @property
    def extra_state_attributes(self):
        try:
            if self._platform.decoded_model['I_Status_Vendor'] in VENDOR_STATUS:
                return {"description": VENDOR_STATUS[self._platform.decoded_model['I_Status_Vendor']]}
            
            else:
                return None
        
        except KeyError:
            return None

