"""The SolarEdge Modbus Multi virtual system select module.

Selects here set how SolarEdgeSystem calculates its values. They never write to
the devices on the hub.
"""

from __future__ import annotations

import logging

from homeassistant.components.select import DOMAIN as SELECT_DOMAIN, SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, PRODUCTION_METER_SCOPE, MeterScope
from .coordinator import SolarEdgeConfigEntry, SolarEdgeCoordinator
from .entity import SolarEdgeEntity

_LOGGER = logging.getLogger(__name__)

SCOPE_BY_OPTION = {option: scope for scope, option in PRODUCTION_METER_SCOPE.items()}


def async_virtual_system_select_entities(
    hass: HomeAssistant,
    hub,
    config_entry: SolarEdgeConfigEntry,
    coordinator: SolarEdgeCoordinator,
) -> list[SelectEntity]:
    """Return the virtual system select entities for a hub.

    Same check as the virtual system sensors: none for systems with batteries.
    """
    if not hub.inverters or hub.system.has_storage:
        return []

    ent_reg = er.async_get(hass)
    entities: list[SelectEntity] = []

    for meter in hub.system.production_meters:
        entity = ProductionMeterScope(hub.system, meter, config_entry, coordinator)
        entity_id = ent_reg.async_get_entity_id(SELECT_DOMAIN, DOMAIN, entity.unique_id)
        reg_entry = ent_reg.async_get(entity_id) if entity_id else None
        if reg_entry is not None and reg_entry.disabled:
            # A disabled entity is never added, so it can't restore a scope.
            hub.system.production_meter_scopes[meter.uid_base] = MeterScope.INVERTER
        else:
            entities.append(entity)

    return entities


class ProductionMeterScope(SolarEdgeEntity, SelectEntity, RestoreEntity):
    """What a Production meter measures, for the virtual system device.

    Modbus can't tell, so the user sets it and the last state is restored.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:meter-electric"

    def __init__(self, system, meter, config_entry, coordinator):
        """Initialize the production meter scope."""
        super().__init__(system, config_entry, coordinator)
        self._meter = meter
        self._attr_name = (
            f"Production Meter I{meter.inverter_unit_id} M{meter.meter_id}"
        )
        self._attr_unique_id = f"{system.uid_base}_production_meter_{meter.uid_base}"
        self._attr_options = list(PRODUCTION_METER_SCOPE.values())

    async def async_added_to_hass(self) -> None:
        """Restore the last scope, Inverter Only if there is none."""
        await super().async_added_to_hass()
        scope = MeterScope.INVERTER
        if (last_state := await self.async_get_last_state()) is not None:
            scope = SCOPE_BY_OPTION.get(last_state.state, scope)
        self._set_scope(scope)

    @property
    def current_option(self) -> str:
        """Return the current option."""
        return PRODUCTION_METER_SCOPE[
            self._platform.production_meter_scope(self._meter)
        ]

    async def async_select_option(self, option: str) -> None:
        """Select option."""
        _LOGGER.debug("set %s to %s", self.unique_id, option)
        self._set_scope(SCOPE_BY_OPTION[option])

    def _set_scope(self, scope: MeterScope) -> None:
        """Set the scope and recalculate the system values."""
        self._platform.production_meter_scopes[self._meter.uid_base] = scope
        self.coordinator.async_update_listeners()
