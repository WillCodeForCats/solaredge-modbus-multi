"""Structural checks on Component fields."""

import inspect

import pytest
from modbus_connection.model import Component, RegisterField

from custom_components.solaredge_modbus_multi import components


def _component_classes() -> list[type[Component]]:
    """Return all Components from components.py."""
    return [
        obj
        for _, obj in inspect.getmembers(components, inspect.isclass)
        if issubclass(obj, Component)
        and obj is not Component
        and obj.__module__ == components.__name__
    ]


# 3b48cab "Fix incorrect string size in MmpptUnit"
# catch a field length overlapping the next address


@pytest.mark.parametrize(
    "component_class", _component_classes(), ids=lambda c: c.__name__
)
def test_no_overlapping_registers(component_class: type[Component]) -> None:
    """Check if any register fields in a Component overlap."""
    spans = []
    for name in component_class.declared_fields:
        field = getattr(component_class, name)
        if not isinstance(field, RegisterField):
            continue  # bit fields are in a separate address space
        start = field.address
        end = start + field.count  # exclusive
        spans.append((start, end, name))

    spans.sort()
    for (start_a, end_a, name_a), (start_b, end_b, name_b) in zip(
        spans, spans[1:], strict=False
    ):
        assert end_a <= start_b, (
            f"{component_class.__name__}.{name_a} ({start_a}-{end_a - 1}) overlaps "
            f"{component_class.__name__}.{name_b} ({start_b}-{end_b - 1})"
        )
