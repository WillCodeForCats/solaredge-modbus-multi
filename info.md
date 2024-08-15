## SolarEdge Modbus Multi

This integration provides Modbus/TCP local polling to one or more SolarEdge inverters. Each inverter can support three meters and three batteries over Modbus/TCP. It works with single inverters, multiple inverters, meters, and batteries. It has significant improvements over similar integrations, and solaredge-modbus-multi is actively maintained.

Read more on the wiki: [WillCodeForCats/solaredge-modbus-multi/wiki](https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki)

## Features
* Inverter support for 1 to 32 SolarEdge inverters.
* Meter support for 1 to 3 meters per inverter.
* Battery support for 1 to 3 batteries per inverter.
* Supports site limit and storage controls.
* Automatically detects meters and batteries.
* Supports Three Phase Inverters with Synergy Technology.
* Polling frequency configuration option (1 to 86400 seconds).
* Configurable starting inverter device ID.
* Connects locally using Modbus/TCP - no cloud dependencies.
* Informational sensor for device and its attributes
* Supports status and error reporting sensors.
* User friendly: Config Flow, Options, Repair Issues, and Reconfiguration.

Requires Home Assistant 2024.4.0 and newer with pymodbus 3.6.6 and newer.
