ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:3.20
FROM ${BUILD_FROM}

# skrypt używa tylko biblioteki standardowej; obraz bazowy HA ma bashio, curl, jq i tzdata
RUN apk add --no-cache python3

# bore – tunel na bore.pub dla efektu „napisz” (wiadomości z internetu za NAT-em, bez domeny);
# statyczny plik z wydań GitHub, suma SHA-256 sprawdzana przy budowaniu
ARG BUILD_ARCH=amd64
ARG BORE_VERSION=0.6.0
RUN set -e; \
    case "${BUILD_ARCH}" in \
      amd64) t=x86_64; sum=e484d1e3acba77169b773f31a5bfb34192d4b660f44a094a658a2522cd2270f7 ;; \
      aarch64) t=aarch64; sum=ffc4515f3617420b243758cf36ed6a63208d7dba76b2ec3e90d1f476a9742951 ;; \
      *) echo "brak bore dla ${BUILD_ARCH}"; exit 1 ;; \
    esac; \
    f="bore-v${BORE_VERSION}-${t}-unknown-linux-musl.tar.gz"; \
    curl -fsSLo "/tmp/${f}" "https://github.com/ekzhang/bore/releases/download/v${BORE_VERSION}/${f}"; \
    echo "${sum}  /tmp/${f}" | sha256sum -c -; \
    tar xzf "/tmp/${f}" -C /usr/local/bin bore; \
    rm "/tmp/${f}"

COPY app/ /app/
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
