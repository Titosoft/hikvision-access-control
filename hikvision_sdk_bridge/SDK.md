# Packaged HCNetSDK runtime

The add-on follows the architecture-specific packaging strategy used by
[pergolafabio/Hikvision-Addons](https://github.com/pergolafabio/Hikvision-Addons/tree/main/hikvision-doorbell).
The runtime files in `lib-aarch64` and `lib-amd64` were sourced from that
project's corresponding directories at commit
`f7c77933aa367e3a37f1f974ca309dcec5bcb11f`.

Packaged SDK builds:

- AArch64: `HCNetSDKV6.1.8.101_build20211210_Arm_aarch64-linux`
- AMD64: `HCNetSDKV6.1.6.3_build20200925_Linux64`

The Docker build copies only `lib-${BUILD_ARCH}` into the resulting image. The
Home Assistant app configuration points to a prebuilt multi-architecture image,
so the Supervisor selects the native AArch64 or AMD64 manifest automatically.

The release workflow publishes the image through GitHub Container Registry.
After its first successful run, ensure the `hikvision-sdk-bridge` package is
**Public** in the GitHub package settings so Home Assistant can pull it without
registry credentials.

These native binaries are third-party Hikvision software. They are not covered
by this repository's MIT license; their original vendor terms continue to apply.
