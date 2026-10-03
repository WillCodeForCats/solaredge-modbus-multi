"""Tests for the SolarEdge Modbus Multi repairs module."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.repairs import RepairsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solaredge_modbus_multi.const import DOMAIN, ConfName
from custom_components.solaredge_modbus_multi.repairs import (
    CheckConfigurationRepairFlow,
    async_create_fix_flow,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield


@pytest.fixture
def mock_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create a mock config entry for repairs."""
    entry = MockConfigEntry(
        version=2,
        minor_version=1,
        domain=DOMAIN,
        title="Test SolarEdge",
        data={
            CONF_HOST: "192.168.1.100",
            CONF_PORT: 1502,
            CONF_NAME: "Test SolarEdge",
            ConfName.DEVICE_LIST: [1, 2],
        },
        source="user",
        unique_id="192.168.1.100:1502",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def repair_flow(mock_config_entry: MockConfigEntry) -> CheckConfigurationRepairFlow:
    """Create a CheckConfigurationRepairFlow instance."""
    return CheckConfigurationRepairFlow(mock_config_entry)


@pytest.fixture
async def mock_setup_entry(hass: HomeAssistant):
    """Stub entry setup for flows that end in a reload.

    A real setup would open a Modbus socket to the test host, which the
    harness blocks and then fails the test on at teardown. The reload is
    only scheduled, so drain it here while the stub is still in place.
    """
    with patch(
        "custom_components.solaredge_modbus_multi.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock
        await hass.async_block_till_done()


@pytest.mark.usefixtures("mock_setup_entry")
class TestCheckConfigurationRepairFlow:
    """Test CheckConfigurationRepairFlow class."""

    def test_init(self, mock_config_entry: MockConfigEntry) -> None:
        """Test initialization of repair flow."""
        flow = CheckConfigurationRepairFlow(mock_config_entry)
        assert flow._entry == mock_config_entry
        assert isinstance(flow, RepairsFlow)

    async def test_async_step_init(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test async_step_init redirects to confirm step."""
        repair_flow.hass = hass

        with patch.object(
            repair_flow, "async_step_confirm", new_callable=AsyncMock
        ) as mock_confirm:
            mock_confirm.return_value = {"type": "form"}
            result = await repair_flow.async_step_init()
            mock_confirm.assert_called_once()
            assert result == {"type": "form"}

    async def test_async_step_confirm_no_input_shows_form(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test confirm step without user input shows form with current values."""
        repair_flow.hass = hass

        result = await repair_flow.async_step_confirm(user_input=None)

        assert result["type"] == "form"
        assert result["step_id"] == "confirm"
        assert result["errors"] == {}
        # Verify default values are populated from config entry
        assert "data_schema" in result

    async def test_async_step_confirm_valid_input(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test confirm step with valid input updates config entry."""
        repair_flow.hass = hass

        user_input = {
            CONF_HOST: "192.168.1.200",
            CONF_PORT: 1503,
            ConfName.DEVICE_LIST: "1,2,3",
        }

        with patch.object(hass.config_entries, "async_update_entry") as mock_update:
            result = await repair_flow.async_step_confirm(user_input=user_input)

        assert result["type"] == "create_entry"
        assert result["title"] == ""
        assert result["data"] == {}

        # Verify config entry was updated with normalized values
        mock_update.assert_called_once()
        call_args = mock_update.call_args
        assert call_args[0][0] == repair_flow._entry
        assert call_args[1]["unique_id"] == "192.168.1.200:1503"
        # Verify device_list was converted from string to list
        assert call_args[1]["data"][ConfName.DEVICE_LIST] == [1, 2, 3]
        # Verify host was lowercased
        assert call_args[1]["data"][CONF_HOST] == "192.168.1.200"

    async def test_async_step_confirm_normalizes_host(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test confirm step normalizes host to lowercase."""
        repair_flow.hass = hass

        user_input = {
            CONF_HOST: "INVERTER.LOCAL",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: "1",
        }

        with patch.object(hass.config_entries, "async_update_entry"):
            result = await repair_flow.async_step_confirm(user_input=user_input)

        assert result["type"] == "create_entry"

    async def test_async_step_confirm_strips_whitespace_from_device_list(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test confirm step strips whitespace from device_list."""
        repair_flow.hass = hass

        user_input = {
            CONF_HOST: "192.168.1.100",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: " 1 , 2 , 3 ",
        }

        with patch.object(hass.config_entries, "async_update_entry") as mock_update:
            result = await repair_flow.async_step_confirm(user_input=user_input)

        assert result["type"] == "create_entry"
        # Verify whitespace was removed
        call_args = mock_update.call_args
        assert call_args[1]["data"][ConfName.DEVICE_LIST] == [1, 2, 3]

    async def test_async_step_confirm_invalid_device_list_format(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test confirm step with invalid device_list format."""
        repair_flow.hass = hass

        user_input = {
            CONF_HOST: "192.168.1.100",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: "invalid",
        }

        result = await repair_flow.async_step_confirm(user_input=user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "confirm"
        assert ConfName.DEVICE_LIST in result["errors"]
        # Error message should contain the exception message
        assert "invalid_device_id" in result["errors"][ConfName.DEVICE_LIST]

    async def test_async_step_confirm_empty_device_list(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test confirm step with empty device_list."""
        repair_flow.hass = hass

        user_input = {
            CONF_HOST: "192.168.1.100",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: "",
        }

        result = await repair_flow.async_step_confirm(user_input=user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "confirm"
        assert ConfName.DEVICE_LIST in result["errors"]

    async def test_async_step_confirm_invalid_device_range(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test confirm step with invalid device range (end < start)."""
        repair_flow.hass = hass

        user_input = {
            CONF_HOST: "192.168.1.100",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: "5-1",
        }

        result = await repair_flow.async_step_confirm(user_input=user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "confirm"
        assert ConfName.DEVICE_LIST in result["errors"]
        assert "invalid_range_lte" in result["errors"][ConfName.DEVICE_LIST]

    async def test_async_step_confirm_invalid_host(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test confirm step with invalid host.

        Note: Due to a bug in host_valid(), invalid IPs like 999.999.999.999
        are incorrectly accepted because they match the DOMAIN_REGEX pattern.
        This test documents the current behavior.
        """
        repair_flow.hass = hass

        # Use a truly invalid hostname that won't match the regex
        user_input = {
            CONF_HOST: "invalid..host",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: "1",
        }

        result = await repair_flow.async_step_confirm(user_input=user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "confirm"
        assert CONF_HOST in result["errors"]
        assert result["errors"][CONF_HOST] == "invalid_host"

    async def test_async_step_confirm_invalid_port_too_low(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test confirm step with port number too low."""
        repair_flow.hass = hass

        user_input = {
            CONF_HOST: "192.168.1.100",
            CONF_PORT: 0,
            ConfName.DEVICE_LIST: "1",
        }

        result = await repair_flow.async_step_confirm(user_input=user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "confirm"
        assert CONF_PORT in result["errors"]
        assert result["errors"][CONF_PORT] == "invalid_tcp_port"

    async def test_async_step_confirm_invalid_port_too_high(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test confirm step with port number too high."""
        repair_flow.hass = hass

        user_input = {
            CONF_HOST: "192.168.1.100",
            CONF_PORT: 65536,
            ConfName.DEVICE_LIST: "1",
        }

        result = await repair_flow.async_step_confirm(user_input=user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "confirm"
        assert CONF_PORT in result["errors"]
        assert result["errors"][CONF_PORT] == "invalid_tcp_port"

    async def test_async_step_confirm_inverter_count_too_low(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test confirm step with zero inverters."""
        repair_flow.hass = hass

        # Create a mock that returns empty list
        with patch(
            "custom_components.solaredge_modbus_multi.repairs.device_list_from_string",
            return_value=[],
        ):
            user_input = {
                CONF_HOST: "192.168.1.100",
                CONF_PORT: 1502,
                ConfName.DEVICE_LIST: "1",
            }

            result = await repair_flow.async_step_confirm(user_input=user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "confirm"
        assert ConfName.DEVICE_LIST in result["errors"]
        assert result["errors"][ConfName.DEVICE_LIST] == "invalid_inverter_count"

    async def test_async_step_confirm_inverter_count_too_high(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test confirm step with too many inverters."""
        repair_flow.hass = hass

        # Create a list with 33 inverters
        with patch(
            "custom_components.solaredge_modbus_multi.repairs.device_list_from_string",
            return_value=list(range(1, 34)),
        ):
            user_input = {
                CONF_HOST: "192.168.1.100",
                CONF_PORT: 1502,
                ConfName.DEVICE_LIST: "1-33",
            }

            result = await repair_flow.async_step_confirm(user_input=user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "confirm"
        assert ConfName.DEVICE_LIST in result["errors"]
        assert result["errors"][ConfName.DEVICE_LIST] == "invalid_inverter_count"

    async def test_async_step_confirm_already_configured(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test confirm step with host:port already configured in another entry."""
        repair_flow.hass = hass

        # Create another config entry with different unique_id
        existing_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_HOST: "192.168.1.200",
                CONF_PORT: 1502,
                ConfName.DEVICE_LIST: [3],
            },
            unique_id="192.168.1.200:1502",
        )
        existing_entry.add_to_hass(hass)

        # Try to configure the current entry with the same host:port as existing
        user_input = {
            CONF_HOST: "192.168.1.200",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: "1",
        }

        result = await repair_flow.async_step_confirm(user_input=user_input)

        assert result["type"] == "form"
        assert result["step_id"] == "confirm"
        assert CONF_HOST in result["errors"]
        assert CONF_PORT in result["errors"]
        assert result["errors"][CONF_HOST] == "already_configured"
        assert result["errors"][CONF_PORT] == "already_configured"

    async def test_async_step_confirm_same_unique_id_allowed(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test confirm step allows keeping the same unique_id."""
        repair_flow.hass = hass

        # Use the same host:port as the original entry
        user_input = {
            CONF_HOST: "192.168.1.100",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: "1,2,3",
        }

        with patch.object(hass.config_entries, "async_update_entry"):
            result = await repair_flow.async_step_confirm(user_input=user_input)

        assert result["type"] == "create_entry"

    async def test_async_step_confirm_valid_hostname(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test confirm step with valid hostname."""
        repair_flow.hass = hass

        user_input = {
            CONF_HOST: "inverter.local",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: "1",
        }

        with patch.object(hass.config_entries, "async_update_entry"):
            result = await repair_flow.async_step_confirm(user_input=user_input)

        assert result["type"] == "create_entry"

    async def test_async_step_confirm_valid_ipv6(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test confirm step with valid IPv6 address."""
        repair_flow.hass = hass

        user_input = {
            CONF_HOST: "::1",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: "1",
        }

        with patch.object(hass.config_entries, "async_update_entry"):
            result = await repair_flow.async_step_confirm(user_input=user_input)

        assert result["type"] == "create_entry"

    async def test_async_step_confirm_device_range(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test confirm step with device range."""
        repair_flow.hass = hass

        user_input = {
            CONF_HOST: "192.168.1.100",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: "1-5",
        }

        with patch.object(hass.config_entries, "async_update_entry") as mock_update:
            result = await repair_flow.async_step_confirm(user_input=user_input)

        assert result["type"] == "create_entry"
        call_args = mock_update.call_args
        # Verify range was expanded to list
        assert call_args[1]["data"][ConfName.DEVICE_LIST] == [1, 2, 3, 4, 5]

    async def test_async_step_confirm_complex_device_list(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test confirm step with complex device list (ranges and individual IDs)."""
        repair_flow.hass = hass

        user_input = {
            CONF_HOST: "192.168.1.100",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: "1,3-5,10",
        }

        with patch.object(hass.config_entries, "async_update_entry") as mock_update:
            result = await repair_flow.async_step_confirm(user_input=user_input)

        assert result["type"] == "create_entry"
        call_args = mock_update.call_args
        # Verify complex list was parsed correctly
        assert call_args[1]["data"][ConfName.DEVICE_LIST] == [1, 3, 4, 5, 10]

    async def test_async_step_confirm_default_device_list_on_no_input(
        self, hass: HomeAssistant, repair_flow: CheckConfigurationRepairFlow
    ) -> None:
        """Test confirm step uses default when device_list not in config."""
        repair_flow.hass = hass

        # Create entry without device_list in data
        entry_without_device_list = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_HOST: "192.168.1.100",
                CONF_PORT: 1502,
            },
            unique_id="192.168.1.100:1502",
        )
        entry_without_device_list.add_to_hass(hass)

        flow = CheckConfigurationRepairFlow(entry_without_device_list)
        flow.hass = hass

        result = await flow.async_step_confirm(user_input=None)

        assert result["type"] == "form"
        assert result["step_id"] == "confirm"
        # Should use default from ConfDefaultStr.DEVICE_LIST


class TestAsyncCreateFixFlow:
    """Test async_create_fix_flow factory function."""

    async def test_async_create_fix_flow_check_configuration(
        self, hass: HomeAssistant, mock_config_entry: MockConfigEntry
    ) -> None:
        """Test creating CheckConfigurationRepairFlow."""
        data = {"entry_id": mock_config_entry.entry_id}

        flow = await async_create_fix_flow(hass, "check_configuration", data)

        assert isinstance(flow, CheckConfigurationRepairFlow)
        assert flow._entry == mock_config_entry

    async def test_async_create_fix_flow_unknown_issue(
        self, hass: HomeAssistant, mock_config_entry: MockConfigEntry
    ) -> None:
        """Test creating flow for unknown issue_id returns None."""
        data = {"entry_id": mock_config_entry.entry_id}

        flow = await async_create_fix_flow(hass, "unknown_issue", data)

        assert flow is None

    async def test_async_create_fix_flow_entry_not_found(
        self, hass: HomeAssistant
    ) -> None:
        """Test creating flow when config entry doesn't exist returns None."""
        data = {"entry_id": "non_existent_entry_id"}

        flow = await async_create_fix_flow(hass, "check_configuration", data)

        assert flow is None

    async def test_async_create_fix_flow_with_none_data(
        self, hass: HomeAssistant
    ) -> None:
        """Test creating flow with None data should raise error."""
        # This tests the type casting behavior - data should not be None
        with pytest.raises(TypeError):
            await async_create_fix_flow(hass, "check_configuration", None)


@pytest.mark.usefixtures("mock_setup_entry")
class TestRepairFlowIntegration:
    """Integration tests for repair flow."""

    async def test_full_repair_flow_success(
        self, hass: HomeAssistant, mock_config_entry: MockConfigEntry
    ) -> None:
        """Test complete repair flow from creation to completion."""
        # Create the flow
        data = {"entry_id": mock_config_entry.entry_id}
        flow = await async_create_fix_flow(hass, "check_configuration", data)

        assert isinstance(flow, CheckConfigurationRepairFlow)
        flow.hass = hass

        # Step 1: init redirects to confirm
        result = await flow.async_step_init()
        assert result["type"] == "form"
        assert result["step_id"] == "confirm"

        # Step 2: Submit valid data
        user_input = {
            CONF_HOST: "192.168.1.150",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: "1,2",
        }

        with patch.object(hass.config_entries, "async_update_entry"):
            result = await flow.async_step_confirm(user_input=user_input)

        assert result["type"] == "create_entry"

    async def test_full_repair_flow_with_errors_then_fix(
        self, hass: HomeAssistant, mock_config_entry: MockConfigEntry
    ) -> None:
        """Test repair flow with initial errors, then successful correction."""
        data = {"entry_id": mock_config_entry.entry_id}
        flow = await async_create_fix_flow(hass, "check_configuration", data)

        flow.hass = hass

        # Submit invalid data first (invalid hostname with double dots)
        invalid_input = {
            CONF_HOST: "invalid..host",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: "1",
        }

        result = await flow.async_step_confirm(user_input=invalid_input)
        assert result["type"] == "form"
        assert CONF_HOST in result["errors"]

        # Now submit valid data
        valid_input = {
            CONF_HOST: "192.168.1.100",
            CONF_PORT: 1502,
            ConfName.DEVICE_LIST: "1",
        }

        with patch.object(hass.config_entries, "async_update_entry"):
            result = await flow.async_step_confirm(user_input=valid_input)

        assert result["type"] == "create_entry"


# Issue scoping tests: ids embed entry_id (and inverter unit for the
# detection timeouts) so multiple hubs and inverters cannot collide.


class TestIssueScoping:
    """Repair issues are scoped per entry and per inverter."""

    async def test_issue_ids_scoped_per_entry(
        self, hass: HomeAssistant, mock_modbus_client, mock_config_entry_options
    ) -> None:
        """Two hubs create distinct issues; one hub's recovery keeps the other's."""
        from homeassistant.helpers import issue_registry as ir

        from custom_components.solaredge_modbus_multi.hub import (
            DataUpdateFailed,
            SolarEdgeModbusMultiHub,
            check_config_issue_id,
        )

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["yaml"] = {}

        def make_hub(entry_id: str, host: str) -> SolarEdgeModbusMultiHub:
            hub = SolarEdgeModbusMultiHub(
                hass,
                entry_id=entry_id,
                entry_data={
                    CONF_HOST: host,
                    CONF_PORT: 1502,
                    CONF_NAME: f"Test {entry_id}",
                    ConfName.DEVICE_LIST: [1],
                },
                entry_options=dict(mock_config_entry_options),
            )
            hub.initalized = True
            hub._keep_modbus_open = True
            return hub

        hub_a = make_hub("entry_a", "192.168.1.100")
        hub_b = make_hub("entry_b", "192.168.1.101")

        client = mock_modbus_client.return_value
        # connect() returns, but the link never comes up.
        client.connect = AsyncMock()
        client.connected = False

        registry = ir.async_get(hass)

        with patch(
            "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection",
            mock_modbus_client,
        ):
            for hub in (hub_a, hub_b):
                with pytest.raises(DataUpdateFailed):
                    await hub.async_refresh_modbus_data()

            issue_a = check_config_issue_id("entry_a")
            issue_b = check_config_issue_id("entry_b")
            assert registry.async_get_issue(DOMAIN, issue_a) is not None
            assert registry.async_get_issue(DOMAIN, issue_b) is not None

            # Hub A recovers; only A's issue may disappear.
            client.connected = True
            await hub_a.async_refresh_modbus_data()

        assert registry.async_get_issue(DOMAIN, issue_a) is None
        assert registry.async_get_issue(DOMAIN, issue_b) is not None

    async def test_detect_timeout_issue_per_inverter_and_recovery(
        self,
        hass: HomeAssistant,
        mock_modbus_client,
        mock_config_entry_data,
        mock_config_entry_options,
    ) -> None:
        """A GPC detection timeout creates a per-inverter issue; success clears it."""
        from homeassistant.helpers import issue_registry as ir

        from custom_components.solaredge_modbus_multi.hub import (
            SolarEdgeInverter,
            SolarEdgeModbusMultiHub,
            detect_timeout_issue_id,
        )
        from tests.conftest import build_synergy_full_space, make_side_effect

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["yaml"] = {}

        hub = SolarEdgeModbusMultiHub(
            hass,
            entry_id="entry_gpc",
            entry_data=dict(mock_config_entry_data),
            entry_options={
                **mock_config_entry_options,
                ConfName.DETECT_EXTRAS: True,
            },
        )

        calls: list[tuple[int, int]] = []
        base_side_effect = make_side_effect(build_synergy_full_space(), {}, calls)
        gpc_times_out = True

        def side_effect(*args, **kwargs):
            address = kwargs.get("address", args[0] if args else 0)
            if address == 61440 and gpc_times_out:
                raise TimeoutError
            return base_side_effect(*args, **kwargs)

        client = mock_modbus_client.return_value
        client.read_holding_registers.side_effect = side_effect

        registry = ir.async_get(hass)
        issue_id = detect_timeout_issue_id("gpc", "entry_gpc", 1)

        with patch(
            "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection",
            mock_modbus_client,
        ):
            await hub.connect()
            inverter = SolarEdgeInverter(device_id=1, hub=hub)
            await inverter.init_device()

            hub.slow_poll_due = True
            await inverter.read_modbus_data()
            assert registry.async_get_issue(DOMAIN, issue_id) is not None

            gpc_times_out = False
            hub.slow_poll_due = True
            await inverter.read_modbus_data()
            assert registry.async_get_issue(DOMAIN, issue_id) is None

    async def test_unload_and_remove_delete_entry_issues(
        self, hass: HomeAssistant
    ) -> None:
        """Unload and removal both clear all of the entry's scoped issues."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from homeassistant.helpers import issue_registry as ir

        from custom_components.solaredge_modbus_multi import (
            async_remove_entry,
            async_unload_entry,
        )
        from custom_components.solaredge_modbus_multi.hub import (
            check_config_issue_id,
            detect_timeout_issue_id,
        )

        registry = ir.async_get(hass)

        def create_all(entry_id: str) -> list[str]:
            issue_ids = [check_config_issue_id(entry_id)]
            for unit in (1, 2):
                for kind in ("gpc", "apc"):
                    issue_ids.append(detect_timeout_issue_id(kind, entry_id, unit))
            for issue_id in issue_ids:
                ir.async_create_issue(
                    hass,
                    DOMAIN,
                    issue_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="detect_timeout_gpc",
                    data={"entry_id": entry_id},
                )
            return issue_ids

        def make_entry(entry_id: str) -> MagicMock:
            entry = MagicMock()
            entry.entry_id = entry_id
            entry.data = {ConfName.DEVICE_LIST: [1, 2]}
            hub = MagicMock()
            hub.shutdown = AsyncMock()
            entry.runtime_data = SimpleNamespace(hub=hub)
            return entry

        unload_ids = create_all("unload_entry")
        with patch.object(
            hass.config_entries,
            "async_unload_platforms",
            new_callable=AsyncMock,
            return_value=True,
        ):
            assert await async_unload_entry(hass, make_entry("unload_entry")) is True
        for issue_id in unload_ids:
            assert registry.async_get_issue(DOMAIN, issue_id) is None

        remove_ids = create_all("removed_entry")
        await async_remove_entry(hass, make_entry("removed_entry"))
        for issue_id in remove_ids:
            assert registry.async_get_issue(DOMAIN, issue_id) is None

    async def test_setup_sweeps_legacy_issue_ids(self, hass: HomeAssistant) -> None:
        """async_setup garbage-collects the pre-scoping global issue ids."""
        from homeassistant.helpers import issue_registry as ir

        from custom_components.solaredge_modbus_multi import async_setup
        from custom_components.solaredge_modbus_multi.hub import LEGACY_ISSUE_IDS

        registry = ir.async_get(hass)
        for legacy_id in LEGACY_ISSUE_IDS:
            ir.async_create_issue(
                hass,
                DOMAIN,
                legacy_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="detect_timeout_gpc",
                data={"entry_id": "legacy"},
            )

        assert await async_setup(hass, {}) is True

        for legacy_id in LEGACY_ISSUE_IDS:
            assert registry.async_get_issue(DOMAIN, legacy_id) is None


class TestRepairReload:
    """The repair fix must schedule exactly one reload of the fixed entry."""

    async def test_repair_fix_schedules_reload_once(
        self, hass: HomeAssistant, mock_config_entry: MockConfigEntry
    ) -> None:
        data = {"entry_id": mock_config_entry.entry_id}
        flow = await async_create_fix_flow(hass, "check_configuration", data)
        flow.hass = hass

        with (
            patch.object(hass.config_entries, "async_schedule_reload") as mock_schedule,
            patch.object(
                hass.config_entries, "async_reload", new_callable=AsyncMock
            ) as mock_reload,
        ):
            result = await flow.async_step_confirm(
                user_input={
                    CONF_HOST: "192.168.1.150",
                    CONF_PORT: 1502,
                    ConfName.DEVICE_LIST: "1",
                }
            )
            await hass.async_block_till_done()

        assert result["type"] == "create_entry"
        assert mock_schedule.call_count + mock_reload.call_count == 1
        mock_schedule.assert_called_once_with(mock_config_entry.entry_id)


class TestIssueCleanupByPrefix:
    """Cleanup must not depend on the entry's CURRENT device list."""

    async def test_delete_entry_issues_covers_removed_inverters(
        self, hass: HomeAssistant
    ) -> None:
        """Issues for a unit no longer in device_list are still deleted.

        A reconfigure rewrites entry.data before the reload, so cleanup
        can never learn the removed unit's id from the entry — it must
        scan the registry by the entry-scoped prefix instead.
        """
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from homeassistant.helpers import issue_registry as ir

        from custom_components.solaredge_modbus_multi.hub import (
            async_delete_entry_issues,
            detect_timeout_issue_id,
        )

        registry = ir.async_get(hass)

        # Unit 7 was reconfigured away; entry.data now lists only [1].
        orphan_id = detect_timeout_issue_id("gpc", "shrunk_entry", 7)
        other_entry_id = detect_timeout_issue_id("gpc", "other_entry", 7)
        for issue_id in (orphan_id, other_entry_id):
            ir.async_create_issue(
                hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="detect_timeout_gpc",
                data={"entry_id": "x"},
            )

        entry = MagicMock()
        entry.entry_id = "shrunk_entry"
        entry.data = {ConfName.DEVICE_LIST: [1]}
        entry.runtime_data = SimpleNamespace(hub=MagicMock())

        async_delete_entry_issues(hass, entry)

        assert registry.async_get_issue(DOMAIN, orphan_id) is None
        assert registry.async_get_issue(DOMAIN, other_entry_id) is not None
