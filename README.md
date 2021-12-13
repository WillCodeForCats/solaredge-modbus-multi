[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)

# solaredge-modbus-multi
A Home Assistant integration for Solaredge inverters. Supports multiple inverters chained through RS485.

Works with 1 or more inverters - you don't need to have multiple inverters to use this integration, it will work fine with a single inverter.

This integration is for installations where you have a single Leader (Master) inverter connected to network, and one or more Follower (Slave) inverters connected behild it using one of the RS485 bus ports. This integration also supports up to three meters connected to the first inverter.

# Multiple Inverter Support
Important: The inverters must have sequential unit IDs (i.e. 1, 2, 3, ...). It doesn't matter which RS485 bus your inverter chain is on as long as it's configured as Solaredge leader/follower (master/slave in older firmware). If you have meters connected to inverter unit 1 the meter IDs *can* overlap the inverter unit IDs because they're on different busses (the solaredge meter ships with default ID 2).

This integration is developed on a system that consists of two inverters and one meter:
* Inverters (addressed 1 and 2) on RS485-1
* Ethernet connected to inverter 1 with modbus/tcp enabled
* E+I meter (address 2) connected to inverter 1 on RS485-2.
* Ethernet is also for Solaredge comms - no wireless or cell options

# Installation
Copy the contents of the custom_components folder into to your Home Assistant config/custom_components folder or install through HACS.
After rebooting Home Assistant, this integration can be configured through the integration setup UI.

NOTICE: Starting with version 1.1.0 this integration requires Home Assistant 2012.12.0 or newer.

# Enabling Modbus TCP on SolarEdge Inverter
1. Enable wifi direct on the inverter by switching the red toggle switch on the inverter to "P" position for less than 5 seconds.
2. Connect to the inverter access point like you would for a normal wifi network. The wifi password is published at the right side of the inverter. OR scan the QR code on the side of your inverter.
4. Open up a browser and go to http://172.16.0.1 > Site Communication. From this page you can enable Modbus/TCP.

This only needs to be done on the Leader (Master) inverter with the IP (network) connection.

# Credits
- https://github.com/binsentsu/home-assistant-solaredge-modbus
- https://github.com/julezman/home-assistant-solaredge-modbus/tree/multiple_inverters
- https://www.solaredge.com/sites/default/files/sunspec-implementation-technical-note.pdf

This started as a fork but things got too messy and I wasn't sure how to clean it up to get it merged upstream, so I started a new repository. It's now evolved into my "learn about python and HA" project and I've started to make larger changes.

Origional fork:
- https://github.com/WillCodeForCats/home-assistant-solaredge-modbus
