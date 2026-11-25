"""Describe SolarEdge Modbus Multi logbook events."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from homeassistant.components.logbook import LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import (
    ATTR_EVENTS_TEXT,
    ATTR_STATUS_TEXT,
    ATTR_STATUS_VALUE,
    DEFAULT_NAME,
    DOMAIN,
    EVENT_METER_EVENTS,
    EVENT_PROBLEM,
    EVENT_STATUS_VENDOR,
)


def _status(data: Mapping[str, Any]) -> str | None:
    """Return the status text and value, or None when neither is known."""
    value = data.get(ATTR_STATUS_VALUE)
    text = data.get(ATTR_STATUS_TEXT)
    if text is not None:
        return f"{text} ({value})"
    if value is not None:
        return f"Status {value}"
    return None


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, str]]], None],
) -> None:
    """Describe logbook events.

    The name is the cause and the message is the device. The "what happened"
    box in the frontend shows only the name of an integration's event, so the
    cause must be in the name to be seen there.
    """

    @callback
    def _device_name(data: Mapping[str, Any]) -> str:
        """Return the device name, preferring the user's name."""
        if (device_id := data.get(ATTR_DEVICE_ID)) and (
            device := dr.async_get(hass).async_get(device_id)
        ):
            return device.name_by_user or device.name or DEFAULT_NAME
        return DEFAULT_NAME

    @callback
    def async_describe_problem_event(event: Event) -> dict[str, str]:
        """Describe a fault being reported."""
        data = event.data

        if events := data.get(ATTR_EVENTS_TEXT):
            name = "; ".join(events)
        else:
            name = _status(data) or "Fault"

        return {LOGBOOK_ENTRY_NAME: name, LOGBOOK_ENTRY_MESSAGE: _device_name(data)}

    @callback
    def async_describe_status_vendor_event(event: Event) -> dict[str, str]:
        """Describe a vendor status code change."""
        data = event.data
        name = _status(data) or "Status unknown"

        return {LOGBOOK_ENTRY_NAME: name, LOGBOOK_ENTRY_MESSAGE: _device_name(data)}

    @callback
    def async_describe_meter_events_event(event: Event) -> dict[str, str]:
        """Describe a meter event bits change."""
        data = event.data
        if events := data.get(ATTR_EVENTS_TEXT):
            name = "; ".join(events)
        else:
            name = "No meter events"

        return {LOGBOOK_ENTRY_NAME: name, LOGBOOK_ENTRY_MESSAGE: _device_name(data)}

    async_describe_event(DOMAIN, EVENT_PROBLEM, async_describe_problem_event)
    async_describe_event(
        DOMAIN, EVENT_STATUS_VENDOR, async_describe_status_vendor_event
    )
    async_describe_event(DOMAIN, EVENT_METER_EVENTS, async_describe_meter_events_event)
