#!/usr/bin/env bash
# Uruchomienie na komputerze: TUI w terminalu (domyślnie), np.
#   scripts/run_local.sh --host 192.168.68.81
#   scripts/run_local.sh --host 192.168.68.81 --web 8099     # TUI + panel WWW na http://localhost:8099/
exec python3 "$(dirname "$0")/../wled_clocks/app/wled_clocks.py" "$@"
