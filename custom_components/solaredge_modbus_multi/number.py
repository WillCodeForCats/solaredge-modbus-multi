import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, TIME_SECONDS, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadBuilder

from .const import DOMAIN, SunSpecNotImpl
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

    """ Power Control Options: Storage Control """
    if hub.option_storage_control is True:
        for battery in hub.batteries:
            for inverter in hub.inverters:
                if inverter.inverter_unit_id != battery.inverter_unit_id:
                    continue
                entities.append(
                    StorageACChargeLimit(inverter, config_entry, coordinator)
                )
                entities.append(
                    StorageBackupReserve(inverter, config_entry, coordinator)
                )
                entities.append(
                    StorageCommandTimeout(inverter, config_entry, coordinator)
                )
                entities.append(
                    StorageChargeLimit(inverter, battery, config_entry, coordinator)
                )
                entities.append(
                    StorageDischargeLimit(inverter, battery, config_entry, coordinator)
                )

    """ Power Control Options: Site Limit Control """
    if hub.option_export_control is True:
        for inverter in hub.inverters:
            entities.append(SolarEdgeSiteLimit(inverter, config_entry, coordinator))
            entities.append(
                SolarEdgeExternalProductionMax(inverter, config_entry, coordinator)
            )

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
        return self._platform.online

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class StorageACChargeLimit(SolarEdgeNumberBase):
    icon = "mdi:lightning-bolt"

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storage_ac_charge_limit"

    @property
    def name(self) -> str:
        return "AC Charge Limit"

    @property
    def available(self) -> bool:
        # Available for AC charge policies 2 & 3
        return self._platform.online and self._platform.decoded_storage[
            "ac_charge_policy"
        ] in [2, 3]

    @property
    def native_unit_of_measurement(self) -> str | None:
        # kWh in AC policy "Fixed Energy Limit", % in AC policy "Percent of Production"
        if self._platform.decoded_storage["ac_charge_policy"] == 2:
            return UnitOfEnergy.KILO_WATT_HOUR
        elif self._platform.decoded_storage["ac_charge_policy"] == 3:
            return PERCENTAGE
        else:
            return None

    @property
    def native_min_value(self) -> float:
        return 0

    @property
    def native_max_value(self) -> float:
        # 100MWh in AC policy "Fixed Energy Limit"
        if self._platform.decoded_storage["ac_charge_policy"] == 2:
            return 100000000
        elif self._platform.decoded_storage["ac_charge_policy"] == 3:
            return 100
        else:
            return 0

    @property
    def native_value(self) -> float | None:
        if (
            self._platform.decoded_storage is False
            or float_to_hex(self._platform.decoded_storage["ac_charge_limit"])
            == hex(SunSpecNotImpl.FLOAT32)
            or self._platform.decoded_storage["ac_charge_limit"] < 0
        ):
            return None

        return round(self._platform.decoded_storage["ac_charge_limit"], 3)

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
        builder.add_32bit_float(float(value))
        await self._platform.write_registers(
            address=57350, payload=builder.to_registers()
        )
        await self.async_update()


class StorageBackupReserve(SolarEdgeNumberBase):
    icon = "mdi:battery-positive"

    def __init__(self, inverter, config_entry, coordinator):
        super().__init__(inverter, config_entry, coordinator)
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storage_backup_reserve"

    @property
    def name(self) -> str:
        return "Backup Reserve"

    @property
    def native_value(self) -> float | None:
        if (
            self._platform.decoded_storage is False
            or float_to_hex(self._platform.decoded_storage["backup_reserve"])
            == hex(SunSpecNotImpl.FLOAT32)
            or self._platform.decoded_storage["backup_reserve"] < 0
            or self._platform.decoded_storage["backup_reserve"] > 100
        ):
            return None

        return round(self._platform.decoded_storage["backup_reserve"], 3)

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
        builder.add_32bit_float(float(value))
        await self._platform.write_registers(
            address=57352, payload=builder.to_registers()
        )
        await self.async_update()


class StorageCommandTimeout(SolarEdgeNumberBase):
    icon = "mdi:clock-end"

    def __init__(self, inverter, config_entry, coordinator):
        super().__init__(inverter, config_entry, coordinator)
        self._attr_native_min_value = 0
        self._attr_native_max_value = 86400  # 24h
        self._attr_native_unit_of_measurement = TIME_SECONDS

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storage_command_timeout"

    @property
    def name(self) -> str:
        return "Storage Command Timeout"

    @property
    def available(self) -> bool:
        # Available only in remote control mode
        return (
            self._platform.online
            and self._platform.decoded_storage["control_mode"] == 4
        )

    @property
    def native_value(self) -> int | None:
        if (
            self._platform.decoded_storage is False
            or self._platform.decoded_storage["command_timeout"]
            == SunSpecNotImpl.UINT32
            or self._platform.decoded_storage["command_timeout"] > 86400
        ):
            return None

        return int(self._platform.decoded_storage["command_timeout"])

    async def async_set_native_value(self, value: int) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
        builder.add_32bit_uint(int(value))
        await self._platform.write_registers(
            address=57355, payload=builder.to_registers()
        )
        await self.async_update()


