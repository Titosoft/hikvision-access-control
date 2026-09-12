# Hikvision SDK Bridge

This optional Home Assistant add-on keeps one HCNetSDK alarm channel armed on
port 8000. It converts the physical intercom button callback and call-status
payloads into local Home Assistant bus events. It never polls the terminal.

The add-on image already contains the architecture-specific HCNetSDK runtime.
No files need to be copied to `/share`. The image uses the AArch64 or AMD64
library directory selected at build time and a Debian/glibc base compatible with
the packaged runtime. See [SDK.md](SDK.md) for versions and provenance.

Add this GitHub repository to the Home Assistant add-on store, install
**Hikvision SDK Bridge**, and configure the terminal IP, port 8000, local device
user, and password. The matching Hikvision Access Control custom integration
must also be installed and configured for the same IP address.

On success the add-on log contains:

```text
HCNetSDK alarm channel armed
```

The integration then reports `SDK bridge connection: Online` and creates the
`Doorbell ringing` binary sensor. A `COMM_ALARM_BUTTON_DOWN_EXCEPTION` callback
turns it on immediately. A call-status end event turns it off; if the firmware
does not send that transition, a local 45-second timer clears it. The timer does
not contact or poll the terminal.
