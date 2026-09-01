"""Tests for zeroconf/mDNS discovery in config_flow.py."""

import socket
from ipaddress import ip_address
from unittest.mock import AsyncMock

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solaredge_modbus_multi.const import ConfName, DOMAIN

DISCOVERY_INFO = ZeroconfServiceInfo(
    ip_address=ip_address("192.168.1.50"),
    ip_addresses=[ip_address("192.168.1.50")],
    port=1502,
    hostname="solaredge-gateway.local.",
    type="_solaredge-modbus._tcp.local.",
    name="SolarEdge Gateway._solaredge-modbus._tcp.local.",
    properties={},
)

# SolarEdge inverters advertise a hostname like "SolarEdgeInv-<serial>.local"
# that (probably) stays the same across a device's different interfaces,
# unlike the resolved IP.
DISCOVERY_INFO_WITH_SERIAL = ZeroconfServiceInfo(
    ip_address=ip_address("192.168.1.60"),
    ip_addresses=[ip_address("192.168.1.60")],
    port=1502,
    hostname="SolarEdgeInv-730663BC.local.",
    type="_solaredge-modbus._tcp.local.",
    name="SolarEdgeInv-730663BC._solaredge-modbus._tcp.local.",
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


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_zeroconf_discovery_aborts_if_configured_by_mdns_hostname(hass):
    """A manual entry using the raw mDNS hostname instead of the IP
    should still be treated as the same device.

    discovery_info.hostname is "solaredge-gateway.local." - only the
    trailing FQDN dot is stripped, so ".local" remains part of the host
    the config flow compares against.
    """
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="solaredge-gateway.local:1502",
        data={CONF_HOST: "solaredge-gateway.local", CONF_PORT: 1502},
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=DISCOVERY_INFO,
    )

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_zeroconf_discovery_aborts_if_configured_by_dns_name(hass, monkeypatch):
    """A manual entry using a DNS name that resolves to the
    discovered IP should be treated as the same device."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="inverter.example.com:1502",
        data={CONF_HOST: "inverter.example.com", CONF_PORT: 1502},
    ).add_to_hass(hass)

    resolve = AsyncMock(
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", 0)),
        ]
    )
    monkeypatch.setattr(hass.loop, "getaddrinfo", resolve)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=DISCOVERY_INFO,
    )

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
    resolve.assert_awaited_once_with("inverter.example.com", None)


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_zeroconf_discovery_does_not_abort_for_unrelated_dns_name(
    hass, monkeypatch
):
    """A DNS name that resolves to a different device must not dedupe."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="other-inverter.example.com:1502",
        data={CONF_HOST: "other-inverter.example.com", CONF_PORT: 1502},
    ).add_to_hass(hass)

    resolve = AsyncMock(
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.99", 0)),
        ]
    )
    monkeypatch.setattr(hass.loop, "getaddrinfo", resolve)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=DISCOVERY_INFO,
    )

    assert result["type"] == "form"
    assert result["step_id"] == "zeroconf_confirm"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_zeroconf_discovery_ignores_dns_resolution_failures(hass, monkeypatch):
    """Don't break discovery if a DNS name fails to resolve."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="unreachable.example.com:1502",
        data={CONF_HOST: "unreachable.example.com", CONF_PORT: 1502},
    ).add_to_hass(hass)

    resolve = AsyncMock(side_effect=OSError("name resolution failed"))
    monkeypatch.setattr(hass.loop, "getaddrinfo", resolve)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=DISCOVERY_INFO,
    )

    assert result["type"] == "form"
    assert result["step_id"] == "zeroconf_confirm"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_zeroconf_discovery_does_not_abort_for_different_port(hass):
    """Same host but a different port is a different hub."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.50:502",
        data={CONF_HOST: "192.168.1.50", CONF_PORT: 502},
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=DISCOVERY_INFO,
    )

    assert result["type"] == "form"
    assert result["step_id"] == "zeroconf_confirm"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_zeroconf_discovery_aborts_for_matching_mdns_serial_on_new_interface(
    hass,
):
    """Same inverter discovered via a second interface (different IP,
    different mDNS record)"""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.50:502",
        data={
            CONF_HOST: "192.168.1.50",
            CONF_PORT: 502,
            ConfName.MDNS_SERIAL: "730663bc",
        },
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=DISCOVERY_INFO_WITH_SERIAL,
    )

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_zeroconf_discovery_does_not_abort_for_different_mdns_serial(hass):
    """A different inverter's serial must not be treated as a match."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.50:1502",
        data={
            CONF_HOST: "192.168.1.50",
            CONF_PORT: 1502,
            ConfName.MDNS_SERIAL: "deadbeef",
        },
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=DISCOVERY_INFO_WITH_SERIAL,
    )

    assert result["type"] == "form"
    assert result["step_id"] == "zeroconf_confirm"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_zeroconf_discovery_does_not_resolve_dns_for_mismatched_ip(
    hass, monkeypatch
):
    """A manually configured entry using a different IP is
    a different host and shouldn't trigger a DNS lookup."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.99:1502",
        data={CONF_HOST: "192.168.1.99", CONF_PORT: 1502},
    ).add_to_hass(hass)

    resolve = AsyncMock()
    monkeypatch.setattr(hass.loop, "getaddrinfo", resolve)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=DISCOVERY_INFO,
    )

    assert result["type"] == "form"
    assert result["step_id"] == "zeroconf_confirm"
    resolve.assert_not_awaited()
