"""Repairs for SolarEdge Modbus Multi Device."""

from __future__ import annotations

import re
from typing import cast

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
import voluptuous as vol

from .config_flow import generate_config_schema
from .const import DOMAIN, ConfDefaultStr, ConfName
from .helpers import device_list_from_string, host_valid


class CheckConfigurationRepairFlow(RepairsFlow):
    """Handler for an issue fixing flow."""

    _entry: ConfigEntry

    def __init__(self, entry: ConfigEntry) -> None:
        """Create flow."""

        self._entry = entry
        super().__init__()

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the first step of a fix flow."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the confirm step of a fix flow."""
        errors = {}

        if user_input is not None:
            user_input[CONF_HOST] = user_input[CONF_HOST].lower()
            user_input[ConfName.DEVICE_LIST] = re.sub(
                r"\s+", "", user_input[ConfName.DEVICE_LIST], flags=re.UNICODE
            )

            try:
                inverter_count = len(
                    device_list_from_string(user_input[ConfName.DEVICE_LIST])
                )
            except HomeAssistantError as e:
                errors[ConfName.DEVICE_LIST] = f"{e}"

            else:
                if not host_valid(user_input[CONF_HOST]):
                    errors[CONF_HOST] = "invalid_host"
                elif not 1 <= user_input[CONF_PORT] <= 65535:
                    errors[CONF_PORT] = "invalid_tcp_port"
                elif not 1 <= inverter_count <= 32:
                    errors[ConfName.DEVICE_LIST] = "invalid_inverter_count"
                else:
                    user_input[ConfName.DEVICE_LIST] = device_list_from_string(
                        user_input[ConfName.DEVICE_LIST]
                    )
                    this_unique_id = f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                    existing_entry = (
                        self.hass.config_entries.async_entry_for_domain_unique_id(
                            DOMAIN, this_unique_id
                        )
                    )

                    if (
                        existing_entry is not None
                        and self._entry.unique_id != this_unique_id
                    ):
                        errors[CONF_HOST] = "already_configured"
                        errors[CONF_PORT] = "already_configured"

                    else:
                        self.hass.config_entries.async_update_entry(
                            self._entry,
                            unique_id=this_unique_id,
                            data={**self._entry.data, **user_input},
                        )

                        return self.async_create_entry(title="", data={})

        else:
            reconfig_device_list = ",".join(
                str(device)
                for device in self._entry.data.get(
                    ConfName.DEVICE_LIST, ConfDefaultStr.DEVICE_LIST
                )
            )

            user_input = {
                CONF_HOST: self._entry.data[CONF_HOST],
                CONF_PORT: self._entry.data[CONF_PORT],
                ConfName.DEVICE_LIST: reconfig_device_list,
            }

        return self.async_show_form(
            step_id="confirm",
            data_schema=generate_config_schema("confirm", user_input),
            errors=errors,
        )


class RetryFeatureDetectionRepairFlow(RepairsFlow):
    """Reset an inverter's optional-feature detection flag."""

    def __init__(self, entry_id: str, inverter_unit_id: int, attr: str) -> None:
        """Create flow.

        attr is global_power_control or advanced_power_control
        """
        self._entry_id = entry_id
        self._inverter_unit_id = inverter_unit_id
        self._attr = attr
        super().__init__()

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the first step of a fix flow."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the confirm step of a fix flow."""
        if user_input is not None:
            hub = self.hass.data[DOMAIN][self._entry_id]["hub"]
            for inverter in hub.inverters:
                if inverter.inverter_unit_id == self._inverter_unit_id:
                    setattr(inverter, self._attr, None)
                    break

            return self.async_create_entry(title="", data={})

        issue_registry = ir.async_get(self.hass)
        description_placeholders = None
        if issue := issue_registry.async_get_issue(self.handler, self.issue_id):
            description_placeholders = issue.translation_placeholders

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders=description_placeholders,
        )


