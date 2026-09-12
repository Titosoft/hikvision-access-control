# Hikvision SDK Bridge

This add-on receives intercom callbacks from a Hikvision terminal over the
HCNetSDK server port, normally TCP 8000. It maintains one alarm channel and does
not poll the device.

## Before installing

The Hikvision runtime is proprietary and is not included. Download the Device
Network SDK for Linux from Hikvision and use the package matching the Home
Assistant host architecture. Copy the complete runtime library set to:

```text
/share/hikvision_sdk/lib/libhcnetsdk.so
/share/hikvision_sdk/lib/HCNetSDKCom/...
```

Keep any OpenSSL and component `.so` files from that same SDK release alongside
the files above. Mixing architectures or releases can prevent the add-on from
starting. The add-on uses a Debian/glibc base because the official Hikvision
Linux runtime is not compatible with Alpine/musl.

## Configuration

- `device_host`: IP address used by the Hikvision Access Control integration.
- `device_port`: SDK Server port, normally `8000`.
- `username` and `password`: local terminal credentials allowed to use HCNetSDK.
- `sdk_library`: full path to `libhcnetsdk.so` under `/share`.

After starting, look for `HCNetSDK alarm channel armed` in the log. The custom
integration will show **SDK bridge connection: Online** and update its
**Doorbell ringing** binary sensor from callbacks.

The add-on repeats only its local connection status every 60 seconds so the
integration can recover the diagnostic state after a Home Assistant restart.
That heartbeat does not query or poll the terminal; bell events remain native
HCNetSDK callbacks.

Only expose port 8000 on the trusted local network. Do not forward it through the
internet.
