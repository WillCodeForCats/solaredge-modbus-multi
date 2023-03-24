[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

# SolarEdge Modbus Multi Device

Home Assistant integration `solaredge-modbus-multi` was designed for SolarEdge inverters using Modbus/TCP. It supports single inverters, multiple inverters, meters, batteries, and many other improvements over other integrations that didn't work well with a multi-device setup.

It is designed to communicate locally using Modbus/TCP where you have a single Leader inverter connected with one or more Follower inverters chained using the RS485 bus. Inverters support up to three meters and two batteries over modbus.

Simple single inverter setups are fully supported - multiple devices is a feature, not a requirement.

### Features
* Inverter support for 1 to 32 SolarEdge inverters.
* Meter support for 1 to 3 meters per inverter.
* Battery support for 1 or 2 batteries per inverter.
* Automatically detects meters and batteries.
* Supports Three Phase Inverters with Synergy Technology.
* Polling frequency configuration option (1 to 86400 seconds).
* Configurable starting inverter device ID.
* Connects using Modbus/TCP - no cloud dependencies.
* Informational sensor for device and its attributes
* Supports status and error reporting sensors.
* User friendly configuration through Config Flow.

Read about more features on the wiki: [WillCodeForCats/solaredge-modbus-multi/wiki](https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki)

Note: The modbus interface currently only defines up to 2 batteries per inverter (even if the SolarEdge cloud monitoring platform shows more).

## Installation
Install with [HACS](https://hacs.xyz): Search for "SolarEdge Modbus Multi" in the default repository,

OR

Copy the `solaredge_modbus_multi` folder into to your Home Assistant `config/custom_components` folder.

After rebooting Home Assistant, this integration can be configured through the integration setup UI.

### Configuration
[WillCodeForCats/solaredge-modbus-multi/wiki/Configuration](https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki/Configuration)

### Documentation
[WillCodeForCats/solaredge-modbus-multi/wiki](https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki)

### Required Versions
* Home Assistant 2023.2.0 or newer
* Python 3.10 or newer
* pymodbus 3.1.1 or newer

## Specifications
[WillCodeForCats/solaredge-modbus-multi/tree/main/doc](https://github.com/WillCodeForCats/solaredge-modbus-multi/tree/main/doc)

## Project Sponsors
* [@bertybuttface](https://github.com/bertybuttface)
* [@dominikamann](https://github.com/dominikamann)
* [@maksyms](https://github.com/maksyms)
* [@pwo108](https://github.com/pwo108)
