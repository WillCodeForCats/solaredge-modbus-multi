DOMAIN = "solaredge_modbus_multi"
DEFAULT_NAME = "solaredge"
DEFAULT_SCAN_INTERVAL = 60
DEFAULT_PORT = 1502
DEFAULT_NUMBER_INVERTERS = 1
DEFAULT_DEVICE_ID = 1
DEFAULT_READ_METER1 = False
DEFAULT_READ_METER2 = False
DEFAULT_READ_METER3 = False
ATTR_DESCRIPTION = "description"
ATTR_MANUFACTURER = "SolarEdge"
CONF_NUMBER_INVERTERS = "number_of_inverters"
CONF_DEVICE_ID = "device_id"
CONF_READ_METER1 = "read_meter_1"
CONF_READ_METER2 = "read_meter_2"
CONF_READ_METER3 = "read_meter_3"

from homeassistant.helpers.entity import EntityCategory

# units from homeassistant core
from homeassistant.const import (
    ENERGY_KILO_WATT_HOUR,
    POWER_WATT, POWER_KILO_WATT, POWER_VOLT_AMPERE,
    ELECTRIC_CURRENT_AMPERE, ELECTRIC_POTENTIAL_VOLT,
    PERCENTAGE, TEMP_CELSIUS, FREQUENCY_HERTZ,
)
# units missing in homeassistant core
POWER_VOLT_AMPERE_REACTIVE = "var"
ENERGY_VOLT_AMPERE_HOUR = "VAh"
ENERGY_VOLT_AMPERE_REACTIVE_HOUR = "varh"

SUNSPEC_NOT_IMPL_INT16 = 0x8000
SUNSPEC_NOT_IMPL_UINT16 = 0xFFFF
SUNSPEC_NOT_ACCUM_ACC16 = 0x0000
SUNSPEC_NOT_IMPL_INT32 = 0x80000000
SUNSPEC_NOT_IMPL_UINT32 = 0xFFFFFFFF
SUNSPEC_NOT_ACCUM_ACC32 = 0x00000000
SUNSPEC_ACCUM_LIMIT = 4294967295

