---
name: Bug Report
about: Create a report to help us improve or fix a problem.
title: ''
labels: ''
assignees: ''

---

Before reporting a bug, make sure your configuration is correct and your LAN is working.
https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki/Configuration

**Describe the bug**
A clear and concise description of what the bug is.

**Expected behavior**
A clear and concise description of what you expected to happen.

**Screenshots**
If applicable, add screenshots of the problem and/or configuration.

**Logs**
Copy any log warnings or errors in Home Assistant from "custom_components.solaredge_modbus" and "pymodbus.client.sync".

**Debug Logs**
Debug logs are not always necessary, but may be required for more complex issues. You can enable debug logs by adding the following to your `configuration.yaml` file and restarting Home Assistant.
```
logger:
    default: warning
    logs:
        custom_components.solaredge_modbus_multi: debug
        pymodbus.client.sync: debug
```

**Home Assistant (please complete the following information):**
 - Home Assistant Core Version:
 - solaredge-modbus-multi Version:

**Additional context**
Add any other context about the problem here.
