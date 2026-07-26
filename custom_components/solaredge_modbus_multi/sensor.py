from __future__ import annotations

import datetime
import logging
import re
from dataclasses import dataclass

from awesomeversion import AwesomeVersion
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfReactivePower,
    UnitOfTemperature,
)
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SolarEdgeConfigEntry
from .const import (
    BATTERY_STATUS,
    BATTERY_STATUS_TEXT,
    DEVICE_STATUS,
    DEVICE_STATUS_TEXT,
    ENERGY_VOLT_AMPERE_HOUR,
    ENERGY_VOLT_AMPERE_REACTIVE_HOUR,
    INVERTED_POWER_VERSION,
    METER_EVENTS,
    MMPPT_EVENTS,
    RRCR_STATUS,
    SUNSPEC_DID,
    SUNSPEC_SF_RANGE,
    VENDOR4_STATUS,
    VENDOR_STATUS,
    BatteryLimit,
    SunSpecAccum,
    SunSpecNotImpl,
)
from .entity import SolarEdgeEntityBase
from .helpers import float_to_hex, is_float32_not_impl, update_accum

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SolarEdgeSensorEntityDescription(SensorEntityDescription):
    """Describes a SolarEdge sensor with integration-specific extras.

    model_key: decoded_model register backing the sensor, for shared bases
    whose value/availability logic only differs by register.
    """

    model_key: str | None = None


def _import_export_icon(phase: str | None) -> str | None:
    """Icon for import/export energy accumulators, or None for other phases."""
    if phase is None:
        return None

    if re.match("import", phase.lower()):
        return "mdi:transmission-tower-export"

    if re.match("export", phase.lower()):
        return "mdi:transmission-tower-import"

    return None


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: SolarEdgeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub = config_entry.runtime_data.hub
    coordinator = config_entry.runtime_data.coordinator

    entities = []

    for inverter in hub.inverters:
        entities.append(SolarEdgeLastUpdate(inverter, config_entry, coordinator))
        entities.append(SolarEdgeDevice(inverter, config_entry, coordinator))
        entities.append(Version(inverter, config_entry, coordinator))
        entities.append(SolarEdgeInverterStatus(inverter, config_entry, coordinator))
        entities.append(StatusVendor(inverter, config_entry, coordinator))
        if inverter.use_status_vendor4:
            entities.append(StatusVendor4(inverter, config_entry, coordinator))
        entities.append(ACCurrentSensor(inverter, config_entry, coordinator))
        entities.append(ACCurrentSensor(inverter, config_entry, coordinator, "A"))
        entities.append(ACCurrentSensor(inverter, config_entry, coordinator, "B"))
        entities.append(ACCurrentSensor(inverter, config_entry, coordinator, "C"))
        entities.append(VoltageSensor(inverter, config_entry, coordinator, "AB"))
        entities.append(VoltageSensor(inverter, config_entry, coordinator, "BC"))
        entities.append(VoltageSensor(inverter, config_entry, coordinator, "CA"))
        entities.append(VoltageSensor(inverter, config_entry, coordinator, "AN"))
        entities.append(VoltageSensor(inverter, config_entry, coordinator, "BN"))
        entities.append(VoltageSensor(inverter, config_entry, coordinator, "CN"))
        entities.append(ACPower(inverter, config_entry, coordinator))
        entities.append(ACFrequency(inverter, config_entry, coordinator))
        entities.append(ACVoltAmp(inverter, config_entry, coordinator))
        entities.append(ACVoltAmpReactive(inverter, config_entry, coordinator))
        entities.append(ACPowerFactor(inverter, config_entry, coordinator))
        entities.append(SolarEdgeACEnergy(inverter, config_entry, coordinator))
        entities.append(DCCurrent(inverter, config_entry, coordinator))
        entities.append(DCVoltage(inverter, config_entry, coordinator))
        entities.append(DCPower(inverter, config_entry, coordinator))
        entities.append(HeatSinkTemperature(inverter, config_entry, coordinator))

        if hub.option_detect_extras and inverter.global_power_control:
            entities.append(SolarEdgeRRCR(inverter, config_entry, coordinator))
            entities.append(
                SolarEdgeActivePowerLimit(inverter, config_entry, coordinator)
            )
            entities.append(SolarEdgeCosPhi(inverter, config_entry, coordinator))

        if hub.option_detect_extras and inverter.advanced_power_control:
            entities.append(
                SolarEdgeCommitControlSettings(inverter, config_entry, coordinator)
            )
            entities.append(
                SolarEdgeDefaultControlSettings(inverter, config_entry, coordinator)
            )

        if inverter.is_mmppt:
            entities.append(SolarEdgeMMPPTEvents(inverter, config_entry, coordinator))

            for mmppt_unit in inverter.mmppt_units:
                entities.append(
                    SolarEdgeDCCurrentMMPPT(mmppt_unit, config_entry, coordinator)
                )
                entities.append(
                    SolarEdgeDCVoltageMMPPT(mmppt_unit, config_entry, coordinator)
                )
                entities.append(
                    SolarEdgeDCPowerMMPPT(mmppt_unit, config_entry, coordinator)
                )
                entities.append(
                    SolarEdgeTemperatureMMPPT(mmppt_unit, config_entry, coordinator)
                )

    for meter in hub.meters:
        entities.append(SolarEdgeLastUpdate(meter, config_entry, coordinator))
        entities.append(SolarEdgeDevice(meter, config_entry, coordinator))
        entities.append(Version(meter, config_entry, coordinator))
        entities.append(MeterEvents(meter, config_entry, coordinator))
        entities.append(ACCurrentSensor(meter, config_entry, coordinator))
        entities.append(ACCurrentSensor(meter, config_entry, coordinator, "A"))
        entities.append(ACCurrentSensor(meter, config_entry, coordinator, "B"))
        entities.append(ACCurrentSensor(meter, config_entry, coordinator, "C"))
        entities.append(VoltageSensor(meter, config_entry, coordinator, "LN"))
        entities.append(VoltageSensor(meter, config_entry, coordinator, "AN"))
        entities.append(VoltageSensor(meter, config_entry, coordinator, "BN"))
        entities.append(VoltageSensor(meter, config_entry, coordinator, "CN"))
        entities.append(VoltageSensor(meter, config_entry, coordinator, "LL"))
        entities.append(VoltageSensor(meter, config_entry, coordinator, "AB"))
        entities.append(VoltageSensor(meter, config_entry, coordinator, "BC"))
        entities.append(VoltageSensor(meter, config_entry, coordinator, "CA"))
        entities.append(ACFrequency(meter, config_entry, coordinator))
        entities.append(ACPower(meter, config_entry, coordinator))
        entities.append(ACPowerInverted(meter, config_entry, coordinator))
        entities.append(ACPower(meter, config_entry, coordinator, "A"))
        entities.append(ACPower(meter, config_entry, coordinator, "B"))
        entities.append(ACPower(meter, config_entry, coordinator, "C"))
        entities.append(ACVoltAmp(meter, config_entry, coordinator))
        entities.append(ACVoltAmp(meter, config_entry, coordinator, "A"))
        entities.append(ACVoltAmp(meter, config_entry, coordinator, "B"))
        entities.append(ACVoltAmp(meter, config_entry, coordinator, "C"))
        entities.append(ACVoltAmpReactive(meter, config_entry, coordinator))
        entities.append(ACVoltAmpReactive(meter, config_entry, coordinator, "A"))
        entities.append(ACVoltAmpReactive(meter, config_entry, coordinator, "B"))
        entities.append(ACVoltAmpReactive(meter, config_entry, coordinator, "C"))
        entities.append(ACPowerFactor(meter, config_entry, coordinator))
        entities.append(ACPowerFactor(meter, config_entry, coordinator, "A"))
        entities.append(ACPowerFactor(meter, config_entry, coordinator, "B"))
        entities.append(ACPowerFactor(meter, config_entry, coordinator, "C"))
        entities.append(SolarEdgeACEnergy(meter, config_entry, coordinator, "Exported"))
        entities.append(
            SolarEdgeACEnergy(meter, config_entry, coordinator, "Exported_A")
        )
        entities.append(
            SolarEdgeACEnergy(meter, config_entry, coordinator, "Exported_B")
        )
        entities.append(
            SolarEdgeACEnergy(meter, config_entry, coordinator, "Exported_C")
        )
        entities.append(SolarEdgeACEnergy(meter, config_entry, coordinator, "Imported"))
        entities.append(
            SolarEdgeACEnergy(meter, config_entry, coordinator, "Imported_A")
        )
        entities.append(
            SolarEdgeACEnergy(meter, config_entry, coordinator, "Imported_B")
        )
        entities.append(
            SolarEdgeACEnergy(meter, config_entry, coordinator, "Imported_C")
        )
        entities.append(MeterVAhIE(meter, config_entry, coordinator, "Exported"))
        entities.append(MeterVAhIE(meter, config_entry, coordinator, "Exported_A"))
        entities.append(MeterVAhIE(meter, config_entry, coordinator, "Exported_B"))
        entities.append(MeterVAhIE(meter, config_entry, coordinator, "Exported_C"))
        entities.append(MeterVAhIE(meter, config_entry, coordinator, "Imported"))
        entities.append(MeterVAhIE(meter, config_entry, coordinator, "Imported_A"))
        entities.append(MeterVAhIE(meter, config_entry, coordinator, "Imported_B"))
        entities.append(MeterVAhIE(meter, config_entry, coordinator, "Imported_C"))
        entities.append(MetervarhIE(meter, config_entry, coordinator, "Import_Q1"))
        entities.append(MetervarhIE(meter, config_entry, coordinator, "Import_Q1_A"))
        entities.append(MetervarhIE(meter, config_entry, coordinator, "Import_Q1_B"))
        entities.append(MetervarhIE(meter, config_entry, coordinator, "Import_Q1_C"))
        entities.append(MetervarhIE(meter, config_entry, coordinator, "Import_Q2"))
        entities.append(MetervarhIE(meter, config_entry, coordinator, "Import_Q2_A"))
        entities.append(MetervarhIE(meter, config_entry, coordinator, "Import_Q2_B"))
        entities.append(MetervarhIE(meter, config_entry, coordinator, "Import_Q2_C"))
        entities.append(MetervarhIE(meter, config_entry, coordinator, "Export_Q3"))
        entities.append(MetervarhIE(meter, config_entry, coordinator, "Export_Q3_A"))
        entities.append(MetervarhIE(meter, config_entry, coordinator, "Export_Q3_B"))
        entities.append(MetervarhIE(meter, config_entry, coordinator, "Export_Q3_C"))
        entities.append(MetervarhIE(meter, config_entry, coordinator, "Export_Q4"))
        entities.append(MetervarhIE(meter, config_entry, coordinator, "Export_Q4_A"))
        entities.append(MetervarhIE(meter, config_entry, coordinator, "Export_Q4_B"))
        entities.append(MetervarhIE(meter, config_entry, coordinator, "Export_Q4_C"))

    for battery in hub.batteries:
        entities.append(SolarEdgeLastUpdate(battery, config_entry, coordinator))
        entities.append(SolarEdgeDevice(battery, config_entry, coordinator))
        entities.append(Version(battery, config_entry, coordinator))
        entities.append(SolarEdgeBatteryAvgTemp(battery, config_entry, coordinator))
        entities.append(SolarEdgeBatteryMaxTemp(battery, config_entry, coordinator))
        entities.append(SolarEdgeBatteryVoltage(battery, config_entry, coordinator))
        entities.append(SolarEdgeBatteryCurrent(battery, config_entry, coordinator))
        entities.append(SolarEdgeBatteryPower(battery, config_entry, coordinator))
        entities.append(
            SolarEdgeBatteryPowerInverted(battery, config_entry, coordinator)
        )
        entities.append(
            SolarEdgeBatteryEnergyExport(battery, config_entry, coordinator)
        )
        entities.append(
            SolarEdgeBatteryEnergyImport(battery, config_entry, coordinator)
        )
        entities.append(SolarEdgeBatteryMaxEnergy(battery, config_entry, coordinator))
        entities.append(
            SolarEdgeBatteryMaxChargePower(battery, config_entry, coordinator)
        )
        entities.append(
            SolarEdgeBatteryMaxDischargePower(battery, config_entry, coordinator)
        )
        entities.append(
            SolarEdgeBatteryMaxChargePeakPower(battery, config_entry, coordinator)
        )
        entities.append(
            SolarEdgeBatteryMaxDischargePeakPower(battery, config_entry, coordinator)
        )
        entities.append(
            SolarEdgeBatteryAvailableEnergy(battery, config_entry, coordinator)
        )
        entities.append(SolarEdgeBatterySOH(battery, config_entry, coordinator))
        entities.append(SolarEdgeBatterySOE(battery, config_entry, coordinator))
        entities.append(SolarEdgeBatteryStatus(battery, config_entry, coordinator))

    for evse in hub.evses:
        entities.append(Version(evse, config_entry, coordinator))

    if entities:
        async_add_entities(entities)


