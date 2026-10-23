# Zmiany

## 1.29.2

- Rysunek: nowe piksele pojawiają się od razu w swoim kolorze, bez białego błysku.
- Panel WWW: „Skrzynka na wiadomości od widzów” to teraz **Strona dla widzów** – wspólna dla napisz, daily
  i rysunku: adres z przyciskami „Kopiuj” i nowym „↗ Otwórz” (strona widzów w nowej karcie), Otwórz dla widzów /
  Zamknij, „Otwarcie i adres na panelu” (czas otwarcia; przy daily i rysunku – adres po ciszy). Wiadomości,
  kolejka, zachęta, ankieta, akceptacja z filtrami i dodatki widać tylko przy „napisz” (przy daily i rysunku nic
  nie dawały). Akceptacja przeniesiona do „Akceptacja i filtry”.

## 1.29.1

- Rysunek: pusty panel pokazuje sam adres strony (np. bore.pub:41234), bez „Rysujcie razem!” i przykładu;
  przy zamkniętej skrzynce – szare „inbox closed” jak w „napisz”.
- Rysunek: po ciszy („adres po ciszy”, domyślnie 10 s) adres świeci, aż ktoś zacznie rysować (wcześniej 5 s).
- Strona widzów: siatka bez kresek między pikselami, a punkt pod palcem/myszą liczony z położenia na siatce –
  przeciąganie rysuje ciągłą linię bez dziur.

## 1.29.0

- Strona widzów „Draw on the panel”: siatka na całą szerokość okna (bez przewijania w bok), paleta i siatka
  na samej górze, pole tekstowe nie przejmuje fokusu (na telefonie nie wyskakuje klawiatura).
- Daily i rysunek: adres skrzynki (np. bore.pub:41234) pokazuje się dopiero po chwili, w której nikt nic nie
  przysłał (domyślnie 10 s, ustawienie „adres po ciszy” w skrzynce; 0 = nigdy) – na 5 s, z kopertą i tą samą czcionką co w „napisz” (rysunek miał dotąd mały adres w rogu co 45 s,
  daily – co 34 s niezależnie od ruchu).

## 1.28.0

- Lista efektów w panelu WWW nie rozwija się już po najechaniu myszą – każdy efekt ma stały, jednolinijkowy opis.
- Opisy wszystkich efektów skrócone do jednego krótkiego zdania.
- Koniec z suwakami (niewygodne na telefonie): ustawienia skryptu wybiera się z list rozwijanych, a liczbowe
  ustawienia efektów WLED (szybkość, intensywność…) wpisuje się w pole liczbowe 0–255.

## 1.27.0

- Daily: przełącznik „pokazuj, kto mówi” – wyłączony daje zwykłą listę do odhaczania (bez złotego mówcy,
  przycisku „Następna osoba”, `teraz mar` i samego `x`).
- Strona dla widzów pokazuje tylko to, co ma efekt, który jest teraz na panelu: przy daily – osoby z przyciskami,
  przy rysunku – siatkę, poza nimi – pole na wiadomość, ankietę, reakcje i instrukcję.
- Rysunek: malowanie z przytrzymanym przyciskiem myszy (albo palcem) jest płynne – kratki pomiędzy ruchami
  dociągnięte linią, piksele wysyłane paczkami (u widzów i w panelu WWW). Bez skryptu siatka działa jak dotąd.
- Strona dla widzów odświeża się sama: co sekundę sprawdza stan – na rysunku dociąga to, co malują inni, a gdy
  na panelu zmieni się efekt albo lista daily / ankieta, przeładowuje się (o ile nikt nie pisze w polu).

## 1.26.0

- Ludzik: nowe pojazdy – żółta **koparka** na gąsienicach (ramię z łyżką, przesuwające się gąsienice, dym z rury,
  6 px/s) i czerwony **samolot** (kręcące się śmigło, lekko faluje w locie, za ogonem rwąca się smuga, 30 px/s).
  Oba można wyłączyć i ustawić im długość jak innym zajęciom.
