"""Base entity for the SolarEdge Modbus Multi integration."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import SolarEdgeConfigEntry, SolarEdgeCoordinator


class SolarEdgeEntity(CoordinatorEntity[SolarEdgeCoordinator]):
    """Base class for SolarEdge Modbus Multi entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        platform,
        config_entry: SolarEdgeConfigEntry,
        coordinator: SolarEdgeCoordinator,
    ) -> None:
        """Initialize the entity for a SolarEdge device."""
        super().__init__(coordinator)
        self._platform = platform
        self._config_entry = config_entry
        self._attr_device_info = platform.device_info

    @callback
    def _async_schedule_refresh(self) -> None:
        """Request a coordinator refresh without waiting for it."""
        self._config_entry.async_create_background_task(
            self.hass,
            self.coordinator.async_request_refresh(),
            f"{self.entity_id} refresh after action",
        )

    @property
    def config_entry_id(self):
        """Return the config entry id."""
        return self._config_entry.entry_id

    @property
    def config_entry_name(self):
        """Return the config entry name."""
        return self._config_entry.data["name"]