SENSOR_TYPES = {
    "C_Manufacturer": ["Manufacturer", "manufacturer", None, None, EntityCategory.DIAGNOSTIC],
    "C_Model": ["Model", "model", None, None, EntityCategory.DIAGNOSTIC],
    "C_Option": ["Option", "option", None, None, EntityCategory.DIAGNOSTIC],
    "C_Version": ["Version", "version", None, None, EntityCategory.DIAGNOSTIC],
    "C_SerialNumber": ["Serial Number", "serialnumber", None, None, EntityCategory.DIAGNOSTIC],
    "C_DeviceAddress": ["Device Address", "deviceaddress", None, None, EntityCategory.DIAGNOSTIC],
    "C_Sunspec_DID": ["Sunspec Device ID", "sunspecdid", None, None, EntityCategory.DIAGNOSTIC],
    "AC_Current": ["AC Current", "accurrent", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac", None],
    "AC_CurrentA": ["AC Current A", "accurrenta", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac", None],
    "AC_CurrentB": ["AC Current B", "accurrentb", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac", None],
    "AC_CurrentC": ["AC Current C", "accurrentc", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac", None],
    "AC_VoltageAB": ["AC Voltage AB", "acvoltageab", ELECTRIC_POTENTIAL_VOLT, None, None],
    "AC_VoltageBC": ["AC Voltage BC", "acvoltagebc", ELECTRIC_POTENTIAL_VOLT, None, None],
    "AC_VoltageCA": ["AC Voltage CA", "acvoltageca", ELECTRIC_POTENTIAL_VOLT, None, None],
    "AC_VoltageAN": ["AC Voltage AN", "acvoltagean", ELECTRIC_POTENTIAL_VOLT, None, None],
    "AC_VoltageBN": ["AC Voltage BN", "acvoltagebn", ELECTRIC_POTENTIAL_VOLT, None, None],
    "AC_VoltageCN": ["AC Voltage CN", "acvoltagecn", ELECTRIC_POTENTIAL_VOLT, None, None],
    "AC_Power": ["AC Power", "acpower", POWER_WATT, "mdi:solar-power", None],
    "AC_Frequency": ["AC Frequency", "acfreq", FREQUENCY_HERTZ, None, None],
    "AC_VA": ["AC VA", "acva", POWER_VOLT_AMPERE, None, None],
    "AC_VAR": ["AC var", "acvar", POWER_VOLT_AMPERE_REACTIVE, None, None],
    "AC_PF": ["AC PF", "acpf", PERCENTAGE, None, None],
    "AC_Energy_kWh": ["AC Energy kWh", "acenergy", ENERGY_KILO_WATT_HOUR, "mdi:solar-power", None],
    "DC_Current": ["DC Current", "dccurrent", ELECTRIC_CURRENT_AMPERE, "mdi:current-dc", None],
    "DC_Voltage": ["DC Voltage", "dcvoltage", ELECTRIC_POTENTIAL_VOLT, None, None],
    "DC_Power": ["DC Power", "dcpower", POWER_WATT, "mdi:solar-power", None],
    "Temp_Sink": ["Temp Sink", "tempsink", TEMP_CELSIUS, None, EntityCategory.DIAGNOSTIC],
    "Status": ["Status", "status", None, None, EntityCategory.DIAGNOSTIC],
    "Status_Text": ["Status Text", "status_text", None, None, None],
    "Status_Vendor": ["Status Vendor", "statusvendor", None, None, EntityCategory.DIAGNOSTIC],
    "Status_Vendor_Text": ["Status Vendor Text", "statusvendor_text", None, None, None],
}

METER_SENSOR_TYPES = {
    "C_Manufacturer": ["Manufacturer", "manufacturer", None, None, EntityCategory.DIAGNOSTIC],
    "C_Model": ["Model", "model", None, None, EntityCategory.DIAGNOSTIC],
    "C_Option": ["Option", "option", None, None, EntityCategory.DIAGNOSTIC],
    "C_Version": ["Version", "version", None, None, EntityCategory.DIAGNOSTIC],
    "C_SerialNumber": ["Serial Number", "serialnumber", None, None, EntityCategory.DIAGNOSTIC],
    "C_DeviceAddress": ["Device Address", "deviceaddress", None, None, EntityCategory.DIAGNOSTIC],
    "C_Sunspec_DID": ["Sunspec Device ID", "sunspecdid", None, None, EntityCategory.DIAGNOSTIC],
    "AC_Current": ["AC Current", "accurrent", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac", None],
    "AC_Current_A": ["AC Current_A", "accurrenta", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac", None],
    "AC_Current_B": ["AC Current_B", "accurrentb", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac", None],
    "AC_Current_C": ["AC Current_C", "accurrentc", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac", None],
    "AC_Voltage_LN": ["AC Voltage LN", "acvoltageln", ELECTRIC_POTENTIAL_VOLT, None, None],
    "AC_Voltage_AN": ["AC Voltage AN", "acvoltagean", ELECTRIC_POTENTIAL_VOLT, None, None],
    "AC_Voltage_BN": ["AC Voltage BN", "acvoltagebn", ELECTRIC_POTENTIAL_VOLT, None, None],
    "AC_Voltage_CN": ["AC Voltage CN", "acvoltagecn", ELECTRIC_POTENTIAL_VOLT, None, None],
    "AC_Voltage_LL": ["AC Voltage LL", "acvoltagell", ELECTRIC_POTENTIAL_VOLT, None, None],
    "AC_Voltage_AB": ["AC Voltage AB", "acvoltageab", ELECTRIC_POTENTIAL_VOLT, None, None],
    "AC_Voltage_BC": ["AC Voltage BC", "acvoltagebc", ELECTRIC_POTENTIAL_VOLT, None, None],
    "AC_Voltage_CA": ["AC Voltage CA", "acvoltageca", ELECTRIC_POTENTIAL_VOLT, None, None],
    "AC_Frequency": ["AC Frequency", "acfreq", FREQUENCY_HERTZ, None, None],
    "AC_Power": ["AC Power", "acpower", POWER_WATT, None, None],
    "AC_Power_A": ["AC Power A", "acpowera", POWER_WATT, None, None],
    "AC_Power_B": ["AC Power B", "acpowerb", POWER_WATT, None, None],
    "AC_Power_C": ["AC Power C", "acpowerc", POWER_WATT, None, None],
    "AC_VA": ["AC VA", "acva", POWER_VOLT_AMPERE, None, None],
    "AC_VA_A": ["AC VA A", "acvaa", POWER_VOLT_AMPERE, None, None],
    "AC_VA_B": ["AC VA B", "acvab", POWER_VOLT_AMPERE, None, None],
    "AC_VA_C": ["AC VA C", "acvac", POWER_VOLT_AMPERE, None, None],
    "AC_VAR": ["AC var", "acvar", POWER_VOLT_AMPERE_REACTIVE, None, None],
    "AC_VAR_A": ["AC var A", "acvara", POWER_VOLT_AMPERE_REACTIVE, None, None],
    "AC_VAR_B": ["AC var B", "acvarb", POWER_VOLT_AMPERE_REACTIVE, None, None],
    "AC_VAR_C": ["AC var C", "acvarc", POWER_VOLT_AMPERE_REACTIVE, None, None],
    "AC_PF": ["AC PF", "acpf", PERCENTAGE, None, None],
    "AC_PF_A": ["AC PF A", "acpfa", PERCENTAGE, None, None],
    "AC_PF_B": ["AC PF B", "acpfb", PERCENTAGE, None, None],
    "AC_PF_C": ["AC PF C", "acpfc", PERCENTAGE, None, None],
    "EXPORTED_KWH": ["Exported kWh", "exported", ENERGY_KILO_WATT_HOUR, 'mdi:transmission-tower-import', None],
    "EXPORTED_KWH_A": ["Exported A kWh", "exporteda", ENERGY_KILO_WATT_HOUR, 'mdi:transmission-tower-import', None],
    "EXPORTED_KWH_B": ["Exported B kWh", "exportedb", ENERGY_KILO_WATT_HOUR, 'mdi:transmission-tower-import', None],
    "EXPORTED_KWH_C": ["Exported C kWh", "exportedc", ENERGY_KILO_WATT_HOUR, 'mdi:transmission-tower-import', None],
    "IMPORTED_KWH": ["Imported kWh", "imported", ENERGY_KILO_WATT_HOUR, 'mdi:transmission-tower-export', None],
    "IMPORTED_KWH_A": ["Imported A kWh", "importeda", ENERGY_KILO_WATT_HOUR, 'mdi:transmission-tower-export', None],
    "IMPORTED_KWH_B": ["Imported B kWh", "importedb", ENERGY_KILO_WATT_HOUR, 'mdi:transmission-tower-export', None],
    "IMPORTED_KWH_C": ["Imported C kWh", "importedc", ENERGY_KILO_WATT_HOUR, 'mdi:transmission-tower-export', None],
    "EXPORTED_VA": ["Exported VAh", "exportedva", ENERGY_VOLT_AMPERE_HOUR, None, None],
    "EXPORTED_VA_A": ["Exported A VAh", "exportedvaa", ENERGY_VOLT_AMPERE_HOUR, None, None],
    "EXPORTED_VA_B": ["Exported B VAh", "exportedvab", ENERGY_VOLT_AMPERE_HOUR, None, None],
    "EXPORTED_VA_C": ["Exported C VAh", "exportedvac", ENERGY_VOLT_AMPERE_HOUR, None, None],
    "IMPORTED_VA": ["Imported VAh", "importedva", ENERGY_VOLT_AMPERE_HOUR, None, None],
    "IMPORTED_VA_A": ["Imported A VAh", "importedvaa", ENERGY_VOLT_AMPERE_HOUR, None, None],
    "IMPORTED_VA_B": ["Imported B VAh", "importedvab", ENERGY_VOLT_AMPERE_HOUR, None, None],
    "IMPORTED_VA_C": ["Imported C VAh", "importedvac", ENERGY_VOLT_AMPERE_HOUR, None, None],
    "IMPORT_VARH_Q1": ["Import varh Q1", "importvarhq1", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
    "IMPORT_VARH_Q1_A": ["Import varh Q1 A", "importvarhq1a", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
    "IMPORT_VARH_Q1_B": ["Import varh Q1 B", "importvarhq1b", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
    "IMPORT_VARH_Q1_C": ["Import varh Q1 C", "importvarhq1c", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
    "IMPORT_VARH_Q2": ["Import varh Q2", "importvarhq2", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
    "IMPORT_VARH_Q2_A": ["Import varh Q2 A", "importvarhq2a", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
    "IMPORT_VARH_Q2_B": ["Import varh Q2 B", "importvarhq2b", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
    "IMPORT_VARH_Q2_C": ["Import varh Q2 C", "importvarhq2c", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
    "IMPORT_VARH_Q3": ["Import varh Q3", "importvarhq3", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
    "IMPORT_VARH_Q3_A": ["Import varh Q3 A", "importvarhq3a", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
    "IMPORT_VARH_Q3_B": ["Import varh Q3 B", "importvarhq3b", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
    "IMPORT_VARH_Q3_C": ["Import varh Q3 C", "importvarhq3c", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
    "IMPORT_VARH_Q4": ["Import varh Q4", "importvarhq4", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
    "IMPORT_VARH_Q4_A": ["Import varh Q4 A", "importvarhq4a", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
    "IMPORT_VARH_Q4_B": ["Import varh Q4 B", "importvarhq4b", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
    "IMPORT_VARH_Q4_C": ["Import varh Q4 C", "importvarhq4c", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None, None],
    "M_Events": ["Meter Events", "meterevents", None, None, EntityCategory.DIAGNOSTIC],
}

SUNSPEC_DID = {
    101: "Single Phase Inverter",
    102: "Split Phase Inverter",
    103: "Three Phase Inverter",
    201: "Single Phase Meter",
    202: "Split Phase Meter",
    203: "Three Phase Wye Meter",
    204: "Three Phase Delta Meter",
}

SE_DEVICE_STATUS = {
    1: "I_STATUS_OFF",
    2: "I_STATUS_SLEEPING",
    3: "I_STATUS_STARTING",
    4: "I_STATUS_MPPT",
    5: "I_STATUS_THROTTLED",
    6: "I_STATUS_SHUTTING_DOWN",
    7: "I_STATUS_FAULT",
    8: "I_STATUS_STANDBY",
}

FR_DEVICE_STATUS = {
    1: "I_STATUS_OFF",
    2: "I_STATUS_SLEEPING",
    3: "I_STATUS_STARTING",
    4: "I_STATUS_MPPT",
    5: "I_STATUS_THROTTLED",
    6: "I_STATUS_SHUTTING_DOWN",
    7: "I_STATUS_FAULT",
    8: "I_STATUS_STANDBY",
    9: "I_STATUS_NO_BUSINIT",
    10: "I_STATUS_NO_COMM_INV",
    11: "I_STATUS_SN_OVERCURRENT",
    12: "I_STATUS_BOOTLOAD",
    13: "I_STATUS_AFCI",
}

SE_DEVICE_STATUS_DESC = {
    SUNSPEC_NOT_IMPL_INT16: None,
    0: "Unknown",
    1: "Off",
    2: "Sleeping (Auto-Shutdown)",
    3: "Grid Monitoring",
    4: "Production",
    5: "Production (Curtailed)",
    6: "Shutting Down",
    7: "Fault",
    8: "Maintenance",
}

FR_DEVICE_STATUS_DESC = {
    SUNSPEC_NOT_IMPL_INT16: None,
    1: "Off",
    2: "Sleeping (Auto-Shutdown)",
    3: "Starting",
    4: "Production",
    5: "Production (Curtailed)",
    6: "Shutting Down",
    7: "Fault",
    8: "Standby",
    9: "No SolarNet Comms",
    10: "No Inverter Comms",
    11: "SolarNet Overcurrent",
    12: "Update In Progress",
    13: "Arc Detection",
}

SE_VENDOR_STATUS = {
    SUNSPEC_NOT_IMPL_INT16: None,
    0: "No Error",
    17: "Temperature too high",
    25: "Isolation faults",
    27: "Hardware error",
    31: "AC voltage too high",
    33: "AC voltage too high",
    32: "AC voltage too low",
    34: "AC freq. too high",
    35: "AC freq. too low",
    41: "AC voltage too low",
    44: "No country selected",
    64: "AC voltage too high",
    65: "AC voltage too high",
    66: "AC voltage too high",
    61: "AC voltage too low",
    62: "AC voltage too low",
    63: "AC voltage too low",
    67: "AC voltage too low",
    68: "AC voltage too low",
    69: "AC voltage too low",
    79: "AC freq. too high",
    80: "AC freq. too high",
    81: "AC freq. too high",
    82: "AC freq. too low",
    83: "AC freq. too low",
    84: "AC freq. too low",
    95: "Hardware error",
    104: "Temperature too high",
    106: "Hardware error",
    120: "Hardware error",
    121: "Isolation faults",
    125: "Hardware error",
    126: "Hardware error",
    150: "Arc fault detected",
    151: "Arc fault detected",
    153: "Hardware error",
}

FR_VENDOR_STATUS = {
    SUNSPEC_NOT_IMPL_INT16: None,
    1: "Off",
    2: "Sleeping (auto-shutdown)",
    3: "Starting up",
    4: "Tracking power point",
    5: "Forced power reduction",
    6: "Shutting down",
    7: "One or more faults exist",
    8: "Standby (service on unit)",
    9: "No SolarNet communication",
    10: "No communication with inverter",
    11: "Overcurrent on SolarNet plug detected",
    12: "Inverter is being updated",
    13: "AFCI Event",
}

SE_METER_EVENTS = {
    0: "undefined_0",
    1: "undefined_1",
    2: "M_EVENT_Power_Failure",
    3: "M_EVENT_Under_Voltage",
    4: "M_EVENT_Low_PF",
    5: "M_EVENT_Over_Current",
    6: "M_EVENT_Over_Voltage",
    7: "M_EVENT_Missing_Sensor",
    8: "M_EVENT_Reserved1",
    9: "M_EVENT_Reserved2",
    10: "M_EVENT_Reserved3",
    11: "M_EVENT_Reserved4",
    12: "M_EVENT_Reserved5",
    13: "M_EVENT_Reserved6",
    14: "M_EVENT_Reserved7",
    15: "M_EVENT_Reserved8",
    16: "M_EVENT_OEM1",
    17: "M_EVENT_OEM2",
    18: "M_EVENT_OEM3",
    19: "M_EVENT_OEM4",
    20: "M_EVENT_OEM5",
    21: "M_EVENT_OEM6",
    22: "M_EVENT_OEM7",
    23: "M_EVENT_OEM8",
    24: "M_EVENT_OEM9",
    25: "M_EVENT_OEM10",
    26: "M_EVENT_OEM11",
    27: "M_EVENT_OEM12",
    28: "M_EVENT_OEM13",
    29: "M_EVENT_OEM14",
    30: "M_EVENT_OEM15",
    31: "undefined_31",
}