- Ludzik: auto, karetka i radiowóz nie mają już żółtego paska „świateł” przed maską – zostaje sam reflektor.

## 1.25.1

- Panel WWW: ustawienia skrzynki uporządkowane – na wierzchu stan, adres, otwórz/zamknij i wiadomości czekające
  na akceptację; reszta w zwijanych grupach z podsumowaniem w nagłówku (Ankieta – „trwa – głosów: 12”, Zachęta,
  Dla widzów, Filtry, Otwarcie i akceptacja, Kolejka i pokazane). Przeglądarka pamięta, które są rozwinięte.
- Daily: edycja listy osób i opcje schowane pod „Edytuj listę osób” / „Opcje i polecenia z calla” (pusta lista
  otwiera się sama).

## 1.25.0

2 nowe efekty w „Na start” (razem 145), sterowane z panelu WWW i z calla przez skrzynkę „napisz”:

- **daily** – lista osób (do 16, skróty 2–3 litery) w dwóch rzędach: kto już mówił – przekreślony na zielono,
  kto mówi – złoty ze strzałką. W panelu WWW: lista do wpisania, ✓ / ↺ / ▶ przy każdej osobie, „Następna osoba”,
  „Od nowa”. Z calla: `x mar`, `-x mar`, `teraz mar`, samo `x`; widzowie mają przyciski na swojej stronie.
- **rysunek** – wspólny rysunek piksel po pikselu: widzowie klikają siatkę 120 × 12 na swojej stronie (paleta,
  gumka, siatka pokazuje to, co już jest na panelu) albo wysyłają `45 3 czerwony` / `45-60 3 niebieski`; w panelu
  WWW malowanie myszą i „Wyczyść”. Nowy piksel błyska; rysunek zostaje po restarcie.
- Skrzynka „napisz” widoczna też w ustawieniach tych dwóch efektów.

## 1.24.2

- Panel WWW: ustawienia wspólne (jasność, płynność, szerokość, kolory diod…) schowane pod rozwijanym nagłówkiem
  „⚙ Ustawienia wspólne” – zwinięte, dopóki ich nie rozwiniesz; przeglądarka pamięta, czy są otwarte.

## 1.24.1

- Napisz: zachęta także w czasie ankiety – przełącznik w sekcji „Ankieta” (domyślnie włączony); na panelu po
  kolei pytanie, wyniki, adres i zachęta.
- Napisz: bez „ludzika na zawołanie” – „ludzik taniec” jest teraz zwykłą wiadomością.

## 1.24.0

Efekt „napisz” – zabawa dla ludzi na callu (każdy dodatek do wyłączenia):

- **Ankieta**: pytanie i 2–4 odpowiedzi w ustawieniach skrzynki; widzowie wysyłają literę albo treść odpowiedzi
  (albo klikają na swojej stronie), panel pokazuje na zmianę pytanie, słupki z wynikami (błysk przy nowym głosie)
  i adres; w panelu WWW wyniki na żywo, zakończ / wznów / wyzeruj.
- **Reakcje**: `<3` serca, `!brawo` (napis BRAWO! i konfetti), `!konfetti`, `!fajerwerki` – animacje na
  wierzchu panelu, bez akceptacji.
- **Ludzik na zawołanie**: `ludzik taniec`, `ludzik gitara`, `guy fire`… – panel na chwilę pokazuje ludzika przy
  tym zajęciu.
- **Kolory** `[czerwony] tekst` (też tęcza) i **emotki** `:) :( :D ;) :P :O <3` jako obrazki w wiadomościach.
- Strona do pisania: instrukcja, przyciski reakcji i głosowania; w panelu WWW ściąga z poleceniami.

## 1.23.0