class SolarEdgeSensorBase(SolarEdgeEntityBase, SensorEntity):
    """Base sensor: static metadata comes from the entity_description.

    unique_id and name default to a `{uid_base}_{key}[_{phase}]` scheme;
    classes with legacy id patterns override the _description_* hooks so
    existing registry entries and statistics are preserved.
    """

    entity_description: SolarEdgeSensorEntityDescription

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator)

        self._phase = phase

        description = getattr(self, "entity_description", None)
        if description is not None:
            self._attr_unique_id = self._description_unique_id(description)
            self._attr_name = self._description_name(description)

    def _description_unique_id(
        self, description: SolarEdgeSensorEntityDescription
    ) -> str:
        if self._phase is None:
            return f"{self._platform.uid_base}_{description.key}"

        return f"{self._platform.uid_base}_{description.key}_{self._phase.lower()}"

    def _description_name(self, description: SolarEdgeSensorEntityDescription) -> str:
        if self._phase is None:
            return description.name

        return f"{description.name} {self._phase.upper()}"

    def scale_factor(self, x: int, y: int):
        return x * (10**y)

    def sf_precision(self, model: dict, sf_key: str):
        """Display precision from a scale factor, or None if not implemented."""
        try:
            sf = model[sf_key]
        except (KeyError, TypeError):
            return None

        if sf == SunSpecNotImpl.INT16 or sf not in SUNSPEC_SF_RANGE:
            return None

        return abs(min(sf, 0))

    def scaled_or_none(self, value_key: str, sf_key: str, not_impl, model=None):
        """Scaled register value, or None when value or SF is not implemented."""
        if model is None:
            model = self._platform.decoded_model

        try:
            value = model[value_key]
            sf = model[sf_key]

            if (
                value == not_impl
                or sf == SunSpecNotImpl.INT16
                or sf not in SUNSPEC_SF_RANGE
            ):
                return None

            return self.scale_factor(value, sf)

        except (TypeError, KeyError):
            return None


