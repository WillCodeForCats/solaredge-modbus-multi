"""Describe SolarEdge Modbus Multi logbook events."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.logbook import LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import (
    ATTR_PROBLEM,
    ATTR_STATUS_TEXT,
    ATTR_STATUS_VALUE,
    DEFAULT_NAME,
    DOMAIN,
    EVENT_PROBLEM,
)


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, str]]], None],
) -> None:
    """Describe logbook events."""

    @callback
    def async_describe_problem_event(event: Event) -> dict[str, str]:
        """Describe a problem sensor turning on or off."""
        data = event.data

        name = DEFAULT_NAME
        if (device_id := data.get(ATTR_DEVICE_ID)) and (
            device := dr.async_get(hass).async_get(device_id)
        ):
            name = device.name_by_user or device.name or name

        if not data.get(ATTR_PROBLEM):
            message = "problem cleared"
        else:
            value = data.get(ATTR_STATUS_VALUE)
            text = data.get(ATTR_STATUS_TEXT)
            if text is not None:
                message = f"reported a fault: {text} ({value})"
            elif value is not None:
                message = f"reported a fault: status {value}"
            else:
                message = "reported a fault"

        return {LOGBOOK_ENTRY_NAME: name, LOGBOOK_ENTRY_MESSAGE: message}

    async_describe_event(DOMAIN, EVENT_PROBLEM, async_describe_problem_event)
