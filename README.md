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
- Battery support for 1 to 3 batteries per inverter.
- Supports site limit and storage controls.
- Automatically detects meters and batteries.
- Supports Three Phase Inverters with Synergy Technology.
- Polling frequency configuration option (1 to 86400 seconds).
- Discovers inverters with Fast Scan (IDs 1–32), Complete Scan (IDs 1–247), or manual device ID list.
- Connects locally using Modbus/TCP - no cloud dependencies.
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

### Documentation

[WillCodeForCats/solaredge-modbus-multi/wiki](https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki)

### Minimum Required Versions

- Home Assistant 2025.9.0
- modbus-connection 4.10.0 or newer

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
