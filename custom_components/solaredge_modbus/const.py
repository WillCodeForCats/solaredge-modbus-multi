DOMAIN = "solaredge_modbus"
DEFAULT_NAME = "solaredge"
DEFAULT_SCAN_INTERVAL = 60
DEFAULT_PORT = 1502
DEFAULT_NUMBER_INVERTERS = 1
DEFAULT_READ_METER1 = False
DEFAULT_READ_METER2 = False
DEFAULT_READ_METER3 = False
CONF_SOLAREDGE_HUB = "solaredge_hub"
ATTR_DESCRIPTION = "description"
ATTR_MANUFACTURER = "Solaredge"
CONF_NUMBER_INVERTERS = "number_of_inverters"
CONF_READ_METER1 = "read_meter_1"
CONF_READ_METER2 = "read_meter_2"
CONF_READ_METER3 = "read_meter_3"

SENSOR_TYPES = {
    "Phase_Config": ["Phase Configuration", "phaseconfig", None, None],
    "AC_Current": ["AC Current", "accurrent", "A", "mdi:current-ac"],
    "AC_CurrentA": ["AC Current A", "accurrenta", "A", "mdi:current-ac"],
    "AC_CurrentB": ["AC Current B", "accurrentb", "A", "mdi:current-ac"],
    "AC_CurrentC": ["AC Current C", "accurrentc", "A", "mdi:current-ac"],
    "AC_VoltageAB": ["AC Voltage AB", "acvoltageab", "V", None],
    "AC_VoltageBC": ["AC Voltage BC", "acvoltagebc", "V", None],
    "AC_VoltageCA": ["AC Voltage CA", "acvoltageca", "V", None],
    "AC_VoltageAN": ["AC Voltage AN", "acvoltagean", "V", None],
    "AC_VoltageBN": ["AC Voltage BN", "acvoltagebn", "V", None],
    "AC_VoltageCN": ["AC Voltage CN", "acvoltagecn", "V", None],
    "AC_Power": ["AC Power", "acpower", "W", "mdi:solar-power"],
    "AC_Frequency": ["AC Frequency", "acfreq", "Hz", None],
    "AC_VA": ["AC VA", "acva", "VA", None],
    "AC_VAR": ["AC VAR", "acvar", "VAR", None],
    "AC_PF": ["AC PF", "acpf", "%", None],
    "AC_Energy_kWh": ["AC Energy kWh", "acenergy", "kWh", "mdi:solar-power"],
    "DC_Current": ["DC Current", "dccurrent", "A", "mdi:current-dc"],
    "DC_Voltage": ["DC Voltage", "dcvoltage", "V", None],
    "DC_Power": ["DC Power", "dcpower", "W", "mdi:solar-power"],
    "Temp_Sink": ["Temp Sink", "tempsink", "°C", None],
    "Status": ["Status", "status", None, None],
    "Status_Text": ["Status Text", "status_text", None, None],
    "Status_Vendor": ["Status Vendor", "statusvendor", None, None],
    "Status_Vendor_Text": ["Status Vendor Text", "statusvendor_text", None, None],
}

