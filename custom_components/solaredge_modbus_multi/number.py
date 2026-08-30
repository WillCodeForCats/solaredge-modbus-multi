from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, BatteryLimit, SunSpecNotImpl
from .helpers import float_to_hex

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
        """Dynamic Power Control and Power Control Block"""
        if hub.option_detect_extras:
            entities.append(
                SolarEdgeActivePowerLimitSet(inverter, config_entry, coordinator)
            )
            entities.append(SolarEdgeCosPhiSet(inverter, config_entry, coordinator))
            entities.append(SolarEdgePowerReduce(inverter, config_entry, coordinator))
            entities.append(SolarEdgeCurrentLimit(inverter, config_entry, coordinator))

        """ Power Control Options: Storage Control """
        if hub.option_storage_control:
            entities.append(StorageACChargeLimit(inverter, config_entry, coordinator))
            entities.append(StorageBackupReserve(inverter, config_entry, coordinator))
            entities.append(StorageCommandTimeout(inverter, config_entry, coordinator))
            entities.append(StorageChargeLimit(inverter, config_entry, coordinator))
            entities.append(StorageDischargeLimit(inverter, config_entry, coordinator))

        """ Power Control Options: Site Limit Control """
        if hub.option_site_limit_control:
            entities.append(SolarEdgeSiteLimit(inverter, config_entry, coordinator))
            entities.append(
                SolarEdgeExternalProductionMax(inverter, config_entry, coordinator)
            )

    if entities:
        async_add_entities(entities)


class SolarEdgeNumberBase(CoordinatorEntity, NumberEntity):
    should_poll = False
    _attr_has_entity_name = True
    entity_category = EntityCategory.CONFIG

    def __init__(self, platform, config_entry, coordinator):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        """Initialize the number."""
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

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class StorageACChargeLimit(SolarEdgeNumberBase):
    icon = "mdi:lightning-bolt"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storage_ac_charge_limit"

    @property
    def name(self) -> str:
        return "AC Charge Limit"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self._platform.has_battery is True

    @property
    def available(self) -> bool:
        ac_charge_limit = self._platform.storage_control_data.ac_charge_limit
        return (
            super().available
            and self._platform.has_storage_control
            and ac_charge_limit is not None
            and float_to_hex(ac_charge_limit) != hex(SunSpecNotImpl.FLOAT32)
            and ac_charge_limit >= 0
            # Available for AC charge policies 2 & 3
            and self._platform.storage_control_data.ac_charge_policy in [2, 3]
        )

    @property
    def native_unit_of_measurement(self) -> str | None:
        # kWh in AC policy "Fixed Energy Limit", % in AC policy "Percent of Production"
        if self._platform.storage_control_data.ac_charge_policy == 2:
            return UnitOfEnergy.KILO_WATT_HOUR
        elif self._platform.storage_control_data.ac_charge_policy == 3:
            return PERCENTAGE
        else:
            return None

    @property
    def native_min_value(self) -> int:
        return 0

    @property
    def native_max_value(self) -> int:
        # 100MWh in AC policy "Fixed Energy Limit"
        if self._platform.storage_control_data.ac_charge_policy == 2:
            return 100000000
        elif self._platform.storage_control_data.ac_charge_policy == 3:
            return 100
        else:
            return 0

    @property
    def native_value(self) -> int:
        return int(self._platform.storage_control_data.ac_charge_limit)

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write(
            self._platform.storage_control_data, "ac_charge_limit", float(value)
        )
        await self.async_update()


class StorageBackupReserve(SolarEdgeNumberBase):
    native_unit_of_measurement = PERCENTAGE
    native_min_value = 0
    native_max_value = 100
    icon = "mdi:battery-positive"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storage_backup_reserve"

    @property
    def name(self) -> str:
        return "Backup Reserve"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self._platform.has_battery is True

    @property
    def available(self) -> bool:
        backup_reserve = self._platform.storage_control_data.backup_reserve
        return (
            super().available
            and self._platform.has_storage_control
            and backup_reserve is not None
            and float_to_hex(backup_reserve) != hex(SunSpecNotImpl.FLOAT32)
            and 0 <= backup_reserve <= 100
        )

    @property
    def native_value(self) -> int:
        return int(self._platform.storage_control_data.backup_reserve)

    async def async_set_native_value(self, value: int) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write(
            self._platform.storage_control_data, "backup_reserve", int(value)
        )
        await self.async_update()


