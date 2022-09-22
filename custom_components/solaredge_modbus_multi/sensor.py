import logging
import re

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ELECTRIC_CURRENT_AMPERE,
    ELECTRIC_POTENTIAL_VOLT,
    ENERGY_KILO_WATT_HOUR,
    FREQUENCY_HERTZ,
    PERCENTAGE,
    POWER_VOLT_AMPERE,
    POWER_VOLT_AMPERE_REACTIVE,
    POWER_WATT,
    TEMP_CELSIUS,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    BATTERY_STATUS,
    DEVICE_STATUS,
    DEVICE_STATUS_DESC,
    DOMAIN,
    ENERGY_VOLT_AMPERE_HOUR,
    ENERGY_VOLT_AMPERE_REACTIVE_HOUR,
    METER_EVENTS,
    SUNSPEC_DID,
    SUNSPEC_SF_RANGE,
    VENDOR_STATUS,
    SunSpecAccum,
    SunSpecNotImpl,
)
from .helpers import float_to_hex, scale_factor, update_accum, watts_to_kilowatts

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
        if inverter.single_device_entity:
            entities.append(SolarEdgeDevice(inverter, config_entry, coordinator))
        else:
            entities.append(SolarEdgeDevice(inverter, config_entry, coordinator))
            entities.append(Manufacturer(inverter, config_entry, coordinator))
            entities.append(Model(inverter, config_entry, coordinator))
            entities.append(SerialNumber(inverter, config_entry, coordinator))
            entities.append(DeviceAddress(inverter, config_entry, coordinator))
            entities.append(SunspecDID(inverter, config_entry, coordinator))
        entities.append(Version(inverter, config_entry, coordinator))
        entities.append(Status(inverter, config_entry, coordinator))
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
        entities.append(ACEnergy(inverter, config_entry, coordinator))
        entities.append(DCCurrent(inverter, config_entry, coordinator))
        entities.append(DCVoltage(inverter, config_entry, coordinator))
        entities.append(DCPower(inverter, config_entry, coordinator))
        entities.append(HeatSinkTemperature(inverter, config_entry, coordinator))

    for meter in hub.meters:
        if meter.single_device_entity:
            entities.append(SolarEdgeDevice(meter, config_entry, coordinator))
        else:
            entities.append(SolarEdgeDevice(meter, config_entry, coordinator))
            entities.append(Manufacturer(meter, config_entry, coordinator))
            entities.append(Model(meter, config_entry, coordinator))
            entities.append(Option(meter, config_entry, coordinator))
            entities.append(SerialNumber(meter, config_entry, coordinator))
            entities.append(DeviceAddress(meter, config_entry, coordinator))
            entities.append(DeviceAddressParent(meter, config_entry, coordinator))
            entities.append(SunspecDID(meter, config_entry, coordinator))
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
        entities.append(ACEnergy(meter, config_entry, coordinator, "Exported"))
        entities.append(ACEnergy(meter, config_entry, coordinator, "Exported_A"))
        entities.append(ACEnergy(meter, config_entry, coordinator, "Exported_B"))
        entities.append(ACEnergy(meter, config_entry, coordinator, "Exported_C"))
        entities.append(ACEnergy(meter, config_entry, coordinator, "Imported"))
        entities.append(ACEnergy(meter, config_entry, coordinator, "Imported_A"))
        entities.append(ACEnergy(meter, config_entry, coordinator, "Imported_B"))
        entities.append(ACEnergy(meter, config_entry, coordinator, "Imported_C"))
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
        if battery.single_device_entity:
            entities.append(SolarEdgeDevice(battery, config_entry, coordinator))
        else:
            entities.append(SolarEdgeDevice(battery, config_entry, coordinator))
            entities.append(Manufacturer(battery, config_entry, coordinator))
            entities.append(Model(battery, config_entry, coordinator))
            entities.append(SerialNumber(battery, config_entry, coordinator))
            entities.append(DeviceAddress(battery, config_entry, coordinator))
            entities.append(DeviceAddressParent(battery, config_entry, coordinator))
        entities.append(Version(battery, config_entry, coordinator))
        entities.append(SolarEdgeBatteryAvgTemp(battery, config_entry, coordinator))
        entities.append(SolarEdgeBatteryMaxTemp(battery, config_entry, coordinator))
        entities.append(SolarEdgeBatteryVoltage(battery, config_entry, coordinator))
        entities.append(SolarEdgeBatteryCurrent(battery, config_entry, coordinator))
        entities.append(SolarEdgeBatteryPower(battery, config_entry, coordinator))
        entities.append(
            SolarEdgeBatteryEnergyExport(battery, config_entry, coordinator)
        )
        entities.append(
            SolarEdgeBatteryEnergyImport(battery, config_entry, coordinator)
        )
        entities.append(SolarEdgeBatteryMaxEnergy(battery, config_entry, coordinator))
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

    def __init__(self, platform, config_entry, coordinator):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        """Initialize the sensor."""
        self._platform = platform
        self._config_entry = config_entry

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
        return self._platform.online

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class SolarEdgeDevice(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_device"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Device"

    @property
    def native_value(self):
        return self._platform.model

    @property
    def extra_state_attributes(self):
        attrs = {}

        try:
            if (
                float_to_hex(self._platform.decoded_common["B_MaxChargePeakPower"])
                != 0xFF7FFFFF
            ):
                attrs["batt_charge_peak"] = self._platform.decoded_common[
                    "B_MaxChargePeakPower"
                ]

            if (
                float_to_hex(self._platform.decoded_common["B_MaxDischargePeakPower"])
                != 0xFF7FFFFF
            ):
                attrs["batt_discharge_peak"] = self._platform.decoded_common[
                    "B_MaxDischargePeakPower"
                ]

            if (
                float_to_hex(self._platform.decoded_common["B_MaxChargePower"])
                != 0xFF7FFFFF
            ):
                attrs["batt_max_charge"] = self._platform.decoded_common[
                    "B_MaxChargePower"
                ]

            if (
                float_to_hex(self._platform.decoded_common["B_MaxDischargePower"])
                != 0xFF7FFFFF
            ):
                attrs["batt_max_discharge"] = self._platform.decoded_common[
                    "B_MaxDischargePower"
                ]

            if (
                float_to_hex(self._platform.decoded_common["B_RatedEnergy"])
                != 0xFF7FFFFF
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

            else:
                attrs["sunspec_device"] = "unknown"

        except KeyError:
            attrs["sunspec_device"] = None

        try:
            attrs["sunspec_did"] = self._platform.decoded_model["C_SunSpec_DID"]
        except KeyError:
            attrs["sunspec_did"] = None

        return attrs


class SerialNumber(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_serial_number"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Serial Number"

    @property
    def native_value(self):
        return self._platform.serial


class Manufacturer(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_manufacturer"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Manufacturer"

    @property
    def native_value(self):
        return self._platform.manufacturer


class Model(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_model"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Model"

    @property
    def native_value(self):
        return self._platform.model


class Option(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_option"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Option"

    @property
    def entity_registry_enabled_default(self) -> bool:
        if len(self._platform.option) == 0:
            return False
        else:
            return True

    @property
    def native_value(self):
        if len(self._platform.option) > 0:
            return self._platform.option
        else:
            return None


class Version(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_version"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Version"

    @property
    def native_value(self):
        return self._platform.fw_version


class DeviceAddress(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_device_id"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Device ID"

    @property
    def native_value(self):
        return self._platform.device_address


class DeviceAddressParent(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_parent_device_id"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Parent Device ID"

    @property
    def native_value(self):
        return self._platform.inverter_unit_id


class SunspecDID(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_sunspec_device_id"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Sunspec Device ID"

    @property
    def native_value(self):
        try:
            if self._platform.decoded_model["C_SunSpec_DID"] == SunSpecNotImpl.UINT16:
                return None

            else:
                return self._platform.decoded_model["C_SunSpec_DID"]

        except TypeError:
            return None

    @property
    def extra_state_attributes(self):
        try:
            if self._platform.decoded_model["C_SunSpec_DID"] in SUNSPEC_DID:
                return {
                    "description": SUNSPEC_DID[
                        self._platform.decoded_model["C_SunSpec_DID"]
                    ]
                }

            else:
                return None

        except KeyError:
            return None


class ACCurrentSensor(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.CURRENT
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = ELECTRIC_CURRENT_AMPERE

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""
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
            return f"{self._platform._device_info['name']} AC Current"
        else:
            return (
                f"{self._platform._device_info['name']} "
                f"AC Current {self._phase.upper()}"
            )

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
                return scale_factor(
                    self._platform.decoded_model[model_key],
                    self._platform.decoded_model["AC_Current_SF"],
                )

        except TypeError:
            return None


class VoltageSensor(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.VOLTAGE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""
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
            return f"{self._platform._device_info['name']} AC Voltage"
        else:
            return (
                f"{self._platform._device_info['name']} "
                f"AC Voltage {self._phase.upper()}"
            )

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
                value = scale_factor(
                    self._platform.decoded_model[model_key],
                    self._platform.decoded_model["AC_Voltage_SF"],
                )
                return round(value, abs(self._platform.decoded_model["AC_Voltage_SF"]))

        except TypeError:
            return None


class ACPower(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.POWER
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = POWER_WATT
    icon = "mdi:solar-power"

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""
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
            return f"{self._platform._device_info['name']} AC Power"
        else:
            return (
                f"{self._platform._device_info['name']} AC Power {self._phase.upper()}"
            )

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
                value = scale_factor(
                    self._platform.decoded_model[model_key],
                    self._platform.decoded_model["AC_Power_SF"],
                )
                return round(value, abs(self._platform.decoded_model["AC_Power_SF"]))

        except TypeError:
            return None


class ACFrequency(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.FREQUENCY
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = FREQUENCY_HERTZ

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_ac_frequency"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} AC Frequency"

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
                value = scale_factor(
                    self._platform.decoded_model["AC_Frequency"],
                    self._platform.decoded_model["AC_Frequency_SF"],
                )
                return round(
                    value, abs(self._platform.decoded_model["AC_Frequency_SF"])
                )

        except TypeError:
            return None


class ACVoltAmp(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.APPARENT_POWER
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = POWER_VOLT_AMPERE

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""
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
            return f"{self._platform._device_info['name']} AC VA"
        else:
            return f"{self._platform._device_info['name']} AC VA {self._phase.upper()}"

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
                value = scale_factor(
                    self._platform.decoded_model[model_key],
                    self._platform.decoded_model["AC_VA_SF"],
                )
                return round(value, abs(self._platform.decoded_model["AC_VA_SF"]))

        except TypeError:
            return None


class ACVoltAmpReactive(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.REACTIVE_POWER
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = POWER_VOLT_AMPERE_REACTIVE

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
            return f"{self._platform._device_info['name']} AC var"
        else:
            return f"{self._platform._device_info['name']} AC var {self._phase.upper()}"

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
                value = scale_factor(
                    self._platform.decoded_model[model_key],
                    self._platform.decoded_model["AC_var_SF"],
                )
                return round(value, abs(self._platform.decoded_model["AC_var_SF"]))

        except TypeError:
            return None


class ACPowerFactor(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.POWER_FACTOR
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = PERCENTAGE

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""
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
            return f"{self._platform._device_info['name']} AC PF"
        else:
            return f"{self._platform._device_info['name']} AC PF {self._phase.upper()}"

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
                value = scale_factor(
                    self._platform.decoded_model[model_key],
                    self._platform.decoded_model["AC_PF_SF"],
                )
                return round(value, abs(self._platform.decoded_model["AC_PF_SF"]))

        except TypeError:
            return None


class ACEnergy(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.ENERGY
    state_class = SensorStateClass.TOTAL_INCREASING
    native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""
        self._phase = phase
        self.last = None

        if self._platform.decoded_model["C_SunSpec_DID"] in [101, 102, 103]:
            self.SUNSPEC_NOT_IMPL = SunSpecNotImpl.UINT16
        elif self._platform.decoded_model["C_SunSpec_DID"] in [201, 202, 203, 204]:
            self.SUNSPEC_NOT_IMPL = SunSpecNotImpl.INT16
        else:
            raise RuntimeError(
                "ACEnergy C_SunSpec_DID ",
                f"{self._platform.decoded_model['C_SunSpec_DID']}",
            )

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

        elif self._platform.decoded_model["C_SunSpec_DID"] in [
            203,
            204,
        ] and self._phase in [
            "Exported_B",
            "Exported_C",
            "Imported_B",
            "Imported_C",
        ]:
            return True

        else:
            return False

    @property
    def name(self) -> str:
        if self._phase is None:
            return f"{self._platform._device_info['name']} AC Energy kWh"
        else:
            return (
                f"{self._platform._device_info['name']} "
                f"{re.sub('_', ' ', self._phase)} kWh"
            )

    @property
    def native_value(self):
        if self._phase is None:
            model_key = "AC_Energy_WH"
        else:
            model_key = f"AC_Energy_WH_{self._phase}"

        try:
            if (
                self._platform.decoded_model[model_key] == SunSpecAccum.NA32
                or self._platform.decoded_model[model_key] > SunSpecAccum.LIMIT32
                or self._platform.decoded_model["AC_Energy_WH_SF"]
                == self.SUNSPEC_NOT_IMPL
                or self._platform.decoded_model["AC_Energy_WH_SF"]
                not in SUNSPEC_SF_RANGE
            ):
                return None

            else:
                value = scale_factor(
                    self._platform.decoded_model[model_key],
                    self._platform.decoded_model["AC_Energy_WH_SF"],
                )

                try:
                    return watts_to_kilowatts(update_accum(self, value))
                except Exception:
                    return None

        except TypeError:
            return None


class DCCurrent(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.CURRENT
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = ELECTRIC_CURRENT_AMPERE
    icon = "mdi:current-dc"

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_dc_current"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} DC Current"

    @property
    def native_value(self):
        try:
            if (
                self._platform.decoded_model["I_DC_Current"] == SunSpecNotImpl.UINT16
                or self._platform.decoded_model["I_DC_Current_SF"]
                == SunSpecNotImpl.INT16
                or self._platform.decoded_model["I_DC_Current_SF"]
                not in SUNSPEC_SF_RANGE
            ):
                return None

            else:
                value = scale_factor(
                    self._platform.decoded_model["I_DC_Current"],
                    self._platform.decoded_model["I_DC_Current_SF"],
                )
                return round(
                    value, abs(self._platform.decoded_model["I_DC_Current_SF"])
                )

        except TypeError:
            return None


class DCVoltage(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.VOLTAGE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_dc_voltage"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} DC Voltage"

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
                value = scale_factor(
                    self._platform.decoded_model["I_DC_Voltage"],
                    self._platform.decoded_model["I_DC_Voltage_SF"],
                )
                return round(
                    value, abs(self._platform.decoded_model["I_DC_Voltage_SF"])
                )

        except TypeError:
            return None


class DCPower(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.POWER
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = POWER_WATT
    icon = "mdi:solar-power"

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_dc_power"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} DC Power"

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
                value = scale_factor(
                    self._platform.decoded_model["I_DC_Power"],
                    self._platform.decoded_model["I_DC_Power_SF"],
                )
                return round(value, abs(self._platform.decoded_model["I_DC_Power_SF"]))

        except TypeError:
            return None


class HeatSinkTemperature(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.TEMPERATURE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = TEMP_CELSIUS

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_temp_sink"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Temp Sink"

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
                value = scale_factor(
                    self._platform.decoded_model["I_Temp_Sink"],
                    self._platform.decoded_model["I_Temp_SF"],
                )
                return round(value, abs(self._platform.decoded_model["I_Temp_SF"]))

        except TypeError:
            return None


class Status(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_status"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Status"

    @property
    def native_value(self):
        try:
            if self._platform.decoded_model["I_Status"] == SunSpecNotImpl.INT16:
                return None

            else:
                return str(self._platform.decoded_model["I_Status"])

        except TypeError:
            return None

    @property
    def extra_state_attributes(self):
        attrs = {}

        try:
            if self._platform.decoded_model["I_Status"] in DEVICE_STATUS_DESC:
                attrs["description"] = DEVICE_STATUS_DESC[
                    self._platform.decoded_model["I_Status"]
                ]

            if self._platform.decoded_model["I_Status"] in DEVICE_STATUS:
                attrs["status_text"] = DEVICE_STATUS[
                    self._platform.decoded_model["I_Status"]
                ]

        except KeyError:
            pass

        return attrs


class StatusVendor(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_status_vendor"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Status Vendor"

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


class MeterEvents(SolarEdgeSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_meter_events"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Meter Events"

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
        try:
            m_events_active = []
            if int(str(self._platform.decoded_model["M_Events"]), 16) == 0x0:
                return {"description": str(m_events_active)}
            else:
                for i in range(2, 31):
                    if int(str(self._platform.decoded_model["M_Events"]), 16) & (
                        1 << i
                    ):
                        m_events_active.append(METER_EVENTS[i])
                return {"description": str(m_events_active)}

        except KeyError:
            return None


class MeterVAhIE(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.ENERGY
    state_class = SensorStateClass.TOTAL_INCREASING
    native_unit_of_measurement = ENERGY_VOLT_AMPERE_HOUR

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""
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
            return (
                f"{self._platform._device_info['name']} "
                f"{re.sub('_', ' ', self._phase)} VAh"
            )

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
                value = scale_factor(
                    self._platform.decoded_model[model_key],
                    self._platform.decoded_model["M_VAh_SF"],
                )

                try:
                    return update_accum(self, value, value)
                except Exception:
                    return None

        except TypeError:
            return None


class MetervarhIE(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.ENERGY
    state_class = SensorStateClass.TOTAL_INCREASING
    native_unit_of_measurement = ENERGY_VOLT_AMPERE_REACTIVE_HOUR

    def __init__(self, platform, config_entry, coordinator, phase: str = None):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""
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
            return (
                f"{self._platform._device_info['name']} "
                f"{re.sub('_', ' ', self._phase)} varh"
            )

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
                value = scale_factor(
                    self._platform.decoded_model[model_key],
                    self._platform.decoded_model["M_varh_SF"],
                )

                try:
                    return update_accum(self, value, value)
                except Exception:
                    return None

        except TypeError:
            return None


class SolarEdgeBatteryAvgTemp(HeatSinkTemperature):
    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_avg_temp"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Average Temperature"

    @property
    def native_value(self):
        try:
            if (
                float_to_hex(self._platform.decoded_model["B_Temp_Average"])
                == SunSpecNotImpl.FLOAT32
                or float_to_hex(self._platform.decoded_model["B_Temp_Average"])
                == 0xFF7FFFFF
                or float_to_hex(self._platform.decoded_model["B_Temp_Average"])
                == 0x7F7FFFFF
            ):
                return None

            else:
                return round(self._platform.decoded_model["B_Temp_Average"], 1)

        except TypeError:
            return None


class SolarEdgeBatteryMaxTemp(HeatSinkTemperature):
    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_max_temp"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Max Temperature"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def native_value(self):
        try:
            if (
                float_to_hex(self._platform.decoded_model["B_Temp_Max"])
                == SunSpecNotImpl.FLOAT32
                or float_to_hex(self._platform.decoded_model["B_Temp_Max"])
                == 0xFF7FFFFF
                or float_to_hex(self._platform.decoded_model["B_Temp_Max"])
                == 0x7F7FFFFF
            ):
                return None

            else:
                return round(self._platform.decoded_model["B_Temp_Max"], 1)

        except TypeError:
            return None


class SolarEdgeBatteryVoltage(DCVoltage):
    @property
    def native_value(self):
        try:
            if (
                float_to_hex(self._platform.decoded_model["B_DC_Voltage"])
                == SunSpecNotImpl.FLOAT32
                or float_to_hex(self._platform.decoded_model["B_DC_Voltage"])
                == 0xFF7FFFFF
                or float_to_hex(self._platform.decoded_model["B_DC_Voltage"])
                == 0x7F7FFFFF
            ):
                return None

            elif self._platform.decoded_model["B_Status"] in [0]:
                return None

            else:
                return round(self._platform.decoded_model["B_DC_Voltage"], 2)

        except TypeError:
            return None


class SolarEdgeBatteryCurrent(DCCurrent):
    @property
    def native_value(self):
        try:
            if (
                float_to_hex(self._platform.decoded_model["B_DC_Current"])
                == SunSpecNotImpl.FLOAT32
                or float_to_hex(self._platform.decoded_model["B_DC_Current"])
                == 0xFF7FFFFF
                or float_to_hex(self._platform.decoded_model["B_DC_Current"])
                == 0x7F7FFFFF
            ):
                return None

            elif self._platform.decoded_model["B_Status"] in [0]:
                return None

            else:
                return round(self._platform.decoded_model["B_DC_Current"], 2)

        except TypeError:
            return None


class SolarEdgeBatteryPower(DCPower):
    icon = "mdi:lightning-bolt"

    @property
    def native_value(self):
        try:
            if (
                float_to_hex(self._platform.decoded_model["B_DC_Power"])
                == SunSpecNotImpl.FLOAT32
                or float_to_hex(self._platform.decoded_model["B_DC_Power"])
                == 0xFF7FFFFF
                or float_to_hex(self._platform.decoded_model["B_DC_Power"])
                == 0x7F7FFFFF
            ):
                return None

            elif self._platform.decoded_model["B_Status"] in [0]:
                return None

            else:
                return round(self._platform.decoded_model["B_DC_Power"], 2)

        except TypeError:
            return None


class SolarEdgeBatteryEnergyExport(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.ENERGY
    state_class = SensorStateClass.TOTAL_INCREASING
    native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
    icon = "mdi:battery-charging-20"

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""
        self.last = None

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_energy_export"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Energy Export"

    @property
    def native_value(self):
        try:
            if self._platform.decoded_model["B_Export_Energy_WH"] == 0xFFFFFFFFFFFFFFFF:
                return None

            else:
                try:
                    return watts_to_kilowatts(
                        update_accum(
                            self, self._platform.decoded_model["B_Export_Energy_WH"]
                        )
                    )
                except Exception:
                    return None

        except TypeError:
            return None


class SolarEdgeBatteryEnergyImport(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.ENERGY
    state_class = SensorStateClass.TOTAL_INCREASING
    native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
    icon = "mdi:battery-charging-100"

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""
        self.last = None

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_energy_import"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Energy Import"

    @property
    def native_value(self):
        try:
            if self._platform.decoded_model["B_Import_Energy_WH"] == 0xFFFFFFFFFFFFFFFF:
                return None

            else:
                try:
                    return watts_to_kilowatts(
                        update_accum(
                            self, self._platform.decoded_model["B_Import_Energy_WH"]
                        )
                    )
                except Exception:
                    return None

        except TypeError:
            return None


class SolarEdgeBatteryMaxEnergy(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.ENERGY
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_max_energy"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Maximum Energy"

    @property
    def native_value(self):
        if (
            float_to_hex(self._platform.decoded_model["B_Energy_Max"])
            == SunSpecNotImpl.FLOAT32
            or float_to_hex(self._platform.decoded_model["B_Energy_Max"]) == 0xFF7FFFFF
            or float_to_hex(self._platform.decoded_model["B_Energy_Max"]) == 0x7F7FFFFF
        ):
            return None

        else:
            return watts_to_kilowatts(self._platform.decoded_model["B_Energy_Max"])


class SolarEdgeBatteryAvailableEnergy(SolarEdgeSensorBase):
    device_class = SensorDeviceClass.ENERGY
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = ENERGY_KILO_WATT_HOUR

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_avail_energy"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} Available Energy"

    @property
    def native_value(self):
        if (
            float_to_hex(self._platform.decoded_model["B_Energy_Available"])
            == SunSpecNotImpl.FLOAT32
            or float_to_hex(self._platform.decoded_model["B_Energy_Available"])
            == 0xFF7FFFFF
            or float_to_hex(self._platform.decoded_model["B_Energy_Available"])
            == 0x7F7FFFFF
        ):
            return None

        else:
            return watts_to_kilowatts(
                self._platform.decoded_model["B_Energy_Available"]
            )


class SolarEdgeBatterySOH(SolarEdgeSensorBase):
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = PERCENTAGE
    entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_battery_soh"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} State of Health"

    @property
    def native_value(self):
        if (
            float_to_hex(self._platform.decoded_model["B_SOH"])
            == SunSpecNotImpl.FLOAT32
            or float_to_hex(self._platform.decoded_model["B_SOH"]) == 0xFF7FFFFF
            or float_to_hex(self._platform.decoded_model["B_SOH"]) == 0x7F7FFFFF
            or self._platform.decoded_model["B_SOH"] < 0
            or self._platform.decoded_model["B_SOH"] > 100
        ):
            return None
        else:
            return round(self._platform.decoded_model["B_SOH"], 0)


class SolarEdgeBatterySOE(SolarEdgeSensorBase):
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = PERCENTAGE
    entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_battery_soe"

    @property
    def name(self) -> str:
        return f"{self._platform._device_info['name']} State of Energy"

    @property
    def native_value(self):
        if (
            float_to_hex(self._platform.decoded_model["B_SOE"])
            == SunSpecNotImpl.FLOAT32
            or float_to_hex(self._platform.decoded_model["B_SOE"]) == 0xFF7FFFFF
            or float_to_hex(self._platform.decoded_model["B_SOE"]) == 0x7F7FFFFF
            or self._platform.decoded_model["B_SOE"] < 0
            or self._platform.decoded_model["B_SOE"] > 100
        ):
            return None
        else:
            return round(self._platform.decoded_model["B_SOE"], 0)


class SolarEdgeBatteryStatus(Status):
    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def native_value(self):
        try:
            if self._platform.decoded_model["B_Status"] == SunSpecNotImpl.UINT32:
                return None

            else:
                return str(self._platform.decoded_model["B_Status"])

        except TypeError:
            return None

    @property
    def extra_state_attributes(self):
        attrs = {}

        try:
            attrs["status_text"] = BATTERY_STATUS[
                self._platform.decoded_model["B_Status"]
            ]

        except KeyError:
            pass

        return attrs
