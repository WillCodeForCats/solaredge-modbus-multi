"""Home Assistant-independent Modbus/TCP transport.

One ModbusTransport = one serialized Modbus/TCP session (SolarEdge
inverters accept a single session; the server closes it after ~2 minutes
idle and the next call reconnects reactively — no keepalive on purpose).

The transport owns the pymodbus client lifecycle, the session lock with
task-reentrancy, the pymodbus 3.7 slave=/device_id= keyword shim, and raw
read/write calls plus PollStats counters. Response validation, exception
mapping and retry policy stay with the callers: pymodbus transaction
retries apply only where the caller's enclosing deadline allows them
(core data reads inside the whole-poll budget); the 2 s detection-probe
deadlines intentionally pre-empt them, and whole-poll retries belong to
the coordinator. Do not enlarge deadlines here to "honor" inner retries —
the 5 s fast-poll envelope depends on fast failure.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from pymodbus.client import AsyncModbusTcpClient

_LOGGER = logging.getLogger(__name__)


@dataclass
class PollStats:
    """Diagnostics-only counters for one transport session."""

    reads: int = 0
    writes: int = 0
    connects: int = 0
    reconnects: int = 0
    last_error: str | None = field(default=None, repr=False)


class ModbusTransport:
    """A single serialized Modbus/TCP client session."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        timeout: int,
        retries: int,
        reconnect_delay: float,
        reconnect_delay_max: float,
        client_factory: Callable[..., AsyncModbusTcpClient] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._retries = retries
        self._reconnect_delay = reconnect_delay
        self._reconnect_delay_max = reconnect_delay_max
        self._client_factory = client_factory

        self._client: AsyncModbusTcpClient | None = None
        self._use_device_id_param = False
        self._lock = asyncio.Lock()
        self._lock_holder: asyncio.Task | None = None
        self.stats = PollStats()

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def connected(self) -> bool:
        if self._client is None:
            return False

        return self._client.connected

    def _held_by_current_task(self) -> bool:
        return self._lock_holder is asyncio.current_task()

    async def _connect_unlocked(self) -> None:
        if self.connected:
            return

        if self._client is None:
            _LOGGER.debug(
                "New AsyncModbusTcpClient: "
                f"reconnect_delay={self._reconnect_delay} "
                f"reconnect_delay_max={self._reconnect_delay_max} "
                f"timeout={self._timeout} "
                f"retries={self._retries}"
            )
            factory = self._client_factory or AsyncModbusTcpClient
            self._client = factory(
                host=self._host,
                port=self._port,
                reconnect_delay=self._reconnect_delay,
                reconnect_delay_max=self._reconnect_delay_max,
                timeout=self._timeout,
                retries=self._retries,
            )
            # pymodbus 3.7 renamed slave= to device_id=; cache the check once.
            sig = inspect.signature(self._client.read_holding_registers)
            self._use_device_id_param = "device_id" in sig.parameters
            self.stats.connects += 1
        elif not self._client.connected:
            self.stats.reconnects += 1

        _LOGGER.debug(f"Connecting to {self._host}:{self._port} ...")
        await self._client.connect()

    async def connect(self) -> None:
        """Connect, creating the client on first use."""
        if self._held_by_current_task():
            await self._connect_unlocked()
            return
        async with self._lock:
            await self._connect_unlocked()

    def _disconnect_unlocked(self, clear_client: bool = False) -> None:
        if self._client is not None:
            _LOGGER.debug(
                f"Disconnecting from {self._host}:{self._port} "
                f"(clear_client={clear_client})."
            )
            self._client.close()

            if clear_client:
                self._client = None

    async def disconnect(self, clear_client: bool = False) -> None:
        """Close the socket; optionally drop the client object."""
        if self._held_by_current_task():
            self._disconnect_unlocked(clear_client)
            return
        async with self._lock:
            self._disconnect_unlocked(clear_client)

    async def read_holding_registers_raw(self, unit: int, address: int, count: int):
        """Raw locked read; returns the pymodbus response unvalidated."""
        if self._held_by_current_task():
            return await self._read_unlocked(unit, address, count)

        async with self._lock:
            self._lock_holder = asyncio.current_task()
            try:
                return await self._read_unlocked(unit, address, count)
            finally:
                self._lock_holder = None

    async def _read_unlocked(self, unit: int, address: int, count: int):
        self.stats.reads += 1
        if self._use_device_id_param:
            return await self._client.read_holding_registers(
                address=address, count=count, device_id=unit
            )
        return await self._client.read_holding_registers(
            address=address, count=count, slave=unit
        )

    async def write_registers_raw(self, unit: int, address: int, payload: list[int]):
        """Raw locked write (function 16); returns the response unvalidated.

        Connects first if the session dropped — SolarEdge idle-closes after
        ~2 minutes, and a write must not fail just because polling is slow.
        """
        async with self._lock:
            await self._connect_unlocked()

            self.stats.writes += 1
            if self._use_device_id_param:
                return await self._client.write_registers(
                    address=address, values=payload, device_id=unit
                )
            return await self._client.write_registers(
                address=address, values=payload, slave=unit
            )

    def hold_session(self) -> _SessionHold:
        """Reserve the session for a batch of calls by the current task.

        Reads inside the batch take the reentrant fast path, so a device's
        whole read cycle is one uninterrupted session use (writes queue
        behind it).
        """
        return _SessionHold(self)


class _SessionHold:
    def __init__(self, transport: ModbusTransport) -> None:
        self._transport = transport

    async def __aenter__(self) -> ModbusTransport:
        await self._transport._lock.acquire()
        self._transport._lock_holder = asyncio.current_task()
        return self._transport

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._transport._lock_holder = None
        self._transport._lock.release()
