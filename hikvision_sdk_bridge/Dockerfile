ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apt-get update \
    && apt-get install --yes --no-install-recommends bash ca-certificates jq python3 \
    && rm -rf /var/lib/apt/lists/*

COPY bridge.py /opt/hikvision_sdk_bridge/bridge.py
COPY run.sh /run.sh
RUN chmod 755 /run.sh

CMD ["/run.sh"]
