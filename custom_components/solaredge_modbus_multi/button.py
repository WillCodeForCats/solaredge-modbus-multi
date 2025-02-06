"""Component to interface with binary sensors."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from pymodbus.client.mixin import ModbusClientMixin

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub = hass.data[DOMAIN][config_entry.entry_id]["hub"]
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    entities = []

    for inverter in hub.inverters:
        entities.append(SolarEdgeRefreshButton(inverter, config_entry, coordinator))

        """ Power Control Block """
        if hub.option_detect_extras and inverter.advanced_power_control:
            entities.append(
                SolarEdgeCommitControlSettings(inverter, config_entry, coordinator)
            )
            entities.append(
                SolarEdgeDefaultControlSettings(inverter, config_entry, coordinator)
            )

    if entities:
        async_add_entities(entities)


class SolarEdgeButtonBase(CoordinatorEntity, ButtonEntity):
    """Base class for SolarEdge button entities."""

    _attr_has_entity_name = True

    def __init__(self, platform, config_entry, coordinator):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        """Initialize the sensor."""
        self._platform = platform
        self._config_entry = config_entry

    @property
    def device_info(self):
        return self._platform.device_info

    @property
    def config_entry_id(self):
        return self._config_entry.entry_id

    @property
    def config_entry_name(self):
        return self._config_entry.data["name"]

    @property
    def available(self) -> bool:
        return super().available and self._platform.online

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class SolarEdgeRefreshButton(SolarEdgeButtonBase):
    """Button to request an immediate device data update."""

    entity_category = EntityCategory.CONFIG
    icon = "mdi:refresh"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_refresh"

    @property
    def name(self) -> str:
        return "Refresh"

    @property
    def available(self) -> bool:
        return True

    async def async_press(self) -> None:
        await self.async_update()


class SolarEdgeCommitControlSettings(SolarEdgeButtonBase):
    """Button to Commit Power Control Settings."""

    entity_category = EntityCategory.CONFIG
    icon = "mdi:content-save-cog-outline"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}bt_commit_pwr_settings"

    @property
    def name(self) -> str:
        return "Commit Power Settings"

    async def async_press(self) -> None:
        _LOGGER.debug(f"set {self.unique_id} to 1")

        await self._platform.write_registers(
            address=61696,
            payload=ModbusClientMixin.convert_to_registers(
                1, data_type=ModbusClientMixin.DATATYPE.UINT16, word_order="little"
            ),
        )
        await self.async_update()


class SolarEdgeDefaultControlSettings(SolarEdgeButtonBase):
    """Button to Restore Power Control Default Settings."""

    entity_category = EntityCategory.CONFIG
    icon = "mdi:restore-alert"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}bt_default_pwr_settings"

    @property
    def name(self) -> str:
        return "Default Power Settings"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    async def async_press(self) -> None:
        _LOGGER.debug(f"set {self.unique_id} to 1")

        await self._platform.write_registers(
            address=61697,
            payload=ModbusClientMixin.convert_to_registers(
                1, data_type=ModbusClientMixin.DATATYPE.UINT16, word_order="little"
            ),
        )
        await self.async_update()