class StorageCommandTimeout(SolarEdgeNumberBase):
    native_min_value = 0
    native_max_value = 86400  # 24h
    native_unit_of_measurement = UnitOfTime.SECONDS
    icon = "mdi:clock-end"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storage_command_timeout"

    @property
    def name(self) -> str:
        return "Storage Command Timeout"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self._platform.has_battery is True

    @property
    def available(self) -> bool:
        command_timeout = self._platform.storage_control_data.command_timeout
        return (
            super().available
            and self._platform.has_storage_control
            and command_timeout is not None
            and command_timeout != SunSpecNotImpl.UINT32
            and command_timeout <= 86400
            # Available only in remote control mode
            and self._platform.storage_control_data.control_mode == 4
        )

    @property
    def native_value(self) -> int:
        return int(self._platform.storage_control_data.command_timeout)

    async def async_set_native_value(self, value: int) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write(
            self._platform.storage_control_data, "command_timeout", int(value)
        )
        await self.async_update()


class StorageChargeLimit(SolarEdgeNumberBase):
    native_min_value = 0
    native_step = 1.0
    native_unit_of_measurement = UnitOfPower.WATT
    icon = "mdi:lightning-bolt"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storage_charge_limit"

    @property
    def name(self) -> str:
        return "Storage Charge Limit"

    @property
    def available(self) -> bool:
        charge_limit = self._platform.storage_control_data.charge_limit
        return (
            super().available
            and self._platform.has_storage_control
            and charge_limit is not None
            and float_to_hex(charge_limit) != hex(SunSpecNotImpl.FLOAT32)
            and charge_limit >= 0
            # Available only in remote control mode
            and self._platform.storage_control_data.control_mode == 4
        )

    @property
    def native_max_value(self) -> int:
        return BatteryLimit.ChargeMax

    @property
    def native_value(self) -> int:
        return int(self._platform.storage_control_data.charge_limit)

    async def async_set_native_value(self, value: int) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write(
            self._platform.storage_control_data, "charge_limit", int(value)
        )
        await self.async_update()


class StorageDischargeLimit(SolarEdgeNumberBase):
    native_min_value = 0
    native_step = 1.0
    native_unit_of_measurement = UnitOfPower.WATT
    icon = "mdi:lightning-bolt"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storage_discharge_limit"

    @property
    def name(self) -> str:
        return "Storage Discharge Limit"

    @property
    def available(self) -> bool:
        discharge_limit = self._platform.storage_control_data.discharge_limit
        return (
            super().available
            and self._platform.has_storage_control
            and discharge_limit is not None
            and float_to_hex(discharge_limit) != hex(SunSpecNotImpl.FLOAT32)
            and discharge_limit >= 0
            # Available only in remote control mode
            and self._platform.storage_control_data.control_mode == 4
        )

    @property
    def native_max_value(self) -> int:
        return BatteryLimit.DischargeMax

    @property
    def native_value(self) -> int:
        return int(self._platform.storage_control_data.discharge_limit)

    async def async_set_native_value(self, value: int) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write(
            self._platform.storage_control_data, "discharge_limit", int(value)
        )
        await self.async_update()


class SolarEdgeSiteLimit(SolarEdgeNumberBase):
    native_min_value = 0
    native_max_value = 1000000
    native_unit_of_measurement = UnitOfPower.WATT
    icon = "mdi:lightning-bolt"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_site_limit"

    @property
    def name(self) -> str:
        return "Site Limit"

    @property
    def available(self) -> bool:
        e_site_limit = self._platform.site_limit_control_data.E_Site_Limit
        e_lim_ctl_mode = self._platform.site_limit_control_data.E_Lim_Ctl_Mode
        return (
            super().available
            and self._platform.has_site_limit_control
            and e_site_limit is not None
            and float_to_hex(e_site_limit) != hex(SunSpecNotImpl.FLOAT32)
            and e_lim_ctl_mode is not None
            and (
                (e_lim_ctl_mode >> 0) & 1
                or (e_lim_ctl_mode >> 1) & 1
                or (e_lim_ctl_mode >> 2) & 1
            )
        )

    @property
    def native_value(self) -> int:
        if self._platform.site_limit_control_data.E_Site_Limit < 0:
            return 0

        return int(self._platform.site_limit_control_data.E_Site_Limit)

    async def async_set_native_value(self, value: int) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write(
            self._platform.site_limit_control_data, "E_Site_Limit", int(value)
        )
        await self.async_update()


