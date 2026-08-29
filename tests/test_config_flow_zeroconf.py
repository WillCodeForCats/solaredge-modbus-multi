"""Tests for zeroconf/mDNS discovery in config_flow.py."""

from ipaddress import ip_address

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solaredge_modbus_multi.const import DOMAIN

DISCOVERY_INFO = ZeroconfServiceInfo(
    ip_address=ip_address("192.168.1.50"),
    ip_addresses=[ip_address("192.168.1.50")],
    port=1502,
    hostname="solaredge-gateway.local.",
    type="_solaredge-modbus._tcp.local.",
    name="SolarEdge Gateway._solaredge-modbus._tcp.local.",
    properties={},
)


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_zeroconf_discovery_shows_confirm_form(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=DISCOVERY_INFO,
    )

    assert result["type"] == "form"
    assert result["step_id"] == "zeroconf_confirm"
    assert result["description_placeholders"] == {
        CONF_HOST: "192.168.1.50",
        CONF_PORT: "1502",
    }

    flow = hass.config_entries.flow.async_get(result["flow_id"])
    assert flow["context"]["unique_id"] == "192.168.1.50:1502"
    assert flow["context"]["title_placeholders"] == {"host": "192.168.1.50"}


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_zeroconf_discovery_aborts_if_already_configured(hass):
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.50:1502",
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 1502},
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=DISCOVERY_INFO,
    )

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
