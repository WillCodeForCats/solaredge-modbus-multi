"""Tests for detecting a replaced inverter and the repair that migrates it."""

from types import SimpleNamespace

from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from modbus_connection.mock import MockModbusConnection
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solaredge_modbus_multi.const import DOMAIN
from custom_components.solaredge_modbus_multi.hub import SolarEdgeModbusMultiHub
from custom_components.solaredge_modbus_multi.repairs import DeviceReplacedRepairFlow

ENTRY_DATA = {
    CONF_NAME: "SolarEdge",
    CONF_HOST: "127.0.0.1",
    CONF_PORT: 1502,
}

OLD_MODEL = "SE7600H-US000BNU4"
OLD_SERIAL = "AAAA1111"
NEW_MODEL = "SE10000H-US000BNU4"
NEW_SERIAL = "BBBB2222"


def _make_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="127.0.0.1:1502", data=ENTRY_DATA)
    entry.add_to_hass(hass)
    return entry


def _make_hub(hass, entry: MockConfigEntry) -> SolarEdgeModbusMultiHub:
    hass.data[DOMAIN] = {"yaml": {}}
    return SolarEdgeModbusMultiHub(
        hass, entry.entry_id, ENTRY_DATA, {}, MockModbusConnection()
    )


def _mock_inverter(unit_id: int, model: str, serial: str) -> SimpleNamespace:
    """Build a minimal stand-in for SolarEdgeInverter.

    check_inverter_replaced() only reads inverter_unit_id/model/serial/uid_base.
    """
    return SimpleNamespace(
        inverter_unit_id=unit_id,
        model=model,
        serial=serial,
        uid_base=f"{model}_{serial}",
    )


def _make_flow(hass, issue_id: str, data: dict) -> DeviceReplacedRepairFlow:
    """Build a repair flow the way RepairsFlowManager does.

    (hass/issue_id/data are normally set by the manager after construction --
    see homeassistant.components.repairs.issue_handler.async_create_flow.)
    """
    flow = DeviceReplacedRepairFlow()
    flow.hass = hass
    flow.issue_id = issue_id
    flow.data = data
    return flow


