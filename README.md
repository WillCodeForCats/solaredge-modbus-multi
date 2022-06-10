[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

# solaredge-modbus-multi
_Note: readme has been updated for version 2.0.0 (currently in pre-release)_

A Home Assistant integration for SolarEdge inverters using Modbus/TCP. It supports single inverters, multiple inverters, meters, batteries, and many of improvements over other integrations that didn't work well with a multi-device setup.

It is designed to communicate locally using Modbus/TCP where you have a single Leader (Master) inverter connected with one or more Follower (Slave) inverters chained using the RS485 bus. Inverters can have up to three meters and two batteries.

### Features
* Inverter support for 1 to 32 SolarEdge inverters.
* Meter support for 1 to 3 meters per inverter.
* Battery support for 1 or 2 batteries per inverter.
* Automatically detects meters and batteries.
* Polling frequency configuration option (10 to 86400 seconds).
* Configurable starting inverter device ID.
* Connects using Modbus/TCP - no cloud dependencies.
* Informational sensor for device and its attributes
* Supports status and error reporting sensors.
* User friendly configuration through Config Flow.

Requires Home Assistant 2022.2.0 and newer.

## Installation
Copy the contents of the custom_components folder into to your Home Assistant config/custom_components folder or install through HACS.
After rebooting Home Assistant, this integration can be configured through the integration setup UI.

Starting with version 2.0.0 this integration requires Home Assistant 2022.2.0 or newer.

### Upgrading from v1.1.x to v1.2.x
Follow instructions at: [How To Upgrade from v1.1.x to v1.2.x](https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki/How-To-Upgrade-from-v1.1.x-to-v1.2.x)

## Configuration
https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki/Configuration

# Test Environment
This integration is developed on a system that consists of two inverters and one meter:
* Inverters (addressed 1 and 2) on RS485-1
* Ethernet connected to inverter 1 with modbus/tcp enabled
* E+I meter (address 2) connected to inverter 1 on RS485-2.
* Ethernet is also for SolarEdge comms - no wireless or cell options

# Credits
- https://www.solaredge.com/sites/default/files/sunspec-implementation-technical-note.pdf
- https://sunspec.org/wp-content/uploads/2015/06/SunSpec-Specification-Common-Models-A12031-1.6.pdf

This started as a fork but things got too messy and I wasn't sure how to clean it up to get it merged upstream, so I started a new repository.
It's now evolved into my "learn about python and HA" project and I've started to make larger changes.

Based on work from:
- https://github.com/WillCodeForCats/home-assistant-solaredge-modbus
- https://github.com/binsentsu/home-assistant-solaredge-modbus
- https://github.com/julezman/home-assistant-solaredge-modbus/tree/multiple_inverters
