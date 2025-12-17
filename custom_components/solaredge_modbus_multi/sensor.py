from __future__ import annotations

import logging
import re

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    BATTERY_STATUS,
    BATTERY_STATUS_TEXT,
    DEVICE_STATUS,
    DEVICE_STATUS_TEXT,
    DOMAIN,
    ENERGY_VOLT_AMPERE_HOUR,
    ENERGY_VOLT_AMPERE_REACTIVE_HOUR,
    METER_EVENTS,
    MMPPT_EVENTS,
    RRCR_STATUS,
    SUNSPEC_DID,
    SUNSPEC_SF_RANGE,
    VENDOR_STATUS,
    BatteryLimit,
    SunSpecAccum,
    SunSpecNotImpl,
)
from .helpers import float_to_hex, update_accum

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub = hass.data[DOMAIN][config_entry.entry_id]["hub"]
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    entities = []

    for inverter in hub.inverters:
        entities.append(SolarEdgeDevice(inverter, config_entry, coordinator))
        entities.append(Version(inverter, config_entry, coordinator))
        entities.append(SolarEdgeInverterStatus(inverter, config_entry, coordinator))
        entities.append(StatusVendor(inverter, config_entry, coordinator))
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

        if hub.option_detect_extras:
            entities.append(SolarEdgeRRCR(inverter, config_entry, coordinator))
            entities.append(
                SolarEdgeActivePowerLimit(inverter, config_entry, coordinator)
            )
            entities.append(SolarEdgeCosPhi(inverter, config_entry, coordinator))

        """ Power Control Block """
        if hub.option_detect_extras:
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
        entities.append(ACPower(meter, config_entry, coordinator, "A"))
        entities.append(ACPower(meter, config_entry, coordinator, "B"))
        entities.append(ACPower(meter, config_entry, coordinator, "C"))
        entities.append(ACPowerInverted(meter, config_entry, coordinator))
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

    if entities:
        async_add_entities(entities)