class StorageChargeLimit(SolarEdgeNumberBase):
    icon = "mdi:lightning-bolt"

    def __init__(self, inverter, battery, config_entry, coordinator):
        super().__init__(inverter, config_entry, coordinator)
        self._battery = battery
        self._attr_native_min_value = 0
        self._attr_native_unit_of_measurement = UnitOfPower.WATT

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storage_charge_limit"

    @property
    def name(self) -> str:
        return "Storage Charge Limit"

    @property
    def available(self) -> bool:
        # Available only in remote control mode
        return (
            self._platform.online
            and self._platform.decoded_storage["control_mode"] == 4
        )

    @property
    def native_max_value(self) -> float:
        # Return batterys max charge power
        return self._battery.decoded_common["B_MaxChargePower"]

    @property
    def native_value(self) -> float | None:
        if (
            self._platform.decoded_storage is False
            or float_to_hex(self._platform.decoded_storage["charge_limit"])
            == hex(SunSpecNotImpl.FLOAT32)
            or self._platform.decoded_storage["charge_limit"] < 0
        ):
            return None

        return round(self._platform.decoded_storage["charge_limit"], 3)

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
        builder.add_32bit_float(float(value))
        await self._platform.write_registers(
            address=57358, payload=builder.to_registers()
        )
        await self.async_update()


class StorageDischargeLimit(SolarEdgeNumberBase):
    icon = "mdi:lightning-bolt"

    def __init__(self, inverter, battery, config_entry, coordinator):
        super().__init__(inverter, config_entry, coordinator)
        self._battery = battery
        self._attr_native_min_value = 0
        self._attr_native_unit_of_measurement = UnitOfPower.WATT

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storage_discharge_limit"

    @property
    def name(self) -> str:
        return "Storage Discharge Limit"

    @property
    def available(self) -> bool:
        # Available only in remote control mode
        return (
            self._platform.online
            and self._platform.decoded_storage["control_mode"] == 4
        )

    @property
    def native_max_value(self) -> float:
        # Return batterys max discharge power
        return self._battery.decoded_common["B_MaxDischargePower"]

    @property
    def native_value(self) -> float | None:
        if (
            self._platform.decoded_storage is False
            or float_to_hex(self._platform.decoded_storage["discharge_limit"])
            == hex(SunSpecNotImpl.FLOAT32)
            or self._platform.decoded_storage["discharge_limit"] < 0
        ):
            return None

        return round(self._platform.decoded_storage["discharge_limit"], 3)

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
        builder.add_32bit_float(float(value))
        await self._platform.write_registers(
            address=57360, payload=builder.to_registers()
        )
        await self.async_update()


class SolarEdgeSiteLimit(SolarEdgeNumberBase):
    icon = "mdi:lightning-bolt"

    def __init__(self, inverter, config_entry, coordinator):
        super().__init__(inverter, config_entry, coordinator)
        self._attr_native_min_value = 0
        self._attr_native_max_value = 1000000
        self._attr_native_unit_of_measurement = UnitOfPower.WATT

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_site_limit"

    @property
    def name(self) -> str:
        return "Site Limit"

    @property
    def available(self) -> bool:
        try:
            return self._platform.online and (
                (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 0) & 1
                or (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 1) & 1
                or (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 2) & 1
            )

        except KeyError:
            return False

    @property
    def native_value(self) -> float | None:
        try:
            if (
                float_to_hex(self._platform.decoded_model["E_Site_Limit"])
                == hex(SunSpecNotImpl.FLOAT32)
                or self._platform.decoded_model["E_Site_Limit"] < 0
            ):
                return None

            return round(self._platform.decoded_model["E_Site_Limit"], 1)

        except KeyError:
            return None

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
        builder.add_32bit_float(float(value))
        await self._platform.write_registers(
            address=57346, payload=builder.to_registers()
        )
        await self.async_update()


class SolarEdgeExternalProductionMax(SolarEdgeNumberBase):
    icon = "mdi:lightning-bolt"

    def __init__(self, inverter, config_entry, coordinator):
        super().__init__(inverter, config_entry, coordinator)
        self._attr_native_min_value = 0
        self._attr_native_max_value = 1000000
        self._attr_native_unit_of_measurement = UnitOfPower.WATT

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_external_production_max"

    @property
    def name(self) -> str:
        return "External Production Max"

    @property
    def available(self) -> bool:
        try:
            return (
                self._platform.online
                and (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 10) & 1
            )

        except KeyError:
            return False

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def native_value(self) -> float | None:
        try:
            if (
                float_to_hex(self._platform.decoded_model["Ext_Prod_Max"])
                == hex(SunSpecNotImpl.FLOAT32)
                or self._platform.decoded_model["Ext_Prod_Max"] < 0
            ):
                return None

            return round(self._platform.decoded_model["Ext_Prod_Max"], 1)

        except KeyError:
            return None

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
        builder.add_32bit_float(float(value))
        await self._platform.write_registers(
            address=57362, payload=builder.to_registers()
        )
        await self.async_update()
