from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

from homeassistant.helpers.entity import DeviceInfo
from pymodbus.client.mixin import ModbusClientMixin

from .const import DOMAIN, METER_REG_BASE, SunSpecNotImpl
from .exceptions import DeviceInvalid, ModbusIllegalAddress, ModbusIOError, ModbusReadError
from .helpers import int_list_to_string

if TYPE_CHECKING:
    from .hub import SolarEdgeModbusMultiHub

_LOGGER = logging.getLogger(__name__)


class SolarEdgeMeter:
    """Defines a SolarEdge meter."""

    def __init__(self, device_id: int, meter_id: int, hub: SolarEdgeModbusMultiHub) -> None:
        self.inverter_unit_id = device_id
        self.hub = hub
        self.decoded_common = {}
        self.decoded_model = {}
        self.meter_id = meter_id
        self.has_parent = True
        self.inverter_common = self.hub.inverter_common[self.inverter_unit_id]
        self.mmppt_common = self.hub.mmppt_common[self.inverter_unit_id]
        self._via_device = None
        self._last_update_timestamp = None

        try:
            self.start_address = METER_REG_BASE[self.meter_id]
        except KeyError:
            raise DeviceInvalid(f"Invalid meter_id {self.meter_id}")

        if self.mmppt_common is not None:
            if self.mmppt_common["mmppt_Units"] == 2:
                self.start_address = self.start_address + 50

            elif self.mmppt_common["mmppt_Units"] == 3:
                self.start_address = self.start_address + 70

            else:
                raise DeviceInvalid(f"Invalid mmppt_Units value {self.mmppt_common['mmppt_Units']}")

    async def init_device(self) -> None:
        try:
            meter_info = await self.hub.modbus_read_holding_registers(
                unit=self.inverter_unit_id,
                address=self.start_address,
                rcount=67,
            )
            if meter_info.isError():
                _LOGGER.debug(meter_info)
                raise ModbusReadError(meter_info)

            uint16_fields = [
                "C_SunSpec_DID",
                "C_SunSpec_Length",
                "C_Device_address",
            ]
            uint16_data = meter_info.registers[0:2] + [meter_info.registers[66]]

            self.decoded_common = dict(
                zip(
                    uint16_fields,
                    ModbusClientMixin.convert_from_registers(
                        uint16_data,
                        data_type=ModbusClientMixin.DATATYPE.UINT16,
                    ),
                )
            )

            self.decoded_common.update(
                dict(
                    [
                        (
                            "C_Manufacturer",  # string(32)
                            int_list_to_string(
                                ModbusClientMixin.convert_from_registers(
                                    meter_info.registers[2:18],
                                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                                )
                            ),
                        ),
                        (
                            "C_Model",  # string(32)
                            int_list_to_string(
                                ModbusClientMixin.convert_from_registers(
                                    meter_info.registers[18:34],
                                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                                )
                            ),
                        ),
                        (
                            "C_Option",  # string(16)
                            int_list_to_string(
                                ModbusClientMixin.convert_from_registers(
                                    meter_info.registers[34:42],
                                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                                )
                            ),
                        ),
                        (
                            "C_Version",  # string(16)
                            int_list_to_string(
                                ModbusClientMixin.convert_from_registers(
                                    meter_info.registers[42:50],
                                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                                )
                            ),
                        ),
                        (
                            "C_SerialNumber",  # string(32)
                            int_list_to_string(
                                ModbusClientMixin.convert_from_registers(
                                    meter_info.registers[50:66],
                                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                                )
                            ),
                        ),
                    ]
                )
            )

            for name, value in iter(self.decoded_common.items()):
                _LOGGER.debug(
                    (
                        f"I{self.inverter_unit_id}M{self.meter_id}: "
                        f"{name} {hex(value) if isinstance(value, int) else value} "
                        f"{type(value)}"
                    ),
                )

            if (
                self.decoded_common["C_SunSpec_DID"] == SunSpecNotImpl.UINT16
                or self.decoded_common["C_SunSpec_DID"] != 0x0001
                or self.decoded_common["C_SunSpec_Length"] != 65
            ):
                raise DeviceInvalid(f"Meter {self.meter_id} ident incorrect or not installed.")

        except ModbusIOError:
            raise DeviceInvalid(f"No response from inverter ID {self.inverter_unit_id}")

        except ModbusIllegalAddress:
            raise DeviceInvalid(f"Meter {self.meter_id}: unsupported address")

        self.manufacturer = self.decoded_common["C_Manufacturer"]
        self.model = self.decoded_common["C_Model"]
        self.option = self.decoded_common["C_Option"]
        self.fw_version = self.decoded_common["C_Version"]
        self.serial = self.decoded_common["C_SerialNumber"]
        self.device_address = self.decoded_common["C_Device_address"]
        self.name = f"{self.hub.hub_id.capitalize()} I{self.inverter_unit_id} M{self.meter_id}"

        inverter_model = self.inverter_common["C_Model"]
        inverter_serial = self.inverter_common["C_SerialNumber"]
        self.uid_base = f"{inverter_model}_{inverter_serial}_M{self.meter_id}"

    async def read_modbus_data(self) -> None:
        try:
            meter_data = await self.hub.modbus_read_holding_registers(
                unit=self.inverter_unit_id,
                address=self.start_address + 67,
                rcount=107,
            )

            self.decoded_model = dict(
                [
                    (
                        "C_SunSpec_DID",
                        ModbusClientMixin.convert_from_registers(
                            [meter_data.registers[0]],
                            data_type=ModbusClientMixin.DATATYPE.UINT16,
                        ),
                    ),
                    (
                        "C_SunSpec_Length",
                        ModbusClientMixin.convert_from_registers(
                            [meter_data.registers[1]],
                            data_type=ModbusClientMixin.DATATYPE.UINT16,
                        ),
                    ),
                ]
            )

            int16_fields = [
                "AC_Current",
                "AC_Current_A",
                "AC_Current_B",
                "AC_Current_C",
                "AC_Current_SF",
                "AC_Voltage_LN",
                "AC_Voltage_AN",
                "AC_Voltage_BN",
                "AC_Voltage_CN",
                "AC_Voltage_LL",
                "AC_Voltage_AB",
                "AC_Voltage_BC",
                "AC_Voltage_CA",
                "AC_Voltage_SF",
                "AC_Frequency",
                "AC_Frequency_SF",
                "AC_Power",
                "AC_Power_A",
                "AC_Power_B",
                "AC_Power_C",
                "AC_Power_SF",
                "AC_VA",
                "AC_VA_A",
                "AC_VA_B",
                "AC_VA_C",
                "AC_VA_SF",
                "AC_var",
                "AC_var_A",
                "AC_var_B",
                "AC_var_C",
                "AC_var_SF",
                "AC_PF",
                "AC_PF_A",
                "AC_PF_B",
                "AC_PF_C",
                "AC_PF_SF",
                "AC_Energy_WH_SF",
                "M_VAh_SF",
                "M_varh_SF",
            ]
            int16_data = (
                meter_data.registers[2:38]
                + [meter_data.registers[54]]
                + [meter_data.registers[71]]
                + [meter_data.registers[104]]
            )
            self.decoded_model.update(
                dict(
                    zip(
                        int16_fields,
                        ModbusClientMixin.convert_from_registers(
                            int16_data,
                            data_type=ModbusClientMixin.DATATYPE.INT16,
                        ),
                    )
                )
            )

            uint32_fields = [
                "AC_Energy_WH_Exported",
                "AC_Energy_WH_Exported_A",
                "AC_Energy_WH_Exported_B",
                "AC_Energy_WH_Exported_C",
                "AC_Energy_WH_Imported",
                "AC_Energy_WH_Imported_A",
                "AC_Energy_WH_Imported_B",
                "AC_Energy_WH_Imported_C",
                "M_VAh_Exported",
                "M_VAh_Exported_A",
                "M_VAh_Exported_B",
                "M_VAh_Exported_C",
                "M_VAh_Imported",
                "M_VAh_Imported_A",
                "M_VAh_Imported_B",
                "M_VAh_Imported_C",
                "M_varh_Import_Q1",
                "M_varh_Import_Q1_A",
                "M_varh_Import_Q1_B",
                "M_varh_Import_Q1_C",
                "M_varh_Import_Q2",
                "M_varh_Import_Q2_A",
                "M_varh_Import_Q2_B",
                "M_varh_Import_Q2_C",
                "M_varh_Export_Q3",
                "M_varh_Export_Q3_A",
                "M_varh_Export_Q3_B",
                "M_varh_Export_Q3_C",
                "M_varh_Export_Q4",
                "M_varh_Export_Q4_A",
                "M_varh_Export_Q4_B",
                "M_varh_Export_Q4_C",
                "M_Events",
            ]
            uint32_data = (
                meter_data.registers[38:54]
                + meter_data.registers[55:70]
                + meter_data.registers[71:104]
                + meter_data.registers[105:107]
            )
            self.decoded_model.update(
                dict(
                    zip(
                        uint32_fields,
                        ModbusClientMixin.convert_from_registers(
                            uint32_data,
                            data_type=ModbusClientMixin.DATATYPE.UINT32,
                        ),
                    )
                )
            )

        except ModbusIOError:
            raise ModbusReadError(f"No response from inverter ID {self.inverter_unit_id}")

        for name, value in iter(self.decoded_model.items()):
            _LOGGER.debug(
                (
                    f"I{self.inverter_unit_id}M{self.meter_id}: "
                    f"{name} {hex(value) if isinstance(value, int) else value} "
                    f"{type(value)}"
                ),
            )

        if (
            self.decoded_model["C_SunSpec_DID"] == SunSpecNotImpl.UINT16
            or self.decoded_model["C_SunSpec_DID"] not in [201, 202, 203, 204]
            or self.decoded_model["C_SunSpec_Length"] != 105
        ):
            raise DeviceInvalid(f"Meter {self.meter_id} ident incorrect or not installed.")

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
            hw_version=self.option,
            via_device=self.via_device,
        )

    @property
    def via_device(self) -> tuple[str, str]:
        return self._via_device

    @via_device.setter
    def via_device(self, device: str) -> None:
        self._via_device = (DOMAIN, device)

    @property
    def last_update(self) -> datetime.datetime | None:
        return self._last_update_timestamp
