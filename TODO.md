# TODO

## Dead code branches

Found while raising test coverage for the Silver `test-coverage` rule. None of
these can be reached by any input, so they can't be covered by tests; remove
them (or fix the condition they were meant to catch) instead. Line numbers are
as of 2026-11-15.

### helpers.py

- [ ] `float_to_hex()` (line 20): `except struct.error` never runs, since
  `struct.pack("<f", float(f))` doesn't raise `struct.error` for a float or
  int. Values beyond the float32 range raise `OverflowError` instead, which is
  not caught. Either catch `OverflowError` (and test with `1e39`) or remove the
  handler.

### hub.py

- [ ] `async_suns_scan_with_retry()` (line 174): the final `return None` is
  unreachable; the loop either returns the models or re-raises on the last
  attempt.
- [ ] `_async_init_solaredge()` meter detection (line 456): the
  `except (ModbusConnectionError, ModbusProtocolError, ModbusTimeoutError)`
  that raises `HubInitFailed` never runs, because `SolarEdgeMeter.init_device()`
  already turns those errors into `DeviceInvalid`.
- [ ] `_async_init_solaredge()` battery detection (line 499): same as above,
  `SolarEdgeBattery.init_device()` already turns those errors into
  `DeviceInvalid`.
- [ ] `initalized` setter (line 747): the `else` branch is never used; nothing
  sets `initalized` to anything but `True`.

### sensor.py

- [ ] `ACPowerInverted.native_value` (line 716): the `None` check never runs.
  `ACPower.native_value` never returns `None`; scaling a `None` value would
  raise first.
- [ ] `SolarEdgeACEnergy._process_data()` (line 1071): `except
  (ZeroDivisionError, OverflowError)` never runs. The scale factor is already
  limited to `SUNSPEC_SF_RANGE`, and an int times a power of ten in that range
  can't raise either.
- [ ] `MeterEvents.extra_state_attributes` (line 1955): `except KeyError` never
  runs. `METER_EVENTS` has every bit from 2 to 30, the full range the loop
  checks.
- [ ] `MeterVAhIE._process_data()` (line 2054) and
  `MetervarhIE._process_data()` (line 2128): `raise NotImplementedError` never
  runs; `__init__` already raises when there is no phase.
- [ ] `SolarEdgeBatteryEnergyExport._process_data()` (line 2445) and
  `SolarEdgeBatteryEnergyImport._process_data()` (line 2543): `except
  OverflowError` never runs; the code only compares and assigns ints.

### diagnostics.py

- [ ] `format_values()` (line 43): the non-dict `return format_input` never
  runs; every caller passes a dict.

## Also found (not dead code)

- [ ] `SolarEdgeBattery.init_device()`: a battery slot reporting NaN rated
  energy (the SunSpec not-implemented float) decodes to `None`, and
  `float_to_hex(None)` raises `TypeError` instead of `DeviceInvalid`. Hub setup
  then fails instead of skipping that battery. Add an `is None` check and a
  regression test.
- [ ] `tests/test_der_storage.py`: after PR #1169 merges, switch the three
  `async_get_device(identifiers=...)` asserts to
  `async_get_device_by_identifier((DOMAIN, ...), entry.entry_id)`; the old call
  is an error on Home Assistant 2026.10.
