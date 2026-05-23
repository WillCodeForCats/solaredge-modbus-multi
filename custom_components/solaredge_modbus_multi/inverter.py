from __future__ import annotations

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING

from awesomeversion import AwesomeVersion
from awesomeversion.exceptions import (
    AwesomeVersionCompareException,
    AwesomeVersionStrategyException,
)
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity import DeviceInfo
from pymodbus.client.mixin import ModbusClientMixin
from pymodbus.exceptions import ModbusIOException

from .const import DOMAIN, STATUS_VENDOR4_VERSION, SolarEdgeTimeouts, SunSpecNotImpl
from .exceptions import (
    DeviceInvalid,
    ModbusIllegalAddress,
    ModbusIOError,
    ModbusReadError,
)
from .helpers import float_to_hex, int_list_to_string

if TYPE_CHECKING:
    from .hub import SolarEdgeModbusMultiHub

_LOGGER = logging.getLogger(__name__)


class SolarEdgeInverter:
    """Defines a SolarEdge inverter."""

    def __init__(self, device_id: int, hub: SolarEdgeModbusMultiHub) -> None:
        self.inverter_unit_id = device_id
        self.hub = hub
        self.mmppt_units = []
        self.decoded_common = {}
        self.decoded_model = {}
        self.decoded_mmppt = {}
        self.decoded_storage_control = None
        self.has_parent = False
        self.has_battery = None
        self.global_power_control = None
        self.advanced_power_control = None
        self.site_limit_control = None
        self._grid_status = None
        self._last_update_timestamp = None
        self._use_status_vendor4 = False

    async def init_device(self) -> None:
        """Set up data about the device from modbus."""

        try:
            inverter_data = await self.hub.modbus_read_holding_registers(
                unit=self.inverter_unit_id, address=40000, rcount=69
            )

            self.decoded_common = dict(
                [
                    (
                        "C_SunSpec_ID",
                        ModbusClientMixin.convert_from_registers(
                            inverter_data.registers[0:2],
                            data_type=ModbusClientMixin.DATATYPE.UINT32,
                        ),
                    )
                ]
            )

            uint16_fields = [
                "C_SunSpec_DID",
                "C_SunSpec_Length",
                "C_Device_address",
            ]
            uint16_data = inverter_data.registers[2:4] + [inverter_data.registers[68]]
            self.decoded_common.update(
                dict(
                    zip(
                        uint16_fields,
                        ModbusClientMixin.convert_from_registers(
                            uint16_data,
                            data_type=ModbusClientMixin.DATATYPE.UINT16,
                        ),
                    )
                )
            )

            self.decoded_common.update(
                dict(
                    [
                        (
                            "C_Manufacturer",  # string(32)
                            int_list_to_string(
                                ModbusClientMixin.convert_from_registers(
                                    inverter_data.registers[4:20],
                                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                                )
                            ),
                        ),
                        (
                            "C_Model",  # string(32)
                            int_list_to_string(
                                ModbusClientMixin.convert_from_registers(
                                    inverter_data.registers[20:36],
                                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                                )
                            ),
                        ),
                        (
                            "C_Option",  # string(16)
                            int_list_to_string(
                                ModbusClientMixin.convert_from_registers(
                                    inverter_data.registers[36:44],
                                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                                )
                            ),
                        ),
                        (
                            "C_Version",  # string(16)
                            int_list_to_string(
                                ModbusClientMixin.convert_from_registers(
                                    inverter_data.registers[44:52],
                                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                                )
                            ),
                        ),
                        (
                            "C_SerialNumber",  # string(32)
                            int_list_to_string(
                                ModbusClientMixin.convert_from_registers(
                                    inverter_data.registers[52:68],
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
                        f"I{self.inverter_unit_id}: "
                        f"{name} {hex(value) if isinstance(value, int) else value}"
                        f"{type(value)}"
                    ),
                )

            self.hub.inverter_common[self.inverter_unit_id] = self.decoded_common

        except ModbusIOError:
            raise DeviceInvalid(f"No response from inverter ID {self.inverter_unit_id}")

        except ModbusIllegalAddress:
            raise DeviceInvalid(f"ID {self.inverter_unit_id} is not a SunSpec inverter.")

        if (
            self.decoded_common["C_SunSpec_ID"] == SunSpecNotImpl.UINT32
            or self.decoded_common["C_SunSpec_DID"] == SunSpecNotImpl.UINT16
            or self.decoded_common["C_SunSpec_ID"] != 0x53756E53
            or self.decoded_common["C_SunSpec_DID"] != 0x0001
            or self.decoded_common["C_SunSpec_Length"] != 65
        ):
            raise DeviceInvalid(f"ID {self.inverter_unit_id} is not a SunSpec inverter.")

        try:
            mmppt_common = await self.hub.modbus_read_holding_registers(
                unit=self.inverter_unit_id, address=40121, rcount=9
            )

            self.decoded_mmppt = dict(
                [
                    (
                        "mmppt_DID",
                        ModbusClientMixin.convert_from_registers(
                            [mmppt_common.registers[0]],
                            data_type=ModbusClientMixin.DATATYPE.UINT16,
                        ),
                    ),
                    (
                        "mmppt_Length",
                        ModbusClientMixin.convert_from_registers(
                            [mmppt_common.registers[1]],
                            data_type=ModbusClientMixin.DATATYPE.UINT16,
                        ),
                    ),
                    (
                        "mmppt_Units",
                        ModbusClientMixin.convert_from_registers(
                            [mmppt_common.registers[8]],
                            data_type=ModbusClientMixin.DATATYPE.UINT16,
                        ),
                    ),
                ]
            )

            for name, value in iter(self.decoded_mmppt.items()):
                _LOGGER.debug(
                    (
                        f"I{self.inverter_unit_id} MMPPT: "
                        f"{name} {hex(value) if isinstance(value, int) else value} "
                        f"{type(value)}"
                    ),
                )

            if (
                self.decoded_mmppt["mmppt_DID"] == SunSpecNotImpl.UINT16
                or self.decoded_mmppt["mmppt_Units"] == SunSpecNotImpl.UINT16
                or self.decoded_mmppt["mmppt_DID"] not in [160]
                or self.decoded_mmppt["mmppt_Units"] not in [2, 3]
            ):
                _LOGGER.debug(f"I{self.inverter_unit_id} is NOT Multiple MPPT")
                self.decoded_mmppt = None

            else:
                _LOGGER.debug(f"I{self.inverter_unit_id} is Multiple MPPT")

        except ModbusIOError:
            raise ModbusReadError(f"No response from inverter ID {self.inverter_unit_id}")

        except ModbusIllegalAddress:
            _LOGGER.debug(f"I{self.inverter_unit_id} is NOT Multiple MPPT")
            self.decoded_mmppt = None

        self.hub.mmppt_common[self.inverter_unit_id] = self.decoded_mmppt

        self.manufacturer = self.decoded_common["C_Manufacturer"]
        self.model = self.decoded_common["C_Model"]
        self.option = self.decoded_common["C_Option"]
        self.serial = self.decoded_common["C_SerialNumber"]
        self.device_address = self.decoded_common["C_Device_address"]
        self.name = f"{self.hub.hub_id.capitalize()} I{self.inverter_unit_id}"
        self.uid_base = f"{self.model}_{self.serial}"

        try:
            this_ver = AwesomeVersion(self.decoded_common["C_Version"])
            self._use_status_vendor4 = this_ver >= AwesomeVersion(STATUS_VENDOR4_VERSION)
        except (AwesomeVersionCompareException, AwesomeVersionStrategyException) as e:
            _LOGGER.error(f"Error checking inverter version: {e}. Please report this issue.")

        if self.decoded_mmppt is not None:
            for unit_index in range(self.decoded_mmppt["mmppt_Units"]):
                self.mmppt_units.append(SolarEdgeMMPPTUnit(self, self.hub, unit_index))
                _LOGGER.debug(f"I{self.inverter_unit_id} MMPPT Unit {unit_index}")

    async def read_modbus_data(self) -> None:
        """Read and update dynamic modbus registers."""

        try:
            inverter_data = await self.hub.modbus_read_holding_registers(
                unit=self.inverter_unit_id, address=40044, rcount=8
            )

            self.decoded_common["C_Version"] = int_list_to_string(
                ModbusClientMixin.convert_from_registers(
                    inverter_data.registers[0:8],
                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                )
            )

            inverter_data = await self.hub.modbus_read_holding_registers(
                unit=self.inverter_unit_id, address=40069, rcount=40
            )

            uint16_fields = [
                "C_SunSpec_DID",
                "C_SunSpec_Length",
                "AC_Current",
                "AC_Current_A",
                "AC_Current_B",
                "AC_Current_C",
                "AC_Voltage_AB",
                "AC_Voltage_BC",
                "AC_Voltage_CA",
                "AC_Voltage_AN",
                "AC_Voltage_BN",
                "AC_Voltage_CN",
                "AC_Frequency",
                "I_DC_Current",
                "I_DC_Voltage",
            ]
            uint16_data = (
                inverter_data.registers[0:6]
                + inverter_data.registers[7:13]
                + [inverter_data.registers[16]]
                + [inverter_data.registers[27]]
                + [inverter_data.registers[29]]
            )
            self.decoded_model = dict(
                zip(
                    uint16_fields,
                    ModbusClientMixin.convert_from_registers(
                        uint16_data,
                        data_type=ModbusClientMixin.DATATYPE.UINT16,
                    ),
                    strict=True,
                )
            )

            int16_fields = [
                "AC_Current_SF",
                "AC_Voltage_SF",
                "AC_Power",
                "AC_Power_SF",
                "AC_Frequency_SF",
                "AC_VA",
                "AC_VA_SF",
                "AC_var",
                "AC_var_SF",
                "AC_PF",
                "AC_PF_SF",
                "AC_Energy_WH_SF",
                "I_DC_Current_SF",
                "I_DC_Voltage_SF",
                "I_DC_Power",
                "I_DC_Power_SF",
                "I_Temp_Cab",
                "I_Temp_Sink",
                "I_Temp_Trns",
                "I_Temp_Other",
                "I_Temp_SF",
                "I_Status",
                "I_Status_Vendor",
            ]
            int16_data = (
                [inverter_data.registers[6]]
                + inverter_data.registers[13:16]
                + inverter_data.registers[17:24]
                + [inverter_data.registers[26]]
                + [inverter_data.registers[28]]
                + inverter_data.registers[30:40]
            )

            self.decoded_model.update(
                dict(
                    zip(
                        int16_fields,
                        ModbusClientMixin.convert_from_registers(
                            int16_data,
                            data_type=ModbusClientMixin.DATATYPE.INT16,
                        ),
                        strict=True,
                    )
                )
            )

            self.decoded_model.update(
                dict(
                    [
                        (
                            "AC_Energy_WH",
                            ModbusClientMixin.convert_from_registers(
                                inverter_data.registers[24:26],
                                data_type=ModbusClientMixin.DATATYPE.UINT32,
                            ),
                        ),
                    ]
                )
            )

            if self.use_status_vendor4:
                inverter_data = await self.hub.modbus_read_holding_registers(
                    unit=self.inverter_unit_id, address=40119, rcount=2
                )
                self.decoded_model.update(
                    dict(
                        [
                            (
                                "I_Status_Vendor4",
                                ModbusClientMixin.convert_from_registers(
                                    inverter_data.registers[0:2],
                                    data_type=ModbusClientMixin.DATATYPE.UINT32,
                                ),
                            ),
                        ]
                    )
                )

            if (
                self.decoded_model["C_SunSpec_DID"] == SunSpecNotImpl.UINT16
                or self.decoded_model["C_SunSpec_DID"] not in [101, 102, 103]
                or self.decoded_model["C_SunSpec_Length"] != 50
            ):
                raise DeviceInvalid(f"Inverter {self.inverter_unit_id} not usable.")

        except ModbusIOError:
            raise ModbusReadError(f"No response from inverter ID {self.inverter_unit_id}")

        """ Multiple MPPT Extension """
        if self.decoded_mmppt is not None:
            if self.decoded_mmppt["mmppt_Units"] == 2:
                mmppt_registers = 48
                mmppt_unit_ids = [0, 1]

            elif self.decoded_mmppt["mmppt_Units"] == 3:
                mmppt_registers = 68
                mmppt_unit_ids = [0, 1, 2]

            else:
                self.decoded_mmppt = None
                raise DeviceInvalid(f"Inverter {self.inverter_unit_id} MMPPT must be 2 or 3 units")

            try:
                inverter_data = await self.hub.modbus_read_holding_registers(
                    unit=self.inverter_unit_id, address=40123, rcount=mmppt_registers
                )

                if self.decoded_mmppt["mmppt_Units"] in [2, 3]:
                    int16_fields = [
                        "mmppt_DCA_SF",
                        "mmppt_DCV_SF",
                        "mmppt_DCW_SF",
                        "mmppt_DCWH_SF",
                        "mmppt_TmsPer",
                    ]
                    int16_data = inverter_data.registers[0:4] + [inverter_data.registers[7]]
                    self.decoded_model.update(
                        dict(
                            zip(
                                int16_fields,
                                ModbusClientMixin.convert_from_registers(
                                    int16_data,
                                    data_type=ModbusClientMixin.DATATYPE.INT16,
                                ),
                                strict=True,
                            )
                        )
                    )

                    self.decoded_model.update(
                        dict(
                            [
                                (
                                    "mmppt_Events",
                                    ModbusClientMixin.convert_from_registers(
                                        inverter_data.registers[4:6],
                                        data_type=ModbusClientMixin.DATATYPE.UINT32,
                                    ),
                                ),
                            ]
                        )
                    )

                    for mmppt_unit_id in mmppt_unit_ids:
                        unit_offset = mmppt_unit_id * 20

                        mmppt_unit_data = dict(
                            [
                                (
                                    "IDStr",  # string(16)
                                    int_list_to_string(
                                        ModbusClientMixin.convert_from_registers(
                                            inverter_data.registers[9 + unit_offset : 17 + unit_offset],
                                            data_type=ModbusClientMixin.DATATYPE.UINT16,
                                        )
                                    ),
                                ),
                                (
                                    "Tmp",
                                    ModbusClientMixin.convert_from_registers(
                                        [inverter_data.registers[24 + unit_offset]],
                                        data_type=ModbusClientMixin.DATATYPE.INT16,
                                    ),
                                ),
                            ]
                        )

                        uint16_fields = [
                            "ID",
                            "DCA",
                            "DCV",
                            "DCW",
                            "DCSt",
                        ]
                        uint16_data = (
                            [inverter_data.registers[8 + unit_offset]]
                            + [inverter_data.registers[17 + unit_offset]]
                            + [inverter_data.registers[18 + unit_offset]]
                            + [inverter_data.registers[19 + unit_offset]]
                            + [inverter_data.registers[25 + unit_offset]]
                        )
                        mmppt_unit_data.update(
                            dict(
                                zip(
                                    uint16_fields,
                                    ModbusClientMixin.convert_from_registers(
                                        uint16_data,
                                        data_type=ModbusClientMixin.DATATYPE.UINT16,
                                    ),
                                    strict=True,
                                )
                            )
                        )

                        uint32_fields = [
                            "DCWH",
                            "Tms",
                            "DCEvt",
                        ]
                        uint32_data = (
                            inverter_data.registers[20 + unit_offset : 22 + unit_offset]
                            + inverter_data.registers[22 + unit_offset : 24 + unit_offset]
                            + inverter_data.registers[26 + unit_offset : 28 + unit_offset]
                        )
                        mmppt_unit_data.update(
                            dict(
                                zip(
                                    uint32_fields,
                                    ModbusClientMixin.convert_from_registers(
                                        uint32_data,
                                        data_type=ModbusClientMixin.DATATYPE.UINT32,
                                    ),
                                    strict=True,
                                )
                            )
                        )

                        self.decoded_model.update(dict([(f"mmppt_{mmppt_unit_id}", mmppt_unit_data)]))

            except ModbusIOError:
                raise ModbusReadError(f"No response from inverter ID {self.inverter_unit_id}")

        """ Global Dynamic Power Control and Status """
        if self.hub.option_detect_extras is True and (
            self.global_power_control is True or self.global_power_control is None
        ):
            try:
                async with asyncio.timeout(SolarEdgeTimeouts.Read / 1000):
                    inverter_data = await self.hub.modbus_read_holding_registers(
                        unit=self.inverter_unit_id, address=61440, rcount=4
                    )

                    self.decoded_model.update(
                        dict(
                            [
                                (
                                    "I_RRCR",
                                    ModbusClientMixin.convert_from_registers(
                                        [inverter_data.registers[0]],
                                        data_type=ModbusClientMixin.DATATYPE.UINT16,
                                        word_order="little",
                                    ),
                                ),
                                (
                                    "I_Power_Limit",
                                    ModbusClientMixin.convert_from_registers(
                                        [inverter_data.registers[1]],
                                        data_type=ModbusClientMixin.DATATYPE.UINT16,
                                        word_order="little",
                                    ),
                                ),
                                (
                                    "I_CosPhi",
                                    ModbusClientMixin.convert_from_registers(
                                        inverter_data.registers[2:4],
                                        data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                                        word_order="little",
                                    ),
                                ),
                            ]
                        )
                    )

                    self.global_power_control = True

            except ModbusIllegalAddress:
                self.global_power_control = False
                _LOGGER.debug(f"I{self.inverter_unit_id}: global power control NOT available")

            except (TimeoutError, ModbusIOException):
                ir.async_create_issue(
                    self.hub._hass,
                    DOMAIN,
                    "detect_timeout_gpc",
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="detect_timeout_gpc",
                    data={"entry_id": self.hub._entry_id},
                )
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: The inverter did not respond while "
                    "reading data for Global Dynamic Power Controls. These entities "
                    "will be unavailable."
                )

            except ModbusIOError:
                raise ModbusReadError(f"No response from inverter ID {self.inverter_unit_id}")

            finally:
                if not self.hub.is_connected:
                    await self.hub.connect()

        """ Advanced Power Control """
        """ Power Control Block """
        if self.hub.option_detect_extras is True and (
            self.advanced_power_control is True or self.advanced_power_control is None
        ):
            try:
                async with asyncio.timeout(SolarEdgeTimeouts.Read / 1000):
                    inverter_data = await self.hub.modbus_read_holding_registers(
                        unit=self.inverter_unit_id, address=61696, rcount=86
                    )

                    int32_fields = [
                        "PwrFrqDeratingConfig",
                        "ReactivePwrConfig",
                        "ActivePwrGrad",
                        "AdvPwrCtrlEn",
                        "FrtEn",
                    ]
                    int32_data = (
                        inverter_data.registers[2:6] + inverter_data.registers[8:10] + inverter_data.registers[66:70]
                    )
                    self.decoded_model.update(
                        dict(
                            zip(
                                int32_fields,
                                ModbusClientMixin.convert_from_registers(
                                    int32_data,
                                    data_type=ModbusClientMixin.DATATYPE.INT32,
                                    word_order="little",
                                ),
                                strict=True,
                            )
                        )
                    )

                    float32_fields = [
                        "FixedCosPhiPhase",
                        "FixedReactPwr",
                        "ReactCosPhiVsPX_0",
                        "ReactCosPhiVsPX_1",
                        "ReactCosPhiVsPX_2",
                        "ReactCosPhiVsPX_3",
                        "ReactCosPhiVsPX_4",
                        "ReactCosPhiVsPX_5",
                        "ReactCosPhiVsPY_0",
                        "ReactCosPhiVsPY_1",
                        "ReactCosPhiVsPY_2",
                        "ReactCosPhiVsPY_3",
                        "ReactCosPhiVsPY_4",
                        "ReactCosPhiVsPY_5",
                        "ReactQVsVgX_0",
                        "ReactQVsVgX_1",
                        "ReactQVsVgX_2",
                        "ReactQVsVgX_3",
                        "ReactQVsVgX_4",
                        "ReactQVsVgX_5",
                        "ReactQVsVgY_0",
                        "ReactQVsVgY_1",
                        "ReactQVsVgY_2",
                        "ReactQVsVgY_3",
                        "ReactQVsVgY_4",
                        "ReactQVsVgY_5",
                        "FRT_KFactor",
                        "PowerReduce",
                        "MaxWakeupFreq",
                        "MinWakeupFreq",
                        "MaxWakeupVg",
                        "MinWakeupVg",
                        "Vnom",
                        "Inom",
                        "PwrVsFreqX_0",
                        "PwrVsFreqX_1",
                    ]
                    float32_data = inverter_data.registers[10:66] + inverter_data.registers[70:86]
                    self.decoded_model.update(
                        dict(
                            zip(
                                float32_fields,
                                ModbusClientMixin.convert_from_registers(
                                    float32_data,
                                    data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                                    word_order="little",
                                ),
                                strict=True,
                            )
                        )
                    )

                    self.decoded_model.update(
                        dict(
                            [
                                (
                                    "CommitPwrCtlSettings",
                                    ModbusClientMixin.convert_from_registers(
                                        [inverter_data.registers[0]],
                                        data_type=ModbusClientMixin.DATATYPE.INT16,
                                        word_order="little",
                                    ),
                                ),
                                (
                                    "RestorePwrCtlDefaults",
                                    ModbusClientMixin.convert_from_registers(
                                        [inverter_data.registers[1]],
                                        data_type=ModbusClientMixin.DATATYPE.INT16,
                                        word_order="little",
                                    ),
                                ),
                                (
                                    "ReactPwrIterTime",
                                    ModbusClientMixin.convert_from_registers(
                                        inverter_data.registers[6:8],
                                        data_type=ModbusClientMixin.DATATYPE.UINT32,
                                        word_order="little",
                                    ),
                                ),
                            ]
                        )
                    )

                async with asyncio.timeout(SolarEdgeTimeouts.Read / 1000):
                    inverter_data = await self.hub.modbus_read_holding_registers(
                        unit=self.inverter_unit_id, address=61782, rcount=84
                    )

                    float32_fields = [
                        "PwrVsFreqY_0",
                        "PwrVsFreqY_1",
                        "ResetFreq",
                        "MaxFreq",
                        "ReactQVsPX_0",
                        "ReactQVsPX_1",
                        "ReactQVsPX_2",
                        "ReactQVsPX_3",
                        "ReactQVsPX_4",
                        "ReactQVsPX_5",
                        "ReactQVsPY_0",
                        "ReactQVsPY_1",
                        "ReactQVsPY_2",
                        "ReactQVsPY_3",
                        "ReactQVsPY_4",
                        "ReactQVsPY_5",
                        "ReactCosPhiVsPVgLockInMax",
                        "ReactCosPhiVsPVgLockInMin",
                        "ReactCosPhiVsPVgLockOutMax",
                        "ReactCosPhiVsPVgLockOutMin",
                        "ReactQVsVgPLockInMax",
                        "ReactQVsVgPLockInMin",
                        "ReactQVsVgPLockOutMax",
                        "ReactQVsVgPLockOutMin",
                        "MaxCurrent",
                        "PwrVsVgX_0",
                        "PwrVsVgX_1",
                        "PwrVsVgX_2",
                        "PwrVsVgX_3",
                        "PwrVsVgX_4",
                        "PwrVsVgX_5",
                        "PwrVsVgY_0",
                        "PwrVsVgY_1",
                        "PwrVsVgY_2",
                        "PwrVsVgY_3",
                        "PwrVsVgY_4",
                        "PwrVsVgY_5",
                        "DisconnectAtZeroPwrLim",
                    ]
                    float32_data = (
                        inverter_data.registers[0:32] + inverter_data.registers[36:52] + inverter_data.registers[56:84]
                    )
                    self.decoded_model.update(
                        dict(
                            zip(
                                float32_fields,
                                ModbusClientMixin.convert_from_registers(
                                    float32_data,
                                    data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                                    word_order="little",
                                ),
                                strict=True,
                            )
                        )
                    )

                    uint32_fields = [
                        "PwrFrqDeratingResetTime",
                        "PwrFrqDeratingGradTime",
                        "ReactQVsVgType",
                        "PwrSoftStartTime",
                    ]
                    uint32_data = inverter_data.registers[32:36] + inverter_data.registers[52:56]
                    self.decoded_model.update(
                        dict(
                            zip(
                                uint32_fields,
                                ModbusClientMixin.convert_from_registers(
                                    uint32_data,
                                    data_type=ModbusClientMixin.DATATYPE.UINT32,
                                    word_order="little",
                                ),
                                strict=True,
                            )
                        )
                    )

                    self.advanced_power_control = True

            except ModbusIllegalAddress:
                self.advanced_power_control = False
                _LOGGER.debug(f"I{self.inverter_unit_id}: advanced power control NOT available")

            except (TimeoutError, ModbusIOException):
                ir.async_create_issue(
                    self.hub._hass,
                    DOMAIN,
                    "detect_timeout_apc",
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="detect_timeout_apc",
                    data={"entry_id": self.hub._entry_id},
                )
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: The inverter did not respond while "
                    "reading data for Advanced Power Controls. These entities "
                    "will be unavailable."
                )

            except ModbusIOError:
                raise ModbusReadError(f"No response from inverter ID {self.inverter_unit_id}")

            finally:
                if not self.hub.is_connected:
                    await self.hub.connect()

        """ Power Control Options: Site Limit Control """
        if self.hub.option_site_limit_control is True and self.site_limit_control is not False:
            """Site Limit and Mode"""
            try:
                inverter_data = await self.hub.modbus_read_holding_registers(
                    unit=self.inverter_unit_id, address=57344, rcount=4
                )

                self.decoded_model.update(
                    dict(
                        [
                            (
                                "E_Lim_Ctl_Mode",
                                ModbusClientMixin.convert_from_registers(
                                    [inverter_data.registers[0]],
                                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                                    word_order="little",
                                ),
                            ),
                            (
                                "E_Lim_Ctl",
                                ModbusClientMixin.convert_from_registers(
                                    [inverter_data.registers[1]],
                                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                                    word_order="little",
                                ),
                            ),
                            (
                                "E_Site_Limit",
                                ModbusClientMixin.convert_from_registers(
                                    inverter_data.registers[2:4],
                                    data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                                    word_order="little",
                                ),
                            ),
                        ]
                    )
                )

                self.site_limit_control = True

            except ModbusIllegalAddress:
                self.site_limit_control = False
                _LOGGER.debug(f"I{self.inverter_unit_id}: site limit control NOT available")

            except ModbusIOError:
                raise ModbusReadError(f"No response from inverter ID {self.inverter_unit_id}")

            """ External Production Max Power """
            try:
                inverter_data = await self.hub.modbus_read_holding_registers(
                    unit=self.inverter_unit_id, address=57362, rcount=2
                )

                self.decoded_model.update(
                    dict(
                        [
                            (
                                "Ext_Prod_Max",
                                ModbusClientMixin.convert_from_registers(
                                    inverter_data.registers[0:2],
                                    data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                                    word_order="little",
                                ),
                            ),
                        ]
                    )
                )

            except ModbusIllegalAddress:
                try:
                    del self.decoded_model["Ext_Prod_Max"]
                except KeyError:
                    pass

                _LOGGER.debug(f"I{self.inverter_unit_id}: Ext_Prod_Max NOT available")

            except ModbusIOError:
                raise ModbusReadError(f"No response from inverter ID {self.inverter_unit_id}")

        """ Grid On/Off Status """
        if self._grid_status is not False:
            try:
                inverter_data = await self.hub.modbus_read_holding_registers(
                    unit=self.inverter_unit_id, address=40113, rcount=2
                )

                self.decoded_model.update(
                    dict(
                        [
                            (
                                "I_Grid_Status",
                                ModbusClientMixin.convert_from_registers(
                                    inverter_data.registers[0:2],
                                    data_type=ModbusClientMixin.DATATYPE.UINT32,
                                    word_order="little",
                                ),
                            ),
                        ]
                    )
                )
                self._grid_status = True

            except ModbusIllegalAddress:
                self._grid_status = False
                _LOGGER.debug(f"I{self.inverter_unit_id}: Grid On/Off NOT available")

            except ModbusIOException as e:
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: A modbus I/O exception occurred "
                    "while reading data for Grid On/Off Status. This entity "
                    f"will be unavailable: {e}"
                )

            except ModbusIOError:
                raise ModbusReadError(f"No response from inverter ID {self.inverter_unit_id}")

            finally:
                if not self.hub.is_connected:
                    await self.hub.connect()

        for name, value in iter(self.decoded_model.items()):
            if isinstance(value, float):
                display_value = float_to_hex(value)
            else:
                display_value = hex(value) if isinstance(value, int) else value
            _LOGGER.debug(f"I{self.inverter_unit_id}: {name} {display_value} {type(value)}")

        """ Power Control Options: Storage Control """
        if self.hub.option_storage_control is True and self.decoded_storage_control is not False:
            if self.has_battery is None:
                self.has_battery = False
                for battery in self.hub.batteries:
                    if self.inverter_unit_id == battery.inverter_unit_id:
                        self.has_battery = True

            try:
                inverter_data = await self.hub.modbus_read_holding_registers(
                    unit=self.inverter_unit_id, address=57348, rcount=14
                )

                uint16_fields = [
                    "control_mode",
                    "ac_charge_policy",
                    "default_mode",
                    "command_mode",
                ]
                uint16_data = inverter_data.registers[0:2] + [inverter_data.registers[6]] + [inverter_data.registers[9]]
                self.decoded_storage_control = dict(
                    zip(
                        uint16_fields,
                        ModbusClientMixin.convert_from_registers(
                            uint16_data,
                            data_type=ModbusClientMixin.DATATYPE.UINT16,
                            word_order="little",
                        ),
                        strict=True,
                    )
                )

                float32_fields = [
                    "ac_charge_limit",
                    "backup_reserve",
                    "charge_limit",
                    "discharge_limit",
                ]
                float32_data = inverter_data.registers[2:6] + inverter_data.registers[10:14]
                self.decoded_storage_control.update(
                    dict(
                        zip(
                            float32_fields,
                            ModbusClientMixin.convert_from_registers(
                                float32_data,
                                data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                                word_order="little",
                            ),
                            strict=True,
                        )
                    )
                )

                self.decoded_storage_control.update(
                    dict(
                        [
                            (
                                "command_timeout",
                                ModbusClientMixin.convert_from_registers(
                                    inverter_data.registers[7:9],
                                    data_type=ModbusClientMixin.DATATYPE.UINT32,
                                    word_order="little",
                                ),
                            ),
                        ]
                    )
                )

                for name, value in iter(self.decoded_storage_control.items()):
                    if isinstance(value, float):
                        display_value = float_to_hex(value)
                    else:
                        display_value = hex(value) if isinstance(value, int) else value
                    _LOGGER.debug(f"I{self.inverter_unit_id}: {name} {display_value} {type(value)}")

            except ModbusIllegalAddress:
                self.decoded_storage_control = False
                _LOGGER.debug(f"I{self.inverter_unit_id}: storage control NOT available")

            except ModbusIOError:
                raise ModbusReadError(f"No response from inverter ID {self.inverter_unit_id}")

    async def write_registers(self, address, payload) -> None:
        """Write inverter register."""
        await self.hub.write_registers(self.inverter_unit_id, address, payload)

    def set_last_update(self, timestamp) -> None:
        self._last_update_timestamp = timestamp

    @property
    def online(self) -> bool:
        """Device is online."""
        return self.hub.online

    @property
    def fw_version(self) -> str | None:
        if "C_Version" in self.decoded_common:
            return self.decoded_common["C_Version"]

        return None

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
        )

    @property
    def is_mmppt(self) -> bool:
        if self.decoded_mmppt is None:
            return False

        return True

    @property
    def last_update(self) -> datetime.datetime | None:
        return self._last_update_timestamp

    @property
    def use_status_vendor4(self) -> bool:
        return self._use_status_vendor4


class SolarEdgeMMPPTUnit:
    """Defines a SolarEdge inverter MMPPT unit."""

    def __init__(self, inverter: SolarEdgeInverter, hub: SolarEdgeModbusMultiHub, unit: int) -> None:
        self.inverter = inverter
        self.hub = hub
        self.unit = unit
        self.mmppt_key = f"mmppt_{self.unit}"

    @property
    def online(self) -> bool:
        """Device is online."""
        return self.hub.online and self.inverter.is_mmppt and self.inverter.online

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.inverter.uid_base, self.mmppt_key)},
            name=f"{self.inverter.name} MPPT{self.unit}",
            manufacturer=self.inverter.manufacturer,
            model=self.inverter.model,
            hw_version=f"ID {self.mmppt_id}",
            serial_number=f"{self.mmppt_idstr}",
            via_device=(DOMAIN, self.inverter.uid_base),
        )

    @property
    def mmppt_id(self) -> str:
        return self.inverter.decoded_model[self.mmppt_key]["ID"]

    @property
    def mmppt_idstr(self) -> str:
        return self.inverter.decoded_model[self.mmppt_key]["IDStr"]
