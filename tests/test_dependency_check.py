"""The installed-library check runs before the modbus backend is imported.

These run in a fresh interpreter on purpose: conftest.py already imports
modbus_connection and the integration package, so an in-process check of
sys.modules could never show that the package import itself stays backend-free.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from custom_components.solaredge_modbus_multi.const import (
    MODBUS_CONNECTION_REQUIRED_VERSION,
    PYMODBUS_REQUIRED_VERSION,
)
from custom_components.solaredge_modbus_multi.helpers import safe_version_tuple

ROOT = Path(__file__).resolve().parents[1]

# Overrides are {distribution: version | None}; None means "not installed".
# Every other distribution resolves normally, so the interpreter's own
# packages are untouched.
_SCRIPT = """
import importlib.metadata
import json
import sys

overrides = json.loads(sys.argv[1])
real_version = importlib.metadata.version


def fake_version(name):
    if name in overrides:
        if overrides[name] is None:
            raise importlib.metadata.PackageNotFoundError(name)
        return overrides[name]
    return real_version(name)


importlib.metadata.version = fake_version

from homeassistant.exceptions import ConfigEntryError  # noqa: E402

import custom_components.solaredge_modbus_multi as integration  # noqa: E402

package_import_loaded_backend = "modbus_connection" in sys.modules

try:
    installed = integration._check_dependency_versions()
except ConfigEntryError as err:
    result = {"error": str(err)}
else:
    import custom_components.solaredge_modbus_multi.hub  # noqa: F401

    result = {"installed": installed}

result["package_import_loaded_backend"] = package_import_loaded_backend
result["backend_loaded"] = "modbus_connection.pymodbus" in sys.modules
print(json.dumps(result))
"""


def _run(overrides: dict[str, str | None]) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT, json.dumps(overrides)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_missing_library_fails_before_backend_import():
    result = _run({"modbus_connection": None})

    assert "modbus-connection is not installed" in result["error"]
    assert result["package_import_loaded_backend"] is False
    assert result["backend_loaded"] is False


def test_old_library_fails_before_backend_import():
    result = _run({"modbus_connection": "4.4.0"})

    assert "modbus-connection 4.4.0 is installed" in result["error"]
    assert MODBUS_CONNECTION_REQUIRED_VERSION in result["error"]
    assert result["package_import_loaded_backend"] is False
    assert result["backend_loaded"] is False


def test_old_pymodbus_fails():
    result = _run({"pymodbus": "3.12.0"})

    assert "pymodbus 3.12.0 is installed" in result["error"]
    assert PYMODBUS_REQUIRED_VERSION in result["error"]


def test_supported_versions_pass_and_backend_loads():
    result = _run({})

    assert set(result["installed"]) == {"modbus-connection", "pymodbus"}
    assert result["package_import_loaded_backend"] is False
    assert result["backend_loaded"] is True


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("4.10.0", (4, 10, 0)),
        ("4.12.3", (4, 12, 3)),
        ("4.0.0a1", (4, 0, 0)),
        ("3.13.1.post1", (3, 13, 1)),
    ],
)
def test_safe_version_tuple(version, expected):
    assert safe_version_tuple(version) == expected


def test_safe_version_tuple_rejects_garbage():
    with pytest.raises(ValueError):
        safe_version_tuple("latest")
