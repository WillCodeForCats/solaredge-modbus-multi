"""Component to interface with buttons."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from modbus_connection.encode import encode_uint16

from . import SolarEdgeConfigEntry
from .entity import SolarEdgeEntityBase

_LOGGER = logging.getLogger(__name__)

# Writes go to an inverter with a single Modbus session; one service call
# at a time per platform (the transport lock is the real guard).
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: SolarEdgeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    hub = config_entry.runtime_data.hub
    coordinator = config_entry.runtime_data.coordinator

    entities = []

    for inverter in hub.inverters:
        # Refresh only re-reads; it is the one button that never writes.
        entities.append(SolarEdgeRefreshButton(inverter, config_entry, coordinator))

        if not hub.option_allow_hardware_writes:
            continue

        """ Power Control Block """
        if inverter.apc_may_be_supported:
            entities.append(
                SolarEdgeCommitControlSettings(inverter, config_entry, coordinator)
            )
            entities.append(
                SolarEdgeDefaultControlSettings(inverter, config_entry, coordinator)
            )

    if entities:
        async_add_entities(entities)


class SolarEdgeButtonBase(SolarEdgeEntityBase, ButtonEntity):
    """Base class for SolarEdge button entities."""

    uid_suffix: str | None = None

    def __init__(self, platform, config_entry, coordinator) -> None:
        super().__init__(platform, config_entry, coordinator)
        if self.uid_suffix is not None:
            self._attr_unique_id = f"{platform.uid_base}_{self.uid_suffix}"


class SolarEdgeRefreshButton(SolarEdgeButtonBase):
    """Button to request an immediate device data update."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:refresh"
    _attr_name = "Refresh"
    uid_suffix = "refresh"

    @property
    def available(self) -> bool:
        return True

    async def async_press(self) -> None:
        await self.async_update()


class SolarEdgeAdvancedPowerControlButton(SolarEdgeButtonBase):
    """A button that writes 1 to an Advanced Power Control register.

    These exist before detection resolves, so both the entity and the write
    itself are gated on confirmed APC support: pressing one commits settings
    to inverter flash, which must never happen on an unverified capability.
    """

    _write_address: int

    @property
    def available(self) -> bool:
        return super().available and self._platform.advanced_power_control is True

    def _assert_supported(self) -> None:
        if self._platform.advanced_power_control is not True:
            raise HomeAssistantError(
                "Advanced Power Control is not confirmed on inverter ID "
                f"{self._platform.inverter_unit_id}; refusing to write."
            )

    async def async_press(self) -> None:
        _LOGGER.debug(f"set {self.unique_id} to 1")

        self._assert_supported()
        await self._platform.write_registers(
            address=self._write_address,
            payload=encode_uint16(1),
        )
        await self.async_update()


class SolarEdgeCommitControlSettings(SolarEdgeAdvancedPowerControlButton):
    """Button to Commit Power Control Settings."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:content-save-cog-outline"
    _attr_name = "Commit Power Settings"
    _write_address = 61696

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}bt_commit_pwr_settings"


class SolarEdgeDefaultControlSettings(SolarEdgeAdvancedPowerControlButton):
    """Button to Restore Power Control Default Settings."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:restore-alert"
    _attr_name = "Default Power Settings"
    _write_address = 61697

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}bt_default_pwr_settings"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False
