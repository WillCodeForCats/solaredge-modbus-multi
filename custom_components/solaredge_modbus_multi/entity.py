"""Base entity for the SolarEdge Modbus Multi integration."""

from __future__ import annotations

from typing import Any

from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID
from homeassistant.core import Context, callback
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

    @property
    def config_entry_id(self):
        """Return the config entry id."""
        return self._config_entry.entry_id

    @property
    def config_entry_name(self):
        """Return the config entry name."""
        return self._config_entry.data["name"]


class SolarEdgeCauseEntity(SolarEdgeEntity):
    """Entity that records the cause of its state changes in the logbook.

    When the tracked value changes, an event is fired and the state is
    written under that event's context. The logbook platform describes the
    event, which fills in the cause shown for the state change.
    """

    _cause_event: str
    _last_cause_value: Any = None
    _cause_context: Context | None = None

    def _cause_value(self) -> Any:
        """Return the value whose changes are recorded."""
        raise NotImplementedError

    def _cause_data(self, value: Any, last_value: Any) -> dict[str, Any] | None:
        """Return event data for a change, or None to not record it.

        last_value is None at startup and after being unavailable.
        """
        raise NotImplementedError

    @callback
    def _async_record_cause(self) -> None:
        """Fire the cause event and use its context if the value changed."""
        if (data := self._async_cause_data()) is None:
            # Entity keeps a context for several seconds, so a later write
            # would still be linked to the last cause. Replace it with a
            # context that has no cause.
            if self._cause_context is not None:
                self._cause_context = None
                self.async_set_context(Context())
            return

        context = Context()
        self.hass.bus.async_fire(
            self._cause_event,
            {
                ATTR_DEVICE_ID: (
                    self.registry_entry.device_id if self.registry_entry else None
                ),
                ATTR_ENTITY_ID: self.entity_id,
                **data,
            },
            context=context,
        )
        self._cause_context = context
        self.async_set_context(context)

    @callback
    def _async_cause_data(self) -> dict[str, Any] | None:
        """Track the value and return event data if a change is recorded."""
        if not self.available:
            self._last_cause_value = None
            return None

        value = self._cause_value()
        last_value = self._last_cause_value
        self._last_cause_value = value

        if value == last_value:
            return None
        return self._cause_data(value, last_value)

    async def async_added_to_hass(self) -> None:
        """Record the cause of the first state."""
        await super().async_added_to_hass()
        self._async_record_cause()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Record the cause, then write the state."""
        self._async_record_cause()
        super()._handle_coordinator_update()
