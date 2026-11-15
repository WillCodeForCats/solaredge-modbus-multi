"""Per-request retries for modbus-connection reads, writes and SunSpec scans."""

from __future__ import annotations

import logging

from modbus_connection.exceptions import (
    ModbusConnectionError,
    ModbusProtocolError,
    ModbusTimeoutError,
)
from modbus_connection.model.sunspec import scan as suns_scan

from .const import REQUEST_RETRIES

_LOGGER = logging.getLogger(__name__)


async def async_update_with_retry(component) -> None:
    """Call component.async_update(), retrying connection/timeout errors.

    modbus-connection has no built-in per-request retry, unlike pymodbus's
    `retries` option, so this method mimics that behavior.
    """
    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            await component.async_update()

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:  # noqa: PERF203
            _LOGGER.debug(
                "%s.async_update() attempt %s of %s failed: %s",
                type(component).__name__,
                attempt,
                REQUEST_RETRIES,
                e,
            )

            if attempt >= REQUEST_RETRIES:
                raise

        else:
            return


async def async_write_with_retry(component, field: str, value) -> None:
    """Call component.write(field, value), retrying connection/timeout errors.

    Like async_update_with_retry() but for writes.
    """
    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            await component.write(field, value)

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:  # noqa: PERF203
            _LOGGER.debug(
                "%s.write(%r) attempt %s of %s failed: %s",
                type(component).__name__,
                field,
                attempt,
                REQUEST_RETRIES,
                e,
            )

            if attempt >= REQUEST_RETRIES:
                raise

        else:
            return


async def async_suns_scan_with_retry(connection, base_address: int):
    """Call suns_scan(), retrying connection/timeout errors.

    Like async_update_with_retry() but for the SunSpec model scan.
    """
    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            models = await suns_scan(connection, base_address)

        except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError) as e:  # noqa: PERF203
            _LOGGER.debug(
                "suns_scan() attempt %s of %s failed: %s",
                attempt,
                REQUEST_RETRIES,
                e,
            )

            if attempt >= REQUEST_RETRIES:
                raise

        else:
            return models

    return None
