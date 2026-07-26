"""SolarEdge device classes: inverter, MMPPT unit, meter, battery, EVSE.

Each class owns its register reads and decoding; the hub passed to the
constructor provides the modbus session, options, and shared state.
Split out of hub.py (which keeps orchestration and re-exports these
names for compatibility).
"""

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

from .const import (
    BATTERY_REG_BASE,
    DETECT_EVSE_REGEX,
    DOMAIN,
    METER_REG_BASE,
    STATUS_VENDOR4_VERSION,
    SolarEdgeTimeouts,
    SunSpecNotImpl,
    detect_timeout_issue_id,
)
from .exceptions import (
    DeviceInvalid,
    DeviceIsEVSE,
    ModbusIllegalAddress,
    ModbusIllegalFunction,
    ModbusIllegalValue,
    ModbusIOError,
    ModbusReadError,
)
from .helpers import float_to_hex, int_list_to_string

if TYPE_CHECKING:
    from .hub import SolarEdgeModbusMultiHub

_LOGGER = logging.getLogger(__name__)


def log_decoded(prefix: str, decoded: dict) -> None:
    """Debug-dump decoded values in hex."""
    if not _LOGGER.isEnabledFor(logging.DEBUG):
        return

    for name, value in decoded.items():
        if isinstance(value, float):
            display_value = float_to_hex(value)
        else:
            display_value = hex(value) if isinstance(value, int) else value
        _LOGGER.debug(f"{prefix}: {name} {display_value} {type(value)}")


