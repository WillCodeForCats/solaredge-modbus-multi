"""Tests for the RestoreSensor-based total increasing energy sensors:
SolarEdgeACEnergy (its Inverter/Meter subclasses), MeterVAhIE, MetervarhIE,
SolarEdgeBatteryEnergyExport, and SolarEdgeBatteryEnergyImport.

5193006 "Remove update_accum helper"
1e3db70/5d62943/49de436 "Use RestoreSensor on ...")
Recommended sensor tolerates minor (<1%) backwards accumulator
per the modbus-connection coordinator docs linked in each class's docstring.

Restore-on-startup (async_get_last_sensor_data) is
already covered for SolarEdgeWriteCount and are not re-tested here.
"""

from types import SimpleNamespace

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
    def test_first_value_is_accepted(self):
        entity = _make_ac_energy(raw_value=1000, sf=0)
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_applies_scale_factor(self):
        entity = _make_ac_energy(raw_value=1000, sf=-1)
        entity._process_data()
        assert entity._attr_native_value == 100.0

    def test_increasing_value_updates(self):
        entity = _make_ac_energy(raw_value=1100, sf=0, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 1100

    def test_raw_value_none_is_skipped(self):
        entity = _make_ac_energy(raw_value=None, sf=0, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_na32_sentinel_is_skipped(self):
        entity = _make_ac_energy(raw_value=SunSpecAccum.NA32, sf=0, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_limit32_saturation_is_skipped(self):
        # PR #1040: a fully saturated accumulator (all-1s) must be detected,
        # not accepted as a legitimate value.
        entity = _make_ac_energy(raw_value=SunSpecAccum.LIMIT32, sf=0, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_scale_factor_out_of_range_is_skipped(self):
        entity = _make_ac_energy(raw_value=1000, sf=99, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_minor_decrease_within_one_percent_is_ignored(self):
        # 995 is within [990, 1000) - the SolarEdge firmware glitch band.
        entity = _make_ac_energy(raw_value=995, sf=0, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 1000
        assert entity._log_once is True

    def test_large_decrease_is_accepted(self):
        # Below the 1% tolerance band (e.g. a device swap) is treated as
        # legitimate rather than a glitch, and falls through to update.
        entity = _make_ac_energy(raw_value=500, sf=0, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 500


class TestSolarEdgeACEnergyEnabledByDefault:
    def _make_meter(self, phase, did=201):
        platform = SimpleNamespace(
            uid_base="meter_1",
            meter_data=SimpleNamespace(C_SunSpec_DID=did),
        )
        return SolarEdgeACEnergyMeter(platform, None, None, phase=phase)

    def test_total_phase_none_is_enabled(self):
        assert self._make_meter(phase=None).entity_registry_enabled_default is True

    @pytest.mark.parametrize(
        "phase", ["Exported", "Imported", "Exported_A", "Imported_A"]
    )
    def test_common_phases_are_enabled(self, phase):
        assert self._make_meter(phase=phase).entity_registry_enabled_default is True

    @pytest.mark.parametrize("phase", ["Exported_B", "Exported_C"])
    def test_per_phase_bc_only_enabled_for_three_phase_meters(self, phase):
        # DIDs 203/204 are 3-phase meters; other DIDs don't have B/C legs.
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


@pytest.mark.parametrize("cls, prefix", METER_ENERGY_CLASSES)
class TestMeterEnergyAccumulators:
    def test_first_value_is_accepted(self, cls, prefix):
        entity = _make_meter_energy(cls, prefix, raw_value=1000, sf=0)
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_na32_sentinel_is_skipped(self, cls, prefix):
        entity = _make_meter_energy(
            cls, prefix, raw_value=SunSpecAccum.NA32, sf=0, last=1000
        )
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_limit32_saturation_is_skipped(self, cls, prefix):
        # PR #1040: a fully saturated accumulator (all-1s) must be detected,
        # not accepted as a legitimate value.
        entity = _make_meter_energy(
            cls, prefix, raw_value=SunSpecAccum.LIMIT32, sf=0, last=1000
        )
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_scale_factor_out_of_range_is_skipped(self, cls, prefix):
        entity = _make_meter_energy(cls, prefix, raw_value=1000, sf=99, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_minor_decrease_within_one_percent_is_ignored(self, cls, prefix):
        entity = _make_meter_energy(cls, prefix, raw_value=995, sf=0, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 1000

    def test_large_decrease_is_accepted(self, cls, prefix):
        entity = _make_meter_energy(cls, prefix, raw_value=500, sf=0, last=1000)
        entity._process_data()
        assert entity._attr_native_value == 500

    def test_unique_id_and_name_require_a_phase(self, cls, prefix):
        entity = cls(SimpleNamespace(uid_base="meter_1"), None, None, phase=None)

        with pytest.raises(NotImplementedError):
            _ = entity.unique_id

        with pytest.raises(NotImplementedError):
            _ = entity.name

    def test_disabled_by_default(self, cls, prefix):
        entity = cls(SimpleNamespace(uid_base="meter_1"), None, None, phase="Exported")
        assert entity.entity_registry_enabled_default is False


BATTERY_ENERGY_CLASSES = [
    (SolarEdgeBatteryEnergyExport, "B_Export_Energy_WH"),
    (SolarEdgeBatteryEnergyImport, "B_Import_Energy_WH"),
]


def _make_battery_energy(
    cls, attr, value, allow_reset=False, reset_cycles=3, last=None, count=0
):
    platform = SimpleNamespace(
        uid_base="battery_1",
        battery_data=SimpleNamespace(**{attr: value}),
        allow_battery_energy_reset=allow_reset,
        battery_energy_reset_cycles=reset_cycles,
    )
    entity = cls(platform, None, None)
    entity._last = last
    entity._attr_native_value = last
    entity._count = count
    return entity


@pytest.mark.parametrize("cls, attr", BATTERY_ENERGY_CLASSES)
class TestBatteryEnergyAccumulators:
    def test_first_value_is_accepted(self, cls, attr):
        entity = _make_battery_energy(cls, attr, value=100)
        entity._process_data()
        assert entity._attr_native_value == 100
        assert entity._last == 100

    def test_none_value_is_skipped(self, cls, attr):
        entity = _make_battery_energy(cls, attr, value=None, last=100)
        entity._process_data()
        assert entity._attr_native_value == 100

    def test_uint64_not_implemented_sentinel_is_skipped(self, cls, attr):
        entity = _make_battery_energy(cls, attr, value=0xFFFFFFFFFFFFFFFF, last=100)
        entity._process_data()
        assert entity._attr_native_value == 100

    def test_zero_is_skipped_when_reset_not_allowed(self, cls, attr):
        # A bare 0 usually means "not yet available" rather than a real reset,
        # unless the user has explicitly opted in to battery energy resets.
        entity = _make_battery_energy(cls, attr, value=0, allow_reset=False, last=100)
        entity._process_data()
        assert entity._attr_native_value == 100

    def test_zero_is_accepted_as_first_reading_when_reset_allowed(self, cls, attr):
        entity = _make_battery_energy(cls, attr, value=0, allow_reset=True, last=None)
        entity._process_data()
        assert entity._attr_native_value == 0
        assert entity._last == 0

    def test_increasing_value_updates_and_resets_count(self, cls, attr):
        entity = _make_battery_energy(
            cls, attr, value=150, allow_reset=True, last=100, count=2
        )
        entity._process_data()
        assert entity._attr_native_value == 150
        assert entity._last == 150
        assert entity._count == 0

    def test_decrease_without_reset_allowed_is_logged_and_ignored(self, cls, attr):
        entity = _make_battery_energy(cls, attr, value=50, allow_reset=False, last=100)
        entity._process_data()
        assert entity._attr_native_value == 100
        assert entity._last == 100
        assert entity._log_once is True

    def test_decrease_with_reset_allowed_increments_count_without_resetting_yet(
        self, cls, attr
    ):
        entity = _make_battery_energy(
            cls, attr, value=50, allow_reset=True, reset_cycles=2, last=100, count=0
        )
        entity._process_data()
        assert entity._count == 1
        assert entity._last == 100
        assert entity._attr_native_value == 100

    def test_decrease_confirmed_over_reset_cycles_clears_last(self, cls, attr):
        # battery_energy_reset_cycles=2: the count must exceed the cycle limit
        # (not just reach it) before the drop is trusted as a real reset.
        entity = _make_battery_energy(
            cls, attr, value=50, allow_reset=True, reset_cycles=2, last=100, count=2
        )
        entity._process_data()
        assert entity._count == 0
        assert entity._last is None
        # native_value is left at its old (now stale) value until the next
        # coordinator update re-runs _process_data with _last reset to None.
        assert entity._attr_native_value == 100

    def test_next_update_after_confirmed_reset_accepts_new_baseline(self, cls, attr):
        entity = _make_battery_energy(
            cls, attr, value=50, allow_reset=True, reset_cycles=2, last=None, count=0
        )
        entity._process_data()
        assert entity._attr_native_value == 50
        assert entity._last == 50
