## Solaredge Modbus Multi-Inverter

A Home Assistant integration for SolarEdge inverters.

Connects locally using Modbus/TCP to single or multiple inverters with support for meters.

{% if installed %}
{% if version_installed.replace("v", "").replace(".","") | int < 120  %}

### Breaking Change in v1.2.x
* Change domain and directory to `solaredge_modbus_multi`

### Required Steps to Upgrade to v1.2.0

Due to a beginner's mistake by not renaming this integration from the one it was based on, starting with release version 1.2.0 the directory name and domain are changing to `solaredge_modbus_multi`. This will require some manual steps to upgrade from any 1.1.x version.

Follow instructions at: [How To Upgrade from v1.1.x to v1.2.x](https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki/How-To-Upgrade-from-v1.1.x-to-v1.2.x)

---
{% endif %}
{% endif %}

### Features
* Inverter support for 1 to 32 SolarEdge inverters.
* Meter support for 1 to 3 meters (first inverter only).
* Custom polling frequency between 10 to 86400 seconds.
* Configurable inverter device address.
* Connects using Modbus/TCP - no cloud dependencies.
* Informational sensors for inverters and meters.
* Supports status and error reporting sensors.
* User friendly configuration through Config Flow.

Requires Home Assistant 2021.12.0 and newer.
