#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
# Start add-onu: panel WWW na porcie Ingress, ustawienia w /data (przetrwają restart i aktualizację).

export WLED_CONFIG=/data/wled_clocks.json
args=(--web 8099 --web-bind 0.0.0.0 --no-tui)

# host z opcji add-onu ma pierwszeństwo; pusty = ten zapisany w panelu
if bashio::config.has_value 'host'; then
    args+=(--host "$(bashio::config 'host')")
fi

# położenie do pogody i słońca: z opcji albo z ustawień Home Assistant
lat=$(bashio::config 'lat')
lon=$(bashio::config 'lon')
if ! bashio::config.has_value 'lat' || ! bashio::config.has_value 'lon'; then
    if loc=$(curl -fsS --max-time 10 -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" http://supervisor/core/api/config); then
        lat=$(jq -r '.latitude // empty' <<<"${loc}")
        lon=$(jq -r '.longitude // empty' <<<"${loc}")
    else
        bashio::log.warning "Nie udało się odczytać położenia z Home Assistant – pogoda dla Warszawy"
    fi
fi
if [[ -n "${lat}" && "${lat}" != "null" && -n "${lon}" && "${lon}" != "null" ]]; then
    args+=(--lat "${lat}" --lon "${lon}")
fi

# wiadomości od widzów (efekt „napisz”): tylko gdy skrzynka jest otwarta w panelu; domyślnie przez tunel bore.pub,
# z pustym msg_tunnel – na porcie 8098 (adres publiczny trzeba załatwić samemu)
args+=(--msg-port 8098)
if bashio::config.has_value 'msg_tunnel'; then
    args+=(--msg-tunnel "$(bashio::config 'msg_tunnel')" --msg-bore /usr/local/bin/bore)
fi
if bashio::config.has_value 'msg_public'; then
    args+=(--msg-public "$(bashio::config 'msg_public')")
fi
if bashio::config.true 'msg_proxy'; then
    args+=(--msg-proxy)
fi

bashio::log.info "Start: python3 /app/wled_clocks.py ${args[*]}"
exec python3 -u /app/wled_clocks.py "${args[@]}"
