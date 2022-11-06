import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ENERGY_KILO_WATT_HOUR,
    PERCENTAGE,
    POWER_WATT,
    TIME_SECONDS,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadBuilder

from .const import DOMAIN

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
    if hub.option_storedge_control is True:
        for battery in hub.batteries:
            for inverter in hub.inverters:
                if inverter.inverter_unit_id != battery.inverter_unit_id:
                    continue
                entities.append(
                    StoredgeACChargeLimit(inverter, config_entry, coordinator)
                )
                entities.append(
                    StoredgeBackupReserved(inverter, config_entry, coordinator)
                )
                entities.append(
                    StoredgeCommandTimeout(inverter, config_entry, coordinator)
                )
                entities.append(
                    StoredgeChargeLimit(inverter, battery, config_entry, coordinator)
                )
                entities.append(
                    StoredgeDischargeLimit(inverter, battery, config_entry, coordinator)
                )

    """ Power Control Options: Site Limit Control """
    if hub.option_export_control is True:
        for inverter in hub.inverters:
            entities.append(
                SolarEdgeExportSiteLimit(inverter, config_entry, coordinator)
            )
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


class StoredgeACChargeLimit(SolarEdgeNumberBase):
    icon = "mdi:lightning-bolt"

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storedge_ac_charge_limit"

    @property
    def name(self) -> str:
        return "Storedge AC Charge Limit"

    @property
    def available(self) -> bool:
        # Available for AC charge policies 2 & 3
        return self._platform.online and self._platform.decoded_storedge[
            "ac_charge_policy"
        ] in [2, 3]

    @property
    def native_unit_of_measurement(self) -> str | None:
        # kWh in AC policy "Fixed Energy Limit", % in AC policy "Percent of Production"
        if self._platform.decoded_storedge["ac_charge_policy"] == 2:
            return ENERGY_KILO_WATT_HOUR
        elif self._platform.decoded_storedge["ac_charge_policy"] == 3:
            return PERCENTAGE
        else:
            return None

    @property
    def native_min_value(self) -> float:
        return 0

    @property
    def native_max_value(self) -> float:
        # 100MWh in AC policy "Fixed Energy Limit"
        if self._platform.decoded_storedge["ac_charge_policy"] == 2:
            return 100000000
        elif self._platform.decoded_storedge["ac_charge_policy"] == 3:
            return 100
        else:
            return 0

    @property
    def native_value(self) -> float | None:
        return round(self._platform.decoded_storedge["ac_charge_limit"], 3)

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
        builder.add_32bit_float(float(value))
        await self._platform.write_registers(
            address=57350, payload=builder.to_registers()
        )
        await self.async_update()


class StoredgeBackupReserved(SolarEdgeNumberBase):
    icon = "mdi:battery-positive"

    def __init__(self, inverter, config_entry, coordinator):
        super().__init__(inverter, config_entry, coordinator)
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storedge_backup_reserved"

    @property
    def name(self) -> str:
        return "Storedge Backup Reserved"

    @property
    def native_value(self) -> float | None:
        return round(self._platform.decoded_storedge["backup_reserved"], 3)

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
        builder.add_32bit_float(float(value))
        await self._platform.write_registers(
            address=57352, payload=builder.to_registers()
        )
        await self.async_update()


class StoredgeCommandTimeout(SolarEdgeNumberBase):
    icon = "mdi:clock-end"

    def __init__(self, inverter, config_entry, coordinator):
        super().__init__(inverter, config_entry, coordinator)
        self._attr_native_min_value = 0
        self._attr_native_max_value = 86400  # 24h
        self._attr_native_unit_of_measurement = TIME_SECONDS

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storedge_remote_command_timeout"

    @property
    def name(self) -> str:
        return "Storedge Remote Command Timeout"

    @property
    def available(self) -> bool:
        # Available only in remote control mode
        return (
            self._platform.online
            and self._platform.decoded_storedge["control_mode"] == 4
        )

    @property
    def native_value(self) -> int | None:
        return int(self._platform.decoded_storedge["remote_command_timeout"])

    async def async_set_native_value(self, value: int) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
        builder.add_32bit_uint(int(value))
        await self._platform.write_registers(
            address=57355, payload=builder.to_registers()
        )
        await self.async_update()


class StoredgeChargeLimit(SolarEdgeNumberBase):
    icon = "mdi:lightning-bolt"

    def __init__(self, inverter, battery, config_entry, coordinator):
        super().__init__(inverter, config_entry, coordinator)
        self._battery = battery
        self._attr_native_min_value = 0
        self._attr_native_unit_of_measurement = POWER_WATT

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storedge_remote_charge_limit"

    @property
    def name(self) -> str:
        return "Storedge Remote Charge Limit"

    @property
    def available(self) -> bool:
        # Available only in remote control mode
        return (
            self._platform.online
            and self._platform.decoded_storedge["control_mode"] == 4
        )

    @property
    def native_max_value(self) -> float:
        # Return batterys max charge power
        return self._battery.decoded_common["B_MaxChargePower"]

    @property
    def native_value(self) -> float | None:
        return round(self._platform.decoded_storedge["remote_charge_limit"], 3)

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
        builder.add_32bit_float(float(value))
        await self._platform.write_registers(
            address=57358, payload=builder.to_registers()
        )
        await self.async_update()


class StoredgeDischargeLimit(SolarEdgeNumberBase):
    icon = "mdi:lightning-bolt"

    def __init__(self, inverter, battery, config_entry, coordinator):
        super().__init__(inverter, config_entry, coordinator)
        self._battery = battery
        self._attr_native_min_value = 0
        self._attr_native_unit_of_measurement = POWER_WATT

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storedge_remote_discharge_limit"

    @property
    def name(self) -> str:
        return "Storedge Remote Discharge Limit"

    @property
    def available(self) -> bool:
        # Available only in remote control mode
        return (
            self._platform.online
            and self._platform.decoded_storedge["control_mode"] == 4
        )

    @property
    def native_max_value(self) -> float:
        # Return batterys max discharge power
        return self._battery.decoded_common["B_MaxDischargePower"]

    @property
    def native_value(self) -> float | None:
        return round(self._platform.decoded_storedge["remote_discharge_limit"], 3)

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
        builder.add_32bit_float(float(value))
        await self._platform.write_registers(
            address=57360, payload=builder.to_registers()
        )
        await self.async_update()


class SolarEdgeExportSiteLimit(SolarEdgeNumberBase):
    icon = "mdi:transmission-tower-import"

    def __init__(self, inverter, config_entry, coordinator):
        super().__init__(inverter, config_entry, coordinator)
        self._attr_native_min_value = 0
        self._attr_native_max_value = 1000000
        self._attr_native_unit_of_measurement = POWER_WATT

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_site_limit"

    @property
    def name(self) -> str:
        return "Site Limit"

    @property
    def native_value(self) -> float | None:
        return round(self._platform.decoded_model["E_Site_Limit"], 1)

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
        self._attr_native_unit_of_measurement = POWER_WATT

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_external_production_max"

    @property
    def name(self) -> str:
        return "External Production Max"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def native_value(self) -> float | None:
        return round(self._platform.decoded_model["Ext_Prod_Max"], 1)

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {value}")
        builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
        builder.add_32bit_float(float(value))
        await self._platform.write_registers(
            address=57362, payload=builder.to_registers()
        )
        await self.async_update()
