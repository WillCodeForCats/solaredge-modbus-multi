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
    STOREDGE_AC_CHARGE_POLICY,
    STOREDGE_CONTROL_MODE,
    STOREDGE_MODE,
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

    """ Advanced Power Control: StorEdge Control """
    if hub.option_storedge_control is True:
        for battery in hub.batteries:
            for inverter in hub.inverters:
                if inverter.inverter_unit_id != battery.inverter_unit_id:
                    continue
                entities.append(
                    StoredgeControlMode(inverter, config_entry, coordinator)
                )
                entities.append(
                    StoredgeACChargePolicy(inverter, config_entry, coordinator)
                )
                entities.append(
                    StoredgeDefaultMode(inverter, config_entry, coordinator)
                )
                entities.append(StoredgeRemoteMode(inverter, config_entry, coordinator))

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


class StoredgeControlMode(SolarEdgeSelectBase):
    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        self._options = STOREDGE_CONTROL_MODE
        self._attr_options = list(self._options.values())

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storedge_control_mode"

    @property
    def name(self) -> str:
        return "Storedge Control Mode"

    @property
    def current_option(self) -> str:
        return self._options[self._platform.decoded_storedge["control_mode"]]

    async def async_select_option(self, option: str) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {option}")
        new_mode = get_key(self._options, option)
        await self._platform.write_registers(address=57348, payload=new_mode)
        await self.async_update()


class StoredgeACChargePolicy(SolarEdgeSelectBase):
    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        self._options = STOREDGE_AC_CHARGE_POLICY
        self._attr_options = list(self._options.values())

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storedge_ac_charge_policy"

    @property
    def name(self) -> str:
        return "AC Charge Policy"

    @property
    def current_option(self) -> str:
        return self._options[self._platform.decoded_storedge["ac_charge_policy"]]

    async def async_select_option(self, option: str) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {option}")
        new_mode = get_key(self._options, option)
        await self._platform.write_registers(address=57349, payload=new_mode)
        await self.async_update()


class StoredgeDefaultMode(SolarEdgeSelectBase):
    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        self._options = STOREDGE_MODE
        self._attr_options = list(self._options.values())

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storedge_default_mode"

    @property
    def name(self) -> str:
        return "Storedge Default Mode"

    @property
    def available(self) -> bool:
        # Available only in remote control mode
        return (
            self._platform.online
            and self._platform.decoded_storedge["control_mode"] == 4
        )

    @property
    def current_option(self) -> str:
        return self._options[self._platform.decoded_storedge["default_mode"]]

    async def async_select_option(self, option: str) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {option}")
        new_mode = get_key(self._options, option)
        await self._platform.write_registers(address=57354, payload=new_mode)
        await self.async_update()


class StoredgeRemoteMode(SolarEdgeSelectBase):
    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        self._options = STOREDGE_MODE
        self._attr_options = list(self._options.values())

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_storedge_remote_mode"

    @property
    def name(self) -> str:
        return "Storedge Remote Mode"

    @property
    def available(self) -> bool:
        # Available only in remote control mode
        return (
            self._platform.online
            and self._platform.decoded_storedge["control_mode"] == 4
        )

    @property
    def current_option(self) -> str:
        try:
            return self._options[self._platform.decoded_storedge["remote_command_mode"]]
        except KeyError:
            return STATE_UNKNOWN

    async def async_select_option(self, option: str) -> None:
        _LOGGER.debug(f"set {self.unique_id} to {option}")
        new_mode = get_key(self._options, option)
        await self._platform.write_registers(address=57357, payload=new_mode)
        await self.async_update()