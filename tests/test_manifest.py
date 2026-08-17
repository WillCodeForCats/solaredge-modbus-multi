"""Validate custom_components/solaredge_modbus_multi/manifest.json.

Home Assistant's integration loader rejects a manifest where the "version" key
isn't parseable by AwesomeVersion and blocks the whole integration from loading.

https://developers.home-assistant.io/blog/2021/01/29/custom-integration-changes#versions.
"""

import json
from pathlib import Path

import pytest
from awesomeversion import (
    AwesomeVersion,
    AwesomeVersionException,
    AwesomeVersionStrategy,
)

MANIFEST_PATH = (
    Path(__file__).parent.parent
    / "custom_components"
    / "solaredge_modbus_multi"
    / "manifest.json"
)

# From (homeassistant/loader.py, Integration.resolve_from_root).
ALLOWED_VERSION_STRATEGIES = [
    AwesomeVersionStrategy.CALVER,
    AwesomeVersionStrategy.SEMVER,
    AwesomeVersionStrategy.SIMPLEVER,
    AwesomeVersionStrategy.BUILDVER,
    AwesomeVersionStrategy.PEP440,
]


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def test_manifest_has_required_keys(manifest):
    for key in ("domain", "name", "version", "requirements"):
        assert key in manifest, f"manifest.json is missing required key {key!r}"


def test_manifest_domain_matches_folder(manifest):
    assert manifest["domain"] == MANIFEST_PATH.parent.name


def test_manifest_requirements_is_list(manifest):
    assert isinstance(manifest["requirements"], list)


def test_manifest_version_is_valid(manifest):
    version = manifest["version"]
    try:
        AwesomeVersion(version, ensure_strategy=ALLOWED_VERSION_STRATEGIES)
    except AwesomeVersionException as err:
        pytest.fail(
            f"manifest.json version {version!r} is not a valid version Home "
            f"Assistant will accept: {err}"
        )
