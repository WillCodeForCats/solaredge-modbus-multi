from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfRatio,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from modbus_connection.encode import encode_float32, encode_uint16, encode_uint32

from . import SolarEdgeConfigEntry
from .const import BatteryLimit, SunSpecNotImpl
from .entity import SolarEdgeEntityBase
from .helpers import is_float32_not_impl

_LOGGER = logging.getLogger(__name__)

# Writes go to an inverter with a single Modbus session; one service call
# at a time per platform (the transport lock is the real guard).
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: SolarEdgeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    hub = config_entry.runtime_data.hub
    coordinator = config_entry.runtime_data.coordinator

    # Every entity on this platform writes to the inverter.
    if not hub.option_allow_hardware_writes:
        return

    entities = []

    for inverter in hub.inverters:
        """Dynamic Power Control"""
        if inverter.gpc_may_be_supported:
            entities.append(
                SolarEdgeActivePowerLimitSet(inverter, config_entry, coordinator)
            )
            entities.append(SolarEdgeCosPhiSet(inverter, config_entry, coordinator))

        """ Power Control Block """
        if inverter.apc_may_be_supported:
            entities.append(SolarEdgePowerReduce(inverter, config_entry, coordinator))
            entities.append(SolarEdgeCurrentLimit(inverter, config_entry, coordinator))

    """ Power Control Options: Storage Control """
    if hub.option_storage_control is True:
        for inverter in hub.inverters:
            if inverter.decoded_storage_control is False:
                continue
            entities.append(StorageACChargeLimit(inverter, config_entry, coordinator))
            entities.append(StorageBackupReserve(inverter, config_entry, coordinator))
            entities.append(StorageCommandTimeout(inverter, config_entry, coordinator))
            if inverter.has_battery is True:
                entities.append(StorageChargeLimit(inverter, config_entry, coordinator))
                entities.append(
                    StorageDischargeLimit(inverter, config_entry, coordinator)
                )

    """ Power Control Options: Site Limit Control """
    if hub.option_site_limit_control is True:
        for inverter in hub.inverters:
            entities.append(SolarEdgeSiteLimit(inverter, config_entry, coordinator))
            entities.append(
                SolarEdgeExternalProductionMax(inverter, config_entry, coordinator)
            )

    if entities:
        async_add_entities(entities)