class SolarEdgeDevice(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="device",
        name="Device",
        entity_category=EntityCategory.DIAGNOSTIC,
    )

    @property
    def native_value(self):
        return self._platform.model

    @property
    def extra_state_attributes(self):
        attrs = {}

        try:
            if (
                not is_float32_not_impl(self._platform.decoded_common["B_RatedEnergy"])
                and self._platform.decoded_common["B_RatedEnergy"] > 0
            ):
                attrs["batt_rated_energy"] = self._platform.decoded_common[
                    "B_RatedEnergy"
                ]

        except KeyError:
            pass

        attrs["device_id"] = self._platform.device_address
        attrs["manufacturer"] = self._platform.manufacturer
        attrs["model"] = self._platform.model

        if len(self._platform.option) > 0:
            attrs["option"] = self._platform.option

        if self._platform.has_parent:
            attrs["parent_device_id"] = self._platform.inverter_unit_id

        attrs["serial_number"] = self._platform.serial

        try:
            if self._platform.decoded_model["C_SunSpec_DID"] in SUNSPEC_DID:
                attrs["sunspec_device"] = SUNSPEC_DID[
                    self._platform.decoded_model["C_SunSpec_DID"]
                ]

        except KeyError:
            pass

        try:
            attrs["sunspec_did"] = self._platform.decoded_model["C_SunSpec_DID"]

        except KeyError:
            pass

        try:
            if self._platform.decoded_mmppt is not None:
                try:
                    if self._platform.decoded_mmppt["mmppt_DID"] in SUNSPEC_DID:
                        attrs["mmppt_device"] = SUNSPEC_DID[
                            self._platform.decoded_mmppt["mmppt_DID"]
                        ]

                except KeyError:
                    pass

                attrs["mmppt_did"] = self._platform.decoded_mmppt["mmppt_DID"]
                attrs["mmppt_units"] = self._platform.decoded_mmppt["mmppt_Units"]

        except AttributeError:
            pass

        return attrs


class Version(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="version",
        name="Version",
        entity_category=EntityCategory.DIAGNOSTIC,
    )

    @property
    def native_value(self):
        return self._platform.fw_version


class ACCurrentSensor(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="ac_current",
        name="AC Current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
    )

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator, phase)

        if self._platform.decoded_model["C_SunSpec_DID"] in [101, 102, 103]:
            self.SUNSPEC_NOT_IMPL = SunSpecNotImpl.UINT16
        elif self._platform.decoded_model["C_SunSpec_DID"] in [201, 202, 203, 204]:
            self.SUNSPEC_NOT_IMPL = SunSpecNotImpl.INT16
        else:
            raise RuntimeError(
                "ACCurrentSensor C_SunSpec_DID "
                f"{self._platform.decoded_model['C_SunSpec_DID']}"
            )

    @property
    def entity_registry_enabled_default(self) -> bool:
        if self._phase is None:
            return True

        elif self._platform.decoded_model["C_SunSpec_DID"] in [
            103,
            203,
            204,
        ] and self._phase in [
            "A",
            "B",
            "C",
        ]:
            return True

        else:
            return False

    @property
    def native_value(self):
        if self._phase is None:
            model_key = "AC_Current"
        else:
            model_key = f"AC_Current_{self._phase.upper()}"

        return self.scaled_or_none(model_key, "AC_Current_SF", self.SUNSPEC_NOT_IMPL)

    @property
    def suggested_display_precision(self):
        return self.sf_precision(self._platform.decoded_model, "AC_Current_SF")


class VoltageSensor(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="ac_voltage",
        name="AC Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
    )

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator, phase)

        if self._platform.decoded_model["C_SunSpec_DID"] in [101, 102, 103]:
            self.SUNSPEC_NOT_IMPL = SunSpecNotImpl.UINT16
        elif self._platform.decoded_model["C_SunSpec_DID"] in [201, 202, 203, 204]:
            self.SUNSPEC_NOT_IMPL = SunSpecNotImpl.INT16
        else:
            raise RuntimeError(
                "ACCurrentSensor C_SunSpec_DID "
                f"{self._platform.decoded_model['C_SunSpec_DID']}"
            )

    @property
    def entity_registry_enabled_default(self) -> bool:
        if self._phase is None:
            raise NotImplementedError

        elif self._phase in ["LN", "LL", "AB"]:
            return True

        elif self._platform.decoded_model["C_SunSpec_DID"] in [
            103,
            203,
            204,
        ] and self._phase in [
            "BC",
            "CA",
            "AN",
            "BN",
            "CN",
        ]:
            return True

        else:
            return False

    @property
    def native_value(self):
        if self._phase is None:
            model_key = "AC_Voltage"
        else:
            model_key = f"AC_Voltage_{self._phase.upper()}"

        return self.scaled_or_none(model_key, "AC_Voltage_SF", self.SUNSPEC_NOT_IMPL)

    @property
    def suggested_display_precision(self):
        return self.sf_precision(self._platform.decoded_model, "AC_Voltage_SF")


class ACPower(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="ac_power",
        name="AC Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:solar-power",
    )

    @property
    def entity_registry_enabled_default(self) -> bool:
        if self._phase is None:
            return True

        elif self._platform.decoded_model["C_SunSpec_DID"] in [
            203,
            204,
        ] and self._phase in [
            "A",
            "B",
            "C",
        ]:
            return True

        else:
            return False

    @property
    def native_value(self):
        if self._phase is None:
            model_key = "AC_Power"
        else:
            model_key = f"AC_Power_{self._phase.upper()}"

        try:
            if (
                self._platform.decoded_model[model_key] == SunSpecNotImpl.INT16
                or self._platform.decoded_model["AC_Power_SF"] == SunSpecNotImpl.INT16
            ):
                return None

            else:
                return self.scale_factor(
                    self._platform.decoded_model[model_key],
                    self._platform.decoded_model["AC_Power_SF"],
                )

        except TypeError:
            return None

    @property
    def suggested_display_precision(self):
        return self.sf_precision(self._platform.decoded_model, "AC_Power_SF")


class ACPowerInverted(ACPower):
    """Inverted AC power sensor for HA 2025.12 energy dashboard.

    HA defines grid power as positive=import, negative=export.
    SolarEdge meters use opposite convention. This class negates values.
    """

    def _description_unique_id(
        self, description: SolarEdgeSensorEntityDescription
    ) -> str:
        return f"{super()._description_unique_id(description)}_inverted"

    def _description_name(self, description: SolarEdgeSensorEntityDescription) -> str:
        return f"{super()._description_name(description)} Inverted"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return AwesomeVersion(HA_VERSION) < AwesomeVersion(INVERTED_POWER_VERSION)

    @property
    def native_value(self):
        value = super().native_value
        return None if value is None else -value


class ACFrequency(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="ac_frequency",
        name="AC Frequency",
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
    )

    @property
    def native_value(self):
        return self.scaled_or_none(
            "AC_Frequency", "AC_Frequency_SF", SunSpecNotImpl.UINT16
        )

    @property
    def suggested_display_precision(self):
        return self.sf_precision(self._platform.decoded_model, "AC_Frequency_SF")


class ACVoltAmp(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="ac_va",
        name="AC Apparent Power",
        device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        entity_registry_enabled_default=False,
    )

    @property
    def native_value(self):
        if self._phase is None:
            model_key = "AC_VA"
        else:
            model_key = f"AC_VA_{self._phase.upper()}"

        return self.scaled_or_none(model_key, "AC_VA_SF", SunSpecNotImpl.INT16)

    @property
    def suggested_display_precision(self):
        return self.sf_precision(self._platform.decoded_model, "AC_VA_SF")