- Lista efektów: rozwinięcie albo zwinięcie kategorii nie przewija już listy – kliknięty nagłówek zostaje w tym
  samym miejscu i z fokusem; inne odświeżenia listy (np. nowa wiadomość) też nie ruszają przewinięcia. Do
  zaznaczonego efektu lista przewija się tylko, gdy na panelu zmieni się efekt.
- Skrzynka „napisz” – filtry widoczne i do ustawienia: słowa z listy (lista do edycji, „Domyślna lista” wraca do
  wbudowanej), linki, powtórki; wszystkie wyłączone = bez cenzury. Widać też stałe limity (długość, tempo).
- Skrzynka „napisz” – zachęta: własny tekst na panelu na zmianę z adresem, co ustawioną liczbę sekund
  (domyślnie „Napisz coś na panel!” co 30 s; 0 = nigdy).

## 1.22.2

- Ludzik: kombajn zostawia po sobie bele słomy – co kawałek bela wypada z tyłu na ziemię i leży do końca
  przejazdu, potem bele powoli gasną.

## 1.22.1

- Ludzik: nowa postać „chłopak zielony” – ta sama sylwetka co chłopak, w zielonej bluzie i ciemnozielonych
  spodenkach.
- Chłopak: czapka bez dziury – daszek z tyłu kończy się równo z czubkiem czapki.

## 1.22.0

- Ludzik: 3 postacie o innej sylwetce (nie tylko kolorach) – we wszystkich pozach, pojazdach i zajęciach:
  - **dziewczyna**: bez kasku, długie włosy do ramion, małe usta, spódniczka i gołe nogi;
  - **brzuchacz**: łysy z siwymi bokami, wąs, szerszy brzuch;
  - **chłopak**: czapka z daszkiem do przodu, uśmiech, krótkie spodenki.

## 1.21.0

- Ludzik: nowe przejazdy – karetka (biała, czerwony pas i krzyż, niebieskie koguty) i radiowóz (granatowo-biały,
  belka świateł niebiesko-czerwona); światła migają na zmianę z poświatą, reflektory i spaliny jak w aucie.
- Ludzik: 3 nowe postacie – policjant, lekarz i superbohater (razem 8).
- Oczy (kot, bajka): zamknięte oko rysuje kreskę powieki – wcześniej przy mrugnięciu znikało całe, a podgląd na
  liście bywał czarny.

## 1.20.0

- Ludzik: zajęcia nie urywają się nagle.
  - Jazda rowerem, autem, traktorem i kombajnem dzieje się poza kadrem na początku i na końcu: ludzik schodzi za
    krawędź po swojej stronie, pojazd wjeżdża z drugiej strony, przejeżdża cały panel (kilka razy) i znika za tą
    samą krawędzią, a ludzik wraca piechotą – pojazd nie pojawia się ani nie znika na środku panelu.
  - Rzeczy po zajęciach: nuty z gitary dolatują, ostatnie podbicie wybija piłkę górą poza kadr, piłeczki
    z żonglowania wypadają z rąk i toczą się na boki, tarcza chowa się w podłogę, zamek z piasku i zaścielone
    łóżko powoli gasną.
- Panel WWW: stan ludzika (teraz / następne / godzinę) na samej górze ustawień efektu.

## 1.19.3

- Ludzik: nowa gitara – pudło z otworem, gryf ukośnie w górę z główką, ręka uderza w struny; nuty lecą falując
  kilkanaście pikseli przed niego (zajęcie wybiera miejsce, gdzie mają wolną drogę).
- Pojazdy jeżdżą równo: prędkość dociągnięta do kroku animacji (1 px co klatkę albo co 2, 3, 4 klatki – zawsze
  tyle samo), więc wolny ruch nie szarpie.

## 1.19.2

- Ludzik: pojazdy jeżdżą mniej więcej o połowę wolniej – rower 14 px/s, auto 22, traktor 8, kombajn 6; wóz
  strażacki dłużej dojeżdża i spokojniej odjeżdża.