# Field names decoded from each optional register block. Also used to
# drop stale values when a block becomes unavailable (tiered polling
# retains decoded_model values between slow poll cycles).
GPC_DECODED_KEYS = ("I_RRCR", "I_Power_Limit", "I_CosPhi")
SITE_LIMIT_DECODED_KEYS = (
    "E_Lim_Ctl_Mode",
    "E_Lim_Ctl",
    "E_Site_Limit",
    "Ext_Prod_Max",
)
GRID_STATUS_DECODED_KEYS = ("I_Grid_Status",)
APC_INT32_FIELDS = [
    "PwrFrqDeratingConfig",
    "ReactivePwrConfig",
    "ActivePwrGrad",
    "AdvPwrCtrlEn",
    "FrtEn",
]
APC_BLOCK1_FLOAT32_FIELDS = [
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
APC_BLOCK2_FLOAT32_FIELDS = [
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
APC_UINT32_FIELDS = [
    "PwrFrqDeratingResetTime",
    "PwrFrqDeratingGradTime",
    "ReactQVsVgType",
    "PwrSoftStartTime",
]
APC_DECODED_KEYS = (
    "CommitPwrCtlSettings",
    "RestorePwrCtlDefaults",
    "ReactPwrIterTime",
    *APC_INT32_FIELDS,
    *APC_BLOCK1_FLOAT32_FIELDS,
    *APC_BLOCK2_FLOAT32_FIELDS,
    *APC_UINT32_FIELDS,
)


def drop_decoded(decoded: dict, keys) -> None:
    """Remove block values so their entities go unavailable, not stale."""
    for key in keys:
        decoded.pop(key, None)


def decode_sunspec_string(registers: list[int], word_order: str = "big") -> str:
    """Decode a SunSpec string field from a span of UINT16 registers."""
    return int_list_to_string(
        ModbusClientMixin.convert_from_registers(
            registers,
            data_type=ModbusClientMixin.DATATYPE.UINT16,
            word_order=word_order,
        )
    )


def decode_sunspec_common_block(registers: list[int]) -> dict:
    """Decode the SunSpec common model block shared by inverters and meters.

    `registers` must start at the C_SunSpec_DID register — the inverter's
    2-register C_SunSpec_ID header, when present, is decoded by the caller.
    Layout: DID, Length, Manufacturer(32), Model(32), Option(16),
    Version(16), SerialNumber(32), Device_address. Validation of the decoded
    values stays with each caller.
    """
    decoded = dict(
        zip(
            ["C_SunSpec_DID", "C_SunSpec_Length", "C_Device_address"],
            ModbusClientMixin.convert_from_registers(
                registers[0:2] + [registers[66]],
                data_type=ModbusClientMixin.DATATYPE.UINT16,
            ),
        )
    )

    decoded.update(
        {
            "C_Manufacturer": decode_sunspec_string(registers[2:18]),  # string(32)
            "C_Model": decode_sunspec_string(registers[18:34]),  # string(32)
            "C_Option": decode_sunspec_string(registers[34:42]),  # string(16)
            "C_Version": decode_sunspec_string(registers[42:50]),  # string(16)
            "C_SerialNumber": decode_sunspec_string(registers[50:66]),  # string(32)
        }
    )

    return decoded


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

            # The inverter block has a 2-register C_SunSpec_ID header; the
            # rest is the standard common model starting at C_SunSpec_DID.
            self.decoded_common = {
                "C_SunSpec_ID": ModbusClientMixin.convert_from_registers(
                    inverter_data.registers[0:2],
                    data_type=ModbusClientMixin.DATATYPE.UINT32,
                ),
                **decode_sunspec_common_block(inverter_data.registers[2:]),
            }

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

        except (ModbusIllegalAddress, ModbusIllegalFunction, ModbusIllegalValue):
            raise DeviceInvalid(
                f"ID {self.inverter_unit_id} is not a SunSpec inverter."
            )

        if DETECT_EVSE_REGEX.match(self.decoded_common["C_Model"]):
            raise DeviceIsEVSE(f"Model {self.decoded_common['C_Model']}")

        if (
            self.decoded_common["C_SunSpec_ID"] == SunSpecNotImpl.UINT32
            or self.decoded_common["C_SunSpec_DID"] == SunSpecNotImpl.UINT16
            or self.decoded_common["C_SunSpec_ID"] != 0x53756E53
            or self.decoded_common["C_SunSpec_DID"] != 0x0001
            or self.decoded_common["C_SunSpec_Length"] != 65
        ):
            raise DeviceInvalid(
                f"ID {self.inverter_unit_id} is not a SunSpec inverter."
            )

        try:
            mmppt_common = await self.hub.modbus_read_holding_registers(
                unit=self.inverter_unit_id, address=40121, rcount=9
            )

            self.decoded_mmppt = {
                "mmppt_DID": ModbusClientMixin.convert_from_registers(
                    [mmppt_common.registers[0]],
                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                ),
                "mmppt_Length": ModbusClientMixin.convert_from_registers(
                    [mmppt_common.registers[1]],
                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                ),
                "mmppt_Units": ModbusClientMixin.convert_from_registers(
                    [mmppt_common.registers[8]],
                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                ),
            }

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
            raise ModbusReadError(
                f"No response from inverter ID {self.inverter_unit_id}"
            )

        except (ModbusIllegalAddress, ModbusIllegalFunction, ModbusIllegalValue):
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
            self._use_status_vendor4 = this_ver >= AwesomeVersion(
                STATUS_VENDOR4_VERSION
            )
        except (AwesomeVersionCompareException, AwesomeVersionStrategyException) as e:
            _LOGGER.error(
                f"Error checking inverter version: {e}. Please report this issue."
            )

        if self.decoded_mmppt is not None:
            for unit_index in range(self.decoded_mmppt["mmppt_Units"]):
                self.mmppt_units.append(SolarEdgeMMPPTUnit(self, self.hub, unit_index))
                _LOGGER.debug(f"I{self.inverter_unit_id} MMPPT Unit {unit_index}")

    async def read_modbus_data(self) -> None:
        """Read and update dynamic modbus registers."""

        try:
            # Merged read: address=40044 rcount=65 covers both C_Version
            # (40044-40051, 8 regs) and main inverter data (40069-40108, 40 regs).
            # Gap of 17 unused registers (40052-40068) is included in the read.
            inverter_data = await self.hub.modbus_read_holding_registers(
                unit=self.inverter_unit_id, address=40044, rcount=65
            )

            # C_Version: registers[0:8] (address 40044-40051). Static at runtime and
            # already decoded in init_device — skip the per-cycle re-decode.
            if "C_Version" not in self.decoded_common:
                self.decoded_common["C_Version"] = decode_sunspec_string(
                    inverter_data.registers[0:8]
                )

            # Main inverter data starts at offset 25 (address 40069 - 40044 = 25)
            # All register indices below are offset +25 from the original code.
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
                "AC_Energy_WH_SF",
                "I_DC_Current",
                "I_DC_Voltage",
                "I_Status",
                "I_Status_Vendor",
            ]
            uint16_data = (
                inverter_data.registers[25:31]
                + inverter_data.registers[32:38]
                + [inverter_data.registers[41]]
                + inverter_data.registers[51:53]
                + [inverter_data.registers[54]]
                + inverter_data.registers[63:65]
            )
            # Update in place: values read on slow poll cycles (power control,
            # site limit, storage) must survive the fast polls in between.
            self.decoded_model.update(
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
                "I_DC_Current_SF",
                "I_DC_Voltage_SF",
                "I_DC_Power",
                "I_DC_Power_SF",
                "I_Temp_Cab",
                "I_Temp_Sink",
                "I_Temp_Trns",
                "I_Temp_Other",
                "I_Temp_SF",
            ]
            int16_data = (
                [inverter_data.registers[31]]
                + inverter_data.registers[38:41]
                + inverter_data.registers[42:49]
                + [inverter_data.registers[53]]
                + inverter_data.registers[55:63]
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
                {
                    "AC_Energy_WH": ModbusClientMixin.convert_from_registers(
                        inverter_data.registers[49:51],
                        data_type=ModbusClientMixin.DATATYPE.UINT32,
                    ),
                }
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
            raise ModbusReadError(
                f"No response from inverter ID {self.inverter_unit_id}"
            )

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
                raise DeviceInvalid(
                    f"Inverter {self.inverter_unit_id} MMPPT must be 2 or 3 units"
                )

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
                    int16_data = inverter_data.registers[0:4] + [
                        inverter_data.registers[7]
                    ]
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
                        {
                            "mmppt_Events": ModbusClientMixin.convert_from_registers(
                                inverter_data.registers[4:6],
                                data_type=ModbusClientMixin.DATATYPE.UINT32,
                            ),
                        }
                    )

                    for mmppt_unit_id in mmppt_unit_ids:
                        unit_offset = mmppt_unit_id * 20

                        mmppt_unit_data = {
                            "IDStr": int_list_to_string(  # string(16)
                                ModbusClientMixin.convert_from_registers(
                                    inverter_data.registers[
                                        9 + unit_offset : 17 + unit_offset
                                    ],
                                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                                )
                            ),
                            "Tmp": ModbusClientMixin.convert_from_registers(
                                [inverter_data.registers[24 + unit_offset]],
                                data_type=ModbusClientMixin.DATATYPE.INT16,
                            ),
                        }

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
                            + inverter_data.registers[
                                22 + unit_offset : 24 + unit_offset
                            ]
                            + inverter_data.registers[
                                26 + unit_offset : 28 + unit_offset
                            ]
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

                        self.decoded_model.update(
                            {f"mmppt_{mmppt_unit_id}": mmppt_unit_data}
                        )

            except ModbusIOError:
                raise ModbusReadError(
                    f"No response from inverter ID {self.inverter_unit_id}"
                )

        """ Global Dynamic Power Control and Status """
        if (
            self.hub.option_detect_extras is True
            and (self.global_power_control is True or self.global_power_control is None)
            and (self.hub.slow_poll_due or self.global_power_control is None)
        ):
            try:
                async with asyncio.timeout(SolarEdgeTimeouts.Read / 1000):
                    inverter_data = await self.hub.modbus_read_holding_registers(
                        unit=self.inverter_unit_id, address=61440, rcount=4
                    )

                    self.decoded_model.update(
                        {
                            "I_RRCR": ModbusClientMixin.convert_from_registers(
                                [inverter_data.registers[0]],
                                data_type=ModbusClientMixin.DATATYPE.UINT16,
                                word_order="little",
                            ),
                            "I_Power_Limit": ModbusClientMixin.convert_from_registers(
                                [inverter_data.registers[1]],
                                data_type=ModbusClientMixin.DATATYPE.UINT16,
                                word_order="little",
                            ),
                            "I_CosPhi": ModbusClientMixin.convert_from_registers(
                                inverter_data.registers[2:4],
                                data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                                word_order="little",
                            ),
                        }
                    )

                    self.global_power_control = True
                    ir.async_delete_issue(
                        self.hub._hass,
                        DOMAIN,
                        detect_timeout_issue_id(
                            "gpc", self.hub._entry_id, self.inverter_unit_id
                        ),
                    )

            except (ModbusIllegalAddress, ModbusIllegalFunction, ModbusIllegalValue):
                self.global_power_control = False
                ir.async_delete_issue(
                    self.hub._hass,
                    DOMAIN,
                    detect_timeout_issue_id(
                        "gpc", self.hub._entry_id, self.inverter_unit_id
                    ),
                )
                drop_decoded(self.decoded_model, GPC_DECODED_KEYS)
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: global power control NOT available"
                )

            except (TimeoutError, ModbusIOException):
                ir.async_create_issue(
                    self.hub._hass,
                    DOMAIN,
                    detect_timeout_issue_id(
                        "gpc", self.hub._entry_id, self.inverter_unit_id
                    ),
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="detect_timeout_gpc",
                    data={"entry_id": self.hub._entry_id},
                )
                drop_decoded(self.decoded_model, GPC_DECODED_KEYS)
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: The inverter did not respond while "
                    "reading data for Global Dynamic Power Controls. These entities "
                    "will be unavailable."
                )

            except ModbusIOError:
                raise ModbusReadError(
                    f"No response from inverter ID {self.inverter_unit_id}"
                )

            finally:
                await self.hub.connect()

        """ Advanced Power Control """
        """ Power Control Block """
        if (
            self.hub.option_detect_extras is True
            and (
                self.advanced_power_control is True
                or self.advanced_power_control is None
            )
            and (self.hub.slow_poll_due or self.advanced_power_control is None)
        ):
            try:
                async with asyncio.timeout(SolarEdgeTimeouts.Read / 1000):
                    inverter_data = await self.hub.modbus_read_holding_registers(
                        unit=self.inverter_unit_id, address=61696, rcount=86
                    )

                    int32_fields = APC_INT32_FIELDS
                    int32_data = (
                        inverter_data.registers[2:6]
                        + inverter_data.registers[8:10]
                        + inverter_data.registers[66:70]
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

                    float32_fields = APC_BLOCK1_FLOAT32_FIELDS
                    float32_data = (
                        inverter_data.registers[10:66] + inverter_data.registers[70:86]
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

                    self.decoded_model.update(
                        {
                            "CommitPwrCtlSettings": ModbusClientMixin.convert_from_registers(
                                [inverter_data.registers[0]],
                                data_type=ModbusClientMixin.DATATYPE.INT16,
                                word_order="little",
                            ),
                            "RestorePwrCtlDefaults": ModbusClientMixin.convert_from_registers(
                                [inverter_data.registers[1]],
                                data_type=ModbusClientMixin.DATATYPE.INT16,
                                word_order="little",
                            ),
                            "ReactPwrIterTime": ModbusClientMixin.convert_from_registers(
                                inverter_data.registers[6:8],
                                data_type=ModbusClientMixin.DATATYPE.UINT32,
                                word_order="little",
                            ),
                        }
                    )

                async with asyncio.timeout(SolarEdgeTimeouts.Read / 1000):
                    inverter_data = await self.hub.modbus_read_holding_registers(
                        unit=self.inverter_unit_id, address=61782, rcount=84
                    )

                    float32_fields = APC_BLOCK2_FLOAT32_FIELDS
                    float32_data = (
                        inverter_data.registers[0:32]
                        + inverter_data.registers[36:52]
                        + inverter_data.registers[56:84]
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

                    uint32_fields = APC_UINT32_FIELDS
                    uint32_data = (
                        inverter_data.registers[32:36] + inverter_data.registers[52:56]
                    )
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
                    ir.async_delete_issue(
                        self.hub._hass,
                        DOMAIN,
                        detect_timeout_issue_id(
                            "apc", self.hub._entry_id, self.inverter_unit_id
                        ),
                    )

            except (ModbusIllegalAddress, ModbusIllegalFunction, ModbusIllegalValue):
                self.advanced_power_control = False
                ir.async_delete_issue(
                    self.hub._hass,
                    DOMAIN,
                    detect_timeout_issue_id(
                        "apc", self.hub._entry_id, self.inverter_unit_id
                    ),
                )
                drop_decoded(self.decoded_model, APC_DECODED_KEYS)
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: advanced power control NOT available"
                )

            except (TimeoutError, ModbusIOException):
                ir.async_create_issue(
                    self.hub._hass,
                    DOMAIN,
                    detect_timeout_issue_id(
                        "apc", self.hub._entry_id, self.inverter_unit_id
                    ),
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="detect_timeout_apc",
                    data={"entry_id": self.hub._entry_id},
                )
                drop_decoded(self.decoded_model, APC_DECODED_KEYS)
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: The inverter did not respond while "
                    "reading data for Advanced Power Controls. These entities "
                    "will be unavailable."
                )

            except ModbusIOError:
                raise ModbusReadError(
                    f"No response from inverter ID {self.inverter_unit_id}"
                )

            finally:
                await self.hub.connect()

        """ Power Control Options: Site Limit Control """
        if (
            self.hub.option_site_limit_control is True
            and self.site_limit_control is not False
            and (self.hub.slow_poll_due or self.site_limit_control is None)
        ):
            """Site Limit and Mode"""
            try:
                inverter_data = await self.hub.modbus_read_holding_registers(
                    unit=self.inverter_unit_id, address=57344, rcount=4
                )

                self.decoded_model.update(
                    {
                        "E_Lim_Ctl_Mode": ModbusClientMixin.convert_from_registers(
                            [inverter_data.registers[0]],
                            data_type=ModbusClientMixin.DATATYPE.UINT16,
                            word_order="little",
                        ),
                        "E_Lim_Ctl": ModbusClientMixin.convert_from_registers(
                            [inverter_data.registers[1]],
                            data_type=ModbusClientMixin.DATATYPE.UINT16,
                            word_order="little",
                        ),
                        "E_Site_Limit": ModbusClientMixin.convert_from_registers(
                            inverter_data.registers[2:4],
                            data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                            word_order="little",
                        ),
                    }
                )

                self.site_limit_control = True

            except (ModbusIllegalAddress, ModbusIllegalFunction, ModbusIllegalValue):
                self.site_limit_control = False
                drop_decoded(self.decoded_model, SITE_LIMIT_DECODED_KEYS)
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: site limit control NOT available"
                )

            except ModbusIOError:
                raise ModbusReadError(
                    f"No response from inverter ID {self.inverter_unit_id}"
                )

            """ External Production Max Power """
            try:
                inverter_data = await self.hub.modbus_read_holding_registers(
                    unit=self.inverter_unit_id, address=57362, rcount=2
                )

                self.decoded_model.update(
                    {
                        "Ext_Prod_Max": ModbusClientMixin.convert_from_registers(
                            inverter_data.registers[0:2],
                            data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                            word_order="little",
                        ),
                    }
                )

            except (ModbusIllegalAddress, ModbusIllegalFunction, ModbusIllegalValue):
                try:
                    del self.decoded_model["Ext_Prod_Max"]
                except KeyError:
                    pass

                _LOGGER.debug(f"I{self.inverter_unit_id}: Ext_Prod_Max NOT available")

            except ModbusIOError:
                raise ModbusReadError(
                    f"No response from inverter ID {self.inverter_unit_id}"
                )

        """ Grid On/Off Status """
        if self._grid_status is not False:
            try:
                inverter_data = await self.hub.modbus_read_holding_registers(
                    unit=self.inverter_unit_id, address=40113, rcount=2
                )

                self.decoded_model.update(
                    {
                        "I_Grid_Status": ModbusClientMixin.convert_from_registers(
                            inverter_data.registers[0:2],
                            data_type=ModbusClientMixin.DATATYPE.UINT32,
                            word_order="little",
                        ),
                    }
                )
                self._grid_status = True

            except (ModbusIllegalAddress, ModbusIllegalFunction, ModbusIllegalValue):
                self._grid_status = False
                drop_decoded(self.decoded_model, GRID_STATUS_DECODED_KEYS)
                _LOGGER.debug(f"I{self.inverter_unit_id}: Grid On/Off NOT available")

            except ModbusIOException as e:
                drop_decoded(self.decoded_model, GRID_STATUS_DECODED_KEYS)
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: A modbus I/O exception occurred "
                    "while reading data for Grid On/Off Status. This entity "
                    f"will be unavailable: {e}"
                )

            except ModbusIOError:
                raise ModbusReadError(
                    f"No response from inverter ID {self.inverter_unit_id}"
                )

            finally:
                await self.hub.connect()

        log_decoded(f"I{self.inverter_unit_id}", self.decoded_model)

        """ Power Control Options: Storage Control """
        if (
            self.hub.option_storage_control is True
            and self.decoded_storage_control is not False
            and (self.hub.slow_poll_due or self.decoded_storage_control is None)
        ):
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
                uint16_data = (
                    inverter_data.registers[0:2]
                    + [inverter_data.registers[6]]
                    + [inverter_data.registers[9]]
                )
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
                float32_data = (
                    inverter_data.registers[2:6] + inverter_data.registers[10:14]
                )
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
                    {
                        "command_timeout": ModbusClientMixin.convert_from_registers(
                            inverter_data.registers[7:9],
                            data_type=ModbusClientMixin.DATATYPE.UINT32,
                            word_order="little",
                        ),
                    }
                )

                log_decoded(f"I{self.inverter_unit_id}", self.decoded_storage_control)

            except (ModbusIllegalAddress, ModbusIllegalFunction, ModbusIllegalValue):
                self.decoded_storage_control = False
                _LOGGER.debug(
                    f"I{self.inverter_unit_id}: storage control NOT available"
                )

            except ModbusIOError:
                raise ModbusReadError(
                    f"No response from inverter ID {self.inverter_unit_id}"
                )

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

    def __init__(
        self, inverter: SolarEdgeInverter, hub: SolarEdgeModbusMultiHub, unit: int
    ) -> None:
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


