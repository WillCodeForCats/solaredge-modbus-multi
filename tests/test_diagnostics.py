"""Tests for the SolarEdge Modbus Multi diagnostics module."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solaredge_modbus_multi.const import DOMAIN, PollGroup
from custom_components.solaredge_modbus_multi.diagnostics import (
    REDACT_BATTERY,
    REDACT_CONFIG,
    REDACT_INVERTER,
    REDACT_METER,
    async_get_config_entry_diagnostics,
    format_values,
)
from custom_components.solaredge_modbus_multi.modbus_transport import PollStats


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield


class TestFormatValues:
    """Test format_values function."""

    def test_format_int_dictionary(self):
        """Test formatting dictionary with integer values."""
        input_dict = {"value1": 100, "value2": 255, "value3": 0}
        result = format_values(input_dict)

        assert result == {"value1": "0x64", "value2": "0xff", "value3": "0x0"}

    def test_format_float_dictionary(self):
        """Test formatting dictionary with float values."""
        input_dict = {"temp": 25.5, "voltage": 240.0, "power": 5000.75}
        result = format_values(input_dict)

        # float_to_hex converts floats to hex representation
        assert isinstance(result["temp"], str)
        assert result["temp"].startswith("0x")
        assert isinstance(result["voltage"], str)
        assert result["voltage"].startswith("0x")
        assert isinstance(result["power"], str)
        assert result["power"].startswith("0x")

    def test_format_mixed_types_dictionary(self):
        """Test formatting dictionary with mixed types."""
        input_dict = {
            "int_value": 42,
            "float_value": 3.14,
            "string_value": "test",
            "bool_value": True,
            "none_value": None,
        }
        result = format_values(input_dict)

        assert result["int_value"] == "0x2a"
        assert result["float_value"].startswith("0x")
        assert result["string_value"] == "test"
        # Boolean True is treated as int 1 in Python, so it becomes "0x1"
        assert result["bool_value"] == "0x1"
        assert result["none_value"] is None

    def test_format_nested_dictionary(self):
        """Test formatting nested dictionary structures."""
        input_dict = {
            "level1": {"level2": {"level3": {"value": 100}}},
            "another_key": 200,
        }
        result = format_values(input_dict)

        assert result["level1"]["level2"]["level3"]["value"] == "0x64"
        assert result["another_key"] == "0xc8"

    def test_format_complex_nested_structure(self):
        """Test formatting complex nested structure with mixed types."""
        input_dict = {
            "inverter": {
                "status": 4,
                "power": 5000.5,
                "voltage": {"ac": 240.0, "dc": 400},
            },
            "meter": {"id": 1, "name": "Main Meter"},
        }
        result = format_values(input_dict)

        assert result["inverter"]["status"] == "0x4"
        assert result["inverter"]["power"].startswith("0x")
        assert result["inverter"]["voltage"]["ac"].startswith("0x")
        assert result["inverter"]["voltage"]["dc"] == "0x190"
        assert result["meter"]["id"] == "0x1"
        assert result["meter"]["name"] == "Main Meter"

    def test_format_empty_dictionary(self):
        """Test formatting empty dictionary."""
        result = format_values({})
        assert result == {}

    def test_format_non_dictionary_input(self):
        """Test that non-dictionary input is returned unchanged."""
        # String
        assert format_values("test") == "test"

        # Integer
        assert format_values(42) == 42

        # Float
        assert format_values(3.14) == 3.14

        # None
        assert format_values(None) is None

        # List
        assert format_values([1, 2, 3]) == [1, 2, 3]

    def test_format_dictionary_with_zero_values(self):
        """Test formatting dictionary with zero values."""
        input_dict = {"zero_int": 0, "zero_float": 0.0}
        result = format_values(input_dict)

        assert result["zero_int"] == "0x0"
        assert result["zero_float"].startswith("0x")

    def test_format_dictionary_with_negative_values(self):
        """Test formatting dictionary with negative integer values."""
        input_dict = {"negative": -1, "positive": 1}
        result = format_values(input_dict)

        # Negative integers should still be converted to hex
        assert isinstance(result["negative"], str)
        assert result["negative"].startswith("-0x") or result["negative"].startswith(
            "0x"
        )
        assert result["positive"] == "0x1"

    def test_format_deeply_nested_structure(self):
        """Test formatting very deeply nested structure."""
        input_dict = {
            "l1": {
                "l2": {
                    "l3": {"l4": {"l5": {"value": 999, "temp": 45.5}}},
                    "another": 100,
                }
            }
        }
        result = format_values(input_dict)

        assert result["l1"]["l2"]["l3"]["l4"]["l5"]["value"] == "0x3e7"
        assert result["l1"]["l2"]["l3"]["l4"]["l5"]["temp"].startswith("0x")
        assert result["l1"]["l2"]["another"] == "0x64"


@pytest.fixture
def mock_hub():
    """Create a mock SolarEdgeModbusMultiHub."""
    hub = MagicMock()
    hub.pymodbus_version = "3.8.3"
    hub.option_allow_hardware_writes = False
    hub.inverters = []
    hub.meters = []
    hub.batteries = []
    # A real PollStats, not an auto-mock: diagnostics serializes the whole
    # dataclass, and a mock standing in for it hides field-level drift.
    hub.transport_stats = PollStats()
    return hub


@pytest.fixture
def mock_inverter():
    """Create a mock SolarEdgeInverter."""
    inverter = MagicMock()
    inverter.inverter_unit_id = 1
    inverter.device_info = {
        "identifiers": {(DOMAIN, "inv_123456789")},
        "name": "SolarEdge Inverter 1",
        "manufacturer": "SolarEdge",
        "model": "SE10K",
        "sw_version": "1.0.0",
    }
    inverter.global_power_control = False
    inverter.advanced_power_control = False
    inverter.site_limit_control = False
    inverter.decoded_common = {
        "C_Manufacturer": "SolarEdge",
        "C_Model": "SE10K",
        "C_Version": "1.0.0",
        "C_SerialNumber": "123456789",
        "C_DeviceAddress": 1,
    }
    inverter.decoded_model = {
        "AC_Power": 5000,
        "AC_Voltage_AN": 240,
        "I_Status": 4,
    }
    inverter.is_mmppt = False
    inverter.decoded_mmppt = {}
    inverter.has_battery = False
    inverter.decoded_storage_control = {}
    return inverter


@pytest.fixture
def mock_meter():
    """Create a mock SolarEdgeMeter."""
    meter = MagicMock()
    meter.meter_id = 1
    meter.inverter_unit_id = 1
    meter.device_info = {
        "identifiers": {(DOMAIN, "meter_1_987654321")},
        "name": "SolarEdge Meter 1",
        "manufacturer": "SolarEdge",
        "model": "WND-3Y-400-MB",
        "via_device_id": "0123456789abcdef0123456789abcdef",
    }
    meter.decoded_common = {
        "C_Manufacturer": "SolarEdge",
        "C_Model": "WND-3Y-400-MB",
        "C_SerialNumber": "987654321",
    }
    meter.decoded_model = {
        "M_AC_Power": 1000,
        "M_AC_Voltage_AN": 240,
    }
    return meter


@pytest.fixture
def mock_battery():
    """Create a mock SolarEdgeBattery."""
    battery = MagicMock()
    battery.battery_id = 1
    battery.inverter_unit_id = 1
    battery.device_info = {
        "identifiers": {(DOMAIN, "bat_1_BAT123456")},
        "name": "SolarEdge Battery 1",
        "manufacturer": "SolarEdge",
        "model": "BAT-10K1PS0B-01",
        "via_device_id": "0123456789abcdef0123456789abcdef",
    }
    battery.decoded_common = {
        "C_Manufacturer": "SolarEdge",
        "C_Model": "BAT-10K1PS0B-01",
        "B_SerialNumber": "BAT123456",
    }
    battery.decoded_model = {
        "B_StateOfCharge": 75,
        "B_Power": 2500,
        "B_Temperature": 25,
    }
    return battery


@pytest.fixture
def mock_config_entry(mock_config_entry_data, mock_config_entry_options):
    """Create a mock config entry."""
    entry = MockConfigEntry(
        version=2,
        minor_version=1,
        domain=DOMAIN,
        title="Test SolarEdge",
        data=mock_config_entry_data,
        source="user",
        unique_id="192.168.1.100:1502",
        options=mock_config_entry_options,
    )
    return entry


class TestAsyncGetConfigEntryDiagnostics:
    """Test async_get_config_entry_diagnostics function."""

    async def test_diagnostics_basic_structure(
        self, hass: HomeAssistant, mock_config_entry, mock_hub
    ):
        """Test basic diagnostics structure without devices."""
        # Setup hass data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["yaml"] = {}
        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=MagicMock()
        )

        result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

        # Check basic structure
        assert "pymodbus_version" in result
        assert result["pymodbus_version"] == "3.8.3"
        assert result["hardware_writes_enabled"] is False
        assert "config_entry" in result
        assert "yaml" in result

    async def test_diagnostics_config_redaction(
        self, hass: HomeAssistant, mock_config_entry, mock_hub
    ):
        """Test that sensitive config data is redacted."""
        # Setup hass data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["yaml"] = {"host": "192.168.1.100"}
        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=MagicMock()
        )

        result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

        # Check config redaction
        config_dict = result["config_entry"]
        assert (
            "host" not in config_dict.get("data", {})
            or config_dict["data"]["host"] == "**REDACTED**"
        )
        assert (
            "unique_id" not in config_dict or config_dict["unique_id"] == "**REDACTED**"
        )

        # Check yaml redaction
        yaml_dict = result["yaml"]
        if "host" in yaml_dict:
            assert yaml_dict["host"] == "**REDACTED**"

    async def test_diagnostics_with_single_inverter(
        self, hass: HomeAssistant, mock_config_entry, mock_hub, mock_inverter
    ):
        """Test diagnostics with a single inverter."""
        mock_hub.inverters = [mock_inverter]

        # Setup hass data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["yaml"] = {}
        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=MagicMock()
        )

        result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

        # Check inverter data
        assert "inverter_unit_id_1" in result
        inverter_data = result["inverter_unit_id_1"]

        assert "device_info" in inverter_data
        assert "global_power_control" in inverter_data
        assert "advanced_power_control" in inverter_data
        assert "site_limit_control" in inverter_data
        assert "common" in inverter_data
        assert "model" in inverter_data
        assert "is_mmppt" in inverter_data
        assert "mmppt" in inverter_data
        assert "has_battery" in inverter_data
        assert "storage_control" in inverter_data

        # Check that values in model are formatted (hex)
        model_data = inverter_data["model"]
        assert model_data["AC_Power"] == "0x1388"  # 5000 in hex
        assert model_data["AC_Voltage_AN"] == "0xf0"  # 240 in hex
        assert model_data["I_Status"] == "0x4"  # 4 in hex

    async def test_diagnostics_inverter_redaction(
        self, hass: HomeAssistant, mock_config_entry, mock_hub, mock_inverter
    ):
        """Test that sensitive inverter data is redacted."""
        mock_hub.inverters = [mock_inverter]

        # Setup hass data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["yaml"] = {}
        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=MagicMock()
        )

        result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

        inverter_data = result["inverter_unit_id_1"]

        # Check redaction of sensitive fields
        device_info = inverter_data["device_info"]
        if "identifiers" in device_info:
            assert device_info["identifiers"] == "**REDACTED**"

        common_data = inverter_data["common"]
        if "C_SerialNumber" in common_data:
            assert common_data["C_SerialNumber"] == "**REDACTED**"

    async def test_diagnostics_with_multiple_inverters(
        self, hass: HomeAssistant, mock_config_entry, mock_hub, mock_inverter
    ):
        """Test diagnostics with multiple inverters."""
        # Create second inverter
        inverter2 = MagicMock()
        inverter2.inverter_unit_id = 2
        inverter2.device_info = mock_inverter.device_info.copy()
        inverter2.global_power_control = False
        inverter2.advanced_power_control = False
        inverter2.site_limit_control = False
        inverter2.decoded_common = mock_inverter.decoded_common.copy()
        inverter2.decoded_model = {"AC_Power": 3000, "I_Status": 4}
        inverter2.is_mmppt = False
        inverter2.decoded_mmppt = {}
        inverter2.has_battery = False
        inverter2.decoded_storage_control = {}

        mock_hub.inverters = [mock_inverter, inverter2]

        # Setup hass data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["yaml"] = {}
        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=MagicMock()
        )

        result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

        # Check both inverters are present
        assert "inverter_unit_id_1" in result
        assert "inverter_unit_id_2" in result

        # Verify different power values are formatted correctly
        # 5000 in hex
        assert result["inverter_unit_id_1"]["model"]["AC_Power"] == "0x1388"
        # 3000 in hex
        assert result["inverter_unit_id_2"]["model"]["AC_Power"] == "0xbb8"

    async def test_diagnostics_with_meter(
        self, hass: HomeAssistant, mock_config_entry, mock_hub, mock_meter
    ):
        """Test diagnostics with a meter."""
        mock_hub.meters = [mock_meter]

        # Setup hass data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["yaml"] = {}
        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=MagicMock()
        )

        result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

        # Check meter data
        assert "meter_id_1" in result
        meter_data = result["meter_id_1"]

        assert "device_info" in meter_data
        assert "inverter_unit_id" in meter_data
        assert meter_data["inverter_unit_id"] == 1
        assert "common" in meter_data
        assert "model" in meter_data

        # Check that values in model are formatted (hex)
        model_data = meter_data["model"]
        assert model_data["M_AC_Power"] == "0x3e8"  # 1000 in hex
        assert model_data["M_AC_Voltage_AN"] == "0xf0"  # 240 in hex

    async def test_diagnostics_meter_redaction(
        self, hass: HomeAssistant, mock_config_entry, mock_hub, mock_meter
    ):
        """Test that sensitive meter data is redacted."""
        mock_hub.meters = [mock_meter]

        # Setup hass data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["yaml"] = {}
        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=MagicMock()
        )

        result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

        meter_data = result["meter_id_1"]

        # Check redaction of sensitive fields
        device_info = meter_data["device_info"]
        if "identifiers" in device_info:
            assert device_info["identifiers"] == "**REDACTED**"
        # The registry id is opaque, not a serial: it is left in the clear
        assert device_info["via_device_id"] == "0123456789abcdef0123456789abcdef"

        common_data = meter_data["common"]
        if "C_SerialNumber" in common_data:
            assert common_data["C_SerialNumber"] == "**REDACTED**"

    async def test_diagnostics_with_battery(
        self, hass: HomeAssistant, mock_config_entry, mock_hub, mock_battery
    ):
        """Test diagnostics with a battery."""
        mock_hub.batteries = [mock_battery]

        # Setup hass data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["yaml"] = {}
        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=MagicMock()
        )

        result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

        # Check battery data
        assert "battery_id_1" in result
        battery_data = result["battery_id_1"]

        assert "device_info" in battery_data
        assert "inverter_unit_id" in battery_data
        assert battery_data["inverter_unit_id"] == 1
        assert "common" in battery_data
        assert "model" in battery_data

        # Check that values in model are formatted (hex)
        model_data = battery_data["model"]
        assert model_data["B_StateOfCharge"] == "0x4b"  # 75 in hex
        assert model_data["B_Power"] == "0x9c4"  # 2500 in hex
        assert model_data["B_Temperature"] == "0x19"  # 25 in hex

    async def test_diagnostics_battery_redaction(
        self, hass: HomeAssistant, mock_config_entry, mock_hub, mock_battery
    ):
        """Test that sensitive battery data is redacted."""
        mock_hub.batteries = [mock_battery]

        # Setup hass data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["yaml"] = {}
        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=MagicMock()
        )

        result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

        battery_data = result["battery_id_1"]

        # Check redaction of sensitive fields
        device_info = battery_data["device_info"]
        if "identifiers" in device_info:
            assert device_info["identifiers"] == "**REDACTED**"
        # The registry id is opaque, not a serial: it is left in the clear
        assert device_info["via_device_id"] == "0123456789abcdef0123456789abcdef"

        common_data = battery_data["common"]
        if "B_SerialNumber" in common_data:
            assert common_data["B_SerialNumber"] == "**REDACTED**"

    async def test_diagnostics_with_all_devices(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_hub,
        mock_inverter,
        mock_meter,
        mock_battery,
    ):
        """Test diagnostics with inverter, meter, and battery."""
        mock_hub.inverters = [mock_inverter]
        mock_hub.meters = [mock_meter]
        mock_hub.batteries = [mock_battery]

        # Setup hass data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["yaml"] = {}
        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=MagicMock()
        )

        result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

        # Check all devices are present
        assert "pymodbus_version" in result
        assert "config_entry" in result
        assert "yaml" in result
        assert "inverter_unit_id_1" in result
        assert "meter_id_1" in result
        assert "battery_id_1" in result

    async def test_diagnostics_with_multiple_meters(
        self, hass: HomeAssistant, mock_config_entry, mock_hub, mock_meter
    ):
        """Test diagnostics with multiple meters."""
        # Create additional meters
        meter2 = MagicMock()
        meter2.meter_id = 2
        meter2.inverter_unit_id = 1
        meter2.device_info = mock_meter.device_info.copy()
        meter2.decoded_common = mock_meter.decoded_common.copy()
        meter2.decoded_model = {"M_AC_Power": 2000}

        meter3 = MagicMock()
        meter3.meter_id = 3
        meter3.inverter_unit_id = 1
        meter3.device_info = mock_meter.device_info.copy()
        meter3.decoded_common = mock_meter.decoded_common.copy()
        meter3.decoded_model = {"M_AC_Power": 3000}

        mock_hub.meters = [mock_meter, meter2, meter3]

        # Setup hass data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["yaml"] = {}
        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=MagicMock()
        )

        result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

        # Check all meters are present
        assert "meter_id_1" in result
        assert "meter_id_2" in result
        assert "meter_id_3" in result

        # Verify different power values
        assert result["meter_id_1"]["model"]["M_AC_Power"] == "0x3e8"  # 1000
        assert result["meter_id_2"]["model"]["M_AC_Power"] == "0x7d0"  # 2000
        assert result["meter_id_3"]["model"]["M_AC_Power"] == "0xbb8"  # 3000

    async def test_diagnostics_with_multiple_batteries(
        self, hass: HomeAssistant, mock_config_entry, mock_hub, mock_battery
    ):
        """Test diagnostics with multiple batteries."""
        # Create additional batteries
        battery2 = MagicMock()
        battery2.battery_id = 2
        battery2.inverter_unit_id = 1
        battery2.device_info = mock_battery.device_info.copy()
        battery2.decoded_common = mock_battery.decoded_common.copy()
        battery2.decoded_model = {"B_StateOfCharge": 50, "B_Power": 1500}

        battery3 = MagicMock()
        battery3.battery_id = 3
        battery3.inverter_unit_id = 1
        battery3.device_info = mock_battery.device_info.copy()
        battery3.decoded_common = mock_battery.decoded_common.copy()
        battery3.decoded_model = {"B_StateOfCharge": 90, "B_Power": 3000}

        mock_hub.batteries = [mock_battery, battery2, battery3]

        # Setup hass data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["yaml"] = {}
        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=MagicMock()
        )

        result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

        # Check all batteries are present
        assert "battery_id_1" in result
        assert "battery_id_2" in result
        assert "battery_id_3" in result

        # Verify different SOC values
        # 75 in hex
        assert result["battery_id_1"]["model"]["B_StateOfCharge"] == "0x4b"
        # 50 in hex
        assert result["battery_id_2"]["model"]["B_StateOfCharge"] == "0x32"
        # 90 in hex
        assert result["battery_id_3"]["model"]["B_StateOfCharge"] == "0x5a"

    async def test_diagnostics_with_mmppt_inverter(
        self, hass: HomeAssistant, mock_config_entry, mock_hub, mock_inverter
    ):
        """Test diagnostics with MMPPT inverter."""
        mock_inverter.is_mmppt = True
        mock_inverter.decoded_mmppt = {
            "MMPPT_Module1_DC_Voltage": 400,
            "MMPPT_Module1_DC_Current": 12,
        }
        mock_hub.inverters = [mock_inverter]

        # Setup hass data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["yaml"] = {}
        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=MagicMock()
        )

        result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

        inverter_data = result["inverter_unit_id_1"]
        assert inverter_data["is_mmppt"] is True
        assert "mmppt" in inverter_data
        assert inverter_data["mmppt"]["MMPPT_Module1_DC_Voltage"] == "0x190"
        assert inverter_data["mmppt"]["MMPPT_Module1_DC_Current"] == "0xc"

    async def test_diagnostics_with_battery_inverter(
        self, hass: HomeAssistant, mock_config_entry, mock_hub, mock_inverter
    ):
        """Test diagnostics with inverter that has battery storage control."""
        mock_inverter.has_battery = True
        mock_inverter.decoded_storage_control = {
            "B1_MaxChargePower": 5000,
            "B1_MaxDischargePower": 5000,
        }
        mock_hub.inverters = [mock_inverter]

        # Setup hass data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["yaml"] = {}
        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=MagicMock()
        )

        result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

        inverter_data = result["inverter_unit_id_1"]
        assert inverter_data["has_battery"] is True
        assert "storage_control" in inverter_data
        storage_control = inverter_data["storage_control"]
        assert storage_control["B1_MaxChargePower"] == "0x1388"
        assert storage_control["B1_MaxDischargePower"] == "0x1388"

    async def test_diagnostics_with_advanced_controls(
        self, hass: HomeAssistant, mock_config_entry, mock_hub, mock_inverter
    ):
        """Test diagnostics with advanced control options enabled."""
        mock_inverter.global_power_control = True
        mock_inverter.advanced_power_control = True
        mock_inverter.site_limit_control = True
        mock_hub.inverters = [mock_inverter]

        # Setup hass data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["yaml"] = {}
        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=MagicMock()
        )

        result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

        inverter_data = result["inverter_unit_id_1"]
        assert inverter_data["global_power_control"] is True
        assert inverter_data["advanced_power_control"] is True
        assert inverter_data["site_limit_control"] is True

    async def test_diagnostics_with_yaml_config(
        self, hass: HomeAssistant, mock_config_entry, mock_hub
    ):
        """Test diagnostics includes YAML configuration."""
        yaml_config = {
            "retry": {"limit": 5, "time": 200},
            "modbus": {"timeout": 5, "retries": 3},
        }

        # Setup hass data
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["yaml"] = yaml_config
        mock_config_entry.runtime_data = SimpleNamespace(
            hub=mock_hub, coordinator=MagicMock()
        )

        result = await async_get_config_entry_diagnostics(hass, mock_config_entry)

        assert "yaml" in result
        yaml_data = result["yaml"]
        assert "retry" in yaml_data
        assert yaml_data["retry"]["limit"] == 5
        assert yaml_data["retry"]["time"] == 200
        assert "modbus" in yaml_data
        assert yaml_data["modbus"]["timeout"] == 5
        assert yaml_data["modbus"]["retries"] == 3


class TestRedactionConstants:
    """Test that redaction constants are properly defined."""

    def test_redact_config_constants(self):
        """Test REDACT_CONFIG contains expected fields."""
        assert "unique_id" in REDACT_CONFIG
        assert "host" in REDACT_CONFIG

    def test_redact_inverter_constants(self):
        """Test REDACT_INVERTER contains expected fields."""
        assert "identifiers" in REDACT_INVERTER
        assert "C_SerialNumber" in REDACT_INVERTER
        assert "serial_number" in REDACT_INVERTER

    def test_redact_meter_constants(self):
        """Test REDACT_METER contains expected fields."""
        assert "identifiers" in REDACT_METER
        assert "C_SerialNumber" in REDACT_METER
        assert "serial_number" in REDACT_METER
        assert "via_device" not in REDACT_METER

    def test_redact_battery_constants(self):
        """Test REDACT_BATTERY contains expected fields."""
        assert "identifiers" in REDACT_BATTERY
        assert "B_SerialNumber" in REDACT_BATTERY
        assert "serial_number" in REDACT_BATTERY
        assert "via_device" not in REDACT_BATTERY


async def test_diagnostics_polling_section(
    hass, mock_config_entry_data, mock_config_entry_options, mock_modbus_client
) -> None:
    """Diagnostics expose poll-tier state and sanitized transport stats."""
    from dataclasses import fields
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from custom_components.solaredge_modbus_multi.const import DOMAIN
    from custom_components.solaredge_modbus_multi.diagnostics import (
        async_get_config_entry_diagnostics,
    )
    from custom_components.solaredge_modbus_multi.hub import SolarEdgeModbusMultiHub

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["yaml"] = {}

    hub = SolarEdgeModbusMultiHub(
        hass,
        entry_id="diag_test",
        entry_data=mock_config_entry_data,
        entry_options=mock_config_entry_options,
    )

    with patch(
        "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection",
        mock_modbus_client,
    ):
        await hub.connect()

    entry = MagicMock()
    entry.as_dict.return_value = {"data": {"host": "1.2.3.4"}}
    entry.runtime_data = SimpleNamespace(hub=hub)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    polling = diagnostics["polling"]
    assert polling["poll_groups"] == hub.poll_groups
    assert sorted(polling["poll_groups"]) == sorted(str(g) for g in PollGroup)
    assert polling["poll_groups"]["core"]["multiplier"] == 1
    # Nothing has been served yet, so the cadence evidence is empty.
    assert all(
        group["last_served_cycle"] is None for group in polling["poll_groups"].values()
    )
    assert polling["uncommitted_power_settings"] == []
    assert polling["transport"]["connects"] == 1
    assert polling["transport"]["reads"] == 0
    assert polling["transport"]["last_error"] is None
    # Every counter must be exported. A hand-picked subset here is how
    # recycles/connection_losses stayed invisible after being added.
    assert set(polling["transport"]) == {f.name for f in fields(PollStats)}
    # Redaction still applies to the config entry payload.
    assert diagnostics["config_entry"]["data"]["host"] == "**REDACTED**"
