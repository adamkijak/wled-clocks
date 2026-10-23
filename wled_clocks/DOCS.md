# WLED zegary

143 zegary i efekty dla panelu WLED 120x12, wysyłanych protokołem DDP. Po starcie add-onu w pasku bocznym
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

Na callu kamerka pokazuje panel z samym adresem skrzynki, np. `bore.pub:41234`. Wysłać można np.
`curl -d hi bore.pub:41234`, `echo hi > /dev/tcp/bore.pub/41234` albo otworzyć adres w przeglądarce i wpisać tekst
w formularz. Nadawca zobaczy swoją wiadomość na panelu –
po kolei, jedna po drugiej.

1. W panelu wybierz efekt **napisz** – skrzynka jest w jego „Ustawieniach efektu” – i kliknij **Otwórz skrzynkę**.
   Jeśli kamerka odwraca obraz, włącz ⇋ Odbicie. Czekające wiadomości widać też na liście efektów (✉ przy „napisz”).
2. Po kilku sekundach na panelu pojawia się adres. Nic nie trzeba ustawiać: dodatek sam zestawia tunel na publiczny
   serwer **bore.pub** (domena stała, port losowy) – działa za NAT-em, bez własnej domeny i przekierowań w routerze.

Zabezpieczenia:

- Tunel istnieje **tylko, gdy skrzynka jest otwarta**; zamyka się sama po czasie wpisanym w „otwarta przez”
  (domyślnie 2 h, od 0,25 do 24 h; zmiana przy otwartej skrzynce liczy się od chwili otwarcia).
  Przy każdym otwarciu jest **nowy losowy port** – znają go tylko ci, którzy widzą panel.
- Serwer wiadomości słucha tylko lokalnie (dla tunelu) i umie wyłącznie przyjąć tekst: nie zmieni efektu ani ustawień,
  nie widzi panelu WWW.
- Do 80 znaków, bez emoji i znaków sterujących; binarne śmieci (np. skanery portów) są odrzucane bez odpowiedzi.
- Przez tunel nie widać adresów nadawców, więc limit jest wspólny: najwyżej 12 wiadomości na minutę, w kolejce
  najwyżej 20; blokowanie nadawcy (⛔) jest niedostępne.
- Filtry (w ustawieniach skrzynki, każdy do wyłączenia – wszystkie wyłączone = bez cenzury): słowa z listy
  (wbudowane wulgaryzmy PL i EN; listę można dowolnie zmienić – rdzenie słów, „kurw” łapie każdą odmianę, także
  „k.u.r.w.a” i „k0rw@”), linki i powtórki tej samej wiadomości. Filtr jest prosty – łatwo go obejść, dlatego
  domyślnie **akceptacja ręczna**: każda wiadomość czeka w panelu na ✓.
- Zachęta: własny tekst (np. „Napisz coś na panel!”) pokazywany na panelu na zmianę z adresem, co ustawioną liczbę
  sekund.
- Zabawa dla widzów (każdy dodatek do wyłączenia w ustawieniach skrzynki; widzowie mają instrukcję i przyciski
  na stronie, na której piszą):
  - **ankieta** – pytanie i 2–4 odpowiedzi w panelu; widzowie wysyłają literę (A, B…) albo treść odpowiedzi,
    na panelu na zmianę pytanie, słupki z wynikami, adres i – jeśli zaznaczone „zachęta także w czasie
    ankiety” – zachęta; głosy liczą się od razu, bez akceptacji (znany nadawca ma jeden głos – drugi go zmienia);
  - **reakcje** – `<3` serca, `!brawo`, `!konfetti`, `!fajerwerki` (też `!bravo`, `!confetti`, `!fireworks`):
    animacja na wierzchu panelu, bez akceptacji;
  - **kolor** – `[czerwony] tekst` (zielony, niebieski, żółty, pomarańczowy, różowy, fioletowy, błękitny, złoty,
    tęcza; po angielsku też) i **emotki** `:) :( :D ;) :P :O <3` jako obrazki – w zwykłych wiadomościach, które
    dalej przechodzą przez filtry i akceptację.
  - Głosy i reakcje mają lżejszy limit: z jednego adresu co 2 s, przez tunel wszyscy razem 60 na minutę.