class ACVoltAmpReactive(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="ac_var",
        name="AC Reactive Power",
        device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
        entity_registry_enabled_default=False,
    )

    @property
    def native_value(self):
        if self._phase is None:
            model_key = "AC_var"
        else:
            model_key = f"AC_var_{self._phase.upper()}"

        return self.scaled_or_none(model_key, "AC_var_SF", SunSpecNotImpl.INT16)

    @property
    def suggested_display_precision(self):
        return self.sf_precision(self._platform.decoded_model, "AC_var_SF")


class ACPowerFactor(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="ac_pf",
        name="AC Power Factor",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_registry_enabled_default=False,
    )

    @property
    def native_value(self):
        if self._phase is None:
            model_key = "AC_PF"
        else:
            model_key = f"AC_PF_{self._phase.upper()}"

        return self.scaled_or_none(model_key, "AC_PF_SF", SunSpecNotImpl.INT16)

    @property
    def suggested_display_precision(self):
        return self.sf_precision(self._platform.decoded_model, "AC_PF_SF")


class SolarEdgeACEnergy(SolarEdgeSensorBase):
    """SolarEdge sensor for AC Energy watt-hour meters."""

    entity_description = SolarEdgeSensorEntityDescription(
        key="ac_energy_kwh",
        name="AC Energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
    )

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator, phase)

        self._last = None
        self._value = None
        self._log_once = False

        if self._phase is None:
            self._model_key = "AC_Energy_WH"
        else:
            self._model_key = f"AC_Energy_WH_{self._phase}"

        self._attr_icon = _import_export_icon(self._phase)

    # older versions of the integration converted to kWh internally
    # before home assistant had UI configurable units and precision
    # changing the unique_id now would cause new entities to be created
    def _description_unique_id(
        self, description: SolarEdgeSensorEntityDescription
    ) -> str:
        if self._phase is None:
            return f"{self._platform.uid_base}_{description.key}"

        return f"{self._platform.uid_base}_{self._phase.lower()}_kwh"

    def _description_name(self, description: SolarEdgeSensorEntityDescription) -> str:
        if self._phase is None:
            return description.name

        return f"{description.name} {re.sub('_', ' ', self._phase)}"

    @property
    def entity_registry_enabled_default(self) -> bool:
        if self._phase is None or self._phase in [
            "Exported",
            "Imported",
            "Exported_A",
            "Imported_A",
        ]:
            return True

        if self._platform.decoded_model["C_SunSpec_DID"] in [
            203,
            204,
        ] and self._phase in [
            "Exported_B",
            "Exported_C",
            "Imported_B",
            "Imported_C",
        ]:
            return True

        return False

    @property
    def available(self) -> bool:
        try:
            if (
                self._platform.decoded_model[self._model_key] == SunSpecAccum.NA32
                or self._platform.decoded_model[self._model_key] > SunSpecAccum.LIMIT32
                or self._platform.decoded_model["AC_Energy_WH_SF"]
                not in SUNSPEC_SF_RANGE
            ):
                return False

            if self._last is None:
                self._last = 0

            self._value = self.scale_factor(
                self._platform.decoded_model[self._model_key],
                self._platform.decoded_model["AC_Energy_WH_SF"],
            )

            if self._value < self._last:
                if not self._log_once:
                    _LOGGER.warning(
                        "Inverter accumulator went backwards; this is a SolarEdge bug: "
                        f"{self._model_key} {self._value} < {self._last}"
                    )
                    self._log_once = True

                return False

        except KeyError:
            return False

        except (ZeroDivisionError, OverflowError) as e:
            _LOGGER.debug(f"total_increasing {self._model_key} exception: {e}")
            return False

        self._log_once = False
        return super().available

    @property
    def native_value(self):
        self._last = self._value
        return self._value


class DCCurrent(SolarEdgeSensorBase):
    """DC Current for a SolarEdge inverter."""

    entity_description = SolarEdgeSensorEntityDescription(
        key="dc_current",
        name="DC Current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-dc",
    )

    @property
    def available(self) -> bool:
        if (
            self._platform.decoded_model["I_DC_Current"] == SunSpecNotImpl.UINT16
            or self._platform.decoded_model["I_DC_Current_SF"] == SunSpecNotImpl.INT16
            or self._platform.decoded_model["I_DC_Current_SF"] not in SUNSPEC_SF_RANGE
        ):
            return False

        return super().available

    @property
    def native_value(self):
        try:
            return self.scale_factor(
                self._platform.decoded_model["I_DC_Current"],
                self._platform.decoded_model["I_DC_Current_SF"],
            )

        except TypeError:
            return None

    @property
    def suggested_display_precision(self):
        return self.sf_precision(self._platform.decoded_model, "I_DC_Current_SF")


class SolarEdgeMMPPTSensorBase(SolarEdgeSensorBase):
    """Sensor on a Synergy MMPPT unit.

    The platform is the MMPPT unit; ids derive from the parent inverter's
    uid_base with the unit number appended to the description key.
    """

    def _description_unique_id(
        self, description: SolarEdgeSensorEntityDescription
    ) -> str:
        return (
            f"{self._platform.inverter.uid_base}_{description.key}{self._platform.unit}"
        )


class SolarEdgeDCCurrentMMPPT(SolarEdgeMMPPTSensorBase):
    """DC Current for Synergy MMPPT units."""

    entity_description = SolarEdgeSensorEntityDescription(
        key="dc_current_mmppt",
        name="DC Current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        icon="mdi:current-dc",
    )

    @property
    def available(self) -> bool:
        if (
            self._platform.inverter.decoded_model[self._platform.mmppt_key]["DCA"]
            == SunSpecNotImpl.INT16
            or self._platform.inverter.decoded_model["mmppt_DCA_SF"]
            == SunSpecNotImpl.INT16
            or self._platform.inverter.decoded_model["mmppt_DCA_SF"]
            not in SUNSPEC_SF_RANGE
        ):
            return False

        return super().available

    @property
    def native_value(self):
        return self.scale_factor(
            self._platform.inverter.decoded_model[self._platform.mmppt_key]["DCA"],
            self._platform.inverter.decoded_model["mmppt_DCA_SF"],
        )

    @property
    def suggested_display_precision(self):
        return self.sf_precision(self._platform.inverter.decoded_model, "mmppt_DCA_SF")


class DCVoltage(SolarEdgeSensorBase):
    """DC Voltage for a SolarEdge inverter."""

    entity_description = SolarEdgeSensorEntityDescription(
        key="dc_voltage",
        name="DC Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
    )

    @property
    def native_value(self):
        return self.scaled_or_none(
            "I_DC_Voltage", "I_DC_Voltage_SF", SunSpecNotImpl.UINT16
        )

    @property
    def suggested_display_precision(self):
        return self.sf_precision(self._platform.decoded_model, "I_DC_Voltage_SF")


