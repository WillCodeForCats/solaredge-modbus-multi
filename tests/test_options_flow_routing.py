"""Tests for the step routing and defaults of the options flow in config_flow.py."""

from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solaredge_modbus_multi.const import DOMAIN, ConfName


def _init_input(**overrides):
    user_input = {
        CONF_SCAN_INTERVAL: 15,
        ConfName.CLOSE_AFTER_POLLING: False,
        ConfName.DETECT_METERS: True,
        ConfName.DETECT_BATTERIES: False,
        ConfName.DETECT_EXTRAS: True,
        ConfName.ADV_PWR_CONTROL: False,
        ConfName.REQUEST_TIMEOUT: 3,
        ConfName.SLEEP_AFTER_WRITE: 0,
    }
    user_input.update(overrides)
    return user_input


async def _start_options(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 1502, ConfName.DEVICE_LIST: [1]},
    )
    entry.add_to_hass(hass)
    return await hass.config_entries.options.async_init(entry.entry_id)


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_init_without_input_shows_form_with_defaults(hass):
    """Test init without input shows form with defaults."""
    result = await _start_options(hass)

    assert result["type"] == "form"
    assert result["step_id"] == "init"
    assert not result["errors"]


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_init_creates_entry_without_follow_up_steps(hass):
    """Test init creates entry without follow up steps."""
    result = await _start_options(hass)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input=_init_input()
    )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_SCAN_INTERVAL] == 15


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_init_routes_to_battery_options_when_batteries_detected(hass):
    """Test init routes to battery options when batteries detected."""
    result = await _start_options(hass)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=_init_input(**{ConfName.DETECT_BATTERIES: True}),
    )

    assert result["type"] == "form"
    assert result["step_id"] == "battery_options"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_init_routes_to_adv_pwr_ctl_when_advanced_control_enabled(hass):
    """Test init routes to adv pwr ctl when advanced control enabled."""
    result = await _start_options(hass)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=_init_input(**{ConfName.ADV_PWR_CONTROL: True}),
    )

    assert result["type"] == "form"
    assert result["step_id"] == "adv_pwr_ctl"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_init_batteries_take_precedence_over_advanced_control(hass):
    """Test init batteries take precedence over advanced control."""
    result = await _start_options(hass)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=_init_input(
            **{ConfName.DETECT_BATTERIES: True, ConfName.ADV_PWR_CONTROL: True}
        ),
    )

    assert result["step_id"] == "battery_options"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            ConfName.ALLOW_BATTERY_ENERGY_RESET: False,
            ConfName.BATTERY_ENERGY_RESET_CYCLES: 0,
            ConfName.BATTERY_RATING_ADJUST: 100,
        },
    )

    assert result["type"] == "form"
    assert result["step_id"] == "adv_pwr_ctl"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_battery_options_creates_entry_when_no_advanced_control(hass):
    """Test battery options creates entry when no advanced control."""
    result = await _start_options(hass)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=_init_input(**{ConfName.DETECT_BATTERIES: True}),
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            ConfName.ALLOW_BATTERY_ENERGY_RESET: True,
            ConfName.BATTERY_ENERGY_RESET_CYCLES: 5,
            ConfName.BATTERY_RATING_ADJUST: 90,
        },
    )

    assert result["type"] == "create_entry"
    assert result["data"][ConfName.BATTERY_RATING_ADJUST] == 90
    assert result["data"][ConfName.DETECT_BATTERIES] is True


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_battery_options_rejects_invalid_percent(hass):
    """Test battery options rejects invalid percent."""
    result = await _start_options(hass)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=_init_input(**{ConfName.DETECT_BATTERIES: True}),
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            ConfName.ALLOW_BATTERY_ENERGY_RESET: False,
            ConfName.BATTERY_ENERGY_RESET_CYCLES: 0,
            ConfName.BATTERY_RATING_ADJUST: 101,
        },
    )

    assert result["type"] == "form"
    assert result["errors"] == {ConfName.BATTERY_RATING_ADJUST: "invalid_percent"}


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize(
    ("override", "error_key", "error"),
    [
        ({CONF_SCAN_INTERVAL: 0}, CONF_SCAN_INTERVAL, "invalid_scan_interval"),
        (
            {ConfName.REQUEST_TIMEOUT: 61},
            ConfName.REQUEST_TIMEOUT,
            "invalid_request_timeout",
        ),
        (
            {ConfName.SLEEP_AFTER_WRITE: -1},
            ConfName.SLEEP_AFTER_WRITE,
            "invalid_sleep_interval",
        ),
    ],
)
async def test_init_rejects_out_of_range_values(hass, override, error_key, error):
    """Test init rejects out of range values."""
    result = await _start_options(hass)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input=_init_input(**override)
    )

    assert result["type"] == "form"
    assert result["step_id"] == "init"
    assert result["errors"] == {error_key: error}
