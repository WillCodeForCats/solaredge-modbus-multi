import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    LIMIT_CONTROL,
    LIMIT_CONTROL_MODE,
    STORAGE_AC_CHARGE_POLICY,
    STORAGE_CONTROL_MODE,
    STORAGE_MODE,
    SunSpecNotImpl,
)

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
                entities.append(StorageControlMode(inverter, config_entry, coordinator))
                entities.append(
                    StorageACChargePolicy(inverter, config_entry, coordinator)
                )
                entities.append(StorageDefaultMode(inverter, config_entry, coordinator))
                entities.append(StorageCommandMode(inverter, config_entry, coordinator))

    """ Power Control Options: Site Limit Control """
    if hub.option_export_control is True:
        for inverter in hub.inverters:
            entities.append(
                SolaredgeLimitControlMode(inverter, config_entry, coordinator)
            )
            entities.append(SolaredgeLimitControl(inverter, config_entry, coordinator))

    if entities:
        async_add_entities(entities)


def get_key(d, search):
    for k, v in d.items():
        if v == search:
            return k
    return None


class SolarEdgeSelectBase(CoordinatorEntity, SelectEntity):
    should_poll = False
    _attr_has_entity_name = True
    entity_category = EntityCategory.CONFIG

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


class StorageControlMode(SolarEdgeSelectBase):
    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        self._options = STORAGE_CONTROL_MODE
        self._attr_options = list(self._options.values())

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storage_control_mode"

    @property
    def name(self) -> str:
        return "Storage Control Mode"

    @property
    def current_option(self) -> str:
        return self._options[self._platform.decoded_storage["control_mode"]]

    async def async_select_option(self, option: str) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {option}")
        new_mode = get_key(self._options, option)
        await self._platform.write_registers(address=57348, payload=new_mode)
        await self.async_update()


class StorageACChargePolicy(SolarEdgeSelectBase):
    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        self._options = STORAGE_AC_CHARGE_POLICY
        self._attr_options = list(self._options.values())

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_ac_charge_policy"

    @property
    def name(self) -> str:
        return "AC Charge Policy"

    @property
    def current_option(self) -> str | None:
        if (
            self._platform.decoded_storage is False
            or self._platform.decoded_storage["ac_charge_policy"]
            == SunSpecNotImpl.UINT16
            or self._platform.decoded_storage["ac_charge_policy"] not in self._options
        ):
            return None

        return self._options[self._platform.decoded_storage["ac_charge_policy"]]

    async def async_select_option(self, option: str) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {option}")
        new_mode = get_key(self._options, option)
        await self._platform.write_registers(address=57349, payload=new_mode)
        await self.async_update()


class StorageDefaultMode(SolarEdgeSelectBase):
    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        self._options = STORAGE_MODE
        self._attr_options = list(self._options.values())

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storage_default_mode"

    @property
    def name(self) -> str:
        return "Storage Default Mode"

    @property
    def available(self) -> bool:
        # Available only in remote control mode
        return (
            self._platform.online
            and self._platform.decoded_storage["control_mode"] == 4
        )

    @property
    def current_option(self) -> str | None:
        if (
            self._platform.decoded_storage is False
            or self._platform.decoded_storage["default_mode"] == SunSpecNotImpl.UINT16
            or self._platform.decoded_storage["default_mode"] not in self._options
        ):
            return None

        return self._options[self._platform.decoded_storage["default_mode"]]

    async def async_select_option(self, option: str) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {option}")
        new_mode = get_key(self._options, option)
        await self._platform.write_registers(address=57354, payload=new_mode)
        await self.async_update()


class StorageCommandMode(SolarEdgeSelectBase):
    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        self._options = STORAGE_MODE
        self._attr_options = list(self._options.values())

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storage_command_mode"

    @property
    def name(self) -> str:
        return "Storage Command Mode"

    @property
    def available(self) -> bool:
        # Available only in remote control mode
        return (
            self._platform.online
            and self._platform.decoded_storage["control_mode"] == 4
        )

    @property
    def current_option(self) -> str:
        if (
            self._platform.decoded_storage is False
            or self._platform.decoded_storage["command_mode"] == SunSpecNotImpl.UINT16
            or self._platform.decoded_storage["command_mode"] not in self._options
        ):
            return None

        try:
            return self._options[self._platform.decoded_storage["command_mode"]]
        except KeyError:
            return STATE_UNKNOWN

    async def async_select_option(self, option: str) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {option}")
        new_mode = get_key(self._options, option)
        await self._platform.write_registers(address=57357, payload=new_mode)
        await self.async_update()


class SolaredgeLimitControlMode(SolarEdgeSelectBase):
    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        self._options = LIMIT_CONTROL_MODE
        self._attr_options = list(self._options.values())

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_limit_control_mode"

    @property
    def name(self) -> str:
        return "Limit Control Mode"

    @property
    def current_option(self) -> str | None:
        try:
            if self._platform.decoded_model["E_Lim_Ctl_Mode"] == SunSpecNotImpl.UINT16:
                return None

            if (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 0) & 1:
                return self._options[0]

            elif (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 1) & 1:
                return self._options[1]

            elif (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 2) & 1:
                return self._options[2]

            else:
                return self._options[None]

        except KeyError:
            return None

    async def async_select_option(self, option: str) -> None:
        set_bits = int(self._platform.decoded_model["E_Lim_Ctl_Mode"])
        new_mode = get_key(self._options, option)

        set_bits = set_bits & ~(1 << 0)
        set_bits = set_bits & ~(1 << 1)
        set_bits = set_bits & ~(1 << 2)

        if new_mode is not None:
            set_bits = set_bits | (1 << int(new_mode))

        _LOGGER.debug(f"set {self.unique_id} bits {set_bits:016b}")
        await self._platform.write_registers(address=57344, payload=set_bits)
        await self.async_update()


class SolaredgeLimitControl(SolarEdgeSelectBase):
    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        self._options = LIMIT_CONTROL
        self._attr_options = list(self._options.values())

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_limit_control"

    @property
    def name(self) -> str:
        return "Limit Control"

    @property
    def current_option(self) -> str | None:
        try:
            if self._platform.decoded_model["E_Lim_Ctl"] == SunSpecNotImpl.UINT16:
                return None

            return self._options[self._platform.decoded_model["E_Lim_Ctl"]]

        except KeyError:
            return None

    async def async_select_option(self, option: str) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {option}")
        new_mode = get_key(self._options, option)
        await self._platform.write_registers(address=57345, payload=new_mode)
        await self.async_update()
