from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

from homeassistant.helpers.entity import DeviceInfo
from pymodbus.client.mixin import ModbusClientMixin

from .const import BATTERY_REG_BASE, DOMAIN, SunSpecNotImpl
from .exceptions import DeviceInvalid, ModbusIllegalAddress, ModbusIOError, ModbusReadError
from .helpers import float_to_hex, int_list_to_string

if TYPE_CHECKING:
    from .hub import SolarEdgeModbusMultiHub

_LOGGER = logging.getLogger(__name__)


class SolarEdgeBattery:
    """Defines a SolarEdge battery."""

    def __init__(self, device_id: int, battery_id: int, hub: SolarEdgeModbusMultiHub) -> None:
        self.inverter_unit_id = device_id
        self.hub = hub
        self.decoded_common = {}
        self.decoded_model = {}
        self.start_address = None
        self.battery_id = battery_id
        self.has_parent = True
        self.inverter_common = self.hub.inverter_common[self.inverter_unit_id]
        self._via_device = None
        self._last_update_timestamp = None

        try:
            self.start_address = BATTERY_REG_BASE[self.battery_id]
        except KeyError:
            raise DeviceInvalid(f"Invalid battery_id {self.battery_id}")

    async def init_device(self) -> None:
        try:
            battery_info = await self.hub.modbus_read_holding_registers(
                unit=self.inverter_unit_id, address=self.start_address, rcount=68
            )

            self.decoded_common = dict(
                [
                    (
                        "B_Manufacturer",  # string(32)
                        int_list_to_string(
                            ModbusClientMixin.convert_from_registers(
                                battery_info.registers[0:16],
                                data_type=ModbusClientMixin.DATATYPE.UINT16,
                                word_order="little",
                            )
                        ),
                    ),
                    (
                        "B_Model",  # string(32)
                        int_list_to_string(
                            ModbusClientMixin.convert_from_registers(
                                battery_info.registers[16:32],
                                data_type=ModbusClientMixin.DATATYPE.UINT16,
                                word_order="little",
                            )
                        ),
                    ),
                    (
                        "B_Version",  # string(32)
                        int_list_to_string(
                            ModbusClientMixin.convert_from_registers(
                                battery_info.registers[32:48],
                                data_type=ModbusClientMixin.DATATYPE.UINT16,
                                word_order="little",
                            )
                        ),
                    ),
                    (
                        "B_SerialNumber",  # string(32)
                        int_list_to_string(
                            ModbusClientMixin.convert_from_registers(
                                battery_info.registers[48:64],
                                data_type=ModbusClientMixin.DATATYPE.UINT16,
                                word_order="little",
                            )
                        ),
                    ),
                    (
                        "B_Device_Address",
                        ModbusClientMixin.convert_from_registers(
                            [battery_info.registers[64]],
                            data_type=ModbusClientMixin.DATATYPE.UINT16,
                            word_order="little",
                        ),
                    ),
                    (
                        "B_RatedEnergy",
                        ModbusClientMixin.convert_from_registers(
                            battery_info.registers[66:68],
                            data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                            word_order="little",
                        ),
                    ),
                ]
            )

            for name, value in iter(self.decoded_common.items()):
                if isinstance(value, float):
                    display_value = float_to_hex(value)
                else:
                    display_value = hex(value) if isinstance(value, int) else value
                _LOGGER.debug(
                    (f"I{self.inverter_unit_id}B{self.battery_id}: {name} {display_value} {type(value)}"),
                )

        except ModbusIOError:
            raise DeviceInvalid(f"No response from inverter ID {self.inverter_unit_id}")

        except ModbusIllegalAddress:
            raise DeviceInvalid(f"Battery {self.battery_id} unsupported address")

        self.decoded_common["B_Manufacturer"] = self.decoded_common["B_Manufacturer"].removesuffix(
            self.decoded_common["B_SerialNumber"]
        )
        self.decoded_common["B_Model"] = self.decoded_common["B_Model"].removesuffix(
            self.decoded_common["B_SerialNumber"]
        )

        # Remove ASCII control characters from descriptive strings
        ascii_ctrl_chars = dict.fromkeys(range(32))
        self.decoded_common["B_Manufacturer"] = self.decoded_common["B_Manufacturer"].translate(ascii_ctrl_chars)
        self.decoded_common["B_Model"] = self.decoded_common["B_Model"].translate(ascii_ctrl_chars)
        self.decoded_common["B_SerialNumber"] = self.decoded_common["B_SerialNumber"].translate(ascii_ctrl_chars)

        if (
            float_to_hex(self.decoded_common["B_RatedEnergy"]) == hex(SunSpecNotImpl.FLOAT32)
            or self.decoded_common["B_RatedEnergy"] <= 0
        ):
            raise DeviceInvalid(f"Battery {self.battery_id} not usable (rating <=0)")

        self.manufacturer = self.decoded_common["B_Manufacturer"]
        self.model = self.decoded_common["B_Model"]
        self.option = ""
        self.fw_version = self.decoded_common["B_Version"]
        self.serial = self.decoded_common["B_SerialNumber"]
        self.device_address = self.decoded_common["B_Device_Address"]
        self.name = f"{self.hub.hub_id.capitalize()} I{self.inverter_unit_id} B{self.battery_id}"

        inverter_model = self.inverter_common["C_Model"]
        inverter_serial = self.inverter_common["C_SerialNumber"]
        self.uid_base = f"{inverter_model}_{inverter_serial}_B{self.battery_id}"

    async def read_modbus_data(self) -> None:
        try:
            battery_data = await self.hub.modbus_read_holding_registers(
                unit=self.inverter_unit_id,
                address=self.start_address + 68,
                rcount=86,
            )

            float32_fields = [
                "B_MaxChargePower",
                "B_MaxDischargePower",
                "B_MaxChargePeakPower",
                "B_MaxDischargePeakPower",
                "B_Temp_Average",
                "B_Temp_Max",
                "B_DC_Voltage",
                "B_DC_Current",
                "B_DC_Power",
                "B_Energy_Max",
                "B_Energy_Available",
                "B_SOH",
                "B_SOE",
            ]
            float32_data = battery_data.registers[0:8] + battery_data.registers[40:50] + battery_data.registers[58:66]
            self.decoded_model = dict(
                zip(
                    float32_fields,
                    ModbusClientMixin.convert_from_registers(
                        float32_data,
                        data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                        word_order="little",
                    ),
                )
            )

            uint64_fields = [
                "B_Export_Energy_WH",
                "B_Import_Energy_WH",
            ]
            uint64_data = battery_data.registers[50:58]
            self.decoded_model.update(
                dict(
                    zip(
                        uint64_fields,
                        ModbusClientMixin.convert_from_registers(
                            uint64_data,
                            data_type=ModbusClientMixin.DATATYPE.UINT64,
                            word_order="little",
                        ),
                    )
                )
            )

            uint32_fields = ["B_Status", "B_Status_Vendor"]
            uint32_data = battery_data.registers[66:70]
            self.decoded_model.update(
                dict(
                    zip(
                        uint32_fields,
                        ModbusClientMixin.convert_from_registers(
                            uint32_data,
                            data_type=ModbusClientMixin.DATATYPE.UINT32,
                            word_order="little",
                        ),
                    )
                )
            )

            uint16_fields = [
                "B_Event_Log1",
                "B_Event_Log2",
                "B_Event_Log3",
                "B_Event_Log4",
                "B_Event_Log5",
                "B_Event_Log6",
                "B_Event_Log7",
                "B_Event_Log8",
                "B_Event_Log_Vendor1",
                "B_Event_Log_Vendor2",
                "B_Event_Log_Vendor3",
                "B_Event_Log_Vendor4",
                "B_Event_Log_Vendor5",
                "B_Event_Log_Vendor6",
                "B_Event_Log_Vendor7",
                "B_Event_Log_Vendor8",
            ]
            uint16_data = battery_data.registers[70:86]
            self.decoded_model.update(
                dict(
                    zip(
                        uint16_fields,
                        ModbusClientMixin.convert_from_registers(
                            uint16_data,
                            data_type=ModbusClientMixin.DATATYPE.UINT16,
                            word_order="little",
                        ),
                    )
                )
            )

        except ModbusIOError:
            raise ModbusReadError(f"No response from inverter ID {self.inverter_unit_id}")

        for name, value in iter(self.decoded_model.items()):
            if isinstance(value, float):
                display_value = float_to_hex(value)
            else:
                display_value = hex(value) if isinstance(value, int) else value

            _LOGGER.debug(f"I{self.inverter_unit_id}B{self.battery_id}: {name} {display_value} {type(value)}")

    def set_last_update(self, timestamp) -> None:
        self._last_update_timestamp = timestamp

    @property
    def online(self) -> bool:
        """Device is online."""
        return self.hub.online

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.uid_base)},
            name=self.name,
            manufacturer=self.manufacturer,
            model=self.model,
            serial_number=self.serial,
            sw_version=self.fw_version,
            via_device=self.via_device,
        )

    @property
    def via_device(self) -> tuple[str, str]:
        return self._via_device

    @via_device.setter
    def via_device(self, device: str) -> None:
        self._via_device = (DOMAIN, device)

    @property
    def allow_battery_energy_reset(self) -> bool:
        return self.hub.allow_battery_energy_reset

    @property
    def battery_rating_adjust(self) -> int:
        return self.hub.battery_rating_adjust

    @property
    def battery_energy_reset_cycles(self) -> int:
        return self.hub.battery_energy_reset_cycles

    @property
    def last_update(self) -> datetime.datetime | None:
        return self._last_update_timestamp
