"""Child devices link to their inverter by device-registry id.

Meters, batteries and MPPT units used to carry ``via_device=(DOMAIN, uid)``,
which Home Assistant deprecated in 2026.8 (removed in 2027.8). They now carry
``via_device_id``: the inverter's registry id, known only once the inverter
has been registered, so the key is omitted until then.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solaredge_modbus_multi.const import DOMAIN
from custom_components.solaredge_modbus_multi.devices import (
    SolarEdgeBattery,
    SolarEdgeInverter,
    SolarEdgeMeter,
    SolarEdgeMMPPTUnit,
)
from custom_components.solaredge_modbus_multi.hub import SolarEdgeModbusMultiHub


@pytest.fixture
def config_entry(hass, mock_config_entry_data, mock_config_entry_options):
    """A config entry the registry knows about (a MagicMock is rejected)."""
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
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def hub(hass, config_entry, mock_config_entry_data, mock_config_entry_options):
    """A real hub, never connected."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["yaml"] = {}
    return SolarEdgeModbusMultiHub(
        hass,
        entry_id=config_entry.entry_id,
        entry_data=mock_config_entry_data,
        entry_options=mock_config_entry_options,
    )


def _make_devices(hub):
    """One inverter with an MPPT unit, a meter and a battery, as after discovery.

    The constructors do not populate the identity fields device_info reads;
    the hub's init path does that from decoded registers. Set them directly.
    """
    hub.inverter_common[1] = {"C_Model": "SE10K", "C_SerialNumber": "INV123"}
    hub.mmppt_common[1] = None

    inverter = SolarEdgeInverter(device_id=1, hub=hub)
    inverter.decoded_common = {"C_Version": "0004.0020.0001"}
    inverter.decoded_model = {"mmppt_1": {"ID": 1, "IDStr": "String 1"}}
    inverter.manufacturer = "SolarEdge"
    inverter.model = "SE10K"
    inverter.option = ""
    inverter.serial = "INV123"
    inverter.name = "Test I1"
    inverter.uid_base = "SE10K_INV123"

    mmppt = SolarEdgeMMPPTUnit(inverter, hub, 1)

    meter = SolarEdgeMeter(device_id=1, meter_id=1, hub=hub)
    meter.manufacturer = "SolarEdge"
    meter.model = "WND-3Y-400-MB"
    meter.option = ""
    meter.fw_version = "1.0"
    meter.serial = "MTR1"
    meter.name = "Test I1 M1"
    meter.uid_base = "SE10K_INV123_M1"
    meter.inverter = inverter

    battery = SolarEdgeBattery(device_id=1, battery_id=1, hub=hub)
    battery.manufacturer = "SolarEdge"
    battery.model = "BAT-10K1PS0B-01"
    battery.fw_version = "2.0"
    battery.serial = "BAT1"
    battery.name = "Test I1 B1"
    battery.uid_base = "SE10K_INV123_B1"
    battery.inverter = inverter

    return inverter, mmppt, meter, battery


async def test_children_omit_link_until_inverter_registered(hass, hub) -> None:
    """No via_device_id (and no deprecated via_device) before registration."""
    inverter, *children = _make_devices(hub)

    for child in children:
        assert child.via_device_id is None
        assert "via_device_id" not in child.device_info
        assert "via_device" not in child.device_info

    inverter.registry_device_id = "0123456789abcdef0123456789abcdef"

    for child in children:
        assert child.via_device_id == inverter.registry_device_id
        assert child.device_info["via_device_id"] == inverter.registry_device_id
        assert "via_device" not in child.device_info


async def test_children_link_to_inverter_in_registry(
    hass: HomeAssistant, hub, config_entry
) -> None:
    """Registering a child's device_info links it to the inverter's entry."""
    inverter, *children = _make_devices(hub)
    registry = dr.async_get(hass)

    inverter_entry = registry.async_get_or_create(
        config_entry_id=config_entry.entry_id, **inverter.device_info
    )
    inverter.registry_device_id = inverter_entry.id

    for child in children:
        child_entry = registry.async_get_or_create(
            config_entry_id=config_entry.entry_id, **child.device_info
        )
        assert child_entry.id != inverter_entry.id
        assert child_entry.via_device_id == inverter_entry.id


async def test_reregistration_keeps_device_id_and_link(
    hass: HomeAssistant, hub, config_entry
) -> None:
    """Every restart re-registers: the child keeps its id and its parent."""
    inverter, _mmppt, meter, _battery = _make_devices(hub)
    registry = dr.async_get(hass)

    inverter_entry = registry.async_get_or_create(
        config_entry_id=config_entry.entry_id, **inverter.device_info
    )
    inverter.registry_device_id = inverter_entry.id
    first = registry.async_get_or_create(
        config_entry_id=config_entry.entry_id, **meter.device_info
    )

    second = registry.async_get_or_create(
        config_entry_id=config_entry.entry_id, **meter.device_info
    )

    assert second.id == first.id
    assert second.via_device_id == inverter_entry.id


async def test_omitted_link_preserves_existing_link(
    hass: HomeAssistant, hub, config_entry
) -> None:
    """An absent via_device_id leaves the stored link alone (None would clear it)."""
    inverter, _mmppt, meter, _battery = _make_devices(hub)
    registry = dr.async_get(hass)

    inverter_entry = registry.async_get_or_create(
        config_entry_id=config_entry.entry_id, **inverter.device_info
    )
    inverter.registry_device_id = inverter_entry.id
    first = registry.async_get_or_create(
        config_entry_id=config_entry.entry_id, **meter.device_info
    )
    assert first.via_device_id == inverter_entry.id

    inverter.registry_device_id = None
    assert "via_device_id" not in meter.device_info
    second = registry.async_get_or_create(
        config_entry_id=config_entry.entry_id, **meter.device_info
    )

    assert second.id == first.id
    assert second.via_device_id == inverter_entry.id
