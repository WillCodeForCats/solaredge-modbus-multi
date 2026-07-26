"""Tests for the SolarEdge Modbus Multi sensor module."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from custom_components.solaredge_modbus_multi.const import (
    BATTERY_STATUS,
    DEVICE_STATUS,
    SunSpecNotImpl,
)

# Patch UnitOfReactivePower if it doesn't exist (for older HA versions)
try:
    from homeassistant.const import UnitOfReactivePower
except ImportError:
    # Create a mock class for testing
    class UnitOfReactivePower:
        VOLT_AMPERE_REACTIVE = "var"

    # Monkey patch it into homeassistant.const
    import homeassistant.const

    homeassistant.const.UnitOfReactivePower = UnitOfReactivePower

# Now import sensor module after patching
from custom_components.solaredge_modbus_multi.sensor import (
    ACCurrentSensor,
    ACFrequency,
    ACPower,
    ACPowerInverted,
    DCCurrent,
    DCPower,
    DCVoltage,
    HeatSinkTemperature,
    SolarEdgeBatteryCurrent,
    SolarEdgeBatteryPower,
    SolarEdgeBatteryPowerInverted,
    SolarEdgeBatterySOE,
    SolarEdgeBatterySOH,
    SolarEdgeBatteryStatus,
    SolarEdgeBatteryVoltage,
    SolarEdgeInverterStatus,
    SolarEdgeSensorBase,
    StatusVendor,
    VoltageSensor,
)


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coordinator = MagicMock()
    coordinator.async_add_listener = MagicMock()
    coordinator.data = {}
    return coordinator


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_123"
    entry.data = {"name": "Test SolarEdge"}
    return entry


@pytest.fixture
def mock_inverter_platform():
    """Create a mock inverter platform with typical decoded data."""
    platform = MagicMock()
    platform.uid_base = "se_inv_1"
    platform.device_info = {
        "identifiers": {("solaredge_modbus_multi", "se_inv_1")},
        "name": "SolarEdge Inverter 1",
        "manufacturer": "SolarEdge",
        "model": "SE10K",
    }
    platform.online = True
    platform.model = "SE10K"
    platform.manufacturer = "SolarEdge"
    platform.serial = "123456789"
    platform.fw_version = "1.0.0"
    platform.device_address = 1
    platform.option = ""
    platform.has_parent = False

    # Common model data for inverter (DID 101 = single phase)
    platform.decoded_model = {
        "C_SunSpec_DID": 101,
        "AC_Current": 100,
        "AC_Current_A": 100,
        "AC_Current_B": 100,
        "AC_Current_C": 100,
        "AC_Current_SF": -2,
        "AC_Voltage_AB": 2400,
        "AC_Voltage_BC": 2400,
        "AC_Voltage_CA": 2400,
        "AC_Voltage_AN": 2400,
        "AC_Voltage_BN": 2400,
        "AC_Voltage_CN": 2400,
        "AC_Voltage_SF": -1,
        "AC_Power": 5000,
        "AC_Power_SF": -1,
        "AC_Frequency": 5000,
        "AC_Frequency_SF": -2,
        "I_DC_Current": 200,
        "I_DC_Current_SF": -1,
        "I_DC_Voltage": 4000,
        "I_DC_Voltage_SF": -1,
        "I_DC_Power": 5100,
        "I_DC_Power_SF": -1,
        "I_Temp_Sink": 450,
        "I_Temp_SF": -1,
        "I_Status": 4,  # MPPT
        "I_Status_Vendor": 0,  # No error
    }

    platform.decoded_common = {}

    return platform


@pytest.fixture
def mock_meter_platform_did201():
    """Create a mock meter platform with DID 201 (single phase)."""
    platform = MagicMock()
    platform.uid_base = "se_meter_1"
    platform.device_info = {
        "identifiers": {("solaredge_modbus_multi", "se_meter_1")},
        "name": "SolarEdge Meter 1",
    }
    platform.online = True

    # Meter model data (DID 201 = single phase meter)
    platform.decoded_model = {
        "C_SunSpec_DID": 201,
        "AC_Current": 150,
        "AC_Current_A": 150,
        "AC_Current_B": 150,
        "AC_Current_C": 150,
        "AC_Current_SF": -2,
        "AC_Voltage_LN": 2400,
        "AC_Voltage_AN": 2400,
        "AC_Voltage_BN": 2400,
        "AC_Voltage_CN": 2400,
        "AC_Voltage_LL": 2400,
        "AC_Voltage_AB": 2400,
        "AC_Voltage_BC": 2400,
        "AC_Voltage_CA": 2400,
        "AC_Voltage_SF": -1,
        "AC_Power": 3000,
        "AC_Power_A": 1000,
        "AC_Power_B": 1000,
        "AC_Power_C": 1000,
        "AC_Power_SF": -1,
        "AC_Frequency": 5000,
        "AC_Frequency_SF": -2,
    }

    return platform


@pytest.fixture
def mock_meter_platform_did203():
    """Create a mock meter platform with DID 203 (three phase wye)."""
    platform = MagicMock()
    platform.uid_base = "se_meter_1"
    platform.device_info = {
        "identifiers": {("solaredge_modbus_multi", "se_meter_1")},
        "name": "SolarEdge Meter 1",
    }
    platform.online = True

    # Meter model data (DID 203 = three phase wye meter)
    platform.decoded_model = {
        "C_SunSpec_DID": 203,
        "AC_Current": 150,
        "AC_Current_A": 150,
        "AC_Current_B": 150,
        "AC_Current_C": 150,
        "AC_Current_SF": -2,
        "AC_Voltage_LN": 2400,
        "AC_Voltage_AN": 2400,
        "AC_Voltage_BN": 2400,
        "AC_Voltage_CN": 2400,
        "AC_Voltage_LL": 4160,
        "AC_Voltage_AB": 4160,
        "AC_Voltage_BC": 4160,
        "AC_Voltage_CA": 4160,
        "AC_Voltage_SF": -1,
        "AC_Power": 9000,
        "AC_Power_A": 3000,
        "AC_Power_B": 3000,
        "AC_Power_C": 3000,
        "AC_Power_SF": -1,
        "AC_Frequency": 5000,
        "AC_Frequency_SF": -2,
    }

    return platform


@pytest.fixture
def mock_battery_platform():
    """Create a mock battery platform with typical decoded data."""
    platform = MagicMock()
    platform.uid_base = "se_battery_1"
    platform.device_info = {
        "identifiers": {("solaredge_modbus_multi", "se_battery_1")},
        "name": "SolarEdge Battery 1",
    }
    platform.online = True
    platform.inverter_unit_id = 1
    platform.battery_id = 1
    platform.battery_rating_adjust = 1.0
    platform.allow_battery_energy_reset = False
    platform.battery_energy_reset_cycles = 3

    # Battery model data
    platform.decoded_model = {
        "B_Temp_Average": 25.5,
        "B_Temp_Max": 27.0,
        "B_DC_Voltage": 400.5,
        "B_DC_Current": 10.5,
        "B_DC_Power": 4200.0,
        "B_SOE": 75.0,
        "B_SOH": 98.0,
        "B_Status": 3,  # Charge
        "B_Energy_Max": 10000.0,
        "B_MaxChargePower": 5000.0,
        "B_MaxChargePeakPower": 6000.0,
        "B_MaxDischargePower": 5000.0,
        "B_MaxDischargePeakPower": 6000.0,
        "B_Energy_Available": 7500.0,
        "B_Export_Energy_WH": 50000,
        "B_Import_Energy_WH": 60000,
    }

    platform.decoded_common = {
        "B_RatedEnergy": 10000.0,
    }

    return platform


class TestSolarEdgeSensorBase:
    """Tests for SolarEdgeSensorBase class."""

    def test_scale_factor_positive(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test scale_factor with positive exponent."""
        sensor = SolarEdgeSensorBase(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )
        # 100 * 10^2 = 10000
        assert sensor.scale_factor(100, 2) == 10000

    def test_scale_factor_negative(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test scale_factor with negative exponent."""
        sensor = SolarEdgeSensorBase(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )
        # 100 * 10^-2 = 1.0
        assert sensor.scale_factor(100, -2) == 1.0

    def test_scale_factor_zero(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test scale_factor with zero exponent."""
        sensor = SolarEdgeSensorBase(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )
        # 100 * 10^0 = 100
        assert sensor.scale_factor(100, 0) == 100

    def test_device_info(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test device_info property returns platform device info."""
        sensor = SolarEdgeSensorBase(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )
        assert sensor.device_info == mock_inverter_platform.device_info

    def test_available_when_online(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test sensor is available when platform is online."""
        mock_inverter_platform.online = True
        mock_coordinator.last_update_success = True

        sensor = SolarEdgeSensorBase(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )
        assert sensor.available is True

    def test_unavailable_when_offline(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test sensor is unavailable when platform is offline."""
        mock_inverter_platform.online = False
        mock_coordinator.last_update_success = True

        sensor = SolarEdgeSensorBase(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )
        assert sensor.available is False


class TestACCurrentSensor:
    """Tests for ACCurrentSensor."""

    def test_inverter_total_current(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test AC current sensor for inverter total current."""
        sensor = ACCurrentSensor(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.device_class == SensorDeviceClass.CURRENT
        assert sensor.native_unit_of_measurement == UnitOfElectricCurrent.AMPERE
        assert sensor.unique_id == "se_inv_1_ac_current"
        assert sensor.name == "AC Current"
        # 100 * 10^-2 = 1.0
        assert sensor.native_value == 1.0
        assert sensor.suggested_display_precision == 2

    def test_inverter_phase_current(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test AC current sensor for inverter phase A."""
        sensor = ACCurrentSensor(
            mock_inverter_platform, mock_config_entry, mock_coordinator, phase="A"
        )

        assert sensor.unique_id == "se_inv_1_ac_current_a"
        assert sensor.name == "AC Current A"
        # 100 * 10^-2 = 1.0
        assert sensor.native_value == 1.0

    def test_sunspec_not_impl_returns_none(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test that SunSpec not implemented value returns None."""
        mock_inverter_platform.decoded_model["AC_Current"] = SunSpecNotImpl.UINT16

        sensor = ACCurrentSensor(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None

    def test_invalid_scale_factor_returns_none(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test that invalid scale factor returns None."""
        mock_inverter_platform.decoded_model["AC_Current_SF"] = SunSpecNotImpl.INT16

        sensor = ACCurrentSensor(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None

    def test_scale_factor_out_of_range_returns_none(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test that scale factor out of valid range returns None."""
        mock_inverter_platform.decoded_model["AC_Current_SF"] = 15  # Out of range

        sensor = ACCurrentSensor(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None

    def test_meter_current_did201(
        self, mock_meter_platform_did201, mock_config_entry, mock_coordinator
    ):
        """Test AC current sensor for meter with DID 201."""
        sensor = ACCurrentSensor(
            mock_meter_platform_did201, mock_config_entry, mock_coordinator
        )

        # DID 201 uses INT16 for not impl
        assert sensor.SUNSPEC_NOT_IMPL == SunSpecNotImpl.INT16
        # 150 * 10^-2 = 1.5
        assert sensor.native_value == 1.5

    def test_meter_current_did203(
        self, mock_meter_platform_did203, mock_config_entry, mock_coordinator
    ):
        """Test AC current sensor for meter with DID 203."""
        sensor = ACCurrentSensor(
            mock_meter_platform_did203, mock_config_entry, mock_coordinator, phase="A"
        )

        # DID 203 uses INT16 for not impl
        assert sensor.SUNSPEC_NOT_IMPL == SunSpecNotImpl.INT16
        assert sensor.entity_registry_enabled_default is True
        # 150 * 10^-2 = 1.5
        assert sensor.native_value == 1.5


class TestVoltageSensor:
    """Tests for VoltageSensor."""

    def test_voltage_sensor_ab(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test voltage sensor for AB phase."""
        sensor = VoltageSensor(
            mock_inverter_platform, mock_config_entry, mock_coordinator, phase="AB"
        )

        assert sensor.device_class == SensorDeviceClass.VOLTAGE
        assert sensor.native_unit_of_measurement == UnitOfElectricPotential.VOLT
        assert sensor.unique_id == "se_inv_1_ac_voltage_ab"
        assert sensor.name == "AC Voltage AB"
        # 2400 * 10^-1 = 240.0
        assert sensor.native_value == 240.0
        assert sensor.suggested_display_precision == 1

    def test_voltage_sensor_an(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test voltage sensor for AN phase."""
        sensor = VoltageSensor(
            mock_inverter_platform, mock_config_entry, mock_coordinator, phase="AN"
        )

        assert sensor.unique_id == "se_inv_1_ac_voltage_an"
        assert sensor.name == "AC Voltage AN"
        # 2400 * 10^-1 = 240.0
        assert sensor.native_value == 240.0

    def test_voltage_sunspec_not_impl_returns_none(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test that SunSpec not implemented value returns None."""
        mock_inverter_platform.decoded_model["AC_Voltage_AB"] = SunSpecNotImpl.UINT16

        sensor = VoltageSensor(
            mock_inverter_platform, mock_config_entry, mock_coordinator, phase="AB"
        )

        assert sensor.native_value is None

    def test_voltage_entity_enabled_default(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test voltage sensor entity enabled by default logic."""
        # AB should be enabled by default
        sensor_ab = VoltageSensor(
            mock_inverter_platform, mock_config_entry, mock_coordinator, phase="AB"
        )
        assert sensor_ab.entity_registry_enabled_default is True

        # LN should be enabled by default
        sensor_ln = VoltageSensor(
            mock_inverter_platform, mock_config_entry, mock_coordinator, phase="LN"
        )
        assert sensor_ln.entity_registry_enabled_default is True

        # LL should be enabled by default
        sensor_ll = VoltageSensor(
            mock_inverter_platform, mock_config_entry, mock_coordinator, phase="LL"
        )
        assert sensor_ll.entity_registry_enabled_default is True

    def test_meter_voltage_did203(
        self, mock_meter_platform_did203, mock_config_entry, mock_coordinator
    ):
        """Test voltage sensor for meter with DID 203."""
        sensor = VoltageSensor(
            mock_meter_platform_did203, mock_config_entry, mock_coordinator, phase="AN"
        )

        # DID 203 uses INT16 for not impl
        assert sensor.SUNSPEC_NOT_IMPL == SunSpecNotImpl.INT16
        # For three-phase, AN should be enabled
        assert sensor.entity_registry_enabled_default is True
        # 2400 * 10^-1 = 240.0
        assert sensor.native_value == 240.0


class TestACPower:
    """Tests for ACPower sensor."""

    def test_ac_power_inverter(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test AC power sensor for inverter."""
        sensor = ACPower(mock_inverter_platform, mock_config_entry, mock_coordinator)

        assert sensor.device_class == SensorDeviceClass.POWER
        assert sensor.native_unit_of_measurement == UnitOfPower.WATT
        assert sensor.unique_id == "se_inv_1_ac_power"
        assert sensor.name == "AC Power"
        assert sensor.icon == "mdi:solar-power"
        # 5000 * 10^-1 = 500.0
        assert sensor.native_value == 500.0
        assert sensor.suggested_display_precision == 1

    def test_ac_power_phase(
        self, mock_meter_platform_did203, mock_config_entry, mock_coordinator
    ):
        """Test AC power sensor for phase A."""
        sensor = ACPower(
            mock_meter_platform_did203, mock_config_entry, mock_coordinator, phase="A"
        )

        assert sensor.unique_id == "se_meter_1_ac_power_a"
        assert sensor.name == "AC Power A"
        # 3000 * 10^-1 = 300.0
        assert sensor.native_value == 300.0

    def test_ac_power_sunspec_not_impl_returns_none(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test that SunSpec not implemented value returns None."""
        mock_inverter_platform.decoded_model["AC_Power"] = SunSpecNotImpl.INT16

        sensor = ACPower(mock_inverter_platform, mock_config_entry, mock_coordinator)

        assert sensor.native_value is None

    def test_ac_power_entity_enabled_default(
        self, mock_meter_platform_did203, mock_config_entry, mock_coordinator
    ):
        """Test AC power entity enabled by default logic."""
        # Total power should be enabled
        sensor_total = ACPower(
            mock_meter_platform_did203, mock_config_entry, mock_coordinator
        )
        assert sensor_total.entity_registry_enabled_default is True

        # Phase A power for DID 203 should be enabled
        sensor_phase = ACPower(
            mock_meter_platform_did203, mock_config_entry, mock_coordinator, phase="A"
        )
        assert sensor_phase.entity_registry_enabled_default is True


class TestACPowerInverted:
    """Tests for ACPowerInverted sensor."""

    def test_ac_power_inverted(
        self, mock_meter_platform_did201, mock_config_entry, mock_coordinator
    ):
        """Test AC power inverted sensor."""
        sensor = ACPowerInverted(
            mock_meter_platform_did201, mock_config_entry, mock_coordinator
        )

        assert sensor.unique_id == "se_meter_1_ac_power_inverted"
        assert sensor.name == "AC Power Inverted"
        # 3000 * 10^-1 = 300.0, then negated = -300.0
        assert sensor.native_value == -300.0

    def test_ac_power_inverted_none_value(
        self, mock_meter_platform_did201, mock_config_entry, mock_coordinator
    ):
        """Test AC power inverted returns None when base value is None."""
        mock_meter_platform_did201.decoded_model["AC_Power"] = SunSpecNotImpl.INT16

        sensor = ACPowerInverted(
            mock_meter_platform_did201, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None


class TestACFrequency:
    """Tests for ACFrequency sensor."""

    def test_ac_frequency(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test AC frequency sensor."""
        sensor = ACFrequency(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.device_class == SensorDeviceClass.FREQUENCY
        assert sensor.native_unit_of_measurement == UnitOfFrequency.HERTZ
        assert sensor.unique_id == "se_inv_1_ac_frequency"
        assert sensor.name == "AC Frequency"
        # 5000 * 10^-2 = 50.0
        assert sensor.native_value == 50.0
        assert sensor.suggested_display_precision == 2

    def test_ac_frequency_sunspec_not_impl(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test AC frequency with SunSpec not implemented."""
        mock_inverter_platform.decoded_model["AC_Frequency"] = SunSpecNotImpl.UINT16

        sensor = ACFrequency(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None


class TestDCCurrent:
    """Tests for DCCurrent sensor."""

    def test_dc_current(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test DC current sensor."""
        sensor = DCCurrent(mock_inverter_platform, mock_config_entry, mock_coordinator)

        assert sensor.device_class == SensorDeviceClass.CURRENT
        assert sensor.native_unit_of_measurement == UnitOfElectricCurrent.AMPERE
        assert sensor.unique_id == "se_inv_1_dc_current"
        assert sensor.name == "DC Current"
        assert sensor.icon == "mdi:current-dc"
        # 200 * 10^-1 = 20.0
        assert sensor.native_value == 20.0
        assert sensor.suggested_display_precision == 1

    def test_dc_current_unavailable_when_not_impl(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test DC current unavailable when value is not implemented."""
        mock_inverter_platform.decoded_model["I_DC_Current"] = SunSpecNotImpl.UINT16

        sensor = DCCurrent(mock_inverter_platform, mock_config_entry, mock_coordinator)

        assert sensor.available is False

    def test_dc_current_unavailable_when_sf_invalid(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test DC current unavailable when scale factor is invalid."""
        mock_inverter_platform.decoded_model["I_DC_Current_SF"] = SunSpecNotImpl.INT16

        sensor = DCCurrent(mock_inverter_platform, mock_config_entry, mock_coordinator)

        assert sensor.available is False


class TestDCVoltage:
    """Tests for DCVoltage sensor."""

    def test_dc_voltage(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test DC voltage sensor."""
        sensor = DCVoltage(mock_inverter_platform, mock_config_entry, mock_coordinator)

        assert sensor.device_class == SensorDeviceClass.VOLTAGE
        assert sensor.native_unit_of_measurement == UnitOfElectricPotential.VOLT
        assert sensor.unique_id == "se_inv_1_dc_voltage"
        assert sensor.name == "DC Voltage"
        # 4000 * 10^-1 = 400.0
        assert sensor.native_value == 400.0
        assert sensor.suggested_display_precision == 1

    def test_dc_voltage_sunspec_not_impl_returns_none(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test DC voltage returns None when not implemented."""
        mock_inverter_platform.decoded_model["I_DC_Voltage"] = SunSpecNotImpl.UINT16

        sensor = DCVoltage(mock_inverter_platform, mock_config_entry, mock_coordinator)

        assert sensor.native_value is None


class TestDCPower:
    """Tests for DCPower sensor."""

    def test_dc_power(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test DC power sensor."""
        sensor = DCPower(mock_inverter_platform, mock_config_entry, mock_coordinator)

        assert sensor.device_class == SensorDeviceClass.POWER
        assert sensor.native_unit_of_measurement == UnitOfPower.WATT
        assert sensor.unique_id == "se_inv_1_dc_power"
        assert sensor.name == "DC Power"
        assert sensor.icon == "mdi:solar-power"
        # 5100 * 10^-1 = 510.0
        assert sensor.native_value == 510.0
        assert sensor.suggested_display_precision == 1

    def test_dc_power_sunspec_not_impl_returns_none(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test DC power returns None when not implemented."""
        mock_inverter_platform.decoded_model["I_DC_Power"] = SunSpecNotImpl.INT16

        sensor = DCPower(mock_inverter_platform, mock_config_entry, mock_coordinator)

        assert sensor.native_value is None


class TestHeatSinkTemperature:
    """Tests for HeatSinkTemperature sensor."""

    def test_heat_sink_temperature(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test heat sink temperature sensor."""
        sensor = HeatSinkTemperature(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.device_class == SensorDeviceClass.TEMPERATURE
        assert sensor.native_unit_of_measurement == UnitOfTemperature.CELSIUS
        assert sensor.unique_id == "se_inv_1_temp_sink"
        assert sensor.name == "Temperature"
        assert sensor.entity_category == EntityCategory.DIAGNOSTIC
        # 450 * 10^-1 = 45.0
        assert sensor.native_value == 45.0
        assert sensor.suggested_display_precision == 1

    def test_heat_sink_temperature_zero_is_valid(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test heat sink temperature of 0 is a legitimate reading."""
        mock_inverter_platform.decoded_model["I_Temp_Sink"] = 0x0

        sensor = HeatSinkTemperature(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value == 0

    def test_heat_sink_temperature_sunspec_not_impl_returns_none(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test heat sink temperature returns None when not implemented."""
        mock_inverter_platform.decoded_model["I_Temp_Sink"] = SunSpecNotImpl.INT16

        sensor = HeatSinkTemperature(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None


class TestSolarEdgeInverterStatus:
    """Tests for SolarEdgeInverterStatus sensor."""

    def test_inverter_status_mppt(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test inverter status sensor with MPPT state."""
        sensor = SolarEdgeInverterStatus(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.device_class == SensorDeviceClass.ENUM
        assert sensor.unique_id == "se_inv_1_status"
        assert sensor.name == "Status"
        assert sensor.options == list(DEVICE_STATUS.values())
        assert sensor.native_value == "I_STATUS_MPPT"

        attrs = sensor.extra_state_attributes
        assert attrs["status_text"] == "Production"
        assert attrs["status_value"] == 4

    def test_inverter_status_off(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test inverter status sensor with OFF state."""
        mock_inverter_platform.decoded_model["I_Status"] = 1

        sensor = SolarEdgeInverterStatus(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value == "I_STATUS_OFF"

    def test_inverter_status_sunspec_not_impl_returns_none(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test inverter status returns None when not implemented."""
        mock_inverter_platform.decoded_model["I_Status"] = SunSpecNotImpl.INT16

        sensor = SolarEdgeInverterStatus(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None


class TestStatusVendor:
    """Tests for StatusVendor sensor."""

    def test_status_vendor_no_error(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test status vendor sensor with no error."""
        sensor = StatusVendor(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.unique_id == "se_inv_1_status_vendor"
        assert sensor.name == "Status Vendor"
        assert sensor.native_value == "0"

        attrs = sensor.extra_state_attributes
        assert attrs["description"] == "No Error"

    def test_status_vendor_temperature_error(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test status vendor sensor with temperature error."""
        mock_inverter_platform.decoded_model["I_Status_Vendor"] = 17

        sensor = StatusVendor(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value == "17"
        attrs = sensor.extra_state_attributes
        assert attrs["description"] == "Temperature Too High"

    def test_status_vendor_sunspec_not_impl_returns_none(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test status vendor returns None when not implemented."""
        mock_inverter_platform.decoded_model["I_Status_Vendor"] = SunSpecNotImpl.UINT16

        sensor = StatusVendor(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None


class TestSolarEdgeBatteryVoltage:
    """Tests for SolarEdgeBatteryVoltage sensor."""

    def test_battery_voltage(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery voltage sensor."""
        sensor = SolarEdgeBatteryVoltage(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.device_class == SensorDeviceClass.VOLTAGE
        assert sensor.native_unit_of_measurement == UnitOfElectricPotential.VOLT
        assert sensor.suggested_display_precision == 2
        assert sensor.native_value == 400.5

    def test_battery_voltage_sunspec_not_impl_returns_none(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery voltage returns None when not implemented."""
        # Set to FLOAT32 not impl
        import struct

        # SunSpecNotImpl.FLOAT32 = 0x7FC00000
        not_impl_float = struct.unpack("!f", bytes.fromhex("7FC00000"))[0]
        mock_battery_platform.decoded_model["B_DC_Voltage"] = not_impl_float

        sensor = SolarEdgeBatteryVoltage(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None

    def test_battery_voltage_out_of_range_returns_none(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery voltage returns None when out of valid range."""
        mock_battery_platform.decoded_model["B_DC_Voltage"] = 1500.0  # > Vmax

        sensor = SolarEdgeBatteryVoltage(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None

    def test_battery_voltage_when_status_off(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery voltage returns None when battery status is off."""
        mock_battery_platform.decoded_model["B_Status"] = 0  # Off

        sensor = SolarEdgeBatteryVoltage(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None


class TestSolarEdgeBatteryCurrent:
    """Tests for SolarEdgeBatteryCurrent sensor."""

    def test_battery_current(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery current sensor."""
        sensor = SolarEdgeBatteryCurrent(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.device_class == SensorDeviceClass.CURRENT
        assert sensor.native_unit_of_measurement == UnitOfElectricCurrent.AMPERE
        assert sensor.unique_id == "se_battery_1_dc_current"
        assert sensor.name == "DC Current"
        assert sensor.icon == "mdi:current-dc"
        assert sensor.suggested_display_precision == 2
        assert sensor.native_value == 10.5

    def test_battery_current_unavailable_when_not_impl(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery current unavailable when not implemented."""
        # Set to FLOAT32 not impl
        import struct

        # SunSpecNotImpl.FLOAT32 = 0x7FC00000
        not_impl_float = struct.unpack("!f", bytes.fromhex("7FC00000"))[0]
        mock_battery_platform.decoded_model["B_DC_Current"] = not_impl_float

        sensor = SolarEdgeBatteryCurrent(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.available is False

    def test_battery_current_unavailable_when_status_off(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery current unavailable when battery status is off."""
        mock_battery_platform.decoded_model["B_Status"] = 0  # Off

        sensor = SolarEdgeBatteryCurrent(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.available is False


class TestSolarEdgeBatteryPower:
    """Tests for SolarEdgeBatteryPower sensor."""

    def test_battery_power(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery power sensor."""
        sensor = SolarEdgeBatteryPower(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.device_class == SensorDeviceClass.POWER
        assert sensor.native_unit_of_measurement == UnitOfPower.WATT
        assert sensor.icon == "mdi:lightning-bolt"
        assert sensor.suggested_display_precision == 2
        assert sensor.native_value == 4200.0

    def test_battery_power_sunspec_not_impl_returns_none(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery power returns None when not implemented."""
        # Import float_to_hex from helpers to properly create FLOAT32 not impl
        # Use a special hex pattern that matches SunSpecNotImpl.FLOAT32
        import struct

        # SunSpecNotImpl.FLOAT32 = 0x7FC00000
        not_impl_float = struct.unpack("!f", bytes.fromhex("7FC00000"))[0]
        mock_battery_platform.decoded_model["B_DC_Power"] = not_impl_float

        sensor = SolarEdgeBatteryPower(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None

    def test_battery_power_when_status_off(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery power returns None when battery status is off."""
        mock_battery_platform.decoded_model["B_Status"] = 0  # Off

        sensor = SolarEdgeBatteryPower(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None


class TestSolarEdgeBatteryPowerInverted:
    """Tests for SolarEdgeBatteryPowerInverted sensor."""

    def test_battery_power_inverted(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery power inverted sensor."""
        sensor = SolarEdgeBatteryPowerInverted(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.unique_id == "se_battery_1_dc_power_inverted"
        assert sensor.name == "DC Power Inverted"
        # 4200.0 negated = -4200.0
        assert sensor.native_value == -4200.0

    def test_battery_power_inverted_none_value(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery power inverted returns None when base value is None."""
        mock_battery_platform.decoded_model["B_Status"] = 0  # Off

        sensor = SolarEdgeBatteryPowerInverted(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None


class TestSolarEdgeBatterySOE:
    """Tests for SolarEdgeBatterySOE (State of Energy) sensor."""

    def test_battery_soe(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery state of energy sensor."""
        sensor = SolarEdgeBatterySOE(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.device_class == SensorDeviceClass.BATTERY
        assert sensor.native_unit_of_measurement == PERCENTAGE
        assert sensor.unique_id == "se_battery_1_battery_soe"
        assert sensor.name == "State of Energy"
        assert sensor.suggested_display_precision == 0
        assert sensor.native_value == 75.0

    def test_battery_soe_sunspec_not_impl_returns_none(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery SOE returns None when not implemented."""
        # Set to FLOAT32 not impl
        import struct

        # SunSpecNotImpl.FLOAT32 = 0x7FC00000
        not_impl_float = struct.unpack("!f", bytes.fromhex("7FC00000"))[0]
        mock_battery_platform.decoded_model["B_SOE"] = not_impl_float

        sensor = SolarEdgeBatterySOE(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None

    def test_battery_soe_out_of_range_returns_none(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery SOE returns None when out of valid range."""
        mock_battery_platform.decoded_model["B_SOE"] = 150.0  # > 100%

        sensor = SolarEdgeBatterySOE(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None

    def test_battery_soe_negative_returns_none(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery SOE returns None when negative."""
        mock_battery_platform.decoded_model["B_SOE"] = -5.0

        sensor = SolarEdgeBatterySOE(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None


class TestSolarEdgeBatterySOH:
    """Tests for SolarEdgeBatterySOH (State of Health) sensor."""

    def test_battery_soh(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery state of health sensor."""
        sensor = SolarEdgeBatterySOH(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_unit_of_measurement == PERCENTAGE
        assert sensor.unique_id == "se_battery_1_battery_soh"
        assert sensor.name == "State of Health"
        assert sensor.icon == "mdi:battery-heart-outline"
        assert sensor.suggested_display_precision == 0
        assert sensor.native_value == 98.0

    def test_battery_soh_sunspec_not_impl_returns_none(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery SOH returns None when not implemented."""
        # Set to FLOAT32 not impl
        import struct

        # SunSpecNotImpl.FLOAT32 = 0x7FC00000
        not_impl_float = struct.unpack("!f", bytes.fromhex("7FC00000"))[0]
        mock_battery_platform.decoded_model["B_SOH"] = not_impl_float

        sensor = SolarEdgeBatterySOH(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None

    def test_battery_soh_out_of_range_returns_none(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery SOH returns None when out of valid range."""
        mock_battery_platform.decoded_model["B_SOH"] = 105.0  # > 100%

        sensor = SolarEdgeBatterySOH(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None


class TestSolarEdgeBatteryStatus:
    """Tests for SolarEdgeBatteryStatus sensor."""

    def test_battery_status_charge(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery status sensor with charge state."""
        sensor = SolarEdgeBatteryStatus(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.device_class == SensorDeviceClass.ENUM
        assert sensor.unique_id == "se_battery_1_status"
        assert sensor.name == "Status"
        assert sensor.options == list(BATTERY_STATUS.values())
        assert sensor.native_value == "B_STATUS_CHARGE"

        attrs = sensor.extra_state_attributes
        assert attrs["status_text"] == "Charge"
        assert attrs["status_value"] == 3

    def test_battery_status_discharge(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery status sensor with discharge state."""
        mock_battery_platform.decoded_model["B_Status"] = 4  # Discharge

        sensor = SolarEdgeBatteryStatus(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value == "B_STATUS_DISCHARGE"
        attrs = sensor.extra_state_attributes
        assert attrs["status_text"] == "Discharge"

    def test_battery_status_sunspec_not_impl_returns_none(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery status returns None when not implemented."""
        mock_battery_platform.decoded_model["B_Status"] = SunSpecNotImpl.UINT32

        sensor = SolarEdgeBatteryStatus(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None


class TestSunSpecNotImplHandling:
    """Tests for various SunSpec not implemented value handling."""

    @pytest.mark.parametrize(
        "sensor_class,platform_fixture,field_name,sunspec_value",
        [
            (
                ACCurrentSensor,
                "mock_inverter_platform",
                "AC_Current",
                SunSpecNotImpl.UINT16,
            ),
            (
                VoltageSensor,
                "mock_inverter_platform",
                "AC_Voltage_AB",
                SunSpecNotImpl.UINT16,
            ),
            (ACPower, "mock_inverter_platform", "AC_Power", SunSpecNotImpl.INT16),
            (
                DCCurrent,
                "mock_inverter_platform",
                "I_DC_Current",
                SunSpecNotImpl.UINT16,
            ),
            (
                DCVoltage,
                "mock_inverter_platform",
                "I_DC_Voltage",
                SunSpecNotImpl.UINT16,
            ),
            (DCPower, "mock_inverter_platform", "I_DC_Power", SunSpecNotImpl.INT16),
        ],
    )
    def test_sunspec_not_impl_values(
        self,
        sensor_class,
        platform_fixture,
        field_name,
        sunspec_value,
        mock_config_entry,
        mock_coordinator,
        request,
    ):
        """Test that various sensors handle SunSpec not implemented values correctly."""
        platform = request.getfixturevalue(platform_fixture)
        platform.decoded_model[field_name] = sunspec_value

        if sensor_class == VoltageSensor:
            sensor = sensor_class(
                platform, mock_config_entry, mock_coordinator, phase="AB"
            )
        else:
            sensor = sensor_class(platform, mock_config_entry, mock_coordinator)

        # DCCurrent uses available property instead of returning None
        if sensor_class == DCCurrent:
            assert sensor.available is False
        else:
            # Should return None for not implemented values
            assert sensor.native_value is None


class TestScaleFactorEdgeCases:
    """Tests for scale factor edge cases."""

    def test_scale_factor_boundary_min(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test scale factor at minimum boundary."""
        mock_inverter_platform.decoded_model["AC_Current_SF"] = -10  # Min value

        sensor = ACCurrentSensor(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        # Should still work at boundary
        assert sensor.native_value is not None
        assert sensor.suggested_display_precision == 10

    def test_scale_factor_boundary_max(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test scale factor at maximum boundary."""
        mock_inverter_platform.decoded_model["AC_Current_SF"] = 10  # Max value

        sensor = ACCurrentSensor(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        # Should still work at boundary; positive SF means whole numbers
        assert sensor.native_value is not None
        assert sensor.suggested_display_precision == 0

    def test_scale_factor_just_outside_range(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test scale factor just outside valid range."""
        mock_inverter_platform.decoded_model["AC_Current_SF"] = 11  # Just outside

        sensor = ACCurrentSensor(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        # Should return None when out of range
        assert sensor.native_value is None


class TestAsyncSetupEntry:
    """Tests for async_setup_entry function."""

    @pytest.mark.asyncio
    async def test_async_setup_entry_basic_inverter(self, hass: HomeAssistant):
        """Test async_setup_entry with basic inverter setup."""
        from custom_components.solaredge_modbus_multi.sensor import async_setup_entry

        # Create mock hub with one inverter
        mock_hub = MagicMock()
        mock_inverter = MagicMock()
        mock_inverter.decoded_model = {"C_SunSpec_DID": 101}
        mock_inverter.is_mmppt = False
        mock_hub.inverters = [mock_inverter]
        mock_hub.meters = []
        mock_hub.batteries = []
        mock_hub.option_detect_extras = False

        # Create mock coordinator
        mock_coordinator = MagicMock()
        mock_coordinator.async_add_listener = MagicMock()

        # Create mock config entry
        mock_config_entry = MagicMock()
        mock_config_entry.entry_id = "test_123"
        mock_config_entry.data = {"name": "Test"}

        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=mock_coordinator
        )

        # Track added entities
        added_entities = []

        def async_add_entities(entities):
            added_entities.extend(entities)

        # Call async_setup_entry
        await async_setup_entry(hass, mock_config_entry, async_add_entities)

        # Should have created basic inverter sensors (at least 15)
        assert len(added_entities) >= 15

    @pytest.mark.asyncio
    async def test_async_setup_entry_with_detect_extras(self, hass: HomeAssistant):
        """Test async_setup_entry with detect_extras enabled."""
        from custom_components.solaredge_modbus_multi.sensor import async_setup_entry

        # Create mock hub with detect_extras
        mock_hub = MagicMock()
        mock_inverter = MagicMock()
        mock_inverter.decoded_model = {"C_SunSpec_DID": 101}
        mock_inverter.is_mmppt = False
        mock_hub.inverters = [mock_inverter]
        mock_hub.meters = []
        mock_hub.batteries = []
        mock_hub.option_detect_extras = True

        mock_coordinator = MagicMock()
        mock_coordinator.async_add_listener = MagicMock()

        mock_config_entry = MagicMock()
        mock_config_entry.entry_id = "test_123"
        mock_config_entry.data = {"name": "Test"}

        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=mock_coordinator
        )

        added_entities = []

        def async_add_entities(entities):
            added_entities.extend(entities)

        await async_setup_entry(hass, mock_config_entry, async_add_entities)

        # Should have created more entities with detect_extras (at least 20)
        assert len(added_entities) >= 20

    @pytest.mark.asyncio
    async def test_async_setup_entry_with_mmppt(self, hass: HomeAssistant):
        """Test async_setup_entry with MMPPT inverter."""
        from custom_components.solaredge_modbus_multi.sensor import async_setup_entry

        # Create mock MMPPT unit
        mock_mmppt_unit = MagicMock()
        mock_mmppt_unit.unit = 1

        # Create mock hub with MMPPT inverter
        mock_hub = MagicMock()
        mock_inverter = MagicMock()
        mock_inverter.decoded_model = {"C_SunSpec_DID": 101}
        mock_inverter.is_mmppt = True
        mock_inverter.mmppt_units = [mock_mmppt_unit]
        mock_hub.inverters = [mock_inverter]
        mock_hub.meters = []
        mock_hub.batteries = []
        mock_hub.option_detect_extras = False

        mock_coordinator = MagicMock()
        mock_coordinator.async_add_listener = MagicMock()

        mock_config_entry = MagicMock()
        mock_config_entry.entry_id = "test_123"
        mock_config_entry.data = {"name": "Test"}

        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=mock_coordinator
        )

        added_entities = []

        def async_add_entities(entities):
            added_entities.extend(entities)

        await async_setup_entry(hass, mock_config_entry, async_add_entities)

        # Should have created MMPPT sensors (basic + MMPPT extras)
        assert len(added_entities) >= 20

    @pytest.mark.asyncio
    async def test_async_setup_entry_with_meter(self, hass: HomeAssistant):
        """Test async_setup_entry with meter."""
        from custom_components.solaredge_modbus_multi.sensor import async_setup_entry

        # Create mock meter
        mock_meter = MagicMock()
        mock_meter.decoded_model = {"C_SunSpec_DID": 203}

        # Create mock hub with meter
        mock_hub = MagicMock()
        mock_hub.inverters = []
        mock_hub.meters = [mock_meter]
        mock_hub.batteries = []
        mock_hub.option_detect_extras = False

        mock_coordinator = MagicMock()
        mock_coordinator.async_add_listener = MagicMock()

        mock_config_entry = MagicMock()
        mock_config_entry.entry_id = "test_123"
        mock_config_entry.data = {"name": "Test"}

        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=mock_coordinator
        )

        added_entities = []

        def async_add_entities(entities):
            added_entities.extend(entities)

        await async_setup_entry(hass, mock_config_entry, async_add_entities)

        # Meters create many sensors (at least 50)
        assert len(added_entities) >= 50

    @pytest.mark.asyncio
    async def test_async_setup_entry_with_battery(self, hass: HomeAssistant):
        """Test async_setup_entry with battery."""
        from custom_components.solaredge_modbus_multi.sensor import async_setup_entry

        # Create mock battery
        mock_battery = MagicMock()

        # Create mock hub with battery
        mock_hub = MagicMock()
        mock_hub.inverters = []
        mock_hub.meters = []
        mock_hub.batteries = [mock_battery]
        mock_hub.option_detect_extras = False

        mock_coordinator = MagicMock()
        mock_coordinator.async_add_listener = MagicMock()

        mock_config_entry = MagicMock()
        mock_config_entry.entry_id = "test_123"
        mock_config_entry.data = {"name": "Test"}

        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=mock_coordinator
        )

        added_entities = []

        def async_add_entities(entities):
            added_entities.extend(entities)

        await async_setup_entry(hass, mock_config_entry, async_add_entities)

        # Batteries create many sensors (at least 15)
        assert len(added_entities) >= 15


@pytest.fixture
def mock_mmppt_platform():
    """Create a mock MMPPT unit platform."""
    platform = MagicMock()
    platform.unit = 1
    platform.mmppt_key = "mmppt_1"
    platform.device_info = {
        "identifiers": {("solaredge_modbus_multi", "se_inv_1_mmppt_1")},
        "name": "MMPPT Unit 1",
    }
    platform.online = True

    # Mock inverter reference
    platform.inverter = MagicMock()
    platform.inverter.uid_base = "se_inv_1"
    platform.inverter.decoded_model = {
        "mmppt_1": {
            "DCA": 150,  # Current
            "DCV": 6000,  # Voltage
            "DCW": 9000,  # Power
            "Tmp": 45,  # Temperature
        },
        "mmppt_DCA_SF": -2,
        "mmppt_DCV_SF": -1,
        "mmppt_DCW_SF": -1,
        "mmppt_Events": 0x0,
        "mmppt_DID": 160,
        "mmppt_Units": 4,
    }
    platform.inverter.decoded_mmppt = {
        "mmppt_DID": 160,
        "mmppt_Units": 4,
    }

    return platform


@pytest.fixture
def mock_inverter_with_power_control():
    """Create a mock inverter with power control enabled."""
    platform = MagicMock()
    platform.uid_base = "se_inv_1"
    platform.device_info = {
        "identifiers": {("solaredge_modbus_multi", "se_inv_1")},
        "name": "SolarEdge Inverter 1",
    }
    platform.online = True
    platform.global_power_control = True
    platform.advanced_power_control = True

    platform.decoded_model = {
        "C_SunSpec_DID": 101,
        "I_RRCR": 0b0101,  # Multiple inputs active
        "I_Power_Limit": 80,  # 80%
        "I_CosPhi": 0.95,
        "CommitPwrCtlSettings": 0x0,  # Success
        "RestorePwrCtlDefaults": 0x0,  # Success
    }

    return platform


class TestMMPPTSensors:
    """Tests for MMPPT sensors."""

    def test_dc_current_mmppt(
        self, mock_mmppt_platform, mock_config_entry, mock_coordinator
    ):
        """Test MMPPT DC current sensor."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeDCCurrentMMPPT,
        )

        sensor = SolarEdgeDCCurrentMMPPT(
            mock_mmppt_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.device_class == SensorDeviceClass.CURRENT
        assert sensor.native_unit_of_measurement == UnitOfElectricCurrent.AMPERE
        assert sensor.unique_id == "se_inv_1_dc_current_mmppt1"
        assert sensor.name == "DC Current"
        assert sensor.icon == "mdi:current-dc"
        # 150 * 10^-2 = 1.5
        assert sensor.native_value == 1.5
        assert sensor.suggested_display_precision == 2

    def test_dc_current_mmppt_unavailable(
        self, mock_mmppt_platform, mock_config_entry, mock_coordinator
    ):
        """Test MMPPT DC current sensor unavailable when not impl."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeDCCurrentMMPPT,
        )

        mock_mmppt_platform.inverter.decoded_model["mmppt_1"]["DCA"] = (
            SunSpecNotImpl.INT16
        )

        sensor = SolarEdgeDCCurrentMMPPT(
            mock_mmppt_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.available is False

    def test_dc_voltage_mmppt(
        self, mock_mmppt_platform, mock_config_entry, mock_coordinator
    ):
        """Test MMPPT DC voltage sensor."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeDCVoltageMMPPT,
        )

        sensor = SolarEdgeDCVoltageMMPPT(
            mock_mmppt_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.device_class == SensorDeviceClass.VOLTAGE
        assert sensor.native_unit_of_measurement == UnitOfElectricPotential.VOLT
        assert sensor.unique_id == "se_inv_1_dc_voltage_mmppt1"
        assert sensor.name == "DC Voltage"
        # 6000 * 10^-1 = 600.0
        assert sensor.native_value == 600.0
        assert sensor.suggested_display_precision == 1

    def test_dc_voltage_mmppt_unavailable(
        self, mock_mmppt_platform, mock_config_entry, mock_coordinator
    ):
        """Test MMPPT DC voltage sensor unavailable when SF invalid."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeDCVoltageMMPPT,
        )

        mock_mmppt_platform.inverter.decoded_model["mmppt_DCV_SF"] = (
            SunSpecNotImpl.INT16
        )

        sensor = SolarEdgeDCVoltageMMPPT(
            mock_mmppt_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.available is False

    def test_dc_power_mmppt(
        self, mock_mmppt_platform, mock_config_entry, mock_coordinator
    ):
        """Test MMPPT DC power sensor."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeDCPowerMMPPT,
        )

        sensor = SolarEdgeDCPowerMMPPT(
            mock_mmppt_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.device_class == SensorDeviceClass.POWER
        assert sensor.native_unit_of_measurement == UnitOfPower.WATT
        assert sensor.unique_id == "se_inv_1_dc_power_mmppt1"
        assert sensor.name == "DC Power"
        assert sensor.icon == "mdi:solar-power"
        # 9000 * 10^-1 = 900.0
        assert sensor.native_value == 900.0
        assert sensor.suggested_display_precision == 1

    def test_dc_power_mmppt_unavailable(
        self, mock_mmppt_platform, mock_config_entry, mock_coordinator
    ):
        """Test MMPPT DC power sensor unavailable when value not impl."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeDCPowerMMPPT,
        )

        mock_mmppt_platform.inverter.decoded_model["mmppt_1"]["DCW"] = (
            SunSpecNotImpl.INT16
        )

        sensor = SolarEdgeDCPowerMMPPT(
            mock_mmppt_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.available is False

    def test_temperature_mmppt(
        self, mock_mmppt_platform, mock_config_entry, mock_coordinator
    ):
        """Test MMPPT temperature sensor."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeTemperatureMMPPT,
        )

        sensor = SolarEdgeTemperatureMMPPT(
            mock_mmppt_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.device_class == SensorDeviceClass.TEMPERATURE
        assert sensor.native_unit_of_measurement == UnitOfTemperature.CELSIUS
        assert sensor.unique_id == "se_inv_1_tmp_mmppt1"
        assert sensor.name == "Temperature"
        assert sensor.entity_category == EntityCategory.DIAGNOSTIC
        assert sensor.suggested_display_precision == 0
        assert sensor.native_value == 45

    def test_temperature_mmppt_unavailable(
        self, mock_mmppt_platform, mock_config_entry, mock_coordinator
    ):
        """Test MMPPT temperature sensor unavailable when not impl."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeTemperatureMMPPT,
        )

        mock_mmppt_platform.inverter.decoded_model["mmppt_1"]["Tmp"] = (
            SunSpecNotImpl.INT16
        )

        sensor = SolarEdgeTemperatureMMPPT(
            mock_mmppt_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.available is False

    def test_mmppt_events(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test MMPPT events sensor."""
        from custom_components.solaredge_modbus_multi.sensor import SolarEdgeMMPPTEvents

        mock_inverter_platform.decoded_model["mmppt_Events"] = 0x0

        sensor = SolarEdgeMMPPTEvents(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.unique_id == "se_inv_1_mmppt_events"
        assert sensor.name == "MMPPT Events"
        assert sensor.native_value == 0x0

        attrs = sensor.extra_state_attributes
        assert "events" in attrs
        assert "bits" in attrs

    def test_mmppt_events_unavailable(
        self, mock_inverter_platform, mock_config_entry, mock_coordinator
    ):
        """Test MMPPT events sensor unavailable when not impl."""
        from custom_components.solaredge_modbus_multi.sensor import SolarEdgeMMPPTEvents

        mock_inverter_platform.decoded_model["mmppt_Events"] = SunSpecNotImpl.UINT32

        sensor = SolarEdgeMMPPTEvents(
            mock_inverter_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.available is False


class TestPowerControlSensors:
    """Tests for power control sensors (RRCR, ActivePowerLimit, CosPhi)."""

    def test_rrcr_sensor(
        self, mock_inverter_with_power_control, mock_config_entry, mock_coordinator
    ):
        """Test RRCR status sensor."""
        from custom_components.solaredge_modbus_multi.sensor import SolarEdgeRRCR

        sensor = SolarEdgeRRCR(
            mock_inverter_with_power_control, mock_config_entry, mock_coordinator
        )

        assert sensor.unique_id == "se_inv_1_rrcr"
        assert sensor.name == "RRCR Status"
        assert sensor.available is True
        assert sensor.entity_registry_enabled_default is True
        assert sensor.native_value == 0b0101

        attrs = sensor.extra_state_attributes
        assert "inputs" in attrs

    def test_rrcr_sensor_not_impl(
        self, mock_inverter_with_power_control, mock_config_entry, mock_coordinator
    ):
        """Test RRCR sensor returns None when not impl."""
        from custom_components.solaredge_modbus_multi.sensor import SolarEdgeRRCR

        mock_inverter_with_power_control.decoded_model["I_RRCR"] = SunSpecNotImpl.UINT16

        sensor = SolarEdgeRRCR(
            mock_inverter_with_power_control, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None

    def test_rrcr_sensor_zero(
        self, mock_inverter_with_power_control, mock_config_entry, mock_coordinator
    ):
        """Test RRCR sensor with zero value (no inputs active)."""
        from custom_components.solaredge_modbus_multi.sensor import SolarEdgeRRCR

        mock_inverter_with_power_control.decoded_model["I_RRCR"] = 0x0

        sensor = SolarEdgeRRCR(
            mock_inverter_with_power_control, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value == 0x0
        attrs = sensor.extra_state_attributes
        assert attrs["inputs"] == "[]"

    def test_active_power_limit_sensor(
        self, mock_inverter_with_power_control, mock_config_entry, mock_coordinator
    ):
        """Test Active Power Limit sensor."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeActivePowerLimit,
        )

        sensor = SolarEdgeActivePowerLimit(
            mock_inverter_with_power_control, mock_config_entry, mock_coordinator
        )

        assert sensor.unique_id == "se_inv_1_active_power_limit"
        assert sensor.name == "Active Power Limit"
        assert sensor.native_unit_of_measurement == PERCENTAGE
        assert sensor.suggested_display_precision == 0
        assert sensor.icon == "mdi:percent"
        assert sensor.available is True
        assert sensor.entity_registry_enabled_default is True
        assert sensor.native_value == 80

    def test_active_power_limit_not_impl(
        self, mock_inverter_with_power_control, mock_config_entry, mock_coordinator
    ):
        """Test Active Power Limit returns None when not impl."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeActivePowerLimit,
        )

        mock_inverter_with_power_control.decoded_model["I_Power_Limit"] = (
            SunSpecNotImpl.UINT16
        )

        sensor = SolarEdgeActivePowerLimit(
            mock_inverter_with_power_control, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None

    def test_active_power_limit_out_of_range(
        self, mock_inverter_with_power_control, mock_config_entry, mock_coordinator
    ):
        """Test Active Power Limit returns None when out of range."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeActivePowerLimit,
        )

        mock_inverter_with_power_control.decoded_model["I_Power_Limit"] = 150  # > 100

        sensor = SolarEdgeActivePowerLimit(
            mock_inverter_with_power_control, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None

    def test_cosphi_sensor(
        self, mock_inverter_with_power_control, mock_config_entry, mock_coordinator
    ):
        """Test CosPhi sensor."""
        from custom_components.solaredge_modbus_multi.sensor import SolarEdgeCosPhi

        sensor = SolarEdgeCosPhi(
            mock_inverter_with_power_control, mock_config_entry, mock_coordinator
        )

        assert sensor.unique_id == "se_inv_1_cosphi"
        assert sensor.name == "CosPhi"
        assert sensor.suggested_display_precision == 1
        assert sensor.icon == "mdi:angle-acute"
        assert sensor.available is True
        assert sensor.entity_registry_enabled_default is True
        assert sensor.native_value == 0.9  # Rounded from 0.95

    def test_cosphi_not_impl(
        self, mock_inverter_with_power_control, mock_config_entry, mock_coordinator
    ):
        """Test CosPhi returns None when not impl."""
        import struct

        from custom_components.solaredge_modbus_multi.sensor import SolarEdgeCosPhi

        # Set to FLOAT32 not impl
        not_impl_float = struct.unpack("!f", bytes.fromhex("7FC00000"))[0]
        mock_inverter_with_power_control.decoded_model["I_CosPhi"] = not_impl_float

        sensor = SolarEdgeCosPhi(
            mock_inverter_with_power_control, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None

    def test_cosphi_out_of_range(
        self, mock_inverter_with_power_control, mock_config_entry, mock_coordinator
    ):
        """Test CosPhi returns None when out of range."""
        from custom_components.solaredge_modbus_multi.sensor import SolarEdgeCosPhi

        mock_inverter_with_power_control.decoded_model["I_CosPhi"] = 1.5  # > 1.0

        sensor = SolarEdgeCosPhi(
            mock_inverter_with_power_control, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None

    def test_commit_control_settings(
        self, mock_inverter_with_power_control, mock_config_entry, mock_coordinator
    ):
        """Test Commit Control Settings sensor."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeCommitControlSettings,
        )

        sensor = SolarEdgeCommitControlSettings(
            mock_inverter_with_power_control, mock_config_entry, mock_coordinator
        )

        assert sensor.unique_id == "se_inv_1_commit_pwr_settings"
        assert sensor.name == "Commit Power Settings"
        assert sensor.icon == "mdi:content-save-cog-outline"
        assert sensor.available is True
        assert sensor.native_value == 0x0

        attrs = sensor.extra_state_attributes
        assert attrs["hex_value"] == "0x0"
        assert attrs["status"] == "SUCCESS"

    def test_commit_control_settings_error(
        self, mock_inverter_with_power_control, mock_config_entry, mock_coordinator
    ):
        """Test Commit Control Settings sensor with error."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeCommitControlSettings,
        )

        mock_inverter_with_power_control.decoded_model["CommitPwrCtlSettings"] = 0x1

        sensor = SolarEdgeCommitControlSettings(
            mock_inverter_with_power_control, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value == 0x1
        attrs = sensor.extra_state_attributes
        assert attrs["status"] == "INTERNAL_ERROR"

    def test_default_control_settings(
        self, mock_inverter_with_power_control, mock_config_entry, mock_coordinator
    ):
        """Test Default Control Settings sensor."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeDefaultControlSettings,
        )

        sensor = SolarEdgeDefaultControlSettings(
            mock_inverter_with_power_control, mock_config_entry, mock_coordinator
        )

        assert sensor.unique_id == "se_inv_1_default_pwr_settings"
        assert sensor.name == "Default Power Settings"
        assert sensor.icon == "mdi:restore-alert"
        assert sensor.available is True
        assert sensor.native_value == 0x0

        attrs = sensor.extra_state_attributes
        assert attrs["hex_value"] == "0x0"
        assert attrs["status"] == "SUCCESS"

    def test_default_control_settings_error(
        self, mock_inverter_with_power_control, mock_config_entry, mock_coordinator
    ):
        """Test Default Control Settings sensor with error."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeDefaultControlSettings,
        )

        mock_inverter_with_power_control.decoded_model["RestorePwrCtlDefaults"] = 0xFFFF

        sensor = SolarEdgeDefaultControlSettings(
            mock_inverter_with_power_control, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value == 0xFFFF
        attrs = sensor.extra_state_attributes
        assert attrs["status"] == "ERROR"


class TestMeterEvents:
    """Tests for meter event sensors."""

    def test_meter_events_no_events(
        self, mock_meter_platform_did201, mock_config_entry, mock_coordinator
    ):
        """Test meter events sensor with no events."""
        from custom_components.solaredge_modbus_multi.sensor import MeterEvents

        mock_meter_platform_did201.decoded_model["M_Events"] = 0x0

        sensor = MeterEvents(
            mock_meter_platform_did201, mock_config_entry, mock_coordinator
        )

        assert sensor.unique_id == "se_meter_1_meter_events"
        assert sensor.name == "Meter Events"
        assert sensor.native_value == 0x0

        attrs = sensor.extra_state_attributes
        assert "events" in attrs
        assert "bits" in attrs
        assert attrs["bits"] == "00000000000000000000000000000000"

    def test_meter_events_with_events(
        self, mock_meter_platform_did201, mock_config_entry, mock_coordinator
    ):
        """Test meter events sensor with active events."""
        from custom_components.solaredge_modbus_multi.sensor import MeterEvents

        mock_meter_platform_did201.decoded_model["M_Events"] = 0b100  # Bit 2

        sensor = MeterEvents(
            mock_meter_platform_did201, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value == 0b100
        attrs = sensor.extra_state_attributes
        assert "events" in attrs

    def test_meter_events_not_impl(
        self, mock_meter_platform_did201, mock_config_entry, mock_coordinator
    ):
        """Test meter events returns None when not impl."""
        from custom_components.solaredge_modbus_multi.sensor import MeterEvents

        mock_meter_platform_did201.decoded_model["M_Events"] = SunSpecNotImpl.UINT32

        sensor = MeterEvents(
            mock_meter_platform_did201, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None


@pytest.fixture
def mock_meter_with_energy():
    """Create a mock meter platform with energy data."""
    platform = MagicMock()
    platform.uid_base = "se_meter_1"
    platform.device_info = {
        "identifiers": {("solaredge_modbus_multi", "se_meter_1")},
        "name": "SolarEdge Meter 1",
    }
    platform.online = True

    platform.decoded_model = {
        "C_SunSpec_DID": 203,
        "M_VAh_Exported": 100000,
        "M_VAh_Exported_A": 33000,
        "M_VAh_Imported": 50000,
        "M_VAh_SF": 0,
        "M_varh_Import_Q1": 20000,
        "M_varh_Import_Q1_A": 6000,
        "M_varh_Import_Q2": 15000,
        "M_varh_Export_Q3": 10000,
        "M_varh_Export_Q4": 5000,
        "M_varh_SF": 0,
    }

    return platform


class TestMeterEnergySensors:
    """Tests for meter energy sensors (VAh and varh)."""

    def test_meter_vah_exported(
        self, mock_meter_with_energy, mock_config_entry, mock_coordinator
    ):
        """Test meter VAh exported sensor."""
        from custom_components.solaredge_modbus_multi.const import (
            ENERGY_VOLT_AMPERE_HOUR,
        )
        from custom_components.solaredge_modbus_multi.sensor import MeterVAhIE

        sensor = MeterVAhIE(
            mock_meter_with_energy,
            mock_config_entry,
            mock_coordinator,
            phase="Exported",
        )

        assert sensor.device_class is None
        assert sensor.native_unit_of_measurement == ENERGY_VOLT_AMPERE_HOUR
        assert sensor.unique_id == "se_meter_1_exported_vah"
        assert sensor.name == "Apparent Energy Exported"
        assert sensor.entity_registry_enabled_default is False
        assert sensor.icon == "mdi:transmission-tower-import"

    def test_meter_vah_imported(
        self, mock_meter_with_energy, mock_config_entry, mock_coordinator
    ):
        """Test meter VAh imported sensor."""
        from custom_components.solaredge_modbus_multi.sensor import MeterVAhIE

        sensor = MeterVAhIE(
            mock_meter_with_energy,
            mock_config_entry,
            mock_coordinator,
            phase="Imported",
        )

        assert sensor.unique_id == "se_meter_1_imported_vah"
        assert sensor.name == "Apparent Energy Imported"
        assert sensor.icon == "mdi:transmission-tower-export"

    def test_meter_vah_not_impl(
        self, mock_meter_with_energy, mock_config_entry, mock_coordinator
    ):
        """Test meter VAh returns None when not impl."""
        from custom_components.solaredge_modbus_multi.const import SunSpecAccum
        from custom_components.solaredge_modbus_multi.sensor import MeterVAhIE

        mock_meter_with_energy.decoded_model["M_VAh_Exported"] = SunSpecAccum.NA32

        sensor = MeterVAhIE(
            mock_meter_with_energy,
            mock_config_entry,
            mock_coordinator,
            phase="Exported",
        )

        assert sensor.native_value is None

    def test_meter_varh_import_q1(
        self, mock_meter_with_energy, mock_config_entry, mock_coordinator
    ):
        """Test meter varh import Q1 sensor."""
        from custom_components.solaredge_modbus_multi.const import (
            ENERGY_VOLT_AMPERE_REACTIVE_HOUR,
        )
        from custom_components.solaredge_modbus_multi.sensor import MetervarhIE

        sensor = MetervarhIE(
            mock_meter_with_energy,
            mock_config_entry,
            mock_coordinator,
            phase="Import_Q1",
        )

        assert sensor.device_class is None
        assert sensor.native_unit_of_measurement == ENERGY_VOLT_AMPERE_REACTIVE_HOUR
        assert sensor.unique_id == "se_meter_1_import_q1_varh"
        assert sensor.name == "Reactive Energy Import Q1"
        assert sensor.entity_registry_enabled_default is False
        assert sensor.icon == "mdi:transmission-tower-export"

    def test_meter_varh_export_q3(
        self, mock_meter_with_energy, mock_config_entry, mock_coordinator
    ):
        """Test meter varh export Q3 sensor."""
        from custom_components.solaredge_modbus_multi.sensor import MetervarhIE

        sensor = MetervarhIE(
            mock_meter_with_energy,
            mock_config_entry,
            mock_coordinator,
            phase="Export_Q3",
        )

        assert sensor.unique_id == "se_meter_1_export_q3_varh"
        assert sensor.name == "Reactive Energy Export Q3"
        assert sensor.icon == "mdi:transmission-tower-import"

    def test_meter_varh_not_impl(
        self, mock_meter_with_energy, mock_config_entry, mock_coordinator
    ):
        """Test meter varh returns None when not impl."""
        from custom_components.solaredge_modbus_multi.const import SunSpecAccum
        from custom_components.solaredge_modbus_multi.sensor import MetervarhIE

        mock_meter_with_energy.decoded_model["M_varh_Import_Q1"] = SunSpecAccum.NA32

        sensor = MetervarhIE(
            mock_meter_with_energy,
            mock_config_entry,
            mock_coordinator,
            phase="Import_Q1",
        )

        assert sensor.native_value is None


class TestBatteryEnergySensors:
    """Tests for battery energy sensors."""

    def test_battery_energy_export(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery energy export sensor."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeBatteryEnergyExport,
        )

        sensor = SolarEdgeBatteryEnergyExport(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.device_class == SensorDeviceClass.ENERGY
        assert sensor.unique_id == "se_battery_1_energy_export"
        assert sensor.name == "Energy Export"
        assert sensor.icon == "mdi:battery-charging-20"
        assert sensor.native_value == 50000

    def test_battery_energy_export_backwards(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery energy export sensor when value goes backwards."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeBatteryEnergyExport,
        )

        sensor = SolarEdgeBatteryEnergyExport(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        # First read
        assert sensor.native_value == 50000

        # Value goes backwards
        mock_battery_platform.decoded_model["B_Export_Energy_WH"] = 40000

        # Should return None and log warning
        assert sensor.native_value is None

    def test_battery_energy_export_with_reset_allowed(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery energy export with reset allowed."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeBatteryEnergyExport,
        )

        mock_battery_platform.allow_battery_energy_reset = True
        mock_battery_platform.battery_energy_reset_cycles = 2

        sensor = SolarEdgeBatteryEnergyExport(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        # First read
        assert sensor.native_value == 50000

        # Value goes backwards once
        mock_battery_platform.decoded_model["B_Export_Energy_WH"] = 40000
        assert sensor.native_value is None  # Cycle 1

        # Still backwards
        assert sensor.native_value is None  # Cycle 2

        # Third time should reset
        assert sensor.native_value is None  # Cycle 3, triggers reset

    def test_battery_energy_import(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery energy import sensor."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeBatteryEnergyImport,
        )

        sensor = SolarEdgeBatteryEnergyImport(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.device_class == SensorDeviceClass.ENERGY
        assert sensor.unique_id == "se_battery_1_energy_import"
        assert sensor.name == "Energy Import"
        assert sensor.icon == "mdi:battery-charging-100"
        assert sensor.native_value == 60000

    def test_battery_max_energy(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery max energy sensor."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeBatteryMaxEnergy,
        )

        sensor = SolarEdgeBatteryMaxEnergy(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.device_class == SensorDeviceClass.ENERGY_STORAGE
        assert sensor.unique_id == "se_battery_1_max_energy"
        assert sensor.name == "Maximum Energy"
        assert sensor.native_value == 10000.0

    def test_battery_max_energy_out_of_range(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery max energy returns None when out of range."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeBatteryMaxEnergy,
        )

        # Set higher than rated energy
        mock_battery_platform.decoded_model["B_Energy_Max"] = 15000.0

        sensor = SolarEdgeBatteryMaxEnergy(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None

    def test_battery_available_energy(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery available energy sensor."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeBatteryAvailableEnergy,
        )

        sensor = SolarEdgeBatteryAvailableEnergy(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.device_class == SensorDeviceClass.ENERGY_STORAGE
        assert sensor.unique_id == "se_battery_1_avail_energy"
        assert sensor.name == "Available Energy"
        assert sensor.native_value == 7500.0

    def test_battery_available_energy_exceeds_rated(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery available energy when exceeds rated energy."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeBatteryAvailableEnergy,
        )

        # Set higher than rated energy
        mock_battery_platform.decoded_model["B_Energy_Available"] = 15000.0

        sensor = SolarEdgeBatteryAvailableEnergy(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        # Should return None and log warning (first time)
        assert sensor.native_value is None


class TestBatteryPowerSensors:
    """Tests for battery power sensors."""

    def test_battery_max_charge_power(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery max charge power sensor."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeBatteryMaxChargePower,
        )

        sensor = SolarEdgeBatteryMaxChargePower(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.device_class == SensorDeviceClass.POWER
        assert sensor.unique_id == "se_battery_1_max_charge_power"
        assert sensor.name == "Max Charge Power"
        assert sensor.available is True
        assert sensor.native_value == 5000.0

    def test_battery_max_charge_power_unavailable(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery max charge power unavailable when not impl."""
        import struct

        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeBatteryMaxChargePower,
        )

        not_impl_float = struct.unpack("!f", bytes.fromhex("7FC00000"))[0]
        mock_battery_platform.decoded_model["B_MaxChargePower"] = not_impl_float

        sensor = SolarEdgeBatteryMaxChargePower(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.available is False

    def test_battery_max_charge_peak_power(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery max charge peak power sensor."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeBatteryMaxChargePeakPower,
        )

        sensor = SolarEdgeBatteryMaxChargePeakPower(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.unique_id == "se_battery_1_max_charge_peak_power"
        assert sensor.name == "Peak Charge Power"
        assert sensor.native_value == 6000.0

    def test_battery_max_discharge_power(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery max discharge power sensor."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeBatteryMaxDischargePower,
        )

        sensor = SolarEdgeBatteryMaxDischargePower(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.unique_id == "se_battery_1_max_discharge_power"
        assert sensor.name == "Max Discharge Power"
        assert sensor.native_value == 5000.0

    def test_battery_max_discharge_peak_power(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery max discharge peak power sensor."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeBatteryMaxDischargePeakPower,
        )

        sensor = SolarEdgeBatteryMaxDischargePeakPower(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.unique_id == "se_battery_1_max_discharge_peak_power"
        assert sensor.name == "Peak Discharge Power"
        assert sensor.native_value == 6000.0


class TestBatteryTemperatureSensors:
    """Tests for battery temperature sensors."""

    def test_battery_avg_temp(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery average temperature sensor."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeBatteryAvgTemp,
        )

        sensor = SolarEdgeBatteryAvgTemp(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.device_class == SensorDeviceClass.TEMPERATURE
        assert sensor.unique_id == "se_battery_1_avg_temp"
        assert sensor.name == "Average Temperature"
        assert sensor.suggested_display_precision == 1
        assert sensor.native_value == 25.5

    def test_battery_avg_temp_out_of_range(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery avg temp returns None when out of range."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeBatteryAvgTemp,
        )

        mock_battery_platform.decoded_model["B_Temp_Average"] = -50.0  # Below Tmin

        sensor = SolarEdgeBatteryAvgTemp(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.native_value is None

    def test_battery_max_temp(
        self, mock_battery_platform, mock_config_entry, mock_coordinator
    ):
        """Test battery max temperature sensor."""
        from custom_components.solaredge_modbus_multi.sensor import (
            SolarEdgeBatteryMaxTemp,
        )

        sensor = SolarEdgeBatteryMaxTemp(
            mock_battery_platform, mock_config_entry, mock_coordinator
        )

        assert sensor.unique_id == "se_battery_1_max_temp"
        assert sensor.name == "Max Temperature"
        assert sensor.entity_registry_enabled_default is False
        assert sensor.native_value == 27.0
