# Appliance state recovery

This branch addresses stale connection/door readings and laundry cycle switches
remaining on after completion. It is a development build, not a guarantee of
connectivity to Haier's cloud. No appliance start/stop command is part of recovery.

## Changes

- Retry initial setup automatically through Home Assistant's backoff when DNS,
  a connection, or a request times out before the recovery coordinator exists.
  Close the failed client before retrying. Authentication and other non-transport
  errors are not silently converted into connectivity failures.
- Refresh every appliance through REST every five minutes, independently of MQTT
  pushes and changes to settings. A busy appliance cannot postpone another one's
  fallback refresh.
- Bound each request to 30 seconds. Continue refreshing other appliances after a
  failure, mark failed device readings unavailable, and recover on a later success.
- Keep program selections: refresh telemetry and the library's `settings` command,
  not the pending `startProgram` settings.
- Cancel timers/in-flight recovery and close the library's MQTT client on unload.
- The companion library synchronizes connection events with the connection sensor,
  recalculates laundry active/pause/program state after MQTT updates, handles new
  parameters and malformed messages, and dispatches messages on the asyncio loop.
- A REST snapshot fetched before a newer push is discarded rather than overwriting
  that update. Newer cloud snapshots can still be stale at their source.

The manifest pins the companion library to an immutable commit and an explicit
development version. Install this branch only as a deliberate test deployment.
Version `0.19.3.dev1` adds startup retry to the state recovery in `0.19.3.dev0`;
updating the integration's Python code requires a Home Assistant restart.

## Comparison reviewed

- [mmalolepszy/hon-revived](https://github.com/mmalolepszy/hon-revived): kept as the
  base because it is the installed integration family. Its main branch already has
  a newer library watchdog fix beyond the released 0.19.2 library.
- [Existing stale connectivity report](https://github.com/mmalolepszy/hon-revived/issues/34)
  and [missed wash updates](https://github.com/mmalolepszy/hon-revived/issues/55)
  match the classes of symptom addressed here.
- [Odyno's contribution](https://github.com/mmalolepszy/hon-revived/pull/64) adds a
  five-minute coordinator polling fallback and lifecycle cleanup, with many other
  changes. It is a useful direction, but a shared coordinator's ordinary polling
  deadline is reset by `async_set_updated_data`, so frequent pushes can postpone
  it. This branch keeps a separate timer and preserves entity unique IDs.
- [Odyno/pyhon-revived](https://github.com/Odyno/pyhon-revived) also addresses MQTT
  cleanup, malformed messages and scalar attribute comparisons. This branch limits
  its changes to state freshness and lifecycle rather than taking the full refactor.
- [rwsender/hon-revived](https://github.com/rwsender/hon-revived) adds a stock-program
  start service; its setup still uses push-only state updates.
- [gvigroux/hon](https://github.com/gvigroux/hon) uses coordinators and explicit
  refreshes in its own implementation. Moving integrations would require a separate
  device/entity compatibility review; it is not established as a better replacement.
- [Andre0512/hon](https://github.com/Andre0512/hon) is the original project; its
  reported latest push is from 2024, so it is not a freshness upgrade over Revived.

## Validation

Run `python -m pytest -q` with Home Assistant, the pinned companion library, pytest
and pytest-asyncio installed. Tests use fake appliances and a real HA coordinator;
they never log into hOn or start an appliance. Startup tests cover DNS errors,
connection failures and timeouts, including cleanup failure, without leaving
timers or partial runtime state. Companion-library tests cover live
connection synchronization, cycle completion, pause, door state, missed pushes,
thread dispatch, malformed messages, snapshot races and shutdown cleanup.

Current HA compatibility is checked by the State regression tests GitHub workflow.
The targeted tests pass on Home Assistant 2026.9.0, and HACS/hassfest validation
passes. The inherited Python quality workflows still report baseline issues:
the integration has two pre-existing return-type errors in climate/binary_sensor;
the library has existing complexity/formatting failures and eight type errors.
The library's type failures were reproduced against untouched upstream main.
Those wider cleanups are outside this state-recovery change and have not been hidden
by weakening or disabling checks.
Actual cloud outages, unavailable Wi-Fi and machine-side refusal can still prevent
updates or starts. The dashboard should continue to require appliance confirmation.