## 1.19.1

- Zegar: dzień tygodnia i data w stylu wybranej czcionki – przy cienkiej, wąskiej i LCD cienkie litery (1 px),
  przy 7-segmentowej i LCD data cyframi jak z wyświetlacza, przy grubej pogrubiona data.

## 1.19.0

- Zegar: ustawienie „kolor zegara” – dowolny kolor z próbnika w panelu WWW (od razu na panelu) zamiast barwy z listy
  albo „pory dnia”; wybór barwy z listy wraca do niej.
- Zegar: ustawienie „czcionka” – klasyczna, kwadratowa, gruba, cienka, wąska, 7-segmentowa i LCD.
- Zegar: nazwa dnia tygodnia zawsze cała (koniec z „PON”) – gdy się nie mieści, pisana węższymi literami; na
  panelu 60 kolumn dzień i data w dwóch wierszach.

## 1.18.0

- Ludzik – nowe zajęcia:
  - **balon**: goni pomarańczowy balonik, który ucieka mu sprzed nosa; podskakuje, w końcu go łapie… i balon pęka;
  - **pożar**: zapala się śmietnik, ludzik ucieka i wraca wozem strażackim na sygnale jako strażak, gasi pożar
    z węża, macha, odjeżdża za zegar (zabiera spalony śmietnik) i wraca piechotą;
  - **zwierzak**: przychodzi kot albo pies, ludzik kuca i go głaszcze (serduszka), a zwierzak potem ucieka;
  - **traktor** (z przyczepą siana i przyczepą dyń, dymi z rury) i **kombajn** (kręci nagarniaczem, sypie
    sieczką) – zielone, jeżdżą jak rower i auto.

## 1.17.0

- Ludzik: zamiast kawy (z daleka wyglądała jak papieros) gra na gitarze (nuty ulatują w górę), podbija piłkę
  (co trzecie podbicie wysoko) i buduje w piaskownicy zamek z piasku, który rośnie aż do chorągiewki.
- Ludzik śpi w łóżku: na poduszce, pod kołdrą, która unosi się przy oddechu.

## 1.16.0

31 nowych efektów bez zegara (razem 143):

- **Postacie i zwierzęta**: kotek (goni kropkę lasera, myje się, śpi), pies (aportuje piłkę, kopie dołek),
  platformowka (bieg z przeskakiwaniem rur, dziur i grzybów, monety z bloków), ptaki (klucze o zachodzie słońca),
  nietoperze (na tle księżyca), zolw (żółw morski w promieniach światła), slimak (z błyszczącym śladem).
- **Światło**: polarna (kurtyny zorzy z promieniami), tesla (lampy plazmowe, „dotyk”), szyld (neony z migotaniem),
  witraz (słońce za witrażem), basen (kaustyki na dnie), iskry (szlifierka), swieca (świece na przeciągu),
  lampa (lampy lava).
- **Fizyka**: wahadla (fala wahadeł zgrywająca się co minutę), newton (kołyski Newtona), kostki (domino
  z cofaniem), kulodrom (tor kulkowy z windą), pileczki (zderzenia i odbicia), slinky (sprężynka po schodach).
- **Sceny**: okno (nocą z okna pociągu, paralaksa), szyba (deszcz na szybie i światła miasta), latarnia (snop
  światła nad morzem), wulkan (erupcje); w kosmosie: start (start rakiety z bliska), saturn (przelot obok planety).
- **Impreza**: disco (kula lustrzana i reflektory), vumetr (wskaźniki wychyłowe i słupki LED), sylwester
  (odliczanie i fajerwerki; 31 grudnia o 23:59 odlicza naprawdę do północy), bsod (żart: ładowanie, niebieski
  ekran, aktualizacja).

## 1.15.0

