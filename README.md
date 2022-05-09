[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

# solaredge-modbus-multi
A Home Assistant integration for SolarEdge inverters using local Modbus/TCP (no cloud). Supports multiple inverters, single inverters, meters, and extra information/error sensors.

This integration was created to address multiple inverter installations where you have a single Leader (Master) inverter connected to the network with one or more Follower (Slave) inverters connected using the RS485 bus. It also supports up to three meters connected to the first inverter. It still works with single inverter installations and can grow with you if you upgrade to multiple inverters in the future.

## Installation
Copy the contents of the custom_components folder into to your Home Assistant config/custom_components folder or install through HACS.
After rebooting Home Assistant, this integration can be configured through the integration setup UI.

NOTICE: Starting with version 1.1.0 this integration requires Home Assistant 2012.12.0 or newer.

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
