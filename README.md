# SolarEdge Modbus Multi

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

This integration provides Modbus/TCP local polling to one or more SolarEdge inverters for Home Assistant.
Each inverter can support three meters and three batteries over Modbus/TCP. It works with single inverters,
multiple inverters, meters, batteries, and controls. The work in this repository is also being used in
other libraries and integrations.

By default, only features which are officially documented by SolarEdge are enabled: inverters,
synergy inverters, and meters. All of the battery (read only) and control features (read/write battery and
limit controls) can be enabled by configuring the hub after you add it to your Home Assistant. Support for
batteries and controls is from documentation not publicly available from SolarEdge or through user
discovery and may not be supported by SolarEdge.

## Features

- Home Assistant Auto Discovery (Zeroconf) support.
- Inverter support for 1 to 32 SolarEdge inverters.
- Meter support for 1 to 3 meters per inverter.
- Battery support for 1 to 3 batteries per inverter (SolarEdge proprietary).
- SunSpec DER Storage Capacity reporting (SunSpec model 713).
- Supports site limit and storage controls.
- Automatically detects meters and batteries.
- Supports Three Phase Inverters with Synergy Technology.
- Polling frequency configuration option (1 to 86400 seconds).
- Discovers inverters with Fast Scan (IDs 1–32), Complete Scan (IDs 1–247), or manual device ID list.
- Connects locally using Modbus/TCP - no cloud dependencies.
- Can use the Home Assistant shared Modbus connection or a direct connection.
- Informational sensor for device and its attributes
- Supports status and error reporting sensors.
- User friendly: Config Flow, Options, Repair Issues, and Reconfiguration.

Read about more features on the wiki: [WillCodeForCats/solaredge-modbus-multi/wiki](https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki)

## Installation

Install with [HACS](https://hacs.xyz): Search for "SolarEdge Modbus Multi" in the default repository,

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=WillCodeForCats&repository=solaredge-modbus-multi&category=integration)

OR

Download the [latest release](https://github.com/WillCodeForCats/solaredge-modbus-multi/releases) and copy the `solaredge_modbus_multi` folder into to your Home Assistant `config/custom_components` folder.

After rebooting Home Assistant, this integration can be configured through the integration setup UI. It also supports options, repair issues, and reconfiguration through the user interface.

### Configuration

[WillCodeForCats/solaredge-modbus-multi/wiki/Configuration](https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki/Configuration)

Inverter site limit and battery storage controls are disabled by default: not all inverters support controls. You will need to enable Power Control Options after adding your inverter hub in the integration.

### Using another integration with the same inverter

> [!WARNING]
> Running SolarEdge Modbus Multi and Home Assistant's built-in SolarEdge Modbus integration
> (`solaredge_modbus`) for the same inverter is not recommended. The built-in integration requests a
> high timeout (30 seconds), and Home Assistant applies it to the shared connection, so it is forced on
> SolarEdge Modbus Multi as well, which can cause slow or missed updates. If SolarEdge Modbus Multi
> raises the "Another Integration Shares This Inverter" repair issue, disable the other integration for this
> inverter and then restart Home Assistant: the shared connection keeps the long timeout until it is
> closed and reopened. Home Assistant may offer to set up the built-in integration when it discovers
> your inverter: check that you are adding the one you intend to use.
>
> Even trying the built-in integration briefly and then disabling or removing it still raises the
> timeout. The shared connection keeps the 30 second timeout after the other integration is gone, so
> restart Home Assistant afterwards.

Home Assistant shares a single Modbus/TCP connection per host and port between integrations, and the
connection's timing settings are shared too. The built-in integration requests a 30 second timeout,
which is much higher than the default of SolarEdge Modbus Multi of 3 seconds. The built-in
integration's timeout is fixed and cannot be configured, while the Modbus Request Timeout of
SolarEdge Modbus Multi can be changed in its options. The shared connection
will use the highest timeout any integration asks for, so 30 seconds applies to every request on it,
including those of SolarEdge Modbus Multi. A request that is slow to fail can then hold up polling by
SolarEdge Modbus Multi, and either integration can change the other's message spacing. The result can
be refreshes that take minutes, slow or missed updates, and unavailable entities.

Disabling the other integration does not shorten the timeout right away. The shared connection keeps
the highest timeout it was given until it is closed and reopened, so restart Home Assistant after
disabling it.

Scanning for inverters during setup uses the shared connection too, so while another integration has
set a high timeout, even the fast scan can take a long time. A scan has to wait out the full timeout
for every Device ID that has no device, and it tries each ID more than once before giving up on it. With
a 30 second timeout a Fast Scan can take tens of minutes and a Complete Scan hours, while with the
default 3 second timeout the same scans take a few minutes. A long scan can look like setup
has stalled, and the scan cannot shorten the wait because the shared connection applies the highest
timeout to every request, including the scan's own. Requests from other integrations on the same
connection are queued with the scan, so they are held up as well.

If you know your inverter Device IDs, use the manual setup instead, which does not scan. Otherwise, if
you can, disable the other integration and restart Home Assistant before adding SolarEdge Modbus Multi.

If you want to run both, open the options of SolarEdge Modbus Multi and change the Modbus Connection.
It has three choices:

| Modbus Connection                                         | What it does                                                                                                                 |
| --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Use the Home Assistant shared Modbus connection (default) | Shares one Modbus/TCP connection with other integrations that talk to the same inverter.                                     |
| Use direct connection                                     | Opens a separate Modbus/TCP connection with its own timeout and message spacing, which other integrations cannot change.     |
| Use direct connection and close it after each poll        | Same as above, and also closes the connection after every poll so that the inverter is free for other clients between polls. |

Closing after each poll relies on those other clients also closing their connections when idle: a client
that holds its connection open between requests can keep the inverter's connection in use regardless.

A direct connection has worked alongside the built-in integration on the maintainer's system, but
SolarEdge does not document support for more than one Modbus/TCP connection, so results may vary with
your inverter and firmware.

### Documentation

[WillCodeForCats/solaredge-modbus-multi/wiki](https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki)

### Minimum Required Versions

- Home Assistant 2026.10.0

## Specifications

[WillCodeForCats/solaredge-modbus-multi/tree/main/doc](https://github.com/WillCodeForCats/solaredge-modbus-multi/tree/main/doc)

## Language Translations

Translations are manually generated from English with Google Translate or using Claude. Native speaker corrections are welcome.
Correct the file in `custom_components/translations` and submit it through a pull request. If you are unsure how to
do that, please open an issue and copy/paste the changes or attach the updated file.

## Crediting Our Work

There are other integrations and libraries that have included this work directly or indirectly, in
some cases through AI agents. If you have used this work directly or indirectly, the author would appreciate it
if you would include a prominent credit and link to this repository so that your users are aware of its origin.
All of the original research on inverter behavior and undocumented features found here was curated by hand
in a pre-AI era. If you use issues previously reported, or a user's diagnostic data as test cases or to generate
code, including user feedback, please also extend credit to that user for their contributions as well as this
repository, preferably with a direct link to the issue.

## Project Sponsors

- [@bertybuttface](https://github.com/bertybuttface)
- [@dominikamann](https://github.com/dominikamann)
- [@maksyms](https://github.com/maksyms)
- [@pwo108](https://github.com/pwo108)
- [@barrown](https://github.com/barrown)
