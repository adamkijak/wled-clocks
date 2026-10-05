ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:3.20
FROM ${BUILD_FROM}

# skrypt używa tylko biblioteki standardowej; obraz bazowy HA ma bashio, curl, jq i tzdata
RUN apk add --no-cache python3

COPY app/ /app/
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