class SolarEdgeSensorBase(CoordinatorEntity, SensorEntity):
    should_poll = False
    suggested_display_precision = None
    _attr_has_entity_name = True

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(coordinator)

        self._platform = platform
        self._config_entry = config_entry

    def scale_factor(self, x: int, y: int):
        return x * (10**y)

    @property
    def device_info(self):
        return self._platform.device_info

    @property
    def config_entry_id(self):
        return self._config_entry.entry_id

    @property
    def config_entry_name(self):
        return self._config_entry.data["name"]

    @property
    def available(self) -> bool:
        return super().available and self._platform.online

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class SolarEdgeDevice(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_device"

    @property
    def name(self) -> str:
        return "Device"

    @property
    def native_value(self):
        return self._platform.model

    @property
    def extra_state_attributes(self):
        attrs = {}

        try:
            if (
                float_to_hex(self._platform.decoded_common["B_RatedEnergy"])
                != hex(SunSpecNotImpl.FLOAT32)
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
    entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_version"

    @property
    def name(self) -> str:
        return "Version"

    @property
    def native_value(self):
        return self._platform.fw_version


class ACCurrentSensor(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.CURRENT
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator)

        self._phase = phase

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
    def unique_id(self) -> str:
        if self._phase is None:
            return f"{self._platform.uid_base}_ac_current"
        else:
            return f"{self._platform.uid_base}_ac_current_{self._phase.lower()}"

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
    def name(self) -> str:
        if self._phase is None:
            return "AC Current"
        else:
            return f"AC Current {self._phase.upper()}"

    @property
    def native_value(self):
        if self._phase is None:
            model_key = "AC_Current"
        else:
            model_key = f"AC_Current_{self._phase.upper()}"

        try:
            if (
                self._platform.decoded_model[model_key] == self.SUNSPEC_NOT_IMPL
                or self._platform.decoded_model["AC_Current_SF"] == SunSpecNotImpl.INT16
                or self._platform.decoded_model["AC_Current_SF"] not in SUNSPEC_SF_RANGE
            ):
                return None

            else:
                return self.scale_factor(
                    self._platform.decoded_model[model_key],
                    self._platform.decoded_model["AC_Current_SF"],
                )

        except TypeError:
            return None

    @property
    def suggested_display_precision(self):
        return abs(self._platform.decoded_model["AC_Current_SF"])


class VoltageSensor(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.VOLTAGE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfElectricPotential.VOLT

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator)

        self._phase = phase

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
    def unique_id(self) -> str:
        if self._phase is None:
            return f"{self._platform.uid_base}_ac_voltage"
        else:
            return f"{self._platform.uid_base}_ac_voltage_{self._phase.lower()}"

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
    def name(self) -> str:
        if self._phase is None:
            return "AC Voltage"
        else:
            return f"AC Voltage {self._phase.upper()}"

    @property
    def native_value(self):
        if self._phase is None:
            model_key = "AC_Voltage"
        else:
            model_key = f"AC_Voltage_{self._phase.upper()}"

        try:
            if (
                self._platform.decoded_model[model_key] == self.SUNSPEC_NOT_IMPL
                or self._platform.decoded_model["AC_Voltage_SF"] == SunSpecNotImpl.INT16
                or self._platform.decoded_model["AC_Voltage_SF"] not in SUNSPEC_SF_RANGE
            ):
                return None

            else:
                return self.scale_factor(
                    self._platform.decoded_model[model_key],
                    self._platform.decoded_model["AC_Voltage_SF"],
                )

        except TypeError:
            return None

    @property
    def suggested_display_precision(self):
        return abs(self._platform.decoded_model["AC_Voltage_SF"])


class ACPower(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.POWER
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfPower.WATT
    icon = "mdi:solar-power"

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator)

        self._phase = phase

    @property
    def unique_id(self) -> str:
        if self._phase is None:
            return f"{self._platform.uid_base}_ac_power"
        else:
            return f"{self._platform.uid_base}_ac_power_{self._phase.lower()}"

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
    def name(self) -> str:
        if self._phase is None:
            return "AC Power"
        else:
            return f"AC Power {self._phase.upper()}"

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
        return abs(self._platform.decoded_model["AC_Power_SF"])


class ACPowerInverted(ACPower):
    """Inverted AC power sensor for Home Assistant energy dashboard compatibility.

    This class exists solely due to a design decision by the Home Assistant team
    for their energy dashboard, which requires power to be represented opposite
    to how a grid-tie inverter normally reports it. The native_value is negated
    to meet this requirement.

    This does not represent how the inverter or SolarEdge dashboard will represent
    the same sensor. You should normally refer to the non-inverted version.
    """

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)

    @property
    def unique_id(self) -> str:
        return f"{super().unique_id}_inverted"

    @property
    def name(self) -> str:
        return f"{super().name} Inverted"

    @property
    def native_value(self):
        value = super().native_value
        if value is None:
            return None
        return -value


class ACFrequency(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.FREQUENCY
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfFrequency.HERTZ

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_ac_frequency"

    @property
    def name(self) -> str:
        return "AC Frequency"

    @property
    def native_value(self):
        try:
            if (
                self._platform.decoded_model["AC_Frequency"] == SunSpecNotImpl.UINT16
                or self._platform.decoded_model["AC_Frequency_SF"]
                == SunSpecNotImpl.INT16
                or self._platform.decoded_model["AC_Frequency_SF"]
                not in SUNSPEC_SF_RANGE
            ):
                return None

            else:
                return self.scale_factor(
                    self._platform.decoded_model["AC_Frequency"],
                    self._platform.decoded_model["AC_Frequency_SF"],
                )

        except TypeError:
            return None

    @property
    def suggested_display_precision(self):
        return abs(self._platform.decoded_model["AC_Frequency_SF"])


class ACVoltAmp(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.APPARENT_POWER
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfApparentPower.VOLT_AMPERE

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator)

        self._phase = phase

    @property
    def unique_id(self) -> str:
        if self._phase is None:
            return f"{self._platform.uid_base}_ac_va"
        else:
            return f"{self._platform.uid_base}_ac_va_{self._phase.lower()}"

    @property
    def name(self) -> str:
        if self._phase is None:
            return "AC Apparent Power"
        else:
            return f"AC Apparent Power {self._phase.upper()}"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def native_value(self):
        if self._phase is None:
            model_key = "AC_VA"
        else:
            model_key = f"AC_VA_{self._phase.upper()}"

        try:
            if (
                self._platform.decoded_model[model_key] == SunSpecNotImpl.INT16
                or self._platform.decoded_model["AC_VA_SF"] == SunSpecNotImpl.INT16
                or self._platform.decoded_model["AC_VA_SF"] not in SUNSPEC_SF_RANGE
            ):
                return None

            else:
                return self.scale_factor(
                    self._platform.decoded_model[model_key],
                    self._platform.decoded_model["AC_VA_SF"],
                )

        except TypeError:
            return None

    @property
    def suggested_display_precision(self):
        return abs(self._platform.decoded_model["AC_VA_SF"])


class ACVoltAmpReactive(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.REACTIVE_POWER
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfReactivePower.VOLT_AMPERE_REACTIVE

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""
        self._phase = phase

    @property
    def unique_id(self) -> str:
        if self._phase is None:
            return f"{self._platform.uid_base}_ac_var"
        else:
            return f"{self._platform.uid_base}_ac_var_{self._phase.lower()}"

    @property
    def name(self) -> str:
        if self._phase is None:
            return "AC Reactive Power"
        else:
            return f"AC Reactive Power {self._phase.upper()}"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def native_value(self):
        if self._phase is None:
            model_key = "AC_var"
        else:
            model_key = f"AC_var_{self._phase.upper()}"

        try:
            if (
                self._platform.decoded_model[model_key] == SunSpecNotImpl.INT16
                or self._platform.decoded_model["AC_var_SF"] == SunSpecNotImpl.INT16
                or self._platform.decoded_model["AC_var_SF"] not in SUNSPEC_SF_RANGE
            ):
                return None

            else:
                return self.scale_factor(
                    self._platform.decoded_model[model_key],
                    self._platform.decoded_model["AC_var_SF"],
                )

        except TypeError:
            return None

    @property
    def suggested_display_precision(self):
        return abs(self._platform.decoded_model["AC_var_SF"])


class ACPowerFactor(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.POWER_FACTOR
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = PERCENTAGE

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator)

        self._phase = phase

    @property
    def unique_id(self) -> str:
        if self._phase is None:
            return f"{self._platform.uid_base}_ac_pf"
        else:
            return f"{self._platform.uid_base}_ac_pf_{self._phase.lower()}"

    @property
    def name(self) -> str:
        if self._phase is None:
            return "AC Power Factor"
        else:
            return f"AC Power Factor {self._phase.upper()}"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def native_value(self):
        if self._phase is None:
            model_key = "AC_PF"
        else:
            model_key = f"AC_PF_{self._phase.upper()}"

        try:
            if (
                self._platform.decoded_model[model_key] == SunSpecNotImpl.INT16
                or self._platform.decoded_model["AC_PF_SF"] == SunSpecNotImpl.INT16
                or self._platform.decoded_model["AC_PF_SF"] not in SUNSPEC_SF_RANGE
            ):
                return None

            else:
                return self.scale_factor(
                    self._platform.decoded_model[model_key],
                    self._platform.decoded_model["AC_PF_SF"],
                )

        except TypeError:
            return None

    @property
    def suggested_display_precision(self):
        return abs(self._platform.decoded_model["AC_PF_SF"])


class SolarEdgeACEnergy(SolarEdgeSensorBase):
    """SolarEdge sensor for AC Energy watt-hour meters."""

    device_class = SensorDeviceClass.ENERGY
    state_class = SensorStateClass.TOTAL_INCREASING
    native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    suggested_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    suggested_display_precision = 3

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator)

        self._phase = phase
        self._last = None
        self._value = None
        self._log_once = False

        if self._phase is None:
            self._model_key = "AC_Energy_WH"
        else:
            self._model_key = f"AC_Energy_WH_{self._phase}"

    @property
    def icon(self) -> str:
        if self._phase is None:
            return None

        elif re.match("import", self._phase.lower()):
            return "mdi:transmission-tower-export"

        elif re.match("export", self._phase.lower()):
            return "mdi:transmission-tower-import"

        else:
            return None

    @property
    def unique_id(self) -> str:
        # older versions of the integration converted to kWh internally
        # before home assistant had UI configurable units and precision
        # changing the unique_id now would cause new entities to be created
        if self._phase is None:
            return f"{self._platform.uid_base}_ac_energy_kwh"
        else:
            return f"{self._platform.uid_base}_{self._phase.lower()}_kwh"

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
    def name(self) -> str:
        if self._phase is None:
            return "AC Energy"
        else:
            return f"AC Energy {re.sub('_', ' ', self._phase)}"

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

    device_class = SensorDeviceClass.CURRENT
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    icon = "mdi:current-dc"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_dc_current"

    @property
    def name(self) -> str:
        return "DC Current"

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
    def suggested_display_precision(self) -> int:
        if self._platform.decoded_model["I_DC_Current_SF"] not in SUNSPEC_SF_RANGE:
            return 1

        return abs(self._platform.decoded_model["I_DC_Current_SF"])


class SolarEdgeDCCurrentMMPPT(SolarEdgeSensorBase):
    """DC Current for Synergy MMPPT units."""

    device_class = SensorDeviceClass.CURRENT
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    icon = "mdi:current-dc"

    @property
    def unique_id(self) -> str:
        return (
            f"{self._platform.inverter.uid_base}_dc_current_mmppt{self._platform.unit}"
        )

    @property
    def name(self) -> str:
        return "DC Current"

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
    def suggested_display_precision(self) -> int:
        return abs(self._platform.inverter.decoded_model["mmppt_DCA_SF"])


class DCVoltage(SolarEdgeSensorBase):
    """DC Voltage for a SolarEdge inverter."""

    device_class = SensorDeviceClass.VOLTAGE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfElectricPotential.VOLT

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_dc_voltage"

    @property
    def name(self) -> str:
        return "DC Voltage"

    @property
    def native_value(self):
        try:
            if (
                self._platform.decoded_model["I_DC_Voltage"] == SunSpecNotImpl.UINT16
                or self._platform.decoded_model["I_DC_Voltage_SF"]
                == SunSpecNotImpl.INT16
                or self._platform.decoded_model["I_DC_Voltage_SF"]
                not in SUNSPEC_SF_RANGE
            ):
                return None

            else:
                return self.scale_factor(
                    self._platform.decoded_model["I_DC_Voltage"],
                    self._platform.decoded_model["I_DC_Voltage_SF"],
                )

        except TypeError:
            return None

    @property
    def suggested_display_precision(self):
        return abs(self._platform.decoded_model["I_DC_Voltage_SF"])


class SolarEdgeDCVoltageMMPPT(SolarEdgeSensorBase):
    """DC Voltage for Synergy MMPPT units."""

    device_class = SensorDeviceClass.VOLTAGE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfElectricPotential.VOLT

    @property
    def unique_id(self) -> str:
        return (
            f"{self._platform.inverter.uid_base}_dc_voltage_mmppt{self._platform.unit}"
        )

    @property
    def name(self) -> str:
        return "DC Voltage"

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
    def suggested_display_precision(self) -> int:
        return abs(self._platform.inverter.decoded_model["mmppt_DCV_SF"])


class DCPower(SolarEdgeSensorBase):
    """DC Power for a SolarEdge inverter."""

    device_class = SensorDeviceClass.POWER
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfPower.WATT
    icon = "mdi:solar-power"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_dc_power"

    @property
    def name(self) -> str:
        return "DC Power"

    @property
    def native_value(self):
        try:
            if (
                self._platform.decoded_model["I_DC_Power"] == SunSpecNotImpl.INT16
                or self._platform.decoded_model["I_DC_Power_SF"] == SunSpecNotImpl.INT16
                or self._platform.decoded_model["I_DC_Power_SF"] not in SUNSPEC_SF_RANGE
            ):
                return None

            else:
                return self.scale_factor(
                    self._platform.decoded_model["I_DC_Power"],
                    self._platform.decoded_model["I_DC_Power_SF"],
                )

        except TypeError:
            return None

    @property
    def suggested_display_precision(self):
        return abs(self._platform.decoded_model["I_DC_Power_SF"])


class SolarEdgeDCPowerMMPPT(SolarEdgeSensorBase):
    """DC Power for Synergy MMPPT units."""

    device_class = SensorDeviceClass.POWER
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfPower.WATT
    icon = "mdi:solar-power"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.inverter.uid_base}_dc_power_mmppt{self._platform.unit}"

    @property
    def name(self) -> str:
        return "DC Power"

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
    def suggested_display_precision(self) -> int:
        return abs(self._platform.inverter.decoded_model["mmppt_DCW_SF"])


class HeatSinkTemperature(SolarEdgeSensorBase):
    """Heat sink temperature for a SolarEdge inverter."""

    device_class = SensorDeviceClass.TEMPERATURE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_temp_sink"

    @property
    def name(self) -> str:
        return "Temperature"

    @property
    def native_value(self):
        try:
            if (
                self._platform.decoded_model["I_Temp_Sink"] == 0x0
                or self._platform.decoded_model["I_Temp_Sink"] == SunSpecNotImpl.INT16
                or self._platform.decoded_model["I_Temp_SF"] == SunSpecNotImpl.INT16
                or self._platform.decoded_model["I_Temp_SF"] not in SUNSPEC_SF_RANGE
            ):
                return None

            else:
                return self.scale_factor(
                    self._platform.decoded_model["I_Temp_Sink"],
                    self._platform.decoded_model["I_Temp_SF"],
                )

        except TypeError:
            return None

    @property
    def suggested_display_precision(self):
        return abs(self._platform.decoded_model["I_Temp_SF"])


class SolarEdgeTemperatureMMPPT(SolarEdgeSensorBase):
    """Temperature for Synergy MMPPT units."""

    device_class = SensorDeviceClass.TEMPERATURE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfTemperature.CELSIUS
    suggested_display_precision = 0

    @property
    def unique_id(self) -> str:
        return f"{self._platform.inverter.uid_base}_tmp_mmppt{self._platform.unit}"

    @property
    def name(self) -> str:
        return "Temperature"

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


class SolarEdgeStatusSensor(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.ENUM
    entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_status"

    @property
    def name(self) -> str:
        return "Status"


class SolarEdgeInverterStatus(SolarEdgeStatusSensor):
    options = list(DEVICE_STATUS.values())

    @property
    def native_value(self):
        try:
            if self._platform.decoded_model["I_Status"] == SunSpecNotImpl.INT16:
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


class SolarEdgeBatteryStatus(SolarEdgeStatusSensor):
    options = list(BATTERY_STATUS.values())

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
    entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_status_vendor"

    @property
    def name(self) -> str:
        return "Status Vendor"

    @property
    def native_value(self):
        try:
            if self._platform.decoded_model["I_Status_Vendor"] == SunSpecNotImpl.INT16:
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


class SolarEdgeGlobalPowerControlBlock(SolarEdgeSensorBase):
    @property
    def available(self) -> bool:
        return super().available and self._platform.global_power_control


class SolarEdgeRRCR(SolarEdgeGlobalPowerControlBlock):
    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_rrcr"

    @property
    def name(self) -> str:
        return "RRCR Status"

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

    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = PERCENTAGE
    suggested_display_precision = 0
    icon = "mdi:percent"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_active_power_limit"

    @property
    def name(self) -> str:
        return "Active Power Limit"

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

    state_class = SensorStateClass.MEASUREMENT
    suggested_display_precision = 1
    icon = "mdi:angle-acute"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_cosphi"

    @property
    def name(self) -> str:
        return "CosPhi"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self._platform.global_power_control

    @property
    def native_value(self) -> float:
        try:
            if (
                float_to_hex(self._platform.decoded_model["I_CosPhi"])
                == hex(SunSpecNotImpl.FLOAT32)
                or self._platform.decoded_model["I_CosPhi"] > 1.0
                or self._platform.decoded_model["I_CosPhi"] < -1.0
            ):
                return None

            else:
                return round(self._platform.decoded_model["I_CosPhi"], 1)

        except KeyError:
            return None


class MeterEvents(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_meter_events"

    @property
    def name(self) -> str:
        return "Meter Events"

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
    entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_mmppt_events"

    @property
    def name(self) -> str:
        return "MMPPT Events"

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
    device_class = SensorDeviceClass.ENERGY
    state_class = SensorStateClass.TOTAL_INCREASING
    native_unit_of_measurement = ENERGY_VOLT_AMPERE_HOUR

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator)

        self._phase = phase
        self.last = None

    @property
    def icon(self) -> str:
        if self._phase is None:
            return None

        elif re.match("import", self._phase.lower()):
            return "mdi:transmission-tower-export"

        elif re.match("export", self._phase.lower()):
            return "mdi:transmission-tower-import"

        else:
            return None

    @property
    def unique_id(self) -> str:
        if self._phase is None:
            raise NotImplementedError
        else:
            return f"{self._platform.uid_base}_" f"{self._phase.lower()}_vah"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def name(self) -> str:
        if self._phase is None:
            raise NotImplementedError
        else:
            return f"Apparent Energy {re.sub('_', ' ', self._phase)}"

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
                    return update_accum(self, value, value)
                except Exception:
                    return None

        except TypeError:
            return None

    @property
    def suggested_display_precision(self):
        return abs(self._platform.decoded_model["M_VAh_SF"])


class MetervarhIE(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.ENERGY
    state_class = SensorStateClass.TOTAL_INCREASING
    native_unit_of_measurement = ENERGY_VOLT_AMPERE_REACTIVE_HOUR

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator)

        self._phase = phase
        self.last = None

    @property
    def icon(self) -> str:
        if self._phase is None:
            return None

        elif re.match("import", self._phase.lower()):
            return "mdi:transmission-tower-export"

        elif re.match("export", self._phase.lower()):
            return "mdi:transmission-tower-import"

        else:
            return None

    @property
    def unique_id(self) -> str:
        if self._phase is None:
            raise NotImplementedError
        else:
            return f"{self._platform.uid_base}_{self._phase.lower()}_varh"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def name(self) -> str:
        if self._phase is None:
            raise NotImplementedError
        else:
            return f"Reactive Energy {re.sub('_', ' ', self._phase)}"

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
                    return update_accum(self, value, value)
                except Exception:
                    return None

        except TypeError:
            return None

    @property
    def suggested_display_precision(self):
        return abs(self._platform.decoded_model["M_varh_SF"])


class SolarEdgeBatteryAvgTemp(HeatSinkTemperature):
    suggested_display_precision = 1

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_avg_temp"

    @property
    def name(self) -> str:
        return "Average Temperature"

    @property
    def native_value(self):
        try:
            if (
                float_to_hex(self._platform.decoded_model["B_Temp_Average"])
                == hex(SunSpecNotImpl.FLOAT32)
                or self._platform.decoded_model["B_Temp_Average"] < BatteryLimit.Tmin
                or self._platform.decoded_model["B_Temp_Average"] > BatteryLimit.Tmax
            ):
                return None

            else:
                return self._platform.decoded_model["B_Temp_Average"]

        except TypeError:
            return None


class SolarEdgeBatteryMaxTemp(HeatSinkTemperature):
    suggested_display_precision = 1

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_max_temp"

    @property
    def name(self) -> str:
        return "Max Temperature"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def native_value(self):
        try:
            if (
                float_to_hex(self._platform.decoded_model["B_Temp_Max"])
                == hex(SunSpecNotImpl.FLOAT32)
                or self._platform.decoded_model["B_Temp_Max"] < BatteryLimit.Tmin
                or self._platform.decoded_model["B_Temp_Max"] > BatteryLimit.Tmax
            ):
                return None

            else:
                return self._platform.decoded_model["B_Temp_Max"]

        except TypeError:
            return None


class SolarEdgeBatteryVoltage(DCVoltage):
    suggested_display_precision = 2

    @property
    def native_value(self):
        try:
            if (
                float_to_hex(self._platform.decoded_model["B_DC_Voltage"])
                == hex(SunSpecNotImpl.FLOAT32)
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
    device_class = SensorDeviceClass.CURRENT
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    suggested_display_precision = 2
    icon = "mdi:current-dc"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_dc_current"

    @property
    def name(self) -> str:
        return "DC Current"

    @property
    def available(self) -> bool:
        try:
            if (
                float_to_hex(self._platform.decoded_model["B_DC_Current"])
                == hex(SunSpecNotImpl.FLOAT32)
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


class SolarEdgeBatteryPower(DCPower):
    suggested_display_precision = 2
    icon = "mdi:lightning-bolt"

    @property
    def native_value(self):
        try:
            if (
                float_to_hex(self._platform.decoded_model["B_DC_Power"])
                == hex(SunSpecNotImpl.FLOAT32)
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
    """Inverted battery power sensor for Home Assistant energy dashboard compatibility.

    This class exists solely due to a design decision by the Home Assistant team
    for their energy dashboard, which requires power to be represented opposite
    to how a grid-tie inverter normally reports it. The native_value is negated
    to meet this requirement.

    This does not represent how the inverter or SolarEdge dashboard will represent
    the same sensor. You should normally refer to the non-inverted version.
    """

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)

    @property
    def unique_id(self) -> str:
        return f"{super().unique_id}_inverted"

    @property
    def name(self) -> str:
        return f"{super().name} Inverted"

    @property
    def native_value(self):
        value = super().native_value
        if value is None:
            return None
        return -value


class SolarEdgeBatteryEnergyExport(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.ENERGY
    state_class = SensorStateClass.TOTAL_INCREASING
    native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    suggested_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    suggested_display_precision = 3
    icon = "mdi:battery-charging-20"

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)

        self._last = None
        self._count = 0
        self._log_once = None

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_energy_export"

    @property
    def name(self) -> str:
        return "Energy Export"

    @property
    def native_value(self):
        try:
            if self._platform.decoded_model[
                "B_Export_Energy_WH"
            ] == 0xFFFFFFFFFFFFFFFF or (
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
                                    "Battery Export Energy went backwards: Current value "  # noqa: B950
                                    f"{self._platform.decoded_model['B_Export_Energy_WH']} "  # noqa: B950
                                    f"is less than last value of {self._last}"
                                )
                            )
                            self._log_once = True

                        if self._platform.allow_battery_energy_reset:
                            self._count += 1
                            _LOGGER.debug(
                                (
                                    "B_Export_Energy went backwards: "
                                    f"{self._platform.decoded_model['B_Export_Energy_WH']} "  # noqa: B950
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
    device_class = SensorDeviceClass.ENERGY
    state_class = SensorStateClass.TOTAL_INCREASING
    native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    suggested_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    suggested_display_precision = 3
    icon = "mdi:battery-charging-100"

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)

        self._last = None
        self._count = 0
        self._log_once = None

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_energy_import"

    @property
    def name(self) -> str:
        return "Energy Import"

    @property
    def native_value(self):
        try:
            if self._platform.decoded_model[
                "B_Import_Energy_WH"
            ] == 0xFFFFFFFFFFFFFFFF or (
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
                                    "Battery Import Energy went backwards: Current value "  # noqa: B950
                                    f"{self._platform.decoded_model['B_Import_Energy_WH']} "  # noqa: B950
                                    f"is less than last value of {self._last}"
                                )
                            )
                            self._log_once = True

                        if self._platform.allow_battery_energy_reset:
                            self._count += 1
                            _LOGGER.debug(
                                (
                                    "B_Import_Energy went backwards: "
                                    f"{self._platform.decoded_model['B_Import_Energy_WH']} "  # noqa: B950
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
    device_class = SensorDeviceClass.ENERGY_STORAGE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    suggested_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    suggested_display_precision = 3

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_max_energy"

    @property
    def name(self) -> str:
        return "Maximum Energy"

    @property
    def native_value(self):
        if (
            float_to_hex(self._platform.decoded_model["B_Energy_Max"])
            == hex(SunSpecNotImpl.FLOAT32)
            or self._platform.decoded_model["B_Energy_Max"] < 0
            or self._platform.decoded_model["B_Energy_Max"]
            > self._platform.decoded_common["B_RatedEnergy"]
        ):
            return None

        else:
            return self._platform.decoded_model["B_Energy_Max"]


class SolarEdgeBatteryPowerBase(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.POWER
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfPower.WATT
    entity_category = EntityCategory.DIAGNOSTIC
    suggested_display_precision = 0


class SolarEdgeBatteryMaxChargePower(SolarEdgeBatteryPowerBase):
    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_max_charge_power"

    @property
    def name(self) -> str:
        return "Max Charge Power"

    @property
    def available(self):
        if (
            float_to_hex(self._platform.decoded_model["B_MaxChargePower"])
            == hex(SunSpecNotImpl.FLOAT32)
            or self._platform.decoded_model["B_MaxChargePower"] < 0
        ):
            return False

        return super().available

    @property
    def native_value(self):
        return self._platform.decoded_model["B_MaxChargePower"]


class SolarEdgeBatteryMaxChargePeakPower(SolarEdgeBatteryPowerBase):
    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_max_charge_peak_power"

    @property
    def name(self) -> str:
        return "Peak Charge Power"

    @property
    def available(self):
        if (
            float_to_hex(self._platform.decoded_model["B_MaxChargePeakPower"])
            == hex(SunSpecNotImpl.FLOAT32)
            or self._platform.decoded_model["B_MaxChargePeakPower"] < 0
        ):
            return False

        return super().available

    @property
    def native_value(self):
        return self._platform.decoded_model["B_MaxChargePeakPower"]


class SolarEdgeBatteryMaxDischargePower(SolarEdgeBatteryPowerBase):
    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_max_discharge_power"

    @property
    def name(self) -> str:
        return "Max Discharge Power"

    @property
    def available(self):
        if (
            float_to_hex(self._platform.decoded_model["B_MaxDischargePower"])
            == hex(SunSpecNotImpl.FLOAT32)
            or self._platform.decoded_model["B_MaxDischargePower"] < 0
        ):
            return False

        return super().available

    @property
    def native_value(self):
        return self._platform.decoded_model["B_MaxDischargePower"]


class SolarEdgeBatteryMaxDischargePeakPower(SolarEdgeBatteryPowerBase):
    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_max_discharge_peak_power"

    @property
    def name(self) -> str:
        return "Peak Discharge Power"

    @property
    def available(self):
        if (
            float_to_hex(self._platform.decoded_model["B_MaxDischargePeakPower"])
            == hex(SunSpecNotImpl.FLOAT32)
            or self._platform.decoded_model["B_MaxDischargePeakPower"] < 0
        ):
            return False

        return super().available

    @property
    def native_value(self):
        return self._platform.decoded_model["B_MaxDischargePeakPower"]


class SolarEdgeBatteryAvailableEnergy(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.ENERGY_STORAGE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    suggested_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    suggested_display_precision = 3

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        self._log_warning = True

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_avail_energy"

    @property
    def name(self) -> str:
        return "Available Energy"

    @property
    def native_value(self):
        if (
            float_to_hex(self._platform.decoded_model["B_Energy_Available"])
            == hex(SunSpecNotImpl.FLOAT32)
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
    state_class = SensorStateClass.MEASUREMENT
    entity_category = EntityCategory.DIAGNOSTIC
    native_unit_of_measurement = PERCENTAGE
    suggested_display_precision = 0
    icon = "mdi:battery-heart-outline"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_battery_soh"

    @property
    def name(self) -> str:
        return "State of Health"

    @property
    def native_value(self):
        if (
            float_to_hex(self._platform.decoded_model["B_SOH"])
            == hex(SunSpecNotImpl.FLOAT32)
            or self._platform.decoded_model["B_SOH"] < 0
            or self._platform.decoded_model["B_SOH"] > 100
        ):
            return None
        else:
            return self._platform.decoded_model["B_SOH"]


class SolarEdgeBatterySOE(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.BATTERY
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = PERCENTAGE
    suggested_display_precision = 0

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_battery_soe"

    @property
    def name(self) -> str:
        return "State of Energy"

    @property
    def native_value(self):
        if (
            float_to_hex(self._platform.decoded_model["B_SOE"])
            == hex(SunSpecNotImpl.FLOAT32)
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

    entity_category = EntityCategory.DIAGNOSTIC
    icon = "mdi:content-save-cog-outline"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_commit_pwr_settings"

    @property
    def name(self) -> str:
        return "Commit Power Settings"

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

    entity_category = EntityCategory.DIAGNOSTIC
    icon = "mdi:restore-alert"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_default_pwr_settings"

    @property
    def name(self) -> str:
        return "Default Power Settings"

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
