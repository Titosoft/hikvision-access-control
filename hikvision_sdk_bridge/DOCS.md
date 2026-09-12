# Hikvision SDK Bridge

This add-on receives intercom callbacks from a Hikvision terminal over the
HCNetSDK server port, normally TCP 8000. It maintains one alarm channel and does
not poll the device.

## Before installing

The prebuilt image includes the matching HCNetSDK runtime for each supported
architecture. No manual download or `/share/hikvision_sdk` directory is needed.
The add-on uses a Debian/glibc base and selects only the matching library folder
while building each image.

Supported Home Assistant architectures are `aarch64` and `amd64`. Current Home
Assistant releases no longer support `armv7` apps.

## Configuration

- `device_host`: IP address used by the Hikvision Access Control integration.
- `device_port`: SDK Server port, normally `8000`.
- `username` and `password`: local terminal credentials allowed to use HCNetSDK.

After starting, look for `HCNetSDK alarm channel armed` in the log. The custom
integration will show **SDK bridge connection: Online** and update its
**Doorbell ringing** binary sensor from callbacks.

The add-on repeats only its local connection status every 60 seconds so the
integration can recover the diagnostic state after a Home Assistant restart.
That heartbeat does not query or poll the terminal; bell events remain native
HCNetSDK callbacks.

Only expose port 8000 on the trusted local network. Do not forward it through the
internet.
