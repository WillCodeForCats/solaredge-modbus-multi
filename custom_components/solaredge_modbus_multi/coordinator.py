"""The SolarEdge Modbus Multi data update coordinator."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    TimestampDataUpdateCoordinator,
    UpdateFailed,
)

from .const import DATA_YAML, RetrySettings
from .hub import (
    DataUpdateFailed,
    DataUpdateTimedOut,
    HubInitFailed,
    SolarEdgeModbusMultiHub,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class SolarEdgeRuntimeData:
    """Runtime data stored on a SolarEdge Modbus Multi config entry."""

    hub: SolarEdgeModbusMultiHub
    coordinator: SolarEdgeCoordinator


type SolarEdgeConfigEntry = ConfigEntry[SolarEdgeRuntimeData]


class SolarEdgeCoordinator(TimestampDataUpdateCoordinator):
    """Solar edge coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        hub: SolarEdgeModbusMultiHub,
        scan_interval: int,
    ):
        """Initialize the solar edge coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="SolarEdge Coordinator",
            update_interval=timedelta(seconds=scan_interval),
        )
        self._hub = hub
        self._yaml_config = hass.data[DATA_YAML]

    async def _async_update_data(self) -> bool:
        """Fetch new data from the hub, retrying with backoff on failure."""
        try:
            return await self._refresh_modbus_data_with_retry(
                ex_type=DataUpdateFailed,
                limit=self._yaml_config.get("retry", {}).get(
                    "limit", RetrySettings.Limit
                ),
                wait_ms=self._yaml_config.get("retry", {}).get(
                    "time", RetrySettings.Time
                ),
                wait_ratio=self._yaml_config.get("retry", {}).get(
                    "ratio", RetrySettings.Ratio
                ),
            )

        except HubInitFailed as e:
            raise UpdateFailed(f"{e}") from e

        except DataUpdateFailed as e:
            raise UpdateFailed(f"{e}") from e

        except DataUpdateTimedOut as e:
            raise UpdateFailed(f"{e}") from e

    async def _refresh_modbus_data_with_retry(
        self,
        ex_type=Exception,
        limit: int = 0,
        wait_ms: int = 100,
        wait_ratio: int = 2,
    ) -> bool:
        """Retry refresh until no exception occurs or retries exhaust.

        :param ex_type: retry only if exception is subclass of this type
        :param limit: maximum number of invocation attempts
        :param wait_ms: initial wait time after each attempt in milliseconds.
        :param wait_ratio: increase wait by multiplying by this after each try.
        :return: result of first successful invocation
        :raises: last invocation exception if attempts exhausted
                 or exception is not an instance of ex_type

        Credit: https://gist.github.com/davidohana/c0518ff6a6b95139e905c8a8caef9995
        """
        _LOGGER.debug("Retry limit=%s time=%s ratio=%s", limit, wait_ms, wait_ratio)
        attempt = 1
        while True:
            try:
                return await self._hub.async_refresh_modbus_data()
            except Exception as ex:  # noqa: PERF203
                if not isinstance(ex, ex_type):
                    raise
                if 0 < limit <= attempt:
                    _LOGGER.debug("No more data refresh attempts (maximum %s)", limit)
                    raise

                _LOGGER.debug("Failed data refresh attempt %s", attempt)

                attempt += 1
                _LOGGER.debug(
                    "Waiting %s ms before data refresh attempt %s", wait_ms, attempt
                )
                await asyncio.sleep(wait_ms / 1000)
                wait_ms *= wait_ratio
