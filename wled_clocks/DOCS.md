# WLED zegary

101 zegarów i efektów dla panelu WLED 120x12, wysyłanych protokołem DDP. Po starcie add-onu w pasku bocznym
Home Assistant pojawia się **WLED zegary**: podgląd panelu na żywo, lista efektów z wyszukiwarką, cykl, pauza
i wszystkie ustawienia znane z TUI.

## Przygotowanie WLED

Config → Sync Interfaces → zaznacz **Receive UDP realtime** (DDP, port 4048).

## Opcje

| opcja  | znaczenie |
|--------|-----------|
| `host` | IP panelu WLED. Puste = host ustawiony w panelu WWW (zapamiętywany). Wpisany tutaj wygrywa przy każdym starcie. |
| `lat`, `lon` | Położenie do pogody i słońca. Puste = położenie domu z ustawień Home Assistant. |

Pozostałe ustawienia (jasność, fps, cykl, szerokość 60/120, zasilacz, ludzik…) zmienia się w panelu;
zapisują się w `/data/wled_clocks.json` i przetrwają restart oraz aktualizację.

## Wyłączenie wysyłania na panel

Przycisk **● Wysyłanie** w panelu (albo klawisz `s`) wstrzymuje wysyłanie klatek DDP – po chwili WLED wraca do
własnego efektu. Stan jest zapamiętywany, więc wyłączone wysyłanie zostaje wyłączone także po restarcie dodatku.
Całkiem wyłączyć można też przez zatrzymanie dodatku.

## Skróty klawiszowe w panelu

← → poprzedni/następny, spacja pauza, `c` cykl, `s` wysyłanie, `m` odbicie, `l` losowa kolejność,
`[` `]` czas w cyklu, `<` `>` przyspieszenie czasu, `r` prawdziwa godzina, `/` szukaj.

## Uwagi

- Nie uruchamiaj jednocześnie skryptu na komputerze z tym samym hostem – panel dostanie dwa strumienie naraz.
- Na słabym komputerze (np. Dell Wyse) część efektów liczy się wolniej: patrz „render ms” na dole panelu.
  Jeśli fps spada, zmniejsz fps w ustawieniach.
- Podgląd nie działa? Otwórz panel z dopiskiem `?poll` w adresie (odpytywanie zamiast strumienia SSE).
