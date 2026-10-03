"""translations/en.json must mirror strings.json.

Home Assistant reads translations/<lang>.json at runtime and strings.json is
the source developers edit; with English the only language shipped, the two
drifting apart silently loses UI text. Compare every leaf path and the
placeholders each string references.
"""

from __future__ import annotations

import json
import pathlib
import re

INTEGRATION = (
    pathlib.Path(__file__).parents[1] / "custom_components" / "solaredge_modbus_multi"
)
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def _leaves(node: dict, prefix: str = "") -> dict[str, str]:
    """Flatten nested dicts to {dotted.path: leaf string}."""
    leaves: dict[str, str] = {}
    for key, value in node.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            leaves.update(_leaves(value, f"{path}."))
        else:
            leaves[path] = value
    return leaves


def test_english_translation_mirrors_strings() -> None:
    strings = _leaves(json.loads((INTEGRATION / "strings.json").read_text()))
    english = _leaves(
        json.loads((INTEGRATION / "translations" / "en.json").read_text())
    )

    assert set(strings) == set(english), {
        "only_in_strings": sorted(set(strings) - set(english)),
        "only_in_en": sorted(set(english) - set(strings)),
    }
    for path, text in strings.items():
        assert set(PLACEHOLDER.findall(text)) == set(
            PLACEHOLDER.findall(english[path])
        ), path


def test_english_is_the_only_shipped_translation() -> None:
    """Both instances run language=en; other locales were stale and removed."""
    assert sorted(p.name for p in (INTEGRATION / "translations").glob("*.json")) == [
        "en.json"
    ]
