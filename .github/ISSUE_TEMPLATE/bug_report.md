---
name: Bug Report
about: Create a report to help us improve or fix a problem.
title: ''
labels: ''
assignees: ''

---
<!-- IF YOU DO NOT FILL OUT THIS TEMPLATE YOUR ISSUE WILL BE CLOSED -->
<!-- Asking for help or basic questions in an issue will be converted to a discussion and the issue will be closed. -->
<!-- If you delete the template the issue will be closed and you will be asked to resubmit using the template. -->

Before reporting a bug, make sure your configuration is correct, your LAN is working, and you have read about the "Known Issues" in the wiki:
https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki

**Describe the bug**
A clear and concise description of what the bug is.

**Expected behavior**
A clear and concise description of what you expected to happen.

**Screenshots**
If applicable, add screenshots of the problem and/or configuration.

**Logs**
Copy any logs in Home Assistant from "custom_components.solaredge_modbus".

**Debug Logs**
Debug logs are not always necessary, but may be required for more complex issues. You can enable debug logs by adding the following to your `configuration.yaml` file and restarting Home Assistant.
```
logger:
    default: warning
    logs:
        custom_components.solaredge_modbus_multi: debug
```
Debug logging will generate a large amount of data: it is recommended to configure it, collect the data needed, then remove debug logging during normal operation.

**Home Assistant (please complete the following information):**
 - Home Assistant Core Version:
 - solaredge-modbus-multi Version:

**Additional context**
Add any other context about the problem here.
