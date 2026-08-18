"""Tests for SolarEdgeModbusMultiHub options."""

from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from modbus_connection.mock import MockModbusConnection

from custom_components.solaredge_modbus_multi.const import DOMAIN, ConfName
from custom_components.solaredge_modbus_multi.hub import SolarEdgeModbusMultiHub

ENTRY_DATA = {
    CONF_NAME: "SolarEdge",
    CONF_HOST: "127.0.0.1",
    CONF_PORT: 1502,
}


# 209460d "Fix bad default" (PR #408)
# bf0e822 "Incorrect casting of default value" (PR #414)


def _make_hub(hass, entry_data=None, entry_options=None):
    hass.data[DOMAIN] = {"yaml": {}}
    return SolarEdgeModbusMultiHub(
        hass,
        "test_entry_id",
        entry_data if entry_data is not None else ENTRY_DATA,
        entry_options if entry_options is not None else {},
        MockModbusConnection(),
    )


async def test_options_default_to_int(hass):
    hub = _make_hub(hass)

    for attr in (
        "_sleep_after_write",
        "_battery_rating_adjust",
        "_battery_energy_reset_cycles",
    ):
        value = getattr(hub, attr)
        assert value == 0
        assert isinstance(value, int) and not isinstance(value, bool), (
            f"{attr} regressed to {type(value).__name__}"
        )


async def test_option_override_is_stored(hass):
    hub = _make_hub(hass, entry_options={ConfName.SLEEP_AFTER_WRITE: 5})

    assert hub._sleep_after_write == 5
    assert isinstance(hub._sleep_after_write, int)
    assert not isinstance(hub._sleep_after_write, bool)


async def test_options_default_to_bool(hass):
    hub = _make_hub(hass)

    for attr in (
        "_detect_meters",
        "_detect_batteries",
    ):
        assert isinstance(getattr(hub, attr), bool)


async def test_device_list_defaults(hass):
    entry_data = dict(ENTRY_DATA)
    hub = _make_hub(hass, entry_data=entry_data)

    assert hub._inverter_list == ["1"]
