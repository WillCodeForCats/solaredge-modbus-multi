"""Device ID scanner for SolarEdge Modbus Multi.

Based on work by thargy: https://github.com/thargy/modbus-scanner
"""

from __future__ import annotations

import asyncio
import logging

from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)


class SolarEdgeDeviceScanner:
    # Device scanning request
    REQUEST = [0x0, 0x0, 0x0, 0x0, 0x0, 0x6, 0x0, 0x3, 0x9C, 0x40, 0x0, 0x09]

    # Device scanning response (inverter signature)
    # 00 02 00 00 00 15 02 03 12 53 75 6e 53 00 01 00 41 53 6f 6c 61 72 45 64 67 65 20
    RESPONSE = [
        0x0,  # transaction high
        0x0,  # transaction low
        0x0,
        0x0,
        0x0,
        0x15,
        0x0,  # modbus address
        0x3,
        0x12,  # C_SunSpec_ID
        0x53,  # C_SunSpec_ID
        0x75,  # C_SunSpec_ID
        0x6E,  # C_SunSpec_ID
        0x53,  # C_SunSpec_ID
        0x0,  # C_SunSpec_DID
        0x1,  # C_SunSpec_DID
        0x0,  # C_SunSpec_Length
        0x41,  # C_SunSpec_Length
        0x53,  # C_Manufacturer
        0x6F,  # C_Manufacturer
        0x6C,  # C_Manufacturer
        0x61,  # C_Manufacturer
        0x72,  # C_Manufacturer
        0x45,  # C_Manufacturer
        0x64,  # C_Manufacturer
        0x67,  # C_Manufacturer
        0x65,  # C_Manufacturer
        0x20,
    ]

    DEVICE_ID_INDEX = 6
    TRANS_HIGH_INDEX = 0
    TRANS_LOW_INDEX = 1
    NOT_FOUND = 0
    FOUND = 1
    FOUND_INV = 2

    def __init__(
        self,
        host: str,
        port: int,
        timeout: float = 5.0,
        scan_retries: int = 3,
    ):
        """Initialize the SolarEdge device scanner.

        Args:
            host: Target host address.
            port: Target port number.
            timeout: Connection timeout in seconds.
            scan_retries: Number of retry attempts for failed scans.
        """
        self._timeout = timeout
        self._scan_retries = scan_retries
        self._host = host
        self._port = port
        self._reader = None
        self._writer = None
        self._transaction = 0

        self.inverters = []

    async def scan_list(
        self, device_list: list[int], slow_scan: bool = False
    ) -> list[int]:
        """Scan a list of device IDs for SolarEdge inverters.

        Args:
            device_list: List of Modbus device IDs to scan.
            slow_scan: If True, retry non-responding devices with longer timeout.

        Returns:
            List of device IDs that are SolarEdge inverters.
        """
        for chunk in self._batch(device_list, 4):
            retry = []
            # Quick scan chunk
            for device_id in chunk:
                result = await self.scan_device_id(device_id, 0.5)
                if result == self.FOUND_INV:
                    self.inverters.append(device_id)
                elif result != self.FOUND:
                    retry.append(device_id)

            # Slow scan chunk (optional)
            if slow_scan:
                for device_id in retry:
                    result = await self.scan_device_id(device_id, 5.0)
                    if result == self.FOUND_INV:
                        self.inverters.append(device_id)

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
            result = await self.scan_device_id(device_id, 1.0)
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
        """Establish TCP connection to the Modbus device."""
        attempt = 1

        while self._writer is None and attempt <= self._scan_retries:
            try:
                _LOGGER.debug(f"Connecting to {self._host}:{self._port} ... ")
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, self._port),
                    timeout=self._timeout,
                )
            except asyncio.TimeoutError:
                await self.disconnect()
                attempt = attempt + 1
                await asyncio.sleep(1.0)
                _LOGGER.warning(
                    f"Timeout occurred while connecting to {self._host}:{self._port}"
                )
            except OSError as e:
                await self.disconnect()
                attempt = attempt + 1
                await asyncio.sleep(1.0)
                _LOGGER.warning(
                    f"Network error connecting to {self._host}:{self._port}: {e}"
                )

        if attempt > self._scan_retries:
            raise HomeAssistantError(
                f"Unable to connect to {self._host}:{self._port} after {attempt - 1} attempts."
            )

    async def disconnect(self) -> None:
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

        expected = self.RESPONSE.copy()
        expected[self.TRANS_HIGH_INDEX] = request[0]
        expected[self.TRANS_LOW_INDEX] = request[1]
        expected[self.DEVICE_ID_INDEX] = request[self.DEVICE_ID_INDEX]

        index = 0
        for a in response:
            if index >= len(expected):
                return self.FOUND if index >= 7 else 0
            if a != expected[index]:
                return self.NOT_FOUND
            index = index + 1

        return self.FOUND_INV

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
            HomeAssistantError: If scanning fails after all retry attempts.

        Credit: https://github.com/thargy/modbus-scanner/blob/main/scan.py
        """

        # Update request
        self._transaction = (self._transaction + 1) % 65536
        request = self.REQUEST.copy()
        request[self.TRANS_HIGH_INDEX] = int(self._transaction / 256)
        request[self.TRANS_LOW_INDEX] = self._transaction % 256
        request[self.DEVICE_ID_INDEX] = device_id

        attempt = 1

        if self._writer is None:
            await self.connect()

        while attempt <= self._scan_retries:
            try:
                self._writer.write(bytes(request))
                await self._writer.drain()
                _LOGGER.debug(f"Scanning ID: {device_id} ...")

                async with asyncio.timeout(timeout):
                    response = await self._reader.read(1024)
                    result = self.device_is_inverter(request, response)
                    if result == self.FOUND_INV:
                        _LOGGER.debug(f" {device_id} is INVERTER")
                        return self.FOUND_INV
                    else:
                        _LOGGER.warning(
                            f"Scanned device {device_id} did not match signature: "
                            f"{' '.join(format(x, '02x') for x in response)}"
                        )

                    _LOGGER.debug(f" Received ({len(response)} bytes)")
                    _LOGGER.debug(f" {' '.join(format(x, '02x') for x in response)}")

                    return self.FOUND

            except asyncio.TimeoutError:
                _LOGGER.debug(f" Timed out after {timeout}s")
                attempt = attempt + 1

            except OSError as e:
                _LOGGER.debug(f" FAILED: {e}")
                attempt = attempt + 1

        _LOGGER.debug(f" No device found at ID {device_id}")
        return self.NOT_FOUND

    def _batch(self, iterable, n=1):
        """Split an iterable into batches of size n.

        Args:
            iterable: Sequence to split into batches.
            n: Size of each batch (default: 1).

        Yields:
            Batches of up to n elements from the iterable.

        Credit: https://github.com/thargy/modbus-scanner/blob/main/scan.py
        """
        length = len(iterable)
        for ndx in range(0, length, n):
            yield iterable[ndx : min(ndx + n, length)]
