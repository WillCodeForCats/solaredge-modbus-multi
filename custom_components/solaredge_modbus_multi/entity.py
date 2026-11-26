"""Base entity for the SolarEdge Modbus Multi integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import Context, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_ERROR_ENTITY_ID, DOMAIN
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

    The event carries the device but not the entity, so the entity's own
    logbook only uses it as the cause and does not also list it as an entry.
    It also carries the device's Error sensor under a different key, which
    the logbook platform links the entry to.

    Entities of one device with the same _cause_group share the event: the
    first to record a cause in a poll fires it, and the others in that poll
    write their state under the same context. The platform must provide a
    cause_contexts dict for this.
    """

    _cause_event: str
    _cause_group: str | None = None
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

        if (context := self._async_shared_cause_context()) is None:
            context = Context()
            event_data = {
                ATTR_DEVICE_ID: (
                    self.registry_entry.device_id if self.registry_entry else None
                ),
                **data,
            }
            if (error_entity_id := self._async_error_entity_id()) is not None:
                event_data[ATTR_ERROR_ENTITY_ID] = error_entity_id
            self.hass.bus.async_fire(self._cause_event, event_data, context=context)
            if self._cause_group is not None:
                self._platform.cause_contexts[self._cause_group] = (
                    self.coordinator.last_update_success_time,
                    context,
                )
        self._cause_context = context
        self.async_set_context(context)

    @callback
    def _async_error_entity_id(self) -> str | None:
        """Return the entity id of this device's Error sensor, if registered."""
        return er.async_get(self.hass).async_get_entity_id(
            SENSOR_DOMAIN, DOMAIN, f"{self._platform.uid_base}_error"
        )

    @callback
    def _async_shared_cause_context(self) -> Context | None:
        """Return the context of the group's event fired in this poll, if any."""
        if self._cause_group is None:
            return None
        shared = self._platform.cause_contexts.get(self._cause_group)
        if shared is None or shared[0] != self.coordinator.last_update_success_time:
            return None
        return shared[1]

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
