# Hikvision SDK Bridge

This optional Home Assistant add-on keeps one HCNetSDK alarm channel armed on
port 8000. It converts the physical intercom button callback and call-status
payloads into local Home Assistant bus events. It never polls the terminal.

The proprietary Hikvision libraries are deliberately not redistributed. Download
the Device Network SDK for the Linux architecture used by Home Assistant, accept
Hikvision's license, and copy its runtime libraries to:

```text
/share/hikvision_sdk/lib/libhcnetsdk.so
/share/hikvision_sdk/lib/HCNetSDKCom/...
```

All dependent `.so` files supplied with the same SDK build must stay beside
`libhcnetsdk.so` or under `HCNetSDKCom`. Do not mix architectures or SDK builds.
The container deliberately uses Debian/glibc to match the official Linux SDK.

Add this GitHub repository to the Home Assistant add-on store, install
**Hikvision SDK Bridge**, and configure the terminal IP, port 8000, local device
user, password, and library path. The matching Hikvision Access Control custom
integration must also be installed and configured for the same IP address.

On success the add-on log contains:

```text
HCNetSDK alarm channel armed
```

The integration then reports `SDK bridge connection: Online` and creates the
`Doorbell ringing` binary sensor. A `COMM_ALARM_BUTTON_DOWN_EXCEPTION` callback
turns it on immediately. A call-status end event turns it off; if the firmware
does not send that transition, a local 45-second timer clears it. The timer does
not contact or poll the terminal.
