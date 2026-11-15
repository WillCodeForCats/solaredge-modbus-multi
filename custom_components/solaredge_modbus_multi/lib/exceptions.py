"""Exceptions raised by the SolarEdge protocol code."""

from __future__ import annotations


class SolarEdgeException(Exception):
    """Base class for other exceptions."""


class HubInitFailed(SolarEdgeException):
    """Raised when an error happens during init."""


class DeviceIsEVSE(SolarEdgeException):
    """Raised when an inverter device matches a EVSE model."""


class DataUpdateFailed(SolarEdgeException):
    """Raised when an update cycle fails."""


class DataUpdateTimedOut(SolarEdgeException):
    """Raised when an update cycle does not finish within the watchdog.

    Not a DataUpdateFailed, so the coordinator does not retry it: whatever held
    up this cycle would hold up each retry for the whole watchdog as well.
    """


class DeviceInvalid(SolarEdgeException):
    """Raised when a device is not usable or invalid."""


class DeviceListError(SolarEdgeException):
    """Raised when a device ID or device ID list is invalid.

    The message is an error key ("invalid_device_id", "invalid_range_format",
    ...) that the config and repair flows show as a translated form error.
    """