class DeviceReplacedRepairFlow(RepairsFlow):
    """Handler for a replaced-inverter repair.

    A different inverter (different model/serial) answered at a Modbus device
    ID that previously belonged to another one -- see
    SolarEdgeModbusMultiHub.check_inverter_replaced() in hub.py
    Offers to migrate entities/history onto the replacement or ignore it.

    self.issue_id/self.data are populated by RepairsFlowManager after this
    flow is created (see homeassistant.components.repairs.issue_handler), and
    it deletes the issue itself once a step returns create_entry -- no need
    to do either here, matching CheckConfigurationRepairFlow above.
    """

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Offer to migrate existing entities/history, or ignore the change."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["migrate", "ignore"],
            description_placeholders={
                "device_id": str(self.data["device_id"]),
                "old_model": str(self.data["old_model"]),
                "old_serial": str(self.data["old_serial"]),
                "new_model": str(self.data["new_model"]),
                "new_serial": str(self.data["new_serial"]),
            },
        )

    async def async_step_migrate(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Move existing entities/history onto the replacement inverter.

        Covers the inverter and everything derived from it (meters,
        batteries, DER batteries, MMPPT units), since all of their
        unique_ids literally start with the inverter's uid_base.
        """
        entry_id = cast(str, self.data["entry_id"])
        unit_id = cast(int, self.data["device_id"])

        hub = self._get_hub(entry_id)
        if hub is None:
            return self.async_abort(reason="reload_required")

        inverter = self._find_inverter(hub, unit_id)
        if inverter is None:
            return self.async_abort(reason="device_not_found")

        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, inverter.anchor)}
        )
        if device is None:
            return self.async_abort(reason="device_not_found")

        old_uid_base = next(
            (
                identifier[1]
                for identifier in device.identifiers
                if identifier[0] == DOMAIN and identifier[1] != inverter.anchor
            ),
            None,
        )

        if old_uid_base is not None and old_uid_base != inverter.uid_base:
            self._migrate_entities(entry_id, old_uid_base, inverter.uid_base)

        self._refresh_devices(hub, unit_id)

        return self.async_create_entry(title="", data={})

    async def async_step_ignore(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Dismiss the repair without migrating entities."""
        unit_id = cast(int, self.data["device_id"])

        hub = self._get_hub(cast(str, self.data["entry_id"]))
        if hub is not None:
            self._refresh_devices(hub, unit_id)

        return self.async_create_entry(title="", data={})

    def _get_hub(self, entry_id: str):
        entry_data = self.hass.data.get(DOMAIN, {}).get(entry_id)
        return entry_data["hub"] if entry_data is not None else None

    @staticmethod
    def _find_inverter(hub, unit_id: int):
        return next((i for i in hub.inverters if i.inverter_unit_id == unit_id), None)

    def _migrate_entities(
        self, entry_id: str, old_uid_base: str, new_uid_base: str
    ) -> None:
        """Rename unique_ids so existing entity_ids/history follow the new hardware."""
        entity_registry = er.async_get(self.hass)
        old_prefix = f"{old_uid_base}_"
        new_prefix = f"{new_uid_base}_"

        entries = er.async_entries_for_config_entry(entity_registry, entry_id)
        by_unique_id = {entry.unique_id: entry for entry in entries}

        for entry in entries:
            if not entry.unique_id.startswith(old_prefix):
                continue

            new_unique_id = new_prefix + entry.unique_id[len(old_prefix) :]

            duplicate = by_unique_id.get(new_unique_id)
            if duplicate is not None:
                entity_registry.async_remove(duplicate.entity_id)

            entity_registry.async_update_entity(
                entry.entity_id, new_unique_id=new_unique_id
            )

    def _refresh_devices(self, hub, unit_id: int) -> None:
        """Drop stale identifiers on the inverter and its child devices.

        Otherwise a device row keeps accumulating every uid_base it has ever
        had, and the next replacement can't tell which one is current.
        """
        device_registry = dr.async_get(self.hass)

        # (anchor, current identifier tuple, update kwargs)
        refresh_targets: list[tuple[str, tuple, dict]] = []

        inverter = self._find_inverter(hub, unit_id)
        if inverter is not None:
            refresh_targets.append(
                (
                    inverter.anchor,
                    (DOMAIN, inverter.uid_base),
                    {"model": inverter.model, "serial_number": inverter.serial},
                )
            )
            refresh_targets.extend(
                (
                    mmppt_unit.anchor,
                    (DOMAIN, inverter.uid_base, mmppt_unit.mmppt_key),
                    {"model": inverter.model},
                )
                for mmppt_unit in inverter.mmppt_units
            )

        refresh_targets.extend(
            (
                device.anchor,
                (DOMAIN, device.uid_base),
                {"model": device.model, "serial_number": device.serial},
            )
            for device in (*hub.meters, *hub.batteries, *hub.der_batteries)
            if device.inverter_unit_id == unit_id
        )

        for anchor, current_identifier, update_kwargs in refresh_targets:
            device = device_registry.async_get_device(identifiers={(DOMAIN, anchor)})
            if device is None:
                continue
            device_registry.async_update_device(
                device.id,
                new_identifiers={(DOMAIN, anchor), current_identifier},
                **update_kwargs,
            )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create flow."""

    if issue_id.startswith("device_replaced_"):
        return DeviceReplacedRepairFlow()

    entry_id = cast(str, data["entry_id"])

    if (entry := hass.config_entries.async_get_entry(entry_id)) is not None:
        if issue_id == "check_configuration":
            return CheckConfigurationRepairFlow(entry)

        if issue_id.startswith("detect_timeout_gpc_"):
            return RetryFeatureDetectionRepairFlow(
                entry_id, cast(int, data["inverter_unit_id"]), "global_power_control"
            )

        if issue_id.startswith("detect_timeout_apc_"):
            return RetryFeatureDetectionRepairFlow(
                entry_id, cast(int, data["inverter_unit_id"]), "advanced_power_control"
            )
    return None
