"""The SolarEdge Modbus Multi sensor module."""

from __future__ import annotations

import contextlib
import datetime
import logging
import re

from awesomeversion import AwesomeVersion
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfReactiveEnergy,
    UnitOfReactivePower,
    UnitOfTemperature,
    __version__ as HA_VERSION,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    BATTERY_STATUS,
    BATTERY_STATUS_TEXT,
    DER_BATTERY_STATUS,
    DER_BATTERY_STATUS_TEXT,
    DEVICE_STATUS,
    DEVICE_STATUS_TEXT,
    DOMAIN,
    ENERGY_VOLT_AMPERE_HOUR,
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
from .helpers import float_to_hex

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setup entry."""
    hub = hass.data[DOMAIN][config_entry.entry_id]["hub"]
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    entities = []

    for inverter in hub.inverters:
        entities.append(SolarEdgeLastUpdate(inverter, config_entry, coordinator))
        entities.append(SolarEdgeInverterDevice(inverter, config_entry, coordinator))
        entities.append(Version(inverter, config_entry, coordinator))
        entities.append(SolarEdgeInverterStatus(inverter, config_entry, coordinator))
        entities.append(StatusVendor(inverter, config_entry, coordinator))
        if inverter.use_status_vendor4:
            entities.append(StatusVendor4(inverter, config_entry, coordinator))
        entities.append(ACCurrentSensorInverter(inverter, config_entry, coordinator))
        entities.append(
            ACCurrentSensorInverter(inverter, config_entry, coordinator, "A")
        )
        entities.append(
            ACCurrentSensorInverter(inverter, config_entry, coordinator, "B")
        )
        entities.append(
            ACCurrentSensorInverter(inverter, config_entry, coordinator, "C")
        )
        entities.append(
            VoltageSensorInverter(inverter, config_entry, coordinator, "AB")
        )
        entities.append(
            VoltageSensorInverter(inverter, config_entry, coordinator, "BC")
        )
        entities.append(
            VoltageSensorInverter(inverter, config_entry, coordinator, "CA")
        )
        entities.append(
            VoltageSensorInverter(inverter, config_entry, coordinator, "AN")
        )
        entities.append(
            VoltageSensorInverter(inverter, config_entry, coordinator, "BN")
        )
        entities.append(
            VoltageSensorInverter(inverter, config_entry, coordinator, "CN")
        )
        entities.append(ACPowerInverter(inverter, config_entry, coordinator))
        entities.append(ACFrequencyInverter(inverter, config_entry, coordinator))
        entities.append(ACVoltAmpInverter(inverter, config_entry, coordinator))
        entities.append(ACVoltAmpReactiveInverter(inverter, config_entry, coordinator))
        entities.append(ACPowerFactorInverter(inverter, config_entry, coordinator))
        entities.append(SolarEdgeACEnergyInverter(inverter, config_entry, coordinator))
        entities.append(DCCurrent(inverter, config_entry, coordinator))
        entities.append(DCVoltage(inverter, config_entry, coordinator))
        entities.append(DCPower(inverter, config_entry, coordinator))
        entities.append(HeatSinkTemperature(inverter, config_entry, coordinator))
        entities.append(SolarEdgeWriteCount(inverter, config_entry, coordinator))

        if hub.option_detect_extras:
            entities.append(SolarEdgeRRCR(inverter, config_entry, coordinator))
            entities.append(
                SolarEdgeActivePowerLimit(inverter, config_entry, coordinator)
            )
            entities.append(SolarEdgeCosPhi(inverter, config_entry, coordinator))
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
        entities.append(SolarEdgeMeterDevice(meter, config_entry, coordinator))
        entities.append(Version(meter, config_entry, coordinator))
        entities.append(MeterEvents(meter, config_entry, coordinator))
        entities.append(ACCurrentSensorMeter(meter, config_entry, coordinator))
        entities.append(ACCurrentSensorMeter(meter, config_entry, coordinator, "A"))
        entities.append(ACCurrentSensorMeter(meter, config_entry, coordinator, "B"))
        entities.append(ACCurrentSensorMeter(meter, config_entry, coordinator, "C"))
        entities.append(VoltageSensorMeter(meter, config_entry, coordinator, "LN"))
        entities.append(VoltageSensorMeter(meter, config_entry, coordinator, "AN"))
        entities.append(VoltageSensorMeter(meter, config_entry, coordinator, "BN"))
        entities.append(VoltageSensorMeter(meter, config_entry, coordinator, "CN"))
        entities.append(VoltageSensorMeter(meter, config_entry, coordinator, "LL"))
        entities.append(VoltageSensorMeter(meter, config_entry, coordinator, "AB"))
        entities.append(VoltageSensorMeter(meter, config_entry, coordinator, "BC"))
        entities.append(VoltageSensorMeter(meter, config_entry, coordinator, "CA"))
        entities.append(ACFrequencyMeter(meter, config_entry, coordinator))
        entities.append(ACPowerMeter(meter, config_entry, coordinator))
        entities.append(ACPowerMeter(meter, config_entry, coordinator, "A"))
        entities.append(ACPowerMeter(meter, config_entry, coordinator, "B"))
        entities.append(ACPowerMeter(meter, config_entry, coordinator, "C"))
        entities.append(ACPowerInverted(meter, config_entry, coordinator))
        entities.append(ACVoltAmpMeter(meter, config_entry, coordinator))
        entities.append(ACVoltAmpMeter(meter, config_entry, coordinator, "A"))
        entities.append(ACVoltAmpMeter(meter, config_entry, coordinator, "B"))
        entities.append(ACVoltAmpMeter(meter, config_entry, coordinator, "C"))
        entities.append(ACVoltAmpReactiveMeter(meter, config_entry, coordinator))
        entities.append(ACVoltAmpReactiveMeter(meter, config_entry, coordinator, "A"))
        entities.append(ACVoltAmpReactiveMeter(meter, config_entry, coordinator, "B"))
        entities.append(ACVoltAmpReactiveMeter(meter, config_entry, coordinator, "C"))
        entities.append(ACPowerFactorMeter(meter, config_entry, coordinator))
        entities.append(ACPowerFactorMeter(meter, config_entry, coordinator, "A"))
        entities.append(ACPowerFactorMeter(meter, config_entry, coordinator, "B"))
        entities.append(ACPowerFactorMeter(meter, config_entry, coordinator, "C"))
        entities.append(
            SolarEdgeACEnergyMeter(meter, config_entry, coordinator, "Exported")
        )
        entities.append(
            SolarEdgeACEnergyMeter(meter, config_entry, coordinator, "Exported_A")
        )
        entities.append(
            SolarEdgeACEnergyMeter(meter, config_entry, coordinator, "Exported_B")
        )
        entities.append(
            SolarEdgeACEnergyMeter(meter, config_entry, coordinator, "Exported_C")
        )
        entities.append(
            SolarEdgeACEnergyMeter(meter, config_entry, coordinator, "Imported")
        )
        entities.append(
            SolarEdgeACEnergyMeter(meter, config_entry, coordinator, "Imported_A")
        )
        entities.append(
            SolarEdgeACEnergyMeter(meter, config_entry, coordinator, "Imported_B")
        )
        entities.append(
            SolarEdgeACEnergyMeter(meter, config_entry, coordinator, "Imported_C")
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
        entities.append(SolarEdgeBatteryDevice(battery, config_entry, coordinator))
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

    for inverter in hub.inverters:
        entities.extend(
            SolarEdgeDERBatterySOE(inverter, config_entry, coordinator, der_id)
            for der_id in range(1, len(inverter.der_storage) + 1)
        )
        # SolarEdgeDERBatterySOH and SolarEdgeDERBatteryStatus are not added:
        # SolarEdge is not known to report State of Health or Status in
        # model 713. Add them here if that changes.

    entities.extend(Version(evse, config_entry, coordinator) for evse in hub.evses)

    if entities:
        async_add_entities(entities)


class SolarEdgeSensorBase(CoordinatorEntity, SensorEntity):
    """Representation of a solar edge sensor base."""

    should_poll = False
    suggested_display_precision = None
    _attr_has_entity_name = True

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the solar edge sensor base."""
        super().__init__(coordinator)

        self._platform = platform
        self._config_entry = config_entry

    def scale_factor(self, x: int, y: int):
        """Scale factor."""
        return x * (10**y)

    @property
    def device_info(self):
        """Return the device info."""
        return self._platform.device_info

    @property
    def config_entry_id(self):
        """Return the config entry id."""
        return self._config_entry.entry_id

    @property
    def config_entry_name(self):
        """Return the config entry name."""
        return self._config_entry.data["name"]

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class SolarEdgeDevice(SolarEdgeSensorBase):
    """Representation of a solar edge device."""

    entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_device"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Device"

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.model

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        attrs = {
            "device_id": self._platform.device_address,
            "manufacturer": self._platform.manufacturer,
            "model": self._platform.model,
        }

        if len(self._platform.option) > 0:
            attrs["option"] = self._platform.option

        if self._platform.has_parent:
            attrs["parent_device_id"] = self._platform.inverter_unit_id

        attrs["serial_number"] = self._platform.serial

        return attrs


