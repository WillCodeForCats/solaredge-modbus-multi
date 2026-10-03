"""Tests for named poll groups: cadence resolution, gating and diagnostics.

Sibling of test_tiered_polling.py, which covers the settings tier through
the slow_poll_due alias; this file exercises the per-group machinery
underneath it.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol

from custom_components.solaredge_modbus_multi import CONFIG_SCHEMA
from custom_components.solaredge_modbus_multi.const import (
    CONFIGURABLE_POLL_GROUPS,
    DOMAIN,
    POLL_MULTIPLIER_MAX,
    POLL_MULTIPLIER_MIN,
    ConfDefaultInt,
    ConfName,
    ModbusExceptions,
    PollGroup,
)
from custom_components.solaredge_modbus_multi.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.solaredge_modbus_multi.hub import (
    DataUpdateFailed,
    ModbusIOError,
    ModbusReadError,
    SolarEdgeInverter,
    SolarEdgeModbusMultiHub,
)
from custom_components.solaredge_modbus_multi.sensor import (
    SolarEdgeCommitControlSettings,
    SolarEdgeRRCR,
)
from custom_components.solaredge_modbus_multi.sensor import (
    async_setup_entry as sensor_setup_entry,
)
from tests.conftest import (
    build_synergy_full_space,
    create_exception_response,
    create_modbus_response,
    install_connection_double,
    make_side_effect,
)

# Groups this file never re-times, so they are due on every cycle.
BASE_GROUPS = {PollGroup.CORE, PollGroup.STATUS, PollGroup.MMPPT, PollGroup.EVSE}

DETECT_PROBES = [
    (61440, "global_power_control", "_gpc_probed"),
    (61696, "advanced_power_control", "_apc_probed"),
]


@pytest.fixture
def make_hub(hass, mock_config_entry_data, mock_config_entry_options):
    """Build a hub from an advanced-YAML `poll:` block plus the slow option.

    Control features are on so the settings-group blocks are actually read.
    """

    def _make(
        poll_yaml: dict | None = None, slow_poll_multiplier: int | None = None
    ) -> SolarEdgeModbusMultiHub:
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["yaml"] = {"poll": poll_yaml} if poll_yaml else {}

        options = {
            **mock_config_entry_options,
            ConfName.DETECT_EXTRAS: True,
            ConfName.ADV_STORAGE_CONTROL: True,
            ConfName.ADV_SITE_LIMIT_CONTROL: True,
        }
        if slow_poll_multiplier is not None:
            options[ConfName.SLOW_POLL_MULTIPLIER] = slow_poll_multiplier

        return SolarEdgeModbusMultiHub(
            hass,
            entry_id="poll_groups",
            entry_data=mock_config_entry_data,
            entry_options=options,
        )

    return _make


@pytest.fixture
def make_live_inverter(make_hub, mock_connection):
    """Connected hub + initialized SolarEdgeInverter over a full register space.

    probe_timeout_address times out reads of that address until
    `ctx.timing_out = False`; errors maps address -> canned response.
    """

    async def _make(
        poll_yaml=None,
        slow_poll_multiplier=None,
        *,
        errors=None,
        probe_timeout_address=None,
        record_timeout_attempts=False,
        register=False,
    ):
        hub = make_hub(poll_yaml, slow_poll_multiplier)
        space = build_synergy_full_space()
        calls: list[tuple[int, int]] = []
        ctx = SimpleNamespace(
            calls=calls,
            space=space,
            connection=mock_connection,
            timing_out=probe_timeout_address is not None,
        )
        base = make_side_effect(space, errors or {}, calls)

        def side_effect(*args, **kwargs):
            address = kwargs.get("address", args[0] if args else 0)
            if ctx.timing_out and address == probe_timeout_address:
                if record_timeout_attempts:
                    # Record the attempt before failing it: these tests assert
                    # which cycles reach the wire, not which ones answer.
                    calls.append((address, 0))
                raise TimeoutError
            return base(*args, **kwargs)

        mock_connection.read_holding_registers.side_effect = side_effect
        await hub.connect()
        inverter = SolarEdgeInverter(device_id=1, hub=hub)
        await inverter.init_device()
        if register:
            hub.inverters = [inverter]
            hub.initalized = True
        ctx.hub = hub
        ctx.inverter = inverter
        return ctx

    return _make


def _ready_to_cycle(hub: SolarEdgeModbusMultiHub) -> SolarEdgeModbusMultiHub:
    """Let a refresh run its cycle bookkeeping without touching modbus."""
    hub.initalized = True
    hub._keep_modbus_open = True
    install_connection_double(hub._transport)
    return hub


def _due(hub: SolarEdgeModbusMultiHub) -> set[PollGroup]:
    """The groups the last refresh decided to read."""
    return {group for group in PollGroup if hub.poll_due(group)}


def _multipliers(hub: SolarEdgeModbusMultiHub) -> dict[str, int]:
    """The resolved cadence per group, as diagnostics reports it."""
    return {name: group["multiplier"] for name, group in hub.poll_groups.items()}


def _recording_device() -> MagicMock:
    """Device stub that keeps the timestamp the hub handed it."""
    device = MagicMock()
    device.read_modbus_data = AsyncMock()
    device.last_update = None
    device.set_last_update = MagicMock(
        side_effect=lambda timestamp: setattr(device, "last_update", timestamp)
    )
    return device


def _addresses(calls: list[tuple[int, int]]) -> list[int]:
    return [address for address, _ in calls]


async def test_default_multipliers_slow_poll_settings_only(make_hub) -> None:
    """With no YAML, only the settings blocks are thinned."""
    hub = make_hub()

    assert _multipliers(hub) == {
        "core": 1,
        "meter": 1,
        "battery": 1,
        "status": 1,
        "mmppt": 1,
        "evse": 1,
        "settings": int(ConfDefaultInt.SLOW_POLL_MULTIPLIER),
    }


async def test_slow_poll_option_moves_only_the_settings_group(make_hub) -> None:
    """Changing the options-flow multiplier leaves every other group at 1."""
    hub = make_hub(slow_poll_multiplier=9)

    assert _multipliers(hub)["settings"] == 9
    assert all(
        multiplier == 1
        for group, multiplier in _multipliers(hub).items()
        if group != "settings"
    )


async def test_yaml_poll_overrides_named_groups(make_hub) -> None:
    """A YAML `poll:` block retimes exactly the groups it names."""
    hub = make_hub({"status": 6, "battery": 3}, slow_poll_multiplier=2)

    assert _multipliers(hub) == {
        "core": 1,
        "meter": 1,
        "battery": 3,
        "status": 6,
        "mmppt": 1,
        "evse": 1,
        "settings": 2,
    }


async def test_yaml_settings_wins_over_the_options_multiplier(make_hub) -> None:
    """Advanced YAML is the last word on the settings cadence."""
    hub = make_hub({"settings": 2}, slow_poll_multiplier=6)

    assert _multipliers(hub)["settings"] == 2


async def test_core_multiplier_is_pinned_to_one(make_hub) -> None:
    """Thinning the inverter model block is never allowed."""
    hub = make_hub({"core": 10, "meter": 10})

    assert PollGroup.CORE not in CONFIGURABLE_POLL_GROUPS
    assert _multipliers(hub)["core"] == 1
    assert _multipliers(hub)["meter"] == 10


@pytest.mark.parametrize("multiplier", [0, -1])
async def test_multipliers_below_one_clamp_to_one(make_hub, multiplier) -> None:
    """The schema rejects these, but neither source is trusted blindly."""
    hub = make_hub({"meter": multiplier}, slow_poll_multiplier=multiplier)

    assert _multipliers(hub)["meter"] == 1
    assert _multipliers(hub)["settings"] == 1


@pytest.mark.parametrize(
    "poll_config",
    [
        {"settings": POLL_MULTIPLIER_MIN},
        {"status": 6, "battery": 3},
        {f"{group}": POLL_MULTIPLIER_MAX for group in CONFIGURABLE_POLL_GROUPS},
    ],
)
def test_config_schema_accepts_poll_block(poll_config) -> None:
    """Every configurable group is valid across the whole documented range."""
    validated = CONFIG_SCHEMA({DOMAIN: {"poll": poll_config}})

    assert validated[DOMAIN]["poll"] == poll_config


@pytest.mark.parametrize(
    "poll_config",
    [
        {"inverter": 2},  # not a group name
        {"core": 2},  # never configurable
        {"settings": 0},  # below POLL_MULTIPLIER_MIN
        {"settings": POLL_MULTIPLIER_MAX + 1},
    ],
)
def test_config_schema_rejects_invalid_poll_block(poll_config) -> None:
    """A bad cadence fails at startup instead of silently polling everything."""
    with pytest.raises(vol.Invalid):
        CONFIG_SCHEMA({DOMAIN: {"poll": poll_config}})


async def test_new_hub_has_every_group_due(make_hub) -> None:
    """Discovery must see every block before any cadence applies."""
    hub = make_hub({"meter": 4}, slow_poll_multiplier=6)

    assert _due(hub) == set(PollGroup)


async def test_first_refresh_cycle_is_all_due(make_hub) -> None:
    """Cycle 0 divides by every multiplier, so nothing is skipped."""
    hub = _ready_to_cycle(make_hub({"meter": 4}, slow_poll_multiplier=6))

    await hub.async_refresh_modbus_data()

    assert hub._poll_cycle == 0
    assert _due(hub) == set(PollGroup)


async def test_group_cadence_follows_multipliers(make_hub) -> None:
    """Each group is due exactly when cycle % multiplier == 0."""
    hub = _ready_to_cycle(make_hub({"meter": 2, "battery": 3}, slow_poll_multiplier=4))

    expected = [
        BASE_GROUPS | {PollGroup.METER, PollGroup.BATTERY, PollGroup.SETTINGS},
        BASE_GROUPS,
        BASE_GROUPS | {PollGroup.METER},
        BASE_GROUPS | {PollGroup.BATTERY},
        BASE_GROUPS | {PollGroup.METER, PollGroup.SETTINGS},
        BASE_GROUPS,
        BASE_GROUPS | {PollGroup.METER, PollGroup.BATTERY},
        BASE_GROUPS,
        BASE_GROUPS | {PollGroup.METER, PollGroup.SETTINGS},
    ]

    seen = []
    for _ in expected:
        await hub.async_refresh_modbus_data()
        seen.append(_due(hub))

    assert seen == expected


async def test_failed_refresh_does_not_consume_a_cycle(make_hub) -> None:
    """A failure must leave the same cycle for the next attempt to serve."""
    hub = _ready_to_cycle(make_hub({"meter": 2, "battery": 2}, slow_poll_multiplier=3))

    await hub.async_refresh_modbus_data()
    assert hub._poll_cycle == 0

    failing_inverter = MagicMock()
    failing_inverter.read_modbus_data = AsyncMock(side_effect=ModbusReadError("boom"))
    hub.inverters = [failing_inverter]

    with pytest.raises(DataUpdateFailed):
        await hub.async_refresh_modbus_data()

    assert hub._poll_cycle == 0

    # Cycle 1 (not 2) is next: the failed attempt did not advance anything.
    hub.inverters = []
    await hub.async_refresh_modbus_data()
    assert hub._poll_cycle == 1
    assert _due(hub) == BASE_GROUPS

    await hub.async_refresh_modbus_data()
    assert _due(hub) == BASE_GROUPS | {PollGroup.METER, PollGroup.BATTERY}


async def test_write_forces_settings_group_on_next_refresh(
    make_hub, mock_modbus_client
) -> None:
    """A hardware write re-reads the settings blocks off-cycle."""
    hub = make_hub(slow_poll_multiplier=3)
    hub._sleep_after_write = 0
    mock_client = mock_modbus_client.return_value
    mock_client.write_registers.return_value = create_modbus_response([])

    with patch(
        "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection",
        mock_modbus_client,
    ):
        await hub.connect()
        hub.initalized = True
        hub._keep_modbus_open = True

        await hub.async_refresh_modbus_data()  # cycle 0
        await hub.async_refresh_modbus_data()  # cycle 1
        assert hub.poll_due(PollGroup.SETTINGS) is False

        await hub.write_registers(unit=1, address=57348, payload=[1])
        assert hub._slow_poll_requests == 1

        await hub.async_refresh_modbus_data()  # cycle 2, forced by the write
        assert hub.poll_due(PollGroup.SETTINGS) is True
        assert hub._slow_poll_requests == 0


async def test_forced_settings_poll_does_not_pull_in_other_groups(make_hub) -> None:
    """A write requests the settings blocks only, and only once."""
    hub = _ready_to_cycle(make_hub({"meter": 4, "battery": 4}, slow_poll_multiplier=3))

    await hub.async_refresh_modbus_data()  # cycle 0
    await hub.async_refresh_modbus_data()  # cycle 1

    hub._slow_poll_requests += 1
    await hub.async_refresh_modbus_data()  # cycle 2
    assert _due(hub) == BASE_GROUPS | {PollGroup.SETTINGS}

    await hub.async_refresh_modbus_data()  # cycle 3, natural settings cycle
    assert hub.poll_due(PollGroup.SETTINGS) is True

    await hub.async_refresh_modbus_data()  # cycle 4, one-shot already spent
    assert _due(hub) == BASE_GROUPS | {PollGroup.METER, PollGroup.BATTERY}


async def test_write_during_refresh_keeps_settings_request_pending(make_hub) -> None:
    """A write between device polls must survive that refresh completing."""
    hub = _ready_to_cycle(make_hub(slow_poll_multiplier=3))

    await hub.async_refresh_modbus_data()  # cycle 0
    await hub.async_refresh_modbus_data()  # cycle 1

    async def write_lands_between_device_polls():
        hub._slow_poll_requests += 1

    inverter = MagicMock()
    inverter.read_modbus_data = AsyncMock(side_effect=write_lands_between_device_polls)
    hub.inverters = [inverter]

    await hub.async_refresh_modbus_data()  # cycle 2, tier already snapshotted
    assert hub.poll_due(PollGroup.SETTINGS) is False
    assert hub._slow_poll_requests == 1

    hub.inverters = []
    await hub.async_refresh_modbus_data()
    assert hub.poll_due(PollGroup.SETTINGS) is True
    assert hub._slow_poll_requests == 0


async def test_off_cycle_group_keeps_values_and_entity_available(
    make_live_inverter,
) -> None:
    """Skipping a group retains its values; only a dead block drops them."""
    ctx = await make_live_inverter(slow_poll_multiplier=3)
    hub, inverter = ctx.hub, ctx.inverter

    config_entry = MagicMock()
    config_entry.entry_id = "poll_groups"
    config_entry.data = {"name": "Test SolarEdge"}
    coordinator = MagicMock()
    coordinator.last_update_success = True
    entity = SolarEdgeCommitControlSettings(inverter, config_entry, coordinator)

    await inverter.read_modbus_data()
    assert inverter.advanced_power_control is True
    assert entity.available is True

    ctx.calls.clear()
    hub.slow_poll_due = False
    await inverter.read_modbus_data()

    assert 61696 not in _addresses(ctx.calls)
    assert "CommitPwrCtlSettings" in inverter.decoded_model
    assert inverter.advanced_power_control is True
    assert entity.available is True

    # Contrast: a block that answers IllegalAddress really is dropped.
    ctx.connection.read_holding_registers.side_effect = make_side_effect(
        ctx.space,
        {61696: create_exception_response(ModbusExceptions.IllegalAddress)},
        ctx.calls,
    )
    hub.slow_poll_due = True
    await inverter.read_modbus_data()

    assert inverter.advanced_power_control is False
    assert "CommitPwrCtlSettings" not in inverter.decoded_model
    assert entity.available is False


async def test_timestamps_follow_physical_reads(make_hub) -> None:
    """Devices whose group was skipped must not claim a refresh."""
    hub = _ready_to_cycle(make_hub({"meter": 2, "battery": 2}))
    inverter = _recording_device()
    meter = _recording_device()
    battery = _recording_device()
    hub.inverters = [inverter]
    hub.meters = [meter]
    hub.batteries = [battery]

    await hub.async_refresh_modbus_data()  # cycle 0, everything read
    first = inverter.last_update
    assert meter.last_update is first
    assert battery.last_update is first

    await hub.async_refresh_modbus_data()  # cycle 1, meter and battery skipped

    # Identity, not equality: two dt.now() calls can land in one microsecond.
    assert inverter.last_update is not first
    assert meter.last_update is first
    assert battery.last_update is first
    assert meter.read_modbus_data.await_count == 1
    assert battery.read_modbus_data.await_count == 1
    assert inverter.read_modbus_data.await_count == 2


async def test_capability_gate_stays_open_until_a_verdict(make_hub) -> None:
    """The tri-state gate: undecided (None) keeps entities and probes alive.

    Only an inverter verdict (False) — or the detect-extras option being
    off — closes it. Platforms and the probe preconditions all read these
    properties, so this is the one place the rule is decided.
    """
    hub = make_hub()
    inverter = SolarEdgeInverter(device_id=1, hub=hub)

    assert inverter.gpc_may_be_supported is True  # None = undecided
    assert inverter.apc_may_be_supported is True

    inverter.global_power_control = False
    inverter.advanced_power_control = False
    assert inverter.gpc_may_be_supported is False
    assert inverter.apc_may_be_supported is False

    inverter.global_power_control = True
    inverter.advanced_power_control = True
    assert inverter.gpc_may_be_supported is True
    assert inverter.apc_may_be_supported is True

    hub._detect_extras = False
    assert inverter.gpc_may_be_supported is False
    assert inverter.apc_may_be_supported is False


async def test_slow_poll_due_aliases_the_settings_group(make_hub) -> None:
    """The alias reads and writes PollGroup.SETTINGS, and nothing else."""
    hub = make_hub(slow_poll_multiplier=3)
    assert hub.slow_poll_due is True

    hub.slow_poll_due = False
    assert hub.poll_due(PollGroup.SETTINGS) is False
    assert _due(hub) == set(PollGroup) - {PollGroup.SETTINGS}

    hub.slow_poll_due = True
    assert hub.poll_due(PollGroup.SETTINGS) is True
    assert _due(hub) == set(PollGroup)

    hub._due_groups.discard(PollGroup.SETTINGS)
    assert hub.slow_poll_due is False
    hub._due_groups.add(PollGroup.SETTINGS)
    assert hub.slow_poll_due is True


async def test_diagnostics_exposes_poll_groups(hass, make_hub) -> None:
    """Diagnostics report the resolved cadence and the live due set."""
    hub = _ready_to_cycle(make_hub({"meter": 2, "battery": 3}, slow_poll_multiplier=4))

    await hub.async_refresh_modbus_data()  # cycle 0
    await hub.async_refresh_modbus_data()  # cycle 1

    entry = MagicMock()
    entry.as_dict.return_value = {"data": {"host": "192.168.1.100"}}
    entry.runtime_data = SimpleNamespace(hub=hub)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    polling = diagnostics["polling"]
    groups = polling["poll_groups"]
    assert polling["poll_cycle"] == 1
    assert groups == hub.poll_groups
    assert groups["meter"]["multiplier"] == 2
    assert groups["battery"]["multiplier"] == 3
    assert groups["settings"]["multiplier"] == 4

    assert {name for name, group in groups.items() if group["due"]} == {
        f"{group}" for group in BASE_GROUPS
    }

    # This hub has no devices, so "due" is all it can honestly claim: being
    # scheduled is not evidence that anything was read.
    assert all(group["last_served_cycle"] is None for group in groups.values()), (
        "cadence evidence must require an actual read"
    )

    assert diagnostics["yaml"]["poll"] == {"meter": 2, "battery": 3}


async def test_last_served_cycle_tracks_physical_reads(make_live_inverter) -> None:
    """`last_served_cycle` advances only for groups that really read."""
    ctx = await make_live_inverter({"battery": 2}, register=True)
    hub = ctx.hub

    await hub.async_refresh_modbus_data()  # cycle 0
    groups = hub.poll_groups

    assert groups["core"]["last_served_cycle"] == 0
    assert groups["status"]["last_served_cycle"] == 0
    assert groups["settings"]["last_served_cycle"] == 0
    # No meter, battery or EVSE exists on this hub, so those groups were
    # due but read nothing — they must not claim a served cycle.
    for absent in ("meter", "battery", "evse"):
        assert groups[absent]["due"] is True
        assert groups[absent]["last_served_cycle"] is None

    await hub.async_refresh_modbus_data()  # cycle 1
    groups = hub.poll_groups

    assert groups["core"]["last_served_cycle"] == 1
    # settings is on the default multiplier, so it did not run again.
    assert groups["settings"]["last_served_cycle"] == 0


@pytest.mark.parametrize(("address", "capability", "probed_flag"), DETECT_PROBES)
async def test_detect_timeout_falls_back_to_settings_cadence(
    make_live_inverter, address, capability, probed_flag
) -> None:
    """A timeout leaves the capability undecided but stops per-cycle probing."""
    ctx = await make_live_inverter(
        slow_poll_multiplier=3,
        probe_timeout_address=address,
        record_timeout_attempts=True,
    )
    hub, inverter = ctx.hub, ctx.inverter

    ctx.calls.clear()
    await inverter.read_modbus_data()
    assert address in _addresses(ctx.calls)
    assert getattr(inverter, capability) is None  # not disabled by a timeout
    assert getattr(inverter, probed_flag) is True

    # Off-cycle: an unresolved probe must not re-read every cycle.
    ctx.calls.clear()
    hub.slow_poll_due = False
    await inverter.read_modbus_data()
    assert address not in _addresses(ctx.calls)

    # The next settings cycle retries, and a good read resolves it.
    ctx.timing_out = False
    ctx.calls.clear()
    hub.slow_poll_due = True
    await inverter.read_modbus_data()
    assert address in _addresses(ctx.calls)
    assert getattr(inverter, capability) is True


@pytest.mark.parametrize(
    ("address", "capability"), [probe[:2] for probe in DETECT_PROBES]
)
@pytest.mark.parametrize(
    "exception_code",
    [
        ModbusExceptions.IllegalAddress,
        ModbusExceptions.IllegalFunction,
        ModbusExceptions.IllegalValue,
    ],
)
async def test_detect_illegal_response_disables_block_permanently(
    make_live_inverter, address, capability, exception_code
) -> None:
    """An illegal response is a verdict: the block is never read again."""
    ctx = await make_live_inverter(
        slow_poll_multiplier=3,
        errors={address: create_exception_response(exception_code)},
    )
    hub, inverter = ctx.hub, ctx.inverter

    await inverter.read_modbus_data()
    assert getattr(inverter, capability) is False

    # The guard, not the error, is what stops the read: answer normally.
    ctx.calls.clear()
    ctx.connection.read_holding_registers.side_effect = make_side_effect(
        ctx.space, {}, ctx.calls
    )
    hub.slow_poll_due = True
    await inverter.read_modbus_data()

    assert address not in _addresses(ctx.calls)
    assert getattr(inverter, capability) is False


# --- review findings: capability recovery and forced-poll accounting ---------


@pytest.mark.parametrize(
    ("address", "capability", "entity_class"),
    [
        (61440, "global_power_control", SolarEdgeRRCR),
        (61696, "advanced_power_control", SolarEdgeCommitControlSettings),
    ],
    ids=["gpc", "apc"],
)
async def test_startup_probe_timeout_still_creates_entities(
    hass, make_live_inverter, address, capability, entity_class
) -> None:
    """A probe that times out during setup must not omit entities forever.

    Home Assistant runs platform setup once. If a transient timeout left the
    capability undecided and the platform skipped the entities, a later
    successful probe could never bring them back without an integration
    reload — so the entities are created and simply stay unavailable until
    detection succeeds.
    """
    ctx = await make_live_inverter(
        slow_poll_multiplier=3, probe_timeout_address=address
    )
    hub, inverter = ctx.hub, ctx.inverter
    await inverter.read_modbus_data()

    assert getattr(inverter, capability) is None

    # Platform setup happens exactly once, right here.
    hub.inverters = [inverter]
    entry = MagicMock()
    entry.entry_id = "poll_groups"
    entry.data = {"name": "Test SolarEdge"}
    entry.runtime_data = SimpleNamespace(hub=hub, coordinator=MagicMock())
    async_add_entities = MagicMock()
    await sensor_setup_entry(hass, entry, async_add_entities)

    created = async_add_entities.call_args[0][0]
    blocked = [entity for entity in created if isinstance(entity, entity_class)]
    assert blocked, "capability entities must exist while detection is undecided"
    assert all(not entity.available for entity in blocked)

    # Detection succeeds later; the same entity objects come good.
    ctx.timing_out = False
    hub.slow_poll_due = True
    await inverter.read_modbus_data()

    assert getattr(inverter, capability) is True
    assert all(entity.available for entity in blocked)


@pytest.mark.parametrize(
    "address", [probe[0] for probe in DETECT_PROBES], ids=["gpc", "apc"]
)
async def test_settings_timeout_does_not_consume_forced_poll(
    make_live_inverter, address
) -> None:
    """A write-forced settings re-read is only spent once it actually happens.

    Detect-probe timeouts are swallowed inside the device read, so the refresh
    still succeeds. That must not be mistaken for having verified the write.
    """
    ctx = await make_live_inverter(
        slow_poll_multiplier=6, probe_timeout_address=address, register=True
    )
    hub = ctx.hub

    # Cycle 0 is settings-due but the probe times out, so nothing is served.
    await hub.async_refresh_modbus_data()
    assert hub.poll_groups["settings"]["last_served_cycle"] is None

    # Stand in for a write: request a settings re-read off-cycle.
    hub._slow_poll_requests = 1

    await hub.async_refresh_modbus_data()  # cycle 1, forced settings poll
    assert hub.slow_poll_due is True
    assert hub._slow_poll_requests == 1, "timed-out poll must not spend it"
    assert hub.poll_groups["settings"]["last_served_cycle"] is None

    ctx.timing_out = False
    await hub.async_refresh_modbus_data()  # cycle 2, still forced
    assert hub.slow_poll_due is True
    assert hub._slow_poll_requests == 0, "a served poll spends the request"
    assert hub.poll_groups["settings"]["last_served_cycle"] == 2


async def test_settings_timeout_defers_uncommitted_warning(
    make_live_inverter, caplog
) -> None:
    """The uncommitted-settings warning waits for real settings data."""
    ctx = await make_live_inverter(
        slow_poll_multiplier=6, probe_timeout_address=61696, register=True
    )
    hub = ctx.hub
    await hub.async_refresh_modbus_data()

    hub._uncommitted_power_settings = {61760}
    hub._slow_poll_requests = 1

    caplog.clear()
    await hub.async_refresh_modbus_data()
    assert "written without" not in caplog.text

    ctx.timing_out = False
    await hub.async_refresh_modbus_data()
    assert "written without" in caplog.text


async def test_ext_prod_max_alone_counts_as_a_settings_read(
    make_live_inverter,
) -> None:
    """A settings block can succeed even where its neighbour is unsupported.

    Site limit (57344) and external production max (57362) sit in separate
    try blocks, so an inverter that rejects the first can still answer the
    second — and that transaction is real cadence evidence.
    """
    ctx = await make_live_inverter(
        errors={
            61440: create_exception_response(ModbusExceptions.IllegalAddress),
            61696: create_exception_response(ModbusExceptions.IllegalAddress),
            57344: create_exception_response(ModbusExceptions.IllegalAddress),
            57348: create_exception_response(ModbusExceptions.IllegalAddress),
        },
        register=True,
    )
    hub, inverter = ctx.hub, ctx.inverter

    await hub.async_refresh_modbus_data()

    assert inverter.site_limit_control is False
    assert 57362 in _addresses(ctx.calls)
    assert hub.poll_groups["settings"]["last_served_cycle"] == 0


@pytest.mark.parametrize("address", [61440, 61696, 40113], ids=["gpc", "apc", "grid"])
async def test_cancelled_probe_propagates_as_cancellation(
    make_hub, mock_modbus_client, address
) -> None:
    """Cancellation must survive the whole device read, not just the request.

    A `finally` that raises replaces the exception propagating through it, so
    an eager reconnect after a cancelled probe would swap CancelledError for a
    connection error — and the outer deadline could then never become
    TimeoutError, bypassing the hub's timeout counter entirely.
    """
    hub = make_hub()
    space = build_synergy_full_space()
    calls: list[tuple[int, int]] = []
    base = make_side_effect(space, {}, calls)

    def side_effect(*args, **kwargs):
        if kwargs.get("address", args[0] if args else 0) == address:
            raise asyncio.CancelledError
        return base(*args, **kwargs)

    mock_modbus_client.return_value.read_holding_registers.side_effect = side_effect

    with patch(
        "custom_components.solaredge_modbus_multi.modbus_transport.ModbusConnection",
        mock_modbus_client,
    ):
        await hub.connect()
        inverter = SolarEdgeInverter(device_id=1, hub=hub)
        await inverter.init_device()

        # A reconnect that would clobber the cancellation, if one were tried.
        hub.connect = AsyncMock(side_effect=ModbusIOError("connect refused"))

        with pytest.raises(asyncio.CancelledError):
            await inverter.read_modbus_data()
