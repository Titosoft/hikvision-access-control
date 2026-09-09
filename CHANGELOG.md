# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- Executable `bump_version.sh` release workflow with patch/minor/major or explicit
  versions, a dry-run preview, validation, version commit, atomic branch/tag push,
  and GitHub Release publication using the unreleased changelog notes.

### Changed

- Show unknown events with their raw ISAPI type or access-control major/minor
  codes in parentheses in both the event entity and last-event sensor. Labels
  use the Home Assistant server language when the integration is loaded.
- Expose the stable classification as `event_code` on both entities. Automations
  matching the previous unknown `event_type` or sensor state must use this
  attribute; known event types are unchanged.

### Fixed

- Install missing release-test dependencies automatically, including in virtual
  environments created without `pip` when `uv` is available.
- Ignore ISAPI `videoloss` notifications with an `inactive` state, which are
  stream heartbeats, so they do not overwrite the latest access event or flood
  its history with unknown events. Active video-loss alerts remain available.
- Preserve pending access pictures when a heartbeat arrives before the image.

## [0.1.4] - 2026-09-08

### Added

- Classification for documented access denial, authentication failure, physical
  door, exit-button, input fault, duress, and tamper events.
- Doorbell detection from both documented access-control codes `5/37` (doorbell)
  and `5/51` (call center).
- Doorbell detection from documented `changedCallStatus` events whose call status
  changes to `ring`, for video-intercom firmwares.

### Fixed

- Accept hexadecimal `majorEventType` and `subEventType` strings in addition to
  the documented decimal representation.
- Include `unknown_isapi_event` in the last-event sensor options instead of letting
  Home Assistant render that valid diagnostic state as unknown.
- Redact caller, employee, and card identifiers from nested diagnostic event data.

## [0.1.3] - 2026-09-07

### Added

- Diagnostic `unknown_isapi_event` events for non-heartbeat ISAPI payloads not yet
  classified by the integration, including their event type and event-specific data.

### Fixed

- Parse JSON alert parts even when a Hikvision firmware labels them as `text/json`.
- Preserve nested fields from non-access-control XML alerts so device-specific
  intercom button payloads can be identified without guessing.

## [0.1.2] - 2026-09-07

### Added

- Official access-control doorbell event `majorEventType: 5`, `subEventType: 37`.
- Dedicated last-visitor camera for automations and notifications.
- Visitor snapshot fallback through `/Streaming/channels/101/picture` when the
  doorbell event does not include a JPEG attachment.

### Fixed

- Delay the doorbell event until its attached image or snapshot fallback is ready,
  allowing notification automations to use the current visitor picture.
- Suppress repeated notifications for the same doorbell event serial number or
  timestamp.

## [0.1.1] - 2026-09-02

### Added

- XML `EventNotificationAlert` support in addition to JSON event payloads.
- Door-control capability discovery before exposing the remote-open button.
- Documented card, PIN, fingerprint, and combined successful authentication events.

### Fixed

- Validate ISAPI `ResponseStatus` bodies so application-level errors are not treated
  as successful door commands.
- Keep the visible `Picture` attachment as the latest access image and ignore the
  separate thermal JPEG.
- Ignore unrelated JPEG stream parts that are not attached to an access event.
- Point HACS and Home Assistant metadata to the actual GitHub repository.

## [0.1.0] - 2026-09-02

### Added

- Initial HACS-compatible release.
- UI configuration, reconfiguration, and reauthentication flows.
- Local HTTPS/ISAPI event stream with HTTP Digest authentication.
- Remote door button, native event entity, access sensors, relay state, connection
  state, and latest-access JPEG camera.
- Automatic `alertStream` reconnection and clean client shutdown.
- English and Brazilian Portuguese translations.
- HACS, hassfest, and Python test workflows.

### Security

- Diagnostics redact host, username, password, user name, and employee ID.
- Only event mappings confirmed by the supplied DS-K1T344 observations are
  classified.

[0.1.4]: https://github.com/Titosoft/hikvision-access-control/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/Titosoft/hikvision-access-control/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/Titosoft/hikvision-access-control/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/Titosoft/hikvision-access-control/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Titosoft/hikvision-access-control/releases/tag/v0.1.0
