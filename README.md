# wled-clocks

145 kreatywne zegary i efekty dla panelu WLED 120x12 (DDP), tylko biblioteka standardowa Pythona 3.8+.
Trzy sposoby sterowania, ta sama logika (`Engine`):

- **TUI** w terminalu (jak dotąd),
- **panel WWW** (`--web PORT`), razem z TUI albo bez niego,
- **add-on Home Assistant** z panelem w pasku bocznym (Ingress).

## Na komputerze

```bash
scripts/run_local.sh --host 192.168.68.81                 # TUI
scripts/run_local.sh --host 192.168.68.81 --web 8099      # TUI + panel na http://localhost:8099/
scripts/run_local.sh --host 192.168.68.81 --web 8099 --no-tui   # sam panel WWW (np. w tle)
scripts/run_local.sh --list                               # wszystkie efekty
scripts/run_local.sh --preview demo.gif --mode roj --seconds 8
```

Panel WWW domyślnie słucha tylko na tym komputerze; `--web-bind 0.0.0.0` udostępnia go w sieci (bez hasła).
Ustawienia: `~/.config/wled_clocks.json` albo plik wskazany w `WLED_CONFIG`.

## Home Assistant OS

To repozytorium jest repozytorium dodatków HA (`repository.yaml`, add-on w `wled_clocks/`).

**Z GitHuba:** wypchnij repo, potem w HA: Ustawienia → Dodatki → Sklep z dodatkami → ⋮ → Repozytoria → dodaj URL.

**Bez GitHuba:** skopiuj katalog `wled_clocks/` do udziału `addons` w HA (dodatek Samba albo Terminal & SSH),
potem Sklep z dodatkami → ⋮ → Sprawdź aktualizacje → sekcja „Local add-ons”.

Dalej: WLED zegary → Instaluj → (opcjonalnie) `host` w zakładce Konfiguracja → Uruchom → „Pokaż w pasku bocznym”.
Szczegóły: [wled_clocks/DOCS.md](wled_clocks/DOCS.md).

## Układ

```
wled_clocks/            add-on (kontekst budowania obrazu)
  app/wled_clocks.py    efekty, Engine, Tui, serwer WWW
  app/web/              strona panelu (HTML/CSS/JS, bez zewnętrznych bibliotek)
  config.yaml build.yaml Dockerfile run.sh
tests/                  python3 -m unittest discover tests
scripts/run_local.sh
```
