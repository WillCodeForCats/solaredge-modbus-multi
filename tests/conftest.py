"""Activate pytest-homeassistant-custom-component and modbus-connection for all tests."""

pytest_plugins = [
    "pytest_homeassistant_custom_component",
    "modbus_connection.pytest_plugin",
]
