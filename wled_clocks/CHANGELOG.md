# Zmiany

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
