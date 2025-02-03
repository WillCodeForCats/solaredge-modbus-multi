"""Classes for a SolarEdge Modbus Inverter."""

from __future__ import annotations


class SolarEdgeModbusDevice:
    """Helper functions for SolarEdge modbus devices."""

    @staticmethod
    def mb_str(s: bytes | str) -> str:
        if isinstance(s, bytes):
            s = s.decode(encoding="utf-8", errors="ignore")
        return s.replace("\x00", "").rstrip()
