DOMAIN = "solaredge_modbus"
DEFAULT_NAME = "solaredge"
DEFAULT_SCAN_INTERVAL = 60
DEFAULT_PORT = 1502
DEFAULT_NUMBER_INVERTERS = 1
DEFAULT_DEVICE_ID = 1
DEFAULT_READ_METER1 = False
DEFAULT_READ_METER2 = False
DEFAULT_READ_METER3 = False
CONF_SOLAREDGE_HUB = "solaredge_hub"
ATTR_DESCRIPTION = "description"
ATTR_MANUFACTURER = "Solaredge"
CONF_NUMBER_INVERTERS = "number_of_inverters"
CONF_DEVICE_ID = "device_id"
CONF_READ_METER1 = "read_meter_1"
CONF_READ_METER2 = "read_meter_2"
CONF_READ_METER3 = "read_meter_3"

# units from homeassistant core
from homeassistant.const import (
    ENERGY_KILO_WATT_HOUR,
    POWER_WATT, POWER_KILO_WATT, POWER_VOLT_AMPERE,
    ELECTRIC_CURRENT_AMPERE, ELECTRIC_POTENTIAL_VOLT,
    PERCENTAGE, TEMP_CELSIUS, FREQUENCY_HERTZ,
)
# units missing in homeassistant core
POWER_VOLT_AMPERE_REACTIVE = "VAR"
ENERGY_VOLT_AMPERE_HOUR = "VAh"
ENERGY_VOLT_AMPERE_REACTIVE_HOUR = "VARh"

