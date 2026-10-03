"""Switch platform for SolarEdge Modbus Multi."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from modbus_connection.encode import encode_int32, encode_uint16

from . import SolarEdgeConfigEntry
from .const import SunSpecNotImpl
from .entity import SolarEdgeEntityBase

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

    """ Power Control Options: Site Limit Control """
    for inverter in hub.inverters:
        if hub.option_site_limit_control is True:
            entities.append(
                SolarEdgeExternalProduction(inverter, config_entry, coordinator)
            )
            entities.append(
                SolarEdgeNegativeSiteLimit(inverter, config_entry, coordinator)
            )

        if inverter.apc_may_be_supported:
            entities.append(SolarEdgeGridControl(inverter, config_entry, coordinator))

    if entities:
        async_add_entities(entities)


class SolarEdgeSwitchBase(SolarEdgeEntityBase, SwitchEntity):
    """Base class for SolarEdge switch entities."""

    uid_suffix: str | None = None

    def __init__(self, platform, config_entry, coordinator) -> None:
        super().__init__(platform, config_entry, coordinator)
        if self.uid_suffix is not None:
            self._attr_unique_id = f"{platform.uid_base}_{self.uid_suffix}"


class SolarEdgeExternalProduction(SolarEdgeSwitchBase):
    """External Production switch. Indicates a non-SolarEdge power sorce in system."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "External Production"
    uid_suffix = "external_production"

    @property
    def available(self) -> bool:
        try:
            if self._platform.decoded_model["E_Lim_Ctl_Mode"] == SunSpecNotImpl.UINT16:
                return False

            return super().available

        except KeyError:
            return False

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def is_on(self) -> bool:
        return (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 10) & 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        set_bits = int(self._platform.decoded_model["E_Lim_Ctl_Mode"])
        set_bits = set_bits | (1 << 10)

        _LOGGER.debug(f"set {self.unique_id} bits {set_bits:016b}")

        await self._platform.write_registers(
            address=57344,
            payload=encode_uint16(set_bits),
        )
        await self.async_update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        set_bits = int(self._platform.decoded_model["E_Lim_Ctl_Mode"])
        set_bits = set_bits & ~(1 << 10)

        _LOGGER.debug(f"set {self.unique_id} bits {set_bits:016b}")

        await self._platform.write_registers(
            address=57344,
            payload=encode_uint16(set_bits),
        )
        await self.async_update()


class SolarEdgeNegativeSiteLimit(SolarEdgeSwitchBase):
    """Negative Site Limit switch. Sets minimum import power when enabled."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Negative Site Limit"
    uid_suffix = "negative_site_limit"

    @property
    def available(self) -> bool:
        try:
            if self._platform.decoded_model["E_Lim_Ctl_Mode"] == SunSpecNotImpl.UINT16:
                return False

            return super().available

        except KeyError:
            return False

    @property
    def is_on(self) -> bool:
        return (int(self._platform.decoded_model["E_Lim_Ctl_Mode"]) >> 11) & 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        set_bits = int(self._platform.decoded_model["E_Lim_Ctl_Mode"])
        set_bits = set_bits | (1 << 11)

        _LOGGER.debug(f"set {self.unique_id} bits {set_bits:016b}")

        await self._platform.write_registers(
            address=57344,
            payload=encode_uint16(set_bits),
        )
        await self.async_update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        set_bits = int(self._platform.decoded_model["E_Lim_Ctl_Mode"])
        set_bits = set_bits & ~(1 << 11)

        _LOGGER.debug(f"set {self.unique_id} bits {set_bits:016b}")

        await self._platform.write_registers(
            address=57344,
            payload=encode_uint16(set_bits),
        )
        await self.async_update()


class SolarEdgeGridControl(SolarEdgeSwitchBase):
    """Grid Control boolean switch. This is "AdvancedPwrControlEn" in specs."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Advanced Power Control"
    uid_suffix = "adv_pwr_ctrl"

    @property
    def available(self) -> bool:
        return (
            super().available
            and self._platform.advanced_power_control
            and "AdvPwrCtrlEn" in self._platform.decoded_model.keys()
        )

    @property
    def is_on(self) -> bool:
        return self._platform.decoded_model["AdvPwrCtrlEn"] == 0x1

    async def async_turn_on(self, **kwargs: Any) -> None:
        _LOGGER.debug(f"set {self.unique_id} to 0x1")

        await self._platform.write_registers(
            address=61762,
            payload=encode_int32(0x1, word_order="little"),
        )
        await self.async_update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        _LOGGER.debug(f"set {self.unique_id} to 0x0")

        await self._platform.write_registers(
            address=61762,
            payload=encode_int32(0x0, word_order="little"),
        )
        await self.async_update()
