# WLED zegary

103 zegary i efekty dla panelu WLED 120x12, wysyłanych protokołem DDP. Po starcie add-onu w pasku bocznym
Home Assistant pojawia się **WLED zegary**: podgląd panelu na żywo, lista efektów z wyszukiwarką, cykl, pauza
i wszystkie ustawienia znane z TUI.

## Przygotowanie WLED

Config → Sync Interfaces → zaznacz **Receive UDP realtime** (DDP, port 4048).

## Opcje

| opcja  | znaczenie |
|--------|-----------|
| `host` | IP panelu WLED. Puste = host ustawiony w panelu WWW (zapamiętywany). Wpisany tutaj wygrywa przy każdym starcie. |
| `lat`, `lon` | Położenie do pogody i słońca. Puste = położenie domu z ustawień Home Assistant. |
| `msg_tunnel` | Serwer tunelu bore dla efektu „napisz” (domyślnie `bore.pub`). Pusty = bez tunelu, patrz niżej. |
| `msg_public`, `msg_proxy` | Tylko bez tunelu – patrz „Wiadomości od widzów”. |

Pozostałe ustawienia (jasność, fps, cykl, szerokość 60/120, zasilacz, ludzik…) zmienia się w panelu;
zapisują się w `/data/wled_clocks.json` i przetrwają restart oraz aktualizację.

## Wiadomości od widzów (efekt „napisz”)

Na callu kamerka pokazuje panel z zachętą po angielsku, np.
`write something on this panel: $ echo hi > /dev/tcp/bore.pub/41234  or  $ curl -d hi bore.pub:41234  or open in a browser: bore.pub:41234`.
Kto to wyśle (albo otworzy adres w przeglądarce i wpisze tekst w formularz), zobaczy swoją wiadomość na panelu –
po kolei, jedna po drugiej.

1. W panelu: **Otwórz skrzynkę**, potem **Pokaż „napisz” na panelu**. Jeśli kamerka odwraca obraz, włącz ⇋ Odbicie.
2. Po kilku sekundach na panelu pojawia się adres. Nic nie trzeba ustawiać: dodatek sam zestawia tunel na publiczny
   serwer **bore.pub** (domena stała, port losowy) – działa za NAT-em, bez własnej domeny i przekierowań w routerze.

Zabezpieczenia:

- Tunel istnieje **tylko, gdy skrzynka jest otwarta**; zamyka się sama po wybranym czasie (domyślnie 2 h).
  Przy każdym otwarciu jest **nowy losowy port** – znają go tylko ci, którzy widzą panel.
- Serwer wiadomości słucha tylko lokalnie (dla tunelu) i umie wyłącznie przyjąć tekst: nie zmieni efektu ani ustawień,
  nie widzi panelu WWW.
- Do 80 znaków, bez emoji i znaków sterujących; binarne śmieci (np. skanery portów) są odrzucane bez odpowiedzi.
- Przez tunel nie widać adresów nadawców, więc limit jest wspólny: najwyżej 12 wiadomości na minutę, w kolejce
  najwyżej 20; blokowanie nadawcy (⛔) jest niedostępne.
- Filtr wulgaryzmów i linków (prosty – łatwo go obejść), dlatego domyślnie **akceptacja ręczna**: każda wiadomość
  czeka w panelu na ✓.
- Dziennik dodatku zapisuje każdą wiadomość.

bore.pub to darmowy serwer bez gwarancji – gdy nie działa, dodatek co chwilę próbuje ponownie (błąd widać w panelu).
Inny serwer bore: opcja `msg_tunnel`.

**Bez tunelu** (zaawansowane): wyczyść `msg_tunnel`, w zakładce Sieć wpisz port dla 8098 i załatw adres publiczny
(przekierowanie portu, własny tunel). Wtedy w adresie jest losowy kod (`adres:8098/k7q2`), działają limity na nadawcę
i blokowanie, a `msg_public` to adres pokazywany na panelu. `msg_proxy: true` tylko za tunelem/proxy, które podaje
adres nadawcy w nagłówku (Cloudflare) – inaczej limity da się obejść.

## Wyłączenie wysyłania na panel

Przycisk **● Wysyłanie** w panelu (albo klawisz `s`) wstrzymuje wysyłanie klatek DDP – po chwili WLED wraca do
własnego efektu. Stan jest zapamiętywany, więc wyłączone wysyłanie zostaje wyłączone także po restarcie dodatku.
Całkiem wyłączyć można też przez zatrzymanie dodatku.

## Efekty wbudowane w WLED

Pod efektami skryptu lista pokazuje też efekty wbudowane w WLED (2D = dla matrycy, ♪ = reaguje na dźwięk, potrzebny
mikrofon w WLED). Po wybraniu skrypt przestaje wysyłać obraz, a efekt rysuje sam WLED – podglądu w panelu wtedy nie
ma. Jasność i limit prądu takich efektów ustawia WLED. Wybranie efektu skryptu wraca do strumienia.

## Skróty klawiszowe w panelu

← → poprzedni/następny, spacja pauza, `c` cykl, `s` wysyłanie, `m` odbicie, `l` losowa kolejność,
`[` `]` czas w cyklu, `<` `>` przyspieszenie czasu, `r` prawdziwa godzina, `/` szukaj.

## Uwagi

- Nie uruchamiaj jednocześnie skryptu na komputerze z tym samym hostem – panel dostanie dwa strumienie naraz.
- Na słabym komputerze (np. Dell Wyse) część efektów liczy się wolniej: patrz „render ms” na dole panelu.
  Jeśli fps spada, zmniejsz fps w ustawieniach.
- Podgląd nie działa? Otwórz panel z dopiskiem `?poll` w adresie (odpytywanie zamiast strumienia SSE).
