## SolarEdge Modbus Multi-Inverter

A Home Assistant integration for SolarEdge inverters.

Connects locally using Modbus/TCP to single or multiple inverters with support for meters.

{% if prerelease %}
**v2.0.0 Pre-Release Notes**: [Release v2.0.0-pre.1](https://github.com/WillCodeForCats/solaredge-modbus-multi/releases/tag/v2.0.0-pre.1)
{% endif %}

{% if installed %}
{% if version_installed.replace("v", "").replace(".","") | int < 120 %}

### Required Steps to Upgrade to v1.2.0

Follow instructions at: [How To Upgrade from v1.1.x to v1.2.x](https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki/How-To-Upgrade-from-v1.1.x-to-v1.2.x)

Make sure you have a full backup before making changes - backups are always best practice.

---
{% endif %}
{% endif %}

## Features
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