class SolarEdgeDCVoltageMMPPT(SolarEdgeMMPPTSensorBase):
    """DC Voltage for Synergy MMPPT units."""

    entity_description = SolarEdgeSensorEntityDescription(
        key="dc_voltage_mmppt",
        name="DC Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
    )

    @property
    def available(self) -> bool:
        if (
            self._platform.inverter.decoded_model[self._platform.mmppt_key]["DCV"]
            == SunSpecNotImpl.INT16
            or self._platform.inverter.decoded_model["mmppt_DCV_SF"]
            == SunSpecNotImpl.INT16
            or self._platform.inverter.decoded_model["mmppt_DCV_SF"]
            not in SUNSPEC_SF_RANGE
        ):
            return False

        return super().available

    @property
    def native_value(self):
        return self.scale_factor(
            self._platform.inverter.decoded_model[self._platform.mmppt_key]["DCV"],
            self._platform.inverter.decoded_model["mmppt_DCV_SF"],
        )

    @property
    def suggested_display_precision(self):
        return self.sf_precision(self._platform.inverter.decoded_model, "mmppt_DCV_SF")


class DCPower(SolarEdgeSensorBase):
    """DC Power for a SolarEdge inverter."""

    entity_description = SolarEdgeSensorEntityDescription(
        key="dc_power",
        name="DC Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:solar-power",
    )

    @property
    def native_value(self):
        return self.scaled_or_none("I_DC_Power", "I_DC_Power_SF", SunSpecNotImpl.INT16)

    @property
    def suggested_display_precision(self):
        return self.sf_precision(self._platform.decoded_model, "I_DC_Power_SF")


class SolarEdgeDCPowerMMPPT(SolarEdgeMMPPTSensorBase):
    """DC Power for Synergy MMPPT units."""

    entity_description = SolarEdgeSensorEntityDescription(
        key="dc_power_mmppt",
        name="DC Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:solar-power",
    )

    @property
    def available(self) -> bool:
        if (
            self._platform.inverter.decoded_model[self._platform.mmppt_key]["DCW"]
            == SunSpecNotImpl.INT16
            or self._platform.inverter.decoded_model["mmppt_DCW_SF"]
            == SunSpecNotImpl.INT16
            or self._platform.inverter.decoded_model["mmppt_DCW_SF"]
            not in SUNSPEC_SF_RANGE
        ):
            return False

        return super().available

    @property
    def native_value(self):
        return self.scale_factor(
            self._platform.inverter.decoded_model[self._platform.mmppt_key]["DCW"],
            self._platform.inverter.decoded_model["mmppt_DCW_SF"],
        )

    @property
    def suggested_display_precision(self):
        return self.sf_precision(self._platform.inverter.decoded_model, "mmppt_DCW_SF")


class HeatSinkTemperature(SolarEdgeSensorBase):
    """Heat sink temperature for a SolarEdge inverter."""

    entity_description = SolarEdgeSensorEntityDescription(
        key="temp_sink",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
    )

    @property
    def native_value(self):
        return self.scaled_or_none("I_Temp_Sink", "I_Temp_SF", SunSpecNotImpl.INT16)

    @property
    def suggested_display_precision(self):
        return self.sf_precision(self._platform.decoded_model, "I_Temp_SF")


class SolarEdgeTemperatureMMPPT(SolarEdgeMMPPTSensorBase):
    """Temperature for Synergy MMPPT units."""

    entity_description = SolarEdgeSensorEntityDescription(
        key="tmp_mmppt",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
    )

    @property
    def available(self) -> bool:
        if (
            self._platform.inverter.decoded_model[self._platform.mmppt_key]["Tmp"]
            == SunSpecNotImpl.INT16
        ):
            return False

        return super().available

    @property
    def native_value(self):
        return self._platform.inverter.decoded_model[self._platform.mmppt_key]["Tmp"]


class SolarEdgeInverterStatus(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="status",
        name="Status",
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
        options=list(DEVICE_STATUS.values()),
    )

    @property
    def native_value(self):
        try:
            if self._platform.decoded_model["I_Status"] == SunSpecNotImpl.UINT16:
                return None

            return str(DEVICE_STATUS[self._platform.decoded_model["I_Status"]])

        except TypeError:
            return None

        except KeyError:
            return None

    @property
    def extra_state_attributes(self):
        attrs = {}

        try:
            if self._platform.decoded_model["I_Status"] in DEVICE_STATUS_TEXT:
                attrs["status_text"] = DEVICE_STATUS_TEXT[
                    self._platform.decoded_model["I_Status"]
                ]

                attrs["status_value"] = self._platform.decoded_model["I_Status"]

        except KeyError:
            pass

        return attrs


class SolarEdgeBatteryStatus(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="status",
        name="Status",
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
        options=list(BATTERY_STATUS.values()),
    )

    @property
    def native_value(self):
        try:
            if self._platform.decoded_model["B_Status"] == SunSpecNotImpl.UINT32:
                return None

            return str(BATTERY_STATUS[self._platform.decoded_model["B_Status"]])

        except TypeError:
            return None

        except KeyError:
            return None

    @property
    def extra_state_attributes(self):
        attrs = {}

        try:
            if self._platform.decoded_model["B_Status"] in BATTERY_STATUS_TEXT:
                attrs["status_text"] = BATTERY_STATUS_TEXT[
                    self._platform.decoded_model["B_Status"]
                ]

            attrs["status_value"] = self._platform.decoded_model["B_Status"]

        except KeyError:
            pass

        return attrs


class StatusVendor(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="status_vendor",
        name="Status Vendor",
        entity_category=EntityCategory.DIAGNOSTIC,
    )

    @property
    def entity_registry_enabled_default(self) -> bool:
        return not self._platform.use_status_vendor4

    @property
    def native_value(self):
        try:
            if self._platform.decoded_model["I_Status_Vendor"] == SunSpecNotImpl.UINT16:
                return None

            else:
                return str(self._platform.decoded_model["I_Status_Vendor"])

        except TypeError:
            return None

    @property
    def extra_state_attributes(self):
        try:
            if self._platform.decoded_model["I_Status_Vendor"] in VENDOR_STATUS:
                return {
                    "description": VENDOR_STATUS[
                        self._platform.decoded_model["I_Status_Vendor"]
                    ]
                }

            else:
                return None

        except KeyError:
            return None


class StatusVendor4(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="status_vendor4",
        name="Status Vendor 4",
        entity_category=EntityCategory.DIAGNOSTIC,
    )

    @property
    def available(self) -> bool:
        return (
            super().available
            and "I_Status_Vendor4" in self._platform.decoded_model
            and self._platform.decoded_model["I_Status_Vendor4"]
            != SunSpecNotImpl.UINT32
        )

    @property
    def native_value(self):
        try:
            value = self._platform.decoded_model["I_Status_Vendor4"]
            controller = (value >> 24) & 0xFF
            error = value & 0xFFFF
            return f"{controller:X}x{error:X}"
        except TypeError:
            return None

    @property
    def extra_state_attributes(self):
        try:
            value = self._platform.decoded_model["I_Status_Vendor4"]

            controller = (value >> 24) & 0xFF
            error = value & 0xFFFF
            attrs = {
                "controller": hex(controller),
                "error_code": hex(error),
            }

            if controller in VENDOR4_STATUS and error in VENDOR4_STATUS[controller]:
                attrs["description"] = VENDOR4_STATUS[controller][error]

            return attrs

        except KeyError:
            return None

        except TypeError:
            return None


class SolarEdgeGlobalPowerControlBlock(SolarEdgeSensorBase):
    @property
    def available(self) -> bool:
        return super().available and self._platform.global_power_control