- Nowa kategoria „Oczy” – 8 efektów bez zegara: kot (pionowa źrenica, kocie przymykanie), czlowiek (białka,
  tęczówki, powieki, brwi), bajka (kreskówkowe miny: radość, serduszka, zdziwienie, oczko), sowa (obraca głowę),
  robot (świecące oczy z minami), sauron (ogniste oko), hal (HAL 9000), mrok (pary oczu w ciemności).
- Ustawienie „kolor oczu” wspólne dla wszystkich oczu: w panelu WWW dowolny kolor z próbnika (widać od razu na
  panelu) albo „naturalny”; w TUI gotowe kolory.

## 1.14.0

- Ludzik: w ustawieniach efektu pole stanu – co robi teraz i co zrobi następnie (z częstością, długością i za ile
  sekund), jak przestawi najbliższą godzinę. Następne zajęcie losuje się z góry, więc zapowiedź zawsze się sprawdza;
  gdy tu się nie mieści, ludzik idzie tam, gdzie się zmieści.

## 1.13.0

- Skrzynka „napisz” w panelu WWW: adres stoi osobno, z przyciskiem 📋 Kopiuj, i da się go zaznaczyć (wcześniej tekst
  odświeżał się co chwilę i kasował zaznaczenie).
- Przy każdej wiadomości jest adres IP nadawcy i skąd jest (miasto, region, kraj – z ipwho.is, wysyłany jest tylko
  adres IP). Za tunelem bore adresu nadawcy nie widać – wtedy „IP ukryty”.

## 1.12.0

- Ludzik: nowe ustawienie „ludzik strona” – dowolnie (jak dotąd), prawa albo lewa. Przy wybranej stronie spaceruje
  i robi swoje zajęcia głównie po niej, najchętniej blisko krawędzi panelu. Na drugą stronę przechodzi tylko na chwilę.
- Efekt „napisz” pokazuje na panelu sam adres skrzynki (domena:port, np. `bore.pub:41234`), bez zachęty i komend.

## 1.11.0

- Lista efektów w panelu WWW ma przy każdym efekcie podgląd (jak wygląda na panelu, w barwach diod). Podglądy liczą
  się na boku dopiero, gdy wiersz jest widoczny, po jednym naraz, i odświeżają się co minutę. Efekty WLED podglądu
  nie mają (rysuje je sam WLED).
- Postać ludzika wybiera się obrazkami (stoi, macha, idzie) zamiast listy.

## 1.10.0

- Ludzik przestawia godzinę na 11 sposobów (ustawienie „ludzik przestawia”: losowo albo jeden wybrany):
  przepychanie (jak dotąd), malarz (zamalowuje wałkiem, maluje świeżą farbą), zapadnia (dźwignia – stare cyfry
  zapadają się, nowe spadają z odbiciem), bazooka (wybuch, nowe wyskakują z ziemi), kopniak (stare odlatują w górę,
  nowe wtaczają się podskakując), zamiatanie (rozsypują się w piasek, nowe wyrastają), magik (znikają i pojawiają się
  w iskrach), spawacz (topi laserem, wypala nowe punkt po punkcie), lina (wciąga do góry, opuszcza nowe), holowanie
  (wywozi autem na holu, wpycha zderzakiem), obrót (korba, cyfry obracają się jak w zegarze klapkowym).
  Nowe cyfry zawsze wchodzą równo z pełną minutą.

## 1.9.0

- Ludzik: przycisk ▶ przy każdym zajęciu w „Zajęcia ludzika” (w TUI klawisz `!`) – ludzik zrobi to zaraz po
  bieżącym zajęciu, bez przerwy i losowania, nawet gdy zajęcie jest wyłączone. Drugie kliknięcie anuluje.
- Ludzik: do wyboru 5 postaci (ustawienie „ludzik postać”): robotnik, strażak, Mikołaj, robot, kosmita.
  Oczy i usta świecą – wcześniej były zgaszonymi diodami i twarz wyglądała dziurawo.

## 1.8.0