class SolarEdgeMeter:
    """Defines a SolarEdge meter."""

    def __init__(
        self, device_id: int, meter_id: int, hub: SolarEdgeModbusMultiHub
    ) -> None:
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
                raise DeviceInvalid(
                    f"Invalid mmppt_Units value {self.mmppt_common['mmppt_Units']}"
                )

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

            # Standard SunSpec common model, starting directly at C_SunSpec_DID
            # (meters have no C_SunSpec_ID header).
            self.decoded_common = decode_sunspec_common_block(meter_info.registers)

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
                raise DeviceInvalid(
                    f"Meter {self.meter_id} ident incorrect or not installed."
                )

        except ModbusIOError:
            raise DeviceInvalid(f"No response from inverter ID {self.inverter_unit_id}")

        except (ModbusIllegalAddress, ModbusIllegalFunction, ModbusIllegalValue):
            raise DeviceInvalid(f"Meter {self.meter_id}: unsupported address")

        self.manufacturer = self.decoded_common["C_Manufacturer"]
        self.model = self.decoded_common["C_Model"]
        self.option = self.decoded_common["C_Option"]
        self.fw_version = self.decoded_common["C_Version"]
        self.serial = self.decoded_common["C_SerialNumber"]
        self.device_address = self.decoded_common["C_Device_address"]
        self.name = (
            f"{self.hub.hub_id.capitalize()} I{self.inverter_unit_id} M{self.meter_id}"
        )

        inverter_model = self.inverter_common["C_Model"]
        inerter_serial = self.inverter_common["C_SerialNumber"]
        self.uid_base = f"{inverter_model}_{inerter_serial}_M{self.meter_id}"

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
            raise ModbusReadError(
                f"No response from inverter ID {self.inverter_unit_id}"
            )

        log_decoded(f"I{self.inverter_unit_id}M{self.meter_id}", self.decoded_model)

        if (
            self.decoded_model["C_SunSpec_DID"] == SunSpecNotImpl.UINT16
            or self.decoded_model["C_SunSpec_DID"] not in [201, 202, 203, 204]
            or self.decoded_model["C_SunSpec_Length"] != 105
        ):
            raise DeviceInvalid(
                f"Meter {self.meter_id} ident incorrect or not installed."
            )

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


