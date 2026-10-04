# solaredge-modbus-multi and HA Core SolarEdge Modbus: Comparison

*Created by Claude Code on 2026-10-04 from reading both codebases, with observations from the maintainer of solaredge-modbus-multi. Statements attributed to the maintainer are observations from the experience of writing and running solaredge-modbus-multi, not independent test results.*

| | Repository | Version compared |
| --- | --- | --- |
| solaredge_modbus_multi (custom) | [WillCodeForCats/solaredge-modbus-multi](https://github.com/WillCodeForCats/solaredge-modbus-multi) | v4.0.4 plus 2 commits (a0ea615) |
| solaredge_modbus (core) | [home-assistant/core](https://github.com/home-assistant/core), folder `homeassistant/components/solaredge_modbus` | tag `2026.10.0b0` (64ed916, 2026-09-30); documentation: [beta page](https://rc.home-assistant.io/integrations/solaredge_modbus) |

In the tables, "Custom" means solaredge-modbus-multi and "Core" means the Home Assistant core `solaredge_modbus` integration.

## Summary

The core integration uses one config entry per inverter and builds on the HA `modbus` integration. solaredge-modbus-multi uses one hub for a whole site, with more options and entities. Both use `_solaredge-modbus._tcp` mDNS discovery and local Modbus polling.

| | solaredge_modbus_multi (custom) | solaredge_modbus (core) |
| --- | --- | --- |
| Version / quality scale | 4.0.4 | Platinum quality scale; library `solaredged` 0.4.0 |
| Integration type | hub (one entry, many inverters) | device (one entry per inverter) |
| Modbus layer | `modbus-connection` + `tmodbus`, owns its connection | borrows a shared unit from HA's `modbus` integration |
| Codeowner | @WillCodeForCats | @frenck |
| Poll interval | user option, default 300 s | fixed: 10 s readings, 5 min settings, 15 min attachment check |
| Options flow | yes (polling, detection, power control, battery) | none |
| Entity identity | host:port based | inverter serial number |

## Setup and discovery

solaredge-modbus-multi finds every inverter behind a gateway in one flow. Core sets up one inverter at a time and does not scan device IDs.

| | Custom | Core |
| --- | --- | --- |
| Entry point | Menu: fast scan (IDs 1–32), full scan (1–247), or manual ID list | Menu: TCP or serial (RS485) |
| mDNS discovery | Yes; confirms the gateway, then offers the scan | Yes; reads `MODBUS_ID` from the announcement, probes the inverter, offers it |
| Multiple inverters on one bus | One entry; the device ID list covers all of them | One entry per device ID; each is added separately |
| Serial / RS485 | TCP only | TCP and serial (baud rate field, default 115200) |
| Default port / unit ID | 1502 / scanned | 1502 / 1, with unit ID in a collapsed "more options" section |
| Validation | Checks each ID answers as an inverter; can be bypassed with "Skip Device ID validation" | Probes the device; rejects EV chargers, missing serial numbers and non-SolarEdge devices |
| Reconfigure | Host, port, ID list | Host, port, unit ID, serial settings; aborts if the serial number differs (`wrong_device`) |
| Unique ID | host:port based | Inverter serial number; a moved address is updated on rediscovery |

Core checks the serial number on every poll and raises a config entry error if another inverter answers at the same address. No equivalent per-poll identity check was found in solaredge-modbus-multi; a replaced-inverter repair issue exists on an unmerged branch.

## Devices and entities

Both create an inverter device with meter and battery sub-devices. solaredge-modbus-multi exposes more diagnostic entities; core disables several secondary measurements by default.

| Area | Custom | Core |
| --- | --- | --- |
| Inverter AC | Power, energy, current, voltage, frequency, apparent/reactive power, power factor | Same set; voltage, frequency, apparent/reactive power and power factor disabled by default |
| Inverter DC | Power, current, voltage | Same |
| Inverter status | Status and vendor status | Status |
| Temperature | Heat sink temperature | Temperature |
| Per-MPPT (Synergy) sensors | DC voltage, current, power, temperature and events per module | Not exposed as entities; present in diagnostics |
| Meters | Power, energy, current, voltage, frequency, VA, var, power factor, VAh/varh import/export, events | Power, import/export energy (also per phase), per-phase power/current/voltage, frequency, VA, var, power factor; no events or VAh/varh |
| Batteries | Power, energy in/out, SOE, SOH, temperature, voltage, current, max charge/discharge power, status | Same core set plus usable and rated capacity; no events |
| Grid status | On-grid binary sensor | On-grid binary sensor |
| Energy counters | Restores last value; options to allow battery energy reset and adjust rating | No equivalent options |
| Diagnostic extras | Last-update sensor, write-count sensor, power-control-enabled binary sensor, refresh button | None |
| Device layout | Inverter, meter and battery devices under the hub, plus a separate device for a DER battery (SunSpec model 713) linked to its inverter (when battery detection is enabled) | Inverter device; meters and batteries linked via device; stale ones removed; a Storage state of charge sensor on the inverter when a DER storage block reports charge and no battery block exists |
| Attachment changes | Auto-detect options for meters, batteries, extras | Checks every 15 min; reloads the entry when meters, batteries, grid status or a control block appear or disappear |
| Diagnostics download | Yes; includes the SunSpec model chain, power control, advanced power control and storage control data, DER battery and EV charger data, and dependency versions | Yes; includes the SunSpec model chain, settings polls and control block data |
| Languages | 19 files in `translations/` (English plus 18 other languages), maintained by hand | English `strings.json`; other languages through HA's translation system |

The entity lists were compiled by reading entity key names in each codebase and have not been checked entry by entry.

## Controls and options

Both integrations can write to the inverter. solaredge-modbus-multi makes battery and control features opt-in and adds a commit step; core creates the controls when the corresponding block answers, and disables some by default.

### Warnings and register support

solaredge-modbus-multi distinguishes officially supported from unsupported registers. It treats as officially supported only the registers in `doc/sunspec-implementation-technical-note.pdf`, obtained from SolarEdge's website (version 3.2, June 2025). That covers the inverter, multiple MPPT and meters. It treats the following as unsupported:

- Grid status (40113), found by reverse engineering and not documented anywhere. Its register lies between the officially documented `I_Status_Vendor` (40108) and `I_Status_Vendor4` (40119), so the line is less clear than for the other blocks.
- Batteries, storage control, export control and power control, which appear in `Power-Control-Open-Protocol-for-SolarEdge-Inverters.pdf` (where batteries are called StorEdge). That document was not obtained directly from SolarEdge.
- The third battery block (58368, 0xE400), which is not in that document and was discovered by a community user.

solaredge-modbus-multi enables only officially supported features by default. Battery and control features are turned on separately under Configure, behind a warning that such changes can violate utility agreements, alter billing, overwrite provisioning by SolarEdge or the installer, and wear flash memory.

Core does not make this distinction between officially supported and unsupported registers. It creates its controls when the corresponding block answers, with no warning or confirmation step in the integration; its strings and code contain only log warnings. The core documentation page (beta) has an "Important Warning" section: register writes "must be used carefully", "An automation that writes one every few minutes will wear it out", and misconfigured settings may violate grid agreements. The warning is in the documentation, not in the setup flow.

### Control entities

| Control | Custom | Core |
| --- | --- | --- |
| Enabling controls | Off by default. Setup states that only officially documented features (inverters, Synergy inverters, meters) are enabled; battery and control features are opt-in under Configure (Storage Control, Site Limit Control) | Created when the block answers; all are config-category entities; some are disabled by default |
| Storage mode selects | Control mode, AC charge policy, default mode, command mode | Same four |
| Storage numbers | AC charge limit, backup reserve, command timeout, charge limit, discharge limit | Backup reserve, charge limit, discharge limit |
| Site export | Limit control mode and type selects, site limit, external production max, external production and negative site limit switches | Export limitation and limit type selects, site limit, external production max, external production and negative site limit switches (limit type and both switches disabled by default) |
| Power control | Active power limit, cos phi, reactive power mode, power reduce, current limit | Active power limit, power factor setpoint (disabled by default) |
| Commit / default buttons | Commit and restore-defaults buttons for advanced power control | None |
| Write handling | Inverter command delay option; write counter sensor | Library errors are translated to HA errors; rejected values raise `rejected_value`; the earlier shared write lock was removed |
| Polling options | Polling frequency, request timeout, close connection after polling | None; timing is handled by the shared `modbus` connection |
| YAML Modbus conflict | Repair issues for deprecated YAML Modbus and keep-open settings | Not applicable |
| Repairs | Check configuration, ID setup failures, detection timeouts | None defined |

## Leader and follower inverters

The two integrations model a leader inverter with followers differently. solaredge-modbus-multi treats the bus as one system; core treats each device ID as a separate device. The observations below are the maintainer's, shared with the core team on 2026-09-30 and 2026-10-02. They have not been independently tested.

| | Custom | Core |
| --- | --- | --- |
| Model | One hub; a loop over the list of device IDs for the leader and its followers | One config entry per device ID, each with its own coordinators |
| Polling | One ID at a time, in a single loop | Separate polls per entry (10 s readings, 5 min settings) that can overlap on the same bus |
| Reported behavior | n/a | Overlapping polls time out; the affected inverter alternates between available and unavailable |
| Measurement consistency | All inverters and meters are read in the same loop | Entries are read at different times, so sums can differ, for example a meter that measures the aggregate of all inverter outputs |
| Commands | A command to the leader can cascade to its followers | Each inverter is commanded separately |
| Attached devices | Meters and batteries can attach to the leader or any follower and are part of one system | Attached to the inverter entry they were read from |

Single-inverter installations are not affected, and are probably the majority.

The core documentation (beta) does not mention leader or follower inverters.

**Leader and follower topology.** The inverter with the IP address is the parent (leader) and acts as a Modbus/TCP proxy. Followers are children on its internal RS485 chain, up to 32 per the specification. Communication with a follower goes through the leader, so one request to the leader can be in flight at a time.

**Reported issue.** The maintainer filed [home-assistant/core#184259](https://github.com/home-assistant/core/issues/184259), "Too many solaredge-modbus timeouts with leader/follower and detection" (2026-10-04, open, assigned to frenck). It was filed against Home Assistant Core 2026.10.0b0 on Home Assistant OS with an SE7600H leader/follower setup, and covers both the polling overlap and the 15-minute detection. It reports repeated errors of the form `read_holding_registers(40004, 65): Response timeout after 10.0 seconds`, the inverter alternating between available and unavailable with its entities unavailable, and more than 683 occurrences logged within hours.

**15-minute feature re-check.** Core re-probes for supported blocks every 15 minutes. The core documentation describes it: the device inventory is checked every 15 minutes, and the integration reloads if hardware changes. It lists as a known limitation that meter or battery additions and removals take up to 15 minutes to appear. Some SolarEdge inverters do not respond to registers they do not support, so each probe of an unsupported block lasts a full timeout. According to the maintainer, the other inverters cannot poll while one waits. On the maintainer's inverters the wait occurs every 15 minutes while core looks for blocks such as batteries that those inverters do not have, and no data is collected during it. solaredge-modbus-multi can be set to skip detection of meters, batteries and extra entities, after which it does not probe for them again. This requires the user to change those options. Core has no options flow, so the periodic probe cannot be turned off.

A diagnostics file from one of the maintainer's inverters lists five entries in `unresponsive_blocks`: `advanced_power_control`, `batteries`, `export_control`, `power_control` and `storage_control`. The library records a block once when it times out, so the battery block counts once, not once per battery slot. That inverter does not support batteries, so according to the maintainer these blocks will not become available. Core's 15-minute check calls the full `async_probe` each time and does not skip blocks that were silent at the previous probe, so the same five timeouts recur. Using the 10 s timeout shown in the error messages in the issue above (the value is not set in core's or the library's code), the estimated effect per day is:

| Item | Value |
| --- | --- |
| Silent blocks per probe cycle | 5 (from the diagnostics file) |
| Timeout wait per probe cycle | 50 s (5 blocks at 10 s) |
| Probe cycles per day | 96 (every 15 min) |
| Missed 10 s polls per day | 96 × 5 = 480 |
| Total 10 s polls per day | 8,640 |
| Share of polling lost | about 5.6% |

**5-minute settings poll.** Core reads control settings every 5 minutes. Settings can also change by other routes: a change in the SolarEdge app, a change pushed by SolarEdge, or a utility program the inverter is enrolled in. Home Assistant sees those changes after up to 5 minutes, and such changes can also revert a value written over Modbus.

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

Core depends on [frenck/python-solaredged](https://github.com/frenck/python-solaredged). The source was read at tag v0.4.0, matching the `solaredged` 0.4.0 pin in the compared core commit. Its README credits `solaredge-modbus-multi` as a basis for its register map, and one of its tests cites the solaredge-modbus-multi issue #1055.

- **One library object per device ID.** The README says a site with several inverters creates one `SolarEdge` object per unit, all sharing one connection. The library has no leader/follower concept.
- **Probing is sequential.** `async_probe` checks MMPPT, meters, batteries, the SunSpec model chain, then grid status and four control blocks, in order. A block that times out is recorded in `unresponsive_blocks` and treated as absent. A code comment says some firmware stops answering unsupported registers instead of refusing them. Each silent block therefore takes a full timeout before the next probe starts. The timeout length comes from `modbus-connection`, not this library; the issue above shows 10.0 s in its error messages.
- **The library does not schedule probes.** It probes when `async_probe` is called; the 15-minute re-probe is in core's code.
- **Polling reads one block at a time.** Each sub-system is reported as updated or failed, so one failing block does not blank the others. If the first block times out and nothing has answered, the poll fails immediately.
- **The library supports more than core exposes.** It reads per-string DC data (SunSpec 160), up to three meters and VAh/varh energy. Core creates no per-string entities and no VAh/varh sensors.
- **Register sources.** Its README states that the register map is based on SolarEdge's public SunSpec documentation and `solaredge-modbus-multi`.

**Coupling.** Core's integration and the `solaredged` library are described by the maintainer as coupled: the integration's structure (one object per device ID, probe then poll, a report of failed blocks) follows the library's API, and library bumps such as 0.2.3 to 0.4.0 come with integration changes. `solaredge-modbus-multi` has not split out a library; register handling and polling live in the integration and change together.

## Strengths by area

Core suits a single inverter, with or without a meter or battery, that needs a supported setup with no configuration. solaredge-modbus-multi targets multi-inverter sites, Synergy per-module data and fine-grained control.

**Core**

- Serial number as unique ID, with automatic address updates and a wrong-inverter check
- RS485 serial connections
- Per-sub-system availability, so a silent block does not blank the others
- No setup options: nothing for the user to configure or change, including detection of attached hardware. The trade-off is that probing for absent hardware repeats every 15 minutes and cannot be switched off
- Translations through HA's pipeline, and maintenance within Home Assistant

**solaredge-modbus-multi**

- Leader and followers modelled as one system: one hub, one polling loop, consistent readings and cascaded commands, set up in one flow with fast and full ID scans
- Per-MPPT sensors and meter/MMPPT event sensors
- Options flow: polling interval, timeouts, command delay, and detection toggles. Switching detection off stops all probing for that hardware, which avoids repeated timeouts on inverters that lack it. The trade-off is that the user must change the option
- Commit and restore-defaults buttons, write counter, refresh button
- Battery energy reset and rating adjustment options
- A warning is shown before enabling features outside SolarEdge's official documentation

**Ideas for solaredge-modbus-multi**

- Read the serial number during setup and use it as the unique ID
- Check identity on each poll and flag a swapped inverter
- Update the host automatically when mDNS rediscovers a known inverter

## Open items

- Core's entity list in the final 2026.10.0 release; this comparison uses the 2026.10.0b0 beta tag
- The core documentation page was read as a summary of the [beta page](https://rc.home-assistant.io/integrations/solaredge_modbus), so quotes from it come from that summary