- Dziennik dodatku zapisuje każdą wiadomość.
- Przy wiadomości widać IP nadawcy i przybliżone miejsce (ipwho.is, dostaje tylko adres IP) – o ile IP jest znane:
  za tunelem bore nie jest, przy własnym porcie (i `--msg-proxy` za Cloudflare) tak.

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

## Włącznik WLED (przycisk, aplikacja, Home Assistant)

Wyłączony WLED zostaje wyłączony: skrypt co sekundę sprawdza jego stan i, gdy jest wyłączony, nie wysyła ani
jednej klatki (każda klatka DDP sama zapala wyłączony WLED). Po wyłączeniu od razu kończy tryb realtime, więc panel
gaśnie bez czekania. Na pasku widać wtedy **⏻ WLED wyłączony**. Po włączeniu skrypt sam wraca do wysyłania.
Ten napis na pasku to też przycisk (albo klawisz `w`): włącza i wyłącza WLED tak jak przycisk w WLED.
Zmiana jasności czy efektu WLED w panelu też go nie zapala – zadziała po włączeniu.

## Kolory: podgląd = panel

Diody WS2812 mają inne barwy niż monitor: czerwony jest głębszy, a zielony daje mniejszą część jasności, więc kolor
„czerwony z odrobiną zielonego” na panelu wygląda czerwono, a na ekranie pomarańczowo. Podgląd przelicza to według
typowych diod WS2812.

1. Włącz efekt **kolory** (ostatni na liście) i porównaj panel z podglądem.
2. Jeśli się różnią, przesuwaj w jego ustawieniach „diody: zielony” (pomarańczowy i żółty na panelu czerwieńsze niż
   w podglądzie → w lewo) i „diody: niebieski” (biel na panelu bardziej niebieska → w prawo).
3. Chcesz, żeby na panelu pomarańczowy był pomarańczowy, a biel neutralna? Włącz **popraw kolory** w ustawieniach
   wspólnych – skrypt przeliczy kolory pod diody (podgląd pokazuje wtedy też wynik poprawki).

Przy małej jasności WLED panel ma mało poziomów na kanał, więc odcienie są przybliżone. Skrypt liczy dokładnie tak,
jak WLED 16 przyciemnia kolory, więc odcień nie zmienia się przy zmianie jasności, a podgląd to pokazuje.

## Kategorie

Lista efektów jest podzielona na zwijane kategorie (zegary, pogoda, gry…); kliknięcie nagłówka zwija i rozwija,
przeglądarka to pamięta. Na początku rozwinięte jest tylko „Na start”; kategoria z efektem na panelu rozwija się sama,
a wyszukiwarka przeszukuje wszystkie.

## Efekty wbudowane w WLED

Pod efektami skryptu lista pokazuje też efekty wbudowane w WLED, w trzech kategoriach:
♪ = reaguje na dźwięk (potrzebny mikrofon w WLED), 2D = dla matrycy i 1D. Po wybraniu skrypt przestaje wysyłać obraz, a efekt rysuje sam WLED – podglądu w panelu wtedy nie
ma. Jasność i limit prądu takich efektów ustawia WLED. Wybranie efektu skryptu wraca do strumienia.

Ustawienia efektu WLED (szybkość, intensywność, własne suwaki, opcje, paleta, kolory) są w „Ustawienia efektu” –
tylko te, których dany efekt używa, z nazwami z WLED. Każdy efekt pamięta swoje ustawienia.

## Skróty klawiszowe w panelu

← → poprzedni/następny, spacja pauza, `c` cykl, `s` wysyłanie, `w` włącznik WLED, `m` odbicie, `l` losowa kolejność,
`[` `]` czas w cyklu, `<` `>` przyspieszenie czasu, `r` prawdziwa godzina, `/` szukaj.

## Uwagi

- Nie uruchamiaj jednocześnie skryptu na komputerze z tym samym hostem – panel dostanie dwa strumienie naraz.
- Na słabym komputerze (np. Dell Wyse) część efektów liczy się wolniej: patrz „render ms” na dole panelu.
  Jeśli fps spada, zmniejsz fps w ustawieniach.
- Podgląd nie działa? Otwórz panel z dopiskiem `?poll` w adresie (odpytywanie zamiast strumienia SSE).
