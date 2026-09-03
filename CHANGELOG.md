# Changelog

All notable changes to this project will be documented in this file.

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

[0.1.1]: https://github.com/Titosoft/hikvision-access-control/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Titosoft/hikvision-access-control/releases/tag/v0.1.0
