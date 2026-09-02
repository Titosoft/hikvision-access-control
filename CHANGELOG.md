# Changelog

All notable changes to this project will be documented in this file.

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

[0.1.0]: https://github.com/titogarrido/ha-hikvision-access-control/releases/tag/v0.1.0