class SolarEdgeInverterDevice(SolarEdgeDevice):
    """Representation of a solar edge inverter device."""

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        attrs = super().extra_state_attributes

        did = self._platform.inverter_data.C_SunSpec_DID
        if did is not None:
            attrs["sunspec_did"] = did
            if did in SUNSPEC_DID:
                attrs["sunspec_device"] = SUNSPEC_DID[did]

        if self._platform.is_mmppt:
            mmppt_common = self._platform.mmppt_common

            if mmppt_common.mmppt_DID in SUNSPEC_DID:
                attrs["mmppt_device"] = SUNSPEC_DID[mmppt_common.mmppt_DID]

            attrs["mmppt_did"] = mmppt_common.mmppt_DID
            attrs["mmppt_units"] = mmppt_common.mmppt_Units

        return attrs


class SolarEdgeMeterDevice(SolarEdgeDevice):
    """Representation of a solar edge meter device."""

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        attrs = super().extra_state_attributes

        did = self._platform.meter_data.C_SunSpec_DID
        if did is not None:
            attrs["sunspec_did"] = did
            if did in SUNSPEC_DID:
                attrs["sunspec_device"] = SUNSPEC_DID[did]

        return attrs


class SolarEdgeBatteryDevice(SolarEdgeDevice):
    """Representation of a solar edge battery device."""

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        attrs = super().extra_state_attributes

        rated_energy = self._platform.battery_info.B_RatedEnergy
        if (
            rated_energy is not None
            and float_to_hex(rated_energy) != hex(SunSpecNotImpl.FLOAT32)
            and rated_energy > 0
        ):
            attrs["batt_rated_energy"] = rated_energy

        return attrs


class Version(SolarEdgeSensorBase):
    """Representation of a version."""

    entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_version"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Version"

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.fw_version


