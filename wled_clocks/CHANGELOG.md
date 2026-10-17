# Zmiany

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