SENSOR_TYPES = {
    "C_Manufacturer": ["Manufacturer", "manufacturer", None, None],
    "C_Model": ["Model", "model", None, None],
    "C_Version": ["Version", "version", None, None],
    "C_SerialNumber": ["Serial Number", "serialnumber", None, None],
    "C_DeviceAddress": ["Device Address", "deviceaddress", None, None],
    "C_Sunspec_DID": ["Sunspec Device ID", "sunspecdid", None, None],
    "AC_Current": ["AC Current", "accurrent", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac"],
    "AC_CurrentA": ["AC Current A", "accurrenta", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac"],
    "AC_CurrentB": ["AC Current B", "accurrentb", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac"],
    "AC_CurrentC": ["AC Current C", "accurrentc", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac"],
    "AC_VoltageAB": ["AC Voltage AB", "acvoltageab", ELECTRIC_POTENTIAL_VOLT, None],
    "AC_VoltageBC": ["AC Voltage BC", "acvoltagebc", ELECTRIC_POTENTIAL_VOLT, None],
    "AC_VoltageCA": ["AC Voltage CA", "acvoltageca", ELECTRIC_POTENTIAL_VOLT, None],
    "AC_VoltageAN": ["AC Voltage AN", "acvoltagean", ELECTRIC_POTENTIAL_VOLT, None],
    "AC_VoltageBN": ["AC Voltage BN", "acvoltagebn", ELECTRIC_POTENTIAL_VOLT, None],
    "AC_VoltageCN": ["AC Voltage CN", "acvoltagecn", ELECTRIC_POTENTIAL_VOLT, None],
    "AC_Power": ["AC Power", "acpower", POWER_WATT, "mdi:solar-power"],
    "AC_Frequency": ["AC Frequency", "acfreq", FREQUENCY_HERTZ, None],
    "AC_VA": ["AC VA", "acva", POWER_VOLT_AMPERE, None],
    "AC_VAR": ["AC VAR", "acvar", POWER_VOLT_AMPERE_REACTIVE, None],
    "AC_PF": ["AC PF", "acpf", PERCENTAGE, None],
    "AC_Energy_kWh": ["AC Energy kWh", "acenergy", ENERGY_KILO_WATT_HOUR, "mdi:solar-power"],
    "DC_Current": ["DC Current", "dccurrent", ELECTRIC_CURRENT_AMPERE, "mdi:current-dc"],
    "DC_Voltage": ["DC Voltage", "dcvoltage", ELECTRIC_POTENTIAL_VOLT, None],
    "DC_Power": ["DC Power", "dcpower", POWER_WATT, "mdi:solar-power"],
    "Temp_Sink": ["Temp Sink", "tempsink", TEMP_CELSIUS, None],
    "Status": ["Status", "status", None, None],
    "Status_Text": ["Status Text", "status_text", None, None],
    "Status_Vendor": ["Status Vendor", "statusvendor", None, None],
    "Status_Vendor_Text": ["Status Vendor Text", "statusvendor_text", None, None],
}

METER_SENSOR_TYPES = {
    "C_Manufacturer": ["Manufacturer", "manufacturer", None, None],
    "C_Model": ["Model", "model", None, None],
    "C_Option": ["Option", "option", None, None],
    "C_Version": ["Version", "version", None, None],
    "C_SerialNumber": ["Serial Number", "serialnumber", None, None],
    "C_DeviceAddress": ["Device Address", "deviceaddress", None, None],
    "C_Sunspec_DID": ["Sunspec Device ID", "sunspecdid", None, None],
    "AC_Current": ["AC Current", "accurrent", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac"],
    "AC_Current_A": ["AC Current_A", "accurrenta", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac"],
    "AC_Current_B": ["AC Current_B", "accurrentb", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac"],
    "AC_Current_C": ["AC Current_C", "accurrentc", ELECTRIC_CURRENT_AMPERE, "mdi:current-ac"],
    "AC_Voltage_LN": ["AC Voltage LN", "acvoltageln", ELECTRIC_POTENTIAL_VOLT, None],
    "AC_Voltage_AN": ["AC Voltage AN", "acvoltagean", ELECTRIC_POTENTIAL_VOLT, None],
    "AC_Voltage_BN": ["AC Voltage BN", "acvoltagebn", ELECTRIC_POTENTIAL_VOLT, None],
    "AC_Voltage_CN": ["AC Voltage CN", "acvoltagecn", ELECTRIC_POTENTIAL_VOLT, None],
    "AC_Voltage_LL": ["AC Voltage LL", "acvoltagell", ELECTRIC_POTENTIAL_VOLT, None],
    "AC_Voltage_AB": ["AC Voltage AB", "acvoltageab", ELECTRIC_POTENTIAL_VOLT, None],
    "AC_Voltage_BC": ["AC Voltage BC", "acvoltagebc", ELECTRIC_POTENTIAL_VOLT, None],
    "AC_Voltage_CA": ["AC Voltage CA", "acvoltageca", ELECTRIC_POTENTIAL_VOLT, None],
    "AC_Frequency": ["AC Frequency", "acfreq", FREQUENCY_HERTZ, None],
    "AC_Power": ["AC Power", "acpower", POWER_WATT, None],
    "AC_Power_A": ["AC Power A", "acpowera", POWER_WATT, None],
    "AC_Power_B": ["AC Power B", "acpowerb", POWER_WATT, None],
    "AC_Power_C": ["AC Power C", "acpowerc", POWER_WATT, None],
    "AC_VA": ["AC VA", "acva", POWER_VOLT_AMPERE, None],
    "AC_VA_A": ["AC VA A", "acvaa", POWER_VOLT_AMPERE, None],
    "AC_VA_B": ["AC VA B", "acvab", POWER_VOLT_AMPERE, None],
    "AC_VA_C": ["AC VA C", "acvac", POWER_VOLT_AMPERE, None],
    "AC_VAR": ["AC VAR", "acvar", POWER_VOLT_AMPERE_REACTIVE, None],
    "AC_VAR_A": ["AC VAR A", "acvara", POWER_VOLT_AMPERE_REACTIVE, None],
    "AC_VAR_B": ["AC VAR B", "acvarb", POWER_VOLT_AMPERE_REACTIVE, None],
    "AC_VAR_C": ["AC VAR C", "acvarc", POWER_VOLT_AMPERE_REACTIVE, None],
    "AC_PF": ["AC PF", "acpf", PERCENTAGE, None],
    "AC_PF_A": ["AC PF A", "acpfa", PERCENTAGE, None],
    "AC_PF_B": ["AC PF B", "acpfb", PERCENTAGE, None],
    "AC_PF_C": ["AC PF C", "acpfc", PERCENTAGE, None],
    "EXPORTED_KWH": ["EXPORTED KWH", "exported", ENERGY_KILO_WATT_HOUR, None],
    "EXPORTED_A_KWH": ["EXPORTED A KWH", "exporteda", ENERGY_KILO_WATT_HOUR, None],
    "EXPORTED_B_KWH": ["EXPORTED B KWH", "exportedb", ENERGY_KILO_WATT_HOUR, None],
    "EXPORTED_C_KWH": ["EXPORTED C KWH", "exportedc", ENERGY_KILO_WATT_HOUR, None],
    "IMPORTED_KWH": ["IMPORTED KWH", "imported", ENERGY_KILO_WATT_HOUR, None],
    "IMPORTED_KWH_A": ["IMPORTED A KWH", "importeda", ENERGY_KILO_WATT_HOUR, None],
    "IMPORTED_KWH_B": ["IMPORTED B KWH", "importedb", ENERGY_KILO_WATT_HOUR, None],
    "IMPORTED_KWH_C": ["IMPORTED C KWH", "importedc", ENERGY_KILO_WATT_HOUR, None],
    "EXPORTED_VA": ["EXPORTED VAh", "exportedva", ENERGY_VOLT_AMPERE_HOUR, None],
    "EXPORTED_VA_A": ["EXPORTED A VAh", "exportedvaa", ENERGY_VOLT_AMPERE_HOUR, None],
    "EXPORTED_VA_B": ["EXPORTED B VAh", "exportedvab", ENERGY_VOLT_AMPERE_HOUR, None],
    "EXPORTED_VA_C": ["EXPORTED C VAh", "exportedvac", ENERGY_VOLT_AMPERE_HOUR, None],
    "IMPORTED_VA": ["IMPORTED VAh", "importedva", ENERGY_VOLT_AMPERE_HOUR, None],
    "IMPORTED_VA_A": ["IMPORTED A VAh", "importedvaa", ENERGY_VOLT_AMPERE_HOUR, None],
    "IMPORTED_VA_B": ["IMPORTED B VAh", "importedvab", ENERGY_VOLT_AMPERE_HOUR, None],
    "IMPORTED_VA_C": ["IMPORTED C VAh", "importedvac", ENERGY_VOLT_AMPERE_HOUR, None],
    "IMPORT_VARH_Q1": ["IMPORT VARH Q1", "importvarhq1", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None],
    "IMPORT_VARH_Q1_A": ["IMPORT VARH Q1 A", "importvarhq1a", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None],
    "IMPORT_VARH_Q1_B": ["IMPORT VARH Q1 B", "importvarhq1b", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None],
    "IMPORT_VARH_Q1_C": ["IMPORT VARH Q1 C", "importvarhq1c", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None],
    "IMPORT_VARH_Q2": ["IMPORT VARH Q2", "importvarhq2", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None],
    "IMPORT_VARH_Q2_A": ["IMPORT VARH Q2 A", "importvarhq2a", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None],
    "IMPORT_VARH_Q2_B": ["IMPORT VARH Q2 B", "importvarhq2b", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None],
    "IMPORT_VARH_Q2_C": ["IMPORT VARH Q2 C", "importvarhq2c", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None],
    "IMPORT_VARH_Q3": ["IMPORT VARH Q3", "importvarhq3", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None],
    "IMPORT_VARH_Q3_A": ["IMPORT VARH Q3 A", "importvarhq3a", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None],
    "IMPORT_VARH_Q3_B": ["IMPORT VARH Q3 B", "importvarhq3b", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None],
    "IMPORT_VARH_Q3_C": ["IMPORT VARH Q3 C", "importvarhq3c", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None],
    "IMPORT_VARH_Q4": ["IMPORT VARH Q4", "importvarhq4", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None],
    "IMPORT_VARH_Q4_A": ["IMPORT VARH Q4 A", "importvarhq4a", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None],
    "IMPORT_VARH_Q4_B": ["IMPORT VARH Q4 B", "importvarhq4b", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None],
    "IMPORT_VARH_Q4_C": ["IMPORT VARH Q4 C", "importvarhq4c", ENERGY_VOLT_AMPERE_REACTIVE_HOUR, None],
    "M_Events": ["Meter Events", "meterevents", None, None],

}

# parameter names per sunspec
DEVICE_STATUS_DESC = {
    1: "I_STATUS_OFF",
    2: "I_STATUS_SLEEPING",
    3: "I_STATUS_STARTING",
    4: "I_STATUS_MPPT",
    5: "I_STATUS_THROTTLED",
    6: "I_STATUS_SHUTTING_DOWN",
    7: "I_STATUS_FAULT",
    8: "I_STATUS_STANDBY",
}

# English descriptions of parameter names
DEVICE_STATUS = {
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

VENDOR_STATUS = {
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

SUNSPEC_DID = {
    101: "Single Phase Inverter",
    102: "Split Phase Inverter",
    103: "Three Phase Inverter",
    201: "Single Phase Meter",
    202: "Split Phase Meter",
    203: "Three Phase Wye Meter",
    204: "Three Phase Delta Meter",
}