METER_SENSOR_TYPES = {
    "AC_Current": ["AC Current", "accurrent", "A", "mdi:current-ac"],
    "AC_Current_A": ["AC Current_A", "accurrenta", "A", "mdi:current-ac"],
    "AC_Current_B": ["AC Current_B", "accurrentb", "A", "mdi:current-ac"],
    "AC_Current_C": ["AC Current_C", "accurrentc", "A", "mdi:current-ac"],
    "AC_Voltage_LN": ["AC Voltage LN", "acvoltageln", "V", None],
    "AC_Voltage_AN": ["AC Voltage AN", "acvoltagean", "V", None],
    "AC_Voltage_BN": ["AC Voltage BN", "acvoltagebn", "V", None],
    "AC_Voltage_CN": ["AC Voltage CN", "acvoltagecn", "V", None],
    "AC_Voltage_LL": ["AC Voltage LL", "acvoltagell", "V", None],
    "AC_Voltage_AB": ["AC Voltage AB", "acvoltageab", "V", None],
    "AC_Voltage_BC": ["AC Voltage BC", "acvoltagebc", "V", None],
    "AC_Voltage_CA": ["AC Voltage CA", "acvoltageca", "V", None],
    "AC_Frequency": ["AC Frequency", "acfreq", "Hz", None],
    "AC_Power": ["AC Power", "acpower", "W", None],
    "AC_Power_A": ["AC Power A", "acpowera", "W", None],
    "AC_Power_B": ["AC Power B", "acpowerb", "W", None],
    "AC_Power_C": ["AC Power C", "acpowerc", "W", None],
    "AC_VA": ["AC VA", "acva", "VA", None],
    "AC_VA_A": ["AC VA A", "acvaa", "VA", None],
    "AC_VA_B": ["AC VA B", "acvab", "VA", None],
    "AC_VA_C": ["AC VA C", "acvac", "VA", None],
    "AC_VAR": ["AC VAR", "acvar", "VAR", None],
    "AC_VAR_A": ["AC VAR A", "acvara", "VAR", None],
    "AC_VAR_B": ["AC VAR B", "acvarb", "VAR", None],
    "AC_VAR_C": ["AC VAR C", "acvarc", "VAR", None],
    "AC_PF": ["AC PF", "acpf", "%", None],
    "AC_PF_A": ["AC PF A", "acpfa", "%", None],
    "AC_PF_B": ["AC PF B", "acpfb", "%", None],
    "AC_PF_C": ["AC PF C", "acpfc", "%", None],
    "EXPORTED_KWH": ["EXPORTED KWH", "exported", "kWh", None],
    "EXPORTED_A_KWH": ["EXPORTED A KWH", "exporteda", "kWh", None],
    "EXPORTED_B_KWH": ["EXPORTED B KWH", "exportedb", "kWh", None],
    "EXPORTED_C_KWH": ["EXPORTED C KWH", "exportedc", "kWh", None],
    "IMPORTED_KWH": ["IMPORTED KWH", "imported", "kWh", None],
    "IMPORTED_KWH_A": ["IMPORTED A KWH", "importeda", "kWh", None],
    "IMPORTED_KWH_B": ["IMPORTED B KWH", "importedb", "kWh", None],
    "IMPORTED_KWH_C": ["IMPORTED C KWH", "importedc", "kWh", None],
    "EXPORTED_VA": ["EXPORTED VAh", "exportedva", "VAh", None],
    "EXPORTED_VA_A": ["EXPORTED A VAh", "exportedvaa", "VAh", None],
    "EXPORTED_VA_B": ["EXPORTED B VAh", "exportedvab", "VAh", None],
    "EXPORTED_VA_C": ["EXPORTED C VAh", "exportedvac", "VAh", None],
    "IMPORTED_VA": ["IMPORTED VAh", "importedva", "VAh", None],
    "IMPORTED_VA_A": ["IMPORTED A VAh", "importedvaa", "VAh", None],
    "IMPORTED_VA_B": ["IMPORTED B VAh", "importedvab", "VAh", None],
    "IMPORTED_VA_C": ["IMPORTED C VAh", "importedvac", "VAh", None],
    "IMPORT_VARH_Q1": ["IMPORT VARH Q1", "importvarhq1", "VARh", None],
    "IMPORT_VARH_Q1_A": ["IMPORT VARH Q1 A", "importvarhq1a", "VARh", None],
    "IMPORT_VARH_Q1_B": ["IMPORT VARH Q1 B", "importvarhq1b", "VARh", None],
    "IMPORT_VARH_Q1_C": ["IMPORT VARH Q1 C", "importvarhq1c", "VARh", None],
    "IMPORT_VARH_Q2": ["IMPORT VARH Q2", "importvarhq2", "VARh", None],
    "IMPORT_VARH_Q2_A": ["IMPORT VARH Q2 A", "importvarhq2a", "VARh", None],
    "IMPORT_VARH_Q2_B": ["IMPORT VARH Q2 B", "importvarhq2b", "VARh", None],
    "IMPORT_VARH_Q2_C": ["IMPORT VARH Q2 C", "importvarhq2c", "VARh", None],
    "IMPORT_VARH_Q3": ["IMPORT VARH Q3", "importvarhq3", "VARh", None],
    "IMPORT_VARH_Q3_A": ["IMPORT VARH Q3 A", "importvarhq3a", "VARh", None],
    "IMPORT_VARH_Q3_B": ["IMPORT VARH Q3 B", "importvarhq3b", "VARh", None],
    "IMPORT_VARH_Q3_C": ["IMPORT VARH Q3 C", "importvarhq3c", "VARh", None],
    "IMPORT_VARH_Q4": ["IMPORT VARH Q4", "importvarhq4", "VARh", None],
    "IMPORT_VARH_Q4_A": ["IMPORT VARH Q4 A", "importvarhq4a", "VARh", None],
    "IMPORT_VARH_Q4_B": ["IMPORT VARH Q4 B", "importvarhq4b", "VARh", None],
    "IMPORT_VARH_Q4_C": ["IMPORT VARH Q4 C", "importvarhq4c", "VARh", None],
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
DEVICE_STATUSES = {
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

VENDOR_STATUSES = {
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

PHASE_CONFIG = {
    101: "Single Phase",
    102: "Split Phase",
    103: "Three Phase",
}
