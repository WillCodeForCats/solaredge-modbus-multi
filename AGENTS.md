# Repository Guidelines

**TL;DR:** Keep changes scoped to the Home Assistant integration, validate them
with Ruff and pytest, and protect live inverter details and write-capable controls.

## Project Structure & Module Organization

Runtime code lives in `custom_components/solaredge_modbus_multi/`. `__init__.py`
owns integration setup and coordinator lifecycle; `hub.py`, `modbus_transport.py`,
`scanner.py`, and `devices.py` handle Modbus/SunSpec behavior. Platform modules
such as `sensor.py`, `number.py`, and `switch.py` expose Home Assistant entities.
User-facing metadata is in `manifest.json`, `strings.json`, and `translations/`.

Tests live in `tests/` and generally mirror runtime modules. Shared fixtures are
in `conftest.py`, transport tests use `fake_modbus_server.py`, and
`tests/fixtures/*.json` contains golden snapshots. CI is defined in
`.github/workflows/test.yml`.

## Build, Test, and Development Commands

Use Python 3.14 to match CI (Home Assistant 2026.8+, the integration's floor,
requires it):

```bash
uv venv --python 3.14
source .venv/bin/activate
uv pip install -r requirements.txt -r requirements_test.txt "ruff==0.8.3" "pre-commit>=3.5.0"
ruff check custom_components/ tests/
ruff format --check custom_components/ tests/
python -m pytest tests/ -q
pre-commit run --all-files
```