class SolarEdgeExternalProductionMax(SolarEdgeNumberBase):
    native_min_value = 0
    native_max_value = 1000000
    native_unit_of_measurement = UnitOfPower.WATT
    icon = "mdi:lightning-bolt"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_external_production_max"

    @property
    def name(self) -> str:
        return "External Production Max"

    @property
    def available(self) -> bool:
        ext_prod_max = self._platform.site_limit_control_data.Ext_Prod_Max
        e_lim_ctl_mode = self._platform.site_limit_control_data.E_Lim_Ctl_Mode
        return (
            super().available
            and self._platform.has_site_limit_control
            and ext_prod_max is not None
            and float_to_hex(ext_prod_max) != hex(SunSpecNotImpl.FLOAT32)
            and ext_prod_max >= 0
            and e_lim_ctl_mode is not None
            and (e_lim_ctl_mode >> 10) & 1
        )

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def native_value(self) -> int:
        return int(self._platform.site_limit_control_data.Ext_Prod_Max)

    async def async_set_native_value(self, value: int) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write(
            self._platform.site_limit_control_data, "Ext_Prod_Max", int(value)
        )
        await self.async_update()


class SolarEdgeActivePowerLimitSet(SolarEdgeNumberBase):
    """Global Dynamic Power Control: Set Inverter Active Power Limit"""

    native_unit_of_measurement = PERCENTAGE
    native_min_value = 0
    native_max_value = 100
    mode = "slider"
    icon = "mdi:percent"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_active_power_limit_set"

    @property
    def name(self) -> str:
        return "Active Power Limit"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self._platform.has_global_power_control is True

    @property
    def available(self) -> bool:
        i_power_limit = self._platform.global_power_control_data.I_Power_Limit
        return (
            super().available
            and self._platform.has_global_power_control
            and i_power_limit is not None
            and i_power_limit != SunSpecNotImpl.UINT16
            and 0 <= i_power_limit <= 100
        )

    @property
    def native_value(self) -> int:
        return self._platform.global_power_control_data.I_Power_Limit

    async def async_set_native_value(self, value: int) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write(
            self._platform.global_power_control_data,
            "I_Power_Limit",
            int(value),
            count_write=False,
        )
        await self.async_update()


class SolarEdgeCosPhiSet(SolarEdgeNumberBase):
    """Global Dynamic Power Control: Set Inverter CosPhi"""

    native_min_value = -1.0
    native_max_value = 1.0
    native_step = 0.1
    mode = "slider"
    icon = "mdi:angle-acute"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_cosphi_set"

    @property
    def name(self) -> str:
        return "CosPhi"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def available(self) -> bool:
        i_cosphi = self._platform.global_power_control_data.I_CosPhi
        return (
            super().available
            and self._platform.has_global_power_control
            and i_cosphi is not None
            and float_to_hex(i_cosphi) != hex(SunSpecNotImpl.FLOAT32)
            and -1.0 <= i_cosphi <= 1.0
        )

    @property
    def native_value(self) -> float:
        return round(self._platform.global_power_control_data.I_CosPhi, 1)

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write(
            self._platform.global_power_control_data,
            "I_CosPhi",
            float(value),
            count_write=False,
        )
        await self.async_update()


class SolarEdgePowerReduce(SolarEdgeNumberBase):
    """Limits the inverter's maximum output power from 0-100%"""

    native_unit_of_measurement = PERCENTAGE
    native_min_value = 0
    native_max_value = 100
    mode = "slider"
    icon = "mdi:percent"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_power_reduce"

    @property
    def name(self) -> str:
        return "Power Reduce"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def available(self) -> bool:
        power_reduce = self._platform.advanced_power_control_data.PowerReduce
        return (
            super().available
            and self._platform.has_advanced_power_control
            and power_reduce is not None
            and float_to_hex(power_reduce) != hex(SunSpecNotImpl.FLOAT32)
            and 0 <= power_reduce <= 100
        )

    @property
    def native_value(self) -> int:
        return round(self._platform.advanced_power_control_data.PowerReduce, 0)

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write(
            self._platform.advanced_power_control_data, "PowerReduce", float(value)
        )
        await self.async_update()


class SolarEdgeCurrentLimit(SolarEdgeNumberBase):
    """Limits the inverter's maximum output current."""

    native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    native_min_value = 0
    native_max_value = 256
    icon = "mdi:current-ac"

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_max_current"

    @property
    def name(self) -> str:
        return "Current Limit"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def available(self) -> bool:
        max_current = self._platform.advanced_power_control_data.MaxCurrent
        return (
            super().available
            and self._platform.has_advanced_power_control
            and max_current is not None
            and float_to_hex(max_current) != hex(SunSpecNotImpl.FLOAT32)
            and 0 <= max_current <= 256
        )

    @property
    def native_value(self) -> int:
        return round(self._platform.advanced_power_control_data.MaxCurrent, 0)

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write(
            self._platform.advanced_power_control_data, "MaxCurrent", float(value)
        )
        await self.async_update()
