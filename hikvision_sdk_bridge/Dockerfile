FROM debian:bookworm-slim

ARG BUILD_VERSION="dev"
ARG BUILD_ARCH

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app" \
    io.hass.arch="${BUILD_ARCH}"

RUN apt-get update \
    && apt-get install --yes --no-install-recommends bash ca-certificates jq python3 \
    && rm -rf /var/lib/apt/lists/*

COPY lib-${BUILD_ARCH}/ /opt/hikvision_sdk_bridge/lib/
COPY bridge.py /opt/hikvision_sdk_bridge/bridge.py
COPY run.sh /run.sh
RUN chmod 755 /run.sh

ENV SDK_LIBRARY="/opt/hikvision_sdk_bridge/lib/libhcnetsdk.so" \
    LD_LIBRARY_PATH="/opt/hikvision_sdk_bridge/lib:/opt/hikvision_sdk_bridge/lib/HCNetSDKCom"

CMD ["/run.sh"]