Run a focused test while iterating, for example
`python -m pytest tests/test_hub.py -q`. There is no build or install step: the
integration is deployed as a git submodule of the `homekit` repository whose
`custom_components/solaredge_modbus_multi` directory is bind-mounted into both
Home Assistant containers. Never edit that live checkout in place — work in a
separate worktree and move the submodule pointer at deploy time (procedure in
the parent repository's `AGENTS.md`). `pyproject.toml` holds tool configuration
only; runtime pins live in `manifest.json`, test pins in `requirements*.txt`.

`PARALLEL_UPDATES` is `0` on the coordinator-driven `sensor` and `binary_sensor`
platforms and `1` on `number`, `select`, `switch` and `button`. It is a
per-platform semaphore on service calls, not an inverter lock — the transport
lock in `modbus_transport.py` is what serialises the single Modbus session.

## Coding Style & Naming Conventions

Use four-space indentation, double quotes, and an 88-character line target. Ruff
enforces E, W, F, I, and B rules plus import sorting. Use `snake_case` for
modules, functions, and fixtures; `PascalCase` for classes; and
`UPPER_SNAKE_CASE` for constants. Reuse existing hub, transport,
entity-description, and fixture patterns.

## Testing Guidelines

Pytest discovers `test_*.py`, `Test*`, and `test_*`; async mode is automatic.
Add focused regression tests for behavior changes, and use the fake server when
protocol or session behavior matters. Change golden fixtures only for deliberate
behavior or entity-metadata updates. No coverage percentage is enforced, but the
full suite must pass before review.

## Commit & Pull Request Guidelines

Recent fork history uses Conventional Commits: `feat:`, `fix:`, `refactor:`,
`test:`, `perf:`, and `chore:`; optional scopes such as `refactor(hub):` are
welcome. Keep commits focused. PRs should summarize behavior and risk, link
issues when relevant, and report exact Ruff/pytest results. Include screenshots
for visible config-flow or UI changes.

## Security & Hardware Safety

Never commit Home Assistant secrets, inverter addresses or serials, diagnostic
exports, or ignored `.claude/` and `DEPLOY_STATUS.md` notes. Keep automated tests
on mocks or the fake server. Treat Modbus writes and advanced power/storage
controls as hardware-affecting, and document safety assumptions.

### Hardware writes are gated, and the deployed policy is "off"

`hub.write_registers()` (Modbus FC16) refuses centrally unless
`ConfName.ALLOW_HARDWARE_WRITES` is set, and the `number` / `select` / `switch` /
`button` platforms create no write-capable entity while it is off. It defaults
off, and **both production instances are deliberately left that way** — the
parents inverter is never to be written to (decided 2026-08-06), and the owner
creates no write-capable entities anyway (`detect_extras: false`, both
advanced-control options off).

The option is still exposed in the options flow **on purpose**. It is per config
entry, so removing the toggle would also remove the capability from the owner,
which was never part of that decision. If writes are ever wanted, enabling them
is a deliberate act, and the central refusal in `hub.write_registers()` remains
the actual guard regardless.

## Decisions that look like unfinished work

### The manifest takes a modbus-connection *range*; the test pin is exact

`manifest.json` requires `modbus-connection[pymodbus]>=4.4.0,<5` while
`requirements.txt` pins `==4.10.0`. That is deliberate. Home Assistant core's own
`modbus` integration pins modbus-connection exactly (4.10.0 in 2026.9) and the HA
image ships that version; an exact *different* pin here made HA pip-install over
it on every first boot after an image update — a network dependency at boot, and
whichever integration loaded last decided which version both ran on. The range
is satisfied by whatever core ships (`util/package.py::is_installed` checks the
specifier), so no pip runs. The test pin follows the version production actually
has: bump it when the HA image moves, and run the suite. The fork touches only
the connection/unit layer, the `exceptions` and `encode`/`decode` helpers — the
surface that stayed compatible from 4.4 through 4.10. The `<5` cap is the guard
against a breaking major arriving through a core bump.

### `close()` is permanent — connection generations remain fork policy

`modbus_connection`'s `close()` sets `_closed` for good; a later `connect()`
raises `ClientClosedError`. modbus-connection 4.0.0's release notes state this as
deliberate design, not an alpha rough edge; 4.10.0 still closes for good and
`connect()` still rejects a closed instance. Version 4.2 added `disconnect()`
(4.9 put it on the unit protocol too) for reusing the same connection object
after dropping its link, but this fork still
retires failed and cancelled generations: its connection graph is small, while
replacement guarantees shielded connects are cleaned up and late callbacks
cannot touch live diagnostics. Keep `ModbusTransport`'s generations,
`_shielded_recycle`, and generation-bound `on_connection_lost`; do not simplify
them away merely because `disconnect()` exists.

### Stage D is closed — not deferred

The v4 migration deliberately kept `keep_modbus_open`, the `modbus:` YAML block,
config-entry schema 2.1, and our own write pacing, pending the library leaving
alpha. modbus-connection 4.0.0 shipped 2026-08-07, so that gate has passed — and
the work is **not** being done.

Its purpose was converging with upstream once it was safe. The fork no longer
tracks upstream, so that purpose is gone. What remains would be removing working
functionality behind a one-way 2.1 → 2.2 config-entry migration on two live
instances, for no user-visible gain. Note these are *unused*, not *inert*:
`keep_modbus_open` drives real branches (`hub.py:495,635`) and `modbus.timeout`
feeds `_mb_timeout` (`hub.py:174`); they simply never fire under the deployed
options. Reopen only if a concrete need appears.

### `awesomeversion` is required

It is not a pymodbus version guard and cannot be dropped: it gates
`use_status_vendor4` on the inverter's firmware `C_Version` (`devices.py:402`).
(It used to gate the inverted-power sensors on `HA_VERSION` too; that comparison
became constant once the floor moved to HA 2026.8 and was removed.)

### Upstream is not a remote

The fork stopped tracking WillCodeForCats/solaredge-modbus-multi in 2026 and the
`upstream` remote (with its ~60 branches and 316 tags) was removed from the
checkouts. `origin` is fetched with `tagOpt --no-tags`. For a one-off cherry-pick:

```bash
git remote add upstream https://github.com/WillCodeForCats/solaredge-modbus-multi.git
git fetch --no-tags upstream main
git cherry-pick <sha>
git remote remove upstream
```