class SolarEdgeRRCR(SolarEdgeGlobalPowerControlBlock):
    entity_description = SolarEdgeSensorEntityDescription(
        key="rrcr",
        name="RRCR Status",
    )

    @property
    def entity_registry_enabled_default(self) -> bool:
        if self._platform.global_power_control is True:
            return True
        else:
            return False

    @property
    def native_value(self):
        try:
            if (
                self._platform.decoded_model["I_RRCR"] == SunSpecNotImpl.UINT16
                or self._platform.decoded_model["I_RRCR"] > 0xF
            ):
                return None

            else:
                return self._platform.decoded_model["I_RRCR"]

        except TypeError:
            return None

        except KeyError:
            return None

    @property
    def extra_state_attributes(self):
        try:
            rrcr_inputs = []

            if int(str(self._platform.decoded_model["I_RRCR"])) == 0x0:
                return {"inputs": str(rrcr_inputs)}

            else:
                for i in range(0, 4):
                    if int(str(self._platform.decoded_model["I_RRCR"])) & (1 << i):
                        rrcr_inputs.append(RRCR_STATUS[i])

                return {"inputs": str(rrcr_inputs)}

        except KeyError:
            return None


class SolarEdgeActivePowerLimit(SolarEdgeGlobalPowerControlBlock):
    """Global Dynamic Power Control: Inverter Active Power Limit"""

    entity_description = SolarEdgeSensorEntityDescription(
        key="active_power_limit",
        name="Active Power Limit",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        icon="mdi:percent",
    )

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self._platform.global_power_control

    @property
    def native_value(self) -> int:
        try:
            if (
                self._platform.decoded_model["I_Power_Limit"] == SunSpecNotImpl.UINT16
                or self._platform.decoded_model["I_Power_Limit"] > 100
                or self._platform.decoded_model["I_Power_Limit"] < 0
            ):
                return None

            else:
                return self._platform.decoded_model["I_Power_Limit"]

        except KeyError:
            return None


class SolarEdgeCosPhi(SolarEdgeGlobalPowerControlBlock):
    """Global Dynamic Power Control: Inverter CosPhi"""

    entity_description = SolarEdgeSensorEntityDescription(
        key="cosphi",
        name="CosPhi",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:angle-acute",
    )

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self._platform.global_power_control

    @property
    def native_value(self) -> float:
        try:
            if (
                is_float32_not_impl(self._platform.decoded_model["I_CosPhi"])
                or self._platform.decoded_model["I_CosPhi"] > 1.0
                or self._platform.decoded_model["I_CosPhi"] < -1.0
            ):
                return None

            else:
                return round(self._platform.decoded_model["I_CosPhi"], 1)

        except KeyError:
            return None


class MeterEvents(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="meter_events",
        name="Meter Events",
        entity_category=EntityCategory.DIAGNOSTIC,
    )

    @property
    def native_value(self):
        try:
            if self._platform.decoded_model["M_Events"] == SunSpecNotImpl.UINT32:
                return None

            else:
                return self._platform.decoded_model["M_Events"]

        except TypeError:
            return None

    @property
    def extra_state_attributes(self):
        attrs = {}
        m_events_active = []

        if int(str(self._platform.decoded_model["M_Events"])) == 0x0:
            attrs["events"] = str(m_events_active)
        else:
            for i in range(2, 31):
                try:
                    if int(str(self._platform.decoded_model["M_Events"])) & (1 << i):
                        m_events_active.append(METER_EVENTS[i])

                except KeyError:
                    pass

        attrs["bits"] = f"{int(self._platform.decoded_model['M_Events']):032b}"
        attrs["events"] = str(m_events_active)

        return attrs


class SolarEdgeMMPPTEvents(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="mmppt_events",
        name="MMPPT Events",
        entity_category=EntityCategory.DIAGNOSTIC,
    )

    @property
    def available(self) -> bool:
        try:
            if self._platform.decoded_model["mmppt_Events"] == SunSpecNotImpl.UINT32:
                return False

            return super().available

        except KeyError:
            return False

    @property
    def native_value(self) -> int:
        return self._platform.decoded_model["mmppt_Events"]

    @property
    def extra_state_attributes(self) -> str:
        attrs = {}
        mmppt_events_active = []

        if int(str(self._platform.decoded_model["mmppt_Events"])) == 0x0:
            attrs["events"] = str(mmppt_events_active)
        else:
            for i in range(0, 31):
                try:
                    if int(str(self._platform.decoded_model["mmppt_Events"])) & (
                        1 << i
                    ):
                        mmppt_events_active.append(MMPPT_EVENTS[i])
                except KeyError:
                    pass

        attrs["events"] = str(mmppt_events_active)
        attrs["bits"] = f"{int(self._platform.decoded_model['mmppt_Events']):032b}"

        return attrs


class MeterVAhIE(SolarEdgeSensorBase):
    # No HA device class accepts VAh/varh units
    entity_description = SolarEdgeSensorEntityDescription(
        key="vah",
        name="Apparent Energy",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=ENERGY_VOLT_AMPERE_HOUR,
        entity_registry_enabled_default=False,
    )

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        if phase is None:
            raise NotImplementedError

        super().__init__(platform, config_entry, coordinator, phase)

        self.last = None
        self._attr_icon = _import_export_icon(self._phase)

    def _description_unique_id(
        self, description: SolarEdgeSensorEntityDescription
    ) -> str:
        return f"{self._platform.uid_base}_{self._phase.lower()}_{description.key}"

    def _description_name(self, description: SolarEdgeSensorEntityDescription) -> str:
        return f"{description.name} {re.sub('_', ' ', self._phase)}"

    @property
    def native_value(self):
        if self._phase is None:
            raise NotImplementedError
        else:
            model_key = f"M_VAh_{self._phase}"

        try:
            if (
                self._platform.decoded_model[model_key] == SunSpecAccum.NA32
                or self._platform.decoded_model[model_key] > SunSpecAccum.LIMIT32
                or self._platform.decoded_model["M_VAh_SF"] == SunSpecNotImpl.INT16
                or self._platform.decoded_model["M_VAh_SF"] not in SUNSPEC_SF_RANGE
            ):
                return None

            else:
                value = self.scale_factor(
                    self._platform.decoded_model[model_key],
                    self._platform.decoded_model["M_VAh_SF"],
                )

                try:
                    return update_accum(self, value)
                except Exception:
                    return None

        except TypeError:
            return None

    @property
    def suggested_display_precision(self):
        return self.sf_precision(self._platform.decoded_model, "M_VAh_SF")


class MetervarhIE(SolarEdgeSensorBase):
    # No HA device class accepts VAh/varh units
    entity_description = SolarEdgeSensorEntityDescription(
        key="varh",
        name="Reactive Energy",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=ENERGY_VOLT_AMPERE_REACTIVE_HOUR,
        entity_registry_enabled_default=False,
    )

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        if phase is None:
            raise NotImplementedError

        super().__init__(platform, config_entry, coordinator, phase)

        self.last = None
        self._attr_icon = _import_export_icon(self._phase)

    def _description_unique_id(
        self, description: SolarEdgeSensorEntityDescription
    ) -> str:
        return f"{self._platform.uid_base}_{self._phase.lower()}_{description.key}"

    def _description_name(self, description: SolarEdgeSensorEntityDescription) -> str:
        return f"{description.name} {re.sub('_', ' ', self._phase)}"

    @property
    def native_value(self):
        if self._phase is None:
            raise NotImplementedError
        else:
            model_key = f"M_varh_{self._phase}"

        try:
            if (
                self._platform.decoded_model[model_key] == SunSpecAccum.NA32
                or self._platform.decoded_model[model_key] > SunSpecAccum.LIMIT32
                or self._platform.decoded_model["M_varh_SF"] == SunSpecNotImpl.INT16
                or self._platform.decoded_model["M_varh_SF"] not in SUNSPEC_SF_RANGE
            ):
                return None

            else:
                value = self.scale_factor(
                    self._platform.decoded_model[model_key],
                    self._platform.decoded_model["M_varh_SF"],
                )

                try:
                    return update_accum(self, value)
                except Exception:
                    return None

        except TypeError:
            return None

    @property
    def suggested_display_precision(self):
        return self.sf_precision(self._platform.decoded_model, "M_varh_SF")


