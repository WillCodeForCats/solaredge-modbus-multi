"""Device ID scanner for SolarEdge Modbus Multi.

Based on work by thargy: https://github.com/thargy/modbus-scanner

Requests go through temporary units on the modbus integration's shared
connection, so a scan never competes with a loaded entry for the device's
single TCP connection.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AsyncExitStack
import logging

from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.core import HomeAssistant
from modbus_connection import (
    GatewayPathUnavailableError,
    GatewayTargetError,
    ModbusConnectionError,
    ModbusExceptionError,
    ModbusProtocolError,
    ModbusTcpParams,
    ModbusTimeoutError,
)

_LOGGER = logging.getLogger(__name__)

# SunSpec common block header and the start of the manufacturer string.
SIGNATURE_ADDRESS = 40000
SIGNATURE = [
    0x5375,  # C_SunSpec_ID "Su"
    0x6E53,  # C_SunSpec_ID "nS"
    0x0001,  # C_SunSpec_DID
    0x0041,  # C_SunSpec_Length
    0x536F,  # C_Manufacturer "So"
    0x6C61,  # C_Manufacturer "la"
    0x7245,  # C_Manufacturer "rE"
    0x6467,  # C_Manufacturer "dg"
    0x6520,  # C_Manufacturer "e "
]


class ScannerConnectionError(Exception):
    """Unable to connect to the device being scanned."""


class SolarEdgeDeviceScanner:
    """Solar edge device scanner."""

    NOT_FOUND = 0
    FOUND = 1
    FOUND_INV = 2

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        scan_retries: int = 3,
        scan_timeout: float = 3.0,
    ):
        """Initialize the SolarEdge device scanner.

        Args:
            hass: Home Assistant instance.
            host: Target host address.
            port: Target port number.
            scan_retries: Number of attempts for each device ID.
            scan_timeout: Request timeout in seconds.

        """
        self._hass = hass
        self._params = ModbusTcpParams(host=host, port=port)
        self._scan_retries = scan_retries
        self._scan_timeout = scan_timeout
        self._stack: AsyncExitStack | None = None

        self.inverters = []

    async def scan_list(
        self,
        device_list: list[int],
        progress_callback: Callable | None = None,
    ) -> list[int]:
        """Scan a list of device IDs for SolarEdge inverters.

        Args:
            device_list: List of Modbus device IDs to scan.
            progress_callback: Optional callback to report progress.
                               Called with (scanned_count, total_count).

        Returns:
            List of device IDs that are SolarEdge inverters.

        """
        total = len(device_list)
        scanned = 0

        if progress_callback:
            await progress_callback(scanned, total)

        for device_id in device_list:
            _LOGGER.debug("Calling scan_device_id on device_id=%s", device_id)
            result = await self.scan_device_id(device_id, self._scan_timeout)
            if result == self.FOUND_INV:
                self.inverters.append(device_id)

            scanned += 1
            if progress_callback:
                _LOGGER.debug("scan_list progress: %s of %s", scanned, total)
                await progress_callback(scanned, total)

        return self.inverters

    async def check_list(self, device_list: list[int]) -> dict[str, list[int]]:
        """Check a list of device IDs and categorize the results.

        Args:
            device_list: List of Modbus device IDs to validate.

        Returns:
            Dictionary with three lists:
            - "inverters": Device IDs that are SolarEdge inverters
            - "other_devices": Device IDs that responded but aren't SolarEdge inverters
            - "no_response": Device IDs that didn't respond or timed out

        """
        inverters = []
        other_devices = []
        no_response = []

        for device_id in device_list:
            result = await self.scan_device_id(device_id, self._scan_timeout)
            if result == self.FOUND_INV:
                inverters.append(device_id)
            elif result == self.FOUND:
                other_devices.append(device_id)
            else:
                no_response.append(device_id)

        return {
            "inverters": inverters,
            "other_devices": other_devices,
            "no_response": no_response,
        }

    async def connect(self) -> None:
        """Hold the shared connection open for the length of the scan.

        Without a hold, the connection would close and reopen around every
        device ID. Raises HomeAssistantError if the device is already in use
        over different link settings.
        """
        if self._stack is not None:
            return

        stack = AsyncExitStack()
        # The hold is on the connection, not on the unit.
        await stack.enter_async_context(
            async_get_temporary_unit(self._hass, self._params, 1)
        )
        self._stack = stack

    async def disconnect(self) -> None:
        """Release the hold; the connection closes if nothing else holds it."""
        if self._stack is not None:
            stack, self._stack = self._stack, None
            await stack.aclose()

    async def scan_device_id(self, device_id: int, timeout: float = 5.0) -> int:
        """Scan a specific Modbus device ID for a SolarEdge inverter.

        Args:
            device_id: The Modbus device ID to scan (1-247).
            timeout: Maximum time in seconds to wait for a response.

        Returns:
            FOUND_INV (2) if a SolarEdge inverter was detected.
            FOUND (1) if a non-inverter Modbus device responded.
            NOT_FOUND (0) if no valid response was received.

        Raises:
            ScannerConnectionError: If the connection cannot be established.

        """
        async with async_get_temporary_unit(
            self._hass, self._params, device_id
        ) as unit:
            link_failed = False

            for attempt in range(1, self._scan_retries + 1):
                _LOGGER.debug("Scanning ID: %s ...", device_id)
                try:
                    registers = await unit.read_holding_registers(
                        SIGNATURE_ADDRESS, len(SIGNATURE)
                    )

                except (GatewayPathUnavailableError, GatewayTargetError):
                    # The gateway itself says nothing is at this ID.
                    _LOGGER.debug("No device found at ID %s", device_id)
                    return self.NOT_FOUND

                except ModbusExceptionError as err:
                    _LOGGER.debug(
                        "ID %s answered with an exception: %s", device_id, err
                    )
                    return self.FOUND

                except ModbusTimeoutError as err:
                    # A connect timeout is also a timeout, so ask the unit
                    # whether the link ever came up.
                    link_failed = not unit.connected
                    _LOGGER.debug(
                        "ID %s attempt %s of %s timed out: %s",
                        device_id,
                        attempt,
                        self._scan_retries,
                        err,
                    )

                except (ModbusConnectionError, ModbusProtocolError, OSError) as err:
                    link_failed = not unit.connected
                    _LOGGER.debug(
                        "ID %s attempt %s of %s failed: %s",
                        device_id,
                        attempt,
                        self._scan_retries,
                        err,
                    )

                else:
                    if registers == SIGNATURE:
                        _LOGGER.debug("%s is INVERTER", device_id)
                        return self.FOUND_INV

                    _LOGGER.warning(
                        "Scanned device %s did not match signature: %s",
                        device_id,
                        " ".join(format(x, "04x") for x in registers),
                    )
                    return self.FOUND

        if link_failed:
            raise ScannerConnectionError(
                f"Unable to connect to {self._params.host}:{self._params.port} "
                f"after {self._scan_retries} attempts."
            )

        _LOGGER.debug("No device found at ID %s", device_id)
        return self.NOT_FOUND