class SolarEdgeBattery:
    """Defines a SolarEdge battery."""

    def __init__(
        self, device_id: int, battery_id: int, hub: SolarEdgeModbusMultiHub
    ) -> None:
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

            # Batteries use a vendor block, not the SunSpec common model:
            # B_-prefixed names, little word order, no Option, and a
            # trailing float32 rated-energy field.
            self.decoded_common = {
                "B_Manufacturer": decode_sunspec_string(  # string(32)
                    battery_info.registers[0:16], word_order="little"
                ),
                "B_Model": decode_sunspec_string(  # string(32)
                    battery_info.registers[16:32], word_order="little"
                ),
                "B_Version": decode_sunspec_string(  # string(32)
                    battery_info.registers[32:48], word_order="little"
                ),
                "B_SerialNumber": decode_sunspec_string(  # string(32)
                    battery_info.registers[48:64], word_order="little"
                ),
                "B_Device_Address": ModbusClientMixin.convert_from_registers(
                    [battery_info.registers[64]],
                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                    word_order="little",
                ),
                "B_RatedEnergy": ModbusClientMixin.convert_from_registers(
                    battery_info.registers[66:68],
                    data_type=ModbusClientMixin.DATATYPE.FLOAT32,
                    word_order="little",
                ),
            }

            log_decoded(
                f"I{self.inverter_unit_id}B{self.battery_id}", self.decoded_common
            )

        except ModbusIOError:
            raise DeviceInvalid(f"No response from inverter ID {self.inverter_unit_id}")

        except (ModbusIllegalAddress, ModbusIllegalFunction, ModbusIllegalValue):
            raise DeviceInvalid(f"Battery {self.battery_id} unsupported address")

        self.decoded_common["B_Manufacturer"] = self.decoded_common[
            "B_Manufacturer"
        ].removesuffix(self.decoded_common["B_SerialNumber"])
        self.decoded_common["B_Model"] = self.decoded_common["B_Model"].removesuffix(
            self.decoded_common["B_SerialNumber"]
        )

        # Remove ASCII control characters from descriptive strings
        ascii_ctrl_chars = dict.fromkeys(range(32))
        self.decoded_common["B_Manufacturer"] = self.decoded_common[
            "B_Manufacturer"
        ].translate(ascii_ctrl_chars)
        self.decoded_common["B_Model"] = self.decoded_common["B_Model"].translate(
            ascii_ctrl_chars
        )
        self.decoded_common["B_SerialNumber"] = self.decoded_common[
            "B_SerialNumber"
        ].translate(ascii_ctrl_chars)

        if (
            float_to_hex(self.decoded_common["B_RatedEnergy"])
            == hex(SunSpecNotImpl.FLOAT32)
            or self.decoded_common["B_RatedEnergy"] <= 0
        ):
            raise DeviceInvalid(f"Battery {self.battery_id} not usable (rating <=0)")

        self.manufacturer = self.decoded_common["B_Manufacturer"]
        self.model = self.decoded_common["B_Model"]
        self.option = ""
        self.fw_version = self.decoded_common["B_Version"]
        self.serial = self.decoded_common["B_SerialNumber"]
        self.device_address = self.decoded_common["B_Device_Address"]
        self.name = (
            f"{self.hub.hub_id.capitalize()} "
            f"I{self.inverter_unit_id} B{self.battery_id}"
        )

        inverter_model = self.inverter_common["C_Model"]
        inerter_serial = self.inverter_common["C_SerialNumber"]
        self.uid_base = f"{inverter_model}_{inerter_serial}_B{self.battery_id}"

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
            float32_data = (
                battery_data.registers[0:8]
                + battery_data.registers[40:50]
                + battery_data.registers[58:66]
            )
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
            raise ModbusReadError(
                f"No response from inverter ID {self.inverter_unit_id}"
            )

        log_decoded(f"I{self.inverter_unit_id}B{self.battery_id}", self.decoded_model)

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


