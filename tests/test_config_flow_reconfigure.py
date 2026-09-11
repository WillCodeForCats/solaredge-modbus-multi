"""Tests for the reconfigure flow's unique_id handling in config_flow.py."""

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solaredge_modbus_multi.const import DOMAIN, ConfName


async def _start_reconfigure(hass, entry):
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_reconfigure_updates_unique_id_when_still_host_port(hass):
    """A unique_id still matches its own stored host:port
    (the default scheme) gets it recomputed when the host changes."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.50:1502",
        data={
            CONF_HOST: "192.168.1.50",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: [1],
        },
    )
    entry.add_to_hass(hass)

    result = await _start_reconfigure(hass, entry)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: "192.168.1.60",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: "1",
        },
    )

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == "192.168.1.60:1502"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_reconfigure_preserves_non_host_port_unique_id(hass):
    """A unique_id that no longer matches its stored host:port must not be
    silently reset back to host:port by a routine host/port change."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="730663bc",
        data={
            CONF_HOST: "192.168.1.50",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: [1],
        },
    )
    entry.add_to_hass(hass)

    result = await _start_reconfigure(hass, entry)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: "192.168.1.60",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: "1",
        },
    )

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == "730663bc"
    assert entry.data[CONF_HOST] == "192.168.1.60"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_reconfigure_aborts_on_host_port_collision(hass):
    """Reconfiguring a host:port entry to another entry's existing
    host:port must be rejected as a duplicate."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.99:1502",
        data={
            CONF_HOST: "192.168.1.99",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: [1],
        },
    ).add_to_hass(hass)

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.50:1502",
        data={
            CONF_HOST: "192.168.1.50",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: [1],
        },
    )
    entry.add_to_hass(hass)

    result = await _start_reconfigure(hass, entry)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: "192.168.1.99",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: "1",
        },
    )

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_reconfigure_with_unchanged_host_port_succeeds(hass):
    """Reconfiguring without changing host/port"""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.50:1502",
        data={
            CONF_HOST: "192.168.1.50",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: [1],
        },
    )
    entry.add_to_hass(hass)

    result = await _start_reconfigure(hass, entry)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: "192.168.1.50",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: "1,2",
        },
    )

    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == "192.168.1.50:1502"
    assert entry.data[ConfName.DEVICE_LIST] == [1, 2]
