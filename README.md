# SolarEdge Modbus Multi

[![hacs_badge](https://img.shields.io/badge/HACS%20%7C%20Marketplace-Default-41BDF5.svg?style=for-the-badge)](https://contributors.home-assistant.io/marketplace/)

This integration provides Modbus/TCP local polling to one or more SolarEdge inverters for Home Assistant.
Each inverter can support three meters and three batteries. It works with single inverters, multiple inverters
(leader/follower systems), meters, batteries, and controls. The work in this repository is also being used in
other libraries and integrations.

Controls are supported, but you need to enable them. By default, only features which are officially documented
by SolarEdge are enabled: inverters, synergy inverters, and meters. All of the battery (read only) and control
features (read/write battery and limit controls) can be enabled by configuring the hub after you add it to your
Home Assistant. Support for batteries and controls is from documentation not publicly available from SolarEdge
or through user discovery not supported by SolarEdge.

All known modbus data has been added to this integration. If something is missing it's because there isn't
any modbus data available for it, or it hasn't been discovered yet in modbus captures.

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
- Error sensors for inverters and meters show the current error or meter events as text with the code.
- Shows the cause of faults and status changes in the Home Assistant activity log.
- User friendly: Config Flow, Options, Repair Issues, and Reconfiguration.
- Virtual System device with whole-site power flows calculated across all inverters, on by default for leader/follower systems.

### Virtual System Device

In a leader/follower system the site's totals for solar generation, consumption, and grid flows are not available
from any single device. Other integrations require you to create template sensors to add the entities together, which can be difficult
to set up and maintain.

SolarEdge Modbus Multi creates a System device that does work this for you. It is on by default when the hub has more than one
inverter, and off for a single inverter. Change it with **Enable Virtual System Device** in the integration options.

- Inputs are added together across every inverter on the hub, and across every meter set up as Export+Import.
- All inputs come from the same poll, so a total never mixes old and new readings.
- If any input is unavailable, the sensor is unavailable. It never falls back to 0.
- The individual sensors of your inverters and meters are not changed.

Sensors provided:

- Solar Generation, Consumption, Grid Import, Grid Export, and Self Consumption.
  These follow the wiki's [template sensors](https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki/Template-Sensors-for-Power-and-Energy) for systems without batteries,
  except Self Consumption, which is Solar AC Power minus Grid Export.
- Solar AC Power: from Production meters if you have any, otherwise from the inverters' AC output.

Limitations:

- Systems with batteries are not supported yet and get no System sensors.
- If two inverters are set up with the same physical meter, that meter is counted twice.

Virtual System is a new feature: please open an issue if you have suggestions for virtual sensors that can replace a template.

<!-- ha-marketplace:exclude-start -->

## Installation

Install with Marketplace (Home Assistant 2026.11 and later): Go to **Settings** → **Marketplace** and search for "SolarEdge Modbus Multi".

Install with [HACS](https://hacs.xyz) (before Home Assistant 2026.11): Search for "SolarEdge Modbus Multi" in the default repository.

Either way, you can also use this link to open the integration's page directly:

[![Open your Home Assistant instance and open a repository in the Marketplace or the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=WillCodeForCats&repository=solaredge-modbus-multi&category=integration)

OR

Download the [latest release](https://github.com/WillCodeForCats/solaredge-modbus-multi/releases) and copy the `solaredge_modbus_multi` folder into to your Home Assistant `config/custom_components` folder.

After rebooting Home Assistant, this integration can be configured through the integration setup UI.
It also supports options, repair issues, and reconfiguration through the user interface.
<!-- ha-marketplace:exclude-end -->

## Configuration

[WillCodeForCats/solaredge-modbus-multi/wiki/Configuration](https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki/Configuration)

Inverter site limit and battery storage controls are disabled by default: not all inverters support controls.
You will need to enable Power Control Options after adding your inverter hub in the integration.

### Using another integration with the same inverter

> [!WARNING]
> Running SolarEdge Modbus Multi and Home Assistant's built-in SolarEdge Modbus integration
> (`solaredge_modbus`) for the same inverter is not recommended. Home Assistant shares one Modbus/TCP
> connection between them, and they ask for very different timeouts. If SolarEdge Modbus Multi raises
> the "Another Integration Shares This Inverter" repair issue, either disable the other integration and
> reload SolarEdge Modbus Multi, or change SolarEdge Modbus Multi to a direct connection (see below).
> Home Assistant may offer to set up the built-in integration when it discovers your inverter: check
> that you are adding the one you intend to use.

Home Assistant shares a single Modbus/TCP connection per host and port between integrations. The
connection keeps a request timeout for each Device ID and uses the longest of them for every request.
The built-in integration asks for 30 seconds, which cannot be configured. SolarEdge Modbus Multi asks
for its Modbus Request Timeout, 10 seconds by default. Both normally use Device ID 1, so whichever
integration sets up last decides the timeout for that ID:

- If the built-in integration sets up last, 30 seconds applies to SolarEdge Modbus Multi as well. A
  request that is slow to fail can then hold up polling, causing slow or missed updates and unavailable
  entities.
- If SolarEdge Modbus Multi sets up last, its shorter timeout applies to the built-in integration too,
  which may then give up on requests it expected to wait for.

Which one sets up last can change from one Home Assistant start to the next, and reloading either
integration makes it the last one. Message spacing is also kept per Device ID: SolarEdge Modbus Multi
applies its own before every request, which changes it for the other integration too.

Disabling or removing the other integration does not clear the timeout it asked for while the
connection stays open. Reload SolarEdge Modbus Multi afterwards: if nothing else is using the
connection, it is closed and reopened with only SolarEdge Modbus Multi's timeout. Restarting Home
Assistant also works.

When another integration is already using the connection, scanning for inverters during setup opens a
separate connection to the inverter instead, so the scan is not slowed by the other integration's
timeout. An inverter accepts only a few connections at once, so this scan can fail to connect while
another client is connected. The manual setup checks the Device IDs you enter over the same separate
connection, so it can fail the same way. If you know your Device IDs, use the manual setup and select
"Skip Device ID validation", or disable the other integration until setup is complete.

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

There are other integrations and libraries that have included this work directly or indirectly. If you have used this
work the author would appreciate it if you would include a prominent credit and link to this repository so that your
users are aware of its origin. All of the original research on inverter behavior and undocumented features found
here was curated by hand in a pre-AI era. If you use issues previously reported, or a user's diagnostic data as
test cases or to generate code, including user feedback, please also extend credit to that user for their
contributions as well as this repository, preferably with a direct link to the issue.

## Project Sponsors

- [@bertybuttface](https://github.com/bertybuttface)
- [@dominikamann](https://github.com/dominikamann)
- [@maksyms](https://github.com/maksyms)
- [@pwo108](https://github.com/pwo108)
- [@barrown](https://github.com/barrown)
