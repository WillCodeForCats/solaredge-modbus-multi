"""Device ID scanner for SolarEdge Modbus Multi.

Based on work by thargy: https://github.com/thargy/modbus-scanner

By default requests go through temporary units on the modbus integration's
shared connection, so a scan never competes with a loaded entry for the
device's single TCP connection. With use_socket the scanner opens its own
socket instead, which gives up that protection but is not slowed by the
timeout other integrations ask the shared connection for.
"""

from __future__ import annotations

import asyncio
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

# Read holding registers (function 3) request for SIGNATURE, as Modbus/TCP:
# transaction (2 bytes), protocol (2), length (2), device ID, function,
# address (2), register count (2). Transaction and device ID are filled in
# per scan.
REQUEST = [
    0x0,
    0x0,
    0x0,
    0x0,
    0x0,
    0x6,
    0x0,
    0x3,
    *SIGNATURE_ADDRESS.to_bytes(2, "big"),
    *len(SIGNATURE).to_bytes(2, "big"),
]

# Response an inverter gives to REQUEST: the MBAP header, function, byte
# count, then the SIGNATURE registers. Transaction and device ID are
# filled in per scan.
RESPONSE = [
    0x0,  # transaction high
    0x0,  # transaction low
    0x0,
    0x0,
    0x0,
    0x3 + 2 * len(SIGNATURE),  # remaining length
    0x0,  # modbus address
    0x3,
    2 * len(SIGNATURE),  # byte count
    *b"".join(word.to_bytes(2, "big") for word in SIGNATURE),
]


class ScannerConnectionError(Exception):
    """Unable to connect to the device being scanned."""


