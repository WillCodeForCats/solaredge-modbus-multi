"""Tests for the tmodbus/modbus-connection version check in
SolarEdgeModbusMultiHub._async_init_solaredge().
"""

import pytest
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from modbus_connection.mock import MockModbusConnection

from custom_components.solaredge_modbus_multi.const import DOMAIN, ConfName
from custom_components.solaredge_modbus_multi.hub import (
    HubInitFailed,
    SolarEdgeModbusMultiHub,
)

ENTRY_DATA = {
    CONF_NAME: "SolarEdge",
    CONF_HOST: "127.0.0.1",
    CONF_PORT: 1502,
    ConfName.DEVICE_LIST: [],
}


def _make_hub(hass):
    hass.data[DOMAIN] = {"yaml": {}}
    return SolarEdgeModbusMultiHub(
        hass, "test_entry_id", ENTRY_DATA, {}, MockModbusConnection()
    )


class TestSafeVersionTuple:
    def test_parses_dotted_version(self):
        assert SolarEdgeModbusMultiHub._safe_version_tuple("4.10.0") == (4, 10, 0)

    def test_rejects_non_numeric_part(self):
        with pytest.raises(ValueError):
            SolarEdgeModbusMultiHub._safe_version_tuple("4.10.0-pre1")


class TestTmodbusVersionCheck:
    async def test_older_than_required_raises(self, hass):
        hub = _make_hub(hass)
        hub._tmodbus_version = "0.6.0"

        with pytest.raises(HubInitFailed, match="tmodbus version must be at least"):
            await hub._async_init_solaredge()

    async def test_meets_required_version_passes(self, hass):
        hub = _make_hub(hass)
        hub._tmodbus_version = hub.tmodbus_required_version

        with pytest.raises(HubInitFailed, match="No usable inverters found"):
            await hub._async_init_solaredge()

    async def test_newer_than_required_passes(self, hass):
        hub = _make_hub(hass)
        hub._tmodbus_version = "99.0.0"

        with pytest.raises(HubInitFailed, match="No usable inverters found"):
            await hub._async_init_solaredge()


class TestModbusConnectionVersionCheck:
    async def test_older_than_required_raises(self, hass):
        hub = _make_hub(hass)
        hub._modbus_connection_version = "4.9.0"

        with pytest.raises(
            HubInitFailed, match="modbus-connection version must be at least"
        ):
            await hub._async_init_solaredge()

    async def test_meets_required_version_passes(self, hass):
        hub = _make_hub(hass)
        hub._modbus_connection_version = hub.modbus_connection_required_version

        with pytest.raises(HubInitFailed, match="No usable inverters found"):
            await hub._async_init_solaredge()

    async def test_newer_than_required_passes(self, hass):
        hub = _make_hub(hass)
        hub._modbus_connection_version = "99.0.0"

        with pytest.raises(HubInitFailed, match="No usable inverters found"):
            await hub._async_init_solaredge()

    async def test_checked_after_tmodbus(self, hass):
        # tmodbus is checked first; old tmodbus version must be reported
        # even if modbus-connection is also too old.
        hub = _make_hub(hass)
        hub._tmodbus_version = "0.1.0"
        hub._modbus_connection_version = "0.1.0"

        with pytest.raises(HubInitFailed, match="tmodbus version must be at least"):
            await hub._async_init_solaredge()