- Ludzik: długość każdego zajęcia ustawia się osobno (krótko / normalnie / długo / bardzo długo) – w panelu WWW
  lista obok częstości w „Zajęcia ludzika”, w TUI klawisze `-` `+`. Rowerem i autem zmienia się liczba okrążeń.
  Zajęcie trwa najwyżej do przestawiania cyfr (ok. 40 s na minutę). Zapisywane w konfiguracji.

## 1.7.0

- Ludzik: zajęcia trwają dużo dłużej (np. czytanie i spanie do pół minuty), strzelanie to seria (kilka strzał
  w różnych miejscach tarczy, kilka magazynków z pistoletu, kilka rakiet z bazooki – po wybuchu wyskakuje nowa
  tarcza), rower i auto robią kilka okrążeń. Długość dopasowuje się do czasu do przestawienia cyfr, więc zajęcie
  nie urywa się w połowie.

## 1.6.0

- „⏻ WLED włączony / wyłączony” na pasku to przycisk: włącza i wyłącza WLED (klawisz `w`, też w TUI). Po
  wyłączeniu z panelu skrypt od razu przestaje wysyłać, nawet zanim WLED potwierdzi zmianę.

## 1.5.1

- Karta „Efekty” jest tak wysoka jak karta ustawień obok; lista efektów wypełnia ją całą.

## 1.5.0

- Włącznik WLED jest nieprzekraczalny: gdy WLED jest wyłączony (przycisk dzwonkowy, aplikacja, HA), skrypt nie
  wysyła klatek, które go same zapalały. Stan sprawdzany co sekundę, po wyłączeniu panel gaśnie od razu, po włączeniu
  wysyłanie wraca samo. Zmiana jasności i wybór efektu WLED też go już nie zapalają.
- Lista efektów w zwijanych kategoriach (Tarcze i wyświetlacze, Inne zapisy czasu, Pogoda, Niebo i kosmos,
  Wiadomości i finanse, Sceny i przyroda, Gry, Abstrakcje i symulacje, Narzędzia; efekty WLED: ♪, 2D, 1D).
  Kolejność efektów, numery i cykl idą teraz według kategorii.
- Skrzynka na wiadomości od widzów jest w „Ustawieniach efektu” **napisz** (widać ją, gdy ten efekt jest na panelu);
  czekające wiadomości sygnalizuje ✉ przy „napisz” na liście. Czas otwarcia wpisuje się w pole „otwarta przez”
  (0,25–24 h) zamiast przełączania przyciskiem; akceptacja ręczna/automatyczna to lista rozwijana.

## 1.4.0

- Kolory na panelu nie zależą już od jasności WLED: skrypt liczy dokładnie tak, jak WLED 16 skaluje jasność
  (zaokrąglenie i „+1” tylko dla kanałów powyżej ~25% najsilniejszego), i dobiera wysyłane wartości pod to.
  Podgląd pokazuje to samo, co panel – także przy jasności 255 (wcześniej kolory wychodziły tam inaczej).
- Efekty wbudowane w WLED mają swoje ustawienia (jak w aplikacji WLED, z nazwami z WLED): suwaki szybkości,
  intensywności i własne efektu, opcje, paleta, kolory. Zapamiętywane osobno dla każdego efektu; efekt bez
  zapisanych ustawień startuje z domyślnymi wartościami WLED.

## 1.3.0

- Podgląd pokazuje kolory jak diody WS2812, nie jak monitor: mieszanki z zielonym są na diodach czerwieńsze
  (np. pomarańczowy wygląda prawie na czerwony), biel niebieskawa.
- Nowy efekt **kolory** (ostatni na liście): pasy testowe i ustawienia „diody: czerwony/zielony/niebieski” do
  dopasowania podglądu do własnego panelu.
- Przełącznik „popraw kolory” (ustawienia wspólne): skrypt przelicza kolory pod diody, żeby pomarańczowy był
  pomarańczowy, a biel neutralna. Domyślnie wyłączony.