class SolarEdgeDeviceScanner:
    """Solar edge device scanner.

    Two ways to scan are available, chosen with use_socket:

    Temporary units (default): requests go through the Home Assistant modbus
    shared connection. A scan never competes with a loaded entry for the
    device's single TCP connection, but the shared connection applies the
    highest timeout any integration asked for to every request. The built-in
    SolarEdge Modbus integration asks for 30 seconds and its timeout cannot be
    configured, and a unit can only raise the timeout, so our scan_timeout
    only takes effect when we are the first on the connection; otherwise it
    cannot shorten the other's. A scan waits out the full timeout for every
    Device ID with no device, on each of its attempts: 30 seconds with 3
    attempts is 90 seconds per empty ID. Worst case with a 30 second timeout
    and 1 inverter, by scan_retries (attempts per ID):

        Scan           IDs scanned   3 (90 s/ID)   2 (60 s/ID)   1 (30 s/ID)
        Fast Scan      1-32          ~45 minutes   ~30 minutes   ~15 minutes
        Complete Scan  1-247         ~6 hours      ~4 hours      ~2 hours

    These figures assume 1 inverter, so all other IDs time out at 30 seconds
    per attempt. Any ID with a detected device will not wait the timeout.

    With the default 3 second timeout the same scans take a few minutes.
    Setup can look stalled, and other integrations on the connection queue
    behind the scan. The long timeout stays until the connection is closed and
    reopened, which means a Home Assistant restart after the other integration
    is disabled. To avoid it, use the manual setup with known Device IDs,
    which does not scan, or disable the other integration and restart Home
    Assistant before scanning. Or use Socket scanning mode.

    Socket (use_socket): the scanner opens its own TCP socket, so scan_timeout
    is honored and empty IDs fail fast. The cost is that the scan does not
    coordinate with the shared connection: an inverter accepts few TCP
    connections at once, so scanning while another client holds it can fail
    to connect.
    """

    DEVICE_ID_INDEX = 6
    TRANS_HIGH_INDEX = 0
    TRANS_LOW_INDEX = 1
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
        use_socket: bool = False,
        connect_timeout: float = 5.0,
    ):
        """Initialize the SolarEdge device scanner.

        Args:
            hass: Home Assistant instance.
            host: Target host address.
            port: Target port number.
            scan_retries: Number of attempts for each device ID.
            scan_timeout: Request timeout in seconds.
            use_socket: Scan over our own TCP socket instead of temporary
                units on the shared connection.
            connect_timeout: Socket connection timeout in seconds, only
                used with use_socket.

        """
        self._hass = hass
        self._params = ModbusTcpParams(host=host, port=port)
        self._scan_retries = scan_retries
        self._scan_timeout = scan_timeout
        self._use_socket = use_socket
        self._connect_timeout = connect_timeout
        self._stack: AsyncExitStack | None = None
        self._reader = None
        self._writer = None
        self._transaction = 0

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

    def _raise_connection_error(self) -> None:
        """Raise ScannerConnectionError for the device being scanned."""
        raise ScannerConnectionError(
            f"Unable to connect to {self._params.host}:{self._params.port} "
            f"after {self._scan_retries} attempts."
        )

    async def connect(self) -> None:
        """Connect for the length of the scan.

        With use_socket this opens the socket; otherwise it holds the shared
        connection open.
        """
        if self._use_socket:
            await self._connect_socket()
        else:
            await self._connect_shared()

    async def disconnect(self) -> None:
        """Close the socket, or release the hold on the shared connection."""
        if self._use_socket:
            await self._disconnect_socket()
        else:
            await self._disconnect_shared()

    async def _connect_shared(self) -> None:
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

    async def _disconnect_shared(self) -> None:
        """Release the hold; the connection closes if nothing else holds it."""
        if self._stack is not None:
            stack, self._stack = self._stack, None
            await stack.aclose()

    async def _connect_socket(self) -> None:
        """Establish TCP connection to the Modbus device."""
        attempt = 1

        while self._writer is None and attempt <= self._scan_retries:
            try:
                _LOGGER.debug(
                    "Connecting to %s:%s ...", self._params.host, self._params.port
                )
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self._params.host, self._params.port),
                    timeout=self._connect_timeout,
                )
            except (TimeoutError, OSError) as e:
                await self._disconnect_socket()
                attempt += 1
                await asyncio.sleep(1.0)
                _LOGGER.warning(
                    "Error connecting to %s:%s: %s",
                    self._params.host,
                    self._params.port,
                    e or "timeout",
                )

        if attempt > self._scan_retries:
            self._raise_connection_error()

    async def _disconnect_socket(self) -> None:
        """Close the TCP connection to the Modbus device."""
        if self._writer is not None:
            self._writer.close()
            await self._writer.wait_closed()
        self._writer = None
        self._reader = None

    def device_is_inverter(self, request: list[int], response: list[int]) -> int:
        """Check if device response matches SolarEdge inverter signature.

        Args:
            request: The Modbus TCP request sent to the device.
            response: The Modbus TCP response received from the device.

        Returns:
            FOUND_INV (2) if a SolarEdge inverter was detected.
            FOUND (1) if a non-inverter Modbus device responded.
            NOT_FOUND (0) if the response was invalid or no device found.

        Credit: https://github.com/thargy/modbus-scanner/blob/main/scan.py

        """
        if len(response) < 7 or len(request) < self.DEVICE_ID_INDEX:
            return self.NOT_FOUND

        expected = RESPONSE.copy()
        expected[self.TRANS_HIGH_INDEX] = request[0]
        expected[self.TRANS_LOW_INDEX] = request[1]
        expected[self.DEVICE_ID_INDEX] = request[self.DEVICE_ID_INDEX]

        for index, a in enumerate(response):
            if index >= len(expected):
                return self.FOUND if index >= 7 else self.NOT_FOUND
            if a != expected[index]:
                return self.NOT_FOUND

        return self.FOUND_INV

    async def _scan_device_id_socket(self, device_id: int, timeout: float) -> int:
        """Scan a device ID over our own socket; see scan_device_id.

        Credit: https://github.com/thargy/modbus-scanner/blob/main/scan.py

        """

        # Update request
        self._transaction = (self._transaction + 1) % 65536
        request = REQUEST.copy()
        request[self.TRANS_HIGH_INDEX] = int(self._transaction / 256)
        request[self.TRANS_LOW_INDEX] = self._transaction % 256
        request[self.DEVICE_ID_INDEX] = device_id

        attempt = 1

        if self._writer is None:
            await self._connect_socket()

        while attempt <= self._scan_retries:
            try:
                self._writer.write(bytes(request))
                await self._writer.drain()
                _LOGGER.debug("Scanning ID: %s ...", device_id)

                async with asyncio.timeout(timeout):
                    response = await self._reader.read(1024)
                    result = self.device_is_inverter(request, response)
                    if result == self.FOUND_INV:
                        _LOGGER.debug("%s is INVERTER", device_id)
                        return self.FOUND_INV
                    _LOGGER.warning(
                        "Scanned device %s did not match signature: %s",
                        device_id,
                        " ".join(format(x, "02x") for x in response),
                    )

                    _LOGGER.debug("Received (%s bytes)", len(response))
                    _LOGGER.debug("%s", " ".join(format(x, "02x") for x in response))

                    return self.FOUND

            except (TimeoutError, OSError) as e:
                _LOGGER.debug("Attempt failed (timeout %ss): %r", timeout, e)
                attempt += 1

        _LOGGER.debug("No device found at ID %s", device_id)
        return self.NOT_FOUND

    async def scan_device_id(self, device_id: int, timeout: float = 5.0) -> int:
        """Scan a specific Modbus device ID for a SolarEdge inverter.

        Uses our own socket with use_socket, otherwise a temporary unit.

        Args:
            device_id: The Modbus device ID to scan (1-247).
            timeout: Maximum time in seconds to wait for a response. With
                temporary units this is only a request: the shared connection
                uses the highest timeout any holder asked for.

        Returns:
            FOUND_INV (2) if a SolarEdge inverter was detected.
            FOUND (1) if a non-inverter Modbus device responded.
            NOT_FOUND (0) if no valid response was received.

        Raises:
            ScannerConnectionError: If the connection cannot be established.

        """
        if self._use_socket:
            return await self._scan_device_id_socket(device_id, timeout)
        return await self._scan_device_id_unit(device_id, timeout)

    async def _scan_device_id_unit(self, device_id: int, timeout: float) -> int:
        """Scan a device ID with a temporary unit; see scan_device_id."""
        async with async_get_temporary_unit(
            self._hass, self._params, device_id
        ) as unit:
            # A unit can only raise the link's timeout, so this holds when we
            # are the first on the connection and has no effect when another
            # holder already asked for a longer one.
            unit.require_timeout(timeout)

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
            self._raise_connection_error()

        _LOGGER.debug("No device found at ID %s", device_id)
        return self.NOT_FOUND
