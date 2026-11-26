"""Tests for _check_ha_version() and _check_dependency_versions().

Called from async_setup_entry via hass.async_add_executor_job before
modbus_connection or .hub are imported, so an old or missing install fails
with a ConfigEntryError message we can define.
"""

import importlib.metadata
from unittest.mock import patch

from homeassistant.exceptions import ConfigEntryError
import pytest

from custom_components.solaredge_modbus_multi import (
    _check_dependency_versions,
    _check_ha_version,
)

INIT = "custom_components.solaredge_modbus_multi"

_MISSING = object()


def _patched_versions(tmodbus, modbus_connection):
    versions = {"tmodbus": tmodbus, "modbus_connection": modbus_connection}

    def fake_version(package):
        if versions[package] is _MISSING:
            raise importlib.metadata.PackageNotFoundError(package)
        return versions[package]

    return patch("importlib.metadata.version", side_effect=fake_version)


class TestCheckDependencyVersions:
    """Test check dependency versions."""

    def test_passes_when_both_versions_meet_the_floor(self):
        """Test passes when both versions meet the floor."""
        with _patched_versions(tmodbus="0.6.1", modbus_connection="4.10.0"):
            _check_dependency_versions()

    def test_passes_when_both_versions_are_newer(self):
        """Test passes when both versions are newer."""
        with _patched_versions(tmodbus="99.0.0", modbus_connection="99.0.0"):
            _check_dependency_versions()

    def test_old_tmodbus_raises(self):
        """Test old tmodbus raises."""
        with (
            _patched_versions(tmodbus="0.6.0", modbus_connection="99.0.0"),
            pytest.raises(ConfigEntryError, match="tmodbus version must be at least"),
        ):
            _check_dependency_versions()

    def test_old_modbus_connection_raises(self):
        """Test old modbus connection raises."""
        with (
            _patched_versions(tmodbus="99.0.0", modbus_connection="4.9.0"),
            pytest.raises(
                ConfigEntryError, match="modbus-connection version must be at least"
            ),
        ):
            _check_dependency_versions()

    def test_tmodbus_checked_before_modbus_connection(self):
        """Test tmodbus checked before modbus connection."""
        with (
            _patched_versions(tmodbus="0.1.0", modbus_connection="0.1.0"),
            pytest.raises(ConfigEntryError, match="tmodbus version must be at least"),
        ):
            _check_dependency_versions()

    def test_missing_tmodbus_raises(self):
        """Test missing tmodbus raises."""
        with (
            _patched_versions(tmodbus=_MISSING, modbus_connection="99.0.0"),
            pytest.raises(ConfigEntryError, match="tmodbus is not installed"),
        ):
            _check_dependency_versions()

    def test_missing_modbus_connection_raises(self):
        """Test missing modbus connection raises."""
        with (
            _patched_versions(tmodbus="99.0.0", modbus_connection=_MISSING),
            pytest.raises(ConfigEntryError, match="modbus-connection is not installed"),
        ):
            _check_dependency_versions()

    def test_missing_tmodbus_checked_before_modbus_connection(self):
        """Test missing tmodbus checked before modbus connection."""
        with (
            _patched_versions(tmodbus=_MISSING, modbus_connection=_MISSING),
            pytest.raises(ConfigEntryError, match="tmodbus is not installed"),
        ):
            _check_dependency_versions()


class TestCheckHaVersion:
    """Test check HA version."""

    @pytest.mark.parametrize("version", ["2026.10.0", "2026.10.4", "2027.1.0"])
    def test_passes_at_or_above_the_floor(self, version):
        """Test passes at or above the floor."""
        with (
            patch(f"{INIT}.HA_REQUIRED_VERSION", "2026.10.0"),
            patch(f"{INIT}.HA_VERSION", version),
        ):
            _check_ha_version()

    @pytest.mark.parametrize("version", ["2025.12.1", "2026.8.0", "2026.10.0b1"])
    def test_older_home_assistant_raises(self, version):
        """Test older home assistant raises."""
        with (
            patch(f"{INIT}.HA_REQUIRED_VERSION", "2026.10.0"),
            patch(f"{INIT}.HA_VERSION", version),
            pytest.raises(ConfigEntryError, match="2026.10.0 or newer is required"),
        ):
            _check_ha_version()