class SolarEdgeBatteryAvgTemp(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="avg_temp",
        name="Average Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
    )

    @property
    def native_value(self):
        try:
            if (
                is_float32_not_impl(self._platform.decoded_model["B_Temp_Average"])
                or self._platform.decoded_model["B_Temp_Average"] < BatteryLimit.Tmin
                or self._platform.decoded_model["B_Temp_Average"] > BatteryLimit.Tmax
            ):
                return None

            else:
                return self._platform.decoded_model["B_Temp_Average"]

        except TypeError:
            return None


class SolarEdgeBatteryMaxTemp(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="max_temp",
        name="Max Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
    )

    @property
    def native_value(self):
        try:
            if (
                is_float32_not_impl(self._platform.decoded_model["B_Temp_Max"])
                or self._platform.decoded_model["B_Temp_Max"] < BatteryLimit.Tmin
                or self._platform.decoded_model["B_Temp_Max"] > BatteryLimit.Tmax
            ):
                return None

            else:
                return self._platform.decoded_model["B_Temp_Max"]

        except TypeError:
            return None


class SolarEdgeBatteryVoltage(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="dc_voltage",
        name="DC Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
    )

    @property
    def native_value(self):
        try:
            if (
                is_float32_not_impl(self._platform.decoded_model["B_DC_Voltage"])
                or self._platform.decoded_model["B_DC_Voltage"] < BatteryLimit.Vmin
                or self._platform.decoded_model["B_DC_Voltage"] > BatteryLimit.Vmax
            ):
                return None

            elif self._platform.decoded_model["B_Status"] in [0]:
                return None

            else:
                return self._platform.decoded_model["B_DC_Voltage"]

        except TypeError:
            return None


class SolarEdgeBatteryCurrent(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="dc_current",
        name="DC Current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=2,
        icon="mdi:current-dc",
    )

    @property
    def available(self) -> bool:
        try:
            if (
                is_float32_not_impl(self._platform.decoded_model["B_DC_Current"])
                or self._platform.decoded_model["B_DC_Current"] < BatteryLimit.Amin
                or self._platform.decoded_model["B_DC_Current"] > BatteryLimit.Amax
            ):
                return False

            if self._platform.decoded_model["B_Status"] in [0]:
                return False

            return super().available

        except (TypeError, KeyError):
            return False

    @property
    def native_value(self):
        return self._platform.decoded_model["B_DC_Current"]


class SolarEdgeBatteryPower(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="dc_power",
        name="DC Power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=2,
        icon="mdi:lightning-bolt",
    )

    @property
    def native_value(self):
        try:
            if (
                is_float32_not_impl(self._platform.decoded_model["B_DC_Power"])
                or float_to_hex(self._platform.decoded_model["B_DC_Power"])
                == "0xff7fffff"
                or float_to_hex(self._platform.decoded_model["B_DC_Power"])
                == "0x7f7fffff"
            ):
                return None

            elif self._platform.decoded_model["B_Status"] in [0]:
                return None

            else:
                return self._platform.decoded_model["B_DC_Power"]

        except TypeError:
            return None


class SolarEdgeBatteryPowerInverted(SolarEdgeBatteryPower):
    """Inverted battery power sensor for HA 2025.12 energy dashboard."""

    def _description_unique_id(
        self, description: SolarEdgeSensorEntityDescription
    ) -> str:
        return f"{super()._description_unique_id(description)}_inverted"

    def _description_name(self, description: SolarEdgeSensorEntityDescription) -> str:
        return f"{super()._description_name(description)} Inverted"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return AwesomeVersion(HA_VERSION) < AwesomeVersion(INVERTED_POWER_VERSION)

    @property
    def native_value(self):
        value = super().native_value
        return None if value is None else -value


class SolarEdgeBatteryEnergyExport(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="energy_export",
        name="Energy Export",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        icon="mdi:battery-charging-20",
    )

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)

        self._last = None
        self._count = 0
        self._log_once = None

    @property
    def native_value(self):
        try:
            if self._platform.decoded_model[
                "B_Export_Energy_WH"
            ] == SunSpecNotImpl.UINT64 or (
                self._platform.decoded_model["B_Export_Energy_WH"] == 0x0
                and not self._platform.allow_battery_energy_reset
            ):
                return None

            else:
                try:
                    if self._last is None:
                        self._last = 0

                    if self._platform.decoded_model["B_Export_Energy_WH"] >= self._last:
                        self._last = self._platform.decoded_model["B_Export_Energy_WH"]
                        self._log_once = False

                        if self._platform.allow_battery_energy_reset:
                            self._count = 0

                        return self._platform.decoded_model["B_Export_Energy_WH"]

                    else:
                        if (
                            not self._platform.allow_battery_energy_reset
                            and not self._log_once
                        ):
                            _LOGGER.warning(
                                (
                                    "Battery Export Energy went backwards: Current value "
                                    f"{self._platform.decoded_model['B_Export_Energy_WH']} "
                                    f"is less than last value of {self._last}"
                                )
                            )
                            self._log_once = True

                        if self._platform.allow_battery_energy_reset:
                            self._count += 1
                            _LOGGER.debug(
                                (
                                    "B_Export_Energy went backwards: "
                                    f"{self._platform.decoded_model['B_Export_Energy_WH']} "
                                    f"< {self._last} cycle {self._count} of "
                                    f"{self._platform.battery_energy_reset_cycles}"
                                )
                            )

                            if self._count > self._platform.battery_energy_reset_cycles:
                                _LOGGER.debug(
                                    f"B_Export_Energy reset at cycle {self._count}"
                                )
                                self._last = None
                                self._count = 0

                        return None

                except OverflowError:
                    return None

        except TypeError:
            return None


class SolarEdgeBatteryEnergyImport(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="energy_import",
        name="Energy Import",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        icon="mdi:battery-charging-100",
    )

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)

        self._last = None
        self._count = 0
        self._log_once = None

    @property
    def native_value(self):
        try:
            if self._platform.decoded_model[
                "B_Import_Energy_WH"
            ] == SunSpecNotImpl.UINT64 or (
                self._platform.decoded_model["B_Import_Energy_WH"] == 0x0
                and not self._platform.allow_battery_energy_reset
            ):
                return None

            else:
                try:
                    if self._last is None:
                        self._last = 0

                    if self._platform.decoded_model["B_Import_Energy_WH"] >= self._last:
                        self._last = self._platform.decoded_model["B_Import_Energy_WH"]
                        self._log_once = False

                        if self._platform.allow_battery_energy_reset:
                            self._count = 0

                        return self._platform.decoded_model["B_Import_Energy_WH"]

                    else:
                        if (
                            not self._platform.allow_battery_energy_reset
                            and not self._log_once
                        ):
                            _LOGGER.warning(
                                (
                                    "Battery Import Energy went backwards: Current value "
                                    f"{self._platform.decoded_model['B_Import_Energy_WH']} "
                                    f"is less than last value of {self._last}"
                                )
                            )
                            self._log_once = True

                        if self._platform.allow_battery_energy_reset:
                            self._count += 1
                            _LOGGER.debug(
                                (
                                    "B_Import_Energy went backwards: "
                                    f"{self._platform.decoded_model['B_Import_Energy_WH']} "
                                    f"< {self._last} cycle {self._count} of "
                                    f"{self._platform.battery_energy_reset_cycles}"
                                )
                            )

                            if self._count > self._platform.battery_energy_reset_cycles:
                                _LOGGER.debug(
                                    f"B_Import_Energy reset at cycle {self._count}"
                                )
                                self._last = None
                                self._count = 0

                        return None

                except OverflowError:
                    return None

        except TypeError:
            return None