class SolarEdgeEVSE:
    """Class that defines a SolarEdge EVSE."""

    def __init__(self, device_id: int, hub: SolarEdgeModbusMultiHub) -> None:
        self.evse_unit_id = device_id
        self.hub = hub
        self.decoded_common = {}
        self.decoded_model = {}
        self.has_parent = False

    async def init_device(self) -> None:
        """Set up data about the device from modbus."""

        try:
            evse_data = await self.hub.modbus_read_holding_registers(
                unit=self.evse_unit_id, address=40000, rcount=69
            )

            self.decoded_common = dict(
                [
                    (
                        "C_SunSpec_ID",
                        ModbusClientMixin.convert_from_registers(
                            evse_data.registers[0:2],
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
            uint16_data = evse_data.registers[2:4] + [evse_data.registers[68]]
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
                                    evse_data.registers[4:20],
                                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                                )
                            ),
                        ),
                        (
                            "C_Model",  # string(32)
                            int_list_to_string(
                                ModbusClientMixin.convert_from_registers(
                                    evse_data.registers[20:36],
                                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                                )
                            ),
                        ),
                        (
                            "C_Option",  # string(16)
                            int_list_to_string(
                                ModbusClientMixin.convert_from_registers(
                                    evse_data.registers[36:44],
                                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                                )
                            ),
                        ),
                        (
                            "C_Version",  # string(16)
                            int_list_to_string(
                                ModbusClientMixin.convert_from_registers(
                                    evse_data.registers[44:52],
                                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                                )
                            ),
                        ),
                        (
                            "C_SerialNumber",  # string(32)
                            int_list_to_string(
                                ModbusClientMixin.convert_from_registers(
                                    evse_data.registers[52:68],
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
                        f"E{self.evse_unit_id}: "
                        f"{name} {hex(value) if isinstance(value, int) else value}"
                        f"{type(value)}"
                    ),
                )

        except ModbusIOError:
            # Transport failure, not an invalid device: the device already
            # answered the inverter probe, so surface this as retryable.
            raise ModbusReadError(f"No response from evse ID {self.evse_unit_id}")

        except (ModbusIllegalAddress, ModbusIllegalFunction, ModbusIllegalValue):
            raise DeviceInvalid(f"ID {self.evse_unit_id} is not SunSpec.")

        if (
            self.decoded_common["C_SunSpec_ID"] == SunSpecNotImpl.UINT32
            or self.decoded_common["C_SunSpec_DID"] == SunSpecNotImpl.UINT16
            or self.decoded_common["C_SunSpec_ID"] != 0x53756E53
            or self.decoded_common["C_SunSpec_DID"] != 0x0001
            or self.decoded_common["C_SunSpec_Length"] != 65
        ):
            raise DeviceInvalid(f"ID {self.evse_unit_id} is not SunSpec.")

        self.manufacturer = self.decoded_common["C_Manufacturer"]
        self.model = self.decoded_common["C_Model"]
        self.option = self.decoded_common["C_Option"]
        self.serial = self.decoded_common["C_SerialNumber"]
        self.device_address = self.decoded_common["C_Device_address"]
        self.name = f"{self.hub.hub_id.capitalize()} E{self.evse_unit_id}"
        self.uid_base = f"{self.model}_{self.serial}"

    async def read_modbus_data(self) -> None:
        """Read and update dynamic modbus registers."""

        try:
            evse_data = await self.hub.modbus_read_holding_registers(
                unit=self.evse_unit_id, address=40044, rcount=16
            )

            self.decoded_common["C_Version"] = int_list_to_string(
                ModbusClientMixin.convert_from_registers(
                    evse_data.registers[0:8],
                    data_type=ModbusClientMixin.DATATYPE.UINT16,
                )
            )

            log_decoded(f"E{self.evse_unit_id}", self.decoded_model)

        except (ModbusIllegalAddress, ModbusIllegalFunction, ModbusIllegalValue):
            _LOGGER.error(f"E{self.evse_unit_id}: EVSE register(s) NOT available")

        except ModbusIOError:
            raise ModbusReadError(f"No response from EVSE ID {self.evse_unit_id}")

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
