"""Component to interface with binary sensors."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import SolarEdgeEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setup entry."""
    hub = hass.data[DOMAIN][config_entry.entry_id]["hub"]
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    entities = []

    for inverter in hub.inverters:
        entities.append(SolarEdgeRefreshButton(inverter, config_entry, coordinator))

        """ Power Control Block """
        if hub.option_detect_extras:
            entities.append(
                SolarEdgeCommitControlSettings(inverter, config_entry, coordinator)
            )
            entities.append(
                SolarEdgeDefaultControlSettings(inverter, config_entry, coordinator)
            )

    if entities:
        async_add_entities(entities)


class SolarEdgeButtonBase(SolarEdgeEntity, ButtonEntity):
    """Base class for SolarEdge button entities."""


class SolarEdgeRefreshButton(SolarEdgeButtonBase):
    """Button to request an immediate device data update."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:refresh"
    _attr_name = "Refresh"

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the entity."""
        super().__init__(platform, config_entry, coordinator)
        self._attr_unique_id = f"{platform.uid_base}_refresh"

    @property
    def available(self) -> bool:
        """Return the available."""
        return True

    async def async_press(self) -> None:
        """Press."""
        await self.async_update()


class SolarEdgeCommitControlSettings(SolarEdgeButtonBase):
    """Button to Commit Power Control Settings."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:content-save-cog-outline"
    _attr_name = "Commit Power Settings"

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the entity."""
        super().__init__(platform, config_entry, coordinator)
        self._attr_unique_id = f"{platform.uid_base}bt_commit_pwr_settings"

    @property
    def available(self) -> bool:
        """Return the available."""
        return super().available and self._platform.has_advanced_power_control

    async def async_press(self) -> None:
        """Press."""
        _LOGGER.debug("set %s to 1", self.unique_id)

        await self._platform.write(
            self._platform.advanced_power_control_data, "CommitPwrCtlSettings", 1
        )
        await self.async_update()


class SolarEdgeDefaultControlSettings(SolarEdgeButtonBase):
    """Button to Restore Power Control Default Settings."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:restore-alert"
    _attr_name = "Default Power Settings"
    _attr_entity_registry_enabled_default = False

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the entity."""
        super().__init__(platform, config_entry, coordinator)
        self._attr_unique_id = f"{platform.uid_base}bt_default_pwr_settings"

    @property
    def available(self) -> bool:
        """Return the available."""
        return super().available and self._platform.has_advanced_power_control

    async def async_press(self) -> None:
        """Press."""
        _LOGGER.debug("set %s to 1", self.unique_id)

        await self._platform.write(
            self._platform.advanced_power_control_data, "RestorePwrCtlDefaults", 1
        )
        await self.async_update()
