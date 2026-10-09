"""Tests for the RestoreSensor-based total increasing energy sensors.

Covers SolarEdgeACEnergy (its Inverter/Meter subclasses), MeterVAhIE, MetervarhIE,
SolarEdgeBatteryEnergyExport, and SolarEdgeBatteryEnergyImport.

5193006 "Remove update_accum helper"
1e3db70/5d62943/49de436 "Use RestoreSensor on ...")
Recommended sensor tolerates minor (<1%) backwards accumulator
per the modbus-connection coordinator docs linked in each class's docstring.

Restore-on-startup (async_get_last_sensor_data) is
already covered for SolarEdgeWriteCount and are not re-tested here.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.components.sensor import RestoreSensor
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import pytest

from custom_components.solaredge_modbus_multi.const import SunSpecAccum
from custom_components.solaredge_modbus_multi.sensor import (
    MeterVAhIE,
    MetervarhIE,
    SolarEdgeACEnergyInverter,
    SolarEdgeACEnergyMeter,
    SolarEdgeBatteryEnergyExport,
    SolarEdgeBatteryEnergyImport,
)


def _make_ac_energy(raw_value, sf, phase=None, last=None):
    model_key = "AC_Energy_WH" if phase is None else f"AC_Energy_WH_{phase}"
    platform = SimpleNamespace(
        uid_base="inverter_1",
        inverter_data=SimpleNamespace(**{model_key: raw_value, "AC_Energy_WH_SF": sf}),
    )
    entity = SolarEdgeACEnergyInverter(platform, None, None, phase=phase)
    entity._attr_native_value = last
    return entity


class TestSolarEdgeACEnergy:
    """Test solar edge ac energy."""

    def test_first_value_is_accepted(self):
        """Test first value is accepted."""
        entity = _make_ac_energy(raw_value=1000, sf=0)
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_applies_scale_factor(self):
        """Test applies scale factor."""
        entity = _make_ac_energy(raw_value=1000, sf=-1)
        entity._process_data()
        assert entity._attr_native_value == 100.0

    def test_increasing_value_updates(self):
        """Test increasing value updates."""
        entity = _make_ac_energy(raw_value=1100, sf=0, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 1100

    def test_raw_value_none_is_skipped(self):
        """Test raw value none is skipped."""
        entity = _make_ac_energy(raw_value=None, sf=0, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_na32_sentinel_is_skipped(self):
        """Test na32 sentinel is skipped."""
        entity = _make_ac_energy(raw_value=SunSpecAccum.NA32, sf=0, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_limit32_saturation_is_skipped(self):
        # PR #1040: a fully saturated accumulator (all-1s) must be detected,
        # not accepted as a legitimate value.
        """Test limit32 saturation is skipped."""
        entity = _make_ac_energy(raw_value=SunSpecAccum.LIMIT32, sf=0, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_scale_factor_out_of_range_is_skipped(self):
        """Test scale factor out of range is skipped."""
        entity = _make_ac_energy(raw_value=1000, sf=99, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_minor_decrease_within_one_percent_is_ignored(self):
        # 995 is within [990, 1000) - the SolarEdge firmware glitch band.
        """Test minor decrease within one percent is ignored."""
        entity = _make_ac_energy(raw_value=995, sf=0, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 1000
        assert entity._log_once is True

    def test_large_decrease_is_accepted(self):
        # Below the 1% tolerance band (e.g. a device swap) is treated as
        # legitimate rather than a glitch, and falls through to update.
        """Test large decrease is accepted."""
        entity = _make_ac_energy(raw_value=500, sf=0, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 500


class TestSolarEdgeACEnergyEnabledByDefault:
    """Test solar edge ac energy enabled by default."""

    def _make_meter(self, phase, did=201):
        platform = SimpleNamespace(
            uid_base="meter_1",
            meter_data=SimpleNamespace(C_SunSpec_DID=did),
        )
        return SolarEdgeACEnergyMeter(platform, None, None, phase=phase)

    def test_total_phase_none_is_enabled(self):
        """Test total phase none is enabled."""
        assert self._make_meter(phase=None).entity_registry_enabled_default is True

    @pytest.mark.parametrize(
        "phase", ["Exported", "Imported", "Exported_A", "Imported_A"]
    )
    def test_common_phases_are_enabled(self, phase):
        """Test common phases are enabled."""
        assert self._make_meter(phase=phase).entity_registry_enabled_default is True

    @pytest.mark.parametrize("phase", ["Exported_B", "Exported_C"])
    def test_per_phase_bc_only_enabled_for_three_phase_meters(self, phase):
        # DIDs 203/204 are 3-phase meters; other DIDs don't have B/C legs.
        """Test per phase bc only enabled for three phase meters."""
        three_phase = self._make_meter(phase=phase, did=203)
        single_phase = self._make_meter(phase=phase, did=201)

        assert three_phase.entity_registry_enabled_default is True
        assert single_phase.entity_registry_enabled_default is False


METER_ENERGY_CLASSES = [(MeterVAhIE, "M_VAh"), (MetervarhIE, "M_varh")]


def _make_meter_energy(cls, prefix, raw_value, sf, phase="Exported", last=None):
    platform = SimpleNamespace(
        uid_base="meter_1",
        meter_data=SimpleNamespace(
            **{f"{prefix}_{phase}": raw_value, f"{prefix}_SF": sf}
        ),
    )
    entity = cls(platform, None, None, phase=phase)
    entity._attr_native_value = last
    return entity


@pytest.mark.parametrize(("cls", "prefix"), METER_ENERGY_CLASSES)
class TestMeterEnergyAccumulators:
    """Test meter energy accumulators."""

    def test_first_value_is_accepted(self, cls, prefix):
        """Test first value is accepted."""
        entity = _make_meter_energy(cls, prefix, raw_value=1000, sf=0)
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_na32_sentinel_is_skipped(self, cls, prefix):
        """Test na32 sentinel is skipped."""
        entity = _make_meter_energy(
            cls, prefix, raw_value=SunSpecAccum.NA32, sf=0, last=1000
        )
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_limit32_saturation_is_skipped(self, cls, prefix):
        # PR #1040: a fully saturated accumulator (all-1s) must be detected,
        # not accepted as a legitimate value.
        """Test limit32 saturation is skipped."""
        entity = _make_meter_energy(
            cls, prefix, raw_value=SunSpecAccum.LIMIT32, sf=0, last=1000
        )
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_scale_factor_out_of_range_is_skipped(self, cls, prefix):
        """Test scale factor out of range is skipped."""
        entity = _make_meter_energy(cls, prefix, raw_value=1000, sf=99, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_minor_decrease_within_one_percent_is_ignored(self, cls, prefix):
        """Test minor decrease within one percent is ignored."""
        entity = _make_meter_energy(cls, prefix, raw_value=995, sf=0, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_large_decrease_is_accepted(self, cls, prefix):
        """Test large decrease is accepted."""
        entity = _make_meter_energy(cls, prefix, raw_value=500, sf=0, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 500

    def test_unique_id_and_name_require_a_phase(self, cls, prefix):
        """Test unique id and name require a phase."""
        entity = cls(SimpleNamespace(uid_base="meter_1"), None, None, phase=None)

        with pytest.raises(NotImplementedError):
            _ = entity.unique_id

        with pytest.raises(NotImplementedError):
            _ = entity.name

    def test_disabled_by_default(self, cls, prefix):
        """Test disabled by default."""
        entity = cls(SimpleNamespace(uid_base="meter_1"), None, None, phase="Exported")
        assert entity.entity_registry_enabled_default is False


BATTERY_ENERGY_CLASSES = [
    (SolarEdgeBatteryEnergyExport, "B_Export_Energy_WH"),
    (SolarEdgeBatteryEnergyImport, "B_Import_Energy_WH"),
]


def _make_battery_energy(cls, attr, value, total=None, prev_raw=None):
    platform = SimpleNamespace(
        uid_base="battery_1",
        battery_data=SimpleNamespace(**{attr: value}),
    )
    entity = cls(platform, None, None)
    entity._attr_native_value = total
    entity._prev_raw = prev_raw
    return entity


@pytest.mark.parametrize(("cls", "attr"), BATTERY_ENERGY_CLASSES)
class TestBatteryEnergyAccumulators:
    """Test battery energy accumulators."""

    def test_first_value_becomes_total_and_reference(self, cls, attr):
        """Test first value becomes total and reference."""
        entity = _make_battery_energy(cls, attr, value=100)
        entity._process_data()
        assert entity._attr_native_value == 100
        assert entity._prev_raw == 100

    @pytest.mark.parametrize("value", [None, 0xFFFFFFFFFFFFFFFF, 0])
    def test_unusable_values_are_skipped(self, cls, attr, value):
        """Test unusable values are skipped."""
        entity = _make_battery_energy(cls, attr, value=value, total=500, prev_raw=100)
        entity._process_data()
        assert entity._attr_native_value == 500
        assert entity._prev_raw == 100

    def test_zero_is_not_accepted_as_first_reading(self, cls, attr):
        """Test zero is not accepted as first reading."""
        entity = _make_battery_energy(cls, attr, value=0)
        entity._process_data()
        assert entity._attr_native_value is None
        assert entity._prev_raw is None

    def test_increase_adds_delta_to_total(self, cls, attr):
        """Test increase adds delta to total."""
        entity = _make_battery_energy(cls, attr, value=150, total=500, prev_raw=100)
        entity._process_data()
        assert entity._attr_native_value == 550
        assert entity._prev_raw == 150

    def test_unchanged_value_adds_nothing(self, cls, attr):
        """Test unchanged value adds nothing."""
        entity = _make_battery_energy(cls, attr, value=100, total=500, prev_raw=100)
        entity._process_data()
        assert entity._attr_native_value == 500
        assert entity._prev_raw == 100

    def test_decrease_keeps_total_and_rebaselines(self, cls, attr):
        """Test decrease keeps total and rebaselines."""
        entity = _make_battery_energy(cls, attr, value=50, total=500, prev_raw=100)
        entity._process_data()
        assert entity._attr_native_value == 500
        assert entity._prev_raw == 50

    def test_counting_resumes_after_decrease(self, cls, attr):
        """Test counting resumes after decrease."""
        entity = _make_battery_energy(cls, attr, value=50, total=500, prev_raw=100)
        entity._process_data()
        setattr(entity._platform.battery_data, attr, 70)
        entity._process_data()
        assert entity._attr_native_value == 520
        assert entity._prev_raw == 70

    def test_restored_total_without_reference_only_sets_reference(self, cls, attr):
        """Test restored total without reference only sets reference."""
        entity = _make_battery_energy(cls, attr, value=900, total=500)
        entity._process_data()
        assert entity._attr_native_value == 500
        assert entity._prev_raw == 900

    def test_stored_data_includes_reference_reading(self, cls, attr):
        """Test stored data includes reference reading."""
        entity = _make_battery_energy(cls, attr, value=150, total=500, prev_raw=100)
        stored = entity.extra_restore_state_data.as_dict()
        assert stored["native_value"] == 500
        assert stored["prev_raw"] == 100

    async def test_restore_loads_total_and_reference(self, cls, attr):
        """Test restore loads total and reference."""
        entity = _make_battery_energy(cls, attr, value=150)
        restored = SimpleNamespace(
            as_dict=lambda: {"native_value": 500, "prev_raw": 100}
        )
        with (
            patch.object(
                RestoreSensor,
                "async_get_last_extra_data",
                AsyncMock(return_value=restored),
            ),
            patch.object(CoordinatorEntity, "async_added_to_hass", AsyncMock()),
        ):
            await entity.async_added_to_hass()
        assert entity._attr_native_value == 550
        assert entity._prev_raw == 150
