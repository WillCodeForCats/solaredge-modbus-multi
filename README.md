[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

# SolarEdge Modbus Multi Device

Home Assistant integration `solaredge-modbus-multi` was designed for SolarEdge inverters using Modbus/TCP. It supports single inverters, multiple inverters, meters, batteries, and many other improvements over other integrations that didn't work well with a multi-device setup.

It is designed to communicate locally using Modbus/TCP where you have a single Leader (Master) inverter connected with one or more Follower (Slave) inverters chained using the RS485 bus. Inverters can have up to three meters and two batteries.

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

Requires Home Assistant 2022.8.0 and newer.

Read about more features on the wiki: [WillCodeForCats/solaredge-modbus-multi/wiki](https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki)

## Installation
Copy the `solaredge_modbus_multi` folder into to your Home Assistant `config/custom_components` folder,

OR

Install with [HACS](https://hacs.xyz): Search for "SolarEdge Modbus Multi" in the default repository.

After rebooting Home Assistant, this integration can be configured through the integration setup UI. If the integartion does not appear in Home Assistant after restarting, you may need to do one or more of the following:

* Reload the Home Assistant page
* Restart your browser
* Clear your browser cache

### Configuration
[WillCodeForCats/solaredge-modbus-multi/wiki/Configuration](https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki/Configuration)

### Documentation
[WillCodeForCats/solaredge-modbus-multi/wiki](https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki)

### Recommended Update Procedure (from releases older than v2.2.0)
1. Delete integration from Settings -> Devices & Services.
2. Update to v2.2.0 release.
3. Add the integration under Settings -> Devices & Services.

This procedure will preserve entity names. If updated in place, existing meter and battery entities will have a `_2` suffix after updating to a v2.2.x or higher release, or from a v1.x.x to a v2.x.x release. If this happens you can either update everything to use the new names, or follow the recommended update procedure to avoid renaming. This assumes the default entity names: custom names will have to be handled manually in any case.

### Upgrading from v1.1.x to v1.2.x
Follow instructions at: [How To Upgrade from v1.1.x to v1.2.x](https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki/How-To-Upgrade-from-v1.1.x-to-v1.2.x)

## Specifications
[WillCodeForCats/solaredge-modbus-multi/tree/main/doc](https://github.com/WillCodeForCats/solaredge-modbus-multi/tree/main/doc)

## Project Sponsors
None yet...