class SolarEdgeBatteryMaxEnergy(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="max_energy",
        name="Maximum Energy",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
    )

    @property
    def native_value(self):
        if (
            is_float32_not_impl(self._platform.decoded_model["B_Energy_Max"])
            or self._platform.decoded_model["B_Energy_Max"] < 0
            or self._platform.decoded_model["B_Energy_Max"]
            > self._platform.decoded_common["B_RatedEnergy"]
        ):
            return None

        else:
            return self._platform.decoded_model["B_Energy_Max"]


def _battery_power_limit_description(
    key: str, name: str, model_key: str
) -> SolarEdgeSensorEntityDescription:
    """The battery charge/discharge power limits share all static metadata."""
    return SolarEdgeSensorEntityDescription(
        key=key,
        name=name,
        model_key=model_key,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
    )


class SolarEdgeBatteryPowerBase(SolarEdgeSensorBase):
    """A battery power limit: a float32 register valid when >= 0."""

    @property
    def available(self):
        if (
            is_float32_not_impl(
                self._platform.decoded_model[self.entity_description.model_key]
            )
            or self._platform.decoded_model[self.entity_description.model_key] < 0
        ):
            return False

        return super().available

    @property
    def native_value(self):
        return self._platform.decoded_model[self.entity_description.model_key]


class SolarEdgeBatteryMaxChargePower(SolarEdgeBatteryPowerBase):
    entity_description = _battery_power_limit_description(
        "max_charge_power", "Max Charge Power", "B_MaxChargePower"
    )


class SolarEdgeBatteryMaxChargePeakPower(SolarEdgeBatteryPowerBase):
    entity_description = _battery_power_limit_description(
        "max_charge_peak_power", "Peak Charge Power", "B_MaxChargePeakPower"
    )


class SolarEdgeBatteryMaxDischargePower(SolarEdgeBatteryPowerBase):
    entity_description = _battery_power_limit_description(
        "max_discharge_power", "Max Discharge Power", "B_MaxDischargePower"
    )


class SolarEdgeBatteryMaxDischargePeakPower(SolarEdgeBatteryPowerBase):
    entity_description = _battery_power_limit_description(
        "max_discharge_peak_power", "Peak Discharge Power", "B_MaxDischargePeakPower"
    )


class SolarEdgeBatteryAvailableEnergy(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="avail_energy",
        name="Available Energy",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
    )

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        self._log_warning = True

    @property
    def native_value(self):
        if (
            is_float32_not_impl(self._platform.decoded_model["B_Energy_Available"])
            or self._platform.decoded_model["B_Energy_Available"] < 0
        ):
            return None

        if self._platform.decoded_model["B_Energy_Available"] > (
            self._platform.decoded_common["B_RatedEnergy"]
            * self._platform.battery_rating_adjust
        ):
            if self._log_warning:
                _LOGGER.warning(
                    f"I{self._platform.inverter_unit_id}B{self._platform.battery_id}: "
                    "Battery available energy exceeds rated energy. "
                    "Set configuration for Battery Rating Adjustment when necessary."
                )
                self._log_warning = False

            return None

        else:
            return self._platform.decoded_model["B_Energy_Available"]


class SolarEdgeBatterySOH(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="battery_soh",
        name="State of Health",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        icon="mdi:battery-heart-outline",
    )

    @property
    def native_value(self):
        if (
            is_float32_not_impl(self._platform.decoded_model["B_SOH"])
            or self._platform.decoded_model["B_SOH"] < 0
            or self._platform.decoded_model["B_SOH"] > 100
        ):
            return None
        else:
            return self._platform.decoded_model["B_SOH"]


class SolarEdgeBatterySOE(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="battery_soe",
        name="State of Energy",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
    )

    @property
    def native_value(self):
        if (
            is_float32_not_impl(self._platform.decoded_model["B_SOE"])
            or self._platform.decoded_model["B_SOE"] < 0
            or self._platform.decoded_model["B_SOE"] > 100
        ):
            return None
        else:
            return self._platform.decoded_model["B_SOE"]


class SolarEdgeAdvancedPowerControlBlock(SolarEdgeSensorBase):
    @property
    def available(self) -> bool:
        return super().available and self._platform.advanced_power_control


class SolarEdgeCommitControlSettings(SolarEdgeAdvancedPowerControlBlock):
    """Entity to show the results of Commit Power Control Settings button."""

    entity_description = SolarEdgeSensorEntityDescription(
        key="commit_pwr_settings",
        name="Commit Power Settings",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:content-save-cog-outline",
    )

    @property
    def available(self) -> bool:
        return (
            super().available and "CommitPwrCtlSettings" in self._platform.decoded_model
        )

    @property
    def native_value(self):
        return self._platform.decoded_model["CommitPwrCtlSettings"]

    @property
    def extra_state_attributes(self):
        attrs = {}

        attrs["hex_value"] = hex(self._platform.decoded_model["CommitPwrCtlSettings"])

        if self._platform.decoded_model["CommitPwrCtlSettings"] == 0x0:
            attrs["status"] = "SUCCESS"
        if self._platform.decoded_model["CommitPwrCtlSettings"] in [0x1, 0x2, 0x3, 0x4]:
            attrs["status"] = "INTERNAL_ERROR"
        if self._platform.decoded_model["CommitPwrCtlSettings"] == 0xFFFF:
            attrs["status"] = "UNKNOWN_ERROR"
        if (
            self._platform.decoded_model["CommitPwrCtlSettings"] >= 0xF102
            and self._platform.decoded_model["CommitPwrCtlSettings"] < 0xFFFF
        ):
            attrs["status"] = "VALUE_ERROR"

        return attrs


class SolarEdgeDefaultControlSettings(SolarEdgeAdvancedPowerControlBlock):
    """Entity to show the results of Restore Power Control Default Settings button."""

    entity_description = SolarEdgeSensorEntityDescription(
        key="default_pwr_settings",
        name="Default Power Settings",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:restore-alert",
    )

    @property
    def available(self) -> bool:
        return (
            super().available
            and "RestorePwrCtlDefaults" in self._platform.decoded_model
        )

    @property
    def native_value(self):
        return self._platform.decoded_model["RestorePwrCtlDefaults"]

    @property
    def extra_state_attributes(self):
        attrs = {}

        attrs["hex_value"] = hex(self._platform.decoded_model["RestorePwrCtlDefaults"])

        if self._platform.decoded_model["RestorePwrCtlDefaults"] == 0x0:
            attrs["status"] = "SUCCESS"
        if self._platform.decoded_model["RestorePwrCtlDefaults"] == 0xFFFF:
            attrs["status"] = "ERROR"

        return attrs


class SolarEdgeLastUpdate(SolarEdgeSensorBase):
    entity_description = SolarEdgeSensorEntityDescription(
        key="last_update_timestamp",
        name="Last Update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    )

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> datetime.datetime | None:
        return self._platform.last_update
