"""Validate hacs.json.

hacs.json tells HACS what to show in its UI and how it decides if this
integration is installable for a Home Assistant version.

https://www.hacs.xyz/docs/publish/start/
"""

import json
from pathlib import Path

import pytest
from awesomeversion import (
    AwesomeVersion,
    AwesomeVersionException,
    AwesomeVersionStrategy,
)

HACS_JSON_PATH = Path(__file__).parent.parent / "hacs.json"

# type per https://www.hacs.xyz/docs/publish/start/ for whichever optional
# keys are present; "name" is the only required key.
OPTIONAL_KEY_TYPES = {
    "content_in_root": bool,
    "zip_release": bool,
    "filename": str,
    "hide_default_branch": bool,
    "country": str,
    "homeassistant": str,
    "hacs": str,
    "persistent_directory": str,
}


@pytest.fixture(scope="module")
def hacs_manifest() -> dict:
    return json.loads(HACS_JSON_PATH.read_text())


def test_hacs_json_has_name(hacs_manifest):
    assert isinstance(hacs_manifest.get("name"), str) and hacs_manifest["name"], (
        "hacs.json must have a non-empty 'name' string"
    )


def test_hacs_json_optional_key_types(hacs_manifest):
    for key, expected_type in OPTIONAL_KEY_TYPES.items():
        if key in hacs_manifest:
            assert isinstance(hacs_manifest[key], expected_type), (
                f"hacs.json key {key!r} should be {expected_type.__name__}, "
                f"got {type(hacs_manifest[key]).__name__}"
            )


def test_hacs_json_homeassistant_version_is_valid(hacs_manifest):
    """Home Assistant is CalVer (YYYY.MM.PATCH), so require that strategy."""
    version = hacs_manifest.get("homeassistant")
    if version is None:
        pytest.skip("hacs.json has no 'homeassistant' minimum version set")

    try:
        AwesomeVersion(version, ensure_strategy=[AwesomeVersionStrategy.CALVER])
    except AwesomeVersionException as err:
        pytest.fail(
            f"hacs.json 'homeassistant' version {version!r} is not a valid "
            f"CalVer Home Assistant version: {err}"
        )
