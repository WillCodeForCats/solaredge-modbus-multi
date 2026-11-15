"""Constants used by SolarEdge Modbus Multi components."""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Any, Final

from homeassistant.util.hass_dict import HassKey

DOMAIN = "solaredge_modbus_multi"
DATA_YAML: HassKey[dict[str, Any]] = HassKey(f"{DOMAIN}_yaml")
DEFAULT_NAME = "SolarEdge"

SETUP_TYPE = "setup_type"
SETUP_SCAN_FAST = "scan_fast"  # Scan IDs 1-32
SETUP_SCAN_FULL = "scan_full"  # Scan IDs 1-247
SETUP_MANUAL = "manual_list"
BYPASS_DEVICE_CHECK = "bypass_device_check"

# Seconds to wait for a TCP connection when probing a discovered inverter
ZEROCONF_PROBE_TIMEOUT = 3.0

# Number of read-only poll cycles to keep a unit's post-write message
# spacing active before clearing it back to 0.
WRITE_SETTLE_CYCLES: Final = 2

# raise a startup exception if library versions are less than this
TMODBUS_REQUIRED_VERSION = "0.6.1"
MODBUS_CONNECTION_REQUIRED_VERSION = "4.10.0"

# units missing in homeassistant core
ENERGY_VOLT_AMPERE_HOUR: Final = "VAh"

INVERTED_POWER_VERSION = "2026.2.0"  # home assistant core version

# Minimum gap, in seconds, between every request on the connection.
# modbus-connection only serializes/paces requests when this is non-zero
# The idea is to help with the coordinator requesting a refresh with a write
# at the same time. Set to 0 to disable.
MESSAGE_SPACING = 0.1

# Seconds a setup or refresh may run before it is given up on as wedged. This
# is not sized to the devices: every request has its own timeout, and taking
# this long means something is broken or misconfigured.
REFRESH_WATCHDOG = 300

# Seconds a refresh may take before it is reported as slow. A healthy refresh
# takes a second or two.
SLOW_REFRESH = 60


class RetrySettings(IntEnum):
    """Retry settings when opening a connection to the inverter fails."""

    Time = 1000  # first attempt in milliseconds
    Ratio = 2  # time multiplier between each attempt
    Limit = 6  # number of attempts before failing
    FeatureProbeTimeouts = 3  # failures tolerated for an already-detected feature


class BatteryLimit(IntEnum):
    """Configure battery limits for input and display validation."""

    Vmin = 0  # volts
    Vmax = 1000  # volts
    Amin = -200  # amps
    Amax = 200  # amps
    Tmax = 100  # degrees C
    Tmin = -30  # degrees C
    ChargeMax = 1000000  # watts
    DischargeMax = 1000000  # watts


class ConfDefaultInt(IntEnum):
    """Defaults for options that are integers."""

    SCAN_INTERVAL = 10
    PORT = 1502
    REQUEST_TIMEOUT = 10
    SLEEP_AFTER_WRITE = 0
    BATTERY_RATING_ADJUST = 0
    BATTERY_ENERGY_RESET_CYCLES = 0


class ConfDefaultFlag(IntEnum):
    """Defaults for options that are booleans."""

    DETECT_METERS = 1
    DETECT_BATTERIES = 0
    DETECT_EXTRAS = 0
    ADV_PWR_CONTROL = 0
    ADV_STORAGE_CONTROL = 0
    ADV_SITE_LIMIT_CONTROL = 0
    ALLOW_BATTERY_ENERGY_RESET = 0
    CLOSE_AFTER_POLLING = 0


class ConfDefaultStr(StrEnum):
    """Defaults for options that are strings."""

    DEVICE_LIST = "1"


class ConfName(StrEnum):
    """Conf name."""

    DEVICE_LIST = "device_list"
    DETECT_METERS = "detect_meters"
    DETECT_BATTERIES = "detect_batteries"
    DETECT_EXTRAS = "detect_extras"
    ADV_PWR_CONTROL = "advanced_power_control"
    ADV_STORAGE_CONTROL = "adv_storage_control"
    ADV_SITE_LIMIT_CONTROL = "adv_site_limit_control"
    ALLOW_BATTERY_ENERGY_RESET = "allow_battery_energy_reset"
    REQUEST_TIMEOUT = "request_timeout"
    SLEEP_AFTER_WRITE = "sleep_after_write"
    BATTERY_RATING_ADJUST = "battery_rating_adjust"
    BATTERY_ENERGY_RESET_CYCLES = "battery_energy_reset_cycles"
    CLOSE_AFTER_POLLING = "close_after_polling"

    # Old config entry names for migration
    NUMBER_INVERTERS = "number_of_inverters"
    DEVICE_ID = "device_id"