def _seed_existing_device(hass, entry: MockConfigEntry, unit_id: int):
    """Simulate a previous boot: an inverter already known at this Device ID."""
    device_registry = dr.async_get(hass)
    anchor = f"{entry.entry_id}_inverter_{unit_id}"
    old_uid_base = f"{OLD_MODEL}_{OLD_SERIAL}"

    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, old_uid_base), (DOMAIN, anchor)},
        manufacturer="SolarEdge",
        model=OLD_MODEL,
        serial_number=OLD_SERIAL,
    )
    return device, anchor, old_uid_base


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_no_issue_on_first_boot(hass):
    """No prior device at this ID -- nothing to compare against."""
    entry = _make_entry(hass)
    hub = _make_hub(hass, entry)

    hub.check_inverter_replaced(_mock_inverter(1, NEW_MODEL, NEW_SERIAL))

    issue_id = f"device_replaced_{entry.entry_id}_1"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_no_issue_when_unchanged(hass):
    """Same model/serial as last boot -- not a replacement."""
    entry = _make_entry(hass)
    hub = _make_hub(hass, entry)
    _seed_existing_device(hass, entry, 1)

    hub.check_inverter_replaced(_mock_inverter(1, OLD_MODEL, OLD_SERIAL))

    issue_id = f"device_replaced_{entry.entry_id}_1"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_issue_created_on_replacement(hass):
    """A different serial at a known unit ID raises the device_replaced issue."""
    entry = _make_entry(hass)
    hub = _make_hub(hass, entry)
    _seed_existing_device(hass, entry, 1)

    hub.check_inverter_replaced(_mock_inverter(1, NEW_MODEL, NEW_SERIAL))

    issue_id = f"device_replaced_{entry.entry_id}_1"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)

    assert issue is not None
    assert issue.data["old_uid_base"] == f"{OLD_MODEL}_{OLD_SERIAL}"
    assert issue.data["new_uid_base"] == f"{NEW_MODEL}_{NEW_SERIAL}"
    assert issue.data["old_model"] == OLD_MODEL
    assert issue.data["new_model"] == NEW_MODEL


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_migrate_preserves_entity_id_and_history(hass):
    """Migrating renames the old entity's unique_id onto the new hardware.

    The old entity must not be left orphaned next to a fresh duplicate.
    """
    entry = _make_entry(hass)
    hub = _make_hub(hass, entry)
    device, anchor, old_uid_base = _seed_existing_device(hass, entry, 1)
    new_uid_base = f"{NEW_MODEL}_{NEW_SERIAL}"

    entity_registry = er.async_get(hass)
    old_entity = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{old_uid_base}_ac_power",
        config_entry=entry,
        device_id=device.id,
    )
    old_entity_id = old_entity.entity_id

    # A normal boot already created the fresh entity for the replacement
    # hardware, under its own unique_id, before the user reaches the repair.
    entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{new_uid_base}_ac_power",
        config_entry=entry,
        device_id=device.id,
    )

    live_inverter = SimpleNamespace(
        inverter_unit_id=1,
        model=NEW_MODEL,
        serial=NEW_SERIAL,
        uid_base=new_uid_base,
        anchor=anchor,
        mmppt_units=[],
    )
    hub.inverters = [live_inverter]
    hub.meters = []
    hub.batteries = []
    hub.der_batteries = []
    hass.data[DOMAIN][entry.entry_id] = {"hub": hub}

    issue_id = f"device_replaced_{entry.entry_id}_1"
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="device_replaced",
        data={
            "entry_id": entry.entry_id,
            "device_id": 1,
            "old_uid_base": old_uid_base,
            "new_uid_base": new_uid_base,
            "old_model": OLD_MODEL,
            "old_serial": OLD_SERIAL,
            "new_model": NEW_MODEL,
            "new_serial": NEW_SERIAL,
        },
    )
    issue_data = ir.async_get(hass).async_get_issue(DOMAIN, issue_id).data
    flow = _make_flow(hass, issue_id, issue_data)

    result = await flow.async_step_migrate()
    assert result["type"] == "create_entry"

    # The original entity_id survives, now backed by the new unique_id.
    migrated = entity_registry.async_get(old_entity_id)
    assert migrated.unique_id == f"{new_uid_base}_ac_power"

    # The duplicate fresh entity was removed rather than left dangling.
    assert (
        entity_registry.async_get_entity_id(
            "sensor", DOMAIN, f"{new_uid_base}_ac_power"
        )
        == old_entity_id
    )

    # Issue deletion on success is RepairsFlowManager's job (it does this for
    # every repair after a step returns create_entry, not something this flow
    # does itself -- see async_finish_flow), so it isn't exercised by calling
    # async_step_migrate() directly here.

    # Device identifiers no longer carry the stale old uid_base.
    device_registry = dr.async_get(hass)
    refreshed = device_registry.async_get_device(identifiers={(DOMAIN, anchor)})
    assert refreshed.identifiers == {(DOMAIN, anchor), (DOMAIN, new_uid_base)}


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_ignore_cleans_up_without_touching_entities(hass):
    """Ignoring clears the issue and leaves existing entities as they are."""
    entry = _make_entry(hass)
    hub = _make_hub(hass, entry)
    device, anchor, old_uid_base = _seed_existing_device(hass, entry, 1)
    new_uid_base = f"{NEW_MODEL}_{NEW_SERIAL}"

    entity_registry = er.async_get(hass)
    old_entity = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{old_uid_base}_ac_power",
        config_entry=entry,
        device_id=device.id,
    )

    live_inverter = SimpleNamespace(
        inverter_unit_id=1,
        model=NEW_MODEL,
        serial=NEW_SERIAL,
        uid_base=new_uid_base,
        anchor=anchor,
        mmppt_units=[],
    )
    hub.inverters = [live_inverter]
    hub.meters = []
    hub.batteries = []
    hub.der_batteries = []
    hass.data[DOMAIN][entry.entry_id] = {"hub": hub}

    issue_id = f"device_replaced_{entry.entry_id}_1"
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="device_replaced",
        data={
            "entry_id": entry.entry_id,
            "device_id": 1,
            "old_uid_base": old_uid_base,
            "new_uid_base": new_uid_base,
            "old_model": OLD_MODEL,
            "old_serial": OLD_SERIAL,
            "new_model": NEW_MODEL,
            "new_serial": NEW_SERIAL,
        },
    )
    issue_data = ir.async_get(hass).async_get_issue(DOMAIN, issue_id).data
    flow = _make_flow(hass, issue_id, issue_data)

    result = await flow.async_step_ignore()
    assert result["type"] == "create_entry"

    # Old entity untouched -- still pointing at the old, now-orphaned unique_id.
    assert entity_registry.async_get(old_entity.entity_id).unique_id == (
        f"{old_uid_base}_ac_power"
    )
