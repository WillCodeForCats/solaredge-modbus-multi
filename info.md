## SolarEdge Modbus Multi

Integrates SolarEdge inverters with Modbus/TCP local polling. Single inverters, multiple inverters, meters, and batteries are supported.

Many improvements over other integrations that didn't work well with a multi-device setup.

Simple single inverter setups are fully supported - multiple devices is a feature, not a requirement.

Read more on the wiki: [WillCodeForCats/solaredge-modbus-multi/wiki](https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki)

## Features
* Inverter support for 1 to 32 SolarEdge inverters.
* Meter support for 1 to 3 meters per inverter.
* Battery support for 1 or 2 batteries per inverter.
* Supports site limit and storage controls.
* Automatically detects meters and batteries.
* Supports Three Phase Inverters with Synergy Technology.
* Polling frequency configuration option (1 to 86400 seconds).
* Configurable starting inverter device ID.
* Connects locally using Modbus/TCP - no cloud dependencies.
* Informational sensor for device and its attributes
* Supports status and error reporting sensors.
* User friendly configuration through Config Flow.

Requires Home Assistant 2023.9.1 and newer with pymodbus 3.5.1 and newer.
