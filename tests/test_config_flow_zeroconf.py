"""Tests for zeroconf/mDNS discovery in config_flow.py."""

import asyncio
from ipaddress import ip_address
import socket
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import UnknownFlow
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solaredge_modbus_multi.const import DOMAIN
from custom_components.solaredge_modbus_multi.scanner import ScannerConnectionError

DISCOVERY_INFO = ZeroconfServiceInfo(
    ip_address=ip_address("192.168.1.50"),
    ip_addresses=[ip_address("192.168.1.50")],
    port=1502,
    hostname="solaredge-gateway.local.",
    type="_solaredge-modbus._tcp.local.",
    name="SolarEdge Gateway._solaredge-modbus._tcp.local.",
    properties={},
)


@pytest.fixture(autouse=True)
def mock_scan():
    """Scan finds inverters 1 and 2 unless a test overrides this."""
    with patch(
        "custom_components.solaredge_modbus_multi.config_flow."
        "SolaredgeModbusMultiConfigFlow._async_scan_devices",
        AsyncMock(return_value=[1, 2]),
    ) as mock:
        yield mock


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_zeroconf_discovery_shows_confirm_form(hass):
    """Test zeroconf discovery shows confirm form."""
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
    """Test zeroconf discovery aborts if already configured."""
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
    """A manual entry using the raw mDNS hostname is the same device.

    The entry uses the hostname instead of the IP.

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
    """A manual entry using a DNS name resolving to the discovered IP matches.

    It is treated as the same device.
    """
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
async def test_zeroconf_discovery_does_not_resolve_dns_for_mismatched_ip(
    hass, monkeypatch
):
    """A manual entry using a different IP is a different host.

    It shouldn't trigger a DNS lookup.
    """
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


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_zeroconf_discovery_withdrawn_if_scan_finds_nothing(hass, mock_scan):
    """A device that is unreachable or has no inverters is not offered.

    A follower inverter may advertise mDNS without a reachable port - see
    issue #1084.
    """
    mock_scan.return_value = ScannerConnectionError("no route")

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=DISCOVERY_INFO,
    )
    await hass.async_block_till_done()

    with pytest.raises(UnknownFlow):
        hass.config_entries.flow.async_get(result["flow_id"])
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)


async def _start_and_confirm(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=DISCOVERY_INFO,
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "SolarEdge"}
    )


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_zeroconf_scan_starts_at_discovery(hass, mock_scan):
    """The scan starts in the background before the user confirms."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=DISCOVERY_INFO,
    )
    await hass.async_block_till_done()

    mock_scan.assert_awaited_once_with({CONF_HOST: "192.168.1.50", CONF_PORT: 1502})


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_zeroconf_select_offers_found_inverters(hass):
    """Found inverters are offered for setup, all selected by default."""
    await asyncio.sleep(0)
    result = await _start_and_confirm(hass)
    if result["type"] == "progress":
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] == "form"
    assert result["step_id"] == "zeroconf_select"
    assert result["data_schema"]({}) == {"device_list": ["1", "2"]}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"device_list": ["2"]}
    )
    assert result["step_id"] == "features_info"

    with patch(
        "custom_components.solaredge_modbus_multi.async_setup_entry",
        AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    assert result["title"] == "SolarEdge"
    assert result["data"] == {
        "name": "SolarEdge",
        CONF_HOST: "192.168.1.50",
        CONF_PORT: 1502,
        "device_list": [2],
    }


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_zeroconf_aborts_if_no_inverters_found(hass, mock_scan):
    """A scan that ends while the user waits on it ends the flow with a reason."""
    release = asyncio.Event()

    async def scan(_):
        await release.wait()
        return []

    mock_scan.side_effect = scan

    result = await _start_and_confirm(hass)
    assert result["type"] == "progress"

    release.set()
    await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] == "abort"
    assert result["reason"] == "no_inverters_found"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_zeroconf_aborts_if_scan_failed(hass, mock_scan):
    """A scan that ends while the user waits on it ends the flow with a reason."""
    release = asyncio.Event()

    async def scan(_):
        await release.wait()
        return ScannerConnectionError("no route")

    mock_scan.side_effect = scan

    result = await _start_and_confirm(hass)
    assert result["type"] == "progress"

    release.set()
    await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] == "abort"
    assert result["reason"] == "scan_failed"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_zeroconf_removing_flow_cancels_scan(hass, mock_scan):
    """Dismissing the discovery stops the background scan."""
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def slow_scan(_):
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    mock_scan.side_effect = slow_scan

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=DISCOVERY_INFO,
    )
    await started.wait()
    hass.config_entries.flow.async_abort(result["flow_id"])
    await asyncio.wait_for(cancelled.wait(), timeout=1)
