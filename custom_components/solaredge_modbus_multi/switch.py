from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadBuilder

from .const import DOMAIN, SunSpecNotImpl

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub = hass.data[DOMAIN][config_entry.entry_id]["hub"]
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    entities = []

    """ Power Control Options: Site Limit Control """
    if hub.option_site_limit_control is True:
        for inverter in hub.inverters:
            entities.append(
                SolarEdgeExternalProduction(inverter, config_entry, coordinator)
            )
            entities.append(
                SolarEdgeNegativeSiteLimit(inverter, config_entry, coordinator)
            )
            if inverter.advanced_power_control:
                entities.append(
                    SolarEdgeGridControl(inverter, config_entry, coordinator)
                )

    if entities:
        async_add_entities(entities)


class SolarEdgeSwitchBase(CoordinatorEntity, SwitchEntity):
    should_poll = False
    _attr_has_entity_name = True

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


class SolarEdgeExternalProduction(SolarEdgeSwitchBase):
    entity_category = EntityCategory.CONFIG

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def available(self) -> bool:
        return (
            super().available
            and "E_Lim_Ctl_Mode" in self._platform.decoded_model.keys()
        )

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_external_production"

    @property
    def name(self) -> str:
        return "External Production"

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def is_on(self) -> bool | None:
        try:
            if self._platform.decoded_model["E_Lim_Ctl_Mode"] == SunSpecNotImpl.UINT16:
                return None

            return (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 10) & 1

        except KeyError:
            return None

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        set_bits = int(self._platform.decoded_model["E_Lim_Ctl_Mode"])
        set_bits = set_bits | (1 << 10)

        _LOGGER.debug(f"set {self.unique_id} bits {set_bits:016b}")
        await self._platform.write_registers(address=57344, payload=set_bits)
        await self.async_update()

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        set_bits = int(self._platform.decoded_model["E_Lim_Ctl_Mode"])
        set_bits = set_bits & ~(1 << 10)

        _LOGGER.debug(f"set {self.unique_id} bits {set_bits:016b}")
        await self._platform.write_registers(address=57344, payload=set_bits)
        await self.async_update()


class SolarEdgeNegativeSiteLimit(SolarEdgeSwitchBase):
    entity_category = EntityCategory.CONFIG

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def available(self) -> bool:
        return (
            super().available
            and "E_Lim_Ctl_Mode" in self._platform.decoded_model.keys()
        )

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_negative_site_limit"

    @property
    def name(self) -> str:
        return "Negative Site Limit"

    @property
    def is_on(self) -> bool | None:
        try:
            if self._platform.decoded_model["E_Lim_Ctl_Mode"] == SunSpecNotImpl.UINT16:
                return None

            return (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 11) & 1

        except KeyError:
            return None

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        set_bits = int(self._platform.decoded_model["E_Lim_Ctl_Mode"])
        set_bits = set_bits | (1 << 11)

        _LOGGER.debug(f"set {self.unique_id} bits {set_bits:016b}")
        await self._platform.write_registers(address=57344, payload=set_bits)
        await self.async_update()

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        set_bits = int(self._platform.decoded_model["E_Lim_Ctl_Mode"])
        set_bits = set_bits & ~(1 << 11)

        _LOGGER.debug(f"set {self.unique_id} bits {set_bits:016b}")
        await self._platform.write_registers(address=57344, payload=set_bits)
        await self.async_update()


class SolarEdgeGridControl(SolarEdgeSwitchBase):
    entity_category = EntityCategory.CONFIG

    def __init__(self, platform, config_entry, coordinator):
        super().__init__(platform, config_entry, coordinator)
        """Initialize the sensor."""

    @property
    def available(self) -> bool:
        return super().available and self._platform.advanced_power_control

    @property
    def unique_id(self) -> str:
        return f"{self._platform.uid_base}_grid_control"

    @property
    def name(self) -> str:
        return "Grid Control"

    @property
    def is_on(self) -> bool | None:
        try:
            return self._platform.decoded_model["I_AdvPwrCtrlEn"] == 0x1

        except KeyError:
            return None

    async def async_turn_on(self, **kwargs):
        _LOGGER.debug(f"set {self.unique_id} to 0x1")
        builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
        builder.add_32bit_int(0x1)
        await self._platform.write_registers(
            address=61762, payload=builder.to_registers()
        )
        await self.async_update()

    async def async_turn_off(self, **kwargs):
        _LOGGER.debug(f"set {self.unique_id} to 0x0")
        builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
        builder.add_32bit_int(0x0)
        await self._platform.write_registers(
            address=61762, payload=builder.to_registers()
        )
        await self.async_update()
