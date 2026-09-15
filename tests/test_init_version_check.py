"""Tests for _check_dependency_versions()

Called from async_setup_entry via hass.async_add_executor_job before
modbus_connection or .hub are imported, so an old or missing install fails
with a ConfigEntryError message we can define.
"""

import importlib.metadata
from unittest.mock import patch

import pytest
from homeassistant.exceptions import ConfigEntryError

from custom_components.solaredge_modbus_multi import _check_dependency_versions

_MISSING = object()


def _patched_versions(tmodbus, modbus_connection):
    versions = {"tmodbus": tmodbus, "modbus_connection": modbus_connection}

    def fake_version(package):
        if versions[package] is _MISSING:
            raise importlib.metadata.PackageNotFoundError(package)
        return versions[package]

    return patch("importlib.metadata.version", side_effect=fake_version)


class TestCheckDependencyVersions:
    def test_passes_when_both_versions_meet_the_floor(self):
        with _patched_versions(tmodbus="0.6.1", modbus_connection="4.10.0"):
            _check_dependency_versions()

    def test_passes_when_both_versions_are_newer(self):
        with _patched_versions(tmodbus="99.0.0", modbus_connection="99.0.0"):
            _check_dependency_versions()

    def test_old_tmodbus_raises(self):
        with (
            _patched_versions(tmodbus="0.6.0", modbus_connection="99.0.0"),
            pytest.raises(ConfigEntryError, match="tmodbus version must be at least"),
        ):
            _check_dependency_versions()

    def test_old_modbus_connection_raises(self):
        with (
            _patched_versions(tmodbus="99.0.0", modbus_connection="4.9.0"),
            pytest.raises(
                ConfigEntryError, match="modbus-connection version must be at least"
            ),
        ):
            _check_dependency_versions()

    def test_tmodbus_checked_before_modbus_connection(self):
        with (
            _patched_versions(tmodbus="0.1.0", modbus_connection="0.1.0"),
            pytest.raises(ConfigEntryError, match="tmodbus version must be at least"),
        ):
            _check_dependency_versions()

    def test_missing_tmodbus_raises(self):
        with (
            _patched_versions(tmodbus=_MISSING, modbus_connection="99.0.0"),
            pytest.raises(ConfigEntryError, match="tmodbus is not installed"),
        ):
            _check_dependency_versions()

    def test_missing_modbus_connection_raises(self):
        with (
            _patched_versions(tmodbus="99.0.0", modbus_connection=_MISSING),
            pytest.raises(ConfigEntryError, match="modbus-connection is not installed"),
        ):
            _check_dependency_versions()

    def test_missing_tmodbus_checked_before_modbus_connection(self):
        with (
            _patched_versions(tmodbus=_MISSING, modbus_connection=_MISSING),
            pytest.raises(ConfigEntryError, match="tmodbus is not installed"),
        ):
            _check_dependency_versions()
