"""SolarEdge Modbus protocol code, staged for extraction into a standalone library.

Nothing in this package may import Home Assistant or depend on `hass`. Code
here talks to the inverters through modbus-connection and reports problems by
raising the exceptions in `exceptions.py`; the integration turns those into
Home Assistant errors, repair issues and entities.
"""
