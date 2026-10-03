# SolarEdge Modbus Multi (cohenam fork)

Home Assistant custom integration polling one or more SolarEdge inverters, their
meters and batteries over Modbus/TCP. A private fork of
[WillCodeForCats/solaredge-modbus-multi](https://github.com/WillCodeForCats/solaredge-modbus-multi)
that stopped tracking upstream in 2026 (last common point: upstream v3.3.x); it is
maintained for the two Home Assistant instances in the `homekit` repository and is
not published to HACS.

## Deployment

The integration is **not** installed — it is a git submodule of `homekit`
(`plugins/solaredge-modbus-multi`) whose `custom_components/solaredge_modbus_multi`
directory is bind-mounted read-only into both Home Assistant containers. Moving the
submodule pointer therefore changes the code for both instances at once; only the
restarts can be staggered. The deployment procedure, the rule about never editing
the live checkout in place, and the inverters' single-Modbus-session constraint are
documented in the parent repository's `AGENTS.md`.

Requirements:

- Home Assistant **2026.8.0** or newer (the `via_device_id` device-registry API).
- Python 3.14 (what HA 2026.8+ runs on; also the test harness floor).
- `pymodbus 3.13.1` and `modbus-connection >=4.4,<5` — the manifest accepts the
  version the HA core image ships so nothing is pip-installed at boot (see `AGENTS.md`).

## Features

- 1 to 32 inverters per hub, up to three meters and three batteries each; Synergy
  (multi-MPPT) inverters; EVSE detection.
- Config flow with fast scan (IDs 1–32), complete scan (IDs 1–247) or a manual ID
  list; options, reconfigure and repair flows; diagnostics download.
- Per-register-group polling cadence (below), hardware writes gated off by default.

### Hardware writes

Modbus write commands are **off by default**. While disabled, no write-capable
entity is created (number, select, switch, and the power-settings buttons) and the
hub refuses a write before it reaches the inverter. Turn on **Allow Hardware
Writes** in the integration options to enable them. The Refresh button is
unaffected — it only re-reads.

### Polling frequency per register group

Modbus reads are block reads, so the finest granularity for thinning polling is a
group of blocks rather than an individual entity. Each group has a cycle
multiplier: `1` means every poll, `6` means every sixth poll.

| Group | Registers | Default |
| --- | --- | --- |
| `core` | inverter model block | always every cycle, not configurable |
| `meter` | meter data | 1 |
| `battery` | battery data | 1 |
| `status` | grid on/off, status vendor 4 | 1 |
| `mmppt` | per-string (MMPPT) data | 1 |
| `evse` | EVSE data | 1 |
| `settings` | power control, site limit, storage | `slow_poll_multiplier` option (6) |

Set them in `configuration.yaml`:

```yaml
solaredge_modbus_multi:
  poll:
    status: 6
    battery: 3
```

Unknown group names, `core`, and values outside 1–60 are rejected at startup.
Skipped groups keep their last values — entities stay available and simply do not
change until the group is read again. A write always forces the `settings` group
on the next poll, so a control entity still shows its new value promptly.

## Development

`AGENTS.md` is the contributor guide: environment setup (Python 3.14, `uv`), Ruff and
pytest commands, the hardware-safety rules, and the design decisions that look like
unfinished work but are deliberate. Tests run on GitHub Actions for pull requests and
for pushes to `fix/**`, `feat/**` and `refactor/**` branches.

`docs/` holds the SunSpec implementation technical note the register maps are based on.

## License

Apache-2.0, as upstream.