class SolarEdgeNumberBase(SolarEdgeEntityBase, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    uid_suffix: str | None = None

    def __init__(self, platform, config_entry, coordinator) -> None:
        super().__init__(platform, config_entry, coordinator)
        if self.uid_suffix is not None:
            self._attr_unique_id = f"{platform.uid_base}_{self.uid_suffix}"


class StorageACChargeLimit(SolarEdgeNumberBase):
    _attr_icon = "mdi:lightning-bolt"
    _attr_name = "AC Charge Limit"
    uid_suffix = "storage_ac_charge_limit"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self._platform.has_battery is True

    @property
    def available(self) -> bool:
        try:
            if (
                self._platform.decoded_storage_control is False
                or is_float32_not_impl(
                    self._platform.decoded_storage_control["ac_charge_limit"]
                )
                or self._platform.decoded_storage_control["ac_charge_limit"] < 0
            ):
                return False

            # Available for AC charge policies 2 & 3
            return super().available and self._platform.decoded_storage_control[
                "ac_charge_policy"
            ] in [2, 3]

        except TypeError, KeyError:
            return False

    @property
    def native_unit_of_measurement(self) -> str | None:
        # kWh in AC policy "Fixed Energy Limit", % in AC policy "Percent of Production"
        if self._platform.decoded_storage_control["ac_charge_policy"] == 2:
            return UnitOfEnergy.KILO_WATT_HOUR
        elif self._platform.decoded_storage_control["ac_charge_policy"] == 3:
            return UnitOfRatio.PERCENTAGE
        else:
            return None

    @property
    def native_min_value(self) -> int:
        return 0

    @property
    def native_max_value(self) -> int:
        # 100MWh in AC policy "Fixed Energy Limit"
        if self._platform.decoded_storage_control["ac_charge_policy"] == 2:
            return 100000000
        elif self._platform.decoded_storage_control["ac_charge_policy"] == 3:
            return 100
        else:
            return 0

    @property
    def native_value(self) -> int:
        return int(self._platform.decoded_storage_control["ac_charge_limit"])

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write_registers(
            address=57350,
            payload=encode_float32(float(value), word_order="little"),
        )
        await self.async_update()


class StorageBackupReserve(SolarEdgeNumberBase):
    _attr_native_unit_of_measurement = UnitOfRatio.PERCENTAGE
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_icon = "mdi:battery-positive"
    _attr_name = "Backup Reserve"
    uid_suffix = "storage_backup_reserve"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self._platform.has_battery is True

    @property
    def available(self) -> bool:
        try:
            if (
                self._platform.decoded_storage_control is False
                or is_float32_not_impl(
                    self._platform.decoded_storage_control["backup_reserve"]
                )
                or self._platform.decoded_storage_control["backup_reserve"] < 0
                or self._platform.decoded_storage_control["backup_reserve"] > 100
            ):
                return False

            return super().available

        except TypeError, KeyError:
            return False

    @property
    def native_value(self) -> int:
        return int(self._platform.decoded_storage_control["backup_reserve"])

    async def async_set_native_value(self, value: int) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write_registers(
            address=57352,
            payload=encode_float32(int(value), word_order="little"),
        )
        await self.async_update()


class StorageCommandTimeout(SolarEdgeNumberBase):
    _attr_native_min_value = 0
    _attr_native_max_value = 86400  # 24h
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:clock-end"
    _attr_name = "Storage Command Timeout"
    uid_suffix = "storage_command_timeout"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self._platform.has_battery is True

    @property
    def available(self) -> bool:
        try:
            if (
                self._platform.decoded_storage_control is False
                or self._platform.decoded_storage_control["command_timeout"]
                == SunSpecNotImpl.UINT32
                or self._platform.decoded_storage_control["command_timeout"] > 86400
            ):
                return False

            # Available only in remote control mode
            return (
                super().available
                and self._platform.decoded_storage_control["control_mode"] == 4
            )

        except TypeError, KeyError:
            return False

    @property
    def native_value(self) -> int:
        return int(self._platform.decoded_storage_control["command_timeout"])

    async def async_set_native_value(self, value: int) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write_registers(
            address=57355,
            payload=encode_uint32(int(value), word_order="little"),
        )
        await self.async_update()


class StorageChargeLimit(SolarEdgeNumberBase):
    _attr_native_min_value = 0
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_icon = "mdi:lightning-bolt"
    _attr_name = "Storage Charge Limit"
    uid_suffix = "storage_charge_limit"

    @property
    def available(self) -> bool:
        try:
            if (
                self._platform.decoded_storage_control is False
                or is_float32_not_impl(
                    self._platform.decoded_storage_control["charge_limit"]
                )
                or self._platform.decoded_storage_control["charge_limit"] < 0
            ):
                return False

            # Available only in remote control mode
            return (
                super().available
                and self._platform.decoded_storage_control["control_mode"] == 4
            )

        except TypeError, KeyError:
            return False

    @property
    def native_max_value(self) -> int:
        return BatteryLimit.ChargeMax

    @property
    def native_value(self) -> int:
        return int(self._platform.decoded_storage_control["charge_limit"])

    async def async_set_native_value(self, value: int) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write_registers(
            address=57358,
            payload=encode_float32(int(value), word_order="little"),
        )
        await self.async_update()


class StorageDischargeLimit(SolarEdgeNumberBase):
    _attr_native_min_value = 0
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_icon = "mdi:lightning-bolt"
    _attr_name = "Storage Discharge Limit"
    uid_suffix = "storage_discharge_limit"

    @property
    def available(self) -> bool:
        try:
            if (
                self._platform.decoded_storage_control is False
                or is_float32_not_impl(
                    self._platform.decoded_storage_control["discharge_limit"]
                )
                or self._platform.decoded_storage_control["discharge_limit"] < 0
            ):
                return False

            # Available only in remote control mode
            return (
                super().available
                and self._platform.decoded_storage_control["control_mode"] == 4
            )

        except TypeError, KeyError:
            return False

    @property
    def native_max_value(self) -> int:
        return BatteryLimit.DischargeMax

    @property
    def native_value(self) -> int:
        return int(self._platform.decoded_storage_control["discharge_limit"])

    async def async_set_native_value(self, value: int) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write_registers(
            address=57360,
            payload=encode_float32(int(value), word_order="little"),
        )
        await self.async_update()


class SolarEdgeSiteLimit(SolarEdgeNumberBase):
    _attr_native_min_value = 0
    _attr_native_max_value = 1000000
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_icon = "mdi:lightning-bolt"
    _attr_name = "Site Limit"
    uid_suffix = "site_limit"

    @property
    def available(self) -> bool:
        try:
            if is_float32_not_impl(self._platform.decoded_model["E_Site_Limit"]):
                return False

            return super().available and (
                (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 0) & 1
                or (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 1) & 1
                or (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 2) & 1
            )

        except TypeError, KeyError:
            return False

    @property
    def native_value(self) -> int:
        if self._platform.decoded_model["E_Site_Limit"] < 0:
            return 0

        return int(self._platform.decoded_model["E_Site_Limit"])

    async def async_set_native_value(self, value: int) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write_registers(
            address=57346,
            payload=encode_float32(int(value), word_order="little"),
        )
        await self.async_update()


class SolarEdgeExternalProductionMax(SolarEdgeNumberBase):
    _attr_native_min_value = 0
    _attr_native_max_value = 1000000
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_icon = "mdi:lightning-bolt"
    _attr_name = "External Production Max"
    uid_suffix = "external_production_max"

    @property
    def available(self) -> bool:
        try:
            if (
                is_float32_not_impl(self._platform.decoded_model["Ext_Prod_Max"])
                or self._platform.decoded_model["Ext_Prod_Max"] < 0
            ):
                return False

            return (
                super().available
                and (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 10) & 1
            )

        except TypeError, KeyError:
            return False

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def native_value(self) -> int:
        return int(self._platform.decoded_model["Ext_Prod_Max"])

    async def async_set_native_value(self, value: int) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write_registers(
            address=57362,
            payload=encode_float32(int(value), word_order="little"),
        )
        await self.async_update()


class SolarEdgeActivePowerLimitSet(SolarEdgeNumberBase):
    """Global Dynamic Power Control: Set Inverter Active Power Limit"""

    _attr_native_unit_of_measurement = UnitOfRatio.PERCENTAGE
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_mode = "slider"
    _attr_icon = "mdi:percent"
    _attr_name = "Active Power Limit"
    uid_suffix = "active_power_limit_set"

    @property
    def entity_registry_enabled_default(self) -> bool:
        # `is not False`, not truthiness: a capability still undecided at setup
        # must register enabled, because this is only consulted once and a
        # later successful probe cannot re-enable a disabled registry entry.
        return self._platform.global_power_control is not False

    @property
    def available(self) -> bool:
        try:
            if (
                self._platform.decoded_model["I_Power_Limit"] == SunSpecNotImpl.UINT16
                or self._platform.decoded_model["I_Power_Limit"] > 100
                or self._platform.decoded_model["I_Power_Limit"] < 0
            ):
                return False

            return super().available

        except TypeError, KeyError:
            return False

    @property
    def native_value(self) -> int:
        return self._platform.decoded_model["I_Power_Limit"]

    async def async_set_native_value(self, value: int) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write_registers(
            address=61441,
            payload=encode_uint16(int(value)),
        )
        await self.async_update()


class SolarEdgeCosPhiSet(SolarEdgeNumberBase):
    """Global Dynamic Power Control: Set Inverter CosPhi"""

    _attr_native_min_value = -1.0
    _attr_native_max_value = 1.0
    _attr_native_step = 0.1
    _attr_mode = "slider"
    _attr_icon = "mdi:angle-acute"
    _attr_name = "CosPhi"
    uid_suffix = "cosphi_set"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def available(self) -> bool:
        try:
            if (
                is_float32_not_impl(self._platform.decoded_model["I_CosPhi"])
                or self._platform.decoded_model["I_CosPhi"] > 1.0
                or self._platform.decoded_model["I_CosPhi"] < -1.0
            ):
                return False

            return super().available

        except TypeError, KeyError:
            return False

    @property
    def native_value(self) -> float:
        return round(self._platform.decoded_model["I_CosPhi"], 1)

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write_registers(
            address=61442,
            payload=encode_float32(float(value), word_order="little"),
        )
        await self.async_update()


class SolarEdgePowerReduce(SolarEdgeNumberBase):
    """Limits the inverter's maximum output power from 0-100%"""

    _attr_native_unit_of_measurement = UnitOfRatio.PERCENTAGE
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_mode = "slider"
    _attr_icon = "mdi:percent"
    _attr_name = "Power Reduce"
    uid_suffix = "power_reduce"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def available(self) -> bool:
        try:
            if (
                is_float32_not_impl(self._platform.decoded_model["PowerReduce"])
                or self._platform.decoded_model["PowerReduce"] > 100
                or self._platform.decoded_model["PowerReduce"] < 0
            ):
                return False

            return super().available

        except TypeError, KeyError:
            return False

    @property
    def native_value(self) -> int:
        return round(self._platform.decoded_model["PowerReduce"], 0)

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write_registers(
            address=61760,
            payload=encode_float32(float(value), word_order="little"),
        )
        await self.async_update()


class SolarEdgeCurrentLimit(SolarEdgeNumberBase):
    """Limits the inverter's maximum output current."""

    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_native_min_value = 0
    _attr_native_max_value = 256
    _attr_icon = "mdi:current-ac"
    _attr_name = "Current Limit"
    uid_suffix = "max_current"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def available(self) -> bool:
        try:
            if (
                is_float32_not_impl(self._platform.decoded_model["MaxCurrent"])
                or self._platform.decoded_model["MaxCurrent"] > 256
                or self._platform.decoded_model["MaxCurrent"] < 0
            ):
                return False

            return super().available

        except TypeError, KeyError:
            return False

    @property
    def native_value(self) -> int:
        return round(self._platform.decoded_model["MaxCurrent"], 0)

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write_registers(
            address=61838,
            payload=encode_float32(float(value), word_order="little"),
        )
        await self.async_update()
