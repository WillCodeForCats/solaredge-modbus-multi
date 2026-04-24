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
from pymodbus.client.mixin import ModbusClientMixin

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

    """ Dynamic Power Control """
    if hub.option_detect_extras:
        for inverter in hub.inverters:
            entities.append(
                SolarEdgeActivePowerLimitSet(inverter, config_entry, coordinator)
            )
            entities.append(SolarEdgeCosPhiSet(inverter, config_entry, coordinator))

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

    """ Power Control Block """
    if hub.option_detect_extras and inverter.advanced_power_control:
        for inverter in hub.inverters:
            entities.append(SolarEdgePowerReduce(inverter, config_entry, coordinator))
            entities.append(SolarEdgeCurrentLimit(inverter, config_entry, coordinator))

    if entities:
        async_add_entities(entities)


def get_key(d, search):
    for k, v in d.items():
        if v == search:
            return k
    return None


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

    @property
    def available(self) -> bool:
        return super().available and self._platform.online

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
        try:
            if (
                self._platform.decoded_storage_control is False
                or float_to_hex(
                    self._platform.decoded_storage_control["ac_charge_limit"]
                )
                == hex(SunSpecNotImpl.FLOAT32)
                or self._platform.decoded_storage_control["ac_charge_limit"] < 0
            ):
                return False

            # Available for AC charge policies 2 & 3
            return super().available and self._platform.decoded_storage_control[
                "ac_charge_policy"
            ] in [2, 3]

        except (TypeError, KeyError):
            return False

    @property
    def native_unit_of_measurement(self) -> str | None:
        # kWh in AC policy "Fixed Energy Limit", % in AC policy "Percent of Production"
        if self._platform.decoded_storage_control["ac_charge_policy"] == 2:
            return UnitOfEnergy.KILO_WATT_HOUR
        elif self._platform.decoded_storage_control["ac_charge_policy"] == 3:
            return PERCENTAGE
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
            payload=ModbusClientMixin.convert_to_registers(
                float(value),
                data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                word_order="little",
            ),
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
        try:
            if (
                self._platform.decoded_storage_control is False
                or float_to_hex(
                    self._platform.decoded_storage_control["backup_reserve"]
                )
                == hex(SunSpecNotImpl.FLOAT32)
                or self._platform.decoded_storage_control["backup_reserve"] < 0
                or self._platform.decoded_storage_control["backup_reserve"] > 100
            ):
                return False

            return super().available

        except (TypeError, KeyError):
            return False

    @property
    def native_value(self) -> int:
        return int(self._platform.decoded_storage_control["backup_reserve"])

    async def async_set_native_value(self, value: int) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write_registers(
            address=57352,
            payload=ModbusClientMixin.convert_to_registers(
                int(value),
                data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                word_order="little",
            ),
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

        except (TypeError, KeyError):
            return False

    @property
    def native_value(self) -> int:
        return int(self._platform.decoded_storage_control["command_timeout"])

    async def async_set_native_value(self, value: int) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write_registers(
            address=57355,
            payload=ModbusClientMixin.convert_to_registers(
                int(value),
                data_type=ModbusClientMixin.DATATYPE.UINT32,
                word_order="little",
            ),
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
        try:
            if (
                self._platform.decoded_storage_control is False
                or float_to_hex(self._platform.decoded_storage_control["charge_limit"])
                == hex(SunSpecNotImpl.FLOAT32)
                or self._platform.decoded_storage_control["charge_limit"] < 0
            ):
                return False

            # Available only in remote control mode
            return (
                super().available
                and self._platform.decoded_storage_control["control_mode"] == 4
            )

        except (TypeError, KeyError):
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
            payload=ModbusClientMixin.convert_to_registers(
                int(value),
                data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                word_order="little",
            ),
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
        try:
            if (
                self._platform.decoded_storage_control is False
                or float_to_hex(
                    self._platform.decoded_storage_control["discharge_limit"]
                )
                == hex(SunSpecNotImpl.FLOAT32)
                or self._platform.decoded_storage_control["discharge_limit"] < 0
            ):
                return False

            # Available only in remote control mode
            return (
                super().available
                and self._platform.decoded_storage_control["control_mode"] == 4
            )

        except (TypeError, KeyError):
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
            payload=ModbusClientMixin.convert_to_registers(
                int(value),
                data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                word_order="little",
            ),
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
        try:
            if float_to_hex(self._platform.decoded_model["E_Site_Limit"]) == hex(
                SunSpecNotImpl.FLOAT32
            ):
                return False

            return super().available and (
                (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 0) & 1
                or (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 1) & 1
                or (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 2) & 1
            )

        except (TypeError, KeyError):
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
            payload=ModbusClientMixin.convert_to_registers(
                int(value),
                data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                word_order="little",
            ),
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
        try:
            if (
                float_to_hex(self._platform.decoded_model["Ext_Prod_Max"])
                == hex(SunSpecNotImpl.FLOAT32)
                or self._platform.decoded_model["Ext_Prod_Max"] < 0
            ):
                return False

            return (
                super().available
                and (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 10) & 1
            )

        except (TypeError, KeyError):
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
            payload=ModbusClientMixin.convert_to_registers(
                int(value),
                data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                word_order="little",
            ),
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
        return self._platform.global_power_control

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

        except (TypeError, KeyError):
            return False

    @property
    def native_value(self) -> int:
        return self._platform.decoded_model["I_Power_Limit"]

    async def async_set_native_value(self, value: int) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write_registers(
            address=61441,
            payload=ModbusClientMixin.convert_to_registers(
                int(value),
                data_type=ModbusClientMixin.DATATYPE.UINT16,
                word_order="little",
            ),
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
        try:
            if (
                float_to_hex(self._platform.decoded_model["I_CosPhi"])
                == hex(SunSpecNotImpl.FLOAT32)
                or self._platform.decoded_model["I_CosPhi"] > 1.0
                or self._platform.decoded_model["I_CosPhi"] < -1.0
            ):
                return False

            return super().available

        except (TypeError, KeyError):
            return False

    @property
    def native_value(self) -> float:
        return round(self._platform.decoded_model["I_CosPhi"], 1)

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write_registers(
            address=61442,
            payload=ModbusClientMixin.convert_to_registers(
                float(value),
                data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                word_order="little",
            ),
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
        try:
            if (
                float_to_hex(self._platform.decoded_model["PowerReduce"])
                == hex(SunSpecNotImpl.FLOAT32)
                or self._platform.decoded_model["PowerReduce"] > 100
                or self._platform.decoded_model["PowerReduce"] < 0
            ):
                return False

            return super().available

        except (TypeError, KeyError):
            return False

    @property
    def native_value(self) -> int:
        return round(self._platform.decoded_model["PowerReduce"], 0)

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write_registers(
            address=61760,
            payload=ModbusClientMixin.convert_to_registers(
                float(value),
                data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                word_order="little",
            ),
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
        try:
            if (
                float_to_hex(self._platform.decoded_model["MaxCurrent"])
                == hex(SunSpecNotImpl.FLOAT32)
                or self._platform.decoded_model["MaxCurrent"] > 256
                or self._platform.decoded_model["MaxCurrent"] < 0
            ):
                return False

            return super().available

        except (TypeError, KeyError):
            return False

    @property
    def native_value(self) -> int:
        return round(self._platform.decoded_model["MaxCurrent"], 0)

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        await self._platform.write_registers(
            address=61838,
            payload=ModbusClientMixin.convert_to_registers(
                float(value),
                data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                word_order="little",
            ),
        )
        await self.async_update()
