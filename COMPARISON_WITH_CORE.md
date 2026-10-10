# solaredge-modbus-multi and HA Core SolarEdge Modbus: Comparison

_Created by Claude Code on 2026-10-04 and updated on 2026-10-10 to the current releases, from reading both codebases, with observations from the maintainer of solaredge-modbus-multi. Statements attributed to the maintainer are observations from the experience of writing and running solaredge-modbus-multi, not independent test results._

|                         | Repository                                                                                                        | Version compared                                                                                                                          |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| solaredge_modbus_multi  | [WillCodeForCats/solaredge-modbus-multi](https://github.com/WillCodeForCats/solaredge-modbus-multi)               | v4.0.6 (1f1eaac, 2026-10-10)                                                                                                              |
| solaredge_modbus (core) | [home-assistant/core](https://github.com/home-assistant/core), folder `homeassistant/components/solaredge_modbus` | release `2026.10.1` (abe1fdd, 2026-10-10); documentation: [integration page](https://www.home-assistant.io/integrations/solaredge_modbus) |

In the tables, "Core" means the Home Assistant core `solaredge_modbus` integration, and "solaredge-modbus-multi" is this integration.

## Summary

The core integration uses one config entry per inverter and builds on the HA `modbus` integration. solaredge-modbus-multi uses one hub for a whole site, with more options and entities. Both use `_solaredge-modbus._tcp` mDNS discovery and local Modbus polling.

|                         | solaredge_modbus_multi                               | solaredge_modbus (core)                                                                              |
| ----------------------- | ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Version / quality scale | 4.0.6                                                | Platinum quality scale; library `solaredged` 0.5.0                                                   |
| First commit            | 2021-10-21 (tag v1.0 the same day)                   | 2026-08-29, added to HA core (#180508); first in release 2026.10.0b0 (final 2026.10.0 on 2026-10-07) |
| Age on 2026-10-10       | about 5 years (1,815 days)                           | 42 days since it was added to core; 3 days in a stable release                                       |
| Integration type        | hub (one entry, many inverters)                      | device (one entry per inverter)                                                                      |
| Modbus layer            | `modbus-connection` + `tmodbus`, owns its connection | borrows a shared unit from HA's `modbus` integration                                                 |
| Codeowner               | @WillCodeForCats                                     | @frenck                                                                                              |
| Poll interval           | user option, default 10 s (was 300 s before v4.0.6)  | fixed: 10 s readings, 5 min settings, 15 min attachment check                                        |
| Options flow            | yes (polling, detection, power control, battery)     | none                                                                                                 |
| Entity identity         | host:port based                                      | inverter serial number                                                                               |

## Setup and discovery

solaredge-modbus-multi finds every inverter behind a gateway in one flow. Core sets up one inverter at a time and does not scan device IDs.

|                               | solaredge-modbus-multi                                                                  | Core                                                                                       |
| ----------------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Entry point                   | Menu: fast scan (IDs 1–32), full scan (1–247), or manual ID list                        | Menu: TCP or serial (RS485)                                                                |
| mDNS discovery                | Yes; confirms the gateway, then offers the scan                                         | Yes; reads `MODBUS_ID` from the announcement, probes the inverter, offers it               |
| Multiple inverters on one bus | One entry; the device ID list covers all of them                                        | One entry per device ID; each is added separately                                          |
| Serial / RS485                | TCP only                                                                                | TCP and serial (baud rate field, default 115200)                                           |
| Default port / unit ID        | 1502 / scanned                                                                          | 1502 / 1, with unit ID in a collapsed "more options" section                               |
| Validation                    | Checks each ID answers as an inverter; can be bypassed with "Skip Device ID validation" | Probes the device; rejects EV chargers, missing serial numbers and non-SolarEdge devices   |
| Reconfigure                   | Host, port, ID list                                                                     | Host, port, unit ID, serial settings; aborts if the serial number differs (`wrong_device`) |
| Unique ID                     | host:port based                                                                         | Inverter serial number; a moved address is updated on rediscovery                          |

Core checks the serial number on every poll and raises a config entry error if another inverter answers at the same address. No equivalent per-poll identity check was found in solaredge-modbus-multi; a replaced-inverter repair issue exists on an unmerged branch.

## Startup time

Both integrations probe the inverter at startup, and a probe of a block the inverter never answers lasts a full timeout. The timeouts differ. The figures below come from reading the code, not from timing a startup.

|                             | solaredge-modbus-multi                                                                                                                                                          | Core (2026.10.1)                                                                                                                        |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Request timeout             | Option, default 3 s (1–60 s)                                                                                                                                                    | Probe: link default, 10 s. Reads after the probe: 30 s (`READ_TIMEOUT`)                                                                 |
| Attempts per request        | 3 for the model scan and for reads, so at most about 9 s at the default; then the coordinator retries a failed refresh up to 6 times, waiting 1, 2, 4, 8 and 16 s between tries | The library's behavior; not read for this table                                                                                         |
| Probing for absent hardware | Only for enabled features. Batteries, extras and the control features are off by default (unofficial registers); only meters are on by default                                  | Always: batteries, meters, multiple-MPPT and the control blocks are asked at every setup unless a previous check settled them as silent |
| Memory between setups       | None; enabled features are probed again at each setup                                                                                                                           | Blocks that stayed silent on two checks are kept in the config entry and skipped, except meters, batteries and multiple-MPPT            |
| Several inverters           | One setup for the whole hub, with a time budget computed from the number of inverters; the model scan runs once per inverter                                                    | Each entry sets up on its own and probes on its own, on a bus that may be shared                                                        |

What this means for startup:

- **The 30 s timeout does not apply to the probe.** Core sets it after `async_probe` returns, so a silent block during setup still costs 10 s. It does apply to the first refresh, so an inverter that is slow to answer can take up to 30 s on a read where solaredge-modbus-multi would give up after 3 s and try again.
- **solaredge-modbus-multi fails fast and then backs off.** With a 3 s timeout and 3 attempts, a request that never answers costs about 9 s, and the user can lower the timeout if their inverters answer quickly. A refresh that fails with a data-update error is then retried by the coordinator, up to 6 attempts with the wait doubling from 1 s (1, 2, 4, 8, 16 s, 31 s of waiting in total). The retry delays leave the bus idle between attempts instead of queuing the next request behind a slow one. A failure during first-time setup (hub initialization) is not retried by this loop. The retry count, first wait and ratio can be changed in `configuration.yaml`.
- **solaredge-modbus-multi does not probe for unofficial registers unless asked.** Battery and extra-entity detection are off by default, so no startup waits on those blocks. Meter detection is on by default and can be switched off at a site with no meter. Core can only skip blocks it has already settled as silent, and never skips meters or batteries.
- **A slow inverter works against solaredge-modbus-multi.** The same short timeout makes solaredge-modbus-multi less tolerant of an inverter that answers late (for example over Wi-Fi), which core's 30 s read timeout was added for. The user can raise the option. On a leader/follower site the maintainer's experience is that this trade-off favors short timeouts (see below).

## Devices and entities

Both create an inverter device with meter and battery sub-devices. solaredge-modbus-multi exposes more diagnostic entities; core disables several secondary measurements by default.

| Area                       | solaredge-modbus-multi                                                                                                                                                     | Core                                                                                                                                                                                              |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Inverter AC                | Power, energy, current, voltage, frequency, apparent/reactive power, power factor                                                                                          | Same set; voltage, frequency, apparent/reactive power and power factor disabled by default                                                                                                        |
| Inverter DC                | Power, current, voltage                                                                                                                                                    | Same                                                                                                                                                                                              |
| Inverter status            | Status, vendor status, and a Problem binary sensor (on at fault status, with vendor status value and text as attributes)                                                   | Status and a Problem binary sensor                                                                                                                                                                |
| Temperature                | Heat sink temperature                                                                                                                                                      | Temperature                                                                                                                                                                                       |
| Per-MPPT (Synergy) sensors | DC voltage, current, power, temperature and events per module                                                                                                              | Not exposed as entities; present in diagnostics. The docs say per-panel data needs the cloud-based SolarEdge integration                                                                          |
| Meters                     | Power, energy, current, voltage, frequency, VA, var, power factor, VAh/varh import/export, events                                                                          | Power, import/export energy (also per phase), per-phase power/current/voltage, frequency, VA, var, power factor; no events or VAh/varh                                                            |
| Batteries                  | Power, energy in/out, SOE, SOH, temperature, voltage, current, max charge/discharge power, status                                                                          | Same core set plus available energy (the docs) / usable and rated capacity (the code); no events                                                                                                  |
| Grid status                | On-grid binary sensor                                                                                                                                                      | On-grid binary sensor, plus a battery Charging binary sensor                                                                                                                                      |
| Energy counters            | Restores last value; options to allow battery energy reset and adjust rating                                                                                               | No equivalent options                                                                                                                                                                             |
| Diagnostic extras          | Last-update sensor, write-count sensor, power-control-enabled binary sensor, refresh button                                                                                | None                                                                                                                                                                                              |
| Device layout              | Inverter, meter and battery devices under the hub, plus a separate device for a DER battery (SunSpec model 713) linked to its inverter (when battery detection is enabled) | Inverter device; meters and batteries linked via device; stale ones removed; a Storage state of charge sensor on the inverter when a DER storage block reports charge and no battery block exists |
| Attachment changes         | Auto-detect options for meters, batteries, extras                                                                                                                          | Checks every 15 min; reloads the entry when meters, batteries, grid status or a control block appear or disappear                                                                                 |
| Diagnostics download       | Yes; includes the SunSpec model chain, power control, advanced power control and storage control data, DER battery and EV charger data, and dependency versions            | Yes; includes the SunSpec model chain, settings polls and control block data                                                                                                                      |
| Languages                  | 19 files in `translations/` (English plus 18 other languages), maintained by hand                                                                                          | English `strings.json`; other languages through HA's translation system                                                                                                                           |

The entity lists were compiled by reading entity key names in each codebase and have not been checked entry by entry.

## Controls and options

Both integrations can write to the inverter. solaredge-modbus-multi makes battery and control features opt-in and adds a commit step; core creates the controls when the corresponding block answers, and disables some by default.

### Warnings and register support

solaredge-modbus-multi distinguishes officially supported from unsupported registers. It treats as officially supported only the registers in `doc/sunspec-implementation-technical-note.pdf`, obtained from SolarEdge's site (version 3.2, June 2025). That covers the inverter, multiple MPPT and meters. It treats the following as unsupported:

- Grid status (40113), found by reverse engineering and not documented anywhere. Its register lies between the officially documented `I_Status_Vendor` (40108) and `I_Status_Vendor4` (40119), so the line is less clear than for the other blocks.
- Batteries, storage control, export control and power control, which appear in `Power-Control-Open-Protocol-for-SolarEdge-Inverters.pdf` (where batteries are called StorEdge). That document was not obtained directly from SolarEdge.
- The third battery block (58368, 0xE400), which is not in that document and was discovered by a community user.

solaredge-modbus-multi enables only officially supported features by default. Battery and control features are turned on separately under Configure, behind a warning that such changes can violate utility agreements, alter billing, overwrite provisioning by SolarEdge or the installer, and wear flash memory.

Core does not make this distinction between officially supported and unsupported registers. It
creates its controls when the corresponding block answers, with no warning or confirmation step in
the integration; its strings and code contain only log warnings. The core documentation page
(read 2026-10-10, as a summary) has a warning that the settings live in the inverter's flash
memory, "which is meant to be written now and then rather than continuously", and that export
limits may be part of a grid operator agreement. Its known limitations add that SolarEdge does not
document the control registers and that firmware varies. The warning is in the documentation, not
in the setup flow. The wording of the page changed since the earlier reading of the beta page, which
was quoted here before.

### Control entities

| Control                  | solaredge-modbus-multi                                                                                                         | Core                                                                                                                                                                                   |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Enabling controls        | Off by default; battery and control features are opt-in under Configure (Storage Control, Site Limit Control)                  | Created when the block answers; config-category entities; some disabled by default                                                                                                     |
| Storage mode selects     | Control mode, AC charge policy, default mode, command mode                                                                     | Same four                                                                                                                                                                              |
| Storage numbers          | AC charge limit, backup reserve, command timeout, charge limit, discharge limit                                                | Backup reserve, charge limit, discharge limit                                                                                                                                          |
| Site export              | Limit control mode and type selects, site limit, external production max, external production and negative site limit switches | Export limitation and limit type selects, site limit, external production max, external production and negative site limit switches (limit type and both switches disabled by default) |
| Power control            | Active power limit, cos phi, reactive power mode, power reduce, current limit                                                  | Active power limit, power factor setpoint (disabled by default)                                                                                                                        |
| Commit / default buttons | Commit and restore-defaults buttons for advanced power control                                                                 | None                                                                                                                                                                                   |
| Write handling           | Inverter command delay option; write counter sensor                                                                            | Library errors are translated to HA errors; rejected values raise `rejected_value`; the earlier shared write lock was removed                                                          |
| Polling options          | Polling frequency, request timeout, close connection after polling                                                             | None; timing is handled by the shared `modbus` connection                                                                                                                              |
| YAML Modbus conflict     | Repair issues for deprecated YAML Modbus and keep-open settings                                                                | Not applicable                                                                                                                                                                         |
| Repairs                  | Check configuration, ID setup failures, detection timeouts                                                                     | None defined                                                                                                                                                                           |

## Leader and follower inverters

The two integrations model a leader inverter with followers differently. solaredge-modbus-multi treats the bus as one system; core treats each device ID as a separate device. The observations below are the maintainer's, shared with the core team on 2026-09-30 and 2026-10-02. They have not been independently tested.

|                         | solaredge-modbus-multi                                                                   | Core                                                                                                                             |
| ----------------------- | ---------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Model                   | One hub; a loop over the list of device IDs for the leader and its followers             | One config entry per device ID, each with its own coordinators                                                                   |
| Polling                 | One ID at a time, in a single loop                                                       | Separate polls per entry (10 s readings, 5 min settings) that can overlap on the same bus                                        |
| Reported behavior       | n/a                                                                                      | Overlapping polls time out; the affected inverter alternates between available and unavailable                                   |
| Measurement consistency | All inverters and meters are read in the same loop                                       | Entries are read at different times, so sums can differ, for example a meter that measures the aggregate of all inverter outputs |
| Attached devices        | Meters and batteries can attach to the leader or any follower and are part of one system | Attached to the inverter entry they were read from                                                                               |

Single-inverter installations are not affected, and are probably the majority.

The core documentation does not mention leader or follower inverters.

**Leader and follower topology.** The inverter with the IP address is the parent (leader) and acts as a Modbus/TCP proxy. Followers are children on its internal RS485 chain, up to 32 per the specification. Communication with a follower goes through the leader, so one request to the leader can be in flight at a time.

**Reported issue.** The maintainer filed
[home-assistant/core#184259](https://github.com/home-assistant/core/issues/184259), "Too many
solaredge-modbus timeouts with leader/follower and detection" (2026-10-04; closed as completed on
2026-10-05 by PR #184290; assigned to frenck, milestone 2026.10.0). It was filed against Home Assistant Core 2026.10.0b0 on Home Assistant OS with an SE7600H
leader/follower setup, and covers both the polling overlap and the 15-minute detection. It reports
repeated errors of the form `read_holding_registers(40004, 65): Response timeout after 10.0
seconds`, the inverter alternating between available and unavailable with its entities unavailable,
and more than 683 occurrences logged within hours.

**15-minute feature re-check.** Core re-probes for supported blocks every 15 minutes. The core
documentation describes it: the device inventory is checked every 15 minutes, and the integration
reloads if hardware changes. It lists as a known limitation that meter or battery additions and
removals take up to 15 minutes to appear. Some SolarEdge inverters do not respond to registers they
do not support, so each probe of an unsupported block lasts a full timeout. According to the
maintainer, the other inverters cannot poll while one waits. solaredge-modbus-multi probes only for what its options enable.
Battery and extra-entity detection are off by default because those registers are not officially
supported, so an inverter without them is never asked. Meter detection is on by default (meters are
officially supported) and can be switched off. Core has no options flow.

**Changed in core 2026.10.1.** The reports in the issue above led to changes (PRs #184290, #185255
and #185518, read in the code, not tested):

- A block that stays silent on two checks in a row (setup, then the first 15-minute check) is
  recorded as settled and passed to the library as `assume_absent`. Later checks and later setups skip
  it. It is stored in the config entry (`silent_blocks`).
- Meters, batteries and the multiple-MPPT block are never settled, because finding hardware depends
  on them, so they are still probed every 15 minutes.
- Probing keeps the 10 s link default; reads after probing use a 30 s timeout, since a SolarEdge
  inverter on Wi-Fi can answer some requests later than 10 s.
- `solaredged` was bumped from 0.4.0 to 0.5.0 (see the library section).

A diagnostics file from one of the maintainer's inverters (taken on 2026.10.0b0) lists five entries in
`unresponsive_blocks`: `advanced_power_control`, `batteries`, `export_control`, `power_control` and
`storage_control`. That inverter does not support batteries, so according to the maintainer these
blocks will not become available. On 2026.10.0b0 the 15-minute check probed all five each time. With
2026.10.1, by reading the code, four of them (the control blocks) should be settled after the first
check and skipped, and `batteries` is still probed every 15 minutes. This has not been run against
the maintainer's inverter. Using the 10 s probe timeout shown in the error messages in the issue
(the value is not set in core's or the library's code), the estimated effect per day is:

| Item                          | 2026.10.0b0                   | 2026.10.1 (estimate, same inverter) |
| ----------------------------- | ----------------------------- | ----------------------------------- |
| Silent blocks per probe cycle | 5 (from the diagnostics file) | 1 (`batteries`)                     |
| Timeout wait per probe cycle  | 50 s (5 blocks at 10 s)       | 10 s                                |
| Probe cycles per day          | 96 (every 15 min)             | 96                                  |
| Missed 10 s polls per day     | 96 × 5 = 480                  | 96 × 1 = 96                         |
| Total 10 s polls per day      | 8,640                         | 8,640                               |
| Share of polling lost         | about 5.6%                    | about 1.1%                          |

The remaining wait still blocks the shared bus.

**Status of the issue (checked 2026-10-10).** The issue was closed by PR #184290. In the issue,
frenck said the diagnostics showed the cause: one inverter silent on five blocks, so each 15-minute
re-check cost five timeouts (about 50 seconds) and queued the other inverter's requests. He noted
that polling all units in one loop, which would address the sync issue, is a separate change not
covered by the fix. So the overlapping-polls and measurement-consistency points above are not
resolved in core 2026.10.1; the 15-minute probe cost is reduced, not removed.

**5-minute settings poll.** Core reads control settings every 5 minutes. Settings can also change by other routes: a change in the SolarEdge app, a change pushed by SolarEdge, or a utility program the inverter is enrolled in. Home Assistant sees those changes after up to 5 minutes, and such changes can also revert a value written over Modbus.

**Long timeouts.** The maintainer's experience is that very long timeouts are inappropriate for leader/follower setups, because the leader and its followers behave as one system rather than as separate devices on a shared bus. A request that waits 30 s holds up every other inverter behind the same leader, so the wait is paid by the whole site. A short timeout with backoff (solaredge-modbus-multi) gives up early and tries again later. This is the maintainer's observation, not a test, and core's 30 s timeout was added for inverters on Wi-Fi that answer late, a case where a short timeout fails the poll.

**Maintainer's suggested approach.** Place every device on the bus under one coordinator and one polling loop.

**Coexistence.** The maintainer reports running core alongside solaredge-modbus-multi with no Modbus/TCP contention, using the `modbus-connection` library without its new pooling feature.

## Migration

There is no automatic path between the two integrations. Entity IDs and unique IDs differ, so switching creates new entities and a gap in history unless entities are renamed.

- **Unique IDs.** Core uses `<serial>_<key>`; solaredge-modbus-multi derives IDs from host and port, so no entity is matched.
- **Device IDs.** Core creates one entry per inverter; a multi-inverter site needs one entry for each.
- **Shared connection.** Core uses HA's `modbus` integration. The maintainer reports it running alongside solaredge-modbus-multi without contention; other setups have not been tested. The core documentation lists as a known limitation that inverters accept a limited number of simultaneous Modbus TCP connections.
- **Dashboards and the Energy panel.** Entity names change (core names inverters `SolarEdge <model>`), and Energy dashboard sources must be selected again.
- **Features without a core equivalent.** Per-MPPT sensors, meter events, VAh/varh, write counter, refresh and commit buttons, polling options and the battery energy reset options.
- **Both installed together.** The domains differ (`solaredge_modbus_multi` and `solaredge_modbus`), so both can be installed at once.

## The python-solaredged library

Core depends on [frenck/python-solaredged](https://github.com/frenck/python-solaredged). The
library's first commit and first release (v0.1.0) are dated 2026-07-14, 88 days before 2026-10-10.
The source was read at tag v0.4.0 for the 2026-10-04 comparison; core 2026.10.1 pins 0.5.0. The v0.4.0 to v0.5.0 changes were read from the GitHub commit list and the diff of PR #106. Of 11 commits, 10 are dependency or CI maintenance; #106 is the only behaviour change.
Its readme credits `solaredge-modbus-multi` as a basis for its register map, and one of its tests
cites the solaredge-modbus-multi issue #1055.

- **One library object per device ID.** The readme says a site with several inverters creates one `SolarEdge` object per unit, all sharing one connection. The library has no leader/follower concept.
- **Probing is sequential (as of v0.4.0).** `async_probe` checks MMPPT, meters, batteries, the SunSpec model chain,
  then grid status and four control blocks, in order. A block that times out is recorded in
  `unresponsive_blocks` and treated as absent. A code comment says some firmware stops answering
  unsupported registers instead of refusing them. Each silent block therefore takes a full timeout
  before the next probe starts. The timeout length comes from `modbus-connection`, not this library;
  the issue above shows 10.0 s in its error messages.
- **0.5.0 adds `assume_absent`.** `async_probe` takes a keyword-only `assume_absent: frozenset[str]`. A block named there is not read: it is added to `unresponsive_blocks` and treated as absent. Applies to the multiple-MPPT, meter, battery, SunSpec model and optional control-block checks. Its docstring says a block named there cannot be discovered until probed for real again. The new test passes a first probe's `unresponsive_blocks` back in and checks that the second probe sends no reads to the silent addresses.
- **The library does not schedule probes.** It probes when `async_probe` is called; the 15-minute re-probe is in core's code.
- **Polling reads one block at a time.** Each sub-system is reported as updated or failed, so one failing block does not blank the others. If the first block times out and nothing has answered, the poll fails immediately.
- **The library supports more than core exposes.** It reads per-string DC data (SunSpec 160), up to three meters and VAh/varh energy. Core creates no per-string entities and no VAh/varh sensors.
- **Register sources.** Its readme states that the register map is based on SolarEdge's public SunSpec documentation and `solaredge-modbus-multi`.

**Coupling.** Core's integration and the `solaredged` library are coupled. The library is under the
same owner as the core codeowner (@frenck), and the integration is built directly on its API: the
integration's structure (one object per device ID, probe then poll, a report of failed blocks)
follows the library's API, and library bumps such as 0.2.3 to 0.4.0 come with integration changes.
`solaredge-modbus-multi` has not split out a library; register handling and polling live in the
integration and change together.

## Strengths by area

Core suits a single inverter, with or without a meter or battery, that needs a supported setup with no configuration. solaredge-modbus-multi targets multi-inverter sites, Synergy per-module data and fine-grained control.

**Core**

- Serial number as unique ID, with automatic address updates and a wrong-inverter check
- RS485 serial connections
- Per-sub-system availability, so a silent block does not blank the others
- No setup options: nothing for the user to configure or change, including detection of attached hardware. The trade-off is that probing for meters, batteries and the multiple-MPPT block repeats every 15 minutes and cannot be switched off; since 2026.10.1 other silent blocks are no longer re-probed
- Translations through HA's pipeline, and maintenance within Home Assistant

**solaredge-modbus-multi**

- Leader and followers modelled as one system: one hub, one polling loop and consistent readings, set up in one flow with fast and full ID scans
- Per-MPPT sensors and meter/MMPPT event sensors
- Options flow: polling interval, timeouts, command delay, and detection toggles. Detection of batteries and extra entities is off by default, so inverters that lack them are never probed for them, while core probes for batteries and meters every 15 minutes. Meter detection is on by default and can be switched off. The trade-off is that the user must change the option
- Commit and restore-defaults buttons, write counter, refresh button
- Battery energy reset and rating adjustment options
- A warning is shown before enabling features outside SolarEdge's official documentation

**Ideas for solaredge-modbus-multi**

- Read the serial number during setup and use it as the unique ID
- Check identity on each poll and flag a swapped inverter
- Update the host automatically when mDNS rediscovers a known inverter

## Open items

- Core's entity list is unchanged between 2026.10.0b0 and 2026.10.1 (only `__init__.py`, `const.py`, `coordinator.py`, the manifest and the quality scale file changed); the entity tables were not re-read
- The core documentation page was read on 2026-10-10 through a summarizing fetch, not the raw page; only the flash-memory sentence and the connection-limit sentence are verbatim quotes
- Library `solaredged` 0.5.0 was read through the PR #106 diff only (a summary of it, not the full source); the issue status was read from the GitHub page (a summary, not the raw thread)