## 1.2.0

- Ustawienia w panelu WWW: suwaki (jasność, tempo, fps, przenikanie, cykl co, temperatura) i listy rozwijane
  (barwa, zasilacz, czas, włącz/wyłącz…) zamiast strzałek ◂ ▸; w TUI strzałki zostają.
- Na liście efektów także **efekty wbudowane w WLED** (lista pobierana z panelu, z oznaczeniem 2D i ♪ = reaguje
  na dźwięk). Wybranie takiego efektu wstrzymuje wysyłanie obrazu ze skryptu i włącza efekt w WLED; ← → przechodzą
  po efektach WLED, wybór efektu skryptu wraca do strumienia. Wybrany efekt WLED zostaje po restarcie.

## 1.1.3

- Przełącznik „auto przyciemnianie” (ustawienia wspólne): wyłączony nie przyciemnia efektów ponad budżet
  zasilacza, tylko ostrzega w statystykach.
- Zegar: suwak „temperatura” (−2000…+3000 K) przesuwa barwę – przy „pora dnia” względem słońca
  (teraz liczonej jako prawdziwa temperatura barwowa: 6500 K w południe, ok. 2200 K w nocy), przy stałym
  kolorze jak balans bieli.
- Podpowiedź przy „tempo tekstu” pokazuje, jak przesuwają się napisy i transparent ludzika; gdy ruch skacze
  (przesuw rzadziej niż co klatkę), świeci na pomarańczowo i podaje najmniejsze płynne tempo.

## 1.1.2

- Ustawienia w panelu (i w TUI): u góry tylko ustawienia efektu, który jest na panelu (ludzik, zegar, cykl),
  pod nimi wspólne dla wszystkich efektów.
- Zegar: barwa do wyboru (pora dnia albo stały kolor). Zegar nie przygasza się już sam wieczorem – jasność jest
  jedna dla wszystkich efektów (ustawienie „jasność WLED”).

## 1.1.1

- Zegar: dzień tygodnia z polskimi znakami (PIĄTEK, ŚRODA).
- Zegar: godzina, sekundy, dzień i data w jednym kolorze.

## 1.1.0

- Nowy efekt **zegar** (drugi na liście): zwykła godzina z sekundami i data; kolor idzie za słońcem – w południe
  jasny biały, wieczorem ciepły żółty, w nocy przygaszony bursztyn.
- Nowy efekt **napisz** (trzeci na liście): widzowie, np. uczestnicy calla, wysyłają tekst na panel –
  `echo hi > /dev/tcp/bore.pub/PORT`, `curl -d hi bore.pub:PORT` albo formularz w przeglądarce. Tunel na bore.pub
  (za NAT-em, bez domeny) działa tylko, gdy skrzynka jest otwarta w panelu, z nowym losowym portem przy każdym
  otwarciu; limity, filtr wulgaryzmów i linków, akceptacja ręczna. Teksty dla widzów po angielsku.
  Nowa opcja `msg_tunnel` (domyślnie `bore.pub`); bez tunelu – własny port 8098 z kodem w adresie.
- Ludzik jeździ rowerem i autem: wyjeżdża za krawędź panelu i wraca z drugiej strony, za cyframi. Oba zajęcia
  można wyłączyć albo ustawić ich częstość w „ludzik zajęcia”.
- Prąd, jasność/model panelu i fps są zaraz pod podglądem, na górze strony.

## 1.0.1

- Ludzik jest pierwszy na liście efektów (i pierwszy w cyklu).
- Wyłączone wysyłanie UDP (przycisk „● Wysyłanie” albo klawisz `s` w panelu) zostaje wyłączone po restarcie
  dodatku i Home Assistant.

## 1.0.0

- Pierwsza wersja add-onu: panel WWW w pasku bocznym (Ingress) z podglądem na żywo, listą efektów i ustawieniami jak w TUI.
