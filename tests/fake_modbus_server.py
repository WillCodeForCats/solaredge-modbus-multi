"""A minimal fake Modbus/TCP server for transport and scanner tests.

Speaks real MBAP + PDU framing (functions 3 and 16) over an ephemeral
localhost port, serving per-unit register spaces with fault injection:

- exception_units: unit -> Modbus exception code (responds fn|0x80)
- silent_units: no response at all (client times out)
- fragment: split every response into two TCP segments with a small delay
- wrong_txn_units: respond with a mismatched transaction id
- wrong_unit_units: respond with a mismatched unit id
- disconnect_units: close the connection instead of responding
- response_delay: seconds to wait before answering
- max_sessions: concurrent-connection cap (SolarEdge allows exactly 1;
  excess connections are accepted and immediately closed)

Writes (function 16) are recorded in `writes` as (unit, address, values).
"""

from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass, field


@dataclass
class FakeModbusServer:
    # {unit: {address: value}}
    spaces: dict[int, dict[int, int]] = field(default_factory=dict)
    exception_units: dict[int, int] = field(default_factory=dict)
    silent_units: set[int] = field(default_factory=set)
    wrong_txn_units: set[int] = field(default_factory=set)
    wrong_unit_units: set[int] = field(default_factory=set)
    disconnect_units: set[int] = field(default_factory=set)
    fragment: bool = False
    response_delay: float = 0.0
    max_sessions: int = 1

    def __post_init__(self) -> None:
        self._server: asyncio.Server | None = None
        self._active_sessions = 0
        self.port: int | None = None
        self.writes: list[tuple[int, int, list[int]]] = []
        self.rejected_sessions = 0

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        if self._active_sessions >= self.max_sessions:
            self.rejected_sessions += 1
            writer.close()
            return

        self._active_sessions += 1
        try:
            while True:
                header = await reader.readexactly(7)
                txn, _proto, length, unit = struct.unpack(">HHHB", header)
                pdu = await reader.readexactly(length - 1)

                response = self._build_response(txn, unit, pdu)
                if response is None:
                    continue  # silent: leave the client waiting
                if response == b"":
                    writer.close()
                    return

                if self.response_delay:
                    await asyncio.sleep(self.response_delay)

                if self.fragment and len(response) > 4:
                    writer.write(response[:4])
                    await writer.drain()
                    await asyncio.sleep(0.01)
                    writer.write(response[4:])
                else:
                    writer.write(response)
                await writer.drain()

        except asyncio.IncompleteReadError, ConnectionResetError, OSError:
            pass
        finally:
            self._active_sessions -= 1
            writer.close()

    def _build_response(self, txn: int, unit: int, pdu: bytes) -> bytes | None:
        """Build a full MBAP+PDU response; None = silent, b"" = disconnect."""
        function = pdu[0]

        if unit in self.silent_units:
            return None
        if unit in self.disconnect_units:
            return b""

        response_txn = txn + 1 if unit in self.wrong_txn_units else txn
        response_unit = unit + 1 if unit in self.wrong_unit_units else unit

        if unit in self.exception_units:
            body = struct.pack(">BB", function | 0x80, self.exception_units[unit])
        elif unit not in self.spaces:
            body = struct.pack(">BB", function | 0x80, 0x0B)  # gateway: no path
        elif function == 3:
            address, count = struct.unpack(">HH", pdu[1:5])
            space = self.spaces[unit]
            values = [space.get(address + offset, 0) for offset in range(count)]
            body = struct.pack(">BB", 3, count * 2) + struct.pack(f">{count}H", *values)
        elif function == 16:
            address, count, byte_count = struct.unpack(">HHB", pdu[1:6])
            values = list(struct.unpack(f">{count}H", pdu[6 : 6 + byte_count]))
            self.writes.append((unit, address, values))
            for offset, value in enumerate(values):
                self.spaces[unit][address + offset] = value
            body = struct.pack(">BHH", 16, address, count)
        else:
            body = struct.pack(">BB", function | 0x80, 0x01)  # illegal function

        mbap = struct.pack(">HHHB", response_txn, 0, len(body) + 1, response_unit)
        return mbap + body