class ACCurrentSensor(SolarEdgeSensorBase):
    """Base class for ACCurrentSensorInverter/ACCurrentSensorMeter."""

    device_class = SensorDeviceClass.CURRENT
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    def __init__(self, platform, config_entry, coordinator, phase: str | None = None):
        """Initialize the ac current sensor."""
        super().__init__(platform, config_entry, coordinator)

        self._phase = phase

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        if self._phase is None:
            return f"{self._platform.uid_base}_ac_current"
        return f"{self._platform.uid_base}_ac_current_{self._phase.lower()}"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        if self._phase is None or (
            self._data.C_SunSpec_DID in [103, 203, 204]
            and self._phase
            in [
                "A",
                "B",
                "C",
            ]
        ):
            return True

        return False

    @property
    def name(self) -> str:
        """Return the name."""
        if self._phase is None:
            return "AC Current"
        return f"AC Current {self._phase.upper()}"

    @property
    def _model_key(self) -> str:
        if self._phase is None:
            return "AC_Current"
        return f"AC_Current_{self._phase.upper()}"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = getattr(self._data, self._model_key)
        sf = self._data.AC_Current_SF
        return (
            super().available
            and value is not None
            and value != self._sunspec_not_impl
            and sf is not None
            and sf != SunSpecNotImpl.INT16
            and sf in SUNSPEC_SF_RANGE
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self.scale_factor(
            getattr(self._data, self._model_key), self._data.AC_Current_SF
        )

    @property
    def suggested_display_precision(self):
        """Return the suggested display precision."""
        return abs(self._data.AC_Current_SF)


class ACCurrentSensorInverter(ACCurrentSensor):
    """Representation of a ac current sensor inverter."""

    _sunspec_not_impl = SunSpecNotImpl.UINT16

    @property
    def _data(self):
        return self._platform.inverter_data


class ACCurrentSensorMeter(ACCurrentSensor):
    """Representation of a ac current sensor meter."""

    _sunspec_not_impl = SunSpecNotImpl.INT16

    @property
    def _data(self):
        return self._platform.meter_data


class VoltageSensor(SolarEdgeSensorBase):
    """Base class for VoltageSensorInverter/VoltageSensorMeter."""

    device_class = SensorDeviceClass.VOLTAGE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfElectricPotential.VOLT

    def __init__(self, platform, config_entry, coordinator, phase: str | None = None):
        """Initialize the voltage sensor."""
        super().__init__(platform, config_entry, coordinator)

        self._phase = phase

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        if self._phase is None:
            return f"{self._platform.uid_base}_ac_voltage"
        return f"{self._platform.uid_base}_ac_voltage_{self._phase.lower()}"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        if self._phase is None:
            raise NotImplementedError

        if self._phase in ["LN", "LL", "AB"] or (
            self._data.C_SunSpec_DID in [103, 203, 204]
            and self._phase
            in [
                "BC",
                "CA",
                "AN",
                "BN",
                "CN",
            ]
        ):
            return True

        return False

    @property
    def name(self) -> str:
        """Return the name."""
        if self._phase is None:
            return "AC Voltage"
        return f"AC Voltage {self._phase.upper()}"

    @property
    def _model_key(self) -> str:
        if self._phase is None:
            return "AC_Voltage"
        return f"AC_Voltage_{self._phase.upper()}"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = getattr(self._data, self._model_key)
        sf = self._data.AC_Voltage_SF
        return (
            super().available
            and value is not None
            and value != self._sunspec_not_impl
            and sf is not None
            and sf != SunSpecNotImpl.INT16
            and sf in SUNSPEC_SF_RANGE
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self.scale_factor(
            getattr(self._data, self._model_key), self._data.AC_Voltage_SF
        )

    @property
    def suggested_display_precision(self):
        """Return the suggested display precision."""
        return abs(self._data.AC_Voltage_SF)


class VoltageSensorInverter(VoltageSensor):
    """Representation of a voltage sensor inverter."""

    _sunspec_not_impl = SunSpecNotImpl.UINT16

    @property
    def _data(self):
        return self._platform.inverter_data


class VoltageSensorMeter(VoltageSensor):
    """Representation of a voltage sensor meter."""

    _sunspec_not_impl = SunSpecNotImpl.INT16

    @property
    def _data(self):
        return self._platform.meter_data


class ACPower(SolarEdgeSensorBase):
    """Base class for ACPowerInverter/ACPowerMeter."""

    device_class = SensorDeviceClass.POWER
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfPower.WATT
    icon = "mdi:solar-power"

    def __init__(self, platform, config_entry, coordinator, phase: str | None = None):
        """Initialize the ac power."""
        super().__init__(platform, config_entry, coordinator)

        self._phase = phase

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        if self._phase is None:
            return f"{self._platform.uid_base}_ac_power"
        return f"{self._platform.uid_base}_ac_power_{self._phase.lower()}"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        if self._phase is None or (
            self._data.C_SunSpec_DID in [203, 204]
            and self._phase
            in [
                "A",
                "B",
                "C",
            ]
        ):
            return True

        return False

    @property
    def name(self) -> str:
        """Return the name."""
        if self._phase is None:
            return "AC Power"
        return f"AC Power {self._phase.upper()}"

    @property
    def _model_key(self) -> str:
        if self._phase is None:
            return "AC_Power"
        return f"AC_Power_{self._phase.upper()}"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = getattr(self._data, self._model_key)
        sf = self._data.AC_Power_SF
        return (
            super().available
            and value is not None
            and value != SunSpecNotImpl.INT16
            and sf is not None
            and sf != SunSpecNotImpl.INT16
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self.scale_factor(
            getattr(self._data, self._model_key), self._data.AC_Power_SF
        )

    @property
    def suggested_display_precision(self):
        """Return the suggested display precision."""
        return abs(self._data.AC_Power_SF)


class ACPowerInverter(ACPower):
    """Representation of a ac power inverter."""

    @property
    def _data(self):
        return self._platform.inverter_data


class ACPowerMeter(ACPower):
    """Representation of a ac power meter."""

    @property
    def _data(self):
        return self._platform.meter_data


class ACPowerInverted(ACPowerMeter):
    """Inverted AC power sensor for Home Assistant energy dashboard compatibility.

    This class exists solely due to a design decision by the Home Assistant team
    for their energy dashboard, which requires power to be represented opposite
    to how a grid-tie inverter normally reports it. The native_value is negated
    to meet this requirement.

    This does not represent how the inverter or SolarEdge dashboard will represent
    the same sensor. You should normally refer to the non-inverted version.
    """

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the ac power inverted."""
        super().__init__(platform, config_entry, coordinator)

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{super().unique_id}_inverted"

    @property
    def name(self) -> str:
        """Return the name."""
        return f"{super().name} Inverted"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return AwesomeVersion(HA_VERSION) < AwesomeVersion(INVERTED_POWER_VERSION)

    @property
    def native_value(self):
        """Return the native value."""
        value = super().native_value
        if value is None:
            return None
        return -value


class ACFrequency(SolarEdgeSensorBase):
    """Base class for ACFrequencyInverter/ACFrequencyMeter."""

    device_class = SensorDeviceClass.FREQUENCY
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfFrequency.HERTZ

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_ac_frequency"

    @property
    def name(self) -> str:
        """Return the name."""
        return "AC Frequency"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._data.AC_Frequency
        sf = self._data.AC_Frequency_SF
        return (
            super().available
            and value is not None
            and value != self._sunspec_not_impl
            and sf is not None
            and sf != SunSpecNotImpl.INT16
            and sf in SUNSPEC_SF_RANGE
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self.scale_factor(self._data.AC_Frequency, self._data.AC_Frequency_SF)

    @property
    def suggested_display_precision(self):
        """Return the suggested display precision."""
        return abs(self._data.AC_Frequency_SF)


class ACFrequencyInverter(ACFrequency):
    """Representation of a ac frequency inverter."""

    _sunspec_not_impl = SunSpecNotImpl.UINT16

    @property
    def _data(self):
        return self._platform.inverter_data


class ACFrequencyMeter(ACFrequency):
    """Representation of a ac frequency meter."""

    _sunspec_not_impl = SunSpecNotImpl.INT16

    @property
    def _data(self):
        return self._platform.meter_data


class ACVoltAmp(SolarEdgeSensorBase):
    """Base class for ACVoltAmpInverter/ACVoltAmpMeter."""

    device_class = SensorDeviceClass.APPARENT_POWER
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfApparentPower.VOLT_AMPERE

    def __init__(self, platform, config_entry, coordinator, phase: str | None = None):
        """Initialize the ac volt amp."""
        super().__init__(platform, config_entry, coordinator)

        self._phase = phase

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        if self._phase is None:
            return f"{self._platform.uid_base}_ac_va"
        return f"{self._platform.uid_base}_ac_va_{self._phase.lower()}"

    @property
    def name(self) -> str:
        """Return the name."""
        if self._phase is None:
            return "AC Apparent Power"
        return f"AC Apparent Power {self._phase.upper()}"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return False

    @property
    def _model_key(self) -> str:
        if self._phase is None:
            return "AC_VA"
        return f"AC_VA_{self._phase.upper()}"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = getattr(self._data, self._model_key)
        sf = self._data.AC_VA_SF
        return (
            super().available
            and value is not None
            and value != SunSpecNotImpl.INT16
            and sf is not None
            and sf != SunSpecNotImpl.INT16
            and sf in SUNSPEC_SF_RANGE
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self.scale_factor(
            getattr(self._data, self._model_key), self._data.AC_VA_SF
        )

    @property
    def suggested_display_precision(self):
        """Return the suggested display precision."""
        return abs(self._data.AC_VA_SF)


class ACVoltAmpInverter(ACVoltAmp):
    """Representation of a ac volt amp inverter."""

    @property
    def _data(self):
        return self._platform.inverter_data


class ACVoltAmpMeter(ACVoltAmp):
    """Representation of a ac volt amp meter."""

    @property
    def _data(self):
        return self._platform.meter_data


class ACVoltAmpReactive(SolarEdgeSensorBase):
    """Base class for ACVoltAmpReactiveInverter/ACVoltAmpReactiveMeter."""

    device_class = SensorDeviceClass.REACTIVE_POWER
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfReactivePower.VOLT_AMPERE_REACTIVE

    def __init__(self, platform, config_entry, coordinator, phase: str | None = None):
        """Initialize the ac volt amp reactive."""
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""
        self._phase = phase

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        if self._phase is None:
            return f"{self._platform.uid_base}_ac_var"
        return f"{self._platform.uid_base}_ac_var_{self._phase.lower()}"

    @property
    def name(self) -> str:
        """Return the name."""
        if self._phase is None:
            return "AC Reactive Power"
        return f"AC Reactive Power {self._phase.upper()}"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return False

    @property
    def _model_key(self) -> str:
        if self._phase is None:
            return "AC_var"
        return f"AC_var_{self._phase.upper()}"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = getattr(self._data, self._model_key)
        sf = self._data.AC_var_SF
        return (
            super().available
            and value is not None
            and value != SunSpecNotImpl.INT16
            and sf is not None
            and sf != SunSpecNotImpl.INT16
            and sf in SUNSPEC_SF_RANGE
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self.scale_factor(
            getattr(self._data, self._model_key), self._data.AC_var_SF
        )

    @property
    def suggested_display_precision(self):
        """Return the suggested display precision."""
        return abs(self._data.AC_var_SF)


class ACVoltAmpReactiveInverter(ACVoltAmpReactive):
    """Representation of a ac volt amp reactive inverter."""

    @property
    def _data(self):
        return self._platform.inverter_data


class ACVoltAmpReactiveMeter(ACVoltAmpReactive):
    """Representation of a ac volt amp reactive meter."""

    @property
    def _data(self):
        return self._platform.meter_data


class ACPowerFactor(SolarEdgeSensorBase):
    """Base class for ACPowerFactorInverter/ACPowerFactorMeter."""

    device_class = SensorDeviceClass.POWER_FACTOR
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = PERCENTAGE

    def __init__(self, platform, config_entry, coordinator, phase: str | None = None):
        """Initialize the ac power factor."""
        super().__init__(platform, config_entry, coordinator)

        self._phase = phase

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        if self._phase is None:
            return f"{self._platform.uid_base}_ac_pf"
        return f"{self._platform.uid_base}_ac_pf_{self._phase.lower()}"

    @property
    def name(self) -> str:
        """Return the name."""
        if self._phase is None:
            return "AC Power Factor"
        return f"AC Power Factor {self._phase.upper()}"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return False

    @property
    def _model_key(self) -> str:
        if self._phase is None:
            return "AC_PF"
        return f"AC_PF_{self._phase.upper()}"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = getattr(self._data, self._model_key)
        sf = self._data.AC_PF_SF
        return (
            super().available
            and value is not None
            and value != SunSpecNotImpl.INT16
            and sf is not None
            and sf != SunSpecNotImpl.INT16
            and sf in SUNSPEC_SF_RANGE
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self.scale_factor(
            getattr(self._data, self._model_key), self._data.AC_PF_SF
        )

    @property
    def suggested_display_precision(self):
        """Return the suggested display precision."""
        return abs(self._data.AC_PF_SF)


class ACPowerFactorInverter(ACPowerFactor):
    """Representation of a ac power factor inverter."""

    @property
    def _data(self):
        return self._platform.inverter_data


class ACPowerFactorMeter(ACPowerFactor):
    """Representation of a ac power factor meter."""

    @property
    def _data(self):
        return self._platform.meter_data


class SolarEdgeACEnergy(SolarEdgeSensorBase, RestoreSensor):
    """A long-term statistic that holds its last value.

    Devices legitimately go offline. Follows the TOTAL_INCREASING pattern from
    https://home-assistant-libs.github.io/modbus-connection/home-assistant/integration/#the-coordinator

    Base class for SolarEdgeACEnergyInverter/SolarEdgeACEnergyMeter.
    """

    device_class = SensorDeviceClass.ENERGY
    state_class = SensorStateClass.TOTAL_INCREASING
    native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    suggested_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    suggested_display_precision = 3

    def __init__(self, platform, config_entry, coordinator, phase: str | None = None):
        """Initialize the solar edge ac energy."""
        super().__init__(platform, config_entry, coordinator)

        self._phase = phase
        self._log_once = False

        if self._phase is None:
            self._model_key = "AC_Energy_WH"
        else:
            self._model_key = f"AC_Energy_WH_{self._phase}"

    @property
    def icon(self) -> str:
        """Return the icon."""
        if self._phase is None:
            return None

        if re.match("import", self._phase.lower()):
            return "mdi:transmission-tower-export"

        if re.match("export", self._phase.lower()):
            return "mdi:transmission-tower-import"

        return None

    @property
    def unique_id(self) -> str:
        # older versions of the integration converted to kWh internally
        # before home assistant had UI configurable units and precision
        # changing the unique_id now would cause new entities to be created
        """Return the unique id."""
        if self._phase is None:
            return f"{self._platform.uid_base}_ac_energy_kwh"
        return f"{self._platform.uid_base}_{self._phase.lower()}_kwh"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        if self._phase is None or self._phase in [
            "Exported",
            "Imported",
            "Exported_A",
            "Imported_A",
        ]:
            return True

        if self._data.C_SunSpec_DID in [203, 204] and self._phase in [
            "Exported_B",
            "Exported_C",
            "Imported_B",
            "Imported_C",
        ]:
            return True

        return False

    @property
    def name(self) -> str:
        """Return the name."""
        if self._phase is None:
            return "AC Energy"
        return f"AC Energy {re.sub('_', ' ', self._phase)}"

    @property
    def available(self) -> bool:
        """Return the available."""
        return True

    async def async_added_to_hass(self) -> None:
        """Added to hass."""
        await super().async_added_to_hass()
        if (last_data := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last_data.native_value
        self._process_data()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._process_data()
        super()._handle_coordinator_update()

    def _process_data(self) -> None:
        raw_value = getattr(self._data, self._model_key)
        sf = self._data.AC_Energy_WH_SF

        if (
            raw_value is None
            or raw_value in (SunSpecAccum.NA32, SunSpecAccum.LIMIT32)
            or sf not in SUNSPEC_SF_RANGE
        ):
            return

        try:
            value = self.scale_factor(raw_value, sf)
        except (ZeroDivisionError, OverflowError) as e:
            _LOGGER.debug("total_increasing %s exception: %s", self._model_key, e)
            return

        last = self._attr_native_value

        if last is not None and last * 0.99 <= value < last:
            if not self._log_once:
                _LOGGER.warning(
                    "Inverter accumulator went backwards; this is a SolarEdge bug: %s "
                    "%s < %s",
                    self._model_key,
                    value,
                    last,
                )
                self._log_once = True

            return  # ignore firmware issue causing minor decrease

        self._log_once = False
        self._attr_native_value = value


class SolarEdgeACEnergyInverter(SolarEdgeACEnergy):
    """Representation of a solar edge ac energy inverter."""

    @property
    def _data(self):
        return self._platform.inverter_data


class SolarEdgeACEnergyMeter(SolarEdgeACEnergy):
    """Representation of a solar edge ac energy meter."""

    @property
    def _data(self):
        return self._platform.meter_data


class DCCurrent(SolarEdgeSensorBase):
    """DC Current for a SolarEdge inverter."""

    device_class = SensorDeviceClass.CURRENT
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    icon = "mdi:current-dc"

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_dc_current"

    @property
    def name(self) -> str:
        """Return the name."""
        return "DC Current"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.inverter_data.I_DC_Current
        sf = self._platform.inverter_data.I_DC_Current_SF
        return (
            super().available
            and value is not None
            and value != SunSpecNotImpl.UINT16
            and sf is not None
            and sf != SunSpecNotImpl.INT16
            and sf in SUNSPEC_SF_RANGE
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self.scale_factor(
            self._platform.inverter_data.I_DC_Current,
            self._platform.inverter_data.I_DC_Current_SF,
        )

    @property
    def suggested_display_precision(self) -> int:
        """Return the suggested display precision."""
        sf = self._platform.inverter_data.I_DC_Current_SF
        if sf not in SUNSPEC_SF_RANGE:
            return 1

        return abs(sf)


class SolarEdgeDCCurrentMMPPT(SolarEdgeSensorBase):
    """DC Current for Synergy MMPPT units."""

    device_class = SensorDeviceClass.CURRENT
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    icon = "mdi:current-dc"

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return (
            f"{self._platform.inverter.uid_base}_dc_current_mmppt{self._platform.unit}"
        )

    @property
    def name(self) -> str:
        """Return the name."""
        return "DC Current"

    @property
    def available(self) -> bool:
        """Return the available."""
        mmppt_data = self._platform.inverter.mmppt_data
        dca = mmppt_data.units[self._platform.unit].DCA
        sf = mmppt_data.mmppt_DCA_SF
        return (
            super().available
            and dca is not None
            and dca != SunSpecNotImpl.UINT16
            and sf is not None
            and sf != SunSpecNotImpl.INT16
            and sf in SUNSPEC_SF_RANGE
        )

    @property
    def native_value(self):
        """Return the native value."""
        mmppt_data = self._platform.inverter.mmppt_data
        return self.scale_factor(
            mmppt_data.units[self._platform.unit].DCA, mmppt_data.mmppt_DCA_SF
        )

    @property
    def suggested_display_precision(self) -> int:
        """Return the suggested display precision."""
        return abs(self._platform.inverter.mmppt_data.mmppt_DCA_SF)


class DCVoltage(SolarEdgeSensorBase):
    """DC Voltage for a SolarEdge inverter."""

    device_class = SensorDeviceClass.VOLTAGE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfElectricPotential.VOLT

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_dc_voltage"

    @property
    def name(self) -> str:
        """Return the name."""
        return "DC Voltage"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.inverter_data.I_DC_Voltage
        sf = self._platform.inverter_data.I_DC_Voltage_SF
        return (
            super().available
            and value is not None
            and value != SunSpecNotImpl.UINT16
            and sf is not None
            and sf != SunSpecNotImpl.INT16
            and sf in SUNSPEC_SF_RANGE
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self.scale_factor(
            self._platform.inverter_data.I_DC_Voltage,
            self._platform.inverter_data.I_DC_Voltage_SF,
        )

    @property
    def suggested_display_precision(self):
        """Return the suggested display precision."""
        return abs(self._platform.inverter_data.I_DC_Voltage_SF)


class SolarEdgeDCVoltageMMPPT(SolarEdgeSensorBase):
    """DC Voltage for Synergy MMPPT units."""

    device_class = SensorDeviceClass.VOLTAGE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfElectricPotential.VOLT

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return (
            f"{self._platform.inverter.uid_base}_dc_voltage_mmppt{self._platform.unit}"
        )

    @property
    def name(self) -> str:
        """Return the name."""
        return "DC Voltage"

    @property
    def available(self) -> bool:
        """Return the available."""
        mmppt_data = self._platform.inverter.mmppt_data
        dcv = mmppt_data.units[self._platform.unit].DCV
        sf = mmppt_data.mmppt_DCV_SF
        return (
            super().available
            and dcv is not None
            and dcv != SunSpecNotImpl.UINT16
            and sf is not None
            and sf != SunSpecNotImpl.INT16
            and sf in SUNSPEC_SF_RANGE
        )

    @property
    def native_value(self):
        """Return the native value."""
        mmppt_data = self._platform.inverter.mmppt_data
        return self.scale_factor(
            mmppt_data.units[self._platform.unit].DCV, mmppt_data.mmppt_DCV_SF
        )

    @property
    def suggested_display_precision(self) -> int:
        """Return the suggested display precision."""
        return abs(self._platform.inverter.mmppt_data.mmppt_DCV_SF)


class DCPower(SolarEdgeSensorBase):
    """DC Power for a SolarEdge inverter."""

    device_class = SensorDeviceClass.POWER
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfPower.WATT
    icon = "mdi:solar-power"

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_dc_power"

    @property
    def name(self) -> str:
        """Return the name."""
        return "DC Power"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.inverter_data.I_DC_Power
        sf = self._platform.inverter_data.I_DC_Power_SF
        return (
            super().available
            and value is not None
            and value != SunSpecNotImpl.INT16
            and sf is not None
            and sf != SunSpecNotImpl.INT16
            and sf in SUNSPEC_SF_RANGE
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self.scale_factor(
            self._platform.inverter_data.I_DC_Power,
            self._platform.inverter_data.I_DC_Power_SF,
        )

    @property
    def suggested_display_precision(self):
        """Return the suggested display precision."""
        return abs(self._platform.inverter_data.I_DC_Power_SF)


class SolarEdgeDCPowerMMPPT(SolarEdgeSensorBase):
    """DC Power for Synergy MMPPT units."""

    device_class = SensorDeviceClass.POWER
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfPower.WATT
    icon = "mdi:solar-power"

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.inverter.uid_base}_dc_power_mmppt{self._platform.unit}"

    @property
    def name(self) -> str:
        """Return the name."""
        return "DC Power"

    @property
    def available(self) -> bool:
        """Return the available."""
        mmppt_data = self._platform.inverter.mmppt_data
        dcw = mmppt_data.units[self._platform.unit].DCW
        sf = mmppt_data.mmppt_DCW_SF
        return (
            super().available
            and dcw is not None
            and dcw != SunSpecNotImpl.UINT16
            and sf is not None
            and sf != SunSpecNotImpl.INT16
            and sf in SUNSPEC_SF_RANGE
        )

    @property
    def native_value(self):
        """Return the native value."""
        mmppt_data = self._platform.inverter.mmppt_data
        return self.scale_factor(
            mmppt_data.units[self._platform.unit].DCW, mmppt_data.mmppt_DCW_SF
        )

    @property
    def suggested_display_precision(self) -> int:
        """Return the suggested display precision."""
        return abs(self._platform.inverter.mmppt_data.mmppt_DCW_SF)


class HeatSinkTemperature(SolarEdgeSensorBase):
    """Heat sink temperature for a SolarEdge inverter."""

    device_class = SensorDeviceClass.TEMPERATURE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfTemperature.CELSIUS
    entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_temp_sink"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Temperature"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.inverter_data.I_Temp_Sink
        sf = self._platform.inverter_data.I_Temp_SF
        return (
            super().available
            and value is not None
            and value not in (0, SunSpecNotImpl.INT16)
            and sf is not None
            and sf != SunSpecNotImpl.INT16
            and sf in SUNSPEC_SF_RANGE
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self.scale_factor(
            self._platform.inverter_data.I_Temp_Sink,
            self._platform.inverter_data.I_Temp_SF,
        )

    @property
    def suggested_display_precision(self):
        """Return the suggested display precision."""
        return abs(self._platform.inverter_data.I_Temp_SF)


class SolarEdgeTemperatureMMPPT(SolarEdgeSensorBase):
    """Temperature for Synergy MMPPT units."""

    device_class = SensorDeviceClass.TEMPERATURE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfTemperature.CELSIUS
    entity_category = EntityCategory.DIAGNOSTIC
    suggested_display_precision = 0

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.inverter.uid_base}_tmp_mmppt{self._platform.unit}"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Temperature"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.inverter.mmppt_data.units[self._platform.unit].Tmp
        return super().available and value is not None and value != SunSpecNotImpl.INT16

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.inverter.mmppt_data.units[self._platform.unit].Tmp


class SolarEdgeWriteCount(RestoreEntity, SolarEdgeSensorBase):
    """Number of Modbus write commands sent to this inverter's unit ID.

    Tracks writes for possible flash wear. This counts only writes we
    addressed to this specific unit ID. A leader inverter may propagate
    settings to linked followers internally, but the integration can't know that,
    so it isn't reflected in any other unit's write count. See discussion
    https://github.com/WillCodeForCats/solaredge-modbus-multi/discussions/727
    """

    entity_category = EntityCategory.DIAGNOSTIC
    state_class = SensorStateClass.TOTAL_INCREASING
    icon = "mdi:file-document-edit-outline"

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_write_count"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Write Count"

    @property
    def available(self) -> bool:
        """Return the available."""
        return True

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.write_count

    async def async_added_to_hass(self) -> None:
        """Added to hass."""
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state not in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            with contextlib.suppress(ValueError):
                self._platform.write_count = int(last_state.state)

        self._platform.write_count_listeners.add(self._write_count_updated)

    async def async_will_remove_from_hass(self) -> None:
        """Will remove from hass."""
        self._platform.write_count_listeners.discard(self._write_count_updated)
        await super().async_will_remove_from_hass()

    @callback
    def _write_count_updated(self) -> None:
        self.async_write_ha_state()


class SolarEdgeStatusSensor(SolarEdgeSensorBase):
    """Representation of a solar edge status sensor."""

    device_class = SensorDeviceClass.ENUM
    entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_status"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Status"


class SolarEdgeInverterStatus(SolarEdgeStatusSensor):
    """Representation of a solar edge inverter status."""

    options = list(DEVICE_STATUS.values())

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.inverter_data.I_Status
        return (
            super().available
            and value is not None
            and value != SunSpecNotImpl.UINT16
            and value in DEVICE_STATUS
        )

    @property
    def native_value(self):
        """Return the native value."""
        return str(DEVICE_STATUS[self._platform.inverter_data.I_Status])

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        value = self._platform.inverter_data.I_Status
        attrs = {}

        if value in DEVICE_STATUS_TEXT:
            attrs["status_text"] = DEVICE_STATUS_TEXT[value]
            attrs["status_value"] = value

        return attrs


class SolarEdgeBatteryStatus(SolarEdgeStatusSensor):
    """Representation of a solar edge battery status."""

    options = list(BATTERY_STATUS.values())

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.battery_data.B_Status
        return (
            super().available
            and value is not None
            and value != SunSpecNotImpl.UINT32
            and value in BATTERY_STATUS
        )

    @property
    def native_value(self):
        """Return the native value."""
        return str(BATTERY_STATUS[self._platform.battery_data.B_Status])

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        value = self._platform.battery_data.B_Status
        attrs = {"status_value": value}

        if value in BATTERY_STATUS_TEXT:
            attrs["status_text"] = BATTERY_STATUS_TEXT[value]

        return attrs


class SolarEdgeDERBatteryBase(SolarEdgeSensorBase):
    """Base for DER Storage Capacity (SunSpec model 713) sensors.

    The platform is the inverter; its entities are reported on the inverter
    device. der_id is the 1-based position of the model 713 block.
    """

    def __init__(self, platform, config_entry, coordinator, der_id: int):
        """Initialize the DER battery sensor."""
        super().__init__(platform, config_entry, coordinator)
        self._der_id = der_id

    @property
    def _der(self):
        return self._platform.der_storage[self._der_id - 1]

    @property
    def _name_prefix(self) -> str:
        if len(self._platform.der_storage) > 1:
            return f"Battery {self._der_id}"
        return "Battery"

    def _unique_id(self, suffix: str) -> str:
        return f"{self._platform.uid_base}_DERB{self._der_id}_{suffix}"

    @staticmethod
    def _enabled_default_for(value) -> bool:
        """Enable by default only for a value other than 0% or not-implemented.

        SolarEdge reports 0% both for an empty battery and for no battery
        installed, so the default is decided once, from the first value seen.
        Users can enable the entity manually.
        """
        return (
            value is not None
            and float_to_hex(value) != hex(SunSpecNotImpl.FLOAT32)
            and value != 0
        )

    async def async_added_to_hass(self) -> None:
        """Register as a DER listener when added."""
        # Only enabled entities are added; the inverter skips reading the DER
        # Storage Capacity block when none are.
        await super().async_added_to_hass()
        self._platform.der_storage_listeners.add(self)

    async def async_will_remove_from_hass(self) -> None:
        """Remove the DER listener when removed."""
        self._platform.der_storage_listeners.discard(self)
        await super().async_will_remove_from_hass()


class SolarEdgeDERBatterySOE(SolarEdgeDERBatteryBase):
    """State of Energy from DER Storage Capacity (SunSpec model 713)."""

    device_class = SensorDeviceClass.BATTERY
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = PERCENTAGE
    suggested_display_precision = 0

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return self._unique_id("battery_soe")

    @property
    def name(self) -> str:
        """Return the name."""
        return f"{self._name_prefix} State of Energy"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return self._enabled_default_for(self._der.SoC)

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._der.SoC
        return (
            super().available
            and value is not None
            and float_to_hex(value) != hex(SunSpecNotImpl.FLOAT32)
            and 0 <= value <= 100
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self._der.SoC


class SolarEdgeDERBatterySOH(SolarEdgeDERBatteryBase):
    """State of Health from DER Storage Capacity (SunSpec model 713)."""

    state_class = SensorStateClass.MEASUREMENT
    entity_category = EntityCategory.DIAGNOSTIC
    native_unit_of_measurement = PERCENTAGE
    suggested_display_precision = 0
    icon = "mdi:battery-heart-outline"

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return self._unique_id("battery_soh")

    @property
    def name(self) -> str:
        """Return the name."""
        return f"{self._name_prefix} State of Health"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return self._enabled_default_for(self._der.SoH)

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._der.SoH
        return (
            super().available
            and value is not None
            and float_to_hex(value) != hex(SunSpecNotImpl.FLOAT32)
            and 0 <= value <= 100
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self._der.SoH


class SolarEdgeDERBatteryStatus(SolarEdgeDERBatteryBase):
    """Status for DER Storage Capacity (SunSpec model 713).

    This doesn't appear to be currently supported by SolarEdge devices;
    this exists in case that changes in the future.
    """

    device_class = SensorDeviceClass.ENUM
    entity_category = EntityCategory.DIAGNOSTIC
    options = list(DER_BATTERY_STATUS.values())

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return self._unique_id("status")

    @property
    def name(self) -> str:
        """Return the name."""
        return f"{self._name_prefix} Status"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return False

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._der.Sta
        return super().available and value is not None and value in DER_BATTERY_STATUS

    @property
    def native_value(self):
        """Return the native value."""
        return str(DER_BATTERY_STATUS[self._der.Sta])

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        value = self._der.Sta
        attrs = {"status_value": value}

        if value in DER_BATTERY_STATUS_TEXT:
            attrs["status_text"] = DER_BATTERY_STATUS_TEXT[value]

        return attrs


class StatusVendor(SolarEdgeSensorBase):
    """Representation of a status vendor."""

    entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_status_vendor"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Status Vendor"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return not self._platform.use_status_vendor4

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.inverter_data.I_Status_Vendor
        return (
            super().available and value is not None and value != SunSpecNotImpl.UINT16
        )

    @property
    def native_value(self):
        """Return the native value."""
        return str(self._platform.inverter_data.I_Status_Vendor)

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        value = self._platform.inverter_data.I_Status_Vendor

        if value in VENDOR_STATUS:
            return {"description": VENDOR_STATUS[value]}

        return None


class StatusVendor4(SolarEdgeSensorBase):
    """Representation of a status vendor4."""

    entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_status_vendor4"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Status Vendor 4"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.inverter_data.I_Status_Vendor4
        return (
            super().available and value is not None and value != SunSpecNotImpl.UINT32
        )

    @property
    def native_value(self):
        """Return the native value."""
        value = self._platform.inverter_data.I_Status_Vendor4
        controller = (value >> 24) & 0xFF
        error = value & 0xFFFF
        return f"{controller:X}x{error:X}"

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        value = self._platform.inverter_data.I_Status_Vendor4

        controller = (value >> 24) & 0xFF
        error = value & 0xFFFF
        attrs = {
            "controller": hex(controller),
            "error_code": hex(error),
        }

        if controller in VENDOR4_STATUS and error in VENDOR4_STATUS[controller]:
            attrs["description"] = VENDOR4_STATUS[controller][error]

        return attrs


class SolarEdgeGlobalPowerControlBlock(SolarEdgeSensorBase):
    """Representation of a solar edge global power control block."""

    @property
    def available(self) -> bool:
        """Return the available."""
        return super().available and self._platform.has_global_power_control


class SolarEdgeRRCR(SolarEdgeGlobalPowerControlBlock):
    """Representation of a solar edge rrcr."""

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_rrcr"

    @property
    def name(self) -> str:
        """Return the name."""
        return "RRCR Status"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return self._platform.has_global_power_control is True

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.global_power_control_data.I_RRCR
        return (
            super().available
            and value is not None
            and value != SunSpecNotImpl.UINT16
            and value <= 0xF
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.global_power_control_data.I_RRCR

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        value = self._platform.global_power_control_data.I_RRCR
        rrcr_inputs = []

        if value != 0x0:
            rrcr_inputs.extend(RRCR_STATUS[i] for i in range(4) if value & (1 << i))

        return {"inputs": str(rrcr_inputs)}


class SolarEdgeActivePowerLimit(SolarEdgeGlobalPowerControlBlock):
    """Global Dynamic Power Control: Inverter Active Power Limit."""

    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = PERCENTAGE
    suggested_display_precision = 0
    icon = "mdi:percent"

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_active_power_limit"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Active Power Limit"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return self._platform.has_global_power_control is True

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.global_power_control_data.I_Power_Limit
        return (
            super().available
            and value is not None
            and value != SunSpecNotImpl.UINT16
            and 0 <= value <= 100
        )

    @property
    def native_value(self) -> int:
        """Return the native value."""
        return self._platform.global_power_control_data.I_Power_Limit


class SolarEdgeCosPhi(SolarEdgeGlobalPowerControlBlock):
    """Global Dynamic Power Control: Inverter CosPhi."""

    state_class = SensorStateClass.MEASUREMENT
    suggested_display_precision = 1
    icon = "mdi:angle-acute"

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_cosphi"

    @property
    def name(self) -> str:
        """Return the name."""
        return "CosPhi"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return self._platform.has_global_power_control is True

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.global_power_control_data.I_CosPhi
        return (
            super().available
            and value is not None
            and float_to_hex(value) != hex(SunSpecNotImpl.FLOAT32)
            and -1.0 <= value <= 1.0
        )

    @property
    def native_value(self) -> float:
        """Return the native value."""
        return round(self._platform.global_power_control_data.I_CosPhi, 1)


class MeterEvents(SolarEdgeSensorBase):
    """Representation of a meter events."""

    entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_meter_events"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Meter Events"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.meter_data.M_Events
        return (
            super().available and value is not None and value != SunSpecNotImpl.UINT32
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.meter_data.M_Events

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        value = self._platform.meter_data.M_Events
        m_events_active = []

        if value != 0x0:
            for i in range(2, 31):
                try:
                    if value & (1 << i):
                        m_events_active.append(METER_EVENTS[i])

                except KeyError:  # noqa: PERF203
                    pass

        return {
            "bits": f"{value:032b}",
            "events": str(m_events_active),
        }


class SolarEdgeMMPPTEvents(SolarEdgeSensorBase):
    """Representation of a solar edge mmppt events."""

    entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_mmppt_events"

    @property
    def name(self) -> str:
        """Return the name."""
        return "MMPPT Events"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.mmppt_data.mmppt_Events
        return (
            super().available and value is not None and value != SunSpecNotImpl.UINT32
        )

    @property
    def native_value(self) -> int:
        """Return the native value."""
        return self._platform.mmppt_data.mmppt_Events

    @property
    def extra_state_attributes(self) -> str:
        """Return the extra state attributes."""
        value = self._platform.mmppt_data.mmppt_Events
        mmppt_events_active = []

        if value != 0x0:
            for i in range(31):
                try:
                    if value & (1 << i):
                        mmppt_events_active.append(MMPPT_EVENTS[i])
                except KeyError:  # noqa: PERF203
                    pass

        return {
            "events": str(mmppt_events_active),
            "bits": f"{value:032b}",
        }


class MeterVAhIE(SolarEdgeSensorBase, RestoreSensor):
    """A long-term statistic that holds its last value.

    Devices legitimately go offline. Follows the TOTAL_INCREASING pattern from
    https://home-assistant-libs.github.io/modbus-connection/home-assistant/integration/#the-coordinator
    """

    device_class = SensorDeviceClass.ENERGY
    state_class = SensorStateClass.TOTAL_INCREASING
    native_unit_of_measurement = ENERGY_VOLT_AMPERE_HOUR

    def __init__(self, platform, config_entry, coordinator, phase: str | None = None):
        """Initialize the meter v ah ie."""
        super().__init__(platform, config_entry, coordinator)

        self._phase = phase

    @property
    def icon(self) -> str:
        """Return the icon."""
        if self._phase is None:
            return None

        if re.match("import", self._phase.lower()):
            return "mdi:transmission-tower-export"

        if re.match("export", self._phase.lower()):
            return "mdi:transmission-tower-import"

        return None

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        if self._phase is None:
            raise NotImplementedError
        return f"{self._platform.uid_base}_{self._phase.lower()}_vah"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return False

    @property
    def name(self) -> str:
        """Return the name."""
        if self._phase is None:
            raise NotImplementedError
        return f"Apparent Energy {re.sub('_', ' ', self._phase)}"

    @property
    def available(self) -> bool:
        """Return the available."""
        return True

    async def async_added_to_hass(self) -> None:
        """Added to hass."""
        await super().async_added_to_hass()
        if (last_data := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last_data.native_value
        self._process_data()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._process_data()
        super()._handle_coordinator_update()

    def _process_data(self) -> None:
        if self._phase is None:
            raise NotImplementedError

        raw_value = getattr(self._platform.meter_data, f"M_VAh_{self._phase}")
        sf = self._platform.meter_data.M_VAh_SF

        if (
            raw_value is None
            or raw_value in (SunSpecAccum.NA32, SunSpecAccum.LIMIT32)
            or sf is None
            or sf == SunSpecNotImpl.INT16
            or sf not in SUNSPEC_SF_RANGE
        ):
            return

        value = self.scale_factor(raw_value, sf)
        last = self._attr_native_value

        if last is not None and last * 0.99 <= value < last:
            return  # ignore firmware issue causing minor decrease

        self._attr_native_value = value

    @property
    def suggested_display_precision(self):
        """Return the suggested display precision."""
        return abs(self._platform.meter_data.M_VAh_SF)


class MetervarhIE(SolarEdgeSensorBase, RestoreSensor):
    """A long-term statistic that holds its last value.

    Devices legitimately go offline. Follows the TOTAL_INCREASING pattern from
    https://home-assistant-libs.github.io/modbus-connection/home-assistant/integration/#the-coordinator
    """

    device_class = SensorDeviceClass.REACTIVE_ENERGY
    state_class = SensorStateClass.TOTAL_INCREASING
    native_unit_of_measurement = UnitOfReactiveEnergy.VOLT_AMPERE_REACTIVE_HOUR

    def __init__(self, platform, config_entry, coordinator, phase: str | None = None):
        """Initialize the metervarh ie."""
        super().__init__(platform, config_entry, coordinator)

        self._phase = phase

    @property
    def icon(self) -> str:
        """Return the icon."""
        if self._phase is None:
            return None

        if re.match("import", self._phase.lower()):
            return "mdi:transmission-tower-export"

        if re.match("export", self._phase.lower()):
            return "mdi:transmission-tower-import"

        return None

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        if self._phase is None:
            raise NotImplementedError
        return f"{self._platform.uid_base}_{self._phase.lower()}_varh"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return False

    @property
    def name(self) -> str:
        """Return the name."""
        if self._phase is None:
            raise NotImplementedError
        return f"Reactive Energy {re.sub('_', ' ', self._phase)}"

    @property
    def available(self) -> bool:
        """Return the available."""
        return True

    async def async_added_to_hass(self) -> None:
        """Added to hass."""
        await super().async_added_to_hass()
        if (last_data := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last_data.native_value
        self._process_data()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._process_data()
        super()._handle_coordinator_update()

    def _process_data(self) -> None:
        if self._phase is None:
            raise NotImplementedError

        raw_value = getattr(self._platform.meter_data, f"M_varh_{self._phase}")
        sf = self._platform.meter_data.M_varh_SF

        if (
            raw_value is None
            or raw_value in (SunSpecAccum.NA32, SunSpecAccum.LIMIT32)
            or sf is None
            or sf == SunSpecNotImpl.INT16
            or sf not in SUNSPEC_SF_RANGE
        ):
            return

        value = self.scale_factor(raw_value, sf)
        last = self._attr_native_value

        if last is not None and last * 0.99 <= value < last:
            return  # ignore firmware issue causing minor decrease

        self._attr_native_value = value

    @property
    def suggested_display_precision(self):
        """Return the suggested display precision."""
        return abs(self._platform.meter_data.M_varh_SF)


class SolarEdgeBatteryAvgTemp(SolarEdgeSensorBase):
    """Representation of a solar edge battery avg temp."""

    device_class = SensorDeviceClass.TEMPERATURE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfTemperature.CELSIUS
    entity_category = EntityCategory.DIAGNOSTIC
    suggested_display_precision = 1

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_avg_temp"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Average Temperature"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.battery_data.B_Temp_Average
        return (
            super().available
            and value is not None
            and float_to_hex(value) != hex(SunSpecNotImpl.FLOAT32)
            and BatteryLimit.Tmin <= value <= BatteryLimit.Tmax
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.battery_data.B_Temp_Average


class SolarEdgeBatteryMaxTemp(SolarEdgeSensorBase):
    """Representation of a solar edge battery max temp."""

    device_class = SensorDeviceClass.TEMPERATURE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfTemperature.CELSIUS
    entity_category = EntityCategory.DIAGNOSTIC
    suggested_display_precision = 1

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_max_temp"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Max Temperature"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return False

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.battery_data.B_Temp_Max
        return (
            super().available
            and value is not None
            and float_to_hex(value) != hex(SunSpecNotImpl.FLOAT32)
            and BatteryLimit.Tmin <= value <= BatteryLimit.Tmax
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.battery_data.B_Temp_Max


class SolarEdgeBatteryVoltage(SolarEdgeSensorBase):
    """Representation of a solar edge battery voltage."""

    device_class = SensorDeviceClass.VOLTAGE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfElectricPotential.VOLT
    suggested_display_precision = 2

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_dc_voltage"

    @property
    def name(self) -> str:
        """Return the name."""
        return "DC Voltage"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.battery_data.B_DC_Voltage
        return (
            super().available
            and value is not None
            and float_to_hex(value) != hex(SunSpecNotImpl.FLOAT32)
            and BatteryLimit.Vmin <= value <= BatteryLimit.Vmax
            and self._platform.battery_data.B_Status != 0
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.battery_data.B_DC_Voltage


class SolarEdgeBatteryCurrent(SolarEdgeSensorBase):
    """Representation of a solar edge battery current."""

    device_class = SensorDeviceClass.CURRENT
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    suggested_display_precision = 2
    icon = "mdi:current-dc"

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_dc_current"

    @property
    def name(self) -> str:
        """Return the name."""
        return "DC Current"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.battery_data.B_DC_Current
        return (
            super().available
            and value is not None
            and float_to_hex(value) != hex(SunSpecNotImpl.FLOAT32)
            and BatteryLimit.Amin <= value <= BatteryLimit.Amax
            and self._platform.battery_data.B_Status != 0
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.battery_data.B_DC_Current


class SolarEdgeBatteryPower(SolarEdgeSensorBase):
    """Representation of a solar edge battery power."""

    device_class = SensorDeviceClass.POWER
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfPower.WATT
    suggested_display_precision = 2
    icon = "mdi:lightning-bolt"

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_dc_power"

    @property
    def name(self) -> str:
        """Return the name."""
        return "DC Power"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.battery_data.B_DC_Power
        return (
            super().available
            and value is not None
            and float_to_hex(value) != hex(SunSpecNotImpl.FLOAT32)
            and float_to_hex(value) != "0xff7fffff"
            and float_to_hex(value) != "0x7f7fffff"
            and self._platform.battery_data.B_Status != 0
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.battery_data.B_DC_Power


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
        """Initialize the solar edge battery power inverted."""
        super().__init__(platform, config_entry, coordinator)

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{super().unique_id}_inverted"

    @property
    def name(self) -> str:
        """Return the name."""
        return f"{super().name} Inverted"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return AwesomeVersion(HA_VERSION) < AwesomeVersion(INVERTED_POWER_VERSION)

    @property
    def native_value(self):
        """Return the native value."""
        value = super().native_value
        if value is None:
            return None
        return -value


class SolarEdgeBatteryEnergyExport(SolarEdgeSensorBase, RestoreSensor):
    """A long-term statistic that holds its last value.

    Devices legitimately go offline. Follows the TOTAL_INCREASING pattern from
    https://home-assistant-libs.github.io/modbus-connection/home-assistant/integration/#the-coordinator

    A sustained decrease here can be expected behavior.
    See allow_battery_energy_reset/battery_energy_reset_cycles.
    """

    device_class = SensorDeviceClass.ENERGY
    state_class = SensorStateClass.TOTAL_INCREASING
    native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    suggested_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    suggested_display_precision = 3
    icon = "mdi:battery-charging-20"

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the solar edge battery energy export."""
        super().__init__(platform, config_entry, coordinator)

        self._last = None
        self._count = 0
        self._log_once = False

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_energy_export"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Energy Export"

    @property
    def available(self) -> bool:
        """Return the available."""
        return True

    async def async_added_to_hass(self) -> None:
        """Added to hass."""
        await super().async_added_to_hass()
        if (last_data := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last_data.native_value
            self._last = last_data.native_value
        self._process_data()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._process_data()
        super()._handle_coordinator_update()

    def _process_data(self) -> None:
        value = self._platform.battery_data.B_Export_Energy_WH

        if (
            value is None
            or value == 0xFFFFFFFFFFFFFFFF
            or (value == 0x0 and not self._platform.allow_battery_energy_reset)
        ):
            return

        if self._last is None:
            self._last = 0

        try:
            if value >= self._last:
                self._last = value
                self._attr_native_value = value
                self._log_once = False

                if self._platform.allow_battery_energy_reset:
                    self._count = 0

                return

            if not self._platform.allow_battery_energy_reset:
                if not self._log_once:
                    _LOGGER.warning(
                        "Battery Export Energy went backwards: Current value %s is "
                        "less than last value of %s",
                        value,
                        self._last,
                    )
                    self._log_once = True
                return

            self._count += 1
            _LOGGER.debug(
                "B_Export_Energy went backwards: %s < %s cycle %s of %s",
                value,
                self._last,
                self._count,
                self._platform.battery_energy_reset_cycles,
            )

            if self._count > self._platform.battery_energy_reset_cycles:
                _LOGGER.debug("B_Export_Energy reset at cycle %s", self._count)
                self._last = None
                self._count = 0

        except OverflowError:
            return


class SolarEdgeBatteryEnergyImport(SolarEdgeSensorBase, RestoreSensor):
    """A long-term statistic that holds its last value.

    Devices legitimately go offline. Follows the TOTAL_INCREASING pattern from
    https://home-assistant-libs.github.io/modbus-connection/home-assistant/integration/#the-coordinator

    A sustained decrease here can be expected behavior.
    See allow_battery_energy_reset/battery_energy_reset_cycles.
    """

    device_class = SensorDeviceClass.ENERGY
    state_class = SensorStateClass.TOTAL_INCREASING
    native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    suggested_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    suggested_display_precision = 3
    icon = "mdi:battery-charging-100"

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the solar edge battery energy import."""
        super().__init__(platform, config_entry, coordinator)

        self._last = None
        self._count = 0
        self._log_once = False

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_energy_import"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Energy Import"

    @property
    def available(self) -> bool:
        """Return the available."""
        return True

    async def async_added_to_hass(self) -> None:
        """Added to hass."""
        await super().async_added_to_hass()
        if (last_data := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last_data.native_value
            self._last = last_data.native_value
        self._process_data()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._process_data()
        super()._handle_coordinator_update()

    def _process_data(self) -> None:
        value = self._platform.battery_data.B_Import_Energy_WH

        if (
            value is None
            or value == 0xFFFFFFFFFFFFFFFF
            or (value == 0x0 and not self._platform.allow_battery_energy_reset)
        ):
            return

        if self._last is None:
            self._last = 0

        try:
            if value >= self._last:
                self._last = value
                self._attr_native_value = value
                self._log_once = False

                if self._platform.allow_battery_energy_reset:
                    self._count = 0

                return

            if not self._platform.allow_battery_energy_reset:
                if not self._log_once:
                    _LOGGER.warning(
                        "Battery Import Energy went backwards: Current value %s is "
                        "less than last value of %s",
                        value,
                        self._last,
                    )
                    self._log_once = True
                return

            self._count += 1
            _LOGGER.debug(
                "B_Import_Energy went backwards: %s < %s cycle %s of %s",
                value,
                self._last,
                self._count,
                self._platform.battery_energy_reset_cycles,
            )

            if self._count > self._platform.battery_energy_reset_cycles:
                _LOGGER.debug("B_Import_Energy reset at cycle %s", self._count)
                self._last = None
                self._count = 0

        except OverflowError:
            return


class SolarEdgeBatteryMaxEnergy(SolarEdgeSensorBase):
    """Representation of a solar edge battery max energy."""

    device_class = SensorDeviceClass.ENERGY_STORAGE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    suggested_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    suggested_display_precision = 3

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_max_energy"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Maximum Energy"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.battery_data.B_Energy_Max
        rated_energy = self._platform.battery_info.B_RatedEnergy
        return (
            super().available
            and value is not None
            and float_to_hex(value) != hex(SunSpecNotImpl.FLOAT32)
            and rated_energy is not None
            and 0 <= value <= rated_energy
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.battery_data.B_Energy_Max


class SolarEdgeBatteryPowerBase(SolarEdgeSensorBase):
    """Representation of a solar edge battery power base."""

    device_class = SensorDeviceClass.POWER
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfPower.WATT
    entity_category = EntityCategory.DIAGNOSTIC
    suggested_display_precision = 0


class SolarEdgeBatteryMaxChargePower(SolarEdgeBatteryPowerBase):
    """Representation of a solar edge battery max charge power."""

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_max_charge_power"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Max Charge Power"

    @property
    def available(self):
        """Return the available."""
        value = self._platform.battery_data.B_MaxChargePower
        return (
            super().available
            and value is not None
            and float_to_hex(value) != hex(SunSpecNotImpl.FLOAT32)
            and value >= 0
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.battery_data.B_MaxChargePower


class SolarEdgeBatteryMaxChargePeakPower(SolarEdgeBatteryPowerBase):
    """Representation of a solar edge battery max charge peak power."""

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_max_charge_peak_power"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Peak Charge Power"

    @property
    def available(self):
        """Return the available."""
        value = self._platform.battery_data.B_MaxChargePeakPower
        return (
            super().available
            and value is not None
            and float_to_hex(value) != hex(SunSpecNotImpl.FLOAT32)
            and value >= 0
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.battery_data.B_MaxChargePeakPower


class SolarEdgeBatteryMaxDischargePower(SolarEdgeBatteryPowerBase):
    """Representation of a solar edge battery max discharge power."""

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_max_discharge_power"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Max Discharge Power"

    @property
    def available(self):
        """Return the available."""
        value = self._platform.battery_data.B_MaxDischargePower
        return (
            super().available
            and value is not None
            and float_to_hex(value) != hex(SunSpecNotImpl.FLOAT32)
            and value >= 0
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.battery_data.B_MaxDischargePower


class SolarEdgeBatteryMaxDischargePeakPower(SolarEdgeBatteryPowerBase):
    """Representation of a solar edge battery max discharge peak power."""

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_max_discharge_peak_power"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Peak Discharge Power"

    @property
    def available(self):
        """Return the available."""
        value = self._platform.battery_data.B_MaxDischargePeakPower
        return (
            super().available
            and value is not None
            and float_to_hex(value) != hex(SunSpecNotImpl.FLOAT32)
            and value >= 0
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.battery_data.B_MaxDischargePeakPower


class SolarEdgeBatteryAvailableEnergy(SolarEdgeSensorBase):
    """Representation of a solar edge battery available energy."""

    device_class = SensorDeviceClass.ENERGY_STORAGE
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    suggested_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    suggested_display_precision = 3

    def __init__(self, platform, config_entry, coordinator):
        """Initialize the solar edge battery available energy."""
        super().__init__(platform, config_entry, coordinator)
        self._log_warning = True

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_avail_energy"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Available Energy"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.battery_data.B_Energy_Available
        rated_energy = self._platform.battery_info.B_RatedEnergy

        if (
            not super().available
            or value is None
            or float_to_hex(value) == hex(SunSpecNotImpl.FLOAT32)
            or value < 0
            or rated_energy is None
        ):
            return False

        if value > rated_energy * self._platform.battery_rating_adjust:
            if self._log_warning:
                _LOGGER.warning(
                    "I%sB%s: Battery available energy exceeds rated energy. Set "
                    "configuration for Battery Rating Adjustment when necessary.",
                    self._platform.inverter_unit_id,
                    self._platform.battery_id,
                )
                self._log_warning = False

            return False

        return True

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.battery_data.B_Energy_Available


class SolarEdgeBatterySOH(SolarEdgeSensorBase):
    """Representation of a solar edge battery soh."""

    state_class = SensorStateClass.MEASUREMENT
    entity_category = EntityCategory.DIAGNOSTIC
    native_unit_of_measurement = PERCENTAGE
    suggested_display_precision = 0
    icon = "mdi:battery-heart-outline"

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_battery_soh"

    @property
    def name(self) -> str:
        """Return the name."""
        return "State of Health"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.battery_data.B_SOH
        return (
            super().available
            and value is not None
            and float_to_hex(value) != hex(SunSpecNotImpl.FLOAT32)
            and 0 <= value <= 100
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.battery_data.B_SOH


class SolarEdgeBatterySOE(SolarEdgeSensorBase):
    """Representation of a solar edge battery soe."""

    device_class = SensorDeviceClass.BATTERY
    state_class = SensorStateClass.MEASUREMENT
    native_unit_of_measurement = PERCENTAGE
    suggested_display_precision = 0

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_battery_soe"

    @property
    def name(self) -> str:
        """Return the name."""
        return "State of Energy"

    @property
    def available(self) -> bool:
        """Return the available."""
        value = self._platform.battery_data.B_SOE
        return (
            super().available
            and value is not None
            and float_to_hex(value) != hex(SunSpecNotImpl.FLOAT32)
            and 0 <= value <= 100
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.battery_data.B_SOE


class SolarEdgeAdvancedPowerControlBlock(SolarEdgeSensorBase):
    """Representation of a solar edge advanced power control block."""

    @property
    def available(self) -> bool:
        """Return the available."""
        return super().available and self._platform.has_advanced_power_control


class SolarEdgeCommitControlSettings(SolarEdgeAdvancedPowerControlBlock):
    """Entity to show the results of Commit Power Control Settings button."""

    entity_category = EntityCategory.DIAGNOSTIC
    icon = "mdi:content-save-cog-outline"

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_commit_pwr_settings"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Commit Power Settings"

    @property
    def available(self) -> bool:
        """Return the available."""
        return (
            super().available
            and self._platform.advanced_power_control_data.CommitPwrCtlSettings
            is not None
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.advanced_power_control_data.CommitPwrCtlSettings

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        value = self._platform.advanced_power_control_data.CommitPwrCtlSettings
        attrs = {"hex_value": hex(value)}

        if value == 0x0:
            attrs["status"] = "SUCCESS"
        if value in [0x1, 0x2, 0x3, 0x4]:
            attrs["status"] = "INTERNAL_ERROR"
        if value == 0xFFFF:
            attrs["status"] = "UNKNOWN_ERROR"
        if 0xF102 <= value < 0xFFFF:
            attrs["status"] = "VALUE_ERROR"

        return attrs


class SolarEdgeDefaultControlSettings(SolarEdgeAdvancedPowerControlBlock):
    """Entity to show the results of Restore Power Control Default Settings button."""

    entity_category = EntityCategory.DIAGNOSTIC
    icon = "mdi:restore-alert"

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_default_pwr_settings"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Default Power Settings"

    @property
    def available(self) -> bool:
        """Return the available."""
        return (
            super().available
            and self._platform.advanced_power_control_data.RestorePwrCtlDefaults
            is not None
        )

    @property
    def native_value(self):
        """Return the native value."""
        return self._platform.advanced_power_control_data.RestorePwrCtlDefaults

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        value = self._platform.advanced_power_control_data.RestorePwrCtlDefaults
        attrs = {"hex_value": hex(value)}

        if value == 0x0:
            attrs["status"] = "SUCCESS"
        if value == 0xFFFF:
            attrs["status"] = "ERROR"

        return attrs


class SolarEdgeLastUpdate(SolarEdgeSensorBase):
    """Representation of a solar edge last update."""

    device_class = SensorDeviceClass.TIMESTAMP
    entity_category = EntityCategory.DIAGNOSTIC

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._platform.uid_base}_last_update_timestamp"

    @property
    def name(self) -> str:
        """Return the name."""
        return "Last Update"

    @property
    def available(self) -> bool:
        """Return the available."""
        return True

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return the entity registry enabled default."""
        return False

    @property
    def native_value(self) -> datetime.datetime | None:
        """Return the native value."""
        return self.coordinator.last_update_success_time
