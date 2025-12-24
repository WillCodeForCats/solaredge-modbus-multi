"""Device ID scanner for SolarEdge Modbus Multi."""

from __future__ import annotations

import asyncio
import logging
import socket

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
    FOUND = 1
    FOUND_INV = 2

    def __init__(
        self,
        host: str,
        port: int,
        timeout: float = 5.0,
        scan_retries: int = 3,
    ):
        self._timeout = timeout
        self._scan_retries = scan_retries
        self._host = host
        self._port = port
        self._sock = None
        self._reader = None
        self._writer = None
        self._transaction = 0

        self.inverters = []

    # def __del__(self):
    #    if self._sock is not None:
    #        try:
    #            self._sock.close()
    #            _LOGGER.debug("Closing connection ... SUCCEEDED")
    #        except socket.error as e:
    #            _LOGGER.debug(f"Closing connection ... FAILED: {e}")

    async def scan_list(self, device_list: list[int]) -> list[int]:
        for chunk in self._batch(device_list, 4):
            retry = []
            # Quick scan chunk
            for device_id in chunk:
                result = await self.scan_device_id(device_id, 0.5)
                if result == self.FOUND_INV:
                    self.inverters.append(device_id)
                elif result != self.FOUND:
                    retry.append(device_id)

            # Slow scan chunk
            # for device_id in retry:
            #    result = await self.scan_device_id(device_id, 5.0)
            #    if result == self.FOUND_INV:
            #        self.inverters.append(device_id)

        return self.inverters

    async def connect(self) -> None:
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
        if self._writer is not None:
            self._writer.close()
            await self._writer.wait_closed()
        self._writer = None
        self._reader = None

    def device_is_inverter(self, request: list[int], response: list[int]) -> int:
        """The function `device_is_inverter` checks if a given response matches the expected response for an inverter
        device.

        Parameters
        ----------
        request
            The request parameter is a list that contains the TCP request.
        response
            The `response` parameter is a list of values that represents the response received from a device.

        Returns
        -------
            The function `device_is_inverter` returns the result of the scanning process, which can be one of the following
        values:
        - `FOUND_INV`: Indicates that an inverter was found.
        - `FOUND`: Indicates that a non-inverter device was found.
        - `0`: Indicates an unknown response or no response was received within the specified timeout.

        Credit: https://github.com/thargy/modbus-scanner/blob/main/scan.py
        """
        if len(response) < 7 or len(request) < self.DEVICE_ID_INDEX:
            return 0

        expected = self.RESPONSE.copy()
        expected[self.TRANS_HIGH_INDEX] = request[0]
        expected[self.TRANS_LOW_INDEX] = request[1]
        expected[self.DEVICE_ID_INDEX] = request[self.DEVICE_ID_INDEX]

        index = 0
        for a in response:
            if index >= len(expected):
                return self.FOUND if index >= 7 else 0
            if a != expected[index]:
                return 0
            index = index + 1

        return self.FOUND_INV

    async def scan_device_id(self, device_id: int, timeout: float = 5.0) -> int:
        """The `scan_device_id` function scans a device ID by sending a request to a server and receiving a response,
        and returns the result of the scan.

        Parameters
        ----------
        device_id
            The `device_id` parameter is the ID of the device that you want to scan. It is used to update the
            request and specify the device ID in the request packet.
        timeout
            The `timeout` parameter is the maximum amount of time (in seconds) to wait for a response from the
            server before considering it as a timeout.

        Returns
        -------
            The function `scan_device_id` returns the result of the scanning process, which can be
            one of the following values:
                - `FOUND_INV`: Indicates that an inverter was found.
                - `FOUND`: Indicates that a non-inverter device was found.
                - `0`: Indicates an unknown response or no response was received within the specified timeout.

        Credit: https://github.com/thargy/modbus-scanner/blob/main/scan.py
        """

        # Update request
        self._transaction = self._transaction + 1
        request = self.REQUEST.copy()
        request[self.TRANS_HIGH_INDEX] = int(self._transaction / 256)
        request[self.TRANS_LOW_INDEX] = self._transaction % 256
        request[self.DEVICE_ID_INDEX] = device_id

        attempt = 1
        result = 0

        if self._sock is None:
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
                    else:
                        _LOGGER.warning(
                            f"Scanned device {device_id} did not match signature: "
                            f"{' '.join(format(x, '02x') for x in response)}"
                        )

                    _LOGGER.debug(f" Received ({len(response)} bytes)")

                    _LOGGER.debug(f" {' '.join(format(x, '02x') for x in response)}")

                    return result

            except asyncio.TimeoutError:
                _LOGGER.debug(f" Timed out after {timeout}s")
                attempt = attempt + 1

            except socket.error as e:
                _LOGGER.debug(f" FAILED: {e}")
                attempt = attempt + 1

            finally:
                break

        if attempt > self._scan_retries:
            raise HomeAssistantError(f"Aborted scanning after {attempt - 1} attempts!")

        return result

    def _batch(self, iterable, n=1):
        """The `batch` function takes an iterable and returns a generator that yields batches of elements from
        the iterable.

        Parameters
        ----------
        iterable
            The `iterable` parameter is any sequence or collection that can be iterated over, such as a list,
            tuple, or string. It is the input data that you want to process in batches.
        n, optional
            The parameter `n` in the `batch` function is an optional parameter that specifies the size of each
            batch. By default, it is set to 1, which means each batch will contain only one element from the
            iterable.

        Credit: https://github.com/thargy/modbus-scanner/blob/main/scan.py
        """
        length = len(iterable)
        for ndx in range(0, length, n):
            yield iterable[ndx : min(ndx + n, length)]
