#!/usr/bin/env python3
"""
104 kreatywne zegary i efekty dla panelu WLED 120x12 (wysyłanie klatek protokołem DDP).
Tylko biblioteka standardowa Pythona 3.8+ – bez żadnych dodatkowych pakietów (podgląd GIF/PNG też).

  python3 wled_clocks.py --list     – pełna lista ze opisami

Kategorie (w tej kolejności lista, numery i cykl – patrz CATEGORIES):
  * Na start: ludzik, zegar (zwykła godzina i data), napisz (wiadomości od widzów, np. na callu)
  * Tarcze i wyświetlacze: analogowy, nixie, segmenty, klapki, licznik, wahadlo, klepsydra, maszyna, pismo, kreskowy,
      neon, radar, obwod, kalendarz, postep, lustro, cien
  * Inne zapisy czasu: binarny, hex, kolor, dziesietny, beaty, unix, rzymski, morse, slownie, domino, strefy, odliczanie
  * Pogoda (Open-Meteo): pogoda, prognoza, opady, wiatr, termometr, smog, slonce, uv, barometr
  * Niebo i kosmos: niebo, doba, ksiezyc, planety, iss, kosmonauci, rakieta (The Space Devs), zorza (NOAA Kp),
      gwiazdy, hiperskok
  * Wiadomości i finanse: kursy, zloto (NBP), krypto (Binance), bloki (mempool.space), hackernews,
      wiadomosci (TVN24 RSS), imieniny, zart, trzesienia (USGS)
  * Sceny i przyroda: akwarium, swietliki, snieg, burza, ocean, miasto, las, gory, pory, fajerwerki, synthwave,
      pociag, ogien, fala
  * Gry: pong, waz, arkanoid, najezdzcy, pacman, dino, flappy, wyscig, labirynt, tetris
  * Abstrakcje i symulacje: roj, matrix, skaner, tecza, glitch, zycie, mrowka, plazma, kalejdoskop, wir, dna,
      oscyloskop, equalizer, ekg, kule, kregi, piasek, lawa, dym
  * Narzędzia: kolory (test do kalibracji), cykl – wszystkie po kolei (albo losowo) z płynnym przenikaniem
  Dane z internetu – bez kluczy API, pobierane w tle tylko dla widocznego efektu.

Pogoda i słońce liczone dla Warszawy; inne miejsce: --lat 50.06 --lon 19.94

Interaktywny TUI (domyślnie, gdy uruchomione w terminalu):
  podgląd panelu na żywo, ↑↓ + Enter wybór zegara, ←→ następny/poprzedni, c cykl,
  Tab ustawienia (tempo animacji, tempo tekstu, fps, cykl…), [ ] czas w cyklu, < > przyspieszenie czasu, r prawdziwa godzina,
  spacja pauza, s wysyłanie on/off, w włącznik WLED, h zmiana IP, v podgląd on/off, m odbicie lustrzane (do kamerki), q wyjście,
  / szukaj (po nazwie i opisie), PgUp/PgDn przewijanie listy, l losowa kolejność w cyklu.
  --no-tui = stare zachowanie (tylko wysyłanie, np. w tle).

Przykłady:
  python3 wled_clocks.py --host 192.168.68.81
  python3 wled_clocks.py --host 192.168.68.81 --mode cykl --every 60
  python3 wled_clocks.py --host 192.168.68.81 --mode ogien --tempo 0.5
  python3 wled_clocks.py --preview demo.gif --mode roj --seconds 8 --start 20:59:55
  python3 wled_clocks.py --preview niebo.gif --mode niebo --speed 3600   # 1 s = 1 h

WLED: Config > Sync Interfaces > "Receive UDP realtime" włączone (DDP, port 4048).
"""
import argparse
import base64
import datetime as dtm
import math
import os
import queue
import random
import re
import secrets
import select
import shutil
import signal
import socket
import subprocess
import sys
import termios
import textwrap
import time
import tty
import hmac
import html
import ipaddress
import http.server as httpd  # „http” to w tym pliku funkcja pobierająca dane
import itertools
import json
import threading
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib

# plik ustawień; w add-onie Home Assistant WLED_CONFIG=/data/wled_clocks.json (przetrwa restart i aktualizację)
CONFIG = os.environ.get("WLED_CONFIG") or os.path.join(os.path.expanduser("~"), ".config", "wled_clocks.json")


def _start_width():
    """Szerokość panelu: zmienna WLED_W albo zapisana konfiguracja (np. 60, gdy działa połowa panelu)."""
    if os.environ.get("WLED_W"):
        return int(os.environ["WLED_W"])
    try:
        with open(CONFIG, encoding="utf-8") as fh:
            return int(json.load(fh).get("width", 120))
    except (OSError, ValueError, TypeError):
        return 120


W, H = _start_width(), 12
SERPENTINE = False  # True tylko, gdy co drugi wiersz jest odwrócony
LAT, LON = 52.23, 21.01  # Warszawa – do pozycji słońca
ANIM = {"fps": 20.0, "tempo": 0.75, "text": 2.0}
# Jasność WLED (0-255) skaluje dane DDP „po wideo”: kanał != 0 daje co najmniej 1, więc przy małej jasności
# każdy kanał ma tylko kilka poziomów, a nawet najciemniejszy kolor świeci wyraźnie.
#   bri    – jasność odczytana z WLED
#   levels – ile poziomów jasności na kanał naprawdę widać (None = tyle, ile wynika z bri); zmierzone --kalibracja
#   pe     – jak jasno wygląda poziom l z L: (l/L)**pe  (1/2.2 = teoria; mniejsze = poziomy wyglądają podobnie)
PANEL = {"bri": 255, "host": "", "levels": None, "levels_bri": None, "pe": 1 / 2.2,
         "mirror": False}  # mirror – obraz odbity w poziomie (np. gdy panel ogląda się przez kamerkę)
# Prąd: WS2812 ok. 55 mA na diodę przy pełnej bieli (ok. 18 mA na kanał) + ok. 0,6 mA spoczynkowo, nawet zgaszona.
POWER = {"psu": 2000, "ma": 55.0, "idle": 0.6, "auto": True}  # psu = budżet w mA (0 = bez limitu); auto = przyciemniaj

# ---------------------------------------------------------------- czcionki
BIG = {  # 6x10, kreska 2 px
    "0": [".####.", "##..##", "##..##", "##..##", "##..##", "##..##", "##..##", "##..##", "##..##", ".####."],
    "1": ["..##..", ".###..", "####..", "..##..", "..##..", "..##..", "..##..", "..##..", "..##..", "######"],
    "2": [".####.", "##..##", "....##", "....##", "...##.", "..##..", ".##...", "##....", "##....", "######"],
    "3": [".####.", "##..##", "....##", "....##", "..###.", "....##", "....##", "....##", "##..##", ".####."],
    "4": ["...##.", "..###.", ".####.", "##.##.", "##.##.", "######", "...##.", "...##.", "...##.", "...##."],
    "5": ["######", "##....", "##....", "#####.", "....##", "....##", "....##", "....##", "##..##", ".####."],
    "6": [".####.", "##..##", "##....", "##....", "#####.", "##..##", "##..##", "##..##", "##..##", ".####."],
    "7": ["######", "....##", "....##", "...##.", "...##.", "..##..", "..##..", ".##...", ".##...", ".##..."],
    "8": [".####.", "##..##", "##..##", "##..##", ".####.", "##..##", "##..##", "##..##", "##..##", ".####."],
    "9": [".####.", "##..##", "##..##", "##..##", "##..##", ".#####", "....##", "....##", "##..##", ".####."],
    ":": ["....", "....", ".##.", ".##.", "....", "....", ".##.", ".##.", "....", "...."],
    " ": ["....", "....", "....", "....", "....", "....", "....", "....", "....", "...."],
}
SMALL = {k: v.split("|") for k, v in {  # 5 wierszy, kreska pionowa 2 px (jak w BIG) – cyfry, litery i znaki
    "0": "#####|##.##|##.##|##.##|#####", "1": "..##.|.###.|..##.|..##.|.####", "2": "#####|...##|#####|##...|#####",
    "3": "#####|...##|.####|...##|#####", "4": "##.##|##.##|#####|...##|...##", "5": "#####|##...|#####|...##|#####",
    "6": "#####|##...|#####|##.##|#####", "7": "#####|...##|...##|...##|...##", "8": "#####|##.##|#####|##.##|#####",
    "9": "#####|##.##|#####|...##|#####", ":": "..|##|..|##|..", " ": "..|..|..|..|..",
    "A": ".###.|##.##|#####|##.##|##.##", "B": "####.|##.##|####.|##.##|####.", "C": ".####|##...|##...|##...|.####",
    "D": "####.|##.##|##.##|##.##|####.", "E": "#####|##...|####.|##...|#####", "F": "#####|##...|####.|##...|##...",
    "G": ".####|##...|##.##|##.##|.####", "H": "##.##|##.##|#####|##.##|##.##", "I": "####|.##.|.##.|.##.|####",
    "J": "...##|...##|...##|##.##|.###.", "K": "##.##|####.|###..|####.|##.##", "L": "##...|##...|##...|##...|#####",
    "M": "##...##|###.###|#######|##...##|##...##", "N": "##..##|###.##|######|##.###|##..##", "O": ".###.|##.##|##.##|##.##|.###.",
    "P": "####.|##.##|####.|##...|##...", "Q": ".###.|##.##|##.##|##.##|.####", "R": "####.|##.##|####.|##.##|##.##",
    "S": ".####|##...|.###.|...##|####.", "T": "######|..##..|..##..|..##..|..##..", "U": "##.##|##.##|##.##|##.##|.###.",
    "V": "##..##|##..##|##..##|.####.|..##..", "W": "##...##|##...##|#######|###.###|##...##",
    "X": "##..##|.####.|..##..|.####.|##..##", "Y": "##..##|##..##|.####.|..##..|..##..", "Z": "#####|...##|.###.|##...|#####",
    "Ł": "##...|##...|####.|##...|#####",
    ".": "..|..|..|..|##", ",": "...|...|...|.##|##.", "-": "....|....|####|....|....", "+": "......|..##..|######|..##..|......",
    "%": "##..##|...##.|..##..|.##...|##..##", "/": "....##|...##.|..##..|.##...|##....", "°": "##|##|..|..|..",
    "!": "##|##|##|..|##", "?": "####.|...##|..##.|.....|..##.", "=": ".....|#####|.....|#####|.....",
    "↑": "..##..|.####.|######|..##..|..##..", "↓": "..##..|..##..|######|.####.|..##..",
    "→": "..##..|...##.|######|...##.|..##..", "$": ".####|###..|.###.|..###|####.", "#": "##.##|#####|##.##|#####|##.##",
    "(": ".##|##.|##.|##.|.##", ")": "##.|.##|.##|.##|##.", "'": "##|##|..|..|..", "_": ".....|.....|.....|.....|#####",
    "@": "#####|##.##|##.##|##...|#####",
}.items()}

BIG.update({
    "-": ["....", "....", "....", "....", "####", "####", "....", "....", "....", "...."],
    ".": ["..", "..", "..", "..", "..", "..", "..", "..", "##", "##"],
    "°": [".###.", "##.##", "##.##", ".###.", ".....", ".....", ".....", ".....", ".....", "....."],
})

# 5x7 z polskimi znakami (11 wierszy: 2 na akcenty, 7 ciało, 2 pod linią) – do tekstów
_F = {
    "A": ".###.|#...#|#...#|#####|#...#|#...#|#...#", "B": "####.|#...#|#...#|####.|#...#|#...#|####.",
    "C": ".###.|#...#|#....|#....|#....|#...#|.###.", "D": "####.|#...#|#...#|#...#|#...#|#...#|####.",
    "E": "#####|#....|#....|####.|#....|#....|#####", "F": "#####|#....|#....|####.|#....|#....|#....",
    "G": ".###.|#...#|#....|#.###|#...#|#...#|.###.", "H": "#...#|#...#|#...#|#####|#...#|#...#|#...#",
    "I": "###|.#.|.#.|.#.|.#.|.#.|###", "J": "..###|...#.|...#.|...#.|...#.|#..#.|.##..",
    "K": "#...#|#..#.|#.#..|##...|#.#..|#..#.|#...#", "L": "#....|#....|#....|#....|#....|#....|#####",
    "Ł": ".#...|.#...|.#.#.|.##..|##...|.#...|.####", "M": "#...#|##.##|#.#.#|#.#.#|#...#|#...#|#...#",
    "N": "#...#|#...#|##..#|#.#.#|#..##|#...#|#...#", "O": ".###.|#...#|#...#|#...#|#...#|#...#|.###.",
    "P": "####.|#...#|#...#|####.|#....|#....|#....", "Q": ".###.|#...#|#...#|#...#|#.#.#|#..#.|.##.#",
    "R": "####.|#...#|#...#|####.|#.#..|#..#.|#...#", "S": ".####|#....|#....|.###.|....#|....#|####.",
    "T": "#####|..#..|..#..|..#..|..#..|..#..|..#..", "U": "#...#|#...#|#...#|#...#|#...#|#...#|.###.",
    "V": "#...#|#...#|#...#|#...#|#...#|.#.#.|..#..", "W": "#...#|#...#|#...#|#.#.#|#.#.#|#.#.#|.#.#.",
    "X": "#...#|#...#|.#.#.|..#..|.#.#.|#...#|#...#", "Y": "#...#|#...#|.#.#.|..#..|..#..|..#..|..#..",
    "Z": "#####|....#|...#.|..#..|.#...|#....|#####",
    "a": ".....|.....|.###.|....#|.####|#...#|.####", "b": "#....|#....|#.##.|##..#|#...#|#...#|####.",
    "c": ".....|.....|.###.|#....|#....|#...#|.###.", "d": "....#|....#|.##.#|#..##|#...#|#...#|.####",
    "e": ".....|.....|.###.|#...#|#####|#....|.###.", "f": "..##.|.#..#|.#...|###..|.#...|.#...|.#...",
    "g": ".....|.....|.####|#...#|#...#|#...#|.####|....#|.###.", "h": "#....|#....|#.##.|##..#|#...#|#...#|#...#",
    "i": ".#.|...|##.|.#.|.#.|.#.|###", "j": "...#|....|..##|...#|...#|...#|...#|#..#|.##.",
    "k": "#...|#...|#..#|#.#.|##..|#.#.|#..#", "l": "##.|.#.|.#.|.#.|.#.|.#.|###",
    "ł": ".##..|..#..|..#.#|..##.|.##..|..#..|.###.", "m": ".....|.....|##.#.|#.#.#|#.#.#|#.#.#|#.#.#",
    "n": ".....|.....|#.##.|##..#|#...#|#...#|#...#", "o": ".....|.....|.###.|#...#|#...#|#...#|.###.",
    "p": ".....|.....|####.|#...#|#...#|#...#|####.|#....|#....",
    "q": ".....|.....|.####|#...#|#...#|#...#|.####|....#|....#", "r": ".....|.....|#.##.|##..#|#....|#....|#....",
    "s": ".....|.....|.####|#....|.###.|....#|####.", "t": ".#...|.#...|####.|.#...|.#...|.#..#|..##.",
    "u": ".....|.....|#...#|#...#|#...#|#..##|.##.#", "v": ".....|.....|#...#|#...#|#...#|.#.#.|..#..",
    "w": ".....|.....|#...#|#...#|#.#.#|#.#.#|.#.#.", "x": ".....|.....|#...#|.#.#.|..#..|.#.#.|#...#",
    "y": ".....|.....|#...#|#...#|#...#|#...#|.####|....#|.###.", "z": ".....|.....|#####|...#.|..#..|.#...|#####",
    "0": ".###.|#...#|#..##|#.#.#|##..#|#...#|.###.", "1": "..#..|.##..|..#..|..#..|..#..|..#..|.###.",
    "2": ".###.|#...#|....#|...#.|..#..|.#...|#####", "3": "#####|...#.|..#..|...#.|....#|#...#|.###.",
    "4": "...#.|..##.|.#.#.|#..#.|#####|...#.|...#.", "5": "#####|#....|####.|....#|....#|#...#|.###.",
    "6": "..##.|.#...|#....|####.|#...#|#...#|.###.", "7": "#####|....#|...#.|..#..|.#...|.#...|.#...",
    "8": ".###.|#...#|#...#|.###.|#...#|#...#|.###.", "9": ".###.|#...#|#...#|.####|....#|...#.|.##..",
    "!": "#|#|#|#|#|.|#", '"': "#.#|#.#|...|...|...|...|...", "#": ".#.#.|.#.#.|#####|.#.#.|#####|.#.#.|.#.#.",
    "$": "..#..|.####|#.#..|.###.|..#.#|####.|..#..", "%": "##...|##..#|...#.|..#..|.#...|#..##|...##",
    "&": ".##..|#..#.|#.#..|.#...|#.#.#|#..#.|.##.#", "'": "#|#|.|.|.|.|.", "(": "..#|.#.|#..|#..|#..|.#.|..#",
    ")": "#..|.#.|..#|..#|..#|.#.|#..", "*": ".....|..#..|#.#.#|.###.|#.#.#|..#..|.....",
    "+": ".....|..#..|..#..|#####|..#..|..#..|.....", ",": "..|..|..|..|..|##|.#|#.|..", "-": "....|....|....|####|....|....|....",
    ".": "..|..|..|..|..|##|##", "/": "....#|...#.|...#.|..#..|.#...|.#...|#....", ":": "..|##|##|..|##|##|..",
    ";": "..|##|##|..|##|##|.#|#.|..", "<": "...#|..#.|.#..|#...|.#..|..#.|...#", "=": ".....|.....|#####|.....|#####|.....|.....",
    ">": "#...|.#..|..#.|...#|..#.|.#..|#...", "?": ".###.|#...#|....#|...#.|..#..|.....|..#..",
    "@": ".###.|#...#|#.###|#.#.#|#.###|#....|.###.", "[": "###|#..|#..|#..|#..|#..|###",
    "]": "###|..#|..#|..#|..#|..#|###", "_": ".....|.....|.....|.....|.....|.....|.....|#####|.....",
    "|": "#|#|#|#|#|#|#|#|.", "°": ".##.|#..#|.##.|....|....|....|....", "▲": ".....|..#..|.###.|#####|.....|.....|.....",
    "▼": ".....|.....|.....|#####|.###.|..#..|.....", "•": "..|..|..|##|##|..|..", "…": ".....|.....|.....|.....|.....|.....|#.#.#",
}
# znaki pogrubione ręcznie – automatyczne pogrubienie (_bold) zlałoby w nich kreski stojące 1 px od siebie
_FB = {
    "G": ".####.|##..##|##....|##.###|##..##|##..##|.####.", "Q": ".####.|##..##|##..##|##..##|##..##|##..##|.####.|....##",
    "M": "##....##|###..###|########|##.##.##|##....##|##....##|##....##",
    "W": "##....##|##....##|##....##|##.##.##|##.##.##|##.##.##|.##..##.",
    "m": "........|........|#######.|##.##.##|##.##.##|##.##.##|##.##.##",
    "w": "........|........|##....##|##....##|##.##.##|##.##.##|.##..##.",
    "k": "##....|##....|##..##|##.##.|####..|##.##.|##..##", "0": ".####.|##..##|##..##|##..##|##..##|##..##|.####.",
    '"': "##.##|##.##|.....|.....|.....|.....|.....", "#": ".##.##.|.##.##.|#######|.##.##.|#######|.##.##.|.##.##.",
    "$": "..##..|.#####|##....|.####.|....##|#####.|..##..", "*": "......|##..##|.####.|######|.####.|##..##|......",
    "&": ".####...|##..##..|.####...|.###....|##.##.##|##..###.|.####.##",
    "@": ".######.|##....##|##.#####|##.##.##|##.#####|##......|.######.",
    "…": "........|........|........|........|........|........|##.##.##",
}
_ACC = {"Ą": "A,", "Ć": "C'", "Ę": "E,", "Ń": "N'", "Ó": "O'", "Ś": "S'", "Ź": "Z'", "Ż": "Z.",
        "ą": "a,", "ć": "c'", "ę": "e,", "ń": "n'", "ó": "o'", "ś": "s'", "ź": "z'", "ż": "z."}


def _build_txt():
    font = {}
    for ch, spec in {**_F, **_FB}.items():
        rows = spec.split("|")
        rows = ["", ""] + rows + [""] * (9 - len(rows))
        w = max(len(r) for r in rows)
        font[ch] = [list(r.ljust(w, ".")) for r in rows]
    for ch, (base, acc) in _ACC.items():
        g = [row[:] for row in font[base]]
        w = len(g[0])
        top = 0 if base.isupper() else 2
        if acc == "'":
            g[top][min(w - 1, w // 2 + 1)] = "#"
            g[top + 1][w // 2] = "#"
        elif acc == ".":
            g[top][w // 2] = "#"
        else:
            g[9][w - 2] = g[10][w - 1] = "#"
        font[ch] = g
    font = {k: ["".join(r) for r in g] for k, g in font.items()}
    font[" "] = ["..."] * 11
    return font


TXT = _build_txt()


def _thin(g):
    """Czy w znaku jest kreska szeroka na 1 diodę (pojedynczy piksel w wierszu) – na panelu nieczytelna."""
    return any(re.search(r"(?<!#)#(?!#)", r) for r in g)


def _bold(g):
    """Pogrubienie: każdy piksel zapala też sąsiada z prawej (znak robi się o 1 kolumnę szerszy)."""
    return ["".join("#" if "#" in (r[i - 1:i + 1] if i else r[:1]) else "." for i in range(len(r) + 1)) for r in g]


for _font in (BIG, SMALL, TXT):  # zasada: każda kreska ma co najmniej 2 diody szerokości
    _font.update({k: _bold(g) for k, g in _font.items() if _thin(g)})
TALL = {k: [r for r in g for _ in (0, 1)] for k, g in SMALL.items()}  # 5x10: SMALL rozciągnięty w pionie


# ---------------------------------------------------------------- czcionki godziny (efekt „zegar”, ustawienie „czcionka”)
def _rows(d):
    return {k: v.split("|") for k, v in d.items()}


THIN = _rows({  # 5x10, kreska 1 px
    "0": ".###.|#...#|#...#|#...#|#...#|#...#|#...#|#...#|#...#|.###.",
    "1": "..#..|.##..|#.#..|..#..|..#..|..#..|..#..|..#..|..#..|#####",
    "2": ".###.|#...#|....#|....#|...#.|..#..|.#...|#....|#....|#####",
    "3": ".###.|#...#|....#|....#|..##.|....#|....#|....#|#...#|.###.",
    "4": "...#.|..##.|.#.#.|#..#.|#..#.|#####|...#.|...#.|...#.|...#.",
    "5": "#####|#....|#....|####.|....#|....#|....#|....#|#...#|.###.",
    "6": ".###.|#...#|#....|#....|####.|#...#|#...#|#...#|#...#|.###.",
    "7": "#####|....#|....#|...#.|...#.|..#..|..#..|.#...|.#...|.#...",
    "8": ".###.|#...#|#...#|#...#|.###.|#...#|#...#|#...#|#...#|.###.",
    "9": ".###.|#...#|#...#|#...#|#...#|.####|....#|....#|#...#|.###.",
    ":": ".|.|.|#|.|.|#|.|.|.", " ": "..|..|..|..|..|..|..|..|..|..",
})
SLIM = _rows({  # 4x10, kreska 1 px – wąska
    "0": ".##.|#..#|#..#|#..#|#..#|#..#|#..#|#..#|#..#|.##.",
    "1": "..#.|.##.|#.#.|..#.|..#.|..#.|..#.|..#.|..#.|..#.",
    "2": ".##.|#..#|...#|...#|..#.|..#.|.#..|#...|#...|####",
    "3": ".##.|#..#|...#|...#|.##.|...#|...#|...#|#..#|.##.",
    "4": "..#.|.##.|#.#.|#.#.|#.#.|####|..#.|..#.|..#.|..#.",
    "5": "####|#...|#...|###.|...#|...#|...#|...#|#..#|.##.",
    "6": ".##.|#..#|#...|#...|###.|#..#|#..#|#..#|#..#|.##.",
    "7": "####|...#|...#|..#.|..#.|..#.|.#..|.#..|.#..|.#..",
    "8": ".##.|#..#|#..#|#..#|.##.|#..#|#..#|#..#|#..#|.##.",
    "9": ".##.|#..#|#..#|#..#|#..#|.###|...#|...#|#..#|.##.",
    ":": ".|.|.|#|.|.|#|.|.|.", " ": "..|..|..|..|..|..|..|..|..|..",
})
def _thick(g):
    """Znak pogrubiony o 1 px w poziomie."""
    return ["".join("#" if "#" in (r + ".")[i:i + 1] + ("." + r)[i:i + 1] else "." for i in range(len(r) + 1)) for r in g]


BOLD = {k: _thick(g) for k, g in BIG.items() if k in "0123456789 "}  # BIG pogrubiony: kreski pionowe 3 px
BOLD[":"] = BIG[":"]
SQUARE = {k: [r.replace(".####.", "######") if i in (0, len(g) - 1) else r for i, r in enumerate(g)]
          for k, g in BIG.items() if k in "0123456789: "}  # BIG z kwadratowymi rogami


def _seg7(w, t, h=9, gaps=True):
    """Cyfry jak na wyświetlaczu 7-segmentowym: w szerokość, t grubość pionowych kresek, h wierszy; gaps – puste rogi
    (małe cyfry bez przerw, inaczej „1” rozpada się na kropki)."""
    on = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc",
          "7": "abc", "8": "abcdefg", "9": "abcdfg"}
    font, m = {}, h // 2
    for ch, segs in on.items():
        g = [["."] * w for _ in range(h)]
        for s, rows, cols in (("a", [0], range(1, w - 1)), ("g", [m], range(1, w - 1)), ("d", [h - 1], range(1, w - 1)),
                              ("f", range(1 - (not gaps), m + (not gaps)), range(t)),
                              ("b", range(1 - (not gaps), m + (not gaps)), range(w - t, w)),
                              ("e", range(m + gaps, h - gaps), range(t)), ("c", range(m + gaps, h - gaps), range(w - t, w))):
            if s in segs:
                for r in rows:
                    for c in cols:
                        g[r][c] = "#"
        font[ch] = ["".join(r) for r in g]
    dot = "#" * t
    font[":"] = [dot if r in (m // 2, h - 1 - m // 2) else "." * t for r in range(h)]
    font["."] = ["." * t] * (h - 1) + [dot]
    font[" "] = [".."] * h
    return font


CLOCK_FONTS = [("klasyczna", BIG), ("kwadratowa", SQUARE), ("gruba", BOLD), ("cienka", THIN), ("wąska", SLIM),
               ("7-segmentowa", _seg7(6, 2)), ("LCD", _seg7(5, 1))]


NARROW_TXT = _rows({  # 3x5 (M, N, W szersze) – długie nazwy dni i daty na wąskim miejscu
    "A": ".#.|#.#|###|#.#|#.#", "B": "##.|#.#|##.|#.#|##.", "C": ".##|#..|#..|#..|.##", "D": "##.|#.#|#.#|#.#|##.",
    "E": "###|#..|##.|#..|###", "F": "###|#..|##.|#..|#..", "G": ".##|#..|#.#|#.#|.##", "H": "#.#|#.#|###|#.#|#.#",
    "I": "#|#|#|#|#", "J": "..#|..#|..#|#.#|.#.", "K": "#.#|#.#|##.|#.#|#.#", "L": "#..|#..|#..|#..|###",
    "Ł": "#..|#..|##.|#..|###", "M": "#...#|##.##|#.#.#|#...#|#...#", "N": "#..#|##.#|#.##|#..#|#..#",
    "O": ".#.|#.#|#.#|#.#|.#.", "P": "##.|#.#|##.|#..|#..", "Q": ".#.|#.#|#.#|##.|.##", "R": "##.|#.#|##.|#.#|#.#",
    "S": ".##|#..|.#.|..#|##.", "T": "###|.#.|.#.|.#.|.#.", "U": "#.#|#.#|#.#|#.#|###", "V": "#.#|#.#|#.#|#.#|.#.",
    "W": "#...#|#...#|#.#.#|##.##|#...#", "X": "#.#|#.#|.#.|#.#|#.#", "Y": "#.#|#.#|.#.|.#.|.#.",
    "Z": "###|..#|.#.|#..|###",
    "0": "###|#.#|#.#|#.#|###", "1": ".#.|##.|.#.|.#.|###", "2": "##.|..#|.#.|#..|###", "3": "##.|..#|.#.|..#|##.",
    "4": "#.#|#.#|###|..#|..#", "5": "###|#..|##.|..#|##.", "6": ".##|#..|###|#.#|###", "7": "###|..#|.#.|.#.|.#.",
    "8": "###|#.#|###|#.#|###", "9": "###|#.#|###|..#|##.", ".": ".|.|.|.|#", " ": "..|..|..|..|..",
})
SMALL_BOLD = {k: _thick(g) for k, g in SMALL.items() if k in "0123456789. "}  # pogrubiona data przy „gruba”
# dzień tygodnia i data w stylu czcionki godziny: nazwa -> (czcionki dnia, czcionki daty), od najszerszej –
# bierze pierwszą, która się mieści (NARROW_TXT – cienkie litery 1 px, _seg7 – data jak na wyświetlaczu)
CLOCK_SMALL = {"gruba": ((SMALL, NARROW_TXT), (SMALL_BOLD, SMALL, NARROW_TXT)),  # pogrubione litery się zlewają
               "cienka": ((NARROW_TXT,), (NARROW_TXT,)), "wąska": ((NARROW_TXT,), (NARROW_TXT,)),
               "7-segmentowa": ((SMALL, NARROW_TXT), (_seg7(5, 2, 5, False), _seg7(4, 1, 5, False))),
               "LCD": ((NARROW_TXT,), (_seg7(4, 1, 5, False),))}


_SMALL_MARK = {"Ą": "ogonek", "Ę": "ogonek", "Ć": "kreska", "Ń": "kreska", "Ó": "kreska", "Ś": "kreska", "Ź": "kreska",
               "Ż": "kropka"}


def small_pl(s, x0, y0, sp=1, font=SMALL):
    """Punkty napisu w SMALL (albo NARROW_TXT) z polskimi znakami: SMALL ma tylko 5 wierszy, więc kreska i kropka
    idą do wiersza nad napisem, a ogonek do wiersza pod nim – napis potrzebuje wolnego wiersza nad sobą i pod sobą."""
    pts, x = [], int(x0)
    for c in s:
        g = glyph(font, c)
        w = len(g[0])
        pts += [(x + k, y0 + ry) for ry, row in enumerate(g) for k, b in enumerate(row) if b == "#"]
        mark = _SMALL_MARK.get(c.upper())
        if mark == "kreska":
            pts += [(x + w // 2, y0 - 1), (x + w // 2 + 1, y0 - 1)]
        elif mark == "kropka":
            pts += [(x + w // 2 - 1, y0 - 1), (x + w // 2, y0 - 1)]
        elif mark == "ogonek":
            pts += [(x + w - 1, y0 + 5), (x + w, y0 + 5)]
        x += w + sp
    return pts


def glyph(font, c):
    g = font.get(c)
    if g is None:
        b = unicodedata.normalize("NFD", c)[0]
        g = font.get(c.upper()) or font.get(b) or font.get(b.upper()) or font.get("?") or font[" "]
    return g


_PTS = {}


def text_rel(s, font=BIG, sp=1):
    key = (s, id(font), sp)
    r = _PTS.get(key)
    if r is None:
        pts, x = [], 0
        for c in s:
            g = glyph(font, c)
            for ry, row in enumerate(g):
                for k, b in enumerate(row):
                    if b == "#":
                        pts.append((x + k, ry))
            x += len(g[0]) + sp
        r = (pts, max(0, x - sp))
        if len(_PTS) > 1000:
            _PTS.clear()
        _PTS[key] = r
    return r


def text_w(s, font=BIG, sp=1):
    return text_rel(s, font, sp)[1]


def text_px(s, x0, y0, font=BIG, sp=1):
    x0, y0 = int(x0), int(y0)
    return [(x0 + x, y0 + y) for x, y in text_rel(s, font, sp)[0]]


def centered(s, font=BIG, y0=1):
    return text_px(s, (W - text_w(s, font)) // 2, y0, font)


# ---------------------------------------------------------------- kolory
def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def hsv(h, s, v):
    h = (h % 1.0) * 6
    i, f = int(h), h - int(h)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    r, g, b = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i % 6]
    return (r * 255, g * 255, b * 255)


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def mul(c, k):
    return (c[0] * k, c[1] * k, c[2] * k)


def lerp_n(a, b, t):
    return a + (b - a) * t


def bounce(a):
    """0..1 -> 0..1: spada i odbija się coraz niżej."""
    for edge, mid, top in ((1 / 2.75, 0, 0), (2 / 2.75, 1.5 / 2.75, 0.75), (2.5 / 2.75, 2.25 / 2.75, 0.9375)):
        if a < edge:
            return 7.5625 * (a - mid) ** 2 + top
    return 7.5625 * (a - 2.625 / 2.75) ** 2 + 0.984375


class Frame:
    def __init__(self, fill=(0, 0, 0)):
        self.px = [[fill] * W for _ in range(H)]

    def set(self, x, y, c):
        x, y = int(math.floor(x)), int(math.floor(y))
        if 0 <= x < W and 0 <= y < H:
            self.px[y][x] = c

    def add(self, x, y, c):
        x, y = int(math.floor(x)), int(math.floor(y))
        if 0 <= x < W and 0 <= y < H:
            o = self.px[y][x]
            self.px[y][x] = (o[0] + c[0], o[1] + c[1], o[2] + c[2])

    def outline(self, pts, c=(0, 0, 0)):
        for x, y in pts:
            for ox in (-1, 0, 1):
                for oy in (-1, 0, 1):
                    self.set(x + ox, y + oy, c)

    def draw(self, pts, c):
        for x, y in pts:
            self.set(x, y, c)

    def get(self, x, y):
        x, y = int(math.floor(x)), int(math.floor(y))
        return self.px[y][x] if 0 <= x < W and 0 <= y < H else (0, 0, 0)

    def fill(self, c):
        self.px = [[c] * W for _ in range(H)]

    def rect(self, x0, y0, x1, y1, c):
        for y in range(max(0, int(y0)), min(H, int(y1) + 1)):
            row = self.px[y]
            for x in range(max(0, int(x0)), min(W, int(x1) + 1)):
                row[x] = c

    def line(self, x0, y0, x1, y1, c, add=False):
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        put = self.add if add else self.set
        for i in range(n + 1):
            a = i / n
            put(x0 + (x1 - x0) * a + 0.5, y0 + (y1 - y0) * a + 0.5, c)

    def text(self, s, x, y, c, font=None, outline=None):
        pts = text_px(s, x, y, font or TXT)
        if outline is not None:
            self.outline(pts, outline)
        self.draw(pts, c)
        return pts

    def rgb_rows(self):
        c8 = lambda v: 255 if v >= 255 else 0 if v <= 0 else int(v)
        rows = [[(c8(r), c8(g), c8(b)) for r, g, b in row] for row in self.px]
        return [row[::-1] for row in rows] if PANEL["mirror"] else rows

    def to_bytes(self):
        q = panel_q() if panel_manual() else None  # ręcznie zmierzone poziomy – stary model; zwykle dokładny WLED 16
        bri = PANEL["bri"]
        fix = led_fix if COLOR["fix"] else None
        out, lut = bytearray(), {}  # lut: kolor -> 3 bajty (w klatce zwykle mało różnych kolorów)
        for y, row in enumerate(self.rgb_rows()):
            if SERPENTINE and y % 2:
                row = row[::-1]
            for c in row:
                px = lut.get(c)
                if px is None:
                    s = fix(c) if fix else c
                    px = lut[c] = bytes((q[s[0]], q[s[1]], q[s[2]]) if q else send_color(s, bri))
                out += px
            pad = PANEL.get("ddp_w", W) - W
            if pad > 0:
                out += bytes(3 * pad)
        return bytes(out)


_QCACHE = {}


def panel_manual():
    """Ręcznie zmierzone poziomy obowiązują tylko przy tej jasności WLED, przy której je zmierzono."""
    return bool(PANEL["levels"]) and PANEL.get("levels_bri") == PANEL["bri"]


def panel_levels():
    return PANEL["levels"] if panel_manual() else PANEL["bri"]


def panel_pe():
    return PANEL["pe"] if panel_manual() else 1 / 2.2


def panel_level(v, lv):
    """Poziom (0..lv), na jakim panel zapali kanał o wartości v."""
    return 0 if v == 0 or lv == 0 else min(lv, (v * lv >> 8) + 1)


def panel_model(lv=None):
    """(tablica 0..255 -> wartość do wysłania, tablica poziom -> jak jasno go widać 0..1)."""
    lv = panel_levels() if lv is None else lv
    pe = panel_pe()
    key = (lv, round(pe, 3))
    m = _QCACHE.get(key)
    if m is None:
        if lv >= 255:
            m = (list(range(256)), [(v / 255) ** (pe * 2.2) for v in range(256)])
        else:
            seen = [(l / lv) ** pe for l in range(lv + 1)]
            send = [0] + [max(1, -(-(l - 1) * 256 // lv)) for l in range(1, lv + 1)]
            q = [send[min(range(lv + 1), key=lambda l: abs(seen[l] - v / 255))] for v in range(256)]
            m = (q, seen)
        _QCACHE[key] = m
    return m


def panel_q(lv=None):
    """Tablica 0..255 -> wartość do wysłania, dopasowana do tego, co panel naprawdę potrafi.
    Wybieramy poziom najbliższy PERCEPCYJNIE zamierzonej wartości: słabe składowe koloru gasimy
    (inaczej kolory płowieją do bieli, a ciemne tła świecą), a resztę wysyłamy tak, by panel trafił
    dokładnie w wybrany poziom."""
    return panel_model(lv)[0]


# Barwy diod WS2812 to nie barwy monitora: czerwony głębszy, a zielony daje dużo mniejszą część jasności bieli niż
# na ekranie – mieszanka „czerwony + trochę zielonego” na diodach wygląda czerwono, na ekranie pomarańczowo.
LED_XY = ((0.69, 0.31), (0.17, 0.72), (0.13, 0.07))  # chromatyczność diody czerwonej, zielonej, niebieskiej (~625/520/470 nm)
LED_Y = (1.0, 2.27, 0.43)  # jasność kanałów: z karty katalogowej (1 : 1,7 : 0,47) dopasowana do bieli ok. 9000 K
COLOR = {"r": 1.0, "g": 1.0, "b": 1.0, "fix": False}  # kalibracja jasności kanałów (efekt „kolory”); fix = popraw kolory
COLOR_STEPS = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0]
_SRGB = ((3.2406, -1.5372, -0.4986), (-0.9689, 1.8758, 0.0415), (0.0557, -0.2040, 1.0570))  # XYZ -> liniowe sRGB
_LEDM, _FIX = {}, {}


def _inv3(m):
    (a, b, c), (d, e, f), (g, h, i) = m
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]


def led_matrix():
    """(m, odwrotność): m[i][j] = ile liniowej składowej i monitora daje kanał j diody; biel diod -> najjaśniejsza
    składowa 1. Przelicza się przy zmianie kalibracji."""
    key = (COLOR["r"], COLOR["g"], COLOR["b"])
    if key not in _LEDM:
        cols = []
        for (x, y), lum, k in zip(LED_XY, LED_Y, key):
            Y = lum * k
            xyz = (x / y * Y, Y, (1 - x - y) / y * Y)
            cols.append([sum(a * v for a, v in zip(row, xyz)) for row in _SRGB])
        top = max(sum(col[i] for col in cols) for i in range(3))
        m = [[cols[j][i] / top for j in range(3)] for i in range(3)]
        _LEDM.clear()
        _FIX.clear()
        _LEDM[key] = (m, _inv3(m))
    return _LEDM[key]


def led_fix(c):
    """„popraw kolory”: co wysłać, żeby dioda wyglądała jak kolor c na ekranie (pomarańczowy = pomarańczowy,
    biel neutralna zamiast niebieskawej). Kolory spoza zasięgu diod – najbliższe możliwe."""
    inv = led_matrix()[1]
    r = _FIX.get(c)
    if r is None:
        t = [(v / 255) ** 2.2 for v in c]
        d = [max(0.0, sum(a * v for a, v in zip(row, t))) for row in inv]
        top = max(d)
        d = [v / top for v in d] if top > 1 else d
        r = tuple(round(255 * v ** (1 / 2.2)) for v in d)
        if len(_FIX) > 4096:
            _FIX.clear()
        _FIX[c] = r
    return r


# ---------------------------------------------------------------- jasność WLED 16 (color_fade w trybie „video”)
# WLED skaluje każdy kanał: (v * bri + 127) >> 8, a najniższy bit ustawia (żeby kanał nie zgasł) tylko kanałom
# powyżej ok. 25% najsilniejszego kanału koloru: v > (max >> 2) + 1. Przy bri = 255 wysyła kolor bez zmian.
# Słaby kanał może więc zgasnąć, a mocniejszy dostaje +1 – stąd przy małej jasności odcień zależy od jasności.
_WF, _SEND = {}, {}


def _wled_tables(bri):
    """(bez bitu, z bitem, zakresy v dla każdego wyjścia bez bitu, zakresy z bitem) dla jasności bri."""
    t = _WF.get(bri)
    if t is None:
        a = [0] + [(v * bri + 127) >> 8 for v in range(1, 256)]
        b = [0] + [x | 1 for x in a[1:]]
        ra, rb = {}, {}
        for v in range(256):
            ra.setdefault(a[v], [v, v])[1] = v
            rb.setdefault(b[v], [v, v])[1] = v
        t = _WF[bri] = (a, b, ra, rb)
    return t


def wled_fade(c, bri):
    """Bajty, które WLED 16 naprawdę wyśle na diody, gdy dostanie kolor c przy jasności bri."""
    if bri >= 255:
        return tuple(c)
    if bri <= 0 or not any(c):
        return (0, 0, 0)
    a, b = _wled_tables(bri)[:2]
    thr = (max(c) >> 2) + 1
    return tuple(b[v] if v > thr else a[v] for v in c)


def wled_top(bri):
    """Najjaśniejsze wyjście kanału przy jasności bri (pełny kolor)."""
    return 255 if bri >= 255 else _wled_tables(max(1, bri))[1][255]


def _odd_near(x, lo, hi):
    """Nieparzyste wyjścia (z ustawionym bitem) wokół x, w zakresie lo..hi, oraz końce zakresu."""
    o = int(x) - 1 + int(x) % 2  # największe nieparzyste <= x (albo x-1)
    return {v for v in (lo, hi, o, o + 2) if lo <= v <= hi}


def _nearest(p, top, outs):
    """Wyjście z outs najbliższe PERCEPCYJNIE zamierzonej wartości p (0..1): słabe składowe gasną zamiast płowieć."""
    return min(outs, key=lambda o: (abs((o / top) ** (1 / 2.2) - p), o))


def send_color(c, bri):
    """Co wysłać (DDP), żeby panel przy jasności bri pokazał kolor jak najbliższy c: najpierw najsilniejszy kanał,
    potem pozostałe – każdy na najbliższy poziom, który WLED przy tym kolorze naprawdę da (próg 25%)."""
    if bri >= 255:  # WLED wysyła bez zmian, diody świecą liniowo – przeliczamy jak przy każdej innej jasności
        return tuple(round(255 * (v / 255) ** 2.2) for v in c)
    key = (c, bri)
    r = _SEND.get(key)
    if r is not None:
        return r
    a, b, ra, rb = _wled_tables(max(1, bri))
    top = b[255]
    m = max(c)
    if m == 0:
        return (0, 0, 0)
    # najsilniejszy kanał ma zawsze ustawiony bit (v > próg), więc jego wyjście jest nieparzyste
    od = _nearest(m / 255, top, {0} | {o for o in _odd_near((m / 255) ** 2.2 * top, b[2], top) if o in rb})
    if od == 0:
        r = (0, 0, 0)
    else:
        vd = rb[od][1]  # największe v z tym wyjściem – wyższy próg, więcej poziomów dla słabszych kanałów
        thr = (vd >> 2) + 1
        low = a[thr]  # do tego wyjścia kanały bez bitu (v <= próg), wyżej tylko z bitem (v > próg)
        hi0 = b[thr + 1] if thr + 1 <= vd else od
        out = []
        for v in c:
            if v == m:
                out.append(vd)
                continue
            x = (v / 255) ** 2.2 * top
            cands = {0, min(low, int(x)), min(low, int(x) + 1)} | {o for o in _odd_near(x, hi0, od) if o in rb}
            o = _nearest(v / 255, top, cands)
            if o <= low:
                out.append(ra[o][0])
            else:
                w = max(rb[o][0], thr + 1)
                out.append(w if w <= vd and b[w] == o else vd)
        r = tuple(out)
    if len(_SEND) > 8192:
        _SEND.clear()
    _SEND[key] = r
    return r


def panel_view(rows, lv=None):
    """Co naprawdę zobaczy oko na panelu (do podglądu): co WLED 16 wyśle na diody przy tej jasności (te same wartości
    co wysyłane DDP, z „popraw kolory”), i barwy diod WS2812 przeliczone na barwy monitora."""
    m = led_matrix()[0]
    fix = led_fix if COLOR["fix"] else None
    bri = PANEL["bri"]
    manual = panel_manual()  # ręcznie zmierzone poziomy (--kalibracja) – stary model
    if manual:
        lv = panel_levels() if lv is None else lv
        q, k = panel_model(lv)[0], panel_pe() * 2.2
        lin_m = [(panel_level(q[v], lv) / lv) ** k for v in range(256)]
    top = wled_top(bri)
    cache, out = {}, []
    for row in rows:
        o = []
        for c in row:
            p = cache.get(c)
            if p is None:
                s_ = fix(c) if fix else c
                ch = [lin_m[v] for v in s_] if manual else [x / top for x in wled_fade(send_color(s_, bri), bri)]
                d = [max(0.0, sum(a * x for a, x in zip(r_, ch))) for r_ in m]
                hi = max(d)
                d = [x / hi for x in d] if hi > 1 else d
                p = cache[c] = tuple(round(255 * x ** (1 / 2.2)) for x in d)
            o.append(p)
        out.append(o)
    return out


def visible(c, level=6):
    """Ciemny kolor, który nie znika przy małej jasności WLED: najjaśniejsza składowa dostaje co najmniej
    `level` stopni panelu (najsłabsze stopnie na diodach i w kamerce prawie nie świecą, choć podgląd je pokazuje)."""
    lv = panel_levels()
    need = 255 * (min(level, max(1, lv // 5)) / lv) ** panel_pe()  # ale nie jaśniej niż 1/5 skali
    m = max(c)
    return c if m == 0 or m >= need else mul(c, need / m)


_ILUT = {}


def frame_current(data, bri=None):
    """Szacowany prąd panelu (mA) dla wysyłanych bajtów przy jasności WLED bri."""
    bri = PANEL["bri"] if bri is None else bri
    key = (bri, POWER["ma"])
    lut = _ILUT.get(key)
    if lut is None:
        per_ch = POWER["ma"] / 3
        lut = [0.0] + [min(255, (v * bri >> 8) + 1) / 255 * per_ch for v in range(1, 256)]
        _ILUT[key] = lut
    return W * H * POWER["idle"] + sum(map(lut.__getitem__, data))


class PowerLimiter:
    """Pilnuje budżetu zasilacza: gdy klatka pobrałaby za dużo, od razu ją przyciemnia (żeby nie przeciążyć
    zasilacza), a potem bardzo powoli wraca do pełnej jasności – bez pulsowania jak w ograniczniku WLED."""

    def __init__(self):
        self.k, self.est, self.raw = 1.0, 0.0, 0.0

    @staticmethod
    def scaled(frame, k):
        if k >= 0.999:
            return frame
        f = Frame()
        f.px = [[(r * k, g * k, b * k) for r, g, b in row] for row in frame.px]
        return f

    def apply(self, frame, dt):
        """-> (klatka do wysłania i podglądu, bajty)"""
        data = frame.to_bytes()
        self.raw = frame_current(data)
        budget = POWER["psu"]
        if not budget or not POWER["auto"]:  # bez limitu albo przyciemnianie wyłączone: zawsze pełna jasność
            self.k, self.est = 1.0, self.raw
            return frame, data
        self.k = min(1.0, self.k + dt * 0.25)          # powolny powrót
        idle = W * H * POWER["idle"]
        if self.raw > budget:
            self.k = min(self.k, max(0.05, (budget - idle) / max(1.0, self.raw - idle)))
        out = self.scaled(frame, self.k)
        data = out.to_bytes()
        self.est = frame_current(data)
        while self.est > budget and self.k > 0.05:  # zaokrąglenia do poziomów panelu potrafią dołożyć prądu
            self.k *= 0.85
            out = self.scaled(frame, self.k)
            data = out.to_bytes()
            self.est = frame_current(data)
        return out, data


def blend(a, b, t):
    f = Frame()
    for y in range(H):
        ra, rb = a.px[y], b.px[y]
        f.px[y] = [lerp(ra[x], rb[x], t) for x in range(W)]
    return f


# ---------------------------------------------------------------- słońce
def sun_position(now):
    """Zwraca (wysokość słońca w stopniach, prawdziwy czas słoneczny w godzinach). Wzory NOAA."""
    u = now.astimezone(dtm.timezone.utc)
    g = 2 * math.pi / 365 * (u.timetuple().tm_yday - 1 + (u.hour - 12) / 24)
    eot = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                    - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    tst = u.hour * 60 + u.minute + u.second / 60 + eot + 4 * LON
    ha = math.radians(tst / 4 - 180)
    lat = math.radians(LAT)
    s = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(ha)
    return math.degrees(math.asin(clamp(s, -1, 1))), (tst / 60) % 24


SKY = [  # wysokość słońca -> (kolor góry nieba, kolor przy horyzoncie)
    (-18, (1, 1, 6), (2, 3, 12)),
    (-10, (3, 4, 22), (18, 10, 40)),
    (-4, (12, 16, 60), (110, 35, 55)),
    (0, (35, 50, 120), (255, 100, 25)),
    (6, (35, 95, 185), (255, 180, 110)),
    (20, (20, 85, 205), (120, 175, 240)),
    (90, (10, 75, 215), (100, 165, 240)),
]


def sky_colors(elev):
    if elev <= SKY[0][0]:
        return SKY[0][1], SKY[0][2]
    for (e0, t0, h0), (e1, t1, h1) in zip(SKY, SKY[1:]):
        if elev <= e1:
            k = (elev - e0) / (e1 - e0)
            return lerp(t0, t1, k), lerp(h0, h1, k)
    return SKY[-1][1], SKY[-1][2]


# ================================================================ ZEGARY
class Clock:
    def draw(self, f, now, t, dt):
        raise NotImplementedError


class Odometer(Clock):
    """Bębny licznika: cyfra toczy się w górę przy zmianie, cieniowanie walca daje efekt 3D."""

    def __init__(self):
        self.slots = {}

    @staticmethod
    def cyl(y):
        return 0.3 + 0.7 * math.cos((y - 5.5) / 6.8 * math.pi / 2)

    def draw(self, f, now, t, dt):
        txt = now.strftime("%H:%M:%S")
        x = (W - text_w(txt)) // 2
        for i, ch in enumerate(txt):
            gw = len(BIG[ch][0])
            cur, prev, tc = self.slots.get(i, (ch, ch, -9))
            if ch != cur:
                prev, cur, tc = cur, ch, t
            self.slots[i] = (cur, prev, tc)
            if ch == ":":
                f.draw(text_px(":", x, 1), (255, 120, 20) if now.second % 2 == 0 else (90, 40, 5))
            else:
                for yy in range(H):  # bęben
                    k = self.cyl(yy)
                    for xx in range(x - 1, x + gw + 1):
                        f.set(xx, yy, (30 * k, 16 * k, 4 * k))
                    f.set(x - 2, yy, (0, 0, 0))
                    f.set(x + gw + 1, yy, (0, 0, 0))
                p = clamp((t - tc) / 0.45)
                p = 1 - (1 - p) ** 3
                for glyph, off in ((prev, -p * 11), (cur, (1 - p) * 11)):
                    for (px, py) in text_px(glyph, x, 1):
                        yy = py + off
                        if 0 <= yy < H:
                            f.set(px, yy, mul((255, 175, 50), self.cyl(yy)))
            x += gw + 1
        for xx in range(W):  # połysk szybki
            f.add(xx, 3, (6, 6, 6))


class Swarm(Clock):
    """Cyfry z cząsteczek. Zmiana czasu = piksele odlatują i lecą w nowe miejsca."""

    def __init__(self):
        self.parts, self.txt = [], None

    def retarget(self, txt):
        targets = centered(txt)
        remaining = set(targets)
        loose = []
        for p in self.parts:
            if p["tgt"] is not None and p["tgt"] in remaining:
                remaining.discard(p["tgt"])
            elif p["tgt"] is not None:
                loose.append(p)
        rem = list(remaining)
        random.shuffle(rem)
        for p in loose:
            if rem:
                p["tgt"] = rem.pop()
                p["vx"] += random.uniform(-60, 60)
                p["vy"] += random.uniform(-40, 40)
            else:
                p["tgt"] = None
                p["life"] = 1.0
                p["vx"], p["vy"] = random.uniform(-50, 50), random.uniform(-40, 0)
        for tg in rem:
            side = random.choice((-3, W + 3))
            self.parts.append({"x": side, "y": random.uniform(0, H), "vx": 0, "vy": 0,
                               "tgt": tg, "life": 1.0, "hue": random.random()})

    def draw(self, f, now, t, dt):
        txt = now.strftime("%H:%M:%S")
        if txt != self.txt:
            self.txt = txt
            self.retarget(txt)
        alive = []
        for p in self.parts:
            if p["tgt"] is not None:
                tx, ty = p["tgt"]
                p["vx"] += (tx - p["x"]) * 60 * dt
                p["vy"] += (ty - p["y"]) * 60 * dt
                d = math.exp(-7 * dt)
                p["vx"] *= d
                p["vy"] *= d
            else:
                p["vy"] += 60 * dt
                p["life"] -= dt * 1.2
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            if p["life"] > 0:
                alive.append(p)
                sp = math.hypot(p["vx"], p["vy"])
                base = hsv(p["tgt"][0] / W * 0.8 + t * 0.05 if p["tgt"] else p["hue"], 0.85, 1)
                c = mul(lerp(base, (255, 255, 255), clamp(sp / 45)), p["life"])
                f.add(round(p["x"]), round(p["y"]), c)
        self.parts = alive


class Fire(Clock):
    """Ściana ognia; cyfry to ciemna sylwetka z żarzącą się krawędzią."""

    PAL = [(0, 0, 0), (60, 0, 0), (170, 20, 0), (255, 80, 0), (255, 170, 20), (255, 240, 120), (255, 255, 230)]

    def __init__(self):
        self.heat = [[0.0] * W for _ in range(H + 2)]
        self.acc = 0

    def color(self, h):
        h = clamp(h) * (len(self.PAL) - 1)
        i = min(int(h), len(self.PAL) - 2)
        return lerp(self.PAL[i], self.PAL[i + 1], h - i)

    def draw(self, f, now, t, dt):
        digits = centered(now.strftime("%H:%M"))
        self.acc += dt
        while self.acc > 1 / 40:
            self.acc -= 1 / 40
            hb = self.heat
            for x in range(W):  # żar na dole
                hb[H + 1][x] = 0.55 + random.random() * 0.45
                hb[H][x] = 0.45 + random.random() * 0.5
            new = [[0.0] * W for _ in range(H + 2)]
            new[H], new[H + 1] = hb[H], hb[H + 1]
            for y in range(H):
                for x in range(W):
                    xl, xr = max(0, x - 1), min(W - 1, x + 1)
                    v = (hb[y + 1][xl] + hb[y + 1][x] * 2 + hb[y + 1][xr] + hb[y + 2][x]) / 5.35
                    new[y][x] = max(0.0, v - random.random() * 0.12 - 0.015)
            self.heat = new
        for y in range(H):
            for x in range(W):
                f.px[y][x] = self.color(self.heat[y][x])
        # cyfry jako ciemna sylwetka wycięta w ogniu, z żarzącą się krawędzią
        dset = set(digits)
        for (x, y) in digits:
            edge = any((x + ox, y + oy) not in dset for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            h = self.heat[y][x]
            f.set(x, y, mul((255, 170, 60), 0.75 + 0.25 * h) if edge else (15 + 40 * h, 2, 0))


class Matrix(Clock):
    """Deszcz kodu; kropla przechodząca przez cyfrę rozbłyskuje na biało."""

    def __init__(self):
        self.glow = [[0.0] * W for _ in range(H)]
        self.drops = []

    def draw(self, f, now, t, dt):
        digits = centered(now.strftime("%H:%M"))
        dset = set(digits)
        if random.random() < 22 * dt:
            self.drops.append([random.randrange(W), -1.0, random.uniform(8, 20)])
        decay = math.exp(-dt * 4.5)
        g = self.glow
        for row in g:
            for x in range(W):
                row[x] *= decay
        keep = []
        heads = set()
        for d in self.drops:
            d[1] += d[2] * dt
            y = int(d[1])
            if 0 <= y < H:
                g[y][d[0]] = 1.0
                heads.add((d[0], y))
            if d[1] < H + 1:
                keep.append(d)
        self.drops = keep
        for y in range(H):
            for x in range(W):
                v = g[y][x]
                f.px[y][x] = (10 * v, 200 * v, 60 * v)
        f.outline(digits, (0, 12, 3))
        for (x, y) in digits:
            v = g[y][x]
            f.set(x, y, lerp((40, 200, 70), (230, 255, 230), v))
        for (x, y) in heads:
            if (x, y) not in dset:
                f.set(x, y, (180, 255, 190))


class Sky(Clock):
    """Prawdziwe położenie słońca i księżyca: świt i zmierzch z pomarańczowym pasem, dzień z chmurami, noc z gwiazdami, wieczorem światła w domach."""

    def __init__(self):
        rnd = random.Random(7)
        self.stars = [(rnd.randrange(W), rnd.randrange(7), rnd.random() * 6) for _ in range(40)]
        self.hills = [int(9.6 - 1.2 * math.sin(x * 0.07) - 0.8 * math.sin(x * 0.19 + 1)) for x in range(W)]
        self.houses = [(8, 5), (27, 4), (45, 6), (70, 4), (100, 5), (112, 4)]
        self.windows = [(hx + k, 9, rnd.random()) for hx, hw in self.houses for k in range(1, hw - 1, 2)]
        self.clouds = [[rnd.uniform(0, W), rnd.uniform(0.5, 3), rnd.uniform(0.6, 1.4), rnd.randint(5, 9)] for _ in range(4)]

    def draw(self, f, now, t, dt):
        elev, solar = sun_position(now)
        night = clamp((-elev - 3) / 6)
        day = clamp((elev + 1) / 6)
        dusk = clamp(1 - abs(elev + 1.5) / 6)
        if night > 0.3:
            for sx, sy, ph in self.stars:
                if math.sin(t * 1.7 + ph) > -0.3:
                    f.set(sx, sy, (170, 170, 220))
        if dusk > 0.2:
            for x in range(W):
                h = self.hills[x]
                f.set(x, h - 1, mul((255, 110, 20), dusk))
                f.set(x, h - 2, mul((230, 40, 110), dusk * 0.8))
        if day > 0.3:
            for c in self.clouds:
                c[0] = (c[0] + c[2] * dt) % (W + 12)
                for k in range(c[3]):
                    top = 1 if 1 < k < c[3] - 2 else 0
                    for yy in range(int(c[1]) + 1 - top, int(c[1]) + 2):
                        f.set(c[0] - 6 + k, yy, (200, 200, 215))
        sx = solar / 24 * W
        if elev > -4:
            sy = 9 - clamp((elev + 4) / 45) * 8
            disc(f, sx, sy, 2.2, (255, 230, 60))
            for k in range(8):
                a = k * math.pi / 4 + t * 0.4
                f.set(sx + math.cos(a) * 3.3, sy + math.sin(a) * 3.3, (255, 120, 0))
        if night > 0.1:
            mx = ((solar + 12) % 24) / 24 * W
            my = 9 - clamp((-elev + 4) / 45) * 8
            for ox, oy in ((0, 0), (1, 0), (0, 1), (1, 1), (0, -1), (-1, 0), (-1, 1)):
                f.set(mx + ox, my + oy, (230, 230, 190))
        edge = lerp((40, 210, 40), (0, 40, 140), night)
        fill = lerp((0, 110, 20), (0, 0, 0), night)
        for x in range(W):
            h = self.hills[x]
            f.set(x, h, edge)
            for y in range(h + 1, H):
                f.set(x, y, fill)
        wall, roof = lerp((210, 120, 50), (120, 50, 10), night), (220, 30, 20)
        for hx, hw in self.houses:
            for y in range(8, H):
                for x in range(hx, hx + hw):
                    f.set(x, y, wall)
            for k in range(hw):
                f.set(hx + k, 7 - min(k, hw - 1 - k) + (hw // 2) - 1, roof)
        for wx, wy, ph in self.windows:
            lit = night > 0.3 and ph > 0.25 or (0.1 < night <= 0.3 and ph > 0.6)
            f.set(wx, wy, (255, 210, 60) if lit else (40, 20, 0))
        tw = text_w(now.strftime("%H:%M"))
        clock_big(f, now, (255, 255, 255), x=(W - tw - (13 if not NARROW else 1)) if solar < 12 else (16 if not NARROW else 1))


class DayRibbon(Clock):
    """Taśma doby: 120 px = 24 h, kolory to niebo o danej godzinie, przeszłość jasna, przyszłość przygaszona."""

    def __init__(self):
        self.cache = (None, None)

    def draw(self, f, now, t, dt):
        key = now.strftime("%Y%m%d%H")
        if self.cache[0] != key:
            day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
            cols = []
            for x in range(W):
                el, _ = sun_position(day0 + dtm.timedelta(minutes=(x + 0.5) * 1440 / W))
                top, hor = sky_colors(el)
                cols.append(lerp(top, hor, 0.55))
            self.cache = (key, cols)
        cols = self.cache[1]
        nowx = (now.hour * 60 + now.minute + now.second / 60) / (1440 / W)
        for x in range(W):
            past = x < nowx
            k = 0.75 if past else 0.16
            for y in range(7, H):
                f.set(x, y, mul(cols[x], k))
            if int(x * 24 / W) != int((x - 1) * 24 / W) or x == 0:
                hour = int(x * 24 / W)
                f.set(x, 6, (90, 90, 90) if hour % 6 == 0 else (25, 25, 25))
                if hour % 6 == 0:
                    f.set(x, 5, (60, 60, 60))
        pulse = 0.6 + 0.4 * math.sin(t * 4)
        cx = int(nowx)
        for y in range(6, H):
            f.set(cx, y, (255, 255, 255))
            for o, k in ((-1, 0.45), (1, 0.45), (-2, 0.18), (2, 0.18)):
                f.add(cx + o, y, mul((255, 255, 255), k * pulse))
        label = now.strftime("%H:%M")
        lw = text_w(label, SMALL)
        lx = int(clamp(cx - lw // 2, 0, W - lw))
        f.draw(text_px(label, lx, 0, SMALL), (255, 255, 255))
        # godziny 0/6/12/18 w wolnym miejscu
        for hh in (6, 12, 18):
            hx = hh * W // 24 - text_w(str(hh), SMALL) // 2
            if abs(hx - lx) > lw + 3:
                f.draw(text_px(str(hh), hx, 0, SMALL), (55, 55, 70))


class Scanner(Clock):
    """Wiązka jak w KITT; cyfry świecą po przejściu wiązki i powoli gasną."""

    def __init__(self):
        self.glow = [[0.0] * W for _ in range(H)]
        self.last = 0

    def draw(self, f, now, t, dt):
        digits = centered(now.strftime("%H:%M"))
        dset = set(digits)
        pos = (math.sin(t * 2.1) * 0.5 + 0.5) * (W + 8) - 4
        decay = math.exp(-dt * 1.6)
        g = self.glow
        lo, hi = sorted((self.last, pos))
        for y in range(H):
            row = g[y]
            for x in range(W):
                row[x] *= decay
                if lo - 1 <= x <= hi + 1:
                    row[x] = 1.0 if (x, y) in dset else max(row[x], 0.22)
        self.last = pos
        for y in range(H):
            for x in range(W):
                v = g[y][x]
                if (x, y) in dset:
                    v = max(v, 0.1)
                    f.px[y][x] = lerp((120 * v * 2, 0, 0), (255, 200, 170), clamp(v - 0.5) * 2) if v > 0.5 else (255 * v * 2, 10 * v, 0)
                else:
                    f.px[y][x] = (90 * v, 0, 0)
        for o in range(-2, 3):
            k = 1 - abs(o) / 3
            for y in range(H):
                f.add(pos + o, y, (255 * k, 30 * k * k, 10 * k * k))


class Rainbow(Clock):
    """Cyfry wypełnione płynącą tęczą, falujące jak flaga; w tle migoczące gwiazdki."""

    def __init__(self):
        self.sp = [(random.randrange(W), random.randrange(H), random.random() * 9, random.uniform(1, 3)) for _ in range(40)]

    def draw(self, f, now, t, dt):
        for x, y, ph, s in self.sp:
            v = max(0, math.sin(t * s + ph)) ** 8
            f.set(x, y, (120 * v, 120 * v, 160 * v))
        txt = now.strftime("%H:%M:%S")
        x = (W - text_w(txt)) // 2
        for i, ch in enumerate(txt):
            dy = round(math.sin(t * 3.2 - i * 0.75))
            pts = text_px(ch, x, 1 + dy)
            if ch == ":":
                k = 0.5 + 0.5 * math.sin(t * 6)
                f.draw(pts, mul((255, 255, 255), 0.3 + 0.7 * k))
            else:
                for (px, py) in pts:
                    f.set(px, py, hsv(px * 0.011 + py * 0.035 - t * 0.25, 0.9, 1))
            x += len(BIG[ch][0]) + 1


class Warp(Clock):
    """Lot przez gwiazdy; nowa minuta (i co 15 s mini) = skok w nadprzestrzeń ze smugami."""

    def __init__(self):
        self.stars = [self.new_star(True) for _ in range(90)]
        self.warp_t, self.last_min, self.last_q = -9, None, None

    @staticmethod
    def new_star(anywhere=False):
        return [random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(0.1, 1) if anywhere else 1.0]

    def draw(self, f, now, t, dt):
        if self.last_min is not None and now.minute != self.last_min:
            self.warp_t = t
        q = now.second // 15
        if self.last_q is not None and q != self.last_q and now.second != 0:
            self.warp_t = t - 0.8  # krótszy skok
        self.last_min, self.last_q = now.minute, q
        w = clamp(1 - abs((t - self.warp_t) - 0.9) / 0.9)
        speed = 0.25 + 2.2 * w
        cx, cy = W / 2, H / 2
        for s in self.stars:
            ox, oy = cx + s[0] / s[2] * 70, cy + s[1] / s[2] * 8
            s[2] -= speed * dt
            if s[2] <= 0.05:
                s[:] = self.new_star()
                continue
            nx, ny = cx + s[0] / s[2] * 70, cy + s[1] / s[2] * 8
            if not (-5 < nx < W + 5 and -3 < ny < H + 3):
                s[:] = self.new_star()
                continue
            b = clamp(1.1 - s[2])
            col = lerp((140, 160, 255), (255, 255, 255), b)
            steps = max(1, int(math.hypot(nx - ox, ny - oy)))
            for k in range(steps + 1):
                a = k / steps
                f.add(ox + (nx - ox) * a, oy + (ny - oy) * a, mul(col, b * (0.3 + 0.7 * a)))
        digits = centered(now.strftime("%H:%M"))
        f.outline(digits, (0, 0, 20))
        f.draw(digits, lerp((210, 225, 255), (255, 255, 255), w))


class Life(Clock):
    """Gra w życie w tle. Każda mijająca minuta rozpada się na żywe komórki."""

    def __init__(self):
        self.cells = [[random.random() < 0.18 for _ in range(W)] for _ in range(H)]
        self.bright = [[0.0] * W for _ in range(H)]
        self.acc, self.txt = 0.0, None

    def step(self):
        c = self.cells
        n = [[False] * W for _ in range(H)]
        pop = 0
        for y in range(H):
            for x in range(W):
                k = 0
                for dy in (-1, 0, 1):
                    row = c[(y + dy) % H]
                    for dx in (-1, 0, 1):
                        if (dx or dy) and row[(x + dx) % W]:
                            k += 1
                alive = k == 3 or (c[y][x] and k == 2)
                n[y][x] = alive
                pop += alive
        self.cells = n
        if pop < 40:
            for _ in range(160):
                self.cells[random.randrange(H)][random.randrange(W)] = True

    def draw(self, f, now, t, dt):
        txt = now.strftime("%H:%M")
        if self.txt is not None and txt != self.txt:
            for (x, y) in centered(self.txt):  # stara minuta ożywa
                self.cells[y % H][x % W] = True
        self.txt = txt
        self.acc += dt
        while self.acc > 0.14:
            self.acc -= 0.14
            self.step()
        for y in range(H):
            for x in range(W):
                b = self.bright[y][x]
                b = 1.0 if self.cells[y][x] else b * math.exp(-dt * 5)
                self.bright[y][x] = b
                f.px[y][x] = mul(hsv(0.45 + x / W * 0.35 + t * 0.02, 0.8, 1), b * 0.55)
        digits = centered(txt)
        f.outline(digits, (0, 0, 0))
        f.draw(digits, (255, 255, 255))


class Aquarium(Clock):
    """Rybki pływają przed i za cyframi, bąbelki, wodorosty, refleksy światła."""

    FISH = ["#.##.", "###e#", "#.##."]

    def __init__(self):
        cols = [(255, 120, 0), (255, 220, 0), (255, 60, 150), (80, 220, 255), (255, 90, 40)]
        self.fish = [{"x": random.uniform(0, W), "y": random.uniform(1, 8), "v": random.choice((-1, 1)) * random.uniform(5, 12),
                      "c": cols[i % len(cols)], "front": i % 2 == 0, "ph": random.random() * 6} for i in range(7)]
        self.bubbles = []
        self.weeds = [(x, random.randint(4, 7), random.random() * 6) for x in (5, 13, 34, 52, 67, 88, 97, 110, 116)]

    def draw_fish(self, f, fi):
        rows = self.FISH if fi["v"] > 0 else [r[::-1] for r in self.FISH]
        for r, row in enumerate(rows):
            for k, ch in enumerate(row):
                if ch != ".":
                    f.set(fi["x"] + k, fi["y"] + r, (10, 10, 30) if ch == "e" else fi["c"])

    def draw(self, f, now, t, dt):
        for y in range(H):
            base = lerp((0, 45, 95), (0, 12, 35), y / (H - 1))
            for x in range(W):
                caust = max(0, math.sin(x * 0.35 + t * 1.3) * math.sin(x * 0.17 - t * 0.9 + y * 0.6)) ** 3
                f.px[y][x] = lerp(base, (40, 120, 170), caust * (1 - y / H) * 0.7)
        for x in range(W):
            f.set(x, H - 1, (70, 55, 20) if x % 3 else (90, 75, 30))
        for wx, wh, ph in self.weeds:
            for k in range(wh):
                y = H - 2 - k
                sway = math.sin(t * 1.4 + ph + k * 0.6) * k / wh * 1.5
                f.set(wx + round(sway), y, (20, 150 - k * 10, 40))
        for fi in self.fish:
            fi["x"] += fi["v"] * dt
            fi["y"] += math.sin(t * 1.5 + fi["ph"]) * dt * 1.2
            fi["y"] = clamp(fi["y"], 0, H - 4)
            if fi["x"] > W + 6 or fi["x"] < -10:
                fi["v"] = -fi["v"]
                fi["y"] = random.uniform(0.5, H - 4.5)
                fi["front"] = not fi["front"]
        for fi in self.fish:
            if not fi["front"]:
                self.draw_fish(f, fi)
        digits = centered(now.strftime("%H:%M"))
        f.draw(digits, (190, 235, 255))
        for fi in self.fish:
            if fi["front"]:
                self.draw_fish(f, fi)
        if random.random() < 5 * dt:
            self.bubbles.append([random.choice(self.weeds)[0] + random.uniform(-2, 2), H - 2.0, random.uniform(3, 6), random.random() * 6])
        keep = []
        for b in self.bubbles:
            b[1] -= b[2] * dt
            if b[1] > -1:
                keep.append(b)
                f.add(b[0] + math.sin(t * 4 + b[3]) * 0.8, b[1], (90, 150, 170))
        self.bubbles = keep


class Pong(Clock):
    """Pong: lewy wynik = godziny, prawy = minuty. Przy zmianie jedna paletka 'przepuszcza' piłkę."""

    PH = 3
    LX, RX = 1, W - 2

    def __init__(self):
        self.shown, self.miss = None, None
        self.ly = self.ry = H / 2
        self.serve(random.choice((-1, 1)))

    def serve(self, d):
        self.bx, self.by = W / 2, random.uniform(3, H - 3)
        self.vx, self.vy = 40 * d, random.choice((-1, 1)) * random.uniform(8, 18)

    def paddle(self, py, side, approaching, dist, dt):
        half = self.PH / 2
        if self.miss == side and approaching:
            goal, speed = (self.by + 6 if self.by < H / 2 else self.by - 6), 25
        elif approaching:
            if dist < 10:
                return clamp(self.by, half, H - 1 - half)
            goal, speed = self.by, 30
        else:
            goal, speed = H / 2, 8
        goal = clamp(goal, half, H - 1 - half)
        step = speed * dt
        return py + clamp(goal - py, -step, step)

    def draw(self, f, now, t, dt):
        target = (now.hour, now.minute)
        if self.shown is None:
            self.shown = target
        if self.miss is None and target != self.shown:
            self.miss = "right" if target[0] != self.shown[0] else "left"
        self.bx += self.vx * dt
        self.by += self.vy * dt
        if self.by < 0:
            self.by, self.vy = -self.by, abs(self.vy)
        if self.by > H - 1:
            self.by, self.vy = 2 * (H - 1) - self.by, -abs(self.vy)
        self.ly = self.paddle(self.ly, "left", self.vx < 0, self.bx - self.LX, dt)
        self.ry = self.paddle(self.ry, "right", self.vx > 0, self.RX - self.bx, dt)
        for side, px, py in (("left", self.LX, self.ly), ("right", self.RX, self.ry)):
            hit = abs(self.by - py) <= self.PH / 2 + 0.6
            if side == "left" and self.vx < 0 and px < self.bx <= px + 1.5 and hit:
                self.vx, self.bx = abs(self.vx), px + 1.5
                self.vy = clamp(self.vy + (self.by - py) * 8, -22, 22)
            if side == "right" and self.vx > 0 and px - 1.5 <= self.bx < px and hit:
                self.vx, self.bx = -abs(self.vx), px - 1.5
                self.vy = clamp(self.vy + (self.by - py) * 8, -22, 22)
        if self.bx < -3 or self.bx > W + 2:
            self.shown, self.miss = target, None
            self.serve(1 if self.bx < 0 else -1)
        hh, mm = f"{self.shown[0]:02d}", f"{self.shown[1]:02d}"
        f.draw(text_px(hh, W // 4 - text_w(hh) // 2, 1), (55, 55, 75))
        f.draw(text_px(mm, 3 * W // 4 - text_w(mm) // 2, 1), (55, 55, 75))
        for y in range(0, H, 2):
            f.set(W // 2, y, (40, 40, 40))
        for px, py in ((self.LX, self.ly), (self.RX, self.ry)):
            top = int(round(py - self.PH / 2))
            for y in range(top, top + self.PH):
                f.set(px, y, (255, 255, 255))
        f.set(round(self.bx), round(self.by), (255, 210, 0))
        f.add(round(self.bx - math.copysign(1, self.vx)), round(self.by), (80, 60, 0))


# ================================================================ SIEĆ (dane z internetu w tle)
def http(url, kind="json", timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "wled-clocks/2.0 (python urllib)",
                                               "Accept": "application/json" if kind == "json" else "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read()
    if kind == "json":
        return json.loads(b)
    if kind == "xml":
        return ET.fromstring(b)
    return b.decode("utf-8", "replace").strip()


def _meteo():
    return http("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": LAT, "longitude": LON, "timezone": "auto", "past_days": 1, "forecast_days": 2,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,"
                   "wind_direction_10m,pressure_msl,precipitation,is_day",
        "hourly": "temperature_2m,precipitation_probability,precipitation,pressure_msl,uv_index",
        "daily": "sunrise,sunset,uv_index_max"}))


def _air():
    return http("https://air-quality-api.open-meteo.com/v1/air-quality?" + urllib.parse.urlencode({
        "latitude": LAT, "longitude": LON, "current": "pm2_5,pm10,european_aqi"}))


def _crypto():
    return http("https://api.binance.com/api/v3/ticker/24hr?symbols="
                + urllib.parse.quote('["BTCUSDT","ETHUSDT","SOLUSDT","DOGEUSDT"]'))


def _quakes():
    out = []
    for q in http("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson")["features"]:
        p, c = q["properties"], q["geometry"]["coordinates"]
        out.append((c[0], c[1], p.get("mag") or 0, p.get("place") or "", p.get("time") or 0))
    return out


def _kp():
    last = http("https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json")[-1]
    return float(last["Kp"] if isinstance(last, dict) else last[1])


def _hn():
    ids = http("https://hacker-news.firebaseio.com/v0/topstories.json")[:10]
    return [(http(f"https://hacker-news.firebaseio.com/v0/item/{i}.json") or {}).get("title", "") for i in ids]


BANNER = {"city": "Wrocławiu", "lat": 51.11, "lon": 17.03}  # transparent ludzika: miasto (w miejscowniku) i współrzędne


def _banner_weather():
    return http("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": BANNER["lat"], "longitude": BANNER["lon"], "timezone": "auto", "forecast_days": 2,
        "current": "temperature_2m", "daily": "temperature_2m_max,weather_code"}))


def _news():
    root = http("https://tvn24.pl/najnowsze.xml", "xml")
    return [html.unescape(i.findtext("title") or "").strip() for i in root.iter("item")][:12]


SOURCES = {  # klucz: (funkcja, co ile sekund odświeżać)
    "meteo": (_meteo, 600),
    "air": (_air, 900),
    "nbp": (lambda: http("https://api.nbp.pl/api/exchangerates/tables/A/last/2/?format=json"), 3600),
    "gold": (lambda: http("https://api.nbp.pl/api/cenyzlota/last/30/?format=json"), 3600),
    "crypto": (_crypto, 60),
    "klines": (lambda: [float(k[4]) for k in http("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=120")], 600),
    "iss": (lambda: http("https://api.wheretheiss.at/v1/satellites/25544"), 5),
    "astros": (lambda: http("http://api.open-notify.org/astros.json"), 3600),
    "quakes": (_quakes, 600),
    "kp": (_kp, 900),
    "height": (lambda: int(http("https://mempool.space/api/blocks/tip/height", "text")), 60),
    "hn": (_hn, 900),
    "news": (_news, 600),
    "names": (lambda: http("https://nameday.abalin.net/api/V2/today/pl")["data"]["pl"], 3600),
    "launch": (lambda: [(x["name"], x["net"]) for x in http("https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=5&mode=list")["results"]], 3600),
    "joke": (lambda: http("https://icanhazdadjoke.com/")["joke"], 300),
    "baner": (lambda: _banner_weather(), 900),
}


class Net:
    """Pobiera dane w osobnym wątku – tylko te, których używa efekt widoczny w ostatnich 90 s; cache z TTL."""

    def __init__(self):
        self.data, self.when, self.want, self.err, self.fail = {}, {}, {}, {}, {}
        self.thread = None

    def get(self, key):
        self.want[key] = time.monotonic()
        if self.thread is None:
            self.thread = threading.Thread(target=self.loop, daemon=True)
            self.thread.start()
        return self.data.get(key)

    def fetch(self, key):
        try:
            self.data[key] = SOURCES[key][0]()
            self.when[key] = time.monotonic()
            self.err.pop(key, None)
            self.fail.pop(key, None)
        except Exception as e:  # noqa: BLE001
            self.err[key] = (str(e) or type(e).__name__)[:60]
            self.fail[key] = time.monotonic()

    def due(self, key, now):
        ttl = SOURCES[key][1]
        if key in self.fail and now - self.fail[key] < min(ttl, 60):
            return False
        return key not in self.when or now - self.when[key] >= ttl

    def loop(self):
        while True:
            now = time.monotonic()
            for key, w in list(self.want.items()):
                if now - w < 90 and self.due(key, now):
                    self.fetch(key)
            time.sleep(0.5)

    def prefetch(self):
        for key in list(self.want):
            if key not in self.data:
                self.fetch(key)

    def status(self):
        now = time.monotonic()
        keys = [k for k, w in self.want.items() if now - w < 3]
        if not keys:
            return ""
        parts = []
        for k in keys:
            if k in self.err:
                parts.append(f"{k}: błąd ({self.err[k]})")
            elif k in self.when:
                parts.append(f"{k}: ok, {int(now - self.when[k])} s temu")
            else:
                parts.append(f"{k}: pobieram…")
        return ", ".join(parts)


NET = Net()


def meteo_now(m):
    return dtm.datetime.now(dtm.timezone.utc).replace(tzinfo=None) + dtm.timedelta(seconds=m.get("utc_offset_seconds", 0))


def meteo_idx(m):
    key, times = meteo_now(m).strftime("%Y-%m-%dT%H:00"), m["hourly"]["time"]
    return times.index(key) if key in times else 0


def meteo_day(m):
    key, days = meteo_now(m).strftime("%Y-%m-%d"), m["daily"]["time"]
    return days.index(key) if key in days else 0


def wmo(code):
    if code == 0:
        return "slonce", "POGODNIE"
    if code in (1, 2):
        return "czesciowo", "CHMURKI"
    if code == 3:
        return "chmury", "POCHMURNO"
    if code in (45, 48):
        return "mgla", "MGŁA"
    if 51 <= code <= 57:
        return "deszcz", "MŻAWKA"
    if 61 <= code <= 67:
        return "deszcz", "DESZCZ"
    if 80 <= code <= 82:
        return "ulewa", "ULEWA"
    if 71 <= code <= 77 or code in (85, 86):
        return "snieg", "ŚNIEG"
    if code >= 95:
        return "burza", "BURZA"
    return "chmury", "?"


# ================================================================ wspólne narzędzia efektów
REG = {}


def reg(name):
    def deco(cls):
        REG[name] = cls
        return cls
    return deco


def grad(stops, v):
    if v <= stops[0][0]:
        return stops[0][1]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if v <= b:
            return lerp(ca, cb, (v - a) / (b - a))
    return stops[-1][1]


TEMP_STOPS = [(-20, (200, 200, 255)), (-5, (60, 120, 255)), (5, (0, 220, 220)), (14, (80, 255, 80)),
              (22, (255, 230, 0)), (30, (255, 120, 0)), (38, (255, 0, 0))]


def temp_color(v):
    return grad(TEMP_STOPS, v)


def hash1(n):
    n = (int(n) * 374761393 + 668265263) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def noise1(x):
    i = math.floor(x)
    fr = x - i
    u = fr * fr * (3 - 2 * fr)
    return hash1(i) * (1 - u) + hash1(i + 1) * u


def noise2(x, y):
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    ux, uy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a0, a1 = hash1(ix * 7919 + iy * 104729), hash1((ix + 1) * 7919 + iy * 104729)
    b0, b1 = hash1(ix * 7919 + (iy + 1) * 104729), hash1((ix + 1) * 7919 + (iy + 1) * 104729)
    a, b = a0 + (a1 - a0) * ux, b0 + (b1 - b0) * ux
    return a + (b - a) * uy


NARROW = W < 100   # np. połowa panelu (60 kolumn): gęste układy pokazujemy na zmianę, „stronami”


def page(t, n, secs=5):
    """Która strona (0..n-1) jest teraz widoczna – zmiana co secs sekund."""
    return int(t / secs) % n


def clock_big(f, now, c=(255, 255, 255), fmt="%H:%M", x=None, y=1, outline=(0, 0, 0)):
    s = now.strftime(fmt)
    pts = text_px(s, (W - text_w(s)) // 2 if x is None else x, y)
    if outline is not None:
        f.outline(pts, outline)
    f.draw(pts, c)
    return pts


def small_time(f, now, x=None, y=0, c=(255, 255, 255), fmt="%H:%M", outline=(0, 0, 0)):
    s = now.strftime(fmt)
    pts = text_px(s, W - text_w(s, SMALL) if x is None else x, y, SMALL)
    if outline is not None:
        f.outline(pts, outline)
    f.draw(pts, c)


def loading(f, t, key, what):
    err = NET.err.get(key)
    s = f"{what}: brak danych" if err else what + "." * (int(t * 3) % 4)
    f.draw(text_px(s, max(0, (W - text_w(s, TXT)) // 2), 0, TXT), (200, 60, 40) if err else (80, 80, 110))


def scroll_px(t, speed):
    """Przesunięcie tekstu w pikselach – zawsze równy krok co klatkę (np. 1 px na klatkę albo 1 px co 2 klatki),
    więc tekst nie szarpie. speed w px/s, mnożone przez ustawienie „tempo tekstu”."""
    fdt = ANIM["tempo"] / ANIM["fps"]          # czas animacji na klatkę
    n = int(round(t / fdt))                   # numer klatki
    ppf = max(0.01, speed * ANIM["text"] * fdt)
    return n * round(ppf) if ppf >= 1 else n // max(1, round(1 / ppf))


def even_speed(v):
    """Prędkość (px/s) dociągnięta do kroku animacji: całe piksele co klatkę albo 1 px co n klatek – zawsze
    w równych odstępach (bez 3, 4, 3, 3, 4 klatek na piksel), więc powolny ruch nie szarpie."""
    fdt = ANIM["tempo"] / ANIM["fps"]
    ppf = v * fdt
    return (round(ppf) if ppf >= 1 else 1 / max(1, round(1 / ppf))) / fdt


def scroll_time(dist, speed):
    """Ile sekund animacji zajmuje przewinięcie dist pikseli (zgodnie ze scroll_px)."""
    fdt = ANIM["tempo"] / ANIM["fps"]
    ppf = max(0.01, speed * ANIM["text"] * fdt)
    per_frame = round(ppf) if ppf >= 1 else 1 / max(1, round(1 / ppf))
    return dist / per_frame * fdt


def scroll_segs(f, segs, t, speed=28, y=0, x_min=0, font=None, gap=18):
    """Pasek przewijany w pętli: segs = [(tekst, kolor), ...]."""
    font = font or TXT
    widths = [text_w(s, font) + 1 for s, _ in segs]
    total = sum(widths) + gap
    k = W - scroll_px(t, speed) % total
    while k > x_min:
        k -= total
    while k < W:
        x = k
        for (s, c), w in zip(segs, widths):
            if x + w >= x_min and x < W:
                for px, py in text_px(s, x, y, font):
                    if x_min <= px < W:
                        f.set(px, py, c)
            x += w
        k += total
    return total


def disc(f, cx, cy, r, c, add=False):
    put = f.add if add else f.set
    ir = int(r) + 1
    for oy in range(-ir, ir + 1):
        for ox in range(-ir, ir + 1):
            if ox * ox + oy * oy < r * r:
                put(cx + ox, cy + oy, c)


def sprite(f, rows, x, y, pal, flip=False):
    """rows: lista napisów; znak -> kolor z pal (kropka = przezroczyste)."""
    for r, row in enumerate(rows):
        if flip:
            row = row[::-1]
        for k, ch in enumerate(row):
            if ch != ".":
                f.set(x + k, y + r, pal[ch])


class Persist:
    """Bufor z poświatą (smugi): add() dokłada światło, fade() wygasza, blit() rysuje na klatce."""

    def __init__(self):
        self.b = [[(0.0, 0.0, 0.0)] * W for _ in range(H)]

    def fade(self, k):
        self.b = [[(r * k, g * k, b * k) for r, g, b in row] for row in self.b]

    def add(self, x, y, c):
        x, y = int(math.floor(x)), int(math.floor(y))
        if 0 <= x < W and 0 <= y < H:
            o = self.b[y][x]
            self.b[y][x] = (o[0] + c[0], o[1] + c[1], o[2] + c[2])

    def blit(self, f):
        for y in range(H):
            row, src = f.px[y], self.b[y]
            f.px[y] = [(a[0] + b[0], a[1] + b[1], a[2] + b[2]) for a, b in zip(row, src)]


# mapa świata 120x12 (3° x 15° na piksel), zakresy kolumn lądu w każdym wierszu
_MAP = {0: [(27, 38), (40, 53), (65, 68), (78, 84), (88, 95)], 1: [(5, 40), (42, 55), (62, 119)],
        2: [(17, 41), (57, 106), (111, 115)], 3: [(18, 36), (57, 63), (64, 68), (69, 100), (103, 107)],
        4: [(23, 31), (54, 79), (82, 90), (91, 100)], 5: [(30, 43), (54, 76), (85, 86), (92, 96), (100, 102)],
        6: [(33, 48), (63, 73), (93, 96), (98, 101), (103, 106)], 7: [(36, 46), (64, 71), (74, 76), (98, 111)],
        8: [(35, 41), (66, 69), (98, 110), (115, 119)], 9: [(35, 38)], 10: [(10, 44), (58, 119)], 11: [(0, 119)]}
_LAND120 = {(x, y) for y, rs in _MAP.items() for a, b in rs for x in range(a, b + 1)}
LAND = {(x, y) for x in range(W) for y in range(H) if (int((x + 0.5) * 120 / W), y) in _LAND120}


def map_xy(lat, lon):
    return (lon + 180) / 360 * W, (90 - lat) / 15


def subsolar(now):
    """(deklinacja słońca w radianach, długość geograficzna punktu podsłonecznego w stopniach)"""
    u = now.astimezone(dtm.timezone.utc)
    g = 2 * math.pi / 365 * (u.timetuple().tm_yday - 1 + (u.hour - 12) / 24)
    eot = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                    - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    return decl, -15 * (u.hour + u.minute / 60 + u.second / 3600 - 12 + eot / 60)


def world_map(f, now, k=1.0):
    dec, slon = subsolar(now)
    sd, cd = math.sin(dec), math.cos(dec)
    for y in range(H):
        lat = math.radians(90 - (y + 0.5) * 15)
        sl, cl = math.sin(lat), math.cos(lat)
        row = f.px[y]
        for x in range(W):
            cz = sl * sd + cl * cd * math.cos(math.radians(-180 + (x + 0.5) * 360 / W - slon))
            light = clamp(cz * 4 + 0.5, 0.15, 1.0) * k
            if (x, y) in LAND:
                c = (140, 150, 160) if y in (0, 10, 11) else (30, 110, 35)
            else:
                c = (0, 30, 80)
            row[x] = mul(c, light)


def draw_icon(f, kind, x0, y0, t, day=1):
    cx, cy = x0 + 8, y0 + 6

    def sun(x, y):
        disc(f, x, y, 2.8, (255, 215, 50))
        for i in range(8):
            a = i * math.pi / 4 + t * 0.5
            k = 0.6 + 0.4 * math.sin(t * 3 + i)
            for r in (4.2, 5.2):
                f.add(x + math.cos(a) * r, y + math.sin(a) * r, mul((255, 140, 20), k))

    def moon(x, y):
        for oy in range(-4, 5):
            for ox in range(-4, 5):
                if ox * ox + oy * oy < 12.5 and (ox + 2) ** 2 + (oy + 1) ** 2 >= 10:
                    f.set(x + ox, y + oy, (230, 230, 190))

    def cloud(x, y, col):
        for bx, by, r in ((-3.5, 1, 2.6), (0, -0.5, 3.3), (3.5, 1, 2.5), (0, 1.5, 2.8)):
            disc(f, x + bx, y + by, r, col)

    light = sun if day else moon
    if kind == "slonce":
        light(cx, cy)
    elif kind == "czesciowo":
        light(cx - 3, cy - 2)
        cloud(cx + 2 + math.sin(t * 0.5), cy + 2, (200, 200, 215))
    elif kind == "chmury":
        cloud(cx - 2 + math.sin(t * 0.4), cy - 1, (110, 110, 125))
        cloud(cx + 2, cy + 1.5, (190, 190, 205))
    elif kind == "mgla":
        for y in range(1, 12, 2):
            for x in range(x0, x0 + 17):
                f.set(x, y0 + y, mul((150, 150, 165), 0.4 + 0.3 * (1 + math.sin(x * 0.5 + t * (1 + y * 0.15) + y))))
    elif kind == "snieg":
        cloud(cx, cy - 2.5, (170, 170, 185))
        for i in range(5):
            f.set(x0 + 3 + i * 2.7 + math.sin(t * 2 + i), cy + 1 + (t * 2.5 + i * 1.3) % 6, (255, 255, 255))
    else:
        n = 4 if kind == "deszcz" else 7
        for i in range(n):
            x, y = x0 + 3 + i * 12 / n, cy + 1 + (t * 9 + i * 1.7) % 6
            f.set(x, y, (90, 150, 255))
            f.set(x, y - 1, (40, 70, 160))
        cloud(cx, cy - 2.5, (150, 150, 165) if kind == "deszcz" else (75, 75, 90))
        if kind == "burza" and (t % 2.7) < 0.25:
            f.line(cx, cy, cx - 2, cy + 3, (255, 255, 120))
            f.line(cx - 2, cy + 3, cx + 1, cy + 3, (255, 255, 120))
            f.line(cx + 1, cy + 3, cx - 1, cy + 6, (255, 255, 120))


PL_DAYS = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
PL_MONTHS = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września",
             "października", "listopada", "grudnia"]
PL_MON3 = ["STY", "LUT", "MAR", "KWI", "MAJ", "CZE", "LIP", "SIE", "WRZ", "PAŹ", "LIS", "GRU"]

# ================================================================ EFEKTY Z DANYMI Z INTERNETU
@reg("pogoda")
class Weather(Clock):
    """Pogoda teraz (Open-Meteo): animowana ikona, temperatura w jej kolorze, opis, wiatr i godzina."""

    def draw(self, f, now, t, dt):
        m = NET.get("meteo")
        if not m:
            return loading(f, t, "meteo", "pogoda")
        c = m["current"]
        kind, desc = wmo(c["weather_code"])
        temp = round(c["temperature_2m"])
        s = f"{temp}°"
        if NARROW:
            pg = page(t, 3)
            if pg == 0:
                draw_icon(f, kind, 2, 0, t, c.get("is_day", 1))
                f.draw(text_px(s, 22, 1), temp_color(temp))
            elif pg == 1:
                f.text(desc, (W - text_w(desc, SMALL)) // 2, 0, (210, 210, 230), SMALL)
                w_ = f"{round(c['wind_speed_10m'])}KM/H"
                f.text(w_, (W - text_w(w_, SMALL)) // 2, 6, (110, 170, 230), SMALL)
            else:
                clock_big(f, now)
            return
        draw_icon(f, kind, 0, 0, t, c.get("is_day", 1))
        f.draw(text_px(s, 19, 1), temp_color(temp))
        x2 = 19 + text_w(s) + 4
        wind = f"{round(c['wind_speed_10m'])}KM/H"
        tx = W - text_w(now.strftime("%H:%M"))
        fits = x2 + max(text_w(desc, SMALL), text_w(wind, SMALL)) < tx - 2
        if fits or page(t, 2) == 0:
            f.draw(text_px(desc, x2, 0, SMALL), (210, 210, 230))
            f.draw(text_px(wind, x2, 6, SMALL), (110, 170, 230))
        if fits or page(t, 2) == 1:
            clock_big(f, now, x=tx)


@reg("prognoza")
class Forecast(Clock):
    """Najbliższe 24 h (Open-Meteo): krzywa temperatury w jej kolorach, niebieskie słupki = szansa opadów."""

    def draw(self, f, now, t, dt):
        m = NET.get("meteo")
        if not m:
            return loading(f, t, "meteo", "prognoza")
        h, i0 = m["hourly"], meteo_idx(m)
        temps = [v if v is not None else 0 for v in h["temperature_2m"][i0:i0 + 25]]
        probs = h["precipitation_probability"][i0:i0 + 25]
        hours = [int(s[11:13]) for s in h["time"][i0:i0 + 25]]
        n = len(temps) - 1
        if n < 2:
            return loading(f, t, "meteo", "prognoza")
        lo, hi = min(temps), max(temps)
        span = max(hi - lo, 3)
        for x in range(W):
            p = x / (W - 1) * n
            i = min(int(p), n - 1)
            v = temps[i] + (temps[i + 1] - temps[i]) * (p - i)
            pr = (probs[i] or 0) / 100
            if pr > 0.05:
                for yy in range(round(12 - pr * 6), 12):
                    f.add(x, yy, (0, 50 * pr + 10, 160 * pr + 30))
            y = 10.5 - (v - lo) / span * 7.5
            col = temp_color(v)
            for yy in range(int(y) + 1, 12):
                f.add(x, yy, mul(col, 0.1))
            f.set(x, y, col)
        lab = f"{round(temps[0])}°"
        for i, hr in enumerate(hours):
            x = round(i * (W - 1) / n)
            hx = x - text_w(str(hr), SMALL) // 2
            if hr % 6 == 0 and hx > text_w(lab, SMALL) + 3 and hx + text_w(str(hr), SMALL) <= W:
                f.draw(text_px(str(hr), hx, 0, SMALL), (90, 90, 130))
        f.text(lab, 0, 0, temp_color(temps[0]), SMALL, (0, 0, 0))
        f.add(0, 10.5 - (temps[0] - lo) / span * 7.5, mul((255, 255, 255), 0.5 + 0.5 * math.sin(t * 5)))


@reg("opady")
class Precip(Clock):
    """Pada tak, jak pada naprawdę: gęstość kropli = opad i szansa opadów teraz (Open-Meteo); przy mrozie płatki śniegu."""

    def __init__(self):
        self.drops, self.acc = [], 0.0

    def draw(self, f, now, t, dt):
        m = NET.get("meteo")
        inten, snow, prob = 0.15, False, None
        if m:
            c = m["current"]
            prob = m["hourly"]["precipitation_probability"][meteo_idx(m)] or 0
            inten = clamp((c.get("precipitation") or 0) / 3 + prob / 100 * 0.35)
            snow = wmo(c["weather_code"])[0] == "snieg" or c["temperature_2m"] < 0.5
        for y in range(H):
            c = lerp((12, 14, 22), (4, 6, 12), y / H)
            for x in range(W):
                f.px[y][x] = c
        for x in range(W):
            for y in range(3):
                v = noise2(x * 0.08 + t * 0.2, y * 0.6) * (0.3 + inten)
                f.add(x, y, mul((70, 75, 90), v * (1 - y / 3)))
        self.acc += (3 + inten * 160) * dt
        while self.acc >= 1:
            self.acc -= 1
            self.drops.append([random.uniform(0, W), -1.0, random.uniform(3, 5) if snow else random.uniform(24, 34),
                               random.random() * 6])
        keep = []
        for d in self.drops:
            d[1] += d[2] * dt
            if snow:
                d[0] += math.sin(t * 2 + d[3]) * dt * 3
                if d[1] < H:
                    f.add(d[0], d[1], (200, 200, 220))
                    keep.append(d)
            elif d[1] < H - 1:
                f.add(d[0], d[1], (70, 120, 220))
                f.add(d[0], d[1] - 1, (25, 45, 90))
                keep.append(d)
            else:
                f.add(d[0] - 1, H - 1, (60, 90, 150))
                f.add(d[0] + 1, H - 1, (60, 90, 150))
        self.drops = keep
        lab = f"{prob}%" if prob is not None else ""
        tw = text_w(now.strftime("%H:%M"))
        clock_big(f, now, (200, 215, 255), x=max((W - tw) // 2, min(W - tw, text_w(lab, SMALL) + 3)))
        if lab:
            f.text(lab, 0, 0, (120, 160, 255), SMALL, (0, 0, 0))


@reg("wiatr")
class Wind(Clock):
    """Wiatr z Open-Meteo: smugi lecą z prawdziwą prędkością i z prawdziwego kierunku, obok km/h i skąd wieje."""

    DIRS = ["PN", "PN-WS", "WSCH", "PD-WS", "PD", "PD-ZA", "ZACH", "PN-ZA"]

    def __init__(self):
        self.p = [[random.uniform(0, W), random.uniform(0, H)] for _ in range(70)]

    def draw(self, f, now, t, dt):
        m = NET.get("meteo")
        spd, deg = (m["current"]["wind_speed_10m"], m["current"]["wind_direction_10m"]) if m else (10, 270)
        vx = -math.sin(math.radians(deg)) * (4 + spd * 1.6)
        vy = math.cos(math.radians(deg)) * (1 + spd * 0.08)
        for q in self.p:
            q[0] += vx * dt * (0.7 + 0.6 * noise1(q[1] * 3 + t))
            q[1] += vy * dt + math.sin(t * 2 + q[0] * 0.1) * dt
            q[0] %= W
            q[1] %= H
            n = max(2, int(abs(vx) * 0.12))
            for k in range(n):
                f.add(q[0] - vx / abs(vx or 1) * k, q[1], mul((120, 170, 220), (1 - k / n) * 0.8))
        s1 = f"{round(spd)} KM/H"
        if NARROW and page(t, 2):
            clock_big(f, now)
            return
        f.text(s1, 1, 0, (230, 230, 255), SMALL, (0, 0, 0))
        f.text(self.DIRS[round(deg / 45) % 8], 1, 6, (130, 190, 255), SMALL, (0, 0, 0))
        if not NARROW:
            clock_big(f, now, x=W - text_w(now.strftime("%H:%M")))


@reg("termometr")
class Thermo(Clock):
    """Termometr rtęciowy od -20 do +40°C: temperatura teraz, odczuwalna i wilgotność (Open-Meteo)."""

    def draw(self, f, now, t, dt):
        m = NET.get("meteo")
        if not m:
            return loading(f, t, "meteo", "termometr")
        c = m["current"]
        temp = c["temperature_2m"]
        info = [f"{round(temp)}° ODCZ {round(c['apparent_temperature'])}°", f"WILG {c['relative_humidity_2m']}%",
                now.strftime("%H:%M")]
        if NARROW:
            f.text(info[page(t, 3, 4)], 0, 0, (220, 220, 230), SMALL)
        else:
            both = info[0] + " " + info[1]
            if text_w(both, SMALL) > W - text_w(info[2], SMALL) - 4:
                both = info[page(t, 2, 4)]
            f.text(both, 0, 0, (220, 220, 230), SMALL)
            small_time(f, now, c=(150, 150, 170))
        x_of = lambda v: 8 + (v + 20) / 60 * (W - 12)
        disc(f, 4, 8.5, 3, temp_color(temp))
        for x in range(7, W - 3):
            f.set(x, 6, (45, 45, 55))
            f.set(x, 10, (45, 45, 55))
            v = (x - 8) / (W - 12) * 60 - 20
            if x <= x_of(temp):
                glow = 0.85 + 0.15 * math.sin(x * 0.4 - t * 4)
                for y in (7, 8, 9):
                    f.set(x, y, mul(temp_color(v), glow))
            if abs(v % 10) < 0.3 or abs(v % 10 - 10) < 0.3:
                f.set(x, 11, (200, 200, 200) if abs(v) < 1 else (80, 80, 90))
        for y in (7, 8, 9):
            f.set(W - 3, y, (45, 45, 55))


@reg("smog")
class Smog(Clock):
    """Jakość powietrza (Open-Meteo): PM2.5 i indeks EAQI; im gorzej, tym gęstszy brunatny smog nad miastem."""

    LEVELS = [(20, "B. DOBRE", (0, 230, 120)), (40, "DOBRE", (130, 230, 0)), (60, "UMIARK.", (255, 220, 0)),
              (80, "ZŁE", (255, 120, 0)), (100, "B. ZŁE", (255, 30, 30)), (9999, "FATALNE", (190, 0, 190))]

    def __init__(self):
        rnd = random.Random(3)
        self.b = []
        x = 0
        while x < W:
            w = rnd.randint(5, 11)
            self.b.append((x, w, rnd.randint(4, 8), rnd.random()))
            x += w + rnd.randint(0, 2)

    def draw(self, f, now, t, dt):
        a = NET.get("air")
        if not a:
            return loading(f, t, "air", "powietrze")
        cur = a["current"]
        pm, aqi = cur.get("pm2_5") or 0, cur.get("european_aqi") or 0
        dens = clamp(pm / 60)
        for y in range(H):
            for x in range(W):
                f.px[y][x] = lerp((5, 10, 30), (40, 30, 15), dens * y / H)
        for bx, bw, bh, ph in self.b:
            for x in range(bx, bx + bw):
                for y in range(H - bh, H):
                    lit = (x + y) % 2 == 0 and y % 2 == 0 and hash1(x * 31 + y * 7 + int(ph * 99)) > 0.6
                    f.set(x, y, (120, 100, 40) if lit else (18, 18, 24))
        for y in range(H):
            for x in range(W):
                n = noise2(x * 0.06 - t * 0.3, y * 0.4 + t * 0.1)
                f.add(x, y, mul((110, 90, 60), dens * n * 0.9))
        name, col = next((nm, c) for lim, nm, c in self.LEVELS if aqi <= lim)
        if NARROW:
            [lambda: f.text(f"PM2.5 {pm:.0f}", 0, 0, (230, 230, 230), SMALL, (0, 0, 0)),
             lambda: f.text(name, 0, 0, col, SMALL, (0, 0, 0)),
             lambda: small_time(f, now, x=0)][page(t, 3, 4)]()
            return
        pm_s = f"PM2.5 {pm:.0f}"
        f.text(pm_s, 0, 0, (230, 230, 230), SMALL, (0, 0, 0))
        f.text(name, text_w(pm_s, SMALL) + 5, 0, col, SMALL, (0, 0, 0))
        small_time(f, now)


@reg("kursy")
class Rates(Clock):
    """Kursy walut NBP (tabela A) przewijane jak na giełdzie; ▲ zielony = kurs wyższy niż wczoraj, ▼ czerwony = niższy."""

    CODES = ["EUR", "USD", "CHF", "GBP", "JPY", "CZK", "NOK", "SEK", "DKK", "HUF", "UAH", "CNY", "CAD", "AUD"]

    def draw(self, f, now, t, dt):
        d = NET.get("nbp")
        if not d:
            return loading(f, t, "nbp", "kursy NBP")
        cur = {r["code"]: r["mid"] for r in d[-1]["rates"]}
        old = {r["code"]: r["mid"] for r in d[0]["rates"]}
        segs = []
        for code in self.CODES:
            if code in cur:
                v, o = cur[code], old.get(code, cur[code])
                arrow, col = ("▲", (0, 230, 90)) if v > o else ("▼", (255, 50, 40)) if v < o else ("=", (150, 150, 150))
                segs += [(code, (255, 190, 40)), (f"{v:.4f}".replace(".", ","), (240, 240, 240)), (arrow + "   ", col)]
        hm = now.strftime("%H:%M")
        bw = text_w("NBP", SMALL) + 2 if NARROW else text_w(hm, SMALL) + 2
        scroll_segs(f, segs, t, 26, 0, bw + 2)
        f.rect(0, 0, bw, 11, (0, 25, 70))
        f.text("NBP", (bw + 1 - text_w("NBP", SMALL)) // 2, 3 if NARROW else 0, (255, 210, 60), SMALL)
        if not NARROW:
            f.text(hm, 1, 6, (200, 200, 220), SMALL)


@reg("zloto")
class Gold(Clock):
    """Cena złota NBP (zł za gram) z połyskiem i wykresem z 30 ostatnich notowań."""

    def draw(self, f, now, t, dt):
        g = NET.get("gold")
        if not g:
            return loading(f, t, "gold", "złoto")
        prices = [x["cena"] for x in g]
        s = f"{prices[-1]:.2f} zł".replace(".", ",")
        chart_only = NARROW and page(t, 2, 6) == 1
        sweep = (t * 40) % 160 - 20 if not chart_only else -99
        if not chart_only:
            for x, y in text_px(s, 0, 0, TXT):
                f.set(x, y, lerp((200, 140, 20), (255, 255, 200), clamp(1 - abs(x - sweep) / 8)))
            if NARROW:
                return
        lo, hi = min(prices), max(prices)
        x0, n = (0 if NARROW else 62), len(prices)
        for x in range(x0, W):
            p = (x - x0) / (W - 1 - x0) * (n - 1)
            i = min(int(p), n - 2)
            v = prices[i] + (prices[i + 1] - prices[i]) * (p - i)
            y = 10.5 - (v - lo) / max(hi - lo, 0.01) * 9
            for yy in range(int(y) + 1, 12):
                f.set(x, yy, (40, 28, 0))
            f.set(x, y, (255, 200, 50))
        f.add(W - 1, 10.5 - (prices[-1] - lo) / max(hi - lo, 0.01) * 9, mul((255, 255, 255), 0.5 + 0.5 * math.sin(t * 6)))


@reg("krypto")
class Crypto(Clock):
    """Kryptowaluty z Binance: BTC, ETH, SOL, DOGE w dolarach i zmiana 24 h; w tle wykres BTC z 5 dni."""

    def draw(self, f, now, t, dt):
        tick, kl = NET.get("crypto"), NET.get("klines")
        if kl:
            lo, hi = min(kl), max(kl)
            for x in range(W):
                v = kl[int(x / W * len(kl))]
                y = 11 - (v - lo) / max(hi - lo, 1) * 10
                for yy in range(int(y), 12):
                    f.set(x, yy, (22, 12, 0))
                f.set(x, y, (70, 40, 0))
        if not tick:
            return loading(f, t, "crypto", "krypto")
        segs = []
        for s in tick:
            p, pct = float(s["lastPrice"]), float(s["priceChangePercent"])
            ps = f"{p:,.0f}".replace(",", " ") if p >= 1000 else f"{p:.2f}" if p >= 1 else f"{p:.4f}"
            segs += [(s["symbol"].replace("USDT", ""), (255, 160, 20)), (f"${ps}", (240, 240, 240)),
                     (f"{pct:+.1f}%   ", (0, 230, 90) if pct >= 0 else (255, 50, 40))]
        scroll_segs(f, segs, t, 26)


@reg("iss")
class ISS(Clock):
    """Mapa świata z granicą dnia i nocy, a na niej Międzynarodowa Stacja Kosmiczna na żywo i jej ślad (wheretheiss.at)."""

    def __init__(self):
        self.trail, self.ts = [], None

    def draw(self, f, now, t, dt):
        world_map(f, dtm.datetime.now().astimezone(), 0.8)
        hx, hy = map_xy(LAT, LON)
        f.set(hx, hy, (255, 40, 40) if int(t * 2) % 2 else (120, 0, 0))
        d = NET.get("iss")
        if not d:
            return
        if d["timestamp"] != self.ts:
            self.ts = d["timestamp"]
            self.trail = (self.trail + [(d["latitude"], d["longitude"])])[-80:]
        for i, (la, lo) in enumerate(self.trail[:-1]):
            f.add(*map_xy(la, lo), mul((255, 200, 80), 0.15 + 0.5 * i / len(self.trail)))
        x, y = map_xy(d["latitude"], d["longitude"])
        for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            f.add(x + ox, y + oy, (90, 90, 90))
        f.set(x, y, (255, 255, 255))
        info = ["ISS", f"{d['altitude']:.0f} KM", f"{d['velocity']:.0f} KM/H"][int(t / 3) % 3]
        f.text(info, 1, 0, (255, 230, 140), SMALL, (0, 0, 0))


@reg("kosmonauci")
class Astronauts(Clock):
    """Ilu ludzi jest teraz w kosmosie (open-notify): ludziki w nieważkości, a potem przewijają się ich nazwiska."""

    SUIT = [".o.", "www", ".w.", "w.w"]

    def draw(self, f, now, t, dt):
        for i in range(40):
            f.set(hash1(i) * W, hash1(i + 99) * H, mul((120, 120, 160), 0.3 + 0.7 * max(0, math.sin(t * 1.5 + i))))
        d = NET.get("astros")
        if not d:
            return loading(f, t, "astros", "kosmos")
        n = d["number"]
        for i in range(n):
            x = (i * 37 + t * (3 + i % 3)) % (W + 6) - 3
            y = 4 + 3.5 * math.sin(t * 0.6 + i * 1.7)
            sprite(f, self.SUIT, x, y, {"o": (255, 220, 180), "w": (230, 230, 240)})
        names = "   ".join(f"{p['name']} ({p['craft']})" for p in d["people"])
        tw = text_w(names, TXT)
        scene, speed = 12, 35
        ph = t % (scene + scroll_time(tw + W, speed))
        if ph < scene:
            x = 4 + text_w(str(n))
            if x + text_w("KOSMOSIE", SMALL) <= W:
                f.text(str(n), 2, 1, (255, 255, 255), BIG, (0, 0, 20))
                f.text("OSÓB W", x, 0, (150, 200, 255), SMALL, (0, 0, 20))
                f.text("KOSMOSIE", x, 6, (150, 200, 255), SMALL, (0, 0, 20))
            else:  # wąski panel: liczba małą czcionką, żeby zmieścić „W KOSMOSIE”
                f.text(str(n), 0, 0, (255, 255, 255), SMALL, (0, 0, 20))
                f.text("OSÓB", text_w(str(n), SMALL) + 4, 0, (150, 200, 255), SMALL, (0, 0, 20))
                f.text("W KOSMOSIE", 0, 6, (150, 200, 255), SMALL, (0, 0, 20))
            if not NARROW:
                small_time(f, now, c=(120, 120, 150))
        else:
            f.text(names, W - scroll_px(ph - scene, speed), 0, (255, 240, 200), TXT, (0, 0, 0))


@reg("trzesienia")
class Quakes(Clock):
    """Trzęsienia ziemi z ostatniej doby (USGS, M2.5+): pulsujące kręgi na mapie świata; największe opisane w rogu."""

    def draw(self, f, now, t, dt):
        world_map(f, dtm.datetime.now().astimezone(), 0.45)
        q = NET.get("quakes")
        if not q:
            return loading(f, t, "quakes", "trzęsienia")
        for i, (lon, lat, mag, place, tm) in enumerate(q):
            x, y = map_xy(lat, lon)
            col = (255, 230, 0) if mag < 4 else (255, 130, 0) if mag < 5 else (255, 30, 30)
            ph = (t * 0.8 + hash1(i)) % 1
            r = ph * mag * 1.2
            for k in range(16):
                a = k * math.pi / 8
                f.add(x + math.cos(a) * r, y + math.sin(a) * r * 0.5, mul(col, (1 - ph) * 0.5))
            f.set(x, y, col)
        big = max(q, key=lambda e: e[2])
        info = f"M{big[2]:.1f}  {len(q)} W 24H"
        if text_w(info, SMALL) > W - 1:
            info = [f"M{big[2]:.1f}", f"{len(q)} W 24H"][page(t, 2, 4)]
        f.text(info, 1, 0, (255, 255, 255), SMALL, (0, 0, 0))
        bx, by = map_xy(big[1], big[0])
        f.add(bx, by, mul((255, 255, 255), 0.5 + 0.5 * math.sin(t * 8)))


@reg("zorza")
class Aurora(Clock):
    """Zorza polarna o sile z prawdziwego indeksu Kp (NOAA SWPC): Kp 0–2 ledwo widać, 5+ = burza geomagnetyczna."""

    def __init__(self):
        rnd = random.Random(5)
        self.stars = [(rnd.randrange(W), rnd.randrange(8), rnd.random() * 6) for _ in range(40)]
        self.trees = [int(9 + 2 * rnd.random() - (1.5 if rnd.random() < 0.3 else 0)) for _ in range(W)]

    def draw(self, f, now, t, dt):
        kp = NET.get("kp")
        kpv = kp if kp is not None else 2.0
        s = clamp(0.5 + kpv / 7)
        for sx, sy, ph in self.stars:
            f.set(sx, sy, mul((140, 140, 170), 0.3 + 0.3 * math.sin(t * 2 + ph)))
        for x in range(W):
            amp = s * (0.3 + 0.7 * noise1(x * 0.05 + t * 0.15)) * (0.5 + 0.5 * noise1(x * 0.13 - t * 0.23 + 5))
            base = 8 - noise1(x * 0.04 + t * 0.1) * 2
            length = 2 + amp * 10
            ray = 0.6 + 0.4 * noise1(x * 0.9 + t * 2)
            for y in range(H):
                d = base - y
                if 0 <= d <= length:
                    k = (1 - d / length) ** 0.7 * amp * ray * 2.4
                    f.add(x, y, mul(lerp((40, 255, 120), (170, 40, 220), clamp(d / length * s * 1.3)), k))
        for x in range(W):
            for y in range(self.trees[x], H):
                f.set(x, y, (0, 4, 2))
        f.text(f"KP {kpv:.1f}" if kp is not None else "KP ?", 1, 0, (160, 255, 190), SMALL, (0, 0, 0))
        small_time(f, now, c=(180, 180, 200))


@reg("bloki")
class Blocks(Clock):
    """Bitcoin na żywo (mempool.space): numer ostatniego bloku; gdy zostanie wykopany nowy, spada kolejny klocek."""

    def __init__(self):
        self.last, self.drop_t = None, -99

    def cube(self, f, x, y, k=1.0):
        for yy in range(6):
            for xx in range(6):
                c = (247, 147, 26) if yy > 0 and xx < 5 else (255, 200, 110) if yy == 0 else (150, 80, 10)
                f.set(x + xx, y + yy, mul(c, k))

    def draw(self, f, now, t, dt):
        h = NET.get("height")
        if h is None:
            return loading(f, t, "height", "bitcoin")
        if self.last is not None and h != self.last:
            self.drop_t = t
        self.last = h
        p = clamp((t - self.drop_t) / 0.9)
        shift = 8 * (1 - p) if p < 1 else 0
        for i in range(1, 9):
            self.cube(f, W - 8 - i * 8 + shift, 6, 0.9 - i * 0.08)
        y = -6 + 12 * min(1, p ** 2) if p < 1 else 6
        self.cube(f, W - 8, y, 1.0)
        f.text(f"#{h}", 1, 0, (255, 170, 40), TXT, (0, 0, 0))


@reg("hackernews")
class HackerNews(Clock):
    """Najpopularniejsze tytuły z Hacker News przewijane jeden po drugim; z lewej pomarańczowe logo Y."""

    def draw(self, f, now, t, dt):
        titles = NET.get("hn")
        f.rect(0, 0, 11, 11, (255, 102, 0))
        f.text("Y", 3, -1, (255, 255, 255), TXT)
        if not titles:
            return
        segs = []
        for s in titles:
            segs += [(s, (240, 240, 240)), ("  |  ", (255, 102, 0))]
        scroll_segs(f, segs, t, 30, 0, 13)


@reg("wiadomosci")
class News(Clock):
    """Najnowsze nagłówki TVN24 (RSS) jak pasek w telewizji informacyjnej – z polskimi znakami i zegarem."""

    def draw(self, f, now, t, dt):
        titles = NET.get("news")
        hm = now.strftime("%H:%M")
        bw = 2 if NARROW else max(text_w(hm, SMALL), text_w("NEWS", SMALL)) + 2  # wąski panel: sam czerwony pasek
        f.rect(0, 0, bw, 11, (170, 0, 0))
        if not NARROW:
            f.text(hm, (bw + 1 - text_w(hm, SMALL)) // 2, 0, (255, 255, 255), SMALL)
            f.text("NEWS", (bw + 1 - text_w("NEWS", SMALL)) // 2, 6, (255, 200, 200), SMALL)
        if not titles:
            return
        segs = []
        for s in titles:
            segs += [(s, (240, 240, 240)), ("  |  ", (220, 30, 30))]
        scroll_segs(f, segs, t, 30, 0, bw + 2)


@reg("imieniny")
class NameDays(Clock):
    """Dzisiejsze imieniny (nameday.abalin.net): imiona płyną nad kwitnącymi kwiatkami."""

    def draw(self, f, now, t, dt):
        for i in range(14):
            x = 4 + i * 8.5
            hgt = 2 + (i % 3)
            for y in range(H - hgt, H):
                f.set(x, y, (20, 120, 30))
            col = hsv(hash1(i + 3), 0.8, 1)
            k = 0.6 + 0.4 * math.sin(t * 1.5 + i)
            cy = H - hgt - 1
            for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                f.set(x + ox, cy + oy, mul(col, k))
            f.set(x, cy, (255, 230, 60))
        names = NET.get("names")
        if not names:
            return loading(f, t, "names", "imieniny")
        scroll_segs(f, [("Imieniny:", (255, 180, 220)), (names, (255, 255, 255)), ("   " + now.strftime("%H:%M"), (130, 130, 160))],
                    t, 24, -2)


@reg("rakieta")
class Launch(Clock):
    """Odliczanie T- do najbliższego startu rakiety na świecie (The Space Devs); rakieta dymi na wyrzutni."""

    ROCKET = ["..r..", ".www.", ".wbw.", ".www.", ".www.", ".www.", ".www.", "rwwwr", "r...r"]

    def draw(self, f, now, t, dt):
        d = NET.get("launch")
        real = dtm.datetime.now(dtm.timezone.utc)
        up = -2.0
        if d:
            nxt = None
            for name, net in d:
                when = dtm.datetime.fromisoformat(net.replace("Z", "+00:00"))
                if when > real - dtm.timedelta(hours=1):
                    nxt = (name, when)
                    break
        if not d or not nxt:
            sprite(f, self.ROCKET, 3, 2, {"r": (220, 40, 30), "w": (230, 230, 230), "b": (60, 120, 255)})
            return loading(f, t, "launch", "start rakiety")
        name, when = nxt
        left = (when - real).total_seconds()
        if left < 0:
            up = -(-left) * 3
        for i in range(10):
            ph = (t * 0.7 + i * 0.1) % 1
            k = 0.5 if left > 0 else 1.0
            f.add(5 + (hash1(i) - 0.5) * 8 * ph, H - 1 - ph * 3, mul((160, 160, 170), (1 - ph) * k))
        if left < 0:
            for y in range(int(11 + up), H):
                f.add(5, y, (255, 140, 0))
        sprite(f, self.ROCKET, 3, 2 + up, {"r": (220, 40, 30), "w": (230, 230, 230), "b": (60, 120, 255)})
        tw = text_w(name, TXT)
        ph = t % (14 + scroll_time(tw + W, 35))
        if ph < 14:
            if left > 0:
                dd, rest = divmod(int(left), 86400)
                hh, mm, ss = rest // 3600, rest % 3600 // 60, rest % 60
                d_ = f"{dd}d " if dd else ""
                opts = [f"T-{d_}{hh:02d}:{mm:02d}:{ss:02d}", f"{d_}{hh:02d}:{mm:02d}", f"{dd}d {hh}h" if dd else f"{hh}:{mm:02d}"]
                s = next((o for o in opts if 14 + text_w(o, TXT) <= W), opts[-1])
            else:
                s = "START!"
            f.text(s, 14, 0, (255, 255, 255))
        else:
            f.text(name, W - scroll_px(ph - 14, 35), 0, (255, 220, 150))


@reg("zart")
class Joke(Clock):
    """Suchar z icanhazdadjoke.com (po angielsku) przewijany obok mrugającej buźki; nowy co 5 minut."""

    def draw(self, f, now, t, dt):
        disc(f, 5, 5.5, 5.2, (255, 210, 0))
        blink = (t % 4) < 0.15
        for ex in (3, 7):
            f.set(ex, 4 if not blink else 5, (40, 20, 0))
            if not blink:
                f.set(ex, 3, (40, 20, 0))
        for mx, my in ((2, 7), (3, 8), (4, 8), (5, 8), (6, 8), (7, 8), (8, 7)):
            f.set(mx, my, (120, 40, 0))
        j = NET.get("joke")
        if not j:
            return
        scroll_segs(f, [(j, (255, 255, 255))], t, 30, 0, 13, gap=40)


@reg("slonce")
class SunArc(Clock):
    """Dzisiejszy wschód i zachód słońca (Open-Meteo): łuk dnia, słońce w obecnym miejscu, długość dnia."""

    def draw(self, f, now, t, dt):
        m = NET.get("meteo")
        if not m:
            return loading(f, t, "meteo", "słońce")
        i = meteo_day(m)
        rise, sset = m["daily"]["sunrise"][i], m["daily"]["sunset"][i]
        mins = lambda s: int(s[11:13]) * 60 + int(s[14:16])
        r, s_ = mins(rise), mins(sset)
        ln = meteo_now(m)
        cur = ln.hour * 60 + ln.minute + ln.second / 60
        frac = (cur - r) / max(1, s_ - r)
        x0, x1 = (4, W - 5) if NARROW else (29, W - 30)
        day = 0 <= frac <= 1
        sky = (0, 15, 45) if day else (0, 0, 8)
        for y in range(H - 1):
            for x in range(W):
                f.px[y][x] = mul(sky, 1 - y / H * 0.5)
        for x in range(W):
            f.set(x, 11, (10, 60, 10) if day else (2, 12, 2))
        for k in range(60):
            a = k / 59
            f.set(x0 + (x1 - x0) * a, 10 - math.sin(math.pi * a) * 8, (70, 60, 20))
        if day:
            disc(f, x0 + (x1 - x0) * frac, 10 - math.sin(math.pi * frac) * 8, 1.8, (255, 220, 60))
        left = (r - cur) % 1440
        dl = s_ - r
        if NARROW:
            lab = [("WSCH. " + rise[11:16], (255, 190, 80)), ("ZACH. " + sset[11:16], (255, 120, 60)),
                   (now.strftime("%H:%M"), (230, 230, 230))][page(t, 3, 4)]
            f.text(lab[0], (W - text_w(lab[0], SMALL)) // 2, 0, lab[1], SMALL, (0, 0, 0))
            return
        f.text(rise[11:16], 1, 6, (255, 190, 80), SMALL)
        f.text(sset[11:16], W - text_w(sset[11:16], SMALL), 6, (255, 120, 60), SMALL)
        if day:
            f.text(f"{dl // 60}:{dl % 60:02d}", 1, 0, (200, 200, 150), SMALL)
        else:  # nocą zamiast długości dnia: ile do wschodu
            f.text(f"WSCHÓD ZA {int(left // 60)}:{int(left % 60):02d}", 1, 0, (150, 150, 200), SMALL, (0, 0, 0))
        small_time(f, now, c=(230, 230, 230))


@reg("uv")
class UV(Clock):
    """Indeks UV teraz i maksymalny dziś (Open-Meteo) na kolorowej skali 0–11+; słońce ma tyle promieni, ile UV."""

    def draw(self, f, now, t, dt):
        m = NET.get("meteo")
        if not m:
            return loading(f, t, "meteo", "UV")
        uv = m["hourly"]["uv_index"][meteo_idx(m)] or 0
        uvmax = m["daily"]["uv_index_max"][meteo_day(m)] or 0
        col = lambda v: (0, 200, 60) if v < 3 else (255, 220, 0) if v < 6 else (255, 130, 0) if v < 8 else (240, 20, 20) if v < 11 else (170, 40, 220)
        lvl = "NISKI" if uv < 3 else "UMIARK." if uv < 6 else "WYSOKI" if uv < 8 else "B.WYSOKI" if uv < 11 else "EKSTREM."
        disc(f, 8, 6, 2.6, (255, 215, 50))
        for i in range(max(1, round(uv * 1.5))):
            a = i / max(1, round(uv * 1.5)) * 2 * math.pi + t * 0.4
            f.add(8 + math.cos(a) * 4.8, 6 + math.sin(a) * 4.8, (255, 150, 20))
        a, b = f"UV {uv:.1f} {lvl}", f"MAX {uvmax:.1f}"
        if NARROW:
            txt = [(f"UV {uv:.1f}", col(uv)), (lvl, col(uv)), (b, col(uvmax))][page(t, 3, 4)]
            f.text(txt[0], min(18, W - text_w(txt[0], SMALL)), 0, txt[1], SMALL)
        elif 18 + text_w(a, SMALL) + 5 + text_w(b, SMALL) <= W:
            f.text(a, 18, 0, col(uv), SMALL)
            f.text(b, W - text_w(b, SMALL), 0, col(uvmax), SMALL)
        else:
            txt, c_ = [(a, col(uv)), (b, col(uvmax))][page(t, 2, 4)]
            f.text(txt, 18, 0, c_, SMALL)
        for x in range(18, W):
            v = (x - 18) / (W - 18) * 12
            for y in (8, 9, 10):
                f.set(x, y, mul(col(v), 0.55))
        xu = 18 + clamp(uv / 12) * (W - 19)
        xm = 18 + clamp(uvmax / 12) * (W - 19)
        for y in range(6, 12):
            f.set(xu, y, (255, 255, 255) if int(t * 3) % 2 or y > 7 else (0, 0, 0))
        f.set(xm, 11, (255, 255, 255))
        f.set(xm, 7, (255, 255, 255))


@reg("barometr")
class Barometer(Clock):
    """Ciśnienie z Open-Meteo i trend z 3 h: wskazówka na skali starego barometru (burza – deszcz – zmiennie – ładnie – sucho)."""

    ZONES = [(990, "BURZA", (150, 0, 200)), (1005, "DESZCZ", (0, 110, 255)), (1020, "ZMIENNIE", (140, 140, 140)),
             (1035, "ŁADNIE", (255, 200, 0)), (9999, "SUCHO", (255, 110, 0))]

    def draw(self, f, now, t, dt):
        m = NET.get("meteo")
        if not m:
            return loading(f, t, "meteo", "barometr")
        p = m["current"]["pressure_msl"]
        hp = m["hourly"]["pressure_msl"]
        i0 = meteo_idx(m)
        tr = p - (hp[max(0, i0 - 3)] or p)
        x_of = lambda v: clamp((v - 970) / 80) * (W - 1)
        for x in range(W):
            v = 970 + x / (W - 1) * 80
            c = next(c for lim, _, c in self.ZONES if v <= lim)
            for y in (9, 10, 11):
                f.set(x, y, mul(c, 0.45))
            if int(v) % 10 == 0 and abs(v - int(v)) < 0.7:
                f.set(x, 8, (90, 90, 90))
        name, col = next((n, c) for lim, n, c in self.ZONES if p <= lim)
        arrow = "↑" if tr > 0.7 else "↓" if tr < -0.7 else "→"
        if NARROW:
            txt = [(f"{p:.0f} HPA {arrow}", (230, 230, 230)), (name, col), (now.strftime("%H:%M"), (150, 150, 170))][page(t, 3, 4)]
            f.text(txt[0], 0, 0, txt[1], SMALL)
        else:
            ptxt = f"{p:.0f} HPA {arrow}"
            f.text(ptxt, 0, 0, (230, 230, 230), SMALL)
            nx = text_w(ptxt, SMALL) + 5
            fits = nx + text_w(name, SMALL) + 4 <= W - text_w(now.strftime("%H:%M"), SMALL)
            if fits or page(t, 2, 4) == 0:
                f.text(name, nx, 0, col, SMALL)
            if fits or page(t, 2, 4) == 1:
                small_time(f, now, c=(150, 150, 170))
        wig = math.sin(t * 25) * 0.8 if (t % 10) < 0.8 else 0
        x = x_of(p) + wig
        for y in range(6, 12):
            f.set(x, y, (255, 255, 255))

# ================================================================ STYLE ZEGARÓW
@reg("binarny")
class Binary(Clock):
    """Zegar binarny BCD: kolumny to cyfry HH MM SS, zapalony kwadrat = bit (8-4-2-1); obok zwykły czas do sprawdzenia."""

    def draw(self, f, now, t, dt):
        digs = now.strftime("%H%M%S")
        cols = [(255, 60, 60), (60, 255, 90), (70, 140, 255)]
        tw = text_w(now.strftime("%H:%M:%S"), TXT)
        x = (W - (6 * 5 + 2 * 4 + (0 if NARROW else 6 + tw))) // 2
        for i, d in enumerate(digs):
            v = int(d)
            for b in range(4):
                on = v >> (3 - b) & 1
                c = cols[i // 2] if on else (18, 18, 24)
                f.rect(x, b * 3, x + 3, b * 3 + 1, c)
            x += 5 + (4 if i in (1, 3) else 0)
        if not NARROW:
            f.text(now.strftime("%H:%M:%S"), x + 6, 0, (200, 200, 210))


@reg("analogowy")
class Analog(Clock):
    """Klasyczne tarcze ze wskazówkami: z lewej godzina, z prawej sekundnik; pośrodku cyfrowy czas i data."""

    def dial(self, f, cx, cy, hands):
        for k in range(12):
            a = k * math.pi / 6
            f.set(cx + math.sin(a) * 5.3, cy - math.cos(a) * 5.3, (120, 120, 140) if k % 3 else (230, 230, 255))
        for ang, ln, c in hands:
            f.line(cx - 0.5, cy - 0.5, cx - 0.5 + math.sin(ang) * ln, cy - 0.5 - math.cos(ang) * ln, c)
        f.set(cx - 0.5, cy - 0.5, (255, 255, 255))

    def draw(self, f, now, t, dt):
        s = now.second + now.microsecond / 1e6
        m = now.minute + s / 60
        h = now.hour % 12 + m / 60
        self.dial(f, 6.5, 6.5, [(h / 12 * 2 * math.pi, 3, (255, 200, 80)), (m / 60 * 2 * math.pi, 4.6, (200, 220, 255)),
                                (s / 60 * 2 * math.pi, 5, (255, 40, 40))])
        self.dial(f, W - 6.5, 6.5, [(s / 60 * 2 * math.pi, 5, (255, 40, 40))])
        if NARROW:
            clock_big(f, now, x=(W - text_w(now.strftime("%H:%M"))) // 2)
            return
        clock_big(f, now, x=14)
        f.text(f"{PL_DAYS[now.weekday()][:3]} {now.day:02d}.{now.month:02d}", 18 + text_w(now.strftime("%H:%M")), 0,
               (170, 190, 255))


def pl_time_words(now):
    H_NOM = ["dwunasta", "pierwsza", "druga", "trzecia", "czwarta", "piąta", "szósta", "siódma", "ósma", "dziewiąta",
             "dziesiąta", "jedenasta"]
    H_LOC = ["dwunastej", "pierwszej", "drugiej", "trzeciej", "czwartej", "piątej", "szóstej", "siódmej", "ósmej",
             "dziewiątej", "dziesiątej", "jedenastej"]
    N = ["", "minuta", "dwie", "trzy", "cztery", "pięć", "sześć", "siedem", "osiem", "dziewięć", "dziesięć", "jedenaście",
         "dwanaście", "trzynaście", "czternaście", "kwadrans", "szesnaście", "siedemnaście", "osiemnaście",
         "dziewiętnaście", "dwadzieścia"]
    num = lambda n: N[n] if n <= 20 else "dwadzieścia " + N[n - 20].replace("minuta", "jeden")
    h, m = now.hour % 12, now.minute
    if m == 0:
        return f"punkt {H_NOM[h]}"
    if m == 30:
        return f"wpół do {H_LOC[(h + 1) % 12]}"
    if m < 30:
        return f"{num(m)} po {H_LOC[h]}"
    r = 60 - m
    return f"za {'minutę' if r == 1 else num(r)} {H_NOM[(h + 1) % 12]}"


@reg("slownie")
class Words(Clock):
    """Godzina słownie, tak jak się mówi: „za kwadrans dziewiąta”, „dwadzieścia po ósmej”, „wpół do trzeciej”."""

    def draw(self, f, now, t, dt):
        s = pl_time_words(now)
        tw = text_w(s, TXT)
        x0 = (W - tw) // 2 if tw <= W else W - scroll_px(t, 25) % (tw + W)
        for x, y in text_px(s, x0, 0, TXT):
            f.set(x, y, hsv(x / 240 + t * 0.05, 0.6, 1))
        sec = now.second + now.microsecond / 1e6
        for x in range(int(sec / 60 * W)):
            f.set(x, 11, (40, 40, 70))


def roman(n):
    out = ""
    for v, s in ((50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out += s
            n -= v
    return out or "N"


@reg("rzymski")
class Roman(Clock):
    """Godzina cyframi rzymskimi, złotem na marmurze między kolumnami (N = nulla, czyli zero)."""

    def draw(self, f, now, t, dt):
        for y in range(H):
            for x in range(W):
                v = noise2(x * 0.15, y * 0.5 + x * 0.05)
                vein = 1 - min(1, abs(v - 0.5) * 12)
                f.px[y][x] = lerp((22, 20, 24), (70, 65, 75), vein * 0.8)
        for cx in (1, W - 6):
            f.rect(cx, 0, cx + 4, 0, (150, 140, 120))
            f.rect(cx, 11, cx + 4, 11, (150, 140, 120))
            for x in range(cx, cx + 5):
                for y in range(1, 11):
                    f.set(x, y, (110, 105, 95) if (x - cx) % 2 == 0 else (70, 66, 60))
        s = f"{roman(now.hour)}:{roman(now.minute)}"
        if text_w(s, TXT) <= W - 14:
            pts = text_px(s, (W - text_w(s, TXT)) // 2, 0, TXT)
        else:  # nie mieści się między kolumnami: godziny nad minutami, mniejszą czcionką
            hh, mm = roman(now.hour), roman(now.minute)
            pts = text_px(hh, (W - text_w(hh, SMALL)) // 2, 0, SMALL) + text_px(mm, (W - text_w(mm, SMALL)) // 2, 6, SMALL)
        for x, y in pts:
            f.set(x, y, lerp((200, 140, 30), (255, 240, 170), 0.5 + 0.5 * math.sin(x * 0.3 - t * 2)))


@reg("morse")
class Morse(Clock):
    """Czas nadawany alfabetem Morse'a: kropki i kreski pod cyframi, a lampka po prawej naprawdę go nadaje."""

    CODE = {"0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-", "5": ".....", "6": "-....",
            "7": "--...", "8": "---..", "9": "----."}

    def draw(self, f, now, t, dt):
        s = now.strftime("%H%M")
        u = 0.09
        seq = []
        for di, d in enumerate(s):
            for si, sym in enumerate(self.CODE[d]):
                seq.append((di, si, True, u if sym == "." else 3 * u))
                seq.append((di, si, False, u))
            seq[-1] = (di, 4, False, 3 * u)
        seq[-1] = (3, 4, False, 10 * u)
        total = sum(q[3] for q in seq)
        p, cur = t % total, None
        for q in seq:
            if p < q[3]:
                cur = q
                break
            p -= q[3]
        if NARROW:
            lw = W - 10
            hm = now.strftime("%H:%M")
            x = (lw - text_w(hm, TXT)) // 2
            for i, ch in enumerate(hm):
                di = i if i < 2 else i - 1
                f.text(ch, x, -2, (255, 230, 60) if ch != ":" and cur and cur[0] == di else (200, 200, 200))
                x += text_w(ch, TXT) + 1
            if cur:
                code = self.CODE[s[cur[0]]]
                x = (lw - sum(3 if c == "-" else 1 for c in code) - len(code) + 1) // 2
                for si, sym in enumerate(code):
                    wdt = 1 if sym == "." else 3
                    f.rect(x, 9, x + wdt - 1, 10, (255, 230, 60) if si == cur[1] and cur[2] else (90, 140, 255))
                    x += wdt + 1
        for di, d in enumerate(s if not NARROW else ""):
            cx = 2 + di * 26 + (4 if di >= 2 else 0)
            f.text(d, cx + 10, -2, (220, 220, 220))
            x = cx
            for si, sym in enumerate(self.CODE[d]):
                wdt = 1 if sym == "." else 4
                on = cur and cur[0] == di and cur[1] == si and cur[2]
                c = (255, 230, 60) if on else (90, 140, 255)
                f.rect(x, 9, x + wdt, 10, c)
                x += wdt + 2
        if not NARROW:
            f.rect(55, 4, 55, 5, (150, 150, 150))
        on = cur and cur[2]
        disc(f, W - 5, 5.5, 3.5, (255, 240, 150) if on else (40, 30, 10))


@reg("klepsydra")
class Hourglass(Clock):
    """Klepsydra minutowa: piasek sypie się z ruchomego lejka, kupka rośnie, a z nową minutą dno się otwiera."""

    def __init__(self):
        self.g = [[None] * W for _ in range(H)]
        self.acc, self.minute, self.drain = 0.0, None, 0.0

    def step(self):
        g = self.g
        for y in range(H - 2, -1, -1):
            xs = list(range(W))
            random.shuffle(xs)
            for x in xs:
                c = g[y][x]
                if c is None:
                    continue
                if g[y + 1][x] is None:
                    g[y + 1][x], g[y][x] = c, None
                else:
                    for dx in random.sample((-1, 1), 2):
                        nx = x + dx
                        if 0 <= nx < W and g[y + 1][nx] is None:
                            g[y + 1][nx], g[y][x] = c, None
                            break

    def draw(self, f, now, t, dt):
        if self.minute is not None and now.minute != self.minute:
            self.drain = 1.2
        self.minute = now.minute
        if self.drain > 0:
            self.drain -= dt
            self.g[H - 1] = [None] * W
        else:
            self.acc += dt * 14
            while self.acc >= 1:
                self.acc -= 1
                x = int(clamp(W / 2 + math.sin(t * 0.7) * (W / 2 - 8) + random.uniform(-2, 2), 0, W - 1))
                if self.g[0][x] is None:
                    self.g[0][x] = hsv(now.minute / 60 + random.uniform(-0.03, 0.03), 0.6, random.uniform(0.6, 1))
        self.step()
        for y in range(H):
            for x in range(W):
                if self.g[y][x] is not None:
                    f.px[y][x] = self.g[y][x]
        small_time(f, now, x=1)
        small_time(f, now, fmt=":%S", c=(150, 150, 170))


@reg("postep")
class Progress(Clock):
    """Paski postępu z procentami: na zmianę rok i miesiąc, a potem doba i godzina."""

    def draw(self, f, now, t, dt):
        y0 = dtm.datetime(now.year, 1, 1, tzinfo=now.tzinfo)
        y1 = dtm.datetime(now.year + 1, 1, 1, tzinfo=now.tzinfo)
        m0 = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        m1 = (m0 + dtm.timedelta(days=32)).replace(day=1)
        sec = now.hour * 3600 + now.minute * 60 + now.second + now.microsecond / 1e6
        pairs = [(("ROK", (now - y0) / (y1 - y0), (255, 140, 0)), ("MIESIĄC", (now - m0) / (m1 - m0), (0, 200, 255))),
                 (("DOBA", sec / 86400, (255, 60, 160)), ("GODZINA", (sec % 3600) / 3600, (120, 255, 80)))]
        def label(lab, pc, short, dec):
            return f"{lab[:4] + '.' if short and len(lab) > 4 else lab} {pc * 100:.{dec}f}%"

        if NARROW:
            lab, pc, col = [x for pr in pairs for x in pr][page(t, 4, 4)]
            opts = [label(lab, pc, sh, dec) for sh, dec in ((False, 1), (True, 1), (True, 0))]
            txt = next((o for o in opts if text_w(o, SMALL) <= W), opts[-1])
            f.text(txt, (W - text_w(txt, SMALL)) // 2, 0, col, SMALL)
            for x in range(W):
                k = 0.9 + 0.1 * math.sin(x * 0.3 - t * 5) if x < pc * W else 0.1
                for y in (8, 9, 10):
                    f.set(x, y, mul(col, k))
            return
        (l1, p1, c1), (l2, p2, c2) = pairs[int(t / 6) % 2]
        for sh, dec in ((False, 2), (False, 1), (True, 2), (True, 1), (True, 0)):
            s1, s2 = label(l1, p1, sh, dec), label(l2, p2, sh, dec)
            if text_w(s1, SMALL) + 6 + text_w(s2, SMALL) <= W:
                break
        f.text(s1, 0, 0, c1, SMALL)
        f.text(s2, W - text_w(s2, SMALL), 0, c2, SMALL)
        for (p, c, ya) in ((p1, c1, 7), (p2, c2, 10)):
            for x in range(W):
                on = x < p * W
                k = 0.9 + 0.1 * math.sin(x * 0.3 - t * 5) if on else 0.1
                f.set(x, ya, mul(c, k))
                f.set(x, ya + 1, mul(c, k * 0.7))


@reg("kalendarz")
class Calendar(Clock):
    """Kartka z kalendarza: dzień miesiąca, dzień tygodnia, miesiąc, numer tygodnia i na zmianę godzina."""

    def draw(self, f, now, t, dt):
        f.rect(0, 0, 16, 11, (170, 165, 150))
        f.rect(0, 0, 16, 1, (200, 30, 30))
        f.draw(text_px(f"{now.day:02d}", 2, 2), (120, 0, 0))
        f.rect(0, 2, 0, 2, (170, 165, 150))
        wd = PL_DAYS[now.weekday()]
        if NARROW:
            lines = [(wd if text_w(wd, TXT) <= W - 20 else wd[:3], (255, 80, 80) if now.weekday() == 6 else (230, 230, 230)),
                     (PL_MONTHS[now.month - 1][:3] + ".", (255, 200, 120)), (f"t.{now.isocalendar()[1]}", (150, 200, 255)),
                     (now.strftime("%H:%M"), (255, 255, 255))]
            txt, col = lines[page(t, 4, 3)]
            f.text(txt, 20, 0, col)
            return
        wcol = (255, 80, 80) if now.weekday() == 6 else (230, 230, 230)
        mon = f"{PL_MON3[now.month - 1]} {now.year}"
        alt = [f"TYDZ {now.isocalendar()[1]}", f"DZIEŃ {now.timetuple().tm_yday}", now.strftime("%H:%M")]
        if 20 + text_w(wd, TXT) + 6 + max(text_w(x, SMALL) for x in [mon] + alt) > W:
            if page(t, 2, 6) == 0:  # długa nazwa dnia: na zmianę cała i skrót z resztą kartki
                f.text(wd, 20, 0, wcol)
                return
            wd = wd[:3]
        f.text(wd, 20, 0, wcol)
        x2 = 20 + text_w(wd, TXT) + 6
        f.text(mon, x2, 0, (255, 200, 120), SMALL)
        f.text(alt[int(t / 3) % 3], x2, 6, (150, 200, 255), SMALL)


def easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    return dtm.date(y, month, (h + l - 7 * m + 114) % 31 + 1)


@reg("odliczanie")
class Countdown(Clock):
    """Odliczania na zmianę: do północy, do weekendu, do Wigilii, do Wielkanocy i do Nowego Roku."""

    def targets(self, now):
        tz = now.tzinfo
        mid = (now + dtm.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        wd = now.weekday()
        if wd < 5:
            wk = (("DO WEEKENDU", "WEEKEND"), (now + dtm.timedelta(days=5 - wd)).replace(hour=0, minute=0, second=0, microsecond=0))
        else:
            wk = (("DO PONIEDZIAŁKU", "PONIEDZ."), (now + dtm.timedelta(days=7 - wd)).replace(hour=0, minute=0, second=0, microsecond=0))
        wig = dtm.datetime(now.year, 12, 24, tzinfo=tz)
        if wig <= now:
            wig = dtm.datetime(now.year + 1, 12, 24, tzinfo=tz)
        e = easter(now.year)
        ea = dtm.datetime(e.year, e.month, e.day, tzinfo=tz)
        if ea <= now:
            e = easter(now.year + 1)
            ea = dtm.datetime(e.year, e.month, e.day, tzinfo=tz)
        return [(("DO PÓŁNOCY", "PÓŁNOC"), mid, (120, 140, 255)), wk + ((255, 200, 0),),
                (("DO WIGILII", "WIGILIA"), wig, (255, 60, 60)), (("DO WIELKANOCY", "WIELKANOC"), ea, (255, 160, 220)),
                (("DO NOWEGO ROKU", "NOWY ROK"), dtm.datetime(now.year + 1, 1, 1, tzinfo=tz), (0, 230, 200))]

    def draw(self, f, now, t, dt):
        (name, short), when, col = self.targets(now)[int(t / 6) % 5]
        left = int((when - now).total_seconds())
        d, r = divmod(max(0, left), 86400)
        days = f"{d} {'DZIEŃ' if d == 1 else 'DNI'}" if d else ""
        opts = ([f"{name}: {days}", f"{short}: {days}"] if d else []) + [name, short]
        label = next((o for o in opts if text_w(o, SMALL) <= W), short)
        if d and label in (name, short):  # liczba dni się nie zmieściła – na zmianę z nazwą
            label = [label, days][int(t / 3) % 2]
        f.text(label, (W - text_w(label, SMALL)) // 2, 0, col, SMALL)
        s = f"{r // 3600:02d}:{r % 3600 // 60:02d}:{r % 60:02d}"
        f.text(s, (W - text_w(s, TXT)) // 2, 3, (255, 255, 255))


@reg("nixie")
class Nixie(Clock):
    """Lampy Nixie: pomarańczowe cyfry z poświatą, widoczna siatka i duchy nieświecących katod; co minutę „przepłukanie” cyfr."""

    def draw(self, f, now, t, dt):
        s = now.strftime("%H%M" if NARROW else "%H%M%S")
        x = (W - (len(s) * 8 + len(s) // 2 + (len(s) // 2 - 1) * 5)) // 2
        flush = now.second == 0 and now.microsecond < 800000
        for i, d in enumerate(s):
            for y in range(H):
                for xx in range(x, x + 8):
                    edge = xx in (x, x + 7) or y == 11 or (y == 0 and xx not in (x, x + 7))
                    if edge and not (y == 0 and xx in (x, x + 7)):
                        f.set(xx, y, (110, 30, 0))
                    elif (xx + y) % 2 == 0:
                        f.set(xx, y, (8, 4, 2))
            f.draw(text_px("8", x + 1, 1), (26, 10, 2))
            dig = str((int(t * 25) + i) % 10) if flush else d
            pts = text_px(dig, x + 1, 1)
            f.draw(pts, (255, 130, 30))
            x += 8 + (1 if i % 2 == 0 else 0)
            if i in (1, 3) and i < len(s) - 1:
                on = now.microsecond < 500000
                for yy in (3, 8):
                    f.set(x + 2, yy, (255, 110, 20) if on else (40, 12, 0))
                x += 5


SEG = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc", "7": "abc",
       "8": "abcdefg", "9": "abcdfg"}


def seg_px(d, x0, y0, w=10):
    pts = {"a": [(x, 0) for x in range(2, w - 2)], "g": [(x, 5) for x in range(2, w - 2)],
           "d": [(x, 10) for x in range(2, w - 2)], "f": [(x, y) for x in (0, 1) for y in range(1, 5)],
           "b": [(x, y) for x in (w - 2, w - 1) for y in range(1, 5)], "e": [(x, y) for x in (0, 1) for y in range(6, 10)],
           "c": [(x, y) for x in (w - 2, w - 1) for y in range(6, 10)]}
    return {k: [(x0 + x, y0 + y) for x, y in v] for k, v in pts.items()}


@reg("segmenty")
class SevenSeg(Clock):
    """Wyświetlacz siedmiosegmentowy jak w starym radiobudziku: czerwone segmenty, słabo widoczne wygaszone, lekkie migotanie."""

    def draw(self, f, now, t, dt):
        s = now.strftime("%H%M" if NARROW else "%H%M%S")
        x = (W - (len(s) * 11 + (len(s) // 2 - 1) * 5)) // 2
        for i, d in enumerate(s):
            segs = seg_px(d, x, 1)
            for name, pts in segs.items():
                f.draw(pts, (255, 25, 15) if name in SEG[d] else (24, 3, 2))
            x += 11
            if i in (1, 3) and i < len(s) - 1:
                c = (255, 25, 15) if now.microsecond < 500000 else (24, 3, 2)
                f.rect(x + 1, 3, x + 2, 4, c)
                f.rect(x + 1, 7, x + 2, 8, c)
                x += 5


@reg("klapki")
class SplitFlap(Clock):
    """Tablica z klapkami jak na starym dworcu: przy zmianie cyfry górna klapka opada i odsłania nową."""

    def __init__(self):
        self.slots = {}

    @staticmethod
    def on(ch, cx, cy):
        g = BIG.get(ch, BIG[" "])
        gx, gy = cx - 1, cy - 1
        return 0 <= gy < len(g) and 0 <= gx < len(g[0]) and g[gy][gx] == "#"

    def draw(self, f, now, t, dt):
        txt = now.strftime("%H:%M")
        x = (W - (4 * 9 + 5)) // 2
        for i, ch in enumerate(txt):
            if ch == ":":
                f.rect(x + 1, 3, x + 2, 4, (200, 200, 200))
                f.rect(x + 1, 7, x + 2, 8, (200, 200, 200))
                x += 5
                continue
            cur, old, tc = self.slots.get(i, (ch, ch, -9))
            if ch != cur:
                old, cur, tc = cur, ch, t
            self.slots[i] = (cur, old, tc)
            p = clamp((t - tc) / 0.4)
            for cy in range(12):
                for cx in range(8):
                    top = cy < 6
                    src = cur if top or p >= 1 else old
                    lit = self.on(src, cx, cy)
                    bg = (38, 38, 42) if top else (30, 30, 34)
                    f.set(x + cx, cy, (230, 230, 220) if lit else bg)
            if p < 1:
                if p < 0.5:
                    s = 1 - p * 2
                    for cy in range(6):
                        sy = 6 - (6 - cy) / max(s, 0.01)
                        for cx in range(8):
                            if sy >= 0:
                                lit = self.on(old, cx, int(sy))
                                f.set(x + cx, cy, mul((230, 230, 220) if lit else (38, 38, 42), 0.5 + 0.5 * s))
                else:
                    s = (p - 0.5) * 2
                    for cy in range(6, 12):
                        sy = 6 + (cy - 6) / max(s, 0.01)
                        for cx in range(8):
                            if sy < 12:
                                lit = self.on(cur, cx, int(sy))
                                f.set(x + cx, cy, mul((230, 230, 220) if lit else (30, 30, 34), 0.5 + 0.5 * s))
            for cx in range(8):
                f.set(x + cx, 6, (5, 5, 5))
            x += 9


@reg("lustro")
class Mirror(Clock):
    """Godzina nad taflą wody i jej falujące odbicie."""

    def draw(self, f, now, t, dt):
        for y in range(7):
            for x in range(W):
                f.px[y][x] = lerp((2, 2, 15), (12, 8, 30), y / 7)
        s = now.strftime("%H:%M:%S")
        x0 = (W - text_w(s, TXT)) // 2
        pts = text_px(s, x0, -2, TXT)
        for x, y in pts:
            f.set(x, y, hsv(0.55 + x / 400 + t * 0.03, 0.5, 1))
        for y in range(7, H):
            k = y - 7
            src = 6 - k
            off = math.sin(t * 3 + k * 1.3) * (0.5 + k * 0.3)
            for x in range(W):
                f.px[y][x] = lerp((0, 10, 30), (0, 4, 14), k / 5)
            for x, yy in pts:
                if yy == src:
                    f.add(x + off, y, mul(hsv(0.55 + x / 400 + t * 0.03, 0.6, 1), 0.45 - k * 0.07))
            for x in range(W):
                if hash1(x * 13 + k * 7 + int(t * 4)) > 0.97:
                    f.add(x, y, (30, 40, 60))


@reg("cien")
class Shadow(Clock):
    """Cyfry na ścianie rzucają długi cień, który obraca się jak w zegarze słonecznym, zgodnie z prawdziwym słońcem."""

    def draw(self, f, now, t, dt):
        elev, solar = sun_position(now)
        day = elev > 0
        wall = (60, 45, 30) if day else (10, 12, 25)
        a = (solar - 12) / 12 * math.pi
        dx = -math.sin(a) * 1.2
        ln = int(3 + 6 * (1 - clamp(elev / 45))) if day else 4
        for y in range(H):
            for x in range(W):
                f.px[y][x] = mul(wall, 0.7 + 0.3 * (x / W if dx < 0 else 1 - x / W))
        pts = clock_big(f, now, outline=None, c=(0, 0, 0))
        ps = set(pts)
        for k in range(ln, 0, -1):
            for x, y in pts:
                q = (round(x + dx * k), round(y + k * 0.35))
                if q not in ps:
                    f.set(q[0], q[1], mul(wall, 0.25 + 0.5 * k / ln))
        f.draw(pts, (255, 240, 210) if day else (170, 180, 230))


@reg("tetris")
class Tetris(Clock):
    """Cyfry układają się z klocków spadających z góry jak w Tetrisie; z nową minutą stare się rozsypują."""

    PAL = [(0, 240, 240), (240, 240, 0), (160, 0, 240), (0, 240, 0), (240, 0, 0), (0, 0, 240), (240, 160, 0)]

    def __init__(self):
        self.txt, self.t0, self.old, self.old_t = None, 0, [], 0

    def draw(self, f, now, t, dt):
        txt = now.strftime("%H:%M")
        if txt != self.txt:
            if self.txt is not None:
                self.old, self.old_t = [(x, y, self.col(x, y, self.txt)) for x, y in centered(self.txt)], t
            self.txt, self.t0 = txt, t + 0.4
        for x, y, c in self.old:
            yy = y + (t - self.old_t) ** 2 * 40
            if yy < H:
                f.set(x, yy, c)
        pts = sorted(centered(txt), key=lambda p: (-p[1], p[0]))
        for i, (x, y) in enumerate(pts):
            st = self.t0 + i * 0.012
            if t >= st:
                f.set(x, min(y, -1 + (t - st) * 30), self.col(x, y, txt))

    def col(self, x, y, txt):
        return self.PAL[int(hash1(x // 2 * 7 + y // 2 * 131 + sum(map(ord, txt))) * 7) % 7]


@reg("hex")
class HexTime(Clock):
    """Czas szesnastkowy: doba = 16 hexgodzin × 256 hexminut × 16 hexsekund, zapis „A_3F_2”; pasek = hexgodzina."""

    def draw(self, f, now, t, dt):
        sec = now.hour * 3600 + now.minute * 60 + now.second + now.microsecond / 1e6
        v = int(sec / 86400 * 65536)
        parts = [(f"{v >> 12:X}", (255, 90, 90)), ("_", (90, 90, 90)), (f"{(v >> 4) & 0xFF:02X}", (90, 255, 120)),
                 ("_", (90, 90, 90)), (f"{v & 0xF:X}", (90, 150, 255))]
        x = (W - sum(text_w(s, TXT) + 1 for s, _ in parts)) // 2
        if x > text_w("HEX", SMALL) + 3:  # podpis tylko, gdy nie wchodzi na cyfry
            f.text("HEX", 1, 0, (70, 70, 90), SMALL)
        for s, c in parts:
            f.text(s, x, 0, c)
            x += text_w(s, TXT) + 1
        for i in range(16):
            c = (255, 90, 90) if i < (v >> 12) else (40, 20, 20) if i == (v >> 12) else (15, 15, 20)
            if i == (v >> 12):
                c = mul((255, 90, 90), 0.3 + 0.7 * ((v >> 4) & 0xFF) / 255)
            f.rect(i * 7 + 4, 11, i * 7 + 8, 11, c)


@reg("kolor")
class ColorTime(Clock):
    """Kolor czasu: godzina, minuta i sekunda to składowe R, G, B tła, zapisane jak kolor #HHMMSS."""

    def draw(self, f, now, t, dt):
        c = (now.hour / 23 * 255, now.minute / 59 * 255, now.second / 59 * 255)
        for y in range(H):
            for x in range(W):
                f.px[y][x] = c
        lum = c[0] * 0.3 + c[1] * 0.59 + c[2] * 0.11
        s = now.strftime("#%H%M%S")
        f.text(s, (W - text_w(s, TXT)) // 2, 0, (255, 255, 255) if lum < 140 else (0, 0, 0), TXT,
               (0, 0, 0) if lum < 140 else None)


@reg("dziesietny")
class Decimal(Clock):
    """Czas dziesiętny z Rewolucji Francuskiej: 10 godzin po 100 minut po 100 sekund; obok zwykły czas."""

    def draw(self, f, now, t, dt):
        sec = now.hour * 3600 + now.minute * 60 + now.second + now.microsecond / 1e6
        d = sec / 86400 * 100000
        s = f"{int(d // 10000)}:{int(d // 100 % 100):02d}:{int(d % 100):02d}"
        if NARROW:
            if page(t, 4, 2) == 0:
                f.text("CZAS", (W - text_w("CZAS", SMALL)) // 2, 0, (100, 100, 255), SMALL)
                f.text("DZIESIĘTNY", (W - text_w("DZIESIĘTNY", SMALL)) // 2, 6, (255, 255, 255), SMALL)
            else:
                f.draw(text_px(s, (W - text_w(s)) // 2, 1), (255, 60, 60))
            return
        f.text("CZAS", 1, 0, (100, 100, 255), SMALL)
        f.text("DZIES.", 1, 6, (255, 255, 255), SMALL)
        f.draw(text_px(s, max(30, text_w("DZIES.", SMALL) + 4), 1), (255, 60, 60))
        n = now.strftime("%H:%M")
        f.text(n, W - text_w(n, SMALL), 6, (120, 120, 140), SMALL)
        f.text("NORM", W - text_w("NORM", SMALL), 0, (70, 70, 90), SMALL)


@reg("beaty")
class Swatch(Clock):
    """Czas internetowy Swatch: doba = 1000 beatów liczonych od Biel (UTC+1), wszędzie na świecie ten sam; obok kręci się Ziemia."""

    def draw(self, f, now, t, dt):
        u = now.astimezone(dtm.timezone.utc)
        beats = ((u.hour + 1) % 24 * 3600 + u.minute * 60 + u.second + u.microsecond / 1e6) / 86.4
        xa = 0 if NARROW else 2
        f.text("@", xa, 0, (255, 60, 60))
        s = f"{int(beats):03d}"
        xd = xa + text_w("@", TXT) + 2
        f.draw(text_px(s, xd, 1), (255, 255, 255))
        f.text(f".{int(beats * 100) % 100:02d}", xd + text_w(s) + 1, 6, (180, 180, 180), SMALL)
        cx, cy, r = W - 10, 5.5, 5.5
        rot = t * 20
        for y in range(H):
            for x in range(W - 20, W):
                dx, dy = (x + 0.5 - cx) / r, (y + 0.5 - cy) / r
                if dx * dx + dy * dy < 1:
                    lat = math.degrees(math.asin(-dy))
                    lon = math.degrees(math.asin(dx / math.sqrt(max(1e-6, 1 - dy * dy)))) + rot
                    mx, my = map_xy(lat, (lon + 180) % 360 - 180)
                    shade = 0.4 + 0.6 * math.sqrt(1 - dx * dx - dy * dy)
                    f.set(x, y, mul((30, 130, 40) if (int(mx), int(my)) in LAND else (0, 40, 120), shade))
        if not NARROW:
            small_time(f, now, x=58, y=0, c=(120, 120, 140))


@reg("unix")
class Unix(Clock):
    """Znacznik czasu Unix – sekundy od 1 stycznia 1970; cyfry, które właśnie się zmieniły, rozbłyskują."""

    def __init__(self):
        self.prev, self.flash = "", {}

    def draw(self, f, now, t, dt):
        s = str(int(now.timestamp()))
        for i, (a, b) in enumerate(zip(s, self.prev.ljust(len(s)))):
            if a != b:
                self.flash[i] = t
        self.prev = s
        if NARROW:  # 10 cyfr: wąska, wysoka czcionka
            x = (W - text_w(s, TALL)) // 2
            for i, ch in enumerate(s):
                k = clamp(1 - (t - self.flash.get(i, -9)) / 0.6)
                base = (60, 200, 255) if i >= len(s) - 3 else (200, 200, 210)
                f.text(ch, x, 1, lerp(base, (255, 255, 255), k), TALL)
                x += text_w(ch, TALL) + 1
            return
        x = (W - text_w(s) - 16) // 2 + 16
        f.text("UNIX", 0, 0, (80, 80, 100), SMALL)
        f.text("TIME", 0, 6, (80, 80, 100), SMALL)
        for i, ch in enumerate(s):
            k = clamp(1 - (t - self.flash.get(i, -9)) / 0.6)
            base = (60, 200, 255) if i >= len(s) - 3 else (200, 200, 210)
            f.draw(text_px(ch, x, 1), lerp(base, (255, 255, 255), k))
            x += 7


def tz_off(std, rule, u):
    """Przesunięcie strefy w godzinach z prostymi regułami czasu letniego (bez zoneinfo)."""
    y = u.year

    def sun(m, n):  # n-ta niedziela miesiąca, n=-1 ostatnia
        if n > 0:
            d = dtm.datetime(y, m, 1)
            return d + dtm.timedelta(days=(6 - d.weekday()) % 7 + 7 * (n - 1))
        d = dtm.datetime(y, m + 1, 1) - dtm.timedelta(days=1) if m < 12 else dtm.datetime(y, 12, 31)
        return d - dtm.timedelta(days=(d.weekday() + 1) % 7)

    n = u.replace(tzinfo=None)
    if rule == "eu":
        dst = sun(3, -1) + dtm.timedelta(hours=1) <= n < sun(10, -1) + dtm.timedelta(hours=1)
    elif rule == "us":
        dst = sun(3, 2) + dtm.timedelta(hours=2 - std) <= n < sun(11, 1) + dtm.timedelta(hours=1 - std)
    elif rule == "au":
        dst = not (sun(4, 1) + dtm.timedelta(hours=3 - std - 1) <= n < sun(10, 1) + dtm.timedelta(hours=2 - std))
    elif rule == "nz":
        dst = not (sun(4, 1) + dtm.timedelta(hours=3 - std - 1) <= n < sun(9, -1) + dtm.timedelta(hours=2 - std))
    else:
        dst = False
    return std + (1 if dst else 0)


@reg("strefy")
class WorldClocks(Clock):
    """Zegary świata przewijane jak na lotnisku: Warszawa, Londyn, Nowy Jork, Tokio, Sydney…; dzień na żółto, noc na niebiesko."""

    CITIES = [("Warszawa", 1, "eu"), ("Londyn", 0, "eu"), ("Nowy Jork", -5, "us"), ("Los Angeles", -8, "us"),
              ("Rio", -3, None), ("Reykjavik", 0, None), ("Dubaj", 4, None), ("Delhi", 5.5, None),
              ("Pekin", 8, None), ("Tokio", 9, None), ("Sydney", 10, "au"), ("Auckland", 12, "nz")]

    def draw(self, f, now, t, dt):
        u = now.astimezone(dtm.timezone.utc)
        segs = []
        for name, std, rule in self.CITIES:
            lt = u + dtm.timedelta(hours=tz_off(std, rule, u))
            day = 7 <= lt.hour < 19
            segs += [(name, (150, 150, 170)), (lt.strftime("%H:%M") + "    ", (255, 220, 60) if day else (90, 140, 255))]
        scroll_segs(f, segs, t, 22)


@reg("obwod")
class Perimeter(Clock):
    """Sekundnik jako świetlny wąż biegnący dookoła krawędzi panelu (pełne okrążenie = minuta), w środku godzina."""

    def __init__(self):
        self.path = ([(x, 0) for x in range(W)] + [(W - 1, y) for y in range(1, H)]
                     + [(x, H - 1) for x in range(W - 2, -1, -1)] + [(0, y) for y in range(H - 2, 0, -1)])

    def draw(self, f, now, t, dt):
        n = len(self.path)
        for k in range(12):
            f.set(*self.path[int(k * n / 12)], (60, 60, 60))
        pos = (now.second + now.microsecond / 1e6) / 60 * n
        for k in range(30):
            x, y = self.path[int(pos - k) % n]
            f.set(x, y, mul(hsv(now.minute / 60 + k * 0.01, 0.8, 1), 1 - k / 30))
        clock_big(f, now, (255, 255, 255))


@reg("wahadlo")
class Pendulum(Clock):
    """Dwa wahadła po bokach tykają co sekundę jak w zegarze stojącym; cyfry lekko rozbłyskują przy każdym tyknięciu."""

    def draw(self, f, now, t, dt):
        s = now.second + now.microsecond / 1e6
        a = 0.55 * math.sin(math.pi * s)
        for px, sign in (((10, 1), (109, -1)) if not NARROW else ((5, 1), (W - 6, -1))):
            ln = 9.5 if not NARROW else 8.5
            bx, by = px + math.sin(a * sign) * ln * (1 if not NARROW else 0.5), math.cos(a) * ln
            f.line(px, 0, bx, by, (140, 110, 60))
            disc(f, bx, by, 1.6, (255, 200, 80))
            f.set(px, 0, (200, 200, 200))
        k = clamp(1 - (now.microsecond / 1e6) / 0.25)
        clock_big(f, now, lerp((220, 200, 160), (255, 255, 255), k))


@reg("fala")
class WaveText(Clock):
    """Godzina z sekundami kołysze się na fali, pod nią morze z pianą."""

    def draw(self, f, now, t, dt):
        for x in range(W):
            h = 9.5 + math.sin(x * 0.15 + t * 1.5) * 0.8 + math.sin(x * 0.4 - t) * 0.4
            for y in range(H):
                if y >= h:
                    f.set(x, y, lerp((0, 70, 140), (0, 20, 60), (y - h) / 3))
            f.set(x, h, (150, 200, 255))
        s = now.strftime("%H:%M:%S")
        x0 = (W - text_w(s, TXT)) // 2
        for x, y in text_px(s, x0, 0, TXT):
            f.set(x, y + math.sin(x * 0.12 - t * 3) * 1.6, (255, 255, 255))


@reg("glitch")
class Glitch(Clock):
    """Cyfrowy glitch: rozjechane kanały RGB, przesunięte linie i szum, który co chwilę psuje obraz."""

    def __init__(self):
        self.until, self.nxt = 0, 1

    def draw(self, f, now, t, dt):
        if t > self.nxt:
            self.until, self.nxt = t + random.uniform(0.1, 0.45), t + random.uniform(1, 4)
        g = t < self.until
        pts = centered(now.strftime("%H:%M"))
        dr, db = (random.randint(-3, 3), random.randint(-3, 3)) if g else (0, 0)
        for x, y in pts:
            f.add(x + dr, y, (255, 0, 0))
            f.add(x, y, (0, 255, 0))
            f.add(x + db, y, (0, 0, 255))
        if g:
            for _ in range(3):
                y = random.randrange(H)
                k = random.randint(-8, 8)
                f.px[y] = f.px[y][-k:] + f.px[y][:-k] if k else f.px[y]
            for _ in range(4):
                x, y = random.randrange(W), random.randrange(H)
                f.rect(x, y, x + random.randint(1, 8), y, hsv(random.random(), 1, random.uniform(0.3, 1)))
        for y in range(0, H, 2):
            f.px[y] = [mul(c, 0.75) for c in f.px[y]]


@reg("neon")
class Neon(Clock):
    """Neon na ceglanym murze: różowe cyfry z poświatą, które czasem zamrugają, i szyld „OTWARTE”."""

    def __init__(self):
        self.off = {}

    def draw(self, f, now, t, dt):
        for y in range(H):
            for x in range(W):
                mortar = y % 3 == 2 or (x + (4 if (y // 3) % 2 else 0)) % 8 == 0
                f.px[y][x] = (6, 2, 2) if mortar else (22, 8, 6)
        txt = now.strftime("%H:%M")
        x = (W - text_w(txt)) // 2
        if not NARROW:  # szyld „OTWARTE”, godzina i „24H” razem pośrodku
            x0 = (W - text_w("OTWARTE", SMALL) - text_w(txt) - text_w("24H", SMALL) - 12) // 2
            x = x0 + text_w("OTWARTE", SMALL) + 6
            k = 1 if (t % 7) > 0.3 else 0.2
            f.text("OTWARTE", x0, 3, mul((40, 140, 255), k), SMALL)
            f.text("24H", x + text_w(txt) + 6, 3, (255, 200, 40), SMALL)
        for i, ch in enumerate(txt):
            if random.random() < 0.004:
                self.off[i] = t + random.uniform(0.05, 0.25)
            lit = t > self.off.get(i, 0)
            pts = text_px(ch, x, 1)
            f.draw(pts, (255, 50, 170) if lit else (110, 0, 60))
            x += text_w(ch) + 1


@reg("pismo")
class Handwriting(Clock):
    """Pióro co minutę pisze godzinę na papierze w linie – piksel po pikselu, z błyszczącą stalówką."""

    def __init__(self):
        self.txt, self.t0 = None, 0

    def draw(self, f, now, t, dt):
        for y in range(H):
            for x in range(W):
                f.px[y][x] = (26, 22, 16) if y % 4 != 3 else (14, 18, 40)
        for y in range(H):
            f.set(8, y, (60, 10, 10))
        txt = now.strftime("%H:%M")
        if txt != self.txt:
            self.txt, self.t0 = txt, t
        x = (W - text_w(txt)) // 2
        order = []
        for ci, ch in enumerate(txt):
            order += sorted(text_px(ch, x, 1), key=lambda p: (p[0], p[1] if p[0] % 2 else -p[1]))
            x += text_w(ch) + 1
        n = int(clamp((t - self.t0) / 2.5) * len(order))
        for x, y in order[:n]:
            f.set(x, y, (70, 130, 255))
        if n < len(order):
            px, py = order[n]
            f.set(px, py, (255, 255, 255))
            f.set(px + 1, py - 1, (180, 180, 180))


@reg("kreskowy")
class Barcode(Clock):
    """Kod kreskowy EAN z godziną i datą (HHMMSSDDMM), z czerwonym laserem skanera."""

    L = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"]

    def draw(self, f, now, t, dt):
        digs = now.strftime("%H%M%S")
        mods = "101" + "".join(self.L[int(d)] for d in digs[:3]) + "01010" + "".join(
            "".join("1" if b == "0" else "0" for b in self.L[int(d)]) for d in digs[3:]) + "101"
        mw = 2 if len(mods) * 2 + 6 <= W else 1
        x0 = (W - len(mods) * mw) // 2
        hms = now.strftime("%H:%M:%S")
        tx, tw = (W - text_w(hms, SMALL)) // 2, text_w(hms, SMALL)
        f.rect(x0 - 3, 0, x0 + len(mods) * mw + 2, 11, (190, 190, 190))
        for i, b in enumerate(mods):
            if b == "1":
                bx = x0 + i * mw
                guard = not 3 <= i < len(mods) - 3 or 24 <= i < 29
                long_ = guard and not tx - 2 <= bx <= tx + tw + 1  # dłuższe kreski nie wchodzą na napis
                f.rect(bx, 0, bx + mw - 1, 8 if long_ else 6, (0, 0, 0))
        f.text(hms, tx, 7, (0, 0, 0), SMALL)
        lx = x0 + (math.sin(t * 2) * 0.5 + 0.5) * len(mods) * mw
        for y in range(H):
            f.add(lx, y, (255, 0, 0))


@reg("maszyna")
class Typewriter(Clock):
    """Maszyna do pisania co minutę wystukuje godzinę i datę; karetka przesuwa się, na końcu dzwonek."""

    def __init__(self):
        self.txt, self.t0 = None, 0

    def draw(self, f, now, t, dt):
        full = f"{now:%H:%M} {PL_DAYS[now.weekday()]}, {now.day} {PL_MONTHS[now.month - 1]}"
        if now.strftime("%H:%M") != self.txt:
            self.txt, self.t0 = now.strftime("%H:%M"), t
        n = min(len(full), int((t - self.t0) * 9))
        s = full[:n]
        tw = text_w(s, TXT)
        pos = W - 30 if NARROW else 90
        x0 = 2 if tw < pos - 2 else pos - tw
        f.text(s, x0, 0, (255, 180, 60))
        if n < len(full) or int(t * 2) % 2:
            f.rect(x0 + tw + 2, 9, x0 + tw + 6, 9, (255, 255, 255))
        done = (t - self.t0) * 9 - len(full)
        if 0 < done < 3:
            f.rect(W - 3, 0, W - 1, 11, (255, 255, 200))


@reg("radar")
class Radar(Clock):
    """Radar: wiązka omiata niebo, cyfry godziny pojawiają się jak wykryte obiekty i powoli gasną."""

    def __init__(self):
        c, sy = W / 2, 5 * W / 120
        self.ang = [[math.atan2((11.5 - y) * sy, x + 0.5 - c) for x in range(W)] for y in range(H)]
        self.dist = [[math.hypot(x + 0.5 - c, (11.5 - y) * sy) for x in range(W)] for y in range(H)]
        self.glow = [[0.0] * W for _ in range(H)]

    def draw(self, f, now, t, dt):
        a = (math.sin(t * 1.1) * 0.5 + 0.5) * math.pi
        dset = set(centered(now.strftime("%H:%M")))
        dec = math.exp(-dt * 1.3)
        for y in range(H):
            gy, ay, dy = self.glow[y], self.ang[y], self.dist[y]
            for x in range(W):
                g = gy[x] * dec
                if abs(ay[x] - a) < 0.05:
                    g = 1.0
                gy[x] = g
                ring = 0.12 if any(abs(dy[x] - r * W / 120) < 0.6 for r in (20, 40, 60)) else 0
                if (x, y) in dset:
                    f.px[y][x] = (40 * g, 255 * max(g, 0.06), 60 * g)
                else:
                    f.px[y][x] = (0, 70 * (g * 0.35 + ring), 0)
        for k in range(W // 2 + 10):
            f.add(W / 2 + math.cos(a) * k, 11.5 - math.sin(a) * k / (5 * W / 120), (60, 255, 60))


@reg("domino")
class Domino(Clock):
    """Czas jako trzy kostki domina: oczka pokazują cyfry godzin, minut i sekund."""

    PIPS = {0: [], 1: [4], 2: [0, 8], 3: [0, 4, 8], 4: [0, 2, 6, 8], 5: [0, 2, 4, 6, 8], 6: [0, 2, 3, 5, 6, 8],
            7: [0, 2, 3, 4, 5, 6, 8], 8: [0, 1, 2, 3, 5, 6, 7, 8], 9: list(range(9))}

    def draw(self, f, now, t, dt):
        digs = now.strftime("%H%M%S")
        nd = 2 if NARROW else 3
        x = (W - (nd * 23 + (nd - 1) * 6)) // 2
        cols = [(255, 80, 80), (80, 255, 120), (80, 160, 255)]
        for k in range(nd):
            f.rect(x, 0, x + 22, 11, (200, 195, 180))
            f.rect(x + 11, 1, x + 11, 10, (80, 75, 70))
            for half in range(2):
                d = int(digs[k * 2 + half])
                hx = x + half * 12
                for p in self.PIPS[d]:
                    px, py = hx + 1 + (p % 3) * 3.5, 1 + (p // 3) * 3.5
                    f.rect(px, py, px + 1, py + 1, mul(cols[k], 0.8))
            x += 29


@reg("ksiezyc")
class MoonPhase(Clock):
    """Faza Księżyca liczona z daty: tarcza z oświetloną częścią, nazwa fazy, procent oświetlenia i ile do pełni."""

    def draw(self, f, now, t, dt):
        syn = 29.530588853
        ref = dtm.datetime(2000, 1, 6, 18, 14, tzinfo=dtm.timezone.utc)
        age = ((now - ref).total_seconds() / 86400) % syn
        frac = age / syn
        phi = 2 * math.pi * frac
        illum = (1 - math.cos(phi)) / 2
        for i in range(30):
            f.set(hash1(i) * W, hash1(i + 50) * H, mul((110, 110, 140), 0.3 + 0.3 * math.sin(t + i)))
        cx, cy, r = 6, 6, 5.6
        for y in range(H):
            for x in range(13):
                nx, ny = (x + 0.5 - cx) / r, (y + 0.5 - cy) / r
                if nx * nx + ny * ny < 1:
                    w = math.sqrt(1 - ny * ny)
                    lit = nx >= w * math.cos(phi) if frac < 0.5 else nx <= -w * math.cos(phi)
                    crater = 0.8 + 0.2 * noise2(x * 0.9, y * 0.9)
                    f.set(x, y, mul((230, 230, 200), crater) if lit else (14, 14, 22))
        names = [(0.0339, "nów"), (0.216, "młody sierp"), (0.284, "I kwadra"), (0.466, "przybywa"), (0.534, "pełnia"),
                 (0.716, "ubywa"), (0.784, "III kwadra"), (0.966, "stary sierp"), (1.01, "nów")]
        name = next(n for lim, n in names if frac < lim)
        to_full = ((0.5 - frac) % 1) * syn
        lines = [name, f"{illum * 100:.0f}% jasna", f"pełnia za {to_full:.0f} d" if to_full > 1 else "pełnia!",
                 now.strftime("%H:%M")]
        if max(text_w(x, TXT) for x in lines) <= W - 16:
            f.text(lines[int(t / 4) % 4], 16, 0, (230, 230, 200))
        else:  # wąski panel: wszystko po kolei jednym paskiem obok tarczy
            scroll_segs(f, [(x + "   ", (230, 230, 200) if i % 2 == 0 else (170, 190, 255)) for i, x in enumerate(lines)],
                        t, 22, 0, 14)

# ================================================================ SCENY, SYMULACJE I GRY
@reg("plazma")
class Plasma(Clock):
    """Klasyczna plazma z demosceny w płynących kolorach, godzina wycięta na czarno z białym środkiem."""

    def draw(self, f, now, t, dt):
        cx, cy = W / 2 + math.sin(t * 0.7) * W / 3, 6 + math.cos(t * 0.9) * 4
        for y in range(H):
            row = f.px[y]
            for x in range(W):
                v = (math.sin(x * 0.08 + t) + math.sin(y * 0.35 + t * 1.3) + math.sin((x * 0.05 + y * 0.2) + t * 0.7)
                     + math.sin(math.hypot(x - cx, (y - cy) * 4) * 0.08))
                row[x] = hsv(v * 0.12 + t * 0.05, 0.9, 0.65)
        clock_big(f, now)


@reg("lawa")
class Lava(Clock):
    """Lampa lawa: bąble gorącego wosku łączą się i rozdzielają w fioletowej butelce."""

    def __init__(self):
        self.b = [(random.uniform(0.1, 0.3), random.uniform(0.2, 0.5), random.random() * 6, random.uniform(3, 4.5)) for _ in range(7)]

    def draw(self, f, now, t, dt):
        balls = [(W / 2 + math.sin(t * sx + ph) * (W / 2 - 5), 6 + math.sin(t * sy + ph * 2) * 5.5, r) for sx, sy, ph, r in self.b]
        for y in range(H):
            row = f.px[y]
            for x in range(W):
                v = 0.0
                for bx, by, r in balls:
                    d = (x - bx) ** 2 + ((y - by) * 1.6) ** 2
                    v += r * r / (d + 0.5)
                if v > 1:
                    row[x] = grad([(1, (200, 20, 0)), (2, (255, 110, 0)), (4, (255, 220, 60))], v)
                elif v > 0.6:
                    row[x] = lerp((25, 0, 30), (140, 10, 10), (v - 0.6) / 0.4)
                else:
                    row[x] = (25, 0, 30)
        clock_big(f, now, (255, 240, 220), outline=(30, 0, 20))


@reg("swietliki")
class Fireflies(Clock):
    """Nocna łąka: świetliki krążą i mrugają nad sylwetkami drzew, godzina świeci jak księżyc."""

    def __init__(self):
        rnd = random.Random(11)
        self.trees = [9 - int(max(0, math.sin(x * 0.21) * 3 + math.sin(x * 0.07 + 2) * 2)) for x in range(W)]
        self.f = [(rnd.random() * 100, rnd.uniform(0.6, 1.8), rnd.random() * 6) for _ in range(28)]

    def draw(self, f, now, t, dt):
        for y in range(H):
            for x in range(W):
                f.px[y][x] = (0, 2, 8) if y < self.trees[x] else (0, 6, 2)
        clock_big(f, now, (70, 80, 60), outline=None)
        for seed, rate, ph in self.f:
            x = noise1(seed + t * 0.08) * W * 1.2 - W * 0.1
            y = noise1(seed + 50 + t * 0.1) * 11
            b = max(0, math.sin(t * rate + ph)) ** 6
            f.add(x, y, mul((200, 255, 60), b))
            for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                f.add(x + ox, y + oy, mul((40, 60, 10), b))


@reg("fajerwerki")
class Fireworks(Clock):
    """Fajerwerki ze smugami; na początku każdej minuty salwa, a o pełnej godzinie pokaz przez całą minutę."""

    def __init__(self):
        self.rk, self.pt, self.buf, self.acc = [], [], Persist(), 0.0

    def draw(self, f, now, t, dt):
        rate = 5 if now.minute == 0 else 7 if now.second < 4 else 1.1
        self.acc += rate * dt
        while self.acc >= 1:
            self.acc -= 1
            self.rk.append([random.uniform(10, W - 10), H, random.uniform(-3, 3), -random.uniform(14, 18), random.random()])
        self.buf.fade(math.exp(-dt * 7))
        keep = []
        for r in self.rk:
            r[3] += 15 * dt
            r[0] += r[2] * dt
            r[1] += r[3] * dt
            self.buf.add(r[0], r[1], (255, 200, 120))
            if r[3] > -2:
                hue = r[4]
                for _ in range(34):
                    a, s = random.uniform(0, 2 * math.pi), random.uniform(4, 17)
                    self.pt.append([r[0], r[1], math.cos(a) * s, math.sin(a) * s * 0.55, random.uniform(0.9, 1.7),
                                    hsv(hue + random.uniform(-0.05, 0.05), 0.8, 1)])
            else:
                keep.append(r)
        self.rk = keep
        alive = []
        for p in self.pt:
            p[3] += 8 * dt
            p[2] *= math.exp(-dt * 1.5)
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[4] -= dt
            if p[4] > 0:
                self.buf.add(p[0], p[1], mul(p[5], min(1, p[4])))
                alive.append(p)
        self.pt = alive
        clock_big(f, now, (60, 60, 75), outline=None)
        self.buf.blit(f)


@reg("snieg")
class Snow(Clock):
    """Śnieg pada i osiada na cyfrach oraz na ziemi; po chwili topnieje, a z nową minutą zsuwa się z cyfr."""

    def __init__(self):
        self.fl, self.set_ = [], {}

    def draw(self, f, now, t, dt):
        digits = set(centered(now.strftime("%H:%M")))
        if random.random() < 30 * dt:
            self.fl.append([random.uniform(0, W), -1.0, random.uniform(2.5, 5), random.random() * 6])
        solid = lambda x, y: y >= H or (x, y) in digits or (x, y) in self.set_
        keep = []
        for q in self.fl:
            nx = q[0] + math.sin(t * 1.5 + q[3]) * dt * 2
            ny = q[1] + q[2] * dt
            cx, cy = int(nx), int(ny)
            if cy >= 0 and solid(cx, cy + 1) and not solid(cx, cy):
                self.set_[(cx, cy)] = t + random.uniform(20, 50)
            else:
                q[0], q[1] = nx % W, ny
                keep.append(q)
        self.fl = keep
        for (x, y), end in list(self.set_.items()):
            if end < t or (x, y) in digits or not solid(x, y + 1):
                del self.set_[(x, y)]
                if end >= t:
                    self.fl.append([x + 0.5, y + 0.5, 4, 0])
        f.outline(list(digits), (0, 0, 10))
        f.draw(list(digits), (120, 170, 255))
        for (x, y) in self.set_:
            f.set(x, y, (240, 245, 255))
        for q in self.fl:
            f.add(q[0], q[1], (200, 200, 220))


@reg("burza")
class Storm(Clock):
    """Burza: ukośny deszcz, kłębiące się chmury i pioruny, w których błysku lepiej widać godzinę."""

    def __init__(self):
        self.drops = [[random.uniform(0, W), random.uniform(0, H)] for _ in range(80)]
        self.flash, self.nxt, self.bolt = 0.0, 2.0, []

    def draw(self, f, now, t, dt):
        if t > self.nxt:
            self.nxt = t + random.uniform(2, 7)
            self.flash = 1.0
            x = random.uniform(10, W - 10)
            self.bolt = [(x, 0)]
            for y in range(1, H):
                x += random.choice((-1, 0, 1))
                self.bolt.append((x, y))
        self.flash = max(0.0, self.flash - dt * 3)
        fl = self.flash * (1 if int(self.flash * 10) % 3 else 0.4)
        for y in range(H):
            for x in range(W):
                c = mul((30, 30, 45), noise2(x * 0.07 + t * 0.3, y * 0.4) * (1 - y / 5)) if y < 5 else (3, 3, 8)
                f.px[y][x] = lerp(c, (140, 140, 180), fl * 0.6)
        for d in self.drops:
            d[0] = (d[0] - 12 * dt) % W
            d[1] += 45 * dt
            if d[1] >= H:
                d[1] -= H
            f.add(d[0], d[1], (60, 80, 130))
            f.add(d[0] + 0.3, d[1] - 1, (25, 30, 55))
        if self.flash > 0.4:
            for x, y in self.bolt:
                f.set(x, y, (255, 255, 255))
                f.add(x + 1, y, (80, 60, 140))
        clock_big(f, now, lerp((70, 75, 100), (255, 255, 255), fl))


@reg("gwiazdy")
class Stars(Clock):
    """Nocne niebo: migoczące gwiazdy, pasmo Drogi Mlecznej i od czasu do czasu spadająca gwiazda."""

    def __init__(self):
        rnd = random.Random(21)
        self.st = [(rnd.randrange(W), rnd.randrange(H), rnd.random() * 6, rnd.uniform(0.3, 1)) for _ in range(90)]
        self.shoot, self.nxt = None, 3

    def draw(self, f, now, t, dt):
        for y in range(H):
            for x in range(W):
                band = math.exp(-((y - 6 + (x - 60) * 0.06) ** 2) / 6)
                f.px[y][x] = mul((25, 18, 40), band * (0.5 + noise2(x * 0.2, y * 0.5)))
        for x, y, ph, b in self.st:
            f.add(x, y, mul((200, 200, 255), b * (0.5 + 0.5 * math.sin(t * 2.5 + ph))))
        if self.shoot is None and t > self.nxt:
            self.shoot = [random.uniform(20, W), random.uniform(0, 3), t]
        if self.shoot:
            sx, sy, st = self.shoot
            p = (t - st) * 60
            for k in range(10):
                f.add(sx - p + k, sy + (p - k) * 0.12, mul((255, 255, 220), 1 - k / 10))
            if p > 70:
                self.shoot, self.nxt = None, t + random.uniform(3, 10)
        clock_big(f, now, (170, 190, 255))


@reg("ocean")
class Ocean(Clock):
    """Morze o prawdziwej porze dnia: fale z pianą, odbicie słońca lub księżyca i żaglówka na horyzoncie."""

    def draw(self, f, now, t, dt):
        elev, solar = sun_position(now)
        top, hor = sky_colors(elev)
        for y in range(6):
            for x in range(W):
                f.px[y][x] = mul(lerp(top, hor, y / 5), 0.5)
        sx = W / 4 + (solar % 24) / 24 * W / 2
        disc(f, sx, 3.5, 1.8, (255, 220, 120) if elev > -3 else (220, 220, 200))
        for x in range(W):
            h = 5.5 + math.sin(x * 0.15 + t * 1.2) * 0.6 + math.sin(x * 0.37 - t * 0.8) * 0.3
            for y in range(int(h), H):
                wc = lerp((0, 50, 110), (0, 12, 40), (y - h) / 6)
                if abs(x - sx) < 3 + (y - 5) and hash1(x * 17 + y * 5 + int(t * 6)) > 0.7:
                    wc = lerp(wc, (255, 230, 150), 0.6)
                f.set(x, y, mul(wc, 0.5 + 0.5 * clamp((elev + 10) / 20)))
            if math.sin(x * 0.15 + t * 1.2) > 0.85:
                f.set(x, h, (200, 220, 255))
        bx = (t * 3) % (W + 20) - 10
        by = 5.5 + math.sin(bx * 0.15 + t * 1.2) * 0.6 - 1
        f.line(bx, by - 3, bx, by, (150, 120, 80))
        f.line(bx + 1, by - 3, bx + 3, by - 1, (230, 230, 230))
        f.line(bx - 2, by, bx + 3, by, (120, 60, 30))
        small_time(f, now, x=1)


@reg("dym")
class Smoke(Clock):
    """Dym z kadzidła snuje się w górę; cyfry wyłaniają się tam, gdzie dym jest gęsty."""

    def draw(self, f, now, t, dt):
        dset = set(centered(now.strftime("%H:%M")))
        for y in range(H):
            for x in range(W):
                d = noise2(x * 0.07 + math.sin(t * 0.2), y * 0.35 + t * 0.9) * noise2(x * 0.03 - t * 0.1, 3 + t * 0.2) * 1.8
                if (x, y) in dset:
                    f.px[y][x] = mul((255, 190, 120), 0.35 + clamp(d) * 0.8)
                else:
                    f.px[y][x] = lerp((4, 4, 8), (90, 95, 120), clamp(d) * 0.8)


@reg("kalejdoskop")
class Kaleido(Clock):
    """Kalejdoskop: kolorowy wzór odbity czterokrotnie, obracający się i zmieniający barwy."""

    def draw(self, f, now, t, dt):
        for y in range(6):
            for x in range((W + 1) // 2):
                v = (math.sin(x * 0.25 + t) + math.sin(y * 0.9 - t * 1.3) + math.sin((x + y) * 0.2 + t * 0.7)
                     + math.sin(math.hypot(x - W / 4 + math.sin(t) * W / 6, y * 3) * 0.3))
                c = hsv(v * 0.15 + t * 0.05, 0.9, clamp(0.25 + 0.75 * (math.sin(v * 2) * 0.5 + 0.5)))
                for xx, yy in ((x, y), (W - 1 - x, y), (x, H - 1 - y), (W - 1 - x, H - 1 - y)):
                    f.px[yy][xx] = c
        clock_big(f, now)


@reg("labirynt")
class Maze(Clock):
    """Labirynt: generuje się na oczach, potem wąż szuka wyjścia; po rozwiązaniu wyświetla się godzina."""

    CW, CH = (W - 1) // 2, 5

    def __init__(self):
        self.reset()

    def reset(self):
        self.open, self.stack, self.seen = set(), [(0, 0)], {(0, 0)}
        self.open.add((1, 1))
        self.state, self.path, self.pi, self.hold = "gen", [], 0, 0

    def draw(self, f, now, t, dt):
        if self.state == "gen":
            for _ in range(8):
                if not self.stack:
                    self.state = "solve"
                    self.path = self.solve()
                    break
                cx, cy = self.stack[-1]
                nb = [(cx + dx, cy + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                      if 0 <= cx + dx < self.CW and 0 <= cy + dy < self.CH and (cx + dx, cy + dy) not in self.seen]
                if nb:
                    nx, ny = random.choice(nb)
                    self.seen.add((nx, ny))
                    self.open.add((cx + nx + 1, cy + ny + 1))
                    self.open.add((2 * nx + 1, 2 * ny + 1))
                    self.stack.append((nx, ny))
                else:
                    self.stack.pop()
        elif self.state == "solve":
            self.pi += 40 * dt
            if self.pi >= len(self.path):
                self.state, self.hold = "hold", t
        elif t - self.hold > 5:
            self.reset()
        for y in range(11):
            for x in range(2 * self.CW + 1):
                f.set(x, y, (0, 0, 0) if (x, y) in self.open else (15, 30, 90))
        if self.state == "gen" and self.stack:
            cx, cy = self.stack[-1]
            f.set(2 * cx + 1, 2 * cy + 1, (255, 255, 255))
        for i, (x, y) in enumerate(self.path[:int(self.pi)]):
            f.set(x, y, hsv(i / 300, 0.9, 1))
        if self.state == "hold":
            clock_big(f, now)

    def solve(self):
        start, goal = (1, 1), (2 * self.CW - 1, 2 * self.CH - 1)
        prev, q = {start: None}, [start]
        for p in q:
            if p == goal:
                break
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (p[0] + dx, p[1] + dy)
                if n in self.open and n not in prev:
                    prev[n] = p
                    q.append(n)
        path, p = [], goal
        while p is not None and p in prev:
            path.append(p)
            p = prev[p]
        return path[::-1]


@reg("waz")
class Snake(Clock):
    """Gra w węża, w którą gra komputer: szuka najkrótszej drogi do jabłka i rośnie, aż się zapętli."""

    GW, GH = W // 2, 6

    def __init__(self):
        self.reset()

    def reset(self):
        self.body = [(10, 3), (9, 3), (8, 3)]
        self.food, self.acc = self.new_food(), 0.0

    def new_food(self):
        while True:
            p = (random.randrange(self.GW), random.randrange(self.GH))
            if p not in getattr(self, "body", []):
                return p

    def next_dir(self):
        head, body = self.body[0], set(self.body[:-1])
        prev, q = {head: None}, [head]
        for p in q:
            if p == self.food:
                break
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (p[0] + dx, p[1] + dy)
                if 0 <= n[0] < self.GW and 0 <= n[1] < self.GH and n not in body and n not in prev:
                    prev[n] = p
                    q.append(n)
        if self.food in prev:
            p = self.food
            while prev[p] != head:
                p = prev[p]
            return p
        free = [(head[0] + dx, head[1] + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        free = [n for n in free if 0 <= n[0] < self.GW and 0 <= n[1] < self.GH and n not in body]
        return random.choice(free) if free else None

    def draw(self, f, now, t, dt):
        self.acc += dt * 14
        while self.acc >= 1:
            self.acc -= 1
            n = self.next_dir()
            if n is None:
                self.reset()
                break
            self.body.insert(0, n)
            if n == self.food:
                self.food = self.new_food()
            else:
                self.body.pop()
        fx, fy = self.food
        f.rect(fx * 2, fy * 2, fx * 2 + 1, fy * 2 + 1, (255, 30, 30) if int(t * 4) % 2 else (150, 0, 0))
        for i, (x, y) in enumerate(self.body):
            f.rect(x * 2, y * 2, x * 2 + 1, y * 2 + 1, (200, 255, 200) if i == 0 else hsv(0.3 + i * 0.005, 0.9, 0.9 - i * 0.004))
        small_time(f, now, c=(200, 200, 200))


@reg("arkanoid")
class Arkanoid(Clock):
    """Arkanoid, w którym cegiełkami są cyfry godziny: piłka je rozbija, a z nową minutą ściana się odbudowuje."""

    def __init__(self):
        self.txt, self.bricks, self.sparks = None, set(), []
        self.bx, self.by, self.vx, self.vy, self.px = 60.0, 10.0, 34.0, -26.0, 60.0

    def draw(self, f, now, t, dt):
        txt = now.strftime("%H:%M")
        if txt != self.txt:
            self.txt, self.bricks = txt, set(text_px(txt, (W - text_w(txt)) // 2, 0))
        self.px += clamp(self.bx - self.px, -50 * dt, 50 * dt)
        self.px = clamp(self.px, 5, W - 6)
        steps = int(max(abs(self.vx), abs(self.vy)) * dt / 0.4) + 1
        for _ in range(steps):
            h = dt / steps
            nx, ny = self.bx + self.vx * h, self.by + self.vy * h
            if nx < 0 or nx >= W:
                self.vx = -self.vx
                continue
            if ny < 0:
                self.vy = abs(self.vy)
                continue
            if ny >= 11:
                if abs(nx - self.px) <= 6:
                    self.vy = -abs(self.vy)
                    self.vx = clamp(self.vx + (nx - self.px) * 4, -45, 45)
                else:
                    self.bx, self.by, self.vy = self.px, 10.0, -26.0
                continue
            cell = (int(nx), int(ny))
            if cell in self.bricks:
                self.bricks.discard(cell)
                for _ in range(4):
                    self.sparks.append([cell[0], cell[1], random.uniform(-15, 15), random.uniform(-15, 15), 0.4])
                if (int(self.bx), int(ny)) in self.bricks or int(self.by) != int(ny):
                    self.vy = -self.vy
                else:
                    self.vx = -self.vx
                continue
            self.bx, self.by = nx, ny
        for x, y in self.bricks:
            f.set(x, y, hsv(x / W, 0.8, 1))
        keep = []
        for s in self.sparks:
            s[0] += s[2] * dt
            s[1] += s[3] * dt
            s[4] -= dt
            if s[4] > 0:
                f.add(s[0], s[1], mul((255, 220, 120), s[4] * 2))
                keep.append(s)
        self.sparks = keep
        f.rect(self.px - 5, 11, self.px + 5, 11, (200, 200, 220))
        f.set(self.bx, self.by, (255, 255, 255))


@reg("najezdzcy")
class Invaders(Clock):
    """Space Invaders: szereg kosmitów maszeruje w rytm kroków, działko strzela samo, godzina jako wynik w rogu."""

    SPR = [["#...#", ".###.", "##.##", "#####", "#.#.#"], [".#.#.", ".###.", "##.##", "#####", ".#.#."]]

    def __init__(self):
        self.dead, self.shots, self.boom = {}, [], []
        self.gx, self.last = 60.0, 0

    def draw(self, f, now, t, dt):
        step = int(t / 0.35)
        n_inv = 8 if not NARROW else max(2, (W - 25) // 10)
        span = max(2, W - 25 - n_inv * 10)
        ox = abs(step % (2 * span) - span)
        frame = self.SPR[step % 2]
        alive = []
        for i in range(n_inv):
            x = ox + i * 10
            if self.dead.get(i, 0) > t:
                continue
            alive.append((i, x))
            sprite(f, frame, x, 1, {"#": hsv(0.3 + i * 0.08, 0.8, 1)})
        if alive:
            tx = alive[int(t / 3) % len(alive)][1] + 2
            self.gx += clamp(tx - self.gx, -30 * dt, 30 * dt)
            if t - self.last > 0.7 and abs(tx - self.gx) < 1:
                self.shots.append([self.gx, 9.0])
                self.last = t
        keep = []
        for s in self.shots:
            s[1] -= 30 * dt
            hit = next((i for i, x in alive if x <= s[0] < x + 5 and 1 <= s[1] < 6), None)
            if hit is not None:
                self.dead[hit] = t + 4
                self.boom.append([s[0], 3, t])
            elif s[1] > -1:
                f.set(s[0], s[1], (255, 255, 100))
                keep.append(s)
        self.shots = keep
        self.boom = [b for b in self.boom if t - b[2] < 0.4]
        for bx, by, bt in self.boom:
            r = (t - bt) * 12
            for k in range(8):
                a = k * math.pi / 4
                f.add(bx + math.cos(a) * r, by + math.sin(a) * r * 0.6, (255, 150, 0))
        sprite(f, ["..#..", "#####"], self.gx - 2, 10, {"#": (0, 255, 120)})
        small_time(f, now, c=(255, 255, 255))


@reg("pacman")
class Pacman(Clock):
    """Pac-Man zjada kropki uciekając duszkom, aż trafi na dużą pigułkę – wtedy role się odwracają."""

    GC = [(255, 0, 0), (255, 180, 255), (0, 255, 255), (255, 180, 80)]

    def __init__(self):
        self.reset()

    def reset(self):
        self.x, self.dir, self.mode = -8.0, 1, "chase"
        self.gh = [[-20.0 - i * 10, True] for i in range(4)]
        self.dots = set(range(4, W, 5))
        self.pill = True

    def draw(self, f, now, t, dt):
        for x in range(W):
            f.set(x, 0, (30, 30, 200))
            f.set(x, 11, (30, 30, 200))
        spd = 22
        if self.mode == "chase":
            self.x += spd * dt
            for g in self.gh:
                g[0] += spd * 0.97 * dt
            if self.pill and self.x >= W - 20:
                self.pill, self.mode, self.fr = False, "fright", t
        else:
            self.x -= spd * 1.25 * dt
            for g in self.gh:
                if g[1]:
                    g[0] -= spd * 0.8 * dt
                    if abs(g[0] - self.x) < 3:
                        g[1] = False
            if self.x < -40:
                self.reset()
        self.dots = {d for d in self.dots if not (abs(d - self.x) < 2)}
        for d in self.dots:
            f.rect(d, 5, d + 1, 6, (255, 200, 150))
        if self.pill:
            disc(f, W - 19.5, 5.5, 1.6, (255, 200, 150) if int(t * 4) % 2 else (120, 90, 60))
        for i, (gx, alive) in enumerate(self.gh):
            if not alive:
                continue
            col = self.GC[i] if self.mode == "chase" else ((40, 40, 255) if t - self.fr < 5 or int(t * 6) % 2 else (230, 230, 255))
            for oy in range(7):
                for ox in range(7):
                    inside = (oy < 3 and (ox - 3) ** 2 + (oy - 3) ** 2 <= 10) or (3 <= oy < 6) or (oy == 6 and (ox + int(t * 6)) % 2 == 0)
                    if inside:
                        f.set(gx + ox, 2 + oy, col)
            for ex in (1, 4):
                f.set(gx + ex + (1 if self.mode == "chase" else 0), 4, (255, 255, 255))
        mouth = abs(math.sin(t * 12)) * 0.8
        for oy in range(-3, 4):
            for ox in range(-3, 4):
                if ox * ox + oy * oy <= 11:
                    a = math.atan2(oy, ox * self.dir) if (ox or oy) else 0
                    if abs(a) > mouth or ox * self.dir <= 0:
                        f.set(self.x + ox, 5.5 + oy, (255, 230, 0))
        small_time(f, now, y=1, c=(255, 255, 255))
        if self.mode == "chase" and self.x > W + 50:
            self.reset()


@reg("dino")
class Dino(Clock):
    """Dinozaur z Chrome'a biegnie przez pustynię i sam przeskakuje kaktusy; wynik to godzina."""

    DINO = ["....####", "....#.##", "....####", "#..###..", "#.#####.", "######..", ".####...", ".#..#..."]
    DINO2 = DINO[:-1] + ["..#..#.."]

    def __init__(self):
        self.y, self.vy, self.cacti, self.nxt, self.off = 0.0, 0.0, [], 1.0, 0.0

    def draw(self, f, now, t, dt):
        spd = 40
        self.off += spd * dt
        if t > self.nxt:
            self.cacti.append([W + 2, random.randint(4, 6), random.choice((1, 2))])
            self.nxt = t + random.uniform(1.1, 2.6)
        for c in self.cacti:
            c[0] -= spd * dt
        self.cacti = [c for c in self.cacti if c[0] > -6]
        near = any(8 < c[0] - 10 < 16 for c in self.cacti)
        if self.y == 0 and near:
            self.vy = -30
        self.vy += 80 * dt
        self.y = min(0.0, self.y + self.vy * dt)
        for i in range(12):
            cx = (20 + i * 40 - self.off * 0.3) % (W + 20) - 10
            f.rect(cx, 2 + i % 2, cx + 5, 2 + i % 2, (40, 40, 50))
        for x in range(W):
            f.set(x, 11, (110, 110, 110) if (x + int(self.off)) % 7 else (60, 60, 60))
        for cx, ch, n in self.cacti:
            for k in range(n):
                x = cx + k * 3
                f.rect(x, 11 - ch, x, 10, (40, 200, 60))
                f.set(x - 1, 11 - ch + 2, (40, 200, 60))
                f.set(x + 1, 11 - ch + 1, (40, 200, 60))
        spr = self.DINO if int(t * 10) % 2 or self.y < 0 else self.DINO2
        sprite(f, spr, 8, 3 + self.y, {"#": (220, 220, 220)})
        small_time(f, now, c=(200, 200, 200), outline=None)


@reg("flappy")
class Flappy(Clock):
    """Flappy Bird na autopilocie: ptaszek przelatuje między rurami, godzina jako wynik u góry."""

    def __init__(self):
        self.y, self.vy, self.pipes, self.off = 5.0, 0.0, [[W + 5, 5]], 0.0

    def draw(self, f, now, t, dt):
        spd = 24
        self.off += spd * dt
        for p in self.pipes:
            p[0] -= spd * dt
        if self.pipes[-1][0] < W - 32:
            self.pipes.append([W + 2, random.randint(3, 7)])
        self.pipes = [p for p in self.pipes if p[0] > -6]
        ahead = next((p for p in self.pipes if p[0] + 4 >= 20), self.pipes[0])
        if self.y > ahead[1] + 0.6 and self.vy > -2:
            self.vy = -13
        self.vy += 45 * dt
        self.y = clamp(self.y + self.vy * dt, 0, 10)
        for px, gap in self.pipes:
            for y in range(H - 1):
                if not (gap - 2.5 <= y <= gap + 2.5):
                    f.rect(px, y, px + 3, y, (40, 180, 40))
                    f.set(px, y, (120, 255, 120))
        for x in range(W):
            f.set(x, 11, (160, 120, 50) if (x + int(self.off)) % 4 else (120, 90, 30))
        wing = int(t * 10) % 2
        sprite(f, [".##.", "####" if wing else "#.##", ".##."], 19, self.y - 1, {"#": (255, 220, 0)})
        f.set(22, self.y, (255, 100, 0))
        s = now.strftime("%H:%M")
        f.text(s, (W - text_w(s, SMALL)) // 2, 0, (255, 255, 255), SMALL, (0, 0, 0))


@reg("wyscig")
class Race(Clock):
    """Wyścig: czerwone auto wyprzedza ruch na dwupasmówce, w tle przesuwają się wzgórza."""

    def __init__(self):
        self.lane, self.ly, self.cars, self.off = 0, 6.0, [], 0.0

    def draw(self, f, now, t, dt):
        spd = 50
        self.off += spd * dt
        for y in range(5):
            for x in range(W):
                f.px[y][x] = lerp((10, 30, 70), (60, 80, 120), y / 5)
        for x in range(W):
            hh = 3 + noise1((x + self.off * 0.2) * 0.05) * 2
            for y in range(int(hh), 5):
                f.set(x, y, (20, 60, 25))
        for y in range(5, H):
            for x in range(W):
                f.px[y][x] = (28, 28, 30)
        for x in range(W):
            f.set(x, 5, (160, 160, 160))
            f.set(x, 11, (160, 160, 160))
            if (x + int(self.off)) % 10 < 5:
                f.set(x, 8, (200, 200, 120))
        if random.random() < 0.9 * dt:
            self.cars.append([W + 5, random.choice((0, 1)), random.uniform(15, 30), hsv(random.random(), 0.7, 1)])
        for c in self.cars:
            c[0] -= (spd - c[2]) * dt
        self.cars = [c for c in self.cars if c[0] > -10]
        ahead = [c for c in self.cars if c[1] == self.lane and 20 < c[0] < 42]
        if ahead and not any(c[1] != self.lane and 10 < c[0] < 40 for c in self.cars):
            self.lane = 1 - self.lane
        ty = 6 if self.lane == 0 else 9
        self.ly += clamp(ty - self.ly, -10 * dt, 10 * dt)
        for cx, lane, _, col in self.cars:
            sprite(f, [".###.", "#####"], cx, 6 if lane == 0 else 9, {"#": col})
        sprite(f, [".####..", "#######"], 14, self.ly, {"#": (255, 30, 30)})
        f.set(21, self.ly + 1, (255, 255, 180))
        small_time(f, now, x=1, y=0)


@reg("pociag")
class Train(Clock):
    """Parowóz ciągnie wagony, a na każdym wagonie jedna cyfra aktualnej godziny; z komina bucha para."""

    LOCO = ["...........##...", "..######...##...", "..#....#.######.", "..#....#########", "################",
            ".o..o.......o..o"]

    def __init__(self):
        self.puffs = []

    def draw(self, f, now, t, dt):
        for y in range(H):
            for x in range(W):
                f.px[y][x] = lerp((20, 40, 80), (70, 90, 120), y / H)
        for x in range(W):
            hh = 7 + noise1(x * 0.04) * 2.5
            for y in range(int(hh), 11):
                f.set(x, y, (25, 70, 30))
            f.set(x, 11, (90, 70, 60) if x % 3 else (50, 40, 35))
        txt = now.strftime("%H:%M")
        spd, length = 22, 17 + len(txt) * 13
        period = (W + length + 50) / spd
        x0 = W - (t % period) * spd
        sprite(f, self.LOCO, x0, 5, {"#": (180, 30, 30), "o": (60, 60, 60)})
        if random.random() < 8 * dt and -5 < x0 < W:
            self.puffs.append([x0 + 12, 4, t])
        for i, ch in enumerate(txt):
            wx = x0 + 17 + i * 13
            f.rect(wx, 5, wx + 11, 9, (30, 60, 150))
            f.set(wx + 2, 10, (60, 60, 60))
            f.set(wx + 9, 10, (60, 60, 60))
            f.text(ch, wx + (12 - text_w(ch, SMALL)) // 2, 5, (255, 255, 255), SMALL)
            f.set(wx - 1, 8, (80, 80, 80))
        keep = []
        for p in self.puffs:
            age = t - p[2]
            if age < 1.5:
                keep.append(p)
                disc(f, p[0] + age * 6, p[1] - age * 2.5, 0.8 + age, mul((200, 200, 210), (1.5 - age) / 3), add=True)
        self.puffs = keep


@reg("miasto")
class City(Clock):
    """Miasto o prawdziwej porze dnia: niebo według słońca, okna zapalają się wieczorem, po ulicy jeżdżą auta."""

    def __init__(self):
        rnd = random.Random(8)
        self.bld, x = [], 0
        while x < W:
            w = rnd.randint(5, 12)
            self.bld.append((x, w, rnd.randint(4, 9)))
            x += w + rnd.randint(0, 1)
        self.cars = [[rnd.uniform(0, W), rnd.choice((-1, 1)) * rnd.uniform(10, 25)] for _ in range(4)]

    def draw(self, f, now, t, dt):
        elev, solar = sun_position(now)
        top, hor = sky_colors(elev)
        night = clamp((-elev - 2) / 8)
        for y in range(H):
            for x in range(W):
                f.px[y][x] = mul(lerp(top, hor, y / H), 0.45)
        if night > 0.3:
            for i in range(25):
                f.add(hash1(i) * W, hash1(i + 7) * 5, mul((150, 150, 180), night * 0.6))
        hr = now.hour + now.minute / 60
        p_lit = 0.65 if 17 <= hr < 23 else 0.15 if hr >= 23 or hr < 6 else 0.35 if hr < 8 else 0.05
        for bx, bw, bh in self.bld:
            for x in range(bx, bx + bw):
                for y in range(H - 1 - bh, H - 1):
                    f.set(x, y, mul((20, 20, 28), 1 - night * 0.4))
            for x in range(bx + 1, bx + bw - 1, 2):
                for y in range(H - bh, H - 2, 2):
                    if noise1(x * 7.3 + y * 3.1 + t * 0.02) < p_lit:
                        f.set(x, y, (255, 200, 90) if hash1(x * 3 + y) > 0.3 else (180, 210, 255))
        for x in range(W):
            f.set(x, 11, (15, 15, 15))
        for c in self.cars:
            c[0] = (c[0] + c[1] * dt) % W
            f.set(c[0], 11, (255, 255, 200) if c[1] > 0 else (255, 20, 20))
            f.set(c[0] - (1 if c[1] > 0 else -1), 11, (60, 60, 60))
        small_time(f, now, x=1, y=0, c=(230, 230, 255))


@reg("las")
class Forest(Clock):
    """Las w trzech warstwach przesuwa się jak z okna pociągu; niebo według prawdziwej pory dnia, nocą świetliki."""

    def draw(self, f, now, t, dt):
        elev, _ = sun_position(now)
        top, hor = sky_colors(elev)
        night = clamp((-elev - 2) / 8)
        for y in range(H):
            for x in range(W):
                f.px[y][x] = mul(lerp(top, hor, y / H), 0.45)
        for layer, (spd, base, col) in enumerate(((3, 5, (0, 90, 60)), (8, 7, (20, 170, 40)), (16, 9, (60, 230, 60)))):
            c = lerp(col, ((0, 0, 90), (0, 40, 130), (0, 90, 160))[layer], night)
            off = t * spd
            for x in range(W):
                wx = x + off
                tree = hash1(int(wx / 6) + layer * 1000)
                cx = int(wx / 6) * 6 + 3 - off
                hgt = base - 1 - int(tree * 3)
                dist = abs(x - cx)
                top_y = hgt + dist * 1.5
                for y in range(int(top_y), H):
                    f.set(x, y, c)
        if night > 0.3:
            for i in range(10):
                f.add(noise1(i * 9 + t * 0.1) * W, 3 + noise1(i * 5 + t * 0.15) * 8,
                      mul((200, 255, 60), night * max(0, math.sin(t * 2 + i)) ** 4))
        else:
            for i in range(3):
                bx = (t * (8 + i * 3) + i * 40) % (W + 10) - 5
                by = 2 + i + math.sin(t * 3 + i)
                f.set(bx, by, (20, 20, 20))
                f.set(bx - 1, by - (int(t * 8) % 2), (20, 20, 20))
                f.set(bx + 1, by - (int(t * 8) % 2), (20, 20, 20))
        small_time(f, now, c=(240, 240, 240))


@reg("gory")
class Mountains(Clock):
    """Pasma gór z ośnieżonymi szczytami, chmury i krążący orzeł; niebo według prawdziwej pory dnia."""

    def draw(self, f, now, t, dt):
        elev, _ = sun_position(now)
        top, hor = sky_colors(elev)
        dim = 1 - clamp((-elev - 2) / 8) * 0.7
        for y in range(H):
            for x in range(W):
                f.px[y][x] = mul(lerp(top, hor, y / H), 0.45)
        for layer, (spd, base, amp, col) in enumerate(((1.5, 4, 5, (60, 60, 90)), (4, 6, 4, (40, 50, 60)), (9, 9, 3, (20, 35, 25)))):
            for x in range(W):
                n = noise1((x + t * spd) * 0.04 + layer * 10) * amp + noise1((x + t * spd) * 0.15 + layer * 5) * 1.2
                hy = base + amp / 2 - n
                for y in range(max(0, int(hy)), H):
                    snow = layer == 0 and y < hy + 1.2 and hy < 4.5
                    f.set(x, y, mul((230, 230, 240) if snow else col, dim))
        for x in range(W):
            for y in range(0, 4):
                v = noise2(x * 0.05 - t * 0.3, y * 0.5 + 20)
                if v > 0.6:
                    f.add(x, y, mul((120, 120, 130), (v - 0.6) * 2 * dim))
        ex, ey = W / 2 + math.cos(t * 0.4) * W / 4, 3 + math.sin(t * 0.8)
        wing = int(t * 4) % 2
        f.set(ex, ey, (20, 15, 10))
        f.set(ex - 1, ey - wing, (20, 15, 10))
        f.set(ex + 1, ey - wing, (20, 15, 10))
        small_time(f, now, c=(255, 255, 255))


@reg("dna")
class DNA(Clock):
    """Podwójna helisa DNA obraca się; szczeble to pary zasad A-T i G-C w swoich kolorach."""

    BASES = [((255, 60, 60), (60, 255, 60)), ((60, 120, 255), (255, 220, 0))]

    def draw(self, f, now, t, dt):
        back, front = [], []
        for x in range(W):
            ph = x * 0.18 + t * 2
            y1, y2 = 5.5 + math.sin(ph) * 4.5, 5.5 - math.sin(ph) * 4.5
            z = math.cos(ph)
            (front if z > 0 else back).append((x, y1, (80, 160, 255), z))
            (back if z > 0 else front).append((x, y2, (255, 110, 200), -z))
            if x % 4 == 0:
                pair = self.BASES[int(hash1(x // 4 + int(t * 2 // 30) * 100) * 2)]
                k = 0.35 + 0.3 * abs(z)
                lo, hi = sorted((y1, y2))
                for y in range(int(lo) + 1, int(hi) + 1):
                    f.set(x, y, mul(pair[0] if y < 5.5 else pair[1], k))
        for x, y, c, z in back:
            f.set(x, y, mul(c, 0.3 + 0.2 * (1 + z)))
        for x, y, c, z in front:
            f.set(x, y, mul(c, 0.6 + 0.4 * z))
        s = now.strftime("%H:%M")
        f.text(s, (W - text_w(s, SMALL)) // 2, 3, (255, 255, 255), SMALL, (0, 0, 0))


@reg("oscyloskop")
class Scope(Clock):
    """Oscyloskop rysuje figury Lissajous z fosforową poświatą; proporcja częstotliwości zmienia się co minutę."""

    RATIOS = [(1, 2), (2, 3), (3, 4), (3, 5), (4, 5), (1, 3), (2, 5), (5, 6)]

    def __init__(self):
        self.buf = Persist()

    def draw(self, f, now, t, dt):
        a, b = self.RATIOS[now.minute % len(self.RATIOS)]
        self.buf.fade(math.exp(-dt * 5))
        d = t * 0.3
        for i in range(160):
            s = t * 2 + i * dt * 2 / 160
            self.buf.add(W / 2 + math.sin(a * s + d) * (W / 2 - 2), 5.5 + math.sin(b * s) * 5.4, (30, 160, 60))
        for x in range(0, W, 10):
            for y in range(0, H, 3):
                f.set(x, y, (0, 25, 10))
        self.buf.blit(f)
        f.text(f"{a}:{b}", 1, 0, (60, 200, 90), SMALL)
        small_time(f, now, c=(60, 200, 90), outline=None)


@reg("equalizer")
class Equalizer(Clock):
    """Korektor graficzny jak w wieży stereo: słupki skaczą w rytm 120 BPM, a kreski szczytów powoli opadają."""

    def __init__(self):
        self.n = W // 5
        self.h, self.peak = [0.0] * self.n, [0.0] * self.n

    def draw(self, f, now, t, dt):
        beat = max(0, math.sin(t * math.pi * 2 * 2)) ** 8
        for i in range(self.n):
            target = 11 * clamp(noise1(i * 0.5 + t * 2.5) * 0.7 + beat * 0.5 * (1 - i / self.n) + 0.05)
            self.h[i] += (target - self.h[i]) * (0.6 if target > self.h[i] else 0.15)
            self.peak[i] = max(self.peak[i] - dt * 6, self.h[i])
            x = i * 5
            for y in range(H - int(self.h[i]), H):
                c = (0, 230, 60) if y > 6 else (255, 210, 0) if y > 2 else (255, 40, 30)
                f.rect(x, y, x + 3, y, c)
            f.rect(x, H - 1 - int(self.peak[i]), x + 3, H - 1 - int(self.peak[i]), (220, 220, 255))
        small_time(f, now, x=1)


@reg("ekg")
class ECG(Clock):
    """Monitor EKG: zielona linia z załamkami P-QRS-T, serce bije w rytm; obok tętno i godzina."""

    def __init__(self):
        self.tw = W - 30
        self.buf, self.pos = [5.5] * self.tw, 0.0

    @staticmethod
    def wave(p):
        g = lambda c, w, a: a * math.exp(-((p - c) / w) ** 2)
        return g(0.12, 0.03, 0.9) - g(0.28, 0.012, 0.8) + g(0.31, 0.012, 5.5) - g(0.34, 0.012, 1.8) + g(0.55, 0.05, 1.4)

    def draw(self, f, now, t, dt):
        bpm = 64 + 8 * math.sin(t * 0.05)
        prev = int(self.pos)
        self.pos = (self.pos + 60 * dt) % self.tw
        for k in range(prev, prev + int(60 * dt) + 2):
            x = k % self.tw
            p = ((t - (int(self.pos) - k) / 60) * bpm / 60) % 1
            self.buf[x] = 7.5 - self.wave(p)
        head = int(self.pos)
        for x in range(self.tw):
            gap = (x - head) % self.tw
            if gap < 5:
                continue
            k = 1 if gap > self.tw - 10 else 0.7
            y0 = self.buf[x]
            y1 = self.buf[(x + 1) % self.tw] if (x + 1 - head) % self.tw >= 5 else y0
            f.line(x, y0, x + 0.4, y1, mul((40, 255, 90), k))
        f.set(head - 1, self.buf[(head - 1) % self.tw], (220, 255, 220))
        p = (t * bpm / 60) % 1
        k = 1 if 0.28 < p < 0.4 else 0.45
        sprite(f, [".#.#.", "#####", "#####", ".###.", "..#.."], W - 26, 0, {"#": mul((255, 30, 50), k)})
        f.text(f"{bpm:.0f}", W - text_w(f"{bpm:.0f}", SMALL), 0, (40, 255, 90), SMALL)
        small_time(f, now, y=6, c=(200, 200, 200))


@reg("mrowka")
class Ant(Clock):
    """Mrówki Langtona (wariant LRRL, 4 kolory): z prostych reguł wyrastają szalone wzory; restart co 3 minuty."""

    RULE = "LRRL"
    PAL = [(0, 0, 0), (255, 60, 60), (60, 200, 255), (255, 210, 60)]

    def __init__(self):
        self.reset(0)

    def reset(self, t):
        self.g = [[0] * W for _ in range(H)]
        self.ants = [[W // 4, 6, 0], [W // 2, 6, 1], [3 * W // 4, 6, 2]]
        self.t0 = t

    def draw(self, f, now, t, dt):
        if t - self.t0 > 180:
            self.reset(t)
        for _ in range(12):
            for a in self.ants:
                x, y, d = a
                c = self.g[y][x]
                d = (d + (1 if self.RULE[c] == "R" else -1)) % 4
                self.g[y][x] = (c + 1) % len(self.RULE)
                dx, dy = ((0, -1), (1, 0), (0, 1), (-1, 0))[d]
                a[0], a[1], a[2] = (x + dx) % W, (y + dy) % H, d
        for y in range(H):
            for x in range(W):
                f.px[y][x] = mul(self.PAL[self.g[y][x]], 0.6)
        for x, y, _ in self.ants:
            f.set(x, y, (255, 255, 255))
        small_time(f, now)


@reg("piasek")
class Sand(Clock):
    """Symulacja sypiącego się piasku: ziarna zatrzymują się na cyfrach godziny; gdy jest pełno, dno się otwiera."""

    def __init__(self):
        self.g = [[None] * W for _ in range(H)]
        self.drain, self.txt = 0.0, None

    def draw(self, f, now, t, dt):
        digits = set(centered(now.strftime("%H:%M")))
        if now.strftime("%H:%M") != self.txt:
            self.txt = now.strftime("%H:%M")
            for x, y in digits:
                self.g[y][x] = None
        g = self.g
        filled = sum(1 for row in g for c in row if c is not None)
        if filled > 600 and self.drain <= 0:
            self.drain = 2.0
        if self.drain > 0:
            self.drain -= dt
            g[H - 1] = [None] * W
        for k in range(3):
            x = int(clamp(W / 2 + math.sin(t * 0.5 + k * 2) * (W / 2 - 4), 0, W - 1))
            if g[0][x] is None and (x, 0) not in digits:
                g[0][x] = hsv(t * 0.03 + random.uniform(-0.02, 0.02), 0.7, random.uniform(0.6, 1))
        for y in range(H - 2, -1, -1):
            xs = list(range(W))
            random.shuffle(xs)
            for x in xs:
                c = g[y][x]
                if c is None:
                    continue
                free = lambda nx, ny: 0 <= nx < W and g[ny][nx] is None and (nx, ny) not in digits
                if free(x, y + 1):
                    g[y + 1][x], g[y][x] = c, None
                else:
                    for dx in random.sample((-1, 1), 2):
                        if free(x + dx, y + 1):
                            g[y + 1][x + dx], g[y][x] = c, None
                            break
        for y in range(H):
            for x in range(W):
                if g[y][x] is not None:
                    f.px[y][x] = g[y][x]
        f.draw(list(digits), (255, 255, 255))


@reg("kule")
class Balls(Clock):
    """Kolorowe kulki odbijają się od ścian i od siebie nawzajem (zderzenia sprężyste), w tle godzina."""

    def __init__(self):
        self.b = [[random.uniform(5, W - 5), random.uniform(2, 8), random.uniform(-30, 30), random.uniform(-10, 10),
                   hsv(i / 8, 0.8, 1)] for i in range(8)]

    def draw(self, f, now, t, dt):
        clock_big(f, now, (40, 40, 60), outline=None)
        r = 1.6
        for b in self.b:
            b[3] += 30 * dt
            b[0] += b[2] * dt
            b[1] += b[3] * dt
            if b[0] < r or b[0] > W - r:
                b[2] = -b[2]
                b[0] = clamp(b[0], r, W - r)
            if b[1] > H - r:
                b[1], b[3] = H - r, -abs(b[3]) * 0.95
                if abs(b[3]) < 8:
                    b[3] = -random.uniform(14, 20)
            if b[1] < r:
                b[1], b[3] = r, abs(b[3])
        for i in range(len(self.b)):
            for j in range(i + 1, len(self.b)):
                a, c = self.b[i], self.b[j]
                dx, dy = c[0] - a[0], c[1] - a[1]
                d = math.hypot(dx, dy)
                if 0 < d < 2 * r:
                    nx, ny = dx / d, dy / d
                    p = (a[2] - c[2]) * nx + (a[3] - c[3]) * ny
                    if p > 0:
                        a[2] -= p * nx
                        a[3] -= p * ny
                        c[2] += p * nx
                        c[3] += p * ny
        for x, y, _, _, col in self.b:
            for oy in (-1, 0, 1):
                for ox in (-1, 0, 1):
                    d = math.hypot(ox, oy)
                    if d <= 1.2:
                        f.set(x + ox, y + oy, mul(col, 1 - d * 0.4))


@reg("kregi")
class Ripples(Clock):
    """Krople wpadają do wody, a rozchodzące się kręgi nakładają się na siebie; godzina faluje pod powierzchnią."""

    def __init__(self):
        self.drops, self.nxt = [], 0

    def draw(self, f, now, t, dt):
        if t > self.nxt:
            self.drops.append((random.uniform(0, W), random.uniform(0, H), t))
            self.nxt = t + random.uniform(0.3, 1.0)
        self.drops = [d for d in self.drops if t - d[2] < 4]
        dset = set(centered(now.strftime("%H:%M")))
        for y in range(H):
            for x in range(W):
                v = 0.0
                for dx_, dy_, dt0 in self.drops:
                    age = t - dt0
                    d = math.hypot(x - dx_, (y - dy_) * 2)
                    front = age * 18
                    if d < front:
                        v += math.sin((d - front) * 0.9) * math.exp(-age * 0.9) * math.exp(-d * 0.03)
                base = (160, 210, 255) if (x, y) in dset else (0, 30, 70)
                f.px[y][x] = lerp(base, (120, 200, 255), clamp(v * 0.5 + 0.1))


@reg("wir")
class Vortex(Clock):
    """Hipnotyczna tęczowa spirala wciągająca do środka, z godziną w oku cyklonu."""

    def draw(self, f, now, t, dt):
        for y in range(H):
            row = f.px[y]
            for x in range(W):
                dx, dy = x - W / 2, (y - 5.5) * 4
                r = math.hypot(dx, dy) + 1
                a = math.atan2(dy, dx)
                v = math.sin(a * 3 + math.log(r) * 4 - t * 3)
                row[x] = hsv(a / (2 * math.pi) + t * 0.05, 0.85, clamp(0.5 + 0.5 * v) * clamp(r / 30))
        clock_big(f, now)


@reg("synthwave")
class Synthwave(Clock):
    """Retro synthwave: pasiasty zachód słońca, neonowe góry i siatka pędząca pod horyzont."""

    def draw(self, f, now, t, dt):
        for y in range(7):
            for x in range(W):
                f.px[y][x] = lerp((20, 0, 40), (120, 0, 80), y / 6)
        for y in range(1, 7):
            for x in range(W):
                d = math.hypot(x - W / 2, (y - 6.5) * 1.3)
                if d < 5.8 and not (y >= 4 and (y + int(t * 3)) % 2 == 0):
                    f.set(x, y, lerp((255, 230, 0), (255, 0, 140), (y - 1) / 6))
        for x in range(W):
            m = max(0, 3 - abs((x % 40) - 20) * 0.25) if abs(x - W / 2) > 20 else 0
            for y in range(int(7 - m), 7):
                f.set(x, y, (40, 0, 60))
            if m > 0:
                f.set(x, 7 - m, (255, 0, 200))
        for y in range(7, H):
            for x in range(W):
                f.px[y][x] = (5, 0, 12)
        for k in range(1, 12):
            z = k - (t * 2 % 1)
            y = 6.5 + 6 / z
            if y < H:
                for x in range(W):
                    f.set(x, y, (200, 0, 180))
        for i in range(-12, 13):
            f.line(W / 2 + i * 3, 7, W / 2 + i * 16, 11, (140, 0, 160))
        s = now.strftime("%H:%M")
        for x, y in text_px(s, 3, -1, TXT):
            f.set(x, y, lerp((0, 255, 255), (255, 0, 255), (y - 1) / 7))


@reg("pory")
class Seasons(Clock):
    """Pora roku według daty: wiosną kwiaty i motyle, latem pszczoły, jesienią spadające liście, zimą śnieg i bałwan."""

    def __init__(self):
        self.p = []

    def draw(self, f, now, t, dt):
        md = now.month * 100 + now.day
        season = "zima" if md < 321 or md >= 1222 else "wiosna" if md < 621 else "lato" if md < 923 else "jesien"
        sky = {"zima": (8, 12, 30), "wiosna": (10, 30, 50), "lato": (20, 50, 90), "jesien": (30, 20, 20)}[season]
        ground = {"zima": (200, 200, 220), "wiosna": (30, 140, 30), "lato": (60, 150, 20), "jesien": (120, 70, 20)}[season]
        for y in range(H):
            for x in range(W):
                f.px[y][x] = mul(sky, 1 - y / 20)
        for x in range(W):
            f.set(x, 11, ground)
        if season == "wiosna":
            for i in range(12):
                x = 5 + i * 10
                f.set(x, 10, (20, 120, 20))
                f.set(x, 9, hsv(hash1(i), 0.7, 1))
            for i in range(4):
                bx, by = noise1(i * 7 + t * 0.2) * W, 2 + noise1(i * 3 + t * 0.3) * 6
                wing = int(t * 8 + i) % 2
                f.set(bx - 1, by - wing, hsv(i / 4, 0.8, 1))
                f.set(bx + 1, by - wing, hsv(i / 4, 0.8, 1))
                f.set(bx, by, (60, 40, 20))
        elif season == "lato":
            disc(f, W - 10, 2.5, 2.5, (255, 220, 60))
            for i in range(6):
                bx = noise1(i * 11 + t * 0.4) * W
                by = 3 + noise1(i * 5 + t * 0.9) * 7
                f.set(bx, by, (255, 210, 0) if int(t * 10 + i) % 2 else (40, 30, 0))
            for x in range(0, W, 2):
                f.set(x, 10, (40, 170, 30))
        else:
            rate = 12 if season == "zima" else 5
            if random.random() < rate * dt:
                col = (240, 240, 255) if season == "zima" else random.choice([(255, 120, 0), (200, 40, 0), (230, 180, 0), (140, 70, 20)])
                self.p.append([random.uniform(0, W), -1.0, random.uniform(2, 4), random.random() * 6, col])
            keep = []
            for q in self.p:
                q[1] += q[2] * dt
                q[0] += math.sin(t * 1.5 + q[3]) * dt * (6 if season == "jesien" else 2)
                if q[1] < 11:
                    keep.append(q)
                    f.set(q[0], q[1], q[4])
            self.p = keep
            if season == "zima":
                disc(f, W - 10, 8.5, 2.5, (230, 230, 240))
                disc(f, W - 10, 4.5, 1.8, (230, 230, 240))
                f.set(W - 10, 4, (255, 120, 0))
                f.rect(W - 12, 1, W - 8, 2, (20, 20, 20))
        clock_big(f, now, (255, 255, 255))


@reg("planety")
class Planets(Clock):
    """Układ Słoneczny z prawdziwym położeniem planet na dziś (średnie długości orbitalne); po kolei podpisujemy każdą planetę."""

    P = [("MERKURY", 0.387, 252.25, 4.09233, (180, 160, 140)), ("WENUS", 0.723, 181.98, 1.60213, (255, 220, 150)),
         ("ZIEMIA", 1.0, 100.46, 0.98561, (60, 140, 255)), ("MARS", 1.524, 355.45, 0.52403, (255, 80, 40)),
         ("JOWISZ", 5.203, 34.40, 0.08309, (230, 180, 120)), ("SATURN", 9.537, 49.94, 0.03346, (230, 210, 140)),
         ("URAN", 19.19, 313.23, 0.01173, (140, 220, 230)), ("NEPTUN", 30.07, 304.88, 0.00598, (80, 110, 255))]

    def draw(self, f, now, t, dt):
        days = (now - dtm.datetime(2000, 1, 1, 12, tzinfo=dtm.timezone.utc)).total_seconds() / 86400
        for name, a, l0, n, col in self.P:
            rs = math.sqrt(a) * 10 * W / 120
            for k in range(0, 360, 4):
                f.add(W / 2 + rs * math.cos(math.radians(k)), 5.5 + rs * math.sin(math.radians(k)) * 0.1 * 120 / W, (8, 8, 14))
        disc(f, W / 2, 5.5, 1.7, (255, 210, 60))
        sel = int(t / 3) % len(self.P)
        for i, (name, a, l0, n, col) in enumerate(self.P):
            L = math.radians((l0 + n * days) % 360)
            rs = math.sqrt(a) * 10 * W / 120
            x, y = W / 2 + rs * math.cos(L), 5.5 + rs * math.sin(L) * 0.1 * 120 / W
            f.set(x, y, col)
            if i == sel:
                for ox, oy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                    f.add(x + ox, y + oy, mul(col, 0.5 + 0.5 * math.sin(t * 6)))
                f.text(name, 1, 0, col, SMALL, (0, 0, 0))
        if not NARROW:
            small_time(f, now, c=(150, 150, 170))


# co ludzik robi z nudów: wyłączone zajęcia i jak często (ustawiane w TUI, zapisywane w konfiguracji)
LUDZIK = {"lvl": {}, "len": {}, "freq": 2, "char": 0, "how": 0, "side": 0, "next": None}  # lvl: częstość zajęcia
# (0–3, brak = normalnie); len: długość zajęcia (0–3, brak = normalnie); freq: przerwy między zajęciami; char: postać
# (LUDZIK_CHARS); how: sposób przestawiania godziny (0 = losowo, potem LUDZIK_HOWS); side: strona (LUDZIK_SIDES);
# next: zajęcie wymuszone jako następne (przycisk ▶, nie zapisywane)
LUDZIK_HOWS = ["przepychanie", "malarz", "zapadnia", "bazooka", "kopniak", "zamiatanie", "magik", "spawacz", "lina",
               "holowanie", "obrót"]
LUDZIK_SIDES = ["dowolnie", "prawa", "lewa"]  # gdzie spaceruje: obie strony albo głównie jedna (na drugą na chwilę)
LUDZIK_FREQ = [("nigdy", None), ("rzadko", (20, 40)), ("normalnie", (4, 10)), ("często", (1, 4)), ("bez przerwy", (0, 0.5))]
LUDZIK_LVL = ["wył.", "rzadko", "normalnie", "często"]
LVL_WEIGHT = [0, 1, 3, 9]                     # zajęcia: waga losowania
LUDZIK_LEN = ["krótko", "normalnie", "długo", "bardzo długo"]
LEN_MUL = [0.4, 1, 1.8, 3]                    # długość: mnożnik czasu zajęcia (rowerem i autem – okrążeń)
BANNER_EVERY = [None, 10, 5, 2]               # transparent z pogodą: co ile minut
WALK_REST = [None, (8, 16), (2, 6), (0.5, 2)]  # spacer: ile stoi między spacerami (s)
CROSS_P = [0, 0.15, 0.35, 0.7]                # przechodzenie: jaka część spacerów kończy się po drugiej stronie
AWAY_REST = (1, 4)                            # ustawiona strona: ile stoi po drugiej stronie, zanim wróci (s)


# postacie: kolory kasku/włosów (Y), skóry (S), oczu (E), zamkniętych oczu (C), ust (M), koszulki (B), spodni (P)
# i butów (O). Oczy i usta świecą – zgaszona dioda w twarzy wygląda jak dziura.
LUDZIK_CHARS = [
    ("robotnik", {"Y": (255, 200, 0), "S": (255, 180, 130), "E": (30, 70, 200), "C": (150, 90, 60),
                  "M": (200, 40, 50), "B": (230, 40, 40), "P": (40, 90, 230), "O": (210, 210, 210)}),
    ("strażak", {"Y": (230, 30, 20), "S": (255, 180, 130), "E": (30, 70, 200), "C": (150, 90, 60),
                 "M": (200, 40, 50), "B": (220, 170, 30), "P": (95, 95, 115), "O": (120, 70, 30)}),
    ("Mikołaj", {"Y": (220, 20, 20), "S": (255, 180, 130), "E": (30, 70, 200), "C": (150, 90, 60),
                 "M": (240, 240, 240), "B": (220, 20, 20), "P": (220, 20, 20), "O": (110, 70, 40)}),  # M = broda
    ("robot", {"Y": (150, 160, 185), "S": (110, 120, 145), "E": (255, 40, 30), "C": (110, 20, 15),
               "M": (0, 210, 255), "B": (170, 180, 205), "P": (90, 100, 125), "O": (70, 80, 100)}),
    ("kosmita", {"Y": (90, 220, 70), "S": (90, 220, 70), "E": (170, 0, 255), "C": (40, 110, 30),
                 "M": (20, 100, 20), "B": (130, 50, 210), "P": (180, 185, 200), "O": (130, 50, 210)}),
]


THUMB = threading.local()
LUDZIK_STATUS = {}  # co ludzik robi teraz i co będzie następne (do panelu WWW), pisze Worker.report()  # .on = rysujemy podgląd na listę efektów: bez skutków ubocznych (wiadomości, ▶)


def ludzik_next():
    """Zajęcie wymuszone przyciskiem ▶ – ale nie dla podglądu na liście (zabrałby je ludzikowi na panelu)."""
    return None if getattr(THUMB, "on", False) else LUDZIK["next"]


def ludzik_lvl(name):
    return LUDZIK["lvl"].get(name, 2)


def ludzik_off():
    """Wyłączone zajęcia."""
    return {a for a in LUDZIK_ACTS if not ludzik_lvl(a)}


def ludzik_len(name):
    return LUDZIK["len"].get(name, 1)


@reg("ludzik")
class Worker(Clock):
    """Robotnik w kasku sam przestawia cyfry, na jeden z 11 sposobów (przepycha, maluje wałkiem, zapadnia, bazooka,
    kopniak, zamiatanie, czary, spawanie laserem, lina, holowanie autem, obrót korbą) – nowe cyfry wchodzą równo z pełną
    minutą; z nudów spaceruje po obu stronach zegara, czyta, śpi w łóżku, je, gra na gitarze, podbija piłkę, buduje
    zamek z piasku, goni balonik, głaszcze kota albo psa, gasi płonący śmietnik (przyjeżdża wozem strażackim),
    żongluje, zamiata, robi pajacyki i pompki, strzela przez zegar do tarczy z łuku, pistoletu albo bazooki (seriami), jeździ rowerem, autem, traktorem z przyczepami i kombajnem (kilka okrążeń:
    wyjeżdża za krawędź i wraca z drugiej strony, za cyframi); co kilka minut przeciąga transparent z pogodą.
    Zajęcia trwają tyle, ile zostało do przestawiania cyfr (najwyżej górna granica z TRICKS)."""

    POSES = {k: [r.ljust(max(map(len, v)), ".") for r in v] for k, v in {  # twarzą w lewo; kolumna 0 = dłonie
        "stoi": ["..YYYYY.", ".YYYYYYY", "..SESES.", "..SSSSS.", "..SMMMS.", "..BBBBB.", ".BBBBBBB", ".SBBBBBS",
                 "..PPPPP.", "..PP.PP.", ".OOO.OOO"],
        "idzie1": ["..YYYYY.", ".YYYYYYY", "..SESES.", "..SSSSS.", "..SMMMS.", "..BBBBB.", ".BBBBBBB", "SSBBBBBS",
                   "..PPPPP.", ".PP...PP", "OOO...OO"],
        "idzie2": ["..YYYYY.", ".YYYYYYY", "..SESES.", "..SSSSS.", "..SMMMS.", "..BBBBB.", "..BBBBBB", "..SBBBS.",
                   "..PPPPP.", "...PPP..", "..OOOO.."],
        "pcha1": ["...YYYYY.", "..YYYYYYY", "...SESES.", "...SSSSS.", "...SSMSS.", "SSBBBBBB.", "SSBBBBBBB", "....BBBBB",
                  "....PPPPP", "...PP...PP", "..OOO....OO"],
        "pcha2": ["...YYYYY.", "..YYYYYYY", "...SESES.", "...SSSSS.", "...SSMSS.", "SSBBBBBB.", "SSBBBBBBB", "....BBBBB",
                  "....PPPPP", ".....PPPP.", "....OOO.OO"],
        "ciagnie1": [".....YYYYY", "....YYYYYYY", ".....SESES", ".....SSSSS", ".....SSMSS", "SSBBBBBBB.", "SSBBBBBBBB",
                     ".....BBBBB", "....PPPPP.", "..PP...PP.", ".OOO..OOO."],
        "ciagnie2": [".....YYYYY", "....YYYYYYY", ".....SESES", ".....SSSSS", ".....SSMSS", "SSBBBBBBB.", "SSBBBBBBBB",
                     ".....BBBBB", "....PPPPP.", "....PPPP..", "...OOOOO.."],
        "macha": ["..YYYYY.SS", ".YYYYYYYSS", "..SESESBB.", "..SSSSSB..", "..SRRRSB..", "..BBBBB...", ".BBBBBB...",
                  ".SBBBBB...", "..PPPPP...", "..PP.PP...", ".OOO.OOO.."],
        "pajac": ["S.YYYYY.S", "BYYYYYYYB", "B.SESES.B", ".BSSSSSB.", ".BSMMMSB.", "..BBBBB..", "..BBBBB..", "..BBBBB..",
                  ".PPPPPPP.", "PP.....PP", "OO.....OO"],
        "pajac_pol": ["..YYYYY..", ".YYYYYYY.", "..SESES..", "..SSSSS..", "..SMMMS..", "SBBBBBBBS", "..BBBBB..", "..BBBBB..",
                      "..PPPPP..", ".PP...PP.", ".OO...OO."],
        "kuca": ["........", "........", "..YYYYY.", ".YYYYYYY", "..SESES.", "..SSSSS.", "..SSMSS.", "SSBBBBB.", "..BBBBB.",
                 ".PPPPPPP", ".OO...OO"],
        "taniec": ["..YYYYY.SS", ".YYYYYYYSS", "..SESESBB.", "..SSSSSB..", "..SRRRSB..", "..BBBBB...", ".BBBBBB...",
                   "SSBBBBB...", "..PPPPP...", "..PP..PPP.", ".OOO...OO."],
        "pompka1": ["............"] * 7 + ["YYSSBBBB....", "YYESBBBBPP..", "....S...PPP.", "....S.....OO"],
        "pompka2": ["............"] * 8 + [".....B......", "YYSSBBBBPPP.", "YYESBBBBPPOO"],
        "czyta1": ["...YYYYY.", "..YYYYYYY", "...SESES.", "...SSSSS.", "...SMMMS.", "WWWSBBBBB", "KKKSBBBBB", "....BBBBS",
                   "...PPPPP.", "...PP.PP.", "..OOO.OOO"],
        "czyta2": ["...YYYYY.", "..YYYYYYY", "...SESES.", "...SSSSS.", ".W.SMMMS.", "W.WSBBBBB", "KKKSBBBBB", "....BBBBS",
                   "...PPPPP.", "...PP.PP.", "..OOO.OOO"],
        "spi1": ["................"] * 5 + ["T...............", "T.YYY...........", "T.YSCS..........",
                                            "TWYSSSJJJJJJJJ.T", "TWWWJJJJJJJJJJJT", "TTTTTTTTTTTTTTTT"],
        "spi2": ["................"] * 5 + ["T...............", "T.YYY...........", "T.YSCS..JJJJJ...",
                                            "TWYSSSJJJJJJJJ.T", "TWWWJJJJJJJJJJJT", "TTTTTTTTTTTTTTTT"],
        "gitara1": ["H.......YYYYY.", "TH.....YYYYYYY", ".TT.....SESES.", "...TT...SSSSS.", "...SSTT.SMMMS.",
                    "....BBTUUBBBB.", ".....BUUUUBBBB", "......UUkUUSBS", ".....uUUUUUuP.", "......uuuuuPP.",
                    ".......OOO.OOO"],  # gryf ukośnie w górę, pudło z otworem, prawa ręka nad otworem
        "gitara2": ["H.......YYYYY.", "TH.....YYYYYYY", ".TT.....SESES.", "...TT...SSSSS.", "...SSTT.SRRRS.",
                    "....BBTUUBBBB.", ".....BUUUUBBBB", "......UUkUUBBS", ".....uUUUUSuP.", "......uuuuuPP.",
                    ".......OOO.OOO"],  # ręka w dół – uderza w struny
        "kopie": ["..YYYYY.", ".YYYYYYY", "..SESES.", "..SSSSS.", "..SMMMS.", "..BBBBB.", ".BBBBBBB", ".SBBBBBS",
                  "..PPPPP.", "OOPP.PP.", ".....OOO"],
        "kuca2": ["........", "........", "..YYYYY.", ".YYYYYYY", "..SESES.", "..SSSSS.", "..SSMSS.", "..BBBBB.",
                  "SSBBBBB.", ".PPPPPPP", ".OO...OO"],
        "je1": ["...YYYYY.", "..YYYYYYY", "...SESES.", ".AASSSSS.", ".AASRRRS.", "..SBBBBBB", "...BBBBBB", "...BBBBBS",
                "...PPPPP.", "...PP.PP.", "..OOO.OOO"],
        "je2": ["...YYYYY.", "..YYYYYYY", "...SESES.", "...SSSSS.", "...SMMMS.", ".AABBBBBB", ".AASBBBBB", "...BBBBBS",
                "...PPPPP.", "...PP.PP.", "..OOO.OOO"],
        "je3": ["...YYYYY.", "..YYYYYYY", "...SESES.", "...SSSSS.", "...SSMSS.", ".AABBBBBB", ".AASBBBBB", "...BBBBBS",
                "...PPPPP.", "...PP.PP.", "..OOO.OOO"],
        "zongl1": ["..YYYYY..", ".YYYYYYY.", "..SESES..", "..SSSSS..", "..SRRRS..", "..BBBBB..", ".SBBBBBB.", "..BBBBBS.",
                   "..PPPPP..", "..PP.PP..", ".OOO.OOO."],
        "zongl2": ["..YYYYY..", ".YYYYYYY.", "..SESES..", "..SSSSS..", "..SRRRS..", "..BBBBB..", ".BBBBBBS.", ".SBBBBB..",
                   "..PPPPP..", "..PP.PP..", ".OOO.OOO."],
        "zamiata1": ["...YYYYY.", "..YYYYYYY", "...SESES.", "...SSSSS.", "...SMMMS.", "...BBBBB.", "..SBBBBBB", "..TSBBBBS",
                     ".T.PPPPP.", "T..PP.PP.", "GG.OOO.OOO"],
        "zamiata2": ["...YYYYY.", "..YYYYYYY", "...SESES.", "...SSSSS.", "...SMMMS.", "...BBBBB.", "..SBBBBBB", "..TSBBBBS",
                     "..TPPPPP.", "..TPP.PP.", ".GGGOO.OOO"],
        "luk1": ["......YYYYY.", ".....YYYYYYY", "..T...SESES.", ".T.W..SSSSS.", ".T..W.SMMMS.", "DTTTTSBBBBB.",
                 ".TSBBBBBBBB.", ".T.W..BBBBBS", "..T...PPPPP.", "......PP.PP.", ".....OOO.OOO"],
        "luk2": ["......YYYYY.", ".....YYYYYYY", "..T...SESES.", ".TW...SSSSS.", ".TW...SMMMS.", ".TW..SBBBBB.",
                 ".TSBBBBBBBB.", ".TW...BBBBBS", "..T...PPPPP.", "......PP.PP.", ".....OOO.OOO"],
        "pist1": ["....YYYYY.", "...YYYYYYY", "....SESES.", "....SSSSS.", "....SMMMS.", "DDSBBBBBB.", ".D..BBBBBB",
                  "....BBBBBS", "....PPPPP.", "....PP.PP.", "...OOO.OOO"],
        "pist2": ["....YYYYY.", "...YYYYYYY", "....SESES.", "....SSSSS.", "DDSBSSMSS.", ".D.BBBBBB.", "....BBBBBB",
                  "....BBBBBS", "....PPPPP.", "....PP.PP.", "...OOO.OOO"],
        "baz1": ["....YYYYY..", "...YYYYYYY.", "....SESES..", "....SSSSS..", "....SMMMS..", "DVVVVVVVVVV", "DVVVVVVVVVV",
                 "...SBBBBBS.", "....PPPPP..", "....PP.PP..", "...OOO.OOO."],
        "baz2": ["....YYYYY..", "...YYYYYYY.", "....SESES..", "....SSSSS..", "....SSMSS..", "DVVVVVVVVVV", "DVVVVVVVVVV",
                 "...SBBBBBS.", "....PPPPP..", "....PP.PP..", "...OOO.OOO."],
        "rower1": ["........YYYYY....", ".......YYYYYYY...", "........SESES....", "........SSSSS....", "........SMMMS....",
                   "..FSSSSSBBBBB....", ".QFQ...BBBBBBQQQ.", "Q.F.QFFFFPPPQ...Q", "Q.H.Q.FF.PP.Q.H.Q",
                   "Q...Q..FHPFFQ...Q", ".QQQ....OO...QQQ."],
        "rower2": ["........YYYYY....", ".......YYYYYYY...", "........SESES....", "........SSSSS....", "........SMMMS....",
                   "..FSSSSSBBBBB....", ".QFQ...BBBBBBQQQ.", "Q.F.QFFFFPPPQ...Q", "Q.H.Q.FF..PPQ.H.Q",
                   "Q...Q..FHFPPQ...Q", ".QQQ......OO.QQQ."],
        "auto": ["....................", "....................", "......NNNNNNNN......", ".....NXXYYYYYXN.....",
                 "....NXXXSESESXXN....", "...NXXXXSSSSSXXXN...", ".NNNNNNNNNNNNNNNNNN.", "LNNNNNNNNNNNNNNNNNNN",
                 "NNNQQQNNNNNNNNQQQNNR", "..QQHQQ......QQHQQ..", "...QQQ........QQQ..."],
    }.items()}
    TRACTOR = [".................", "........NNNNNNNN.", "...D....X.YYY..N.", "...D....XESSY..N.", "...D....XSSSS..N.",
               ".NNDNNNNNBBBBBBN.", "LNNNNNNNQQQQQNNN.", "NNNNNNN{a}NN.", ".QQ.NNNQGGHGGQNT.", "Q{c}Q...{b}.TT",
               ".QQ.....QQQQQ...."]
    HAY = ["..............", "..............", "..............", "....GGGGGG....", "..GGTGGTGGTGG.",
           ".NNNNNNNNNNNNN", ".NNNNNNNNNNNNN", ".DDDDDDDDDDDDD", "...QQQ...QQQ..", "TT.Q{h}Q...Q{h}Q..", "...QQQ...QQQ.."]
    PUMPKINS = HAY[:3] + ["....UU..UU....", "..UUUUUUUUUU.."] + HAY[5:]
    COMBINE = ["........NNNNNNN...........", "........X.YYY.NNNNNNNNN...", "........XESSY.NNNNNNNNNDDD",
               "........XSSSS.NNNNNNNNN...", "........XBBBBNNNNNNNNNN...", "......NNNNNNNNNNNNNNNNNN..",
               "....NNNQQQQQNNNNNNNNNNNNN.", "....NN{a}NNNNNNNNNNNN.", "DDDDDDQGGHGGQNNNNNNN.QQ...",
               "DDDDDD{b}.......Q{c}Q..", ".......QQQQQ.........QQ..."]
    for i, f_ in enumerate((dict(a="QQHGGQQ", b="QQGGHQQ", c="GG", h="H"), dict(a="QQGGHQQ", b="QQHGGQQ", c="GH", h="G"))):
        POSES[f"traktor{i + 1}"], POSES[f"kombajn{i + 1}"] = [], []  # dwie klatki: kręcące się koła
        for x_, y_, z_ in zip(TRACTOR, HAY, PUMPKINS):  # traktor z przyczepą siana i przyczepą dyń
            POSES[f"traktor{i + 1}"].append((x_ + y_ + z_).format(**f_))
        for x_ in COMBINE:
            POSES[f"kombajn{i + 1}"].append(x_.format(**f_))
    POSES["woz"] = ["......................", "..ZZZZ................", ".ZXYYYZ.WWWWWWWWWWWWW.",
                    ".ZXSESZ.W.W.W.W.W.W.W.", ".ZXSSSZZZZZZZZZZZZZZZ.", "LZZZZZZZWWWWWWWWWWWWZ.",
                    "ZZZZZZZZZZZZZZZZZZZZZ.", "ZZZZZZZZZZZZZZZZZZZZZD", ".ZQQQZZZZZZZZZZZQQQZZ.",
                    "..QHQ...........QHQ...", "..QQQ...........QQQ..."]  # wóz strażacki
    del TRACTOR, HAY, PUMPKINS, COMBINE, i, f_, x_, y_, z_
    POSES["glowa1"], POSES["glowa2"] = POSES["stoi"][::-1], POSES["idzie1"][::-1]  # stanie na głowie, nogi machają
    # nudzi się: nazwa -> (czas od–do w s, pozy jednej rundy, czas jednej pozy, co druga odbita w lustrze);
    # czas zaokrągla się do pełnych rund, a gdy do przestawiania cyfr zostało mniej – tyle rund, ile się zmieści
    TRICKS = {
        "pajacyki": ((6, 14), ("stoi", "pajac_pol", "pajac", "pajac_pol"), 0.14, False),
        "przysiady": ((6, 12), ("stoi", "kuca"), 0.5, False),
        "taniec": ((8, 18), ("taniec", "taniec"), 0.35, True),
        "pompki": ((6, 14), ("pompka1", "pompka2"), 0.45, False),
        "na głowie": ((4, 9), ("glowa1", "glowa2"), 0.3, False),
        "czytanie": ((15, 35), ("czyta1",) * 7 + ("czyta2",), 0.25, False),
        "spanie": ((20, 40), ("spi1", "spi2"), 0.9, False),  # w łóżku
        "jedzenie": ((10, 20), ("je1", "je2", "je3", "je2", "je3"), 0.35, False),
        "gitara": ((12, 30), ("gitara1", "gitara2"), 0.25, False),         # nuty lecą daleko przed nim
        "piłka": ((10, 22), ("kopie", "stoi"), 0.35, False),        # runda = jedno podbicie
        "piasek": ((20, 40), ("kuca2", "kuca"), 0.4, False),        # buduje zamek z piasku
        "balon": ((15, 30), ("stoi",), 1.0, False),                   # sceny: rysuje je scene_*()
        "pożar": ((32, 40), ("stoi",), 1.0, False),
        "zwierzak": ((14, 26), ("stoi",), 1.0, False),
        "żonglerka": ((10, 22), ("zongl1", "zongl2"), 0.25, False),
        "zamiatanie": ((10, 20), ("zamiata1", "zamiata2"), 0.4, False),
        "łuk": ((11, 25), ("luk1",) * 4 + ("luk2",) * 8, 0.3, False),  # runda = jedna strzała
        "pistolet": ((8, 20), ("pist1",) * 3 + ("pist2", "pist1", "pist1", "pist1") * 3 + ("pist1",) * 4, 0.2, False),
        "bazooka": ((11, 22), ("baz1",) * 4 + ("baz2",) * 2 + ("baz1",) * 12, 0.3, False),
    }
    # sceny: ludzik się w nich przemieszcza -> (najmniejsza szerokość miejsca po jego stronie w px, najkrótszy czas w s)
    SCENES = {"balon": (26, 12), "pożar": (40, 32), "zwierzak": (21, 10)}
    SCENE_FN = {"balon": "balon", "pożar": "pozar", "zwierzak": "zwierzak"}
    REACH = {"piłka": 3, "piasek": 16, "gitara": 14}  # ile px przed ludzikiem zajmują rzeczy (piłka, piaskownica)
    CASTLE = ["#.#...#.#", "###...###", "###.#.###", "#########", "####.####", "###...###"]  # rzędy 4–9
    RIDES = {"rower": (("rower1", "rower2"), 14, (2, 4)), "auto": (("auto",), 22, (2, 5)),
             "traktor": (("traktor1", "traktor2"), 8, (1, 2)), "kombajn": (("kombajn1", "kombajn2"), 6, (1, 2))}  # pozy, px/s, okrążenia
    RIDE_OFF = 25  # tyle px za krawędzią pojazd znika, zanim wróci z drugiej strony (długie – więcej, ride_off())
    # strzelanie przez zegar do tarczy po drugiej stronie: poza strzału (pierwsza z serii = strzał) i prędkość pocisku (px/s)
    SHOTS = {"łuk": ("luk2", 55), "pistolet": ("pist2", 120), "bazooka": ("baz2", 50)}
    ARROW_DY = (0, -1, 1, -2, 2, 0, 1, -1)  # strzały wbijają się w różne miejsca tarczy
    HOLES = ((1, 0), (1, -2), (1, 2), (0, -1), (2, 1), (0, 1), (2, -1), (1, -1), (1, 1), (0, 0), (2, 0), (0, -2),
             (2, 2), (1, -3), (1, 3))  # dziury po kulach (x w tarczy, y od środka)
    PETS = {"kot": ({"idzie1": ["......O.O.", "O.....OOO.", "O.....OEON", ".OSOSOSOO.", ".OOOOOOO..", ".O.O..O.O."],
                     "idzie2": ["......O.O.", ".O....OOO.", "O.....OEON", ".OSOSOSOO.", ".OOOOOOO..", "..OO..OO.."],
                     "siedzi1": ["......O.O.", "......OOO.", "......OEON", "O....OOOO.", "O..OOOOOO.", ".OOOOO.OO."],
                     "siedzi2": ["......O.O.", "......OOO.", "......OEON", ".....OOOO.", "O..OOOOOO.", "OOOOOO.OO."]},
                    {"O": (230, 120, 25), "S": (150, 60, 10), "E": (60, 255, 60), "N": (255, 110, 150)}),
            "pies": ({"idzie1": ["......OO...", ".....DOEOOK", "O....DOOO..", ".OOOOOOOO..", ".OOOOOOOO..", ".O.O...O.O."],
                      "idzie2": ["......OO...", ".....DOEOOK", ".O...DOOO..", ".OOOOOOOO..", ".OOOOOOOO..", "..O.O.O.O.."],
                      "siedzi1": ["......OO...", ".....DOEOOK", ".....DOOO..", "....OOOO...", "O..OOOOO...", ".OOOO.OO..."],
                      "siedzi2": ["......OO...", ".....DOEOOK", ".....DOOO..", "O...OOOO...", ".O.OOOOO...", "..OOO.OO..."]},
                     {"O": (170, 100, 40), "D": (90, 50, 20), "E": (230, 230, 230), "K": (60, 30, 30)})}
    TARGET = [".R.", "RWR", "WRW", "RYR", "WRW", "RWR", ".R.", "T.T", "T.T"]
    TARGET_PAL = {"R": (230, 30, 30), "W": (235, 235, 235), "Y": (255, 220, 0), "T": (150, 90, 40)}
    PAL = {"Y": (255, 200, 0), "S": (255, 180, 130), "E": (0, 0, 0), "M": (0, 0, 0), "R": (170, 0, 25),
           "B": (230, 40, 40), "P": (40, 90, 230), "O": (210, 210, 210), "C": (150, 90, 60), "W": (235, 235, 235),
           "K": (40, 170, 90), "A": (110, 220, 40), "T": (150, 90, 40), "G": (230, 180, 60), "D": (130, 130, 145),
           "V": (100, 125, 40), "F": (0, 200, 255), "Q": (110, 110, 120), "H": (220, 220, 230), "N": (30, 160, 60),
           "X": (110, 170, 230), "L": (255, 255, 170), "U": (215, 120, 30), "J": (70, 110, 220),
           "Z": (220, 25, 20), "u": (150, 70, 10), "k": (45, 20, 5)}
    # D broń/grot, V rura bazooki, U pudło gitary/dynie (u – cień, k – otwór), J kołdra, Z wóz strażacki
    # E oczy (mrugają), C zamknięte oko, M usta, R uśmiech (w aucie: tylne światło), W kartki/poduszka/drabina,
    # K okładka, A jabłko, T kij/gryf/łóżko/dyszel, G miotła/siano/felgi, F rama roweru, Q opony, H piasty/kołpaki,
    # N karoseria (auto, traktor, kombajn), X szyby, L reflektor
    WALK, MOVE = 10, 9  # px/s: chód i przesuwanie cyfr

    def __init__(self):
        self.shown, self.job, self.x = None, None, None
        self.goal, self.wait, self.moon = None, 0.0, False
        self.trick, self.next_trick, self.upcoming = None, None, None  # upcoming: wylosowane następne zajęcie
        self.banner, self.banner_at = None, None
        self.rate, self.prev = None, None
        self.ride, self.left, self.free = None, 60.0, 0.0  # free: s animacji do przestawiania cyfr
        self.how_seed = random.random()  # losowy sposób przestawiania: inny w każdym uruchomieniu
        self.char = None  # postać na sztywno (podgląd postaci); None = z ustawień
        self.sc = {}  # stan bieżącej sceny (balon, pożar, zwierzak)

    @staticmethod
    def layout(s):
        """x każdego znaku godziny i jej prawa krawędź."""
        xs, x = [], (W - text_w(s)) // 2
        for ch in s:
            xs.append(x)
            x += text_w(ch) + 1
        return xs, x - 2

    def plan(self, old, new, t, x=None):
        """Przestawianie cyfr; x = skąd idzie do roboty (domyślnie: tam, gdzie stoi)."""
        x = self.x if x is None else x
        xs, xr = self.layout(new)
        ch = [i for i, (a, b) in enumerate(zip(old, new)) if a != b]
        k = ch[0]  # przy przepychaniu od tej cyfry w prawo jedzie wszystko
        how = self.pick_how(new)
        stand, end, d = self.how_plan(how, old, new, xs, xr, k, ch)
        return {"old": old, "new": new, "k": k, "ch": ch, "dist": W - xs[k], "t0": t, "x0": x, "how": how,
                "xs": xs, "xr": xr, "home": xr + 1, "stand": stand, "end": end,
                "d": [abs(x - stand) / self.WALK, *d, 1.8]}

    # ---------------------------------------------------------- przestawianie godziny: 11 sposobów
    # fazy roboty: 0 dojście, 1 przygotowanie, 2 stare cyfry znikają, 3 przerwa, 4 nowe się pojawiają (zaczyna się
    # równo z pełną minutą), 5 macha. Faza 0 i 5 są wspólne, 1–4 rysuje how_<sposób>.
    def how_plan(self, how, old, new, xs, xr, k, ch):
        """-> (gdzie stoi w fazie 1, gdzie kończy, czasy faz 1–4)."""
        home, c0 = xr + 1, xs[ch[0]]
        dist = W - xs[k]
        mv = dist / max(self.MOVE, dist / 4.5)  # długi blok cyfr: szybciej, żeby zegar nie stał długo pusty
        sweep = (xr + 2 - c0) / 12
        if how == "bazooka":
            stand = clamp(xr + 16, home, W - 10)
            return stand, stand, [1.0, (stand - 1 - (c0 + xr) / 2) / 50 + 1.4, 0.5, 0.8]
        return home, home, {"przepychanie": [0.5, mv, 0.8, mv], "holowanie": [0.7, mv, 0.8, mv],
                            "malarz": [0.6, sweep, 0.5, sweep], "zapadnia": [0.8, 1.4, 0.6, 1.6],
                            "kopniak": [0.8, 1.4, 0.5, 1.2 + 0.4 * (len(ch) - 1)], "magik": [0.9, 1.6, 0.4, 1.6],
                            "zamiatanie": [0.5, 1.6, 2.2, 1.6],
                            "spawacz": [0.6, 1.8, 0.6, 2.0], "lina": [0.6, 1.6, 0.5, 2.0],
                            "obrót": [0.6, 0.8, 0.1, 0.8]}[how]

    def pick_how(self, new):
        """Sposób przestawiania: ustawiony albo losowy – ten sam przez całą minutę (plan liczy się co klatkę)."""
        if LUDZIK["how"]:
            return LUDZIK_HOWS[LUDZIK["how"] - 1]
        return random.Random(f"{self.how_seed}{new}").choice(LUDZIK_HOWS)

    @staticmethod
    def put(f, pts, c):
        """Piksele cyfr – nad ziemią (wiersz 11 to ziemia)."""
        for x, y in pts:
            if y <= 10:
                f.set(x, y, c)

    def digits(self, f, s, xs, col, skip=()):
        for i, ch in enumerate(s):
            if i not in skip:
                f.draw(text_px(ch, xs[i], 1), col)

    def pose_at(self, f, pose, x, flip=False, blink=False):
        """Poza ustawiona po twarzy (środek twarzy w x + 4)."""
        self.man(f, pose, x + self.place(pose, flip), flip, blink)

    def how_przepychanie(self, f, j, ph, p, t, col, blink):
        """Wyciąga stare cyfry za prawą krawędź i wpycha nowe (od pierwszej zmienionej w prawo jedzie wszystko)."""
        xs, k, dist, d, home = j["xs"], j["k"], j["dist"], j["d"], j["home"]
        s = j["new"] if ph >= 4 else j["old"]
        off = dist * p / d[2] if ph == 2 else dist if ph == 3 else dist * (1 - p / d[4]) if ph == 4 else 0
        for i, ch in enumerate(s):
            f.draw(text_px(ch, xs[i] + (off if i >= k else 0), 1), col)
        if ph in (2, 4) and xs[k] + off < W:  # kurz spod przesuwanych cyfr
            for q in range(3):
                f.add(xs[k] + off - 1 - q, 11, mul((140, 110, 70), hash1(int(t * 20) + q) * (1 - q / 3)))
        if ph == 1:
            self.man(f, "ciagnie2", home)
        elif ph in (2, 4):
            push = ph == 4
            self.man(f, ("pcha" if push else "ciagnie") + ("1" if int(off / 2) % 2 else "2"), home + off)
            if push:  # kropla potu
                f.set(home + off + 8, 3 + int(t * 8) % 4, (120, 190, 255))

    def how_holowanie(self, f, j, ph, p, t, col, blink):
        """Podjeżdża autem: wywozi stare cyfry na holu za prawą krawędź, wraca i wpycha nowe zderzakiem."""
        xs, k, dist, d, home = j["xs"], j["k"], j["dist"], j["d"], j["home"]
        s = j["new"] if ph >= 4 else j["old"]
        off = dist * p / d[2] if ph == 2 else dist if ph == 3 else dist * (1 - p / d[4]) if ph == 4 else 0
        for i, ch in enumerate(s):
            f.draw(text_px(ch, xs[i] + (off if i >= k else 0), 1), col)
        if ph in (1, 2):  # przodem w prawo, hol od tyłu auta do cyfr
            self.man(f, "auto", home + 2 + off, True, blink)
            f.rect(home - 1 + off, 8, home + 1 + off, 8, (150, 150, 160))
        elif ph == 4:     # przodem w lewo, zderzak przy cyfrach
            self.man(f, "auto", home + off, False, blink)
        if ph in (2, 4):  # spaliny
            back = home + off + (-1 if ph == 2 else 20)
            for q in range(3):
                e = (t * 2 + q / 3) % 1
                f.add(back + (-1 if ph == 2 else 1) * e * 6 * (-1 if ph == 2 else 1), 9 - e * 2,
                      mul(visible((90, 90, 95), 4), 1 - e))

    def how_malarz(self, f, j, ph, p, t, col, blink):
        """Zamalowuje stare cyfry wałkiem (od prawej do lewej) i maluje nowe świeżą, żółtawą farbą, która schnie."""
        xs, ch, d = j["xs"], set(j["ch"]), j["d"]
        lo, hi = xs[j["ch"][0]] - 1, j["xr"] + 1
        a = clamp(p / d[ph]) if d[ph] else 1
        rx = hi if ph == 1 else hi - (hi - lo) * a if ph == 2 else lo if ph == 3 else lo + (hi - lo) * a
        s = j["new"] if ph == 4 else j["old"]
        pose = ("ciagnie" if ph == 4 else "pcha") + ("1" if int(rx / 2) % 2 else "2")
        self.man(f, pose, rx + 1)
        self.digits(f, s, xs, col, ch)
        for i in ch:
            for x, y in text_px(s[i], xs[i], 1):
                if ph < 3 and x < rx:              # jeszcze nie zamalowane
                    f.set(x, y, col)
                elif ph == 4 and x < rx:           # świeża farba
                    f.set(x, y, lerp((255, 210, 80), col, clamp((rx - x) / 5)))
        f.rect(rx, 1, rx, 10, (80, 190, 255))      # wałek
        f.set(rx + 1, 6, (150, 90, 40))

    def how_zapadnia(self, f, j, ph, p, t, col, blink):
        """Ciągnie za dźwignię: stare cyfry zapadają się pod ziemię, nowe spadają z góry i odbijają się."""
        xs, ch, d, home = j["xs"], j["ch"], j["d"], j["home"]
        a = clamp(p / d[ph])
        tilt = -2 + 3 * a if ph == 1 else 1
        f.line(home, 10, home + tilt, 5, (150, 90, 40))
        f.set(home + tilt, 4, (230, 40, 40))
        self.man(f, "ciagnie2" if ph == 1 else "stoi", home + 1, blink=blink)
        s = j["new"] if ph == 4 else j["old"]
        self.digits(f, s, xs, col, ch)
        dy = 10 * a * a if ph == 2 else 11 if ph == 3 else -11 * (1 - bounce(a)) if ph == 4 else 0
        for i in ch:
            self.put(f, text_px(s[i], xs[i], 1 + dy), col)
        if (ph == 2 and a > 0.1) or (ph == 4 and a > 0.4):  # kurz przy ziemi
            for i in ch:
                for q in range(4):
                    f.add(xs[i] - 1 + hash1(q * 7 + i + int(t * 15)) * 8, 10, mul((140, 110, 70), 0.5))

    def how_bazooka(self, f, j, ph, p, t, col, blink):
        """Strzał z bazooki: stare cyfry wylatują w powietrze na kawałki, nowe wyskakują z ziemi."""
        xs, ch, d, x = j["xs"], j["ch"], j["d"], j["stand"]
        tx, mx = (xs[ch[0]] + j["xr"]) / 2, x - 1
        ft = (mx - tx) / 50
        fired = ph >= 2
        self.man(f, ("baz2" if ph == 1 and p > d[1] - 0.15 or ph == 2 and p < 0.3 else "baz1") if ph <= 2 else "stoi",
                 x, blink=blink)
        s = j["new"] if ph == 4 else j["old"]
        self.digits(f, s, xs, col, ch)
        if not fired or (ph == 2 and p < ft):
            for i in ch:
                f.draw(text_px(s[i], xs[i], 1), col)
        if ph == 2 and p < ft:                    # rakieta w locie
            px = mx - 50 * p
            for q in range(3, 12):
                f.add(px + q, 5.5 + math.sin(q * 1.7 + t * 9) * 0.6, mul(visible((90, 90, 95), 4), 1 - q / 12))
            f.set(px, 5, (220, 40, 30))
            f.set(px + 1, 5, (100, 125, 40))
            f.set(px + 2, 5, (255, 150 + 100 * (int(t * 20) % 2), 0))
        elif ph == 2:                             # wybuch: piksele cyfr rozlatują się
            e = p - ft
            if e < 0.15:
                disc(f, tx, 5, 3, (255, 255, 220))
            n = 0
            for i in ch:
                for px_, py in text_px(s[i], xs[i], 1):
                    n += 1
                    vx = (px_ - tx) * 2.5 + (hash1(n * 3) - 0.5) * 20
                    vy = -6 - hash1(n * 5) * 10
                    c = lerp(col, (255, 120, 20), clamp(e * 3))
                    if e < 1.3:
                        self.put(f, [(px_ + vx * e, py + vy * e + 14 * e * e)], mul(c, 1 - e / 1.3))
        elif ph == 4:                             # nowe wyskakują z ziemi
            a = clamp(p / d[4])
            dy = 10 * (1 - a) ** 2 - math.sin(a * math.pi) * 1.5
            for i in ch:
                self.put(f, text_px(s[i], xs[i], 1 + dy), col)

    def how_kopniak(self, f, j, ph, p, t, col, blink):
        """Kopie stare cyfry, aż odlatują za górną krawędź; nowe wtaczają się z prawej, podskakując jak piłka."""
        xs, ch, d, home = j["xs"], j["ch"], j["d"], j["home"]
        kick = ph == 1 and p > d[1] * 0.6 or ph == 2 and p < 0.3
        self.man(f, "idzie1" if kick else "stoi", home + 1, blink=blink)
        s = j["new"] if ph == 4 else j["old"]
        self.digits(f, s, xs, col, ch)
        n = len(ch)
        for r, i in enumerate(reversed(ch)):      # od prawej – ta najbliżej buta pierwsza
            if ph == 1:
                f.draw(text_px(s[i], xs[i], 1), col)
            elif ph == 2:                         # prosto w górę, z lekkim zakręceniem
                e = max(0.0, p - 0.12 * r)
                self.put(f, text_px(s[i], xs[i] + math.sin(e * 9) * (1 - e), 1 - 26 * e), col)
            elif ph == 4:                         # od prawej krawędzi, za ludzikiem, coraz niższe podskoki
                a = clamp((p - 0.4 * r) / max(0.3, d[4] - 0.4 * (n - 1)))
                x = lerp_n(W + 2, xs[i], 1 - (1 - a) ** 2)
                self.put(f, text_px(s[i], x, 1 - abs(math.sin(math.pi * a * 3)) * 5 * (1 - a)), col)

    def how_zamiatanie(self, f, j, ph, p, t, col, blink):
        """Stare cyfry rozsypują się w kupkę piasku, ludzik zmiata ją do siebie, a nowe wyrastają z ziemi."""
        xs, ch, d, home = j["xs"], j["ch"], j["d"], j["home"]
        s = j["new"] if ph == 4 else j["old"]
        a = clamp(p / d[ph])
        pose = "zamiata1" if ph != 3 or int(t * 5) % 2 else "zamiata2"
        self.pose_at(f, pose, home + 1, blink=blink)
        self.digits(f, s, xs, col, ch)
        if ph == 4:                               # wyrastają od ziemi
            top = 10 - a * 10
            for i in ch:
                for px_, py in text_px(s[i], xs[i], 1):
                    if py >= top:
                        f.set(px_, py, (120, 230, 110) if py < top + 1.5 else col)
            return
        stack, n = {}, 0
        sand = (210, 175, 110)
        for i in ch:
            for px_, py in sorted(text_px(s[i], xs[i], 1), key=lambda q: -q[1]):
                n += 1
                if ph == 1:
                    f.set(px_, py, col)
                    continue
                lx = px_ + round((hash1(n * 11) - 0.5) * 3)
                rest = 10 - stack.get(lx, 0) // 2   # kupka: dwa ziarenka na wysokość
                stack[lx] = stack.get(lx, 0) + 1
                e = max(0.0, (p if ph == 2 else 9) - hash1(n * 7) * 0.7)
                y = min(rest, py + 20 * e * e)
                x = lx if y >= rest else px_
                if ph == 3:                       # zmiatane do miotły; przy niej znika (na szufelkę)
                    k = clamp(a * 1.6 - hash1(n * 3) * 0.6)
                    if k >= 1:
                        continue
                    x, y = lerp_n(x, home - 1, k), lerp_n(y, 10, k)
                f.set(x, y, lerp(col, sand, clamp(e * 2)))

    def how_magik(self, f, j, ph, p, t, col, blink):
        """Czary: stare cyfry znikają piksel po pikselu w iskrach, nowe pojawiają się tak samo."""
        xs, ch, d, home = j["xs"], j["ch"], j["d"], j["home"]
        self.man(f, "pcha1", home + 1, blink=blink)
        f.line(home + 1, 5, home - 1, 3, (150, 90, 40))          # różdżka
        f.set(home - 2, 2, hsv(t * 2, 0.6, 1))
        s = j["new"] if ph == 4 else j["old"]
        self.digits(f, s, xs, col, ch)
        n = 0
        for i in ch:
            for px_, py in text_px(s[i], xs[i], 1):
                n += 1
                when = hash1(n * 13) * 1.3
                if ph == 1 or (ph == 2 and p < when) or (ph == 4 and p > when + 0.15):
                    f.set(px_, py, col)
                elif (ph == 2 and p < when + 0.2) or (ph == 4 and p > when):
                    f.set(px_, py, hsv(0.75 + hash1(n) * 0.2, 0.4, 1))   # błysk
        if ph in (2, 3, 4):
            lo, hi = xs[ch[0]], j["xr"]
            for q in range(6):
                f.add(lo + hash1(q * 17 + int(t * 12)) * (hi - lo + 1), 1 + hash1(q * 29 + int(t * 12)) * 10,
                      hsv(0.8 + q * 0.04, 0.5, 0.8))

    def how_spawacz(self, f, j, ph, p, t, col, blink):
        """Laserem topi stare cyfry (spływają kałużą), nowe wypala punkt po punkcie."""
        xs, ch, d, home = j["xs"], j["ch"], j["d"], j["home"]
        self.man(f, "pcha1", home + 1, blink=blink)
        s = j["new"] if ph == 4 else j["old"]
        self.digits(f, s, xs, col, ch)
        hand = (home, 5)
        if ph == 1:
            for i in ch:
                f.draw(text_px(s[i], xs[i], 1), col)
        elif ph in (2, 3):
            fade = 1 - clamp(p / d[3]) if ph == 3 else 1
            for i in ch:
                for px_, py in text_px(s[i], xs[i], 1):
                    e = max(0.0, (p if ph == 2 else 9) - hash1(px_ * 7) * 0.8)
                    y = min(10, py + 8 * e * e)
                    c = lerp(col, (255, 110, 20), clamp(e * 1.5))
                    f.set(px_, y, mul(c, fade))
            if ph == 2:
                tx, ty = xs[ch[0]] + hash1(int(t * 10)) * (j["xr"] - xs[ch[0]]), 2 + hash1(int(t * 10) + 5) * 7
                f.line(hand[0], hand[1], tx, ty, (120, 20, 10), add=True)
        else:
            pts = sorted(((x, y) for i in ch for x, y in text_px(s[i], xs[i], 1)))
            done = clamp(p / d[4]) * len(pts)
            for q, (px_, py) in enumerate(pts):
                if q < done:
                    age = (done - q) / max(1, len(pts)) * d[4]
                    f.set(px_, py, lerp((255, 140, 40), col, clamp(age / 0.8)) if age > 0.1 else (255, 255, 210))
            if done < len(pts):                   # promień i iskry przy wypalanym punkcie
                px_, py = pts[int(done)]
                f.line(hand[0], hand[1], px_, py, (120, 20, 10), add=True)
                for q in range(4):
                    a = hash1(q * 3 + int(t * 30)) * 6.3
                    f.add(px_ + math.cos(a) * 1.5, py + math.sin(a) * 1.5, (200, 120, 30))

    def how_lina(self, f, j, ph, p, t, col, blink):
        """Wciąga stare cyfry na linie do góry, nowe opuszcza na linie."""
        xs, ch, d, home = j["xs"], j["ch"], j["d"], j["home"]
        a = clamp(p / d[ph])
        pose = "ciagnie2" if ph in (1, 3) else "ciagnie" + ("1" if int(t * 4) % 2 else "2")
        self.man(f, pose, home + 1, blink=blink)
        s = j["new"] if ph == 4 else j["old"]
        self.digits(f, s, xs, col, ch)
        dy = -11 * a * a if ph == 2 else -11 if ph == 3 else -11 * (1 - a) ** 2 if ph == 4 else 0
        rope = (190, 150, 90)
        f.rect(xs[ch[0]] + 2, 0, home + 1, 0, rope)  # lina pod sufitem do rąk ludzika
        f.rect(home + 1, 0, home + 1, 5, rope)
        for i in ch:
            top = 1 + dy
            cx = xs[i] + 2
            if ph == 1:
                f.rect(cx, 0, cx, a * 1, rope)
            elif top > 0:
                f.rect(cx, 0, cx, top - 1, rope)
            self.put(f, text_px(s[i], xs[i], top), col)

    def how_obrót(self, f, j, ph, p, t, col, blink):
        """Kręci korbą: cyfry obracają się jak w zegarze klapkowym – stara zwęża się do kreski, nowa się rozwija."""
        xs, ch, d, home = j["xs"], j["ch"], j["d"], j["home"]
        crank = t * 6
        self.man(f, "pcha1", home + 1, blink=blink)
        f.set(home, 6, (150, 150, 160))
        f.set(home - 1 + round(math.cos(crank)), 6 + round(math.sin(crank)), (230, 40, 40))  # korba
        s = j["new"] if ph == 4 else j["old"]
        self.digits(f, s, xs, col, ch)
        a = clamp(p / d[ph])
        k = 1 if ph == 1 else math.cos(a * math.pi / 2) if ph == 2 else 0.05 if ph == 3 else math.sin(a * math.pi / 2)
        for i in ch:
            cx = xs[i] + 2.5
            shade = mul(col, 0.5 + 0.5 * k)
            for px_, py in text_px(s[i], xs[i], 1):
                f.set(round(cx + (px_ - cx) * k), py, shade)

    def man(self, f, pose, x, flip=False, blink=False, char=None, dy=0):
        """char: inna postać niż w ustawieniach (strażak przy pożarze); dy: podskok."""
        if char is None:
            char = LUDZIK["char"] if self.char is None else self.char
        pal = dict(self.PAL, **LUDZIK_CHARS[char][1])
        if blink:
            pal["E"] = pal["S"]
        sprite(f, self.POSES[pose], x, round(dy), pal, flip)

    def pose(self, f, pose, x, flip=False, blink=False, char=None, dy=0):
        """Poza ustawiona po twarzy w x (jak w spacerze)."""
        self.man(f, pose, x + self.place(pose, flip), flip, blink, char, dy)

    def place(self, pose, flip):
        """O ile przesunąć pozę, żeby środek twarzy był zawsze w x + 4 (głowa nie skacze między pozami)."""
        rows = self.POSES[pose]
        eyes = next(([i for i, ch in enumerate(r) if ch in "EC"] for r in rows if "E" in r or "C" in r), [4])
        c = (min(eyes) + max(eyes)) / 2
        return round(4 - (len(rows[0]) - 1 - c if flip else c))

    def span(self, pose, x, flip):
        """Pierwsza i ostatnia zapalona kolumna pozy narysowanej przy x (ustawionej po twarzy)."""
        rows = self.POSES[pose]
        lit = [i for r in rows for i, ch in enumerate(r) if ch != "."]
        a, b = (len(rows[0]) - 1 - max(lit), len(rows[0]) - 1 - min(lit)) if flip else (min(lit), max(lit))
        d = x + self.place(pose, flip)
        return d + a, d + b

    def fits(self, trick, fl, xs, xr, x=None):
        """Czy sztuczka mieści się tu, gdzie ludzik stoi (albo w x): w panelu i nie na cyfrach."""
        r = self.REACH.get(next((n for n, v in self.TRICKS.items() if v is trick), None), 0)
        for i, pose in enumerate(trick[1]):
            flip = fl != (trick[3] and i % 2 == 1)
            a, b = self.span(pose, self.x if x is None else x, flip)
            a, b = (a, b + r) if flip else (a - r, b)
            if a < 0 or b > W - 1 or (b >= xs[0] and a <= xr):
                return False
        return True

    @staticmethod
    def zones(xs, xr):
        """Gdzie może spacerować (x pozy „stoi”): z prawej i z lewej strony godziny."""
        return [z for z in ((xr + 1, W - 8), (-1, xs[0] - 9)) if z[0] <= z[1]]

    @staticmethod
    def side_zones(xs, xr):
        """Strefy na ustawionej stronie (prawa/lewa); dowolnie – albo gdy tam brak miejsca – obie."""
        zs = Worker.zones(xs, xr)
        if not LUDZIK["side"]:
            return zs
        return [z for z in zs if (z[0] > xr) == (LUDZIK["side"] == 1)] or zs

    def at_side(self, xs, xr):
        """Czy stoi na swojej stronie (przy „dowolnie” zawsze)."""
        return any(z[0] - 1 <= self.x <= z[1] + 1 for z in self.side_zones(xs, xr))

    @staticmethod
    def spot(z, xr):
        """Losowe miejsce w strefie; przy ustawionej stronie najczęściej blisko krawędzi panelu."""
        if not LUDZIK["side"]:
            return random.randint(z[0], z[1])
        k = round((z[1] - z[0]) * random.random() ** 2)
        return z[1] - k if z[0] > xr else z[0] + k

    def props(self, f, name, pose, e, sx, flip, dur):
        """Rzeczy przy niektórych zajęciach: piłeczki, nuty, piłka, piaskownica z zamkiem, „Z” nad śpiącym."""
        w = len(self.POSES[pose][0])
        cx = lambda c: sx + (w - 1 - c if flip else c)
        if name == "żonglerka":
            for i, c in enumerate(((0, 200, 255), (255, 0, 200), (90, 255, 60))):
                ph = (e / 1.5 + i / 3) % 1
                if ph < 0.65:  # wysoko łukiem z lewej ręki do prawej, nisko z powrotem
                    a = ph / 0.65
                    f.set(cx(1 + 6 * a), 6 - 6 * math.sin(math.pi * a), c)
                else:
                    f.set(cx(7 - 6 * (ph - 0.65) / 0.35), 7, c)
        elif name == "gitara":
            for k in range(4):  # nuty ulatują znad gitary daleko przed niego, falując
                ph = (e / 3.6 + k / 4) % 1
                x, y = cx(1 - 17 * ph), 4 - 5 * ph + math.sin(ph * 11 + k * 2) * 1.2
                c = mul(hsv(k / 4 + int(e / 3.6 + k / 4) * 0.37, 0.7, 1), 1 - 0.7 * ph * ph)
                for dx, dy in ((0, 2), (1, 2), (1, 1), (1, 0), (2, 0)):
                    f.set(x + dx, y + dy, c)
        elif name == "piłka":
            n, ph = int(e / 0.7), (e / 0.7) % 1  # podbicie co 0.7 s, co trzecie wysoko
            top = 0 if n % 3 == 2 else 4
            y = 7 - (7 - top) * 4 * ph * (1 - ph)
            x = min(cx(-1), cx(0))
            dark = (n + int(ph * 4)) % 4  # łata kręci się
            for i, (dx, dy) in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
                f.set(x + dx, y + dy, (40, 40, 45) if i == dark else (235, 235, 235))
        elif name == "piasek":
            sand, wood = (220, 175, 95), (150, 90, 40)
            for c in range(-15, 0):  # piaskownica przed nim
                f.set(cx(c), 10, wood if c == -15 else sand)
            f.set(cx(-15), 9, wood)
            f.set(cx(0), 10, wood)
            f.set(cx(0), 9, wood)
            for c in (-14, -13):  # wiaderko
                for y in (8, 9):
                    f.set(cx(c), y, (230, 40, 40) if y == 9 or c == -14 else (255, 90, 70))
            f.set(cx(-13.5), 7, (200, 200, 200))
            px = [(c, y) for y in range(9, 3, -1) for c in range(9) if self.CASTLE[y - 4][c] == "#"]  # od dołu
            g = clamp(e / max(1.0, dur * 0.85))
            for i, (c, y) in enumerate(px[:int(g * len(px))]):
                f.set(cx(-12 + c), y, lerp(sand, (255, 230, 170), 0.35 * (c < 4) + 0.15 * hash1(i)))
            if g >= 1:  # gotowe: chorągiewka
                for y in (1, 2, 3):
                    f.set(cx(-8), y, (150, 150, 160))
                wave = int(e * 4) % 2
                f.set(cx(-7), 1, (230, 30, 30))
                f.set(cx(-6), 1 + wave, (230, 30, 30))
                f.set(cx(-7), 2, (230, 30, 30))
            if pose == "kuca2":  # łopatka w piasku
                f.set(cx(-1), 9, wood)
                f.set(cx(-2), 10, (170, 180, 200))
                f.set(cx(-1), 10, (170, 180, 200))
            else:  # łopatka w górze, piasek leci na zamek
                f.set(cx(-1), 7, wood)
                f.set(cx(-2), 7, (170, 180, 200))
                q = (e / 0.4) % 1
                for k in range(3):
                    a = clamp(q * 1.4 - k * 0.15)
                    if 0 < a < 1:
                        f.set(cx(-2 - 6 * a), 7 - 3 * math.sin(math.pi * a) + 2 * a, sand)
        elif name in self.SHOTS:
            self.shoot(f, name, e, flip, cx, dur)
        elif name == "spanie":
            for k in (0, 1):
                ph = (e / 2.4 + k / 2) % 1
                f.draw(text_px("Z", cx(3) - 5 * flip + 3 * ph, 3 - 5 * ph, SMALL),  # nad głową na poduszce
                       mul((150, 180, 255), 1 - 0.7 * ph))

    def shot_times(self, name, dur):
        """Kiedy (s od początku) pada każdy strzał serii trwającej dur."""
        fire, _ = self.SHOTS[name]
        _, poses, step, _ = self.TRICKS[name]
        one = [i * step for i, p in enumerate(poses) if p == fire and (i == 0 or poses[i - 1] != fire)]
        cycle = len(poses) * step
        return [c * cycle + ft for c in range(round(dur / cycle)) for ft in one]

    def shoot(self, f, name, e, flip, cx, dur):
        """Tarcza przy przeciwnej krawędzi panelu, pocisk leci za cyframi; trafienia: strzały, dziury albo wybuch
        (po wybuchu wyskakuje nowa tarcza)."""
        times, v = self.shot_times(name, dur), self.SHOTS[name][1]
        d = 1 if flip else -1                      # kierunek lotu
        tx = W - 3 if flip else 0                  # lewy brzeg tarczy
        face = tx if flip else tx + 2              # kolumna tarczy od strony strzelca
        mx, my = cx(-1), 5                         # wylot tuż przed bronią
        dist = abs(face - mx)
        hits = []
        for i, ft in enumerate(times):
            fe = e - ft
            if fe < 0:
                continue
            if fe * v < dist:                      # w locie
                px = mx + d * fe * v
                if name == "łuk":
                    ay = my + self.ARROW_DY[i % len(self.ARROW_DY)]
                    f.set(px, ay, (200, 200, 215))
                    for q in range(1, 4):
                        f.set(px - d * q, ay, (170, 110, 50))
                    f.set(px - d * 4, ay, (230, 40, 40))
                elif name == "pistolet":
                    f.set(px, my, (255, 235, 130))
                    f.set(px - d, my, (140, 110, 40))
                    if fe < 0.08:
                        f.set(mx, my - 1, (255, 255, 200))  # błysk z lufy
                else:
                    for q in range(3, 12):                  # dym za rakietą
                        f.add(px - d * q, my + 0.5 + math.sin(q * 1.7 + e * 9) * 0.6, mul(visible((90, 90, 95), 4), 1 - q / 12))
                    f.set(px, my, (220, 40, 30))
                    f.set(px - d, my, (100, 125, 40))
                    f.set(px - d * 2, my, (255, 150 + 100 * (int(e * 20) % 2), 0))
                    if fe < 0.5:                            # ogień z tyłu rury
                        for q in range(3):
                            f.add(cx(11 + q), 5 + (q + int(e * 15)) % 2, mul((255, 140, 20), 1 - fe * 2))
            else:
                hits.append((i, fe - dist / v))
        pop = e                                    # od kiedy stoi tarcza
        if name == "bazooka" and hits:             # wybuch: tarcza znika, po chwili wyskakuje nowa
            h = hits[-1][1]
            pop = h - 1.5
        if pop < 0:
            cx_, cy_ = tx + 1, 5
            if h < 0.15:
                disc(f, cx_, cy_, 2.5, (255, 255, 220))
            for k in range(16):
                a = k * math.pi / 8 + k * 0.3
                r = h * (5 + 3 * hash1(k))
                c = lerp((255, 230, 80), (200, 30, 0), clamp(h * 1.2))
                if h < 1.2:
                    f.set(cx_ + math.cos(a) * r, cy_ + math.sin(a) * r * 0.8 + h * h * 3, mul(c, 1 - h / 1.2))
            return
        wob = (1 if int(e * 25) % 2 else -1) if any(name == "łuk" and h < 0.4 for _, h in hits) else 0
        y0 = 2 + round((1 - clamp(pop / 0.4)) * 9)  # tarcza wyskakuje z podłogi
        sprite(f, self.TARGET, tx + wob, y0, self.TARGET_PAL)
        if name == "bazooka":
            return
        for i, h in hits:
            if name == "łuk":                       # strzała wbita w tarczę
                ay = my + self.ARROW_DY[i % len(self.ARROW_DY)]
                for q in range(0, 3):
                    f.set(face - d * q + wob, ay, (170, 110, 50))
                f.set(face - d * 3 + wob, ay, (230, 40, 40))
            else:                                   # dziura po kuli (i błysk przy trafieniu)
                hx, hy = self.HOLES[i % len(self.HOLES)]
                f.set(tx + hx, my + hy, (255, 255, 255) if h < 0.1 else (20, 10, 10))

    BANNER_SPEED = 18  # px/s przy tempie tekstu 1 – wolno, żeby dało się przeczytać

    @staticmethod
    def banner_text():
        m = NET.get("baner")
        if not m:
            return None
        try:
            tmax, code = m["daily"]["temperature_2m_max"][1], m["daily"]["weather_code"][1]
            return (f"{round(m['current']['temperature_2m'])}°C we {BANNER['city']}, jutro {round(tmax)}°C, "
                    f"{wmo(code)[1].lower()}")
        except (KeyError, IndexError, TypeError):
            return None

    def banner_due(self, now, t, nxt_t, lead):
        """Czy pora na transparent: co kilka minut (albo wymuszony przyciskiem ▶), i tylko gdy zdąży przed następnym
        przestawianiem cyfr."""
        forced = ludzik_next() == "transparent z pogodą"
        every = BANNER_EVERY[ludzik_lvl("transparent z pogodą")] if LUDZIK["freq"] else None
        if not every and not forced:
            return None
        txt = self.banner_text()
        if txt is None or (not forced and self.banner_at is not None and
                           (now - self.banner_at).total_seconds() < every * 60 - 5):
            return None
        length = text_w(txt, TXT) + 12
        dur = abs(self.x - (W - 9)) / self.WALK + 0.8 + scroll_time(W + length + 10, self.BANNER_SPEED)
        rate = self.rate or 1 / ANIM["tempo"]
        left = (nxt_t - now).total_seconds() - lead * rate
        just_changed = now.second < 15
        if dur * rate < left - 2 or (dur * rate > 50 and just_changed):  # za długi na minutę: tuż po zmianie
            return {"txt": txt, "len": length, "t0": t, "x0": self.x}
        return None

    def draw_banner(self, f, t, xs, col):
        """Ludzik przeciąga przez panel transparent z pogodą; zasłania zegar. -> False, gdy skończył."""
        b = self.banner
        e, walk = t - b["t0"], abs(b["x0"] - (W - 9)) / self.WALK
        start = W - 9
        for ch, x in zip(self.shown, xs):
            if e < walk:
                continue
            f.draw(text_px(ch, x, 1), col)
        if e < walk:  # idzie do prawej krawędzi (za cyframi)
            x = b["x0"] + (start - b["x0"]) * e / walk
            pose, flip = "idzie1" if int(t * 6) % 2 else "idzie2", start > b["x0"]
            self.man(f, pose, x + self.place(pose, flip), flip)
            for ch, xx in zip(self.shown, xs):
                f.draw(text_px(ch, xx, 1), col)
            return True
        e -= walk
        if e < 0.8:  # sięga po zwinięty transparent
            self.man(f, "ciagnie2", start)
            f.rect(W - 1, 0, W - 1, 10, (150, 90, 40))
            return True
        bl = W - scroll_px(e - 0.8, self.BANNER_SPEED)  # lewy brzeg transparentu
        if bl + b["len"] < 0:
            return False
        cloth, pole = visible((30, 25, 70), 4), (150, 90, 40)
        f.rect(bl, 0, bl + b["len"] - 1, 10, cloth)
        f.draw(text_px(b["txt"], bl + 6, 0, TXT), (255, 230, 120))
        f.rect(bl - 1, 0, bl - 1, 10, pole)
        f.rect(bl + b["len"], 0, bl + b["len"], 10, pole)
        pose = "idzie1" if int(t * 6) % 2 else "idzie2"
        self.man(f, pose, bl - 9)
        return True

    def start_ride(self, name, t, xs, xr, here_only):
        """Wsiada i jedzie: za krawędź panelu i z powrotem z drugiej strony (za cyframi), kilka okrążeń, aż do
        nowego miejsca. Okrążeń tyle, ile się zmieści przed przestawianiem cyfr. -> czas jazdy albo None."""
        zs = self.side_zones(xs, xr)
        if here_only:
            zs = [z for z in zs if z[0] - 1 <= self.x <= z[1] + 1] or zs
        z = random.choice(zs)
        goal, o = self.spot(z, xr), self.ride_off(name)
        d = -1 if goal >= self.x else 1  # odjeżdża od celu i wraca zza drugiej krawędzi: trasa najwyżej W + 2*o
        out = W + o - self.x if d > 0 else self.x + o
        back = goal + o if d > 0 else W + o - goal
        _, v, laps_range = self.RIDES[name]
        v = even_speed(v)
        lo, hi = (max(1, round(n * LEN_MUL[ludzik_len(name)])) for n in laps_range)
        free = self.free - 2 - (abs(goal - xr - 1) - abs(self.x - xr - 1)) / self.WALK  # do roboty pójdzie od celu
        if (out + back) / v > free:  # out + back to najwyżej jedno okrążenie
            return None
        laps = min(random.randint(lo, hi), 1 + int((free - (out + back) / v) / self.ride_time(name)))
        self.ride = {"n": name, "t0": t, "x0": self.x, "d": d, "goal": goal, "out": out,
                     "len": out + (laps - 1) * (W + 2 * o) + back}
        return self.ride["len"] / v

    def ride_time(self, name):
        """Czas jednego okrążenia."""
        return (W + 2 * self.ride_off(name)) / even_speed(self.RIDES[name][1])

    def ride_off(self, name):
        """Ile px za krawędzią pojazd całkiem znika (traktor z przyczepami jest długi)."""
        return max(self.RIDE_OFF, max(len(self.POSES[p][0]) for p in self.RIDES[name][0]) + 4)

    def trick_spec(self, name):
        """TRICKS[name] z czasem od–do według ustawionej długości."""
        (lo, hi), *rest = self.TRICKS[name]
        k, need = LEN_MUL[ludzik_len(name)], self.SCENES.get(name, (0, 0))[1]
        return ((max(lo * k, need), max(hi * k, need)), *rest)

    def trick_len(self, name):
        """Ile pełnych rund zajęcia zmieści się przed przestawianiem cyfr -> najdłuższy czas albo None."""
        (lo, hi), poses, step, _ = self.trick_spec(name)
        cycle = len(poses) * step
        dur = int(min(hi, self.free - 2) / cycle) * cycle
        return dur if dur >= (lo if name in self.SCENES else min(lo, 3)) and dur >= cycle else None

    def draw_ride(self, f, t, blink):
        """-> False, gdy dojechał."""
        r = self.ride
        poses, v, _ = self.RIDES[r["n"]]
        k = min(r["len"], round((t - r["t0"]) * even_speed(v), 6))  # round: 0,9999999 to jeszcze nie krok wstecz
        if k >= r["len"]:
            self.x, self.goal, self.ride = r["goal"], None, None
            return False
        d = r["d"]
        o = self.ride_off(r["n"])
        lap = W + 2 * o
        x = r["x0"] + d * k if k < r["out"] else (-o if d > 0 else W + o) + d * ((k - r["out"]) % lap)
        self.x = clamp(x, -10, W)  # gdyby przerwało przestawianie cyfr – idzie do roboty stąd
        pose, flip = poses[int(k / 3) % len(poses)], d > 0
        sx = x + self.place(pose, flip)
        self.man(f, pose, sx, flip, blink)
        w = len(self.POSES[pose][0])
        cx = lambda c: sx + (w - 1 - c if flip else c)
        if r["n"] == "traktor":
            for q in range(3):  # dym z rury wydechowej
                ph = (t * 1.6 + q / 3) % 1
                f.add(cx(3) - d * ph * 5, 1.5 - ph * 2.5, mul(visible((90, 90, 95), 4), 1 - ph))
        elif r["n"] == "kombajn":
            for q in range(4):  # nagarniacz kręci się nad hederem
                a = q * math.pi / 2 + t * 5 * (1 if flip else -1)
                f.line(cx(2.5), 5.5, cx(2.5 + math.cos(a) * 2.4), 5.5 + math.sin(a) * 2.4, visible((120, 100, 30)))
                f.set(cx(2.5 + math.cos(a) * 2.4), 5.5 + math.sin(a) * 2.4, (240, 210, 60))
            for q in range(5):  # sieczka i kurz z tyłu
                ph = (t * 1.8 + q / 5) % 1
                f.add(cx(25 + ph * 7), 8 + (hash1(q) - 0.5) * 2 - ph * 2, mul((200, 170, 90), (1 - ph) * 0.8))
        elif r["n"] == "auto":
            front, back = (sx + w, sx - 1) if flip else (sx - 1, sx + w)
            for q in range(6):  # snop światła przed maską
                f.add(front + d * q, 7 + (q > 2), mul((90, 85, 50), 1 - q / 6))
            for q in range(3):  # spaliny z rury
                ph = (t * 2 + q / 3) % 1
                f.add(back - d * (1 + ph * 6), 9 - ph * 2, mul(visible((90, 90, 95), 4), 1 - ph))
        return True

    def begin_trick(self, n, t, fl, pause, forced=False):
        (lo, hi), poses, step, _ = self.trick_spec(n)
        cycle = len(poses) * step
        dur = max(cycle, int(min(random.uniform(lo, hi), self.trick_len(n)) / cycle) * cycle)
        self.trick = (n, t, fl, dur, forced)
        self.next_trick = t + dur + (random.uniform(*pause) if pause else 0)

    def report(self, t, nxt_t, xr):
        """Co robi teraz, co zrobi następnie i jak przestawi godzinę – do LUDZIK_STATUS (panel WWW)."""
        j, busy = self.job, self.banner or self.job or self.trick or self.ride
        if self.banner:
            now = "transparent z pogodą"
        elif j:
            now = "przestawia godzinę"
        elif self.ride or self.trick:
            now = (self.ride or {}).get("n") or self.trick[0]
        elif self.goal is not None and abs(self.x - self.goal) >= 0.5:
            now = "na drugą stronę" if (self.goal > xr) != (self.x > xr) else "spacer"
        else:
            now = "stoi"
        nxt = LUDZIK["next"] or (self.upcoming if LUDZIK_FREQ[LUDZIK["freq"]][1] else None)
        at = j["new"] if j else nxt_t.strftime("%H:%M")  # najbliższa zmiana godziny
        after = (dtm.datetime.strptime(at, "%H:%M") + dtm.timedelta(minutes=1)).strftime("%H:%M")
        LUDZIK_STATUS.update(now=now, next=nxt, forced=bool(LUDZIK["next"]), never=not LUDZIK_FREQ[LUDZIK["freq"]][1],
                             eta=None if busy or LUDZIK["next"] or not nxt else max(0, round(self.next_trick - t)),
                             how_now=j["how"] if j else None, how_at=after if j else at,
                             how_next=self.pick_how(after if j else at))

    def scene_xs(self, n, z, xr):
        """Gdzie musi stać, żeby zacząć scenę: kot/pies podchodzi od krawędzi panelu, a przy pożarze śmietnik stoi
        od strony zegara."""
        lo, hi = z
        o = 1 if z[0] > xr else -1
        if n == "zwierzak":
            lo, hi = (lo, min(hi, W - 20)) if o > 0 else (max(lo, 12), hi)
        elif n == "pożar":
            lo, hi = (lo + 9, hi) if o > 0 else (lo, hi - 9)
        return lo, hi

    def scene_init(self, n, z, xr):
        o, p0, p1 = (1 if z[0] > xr else -1), max(0, z[0]), min(W - 1, z[1] + 7)
        self.sc = {"o": o, "p0": p0, "p1": p1, "x0": self.x, "seed": random.uniform(0, 100)}
        if n == "balon":
            self.sc.update(mx=self.x, bx=self.x + 4 - 3 * o, by=2.5, vx=0.0, vy=0.0, fl=o > 0, jump=-9.0,
                           gust=-9.0, caught=None)
        elif n == "zwierzak":
            kind = random.choice(list(self.PETS))
            wa = len(self.PETS[kind][0]["idzie1"][0])
            ax = self.x + 8 if o > 0 else self.x - 1 - wa
            a0 = W + 1 if o > 0 else -wa - 1
            run = random.choice((o, -o))  # ucieka tam, skąd przyszedł, albo za zegarem na drugą stronę
            ra = W + 1 if run > 0 else -wa - 1
            self.sc.update(kind=kind, ax=ax, a0=a0, ra=ra, run=run, tin=abs(ax - a0) / 12, trun=abs(ra - ax) / 32)
        elif n == "pożar":
            be = p0 + 4 if o > 0 else p1 - 4  # zewnętrzna krawędź śmietnika; u rośnie od niej na zewnątrz
            far = be if o > 0 else W - 1 - be
            self.sc.update(be=be, xout=W + 1 if o > 0 else -9, u_in=(W - be if o > 0 else be + 1) + 1,
                           u_end=-(far + 23))

    def scene_end(self, n, t):
        if n == "pożar":  # odjechał wozem za zegar – wraca piechotą zza drugiej krawędzi
            self.x, self.goal, self.wait = (-9 if self.sc["o"] > 0 else W + 1), self.sc["x0"], t
        self.sc = {}

    @staticmethod
    def balloon(f, x, y, e):
        """Pomarańczowy balonik ze sznurkiem; (x, y) – środek."""
        for dy in range(-3, 4):
            for dx in range(-2, 3):
                if (dx / 1.7) ** 2 + (dy / 2.3) ** 2 <= 1:
                    c = (255, 185, 90) if (dx, dy) == (-1, -1) else (255, 120, 0) if dx < 1 else (210, 85, 0)
                    f.set(x + dx, y + dy, c)
        f.set(x, y + 2.6, (190, 70, 0))
        for k in range(1, 4):  # sznurek faluje
            f.set(x + math.sin(e * 4 + k) * 0.5 * k / 3, y + 2.6 + k, (150, 150, 160))

    def scene_balon(self, f, e, dt, dur, blink):
        """Goni pomarańczowy balonik: wiatr go unosi, ludzik biegnie i podskakuje; pod koniec łapie go… i balon pęka."""
        s = self.sc
        lo_b, hi_b = s["p0"] + 2, s["p1"] - 2
        pop = dur - 0.7
        if s["caught"] is None and e > 1.0:  # balon lata
            wind = (noise1(e * 0.6 + s["seed"]) - 0.5) * 18
            tgt = 1.8 + 3.2 * noise1(e * 0.45 + s["seed"] + 9)
            gap = s["bx"] - s["mx"] - 4
            if e > 0.7 * dur:  # opada w stronę ludzika
                wind, tgt = wind * 0.3 - gap * 1.2, 4.5
            elif abs(gap) < 8:  # ucieka mu sprzed nosa (pęd powietrza), przy ścianie – górą nad nim
                stuck = not lo_b + 3 < s["bx"] < hi_b - 3
                wind += (1 if gap > 0 else -1) * 30 * (-0.6 if stuck else 1)
                tgt = 0 if stuck else tgt
            s["vx"] += (wind - s["vx"] * 0.9) * dt
            s["vy"] += ((tgt - s["by"]) * 2.5 - s["vy"] * 1.6) * dt
            s["bx"] += s["vx"] * dt
            s["by"] = clamp(s["by"] + s["vy"] * dt, -1, 5.5)
            if not lo_b <= s["bx"] <= hi_b:
                s["bx"], s["vx"] = clamp(s["bx"], lo_b, hi_b), -s["vx"] * 0.6
        jp = (e - s["jump"]) / 0.6
        if s["caught"] is None and e > 1.0:
            if jp >= 1:  # biegnie pod balon
                dx = s["bx"] - 4 - s["mx"]
                if abs(dx) > 0.3:
                    s["fl"] = dx > 0
                s["mx"] = clamp(s["mx"] + min(abs(dx), 13 * dt) * (1 if dx > 0 else -1), s["p0"], s["p1"] - 7)
                if abs(dx) < 4 and e - s["jump"] > 1.0:
                    s["jump"], jp = e, 0
            if 0.5 <= jp < 1 and s["gust"] < s["jump"]:  # w najwyższym punkcie: łapie albo balon ucieka
                s["gust"] = e
                if e > 0.7 * dur:
                    s["caught"] = e
                else:
                    away = 1 if s["bx"] < (lo_b + hi_b) / 2 else -1
                    s["vx"], s["vy"] = away * random.uniform(8, 14), -6
            if e > dur - 2.4:
                s["caught"] = e
        x = s["mx"]
        self.x = x
        hand = x + (6 if s["fl"] else 1)
        if e >= pop:  # pęka: strzępki i zaskoczony ludzik
            self.pose(f, "pajac", x, s["fl"], blink)
            r = (e - pop) * 12
            for k in range(10):
                a = k / 10 * 2 * math.pi
                f.add(s["bx"] + math.cos(a) * r, s["by"] + math.sin(a) * r * 0.7, mul((255, 140, 30), 1 - (e - pop) / 0.7))
            if e - pop < 0.1:
                disc(f, s["bx"], s["by"], 2.5, (255, 255, 220))
            return
        if s["caught"] is not None or e <= 1.0:  # trzyma za sznurek
            k = clamp((e - s["caught"]) / 0.4) if s["caught"] is not None else 1
            s["bx"] += (hand + (2 if s["fl"] else -2) - s["bx"]) * k
            s["by"] += (2.5 - s["by"]) * k
            self.pose(f, "macha" if s["caught"] is not None and int(e * 3) % 2 else "stoi", x, s["fl"], blink)
            f.line(hand, 7, s["bx"], s["by"] + 3, (150, 150, 160))
            self.balloon(f, s["bx"], s["by"], e)
            return
        if jp < 1:
            self.pose(f, "pajac", x, s["fl"], blink, dy=-3 * math.sin(math.pi * jp))
        else:
            moving = abs(s["bx"] - 4 - x) > 0.5
            self.pose(f, ("idzie1" if int(e * 8) % 2 else "idzie2") if moving else "stoi", x, s["fl"], blink)
        self.balloon(f, s["bx"], s["by"], e)

    def scene_zwierzak(self, f, e, dt, dur, blink):
        """Przychodzi kot albo pies, ludzik kuca i go głaszcze (serduszka), a potem zwierzak ucieka."""
        s = self.sc
        o, ax = s["o"], s["ax"]
        poses, pal = self.PETS[s["kind"]]
        pet = max(3.0, dur - s["tin"] - s["trun"] - 1.2)
        out = o > 0  # ludzik patrzy w stronę zwierzaka
        if e < s["tin"]:  # podchodzi
            a = s["a0"] + (ax - s["a0"]) * e / s["tin"]
            sprite(f, poses["idzie1" if int(a / 2) % 2 else "idzie2"], round(a), 5, pal, o > 0)
            self.pose(f, "kuca" if e > s["tin"] - 0.8 else "stoi", self.x, out, blink)
        elif e < s["tin"] + pet:  # głaskanie
            q = e - s["tin"]
            sprite(f, poses["siedzi1" if int(q * 3) % 2 else "siedzi2"], round(ax), 5, pal, o > 0)
            self.pose(f, "kuca2" if int(q / 0.45) % 2 else "kuca", self.x, out, blink)
            wa = len(poses["idzie1"][0])
            hx = ax + (1 if o > 0 else wa - 4)  # nad łebkiem
            for k in range(2):
                ph = (q / 1.6 + k / 2) % 1
                c = mul((255, 60, 130), 1 - ph * 0.8)
                for dx, dy in ((0, 0), (2, 0), (0, 1), (1, 1), (2, 1), (1, 2)):
                    f.set(hx + dx + math.sin(ph * 6 + k) * 0.8, 3 - ph * 5 + dy, c)
        else:  # ucieka
            q = e - s["tin"] - pet
            if q < s["trun"]:
                a = ax + (s["ra"] - ax) * q / s["trun"]
                sprite(f, poses["idzie1" if int(a / 3) % 2 else "idzie2"], round(a), 5, pal, s["run"] < 0)
                self.pose(f, "stoi", self.x, s["run"] > 0, blink)
            else:
                self.pose(f, "macha", self.x, s["run"] < 0, blink)

    def scene_pozar(self, f, e, dt, dur, blink):
        """Pali się śmietnik: ludzik się przeraża i ucieka, wraca wozem strażackim na sygnale jako strażak, gasi
        z węża, a potem odjeżdża (zabierając spalony śmietnik) za zegar i wraca piechotą."""
        s = self.sc
        o, be = s["o"], s["be"]
        pix = lambda u: be + o * u
        if "T" not in s:  # długości etapów
            t_run = abs(s["xout"] - s["x0"]) / 18
            dist = 13 - s["u_end"]
            t_dep = 2.5 + max(0, dist - 18.75) / 15  # rusza powoli, potem 15 px/s
            fixed = 1.5 + 1.5 + t_run + 6.0 + 0.4 + 2.5 + 0.4 + t_dep
            s["T"] = list(itertools.accumulate((1.5, 1.5, t_run, 6.0, 0.4, max(3.0, dur - fixed), 2.5, 0.4, t_dep)))
        T = s["T"]
        ph = next((i for i, v in enumerate(T) if e < v), len(T) - 1)
        p = (e - (T[ph - 1] if ph else 0)) / ((T[ph] - (T[ph - 1] if ph else 0)) or 1)
        fire = clamp(e / 1.5) if ph < 5 else clamp(1 - p * 1.2) if ph == 5 else 0
        uf = None  # przód wozu
        if ph == 3:  # wóz przyjeżdża, zwalnia
            uf = 13 + (s["u_in"] - 13) * (1 - p) ** 2
        elif 3 < ph < 8:
            uf = 13
        elif ph == 8:
            tt = e - T[7]
            uf = 13 - (3 * tt * tt if tt < 2.5 else 18.75 + 15 * (tt - 2.5))
        if uf is None or uf > -3:  # śmietnik (wóz go zabiera)
            for c in range(-3, 1):
                f.set(pix(c), 7, (140, 140, 150))
                for y in (8, 9, 10):
                    f.set(pix(c), y, (120, 125, 135) if c % 2 else (85, 90, 100))
        mid = pix(-1.5)
        if fire > 0:  # płomienie, iskry, dym
            for i, x in enumerate(sorted(pix(c) for c in range(-4, 2))):  # języki ognia, na brzegach niższe
                edge = i in (0, 5)
                h = fire * (2 + 5 * noise1(e * 7 + i * 2.3 + s["seed"])) * (0.45 if edge else 1)
                for j in range(int(h) + 1):
                    fr = j / max(h, 1)
                    c = (255, 235, 140) if fr < 0.3 and not edge else lerp((255, 180, 20), (220, 25, 0), fr)
                    f.set(x, 6 - j, mul(c, min(1, h - j)) if j == int(h) else c)
            for i in range(3):
                q = (e * 1.3 + i / 3) % 1
                f.add(mid + math.sin(e * 3 + i * 2) * 1.5, 4 - 6 * q, mul((255, 150, 30), (1 - q) * fire))
                q = (e * 0.5 + i / 3) % 1
                f.add(mid + q * 3 * math.sin(i + s["seed"]), 2 - 5 * q, mul(visible((70, 70, 70), 4), (1 - q) * fire))
        if ph in (5, 6):  # para po gaszeniu
            for i in range(4):
                q = (e * 0.7 + i / 4) % 1
                k = 1 - fire if ph == 5 else 1 - p
                f.add(mid + math.sin(e + i * 1.7) * 1.5, 6 - 7 * q, mul(visible((140, 140, 150), 4), (1 - q) * k))
        if uf is not None:
            sx = min(pix(uf), pix(uf + 21))
            self.man(f, "woz", sx, o < 0, char=1)
            if ph < 8:  # koguty
                w = 22
                cx = lambda c: sx + (w - 1 - c if o < 0 else c)
                on = int(e * 6) % 2
                f.set(cx(2), 0, (0, 90, 255) if on else (40, 40, 60))
                f.set(cx(3), 0, (0, 90, 255) if on else (40, 40, 60))
                f.set(cx(4), 0, (255, 20, 20) if not on else (60, 40, 40))
                f.set(cx(5), 0, (255, 20, 20) if not on else (60, 40, 40))
        if ph < 2:  # stoi i patrzy, potem panikuje
            pose = "stoi" if ph == 0 else ("pajac" if int(e / 0.12) % 2 else "pajac_pol")
            self.pose(f, pose, s["x0"], o < 0, blink)
            self.x = s["x0"]
        elif ph == 2:  # ucieka za krawędź
            self.x = s["x0"] + (s["xout"] - s["x0"]) * p
            self.pose(f, "idzie1" if int(e * 9) % 2 else "idzie2", self.x, o > 0, blink)
        elif ph in (4, 5):  # wysiadł, gasi z węża
            sx = min(pix(2), pix(11))
            self.man(f, "pist1", sx, o < 0, blink, char=1)
            for u in range(10, 14):
                f.set(pix(u), 10, (200, 180, 120))
            if ph == 5:
                for k in range(7):
                    q = (e * 2.5 + k / 7) % 1
                    f.set(pix(1 - 3.6 * q), 5.5 - 1.8 * math.sin(math.pi * q) + q * 0.8, (90, 170, 255))
                if fire > 0 and int(e * 10) % 2:
                    f.add(pix(-1 - hash1(int(e * 10)) * 2), 6, (150, 200, 255))
            self.x = clamp(sx, -10, W)
        elif ph == 6:  # zgaszone – macha
            self.man(f, "macha", min(pix(2), pix(9)) - (1 if o > 0 else 0), o > 0, blink, char=1)
        if uf is not None:
            self.x = clamp(pix(uf + 6), -10, W)

    def roll(self, off):
        """Losuje następne zajęcie (częstsze częściej) – z góry, żeby panel WWW mógł je pokazać."""
        opts = [n for n in (*self.TRICKS, *self.RIDES) if n not in off]
        return random.choices(opts, [LVL_WEIGHT[ludzik_lvl(n)] for n in opts])[0] if opts else None

    def start_act(self, n, t, xs, xr, pause, forced):
        """Zaczyna zajęcie: wymuszone przyciskiem ▶ (także wyłączone) albo wylosowane wcześniej. Gdy tu się nie mieści –
        idzie tam, gdzie się zmieści. -> "start", "go" (idzie na miejsce), "wait" (brak czasu do przestawiania cyfr –
        czeka na następną minutę) albo "never" (nigdzie się nie mieści)."""
        zs, mine = self.zones(xs, xr), self.side_zones(xs, xr)
        here = next((z for z in zs if z[0] - 1 <= self.x <= z[1] + 1), zs[0])
        stay = not forced and "na drugą stronę" in ludzik_off()  # bez przechodzenia – tylko po tej stronie
        if n in ("spacer", "na drugą stronę"):
            other = [z for z in zs if z != here]
            z = random.choice(other) if n == "na drugą stronę" and other else here if here in mine else mine[0]
            self.goal, self.wait, self.moon = self.spot(z, xr), t, False
            return "start"
        if n in self.RIDES:
            if self.free <= self.ride_time(n) + 2:
                return "wait"
            dur = self.start_ride(n, t, xs, xr, stay)
            if dur is None:
                return "wait"
            self.ride["forced"] = forced
            self.next_trick = t + dur + (random.uniform(*pause) if pause else 0)
            return "start"
        if n not in self.TRICKS:  # transparent rysuje draw()
            return "never"
        if not self.trick_len(n):
            return "wait"
        if n in self.SCENES:  # potrzebuje dość miejsca po swojej stronie
            big = lambda zz: [z for z in zz if min(W - 1, z[1] + 7) - max(0, z[0]) + 1 >= self.SCENES[n][0]]
            cand = big([here]) if stay else big(mine) or big(zs)
            if not cand:
                return "never"
            z = here if here in cand else cand[0]
            lo, hi = self.scene_xs(n, z, xr)
            if z == here and lo <= self.x <= hi:
                self.scene_init(n, z, xr)
                self.begin_trick(n, t, False, pause, forced)
                return "start"
            self.goal, self.wait = (clamp(self.x, lo, hi) if z == here else random.randint(lo, hi)), t
            return "go"
        tr, away = self.TRICKS[n], self.x > xr
        dirs = lambda x: (x < xs[0],) if n in self.SHOTS else (away, not away)  # strzela przez zegar
        fl = next((fl for fl in dirs(self.x) if self.fits(tr, fl, xs, xr)), None) if self.at_side(xs, xr) else None
        if fl is not None:
            self.begin_trick(n, t, fl, pause, forced)
            return "start"
        ok = lambda zs: [x for z in zs for x in range(z[0], z[1] + 1) if any(self.fits(tr, fl, xs, xr, x) for fl in dirs(x))]
        spots = ok([here]) if stay else ok(mine) or ok(zs)  # najpierw na swojej stronie
        if not spots:
            return "never"
        self.goal, self.wait = min(spots, key=lambda x: abs(x - self.x)), t
        return "go"

    def idle(self, f, t, dt, xs, xr, blink):
        """Bez roboty: spaceruje po obu stronach zegara (przechodzi za cyframi), a z nudów coś robi."""
        pause = LUDZIK_FREQ[LUDZIK["freq"]][1]
        off = ludzik_off()
        if self.next_trick is None:
            self.next_trick = t + (random.uniform(*pause) if pause else 0)
        standing = self.goal is None or abs(self.x - self.goal) < 0.5
        if self.trick and self.trick[0] in off and not self.trick[4]:  # właśnie wyłączone w ustawieniach
            self.trick = None
        if self.upcoming in off or self.upcoming is None:
            self.upcoming = self.roll(off)
        forced = ludzik_next()
        if self.trick is None and self.ride is None and standing:
            if forced:
                if self.start_act(forced, t, xs, xr, pause, True) == "start":
                    LUDZIK["next"] = None
            elif pause and self.upcoming and t >= self.next_trick and self.at_side(xs, xr):  # po drugiej stronie
                r = self.start_act(self.upcoming, t, xs, xr, pause, False)                 # jest tylko na chwilę
                if r in ("start", "never"):
                    self.upcoming = self.roll(off)
                if r == "never":
                    self.next_trick = t + 3
            standing = self.goal is None or abs(self.x - self.goal) < 0.5
        if self.ride and self.ride["n"] in off and not self.ride.get("forced"):  # właśnie wyłączone w ustawieniach
            self.ride = None
        if self.ride and self.draw_ride(f, t, blink):
            return
        if self.trick:
            name, t0, fl, dur, _ = self.trick
            _, poses, step, mirror = self.TRICKS[name]
            if name in self.SCENES:
                if t - t0 < dur:
                    getattr(self, "scene_" + self.SCENE_FN[name])(f, t - t0, dt, dur, blink)
                    return
                self.scene_end(name, t)
            elif t - t0 < dur:
                i = int((t - t0) / step) % len(poses)
                flip = fl != (mirror and i % 2 == 1)
                sx = self.x + self.place(poses[i], flip)
                self.man(f, poses[i], sx, flip, blink)
                self.props(f, name, poses[i], t - t0, sx, flip, dur)
                return
            self.trick, self.wait = None, max(self.wait, t + 1)
        away = not self.at_side(xs, xr)  # po drugiej stronie niż ustawiona – zaraz wraca (także bez spacerów)
        if t >= self.wait and standing and ("spacer" not in off or away):
            if self.goal is not None:
                self.wait = t + random.uniform(*(AWAY_REST if away else WALK_REST[ludzik_lvl("spacer")]))
            zs = self.zones(xs, xr)
            here = next((z for z in zs if z[0] - 1 <= self.x <= z[1] + 1), zs[0])
            other = [z for z in zs if z != here]
            if away:
                z = self.side_zones(xs, xr)[0]
            else:
                z = random.choice(other) if other and random.random() < CROSS_P[ludzik_lvl("na drugą stronę")] else here
            self.goal = self.spot(z, xr)
            self.moon = random.random() < 0.25  # czasem idzie tyłem, moonwalkiem
        if self.goal is not None and t >= self.wait and abs(self.x - self.goal) >= 0.5:
            self.x += min(abs(self.goal - self.x), self.WALK * dt) * (1 if self.goal > self.x else -1)
            pose, flip = "idzie1" if int(t * 6) % 2 else "idzie2", (self.goal > self.x) != self.moon
            self.man(f, pose, self.x + self.place(pose, flip), flip)
        else:  # stoi przodem do zegara, czasem się odwraca
            flip = (self.x < xs[0]) != ((t % 9) > 6.5)
            self.man(f, "stoi", self.x + self.place("stoi", flip), flip, blink)

    def draw(self, f, now, t, dt):
        if self.prev and t > self.prev[0]:  # ile sekund zegara mija na sekundę animacji (tempo, przyspieszenie)
            r = clamp((now - self.prev[1]).total_seconds() / (t - self.prev[0]), 0, 1e5)
            self.rate = r if self.rate is None else self.rate * 0.9 + r * 0.1
        self.prev = (t, now)
        cur = now.strftime("%H:%M")
        nxt_t = (now + dtm.timedelta(minutes=1)).replace(second=0, microsecond=0)
        nxt = nxt_t.strftime("%H:%M")
        self.left = (nxt_t - now).total_seconds() / (self.rate or 1 / ANIM["tempo"])  # s animacji do pełnej minuty
        if self.shown is None:
            self.shown = cur
        xs, xr = self.layout(self.shown)
        home = xs[0] - 9 if LUDZIK["side"] == 2 and xs[0] >= 8 else xr + 1  # przy cyfrach, na swojej stronie
        if self.x is None:
            self.x = home
        if LUDZIK["freq"] and ludzik_lvl("transparent z pogodą"):
            NET.get("baner")  # dane do transparentu pobierają się w tle
        if self.banner is None and self.job is None and self.trick is None and self.ride is None and self.shown == cur:
            job = self.plan(self.shown, nxt, t)
            self.banner = self.banner_due(now, t, nxt_t, sum(job["d"][:4]))
            if self.banner:
                self.banner_at = now
                if ludzik_next() == "transparent z pogodą":
                    LUDZIK["next"] = None
        if not getattr(THUMB, "on", False):
            self.report(t, nxt_t, xr)
        if self.banner:
            for x in range(W):
                f.set(x, 11, visible((40, 26, 12)))
            if self.draw_banner(f, t, xs, (235, 235, 255)):
                return
            self.banner, self.x, self.goal, self.wait = None, -10, home, t  # wraca zza lewej krawędzi
            self.next_trick = max(self.next_trick or 0, t + 4)
        if self.job is None:
            self.free = 0.0
            if self.shown not in (cur, nxt):  # spóźniony (start efektu, skok czasu) – od razu do roboty
                self.job = self.plan(self.shown, cur, t)
            elif nxt != self.shown:  # zaczyna wcześniej, żeby nowe cyfry wjeżdżały równo z pełną minutą
                job = self.plan(self.shown, nxt, t, self.ride["goal"] if self.ride else None)  # jazda kończy się u celu
                lead = sum(job["d"][:4])
                if (nxt_t - now).total_seconds() <= lead * (self.rate or 1 / ANIM["tempo"]):
                    self.job = self.plan(self.shown, nxt, t) if self.ride else job
                else:
                    self.free = self.left - lead
        if self.job is not None:
            self.ride = self.trick = None  # do roboty – pojazd znika, ludzik idzie od miejsca, gdzie był
        ground = visible((40, 26, 12))
        for x in range(W):
            f.set(x, 11, ground)
        col = (235, 235, 255)
        blink = (t % 3.7) < 0.15
        j = self.job
        if j is None:  # ludzik najpierw, cyfry na wierzchu – gdy przechodzi na drugą stronę, idzie za nimi
            self.idle(f, t, dt, xs, xr, blink)
            for ch, x in zip(self.shown, xs):
                f.draw(text_px(ch, x, 1), col)
            return
        p, ph, d = t - j["t0"], 0, j["d"]
        while ph < len(d) and p >= d[ph]:
            p -= d[ph]
            ph += 1
        if ph == len(d):
            self.shown, self.job, self.x, self.goal, self.wait = j["new"], None, j["end"], None, t + 3
            self.next_trick = max(self.next_trick or 0, t + 4)
            return self.draw(f, now, t, 0)
        if ph == 0:  # idzie do roboty (za cyframi)
            x = j["x0"] + (j["stand"] - j["x0"]) * (p / d[0] if d[0] else 1)
            pose, flip = "idzie1" if int(t * 6) % 2 else "idzie2", j["stand"] > j["x0"]
            self.man(f, pose, x + self.place(pose, flip), flip)
            self.digits(f, j["old"], j["xs"], col)
        elif ph == 5:
            self.digits(f, j["new"], j["xs"], col)
            self.man(f, "stoi" if p < 0.4 else "macha", j["end"], flip=p >= 0.4, blink=blink)
        else:
            getattr(self, "how_" + j["how"])(f, j, ph, p, t, col, blink)


LUDZIK_ACTS = ["spacer", "na drugą stronę", *Worker.TRICKS, *Worker.RIDES, "transparent z pogodą"]  # co można włączyć/wyłączyć
LUDZIK_TIMED = [*Worker.TRICKS, *Worker.RIDES]  # te mają ustawianą długość


# ---------------------------------------------------------------- zwykły zegar w kolorze pory dnia
def kelvin_rgb(k):
    """Barwa światła o temperaturze k kelwinów (przybliżenie Tannera Hellanda); najjaśniejsza składowa = 255,
    bo jasność jest jedna dla wszystkich efektów (ustawienie „jasność WLED”)."""
    t = clamp(k, 1000, 40000) / 100
    r = 255 if t <= 66 else 329.698727446 * (t - 60) ** -0.1332047592
    g = 99.4708025861 * math.log(t) - 161.1195681661 if t <= 66 else 288.1221695283 * (t - 60) ** -0.0755148492
    b = 255 if t >= 66 else 0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
    c = tuple(clamp(v, 0, 255) for v in (r, g, b))
    return mul(c, 255 / max(c))


DAYLIGHT = [  # wysokość słońca (stopnie) -> temperatura barwowa (K): noc bursztynowa, zmierzch ciepły, południe białe
    (-12, 2200), (-4, 2500), (2, 3000), (12, 4200), (30, 6500),
]
CLOCK_TEMPS = [-2000, -1500, -1000, -750, -500, -250, 0, 250, 500, 750, 1000, 1500, 2000, 3000]  # przesunięcie (K)
CLOCK_HUES = [("pora dnia", None), ("biały", (255, 255, 255)), ("ciepły biały", (255, 214, 150)),
              ("żółty", (255, 200, 0)), ("pomarańczowy", (255, 120, 0)), ("czerwony", (255, 30, 20)),
              ("różowy", (255, 60, 160)), ("fioletowy", (170, 60, 255)), ("niebieski", (40, 110, 255)),
              ("błękitny", (0, 200, 255)), ("zielony", (40, 255, 80))]
CLOCK = {"hue": 0, "temp": 0, "col": None, "font": 0}  # „barwa” (indeks w CLOCK_HUES), „temperatura” (K), dowolny
# kolor (r, g, b) zamiast barwy (None = barwa) i „czcionka” (indeks w CLOCK_FONTS); zapisywane w konfiguracji


def daylight_k(elev):
    """Temperatura barwowa (K) dla wysokości słońca – interpolacja między punktami DAYLIGHT."""
    if elev <= DAYLIGHT[0][0]:
        return DAYLIGHT[0][1]
    for (a, ka), (b, kb) in zip(DAYLIGHT, DAYLIGHT[1:]):
        if elev <= b:
            return ka + (kb - ka) * (elev - a) / (b - a)
    return DAYLIGHT[-1][1]


def clock_color(now):
    """Kolor zegara: „pora dnia” = temperatura za słońcem + przesunięcie; stały kolor (z listy albo dowolny) =
    przesunięcie jak balans bieli."""
    base = CLOCK["col"] or CLOCK_HUES[CLOCK["hue"]][1]
    if base is None:
        return kelvin_rgb(daylight_k(sun_position(now)[0]) + CLOCK["temp"])
    if not CLOCK["temp"]:
        return base
    tint, ref = kelvin_rgb(6500 + CLOCK["temp"]), kelvin_rgb(6500)
    c = tuple(v * a / b for v, a, b in zip(base, tint, ref))
    return mul(c, 255 / max(c))


@reg("zegar")
class PlainClock(Clock):
    """Zwykły, czytelny zegar: godzina z sekundami, dzień tygodnia (zawsze cały – długie nazwy węższymi literami)
    i data, wszystko jednym kolorem. Barwa z listy albo dowolny kolor; „pora dnia” idzie za słońcem – w południe
    biały, wieczorem ciepły żółty, w nocy bursztyn; „temperatura” przesuwa barwę. Cyfry w jednej z kilku czcionek."""

    @staticmethod
    def fit(texts, room, fonts=(SMALL, NARROW_TXT)):
        """Pierwsza czcionka z fonts, w której wszystkie napisy mieszczą się w room -> (czcionka, szerokość)."""
        for font in fonts:
            w = max(text_w(s, font) for s in texts)
            if w <= room:
                return font, w
        return NARROW_TXT, w

    def draw(self, f, now, t, dt):
        c = clock_color(now)
        name, font = CLOCK_FONTS[CLOCK["font"]]
        small, fdates = CLOCK_SMALL.get(name, ((SMALL, NARROW_TXT),) * 2)  # dzień i data w stylu godziny
        hms = now.strftime("%H:%M:%S")
        tw, th = text_w(hms, font), len(font["0"])
        y = 1 + (10 - th) // 2
        wd = PL_DAYS[now.weekday()].upper()
        date = f"{now.day:02d}.{now.month:02d}.{now.year}"
        if NARROW:  # 60 kolumn: sama godzina, co 10 s na chwilę dzień tygodnia i data (dwa wiersze)
            if page(t, 4, 2.5) == 3:
                ff, _ = self.fit([wd], W - 2, small)
                f.draw(small_pl(wd, (W - text_w(wd, ff)) // 2, 1, font=ff), c)
                fdate, _ = self.fit([date], W - 2, fdates)
                f.text(date, (W - text_w(date, fdate)) // 2, 7, c, fdate)
                return
            x = (W - tw) // 2
        else:
            room = W - tw - 6  # najmniej 2 px odstępu przy brzegach i od godziny
            fd, wdw = self.fit([wd], room, small)
            fdate, dw = self.fit([date], room, fdates)
            gap = (W - tw - max(wdw, dw)) // 3  # równe odstępy: brzeg, godzina, data, brzeg
            x = gap
            dx = x + tw + gap
            f.draw(small_pl(wd, dx, 1, font=fd), c)       # wiersz 0 na kreskę (Ś), wiersz 6 na ogonek (Ą)
            f.text(date, dx, 7, c, fdate)
        f.text(hms, x, y, c, font)  # wszystko jednym kolorem


# ---------------------------------------------------------------- test kolorów (kalibracja podglądu)
TEST_COLORS = [("czerwony", (255, 0, 0)), ("pomarańczowy", (255, 120, 0)), ("żółty", (255, 220, 0)),
               ("zielony", (0, 255, 0)), ("błękitny", (0, 200, 255)), ("niebieski", (0, 0, 255)),
               ("fioletowy", (180, 0, 255)), ("biały", (255, 255, 255))]


@reg("kolory")
class ColorTest(Clock):
    """Test kolorów: 8 pasów (czerwony, pomarańczowy, żółty, zielony, błękitny, niebieski, fioletowy, biały), u góry
    pełne, u dołu przygaszone. Do kalibracji: ustawienia „diody: …” dopasowują podgląd do tego, co widać na panelu."""

    def draw(self, f, now, t, dt):
        n = len(TEST_COLORS)
        for i, (_, c) in enumerate(TEST_COLORS):
            x0, x1 = i * W // n, (i + 1) * W // n - 2
            f.rect(x0, 0, x1, 5, c)
            f.rect(x0, 7, x1, 11, mul(c, 0.5))


# ---------------------------------------------------------------- wiadomości od widzów
ENVELOPE = ["YYYYYYYYYYY", "DDYYYYYYYDD", "YDDYYYYYDDY", "YYDDYYYDDYY", "YYYDDYDDYYY", "YYYYDDDYYYY",
            "YYYYYYYYYYY", "YYYYYYYYYYY"]


@reg("napisz")
class Inbound(Clock):
    """Wiadomości od widzów (np. uczestników calla): sam adres (domena:port – tunel bore.pub albo własny),
    pod który wysyła się tekst – echo do /dev/tcp, curl albo przeglądarka – a potem po kolei to, co przyszło.
    Skrzynkę otwiera się w panelu WWW – tylko wtedy coś przyjmuje."""

    X0 = 13  # tekst zaczyna się za kopertą

    def __init__(self):
        self.cur, self.t0, self.dur = None, 0.0, 0.0

    def draw(self, f, now, t, dt):
        if self.cur is not None and t - self.t0 > self.dur:
            self.cur = None
        if self.cur is None:
            self.cur = INBOX.take()
            if self.cur is not None:
                self.t0 = t
                tw = text_w(self.cur, TXT)
                self.dur = 6.0 if tw <= W - self.X0 else scroll_time(tw + W - self.X0, 30) + 0.5
        if self.cur is not None:  # wiadomość: krótka stoi na środku, długa przejeżdża raz
            k = t - self.t0
            flash = k < 0.6 and int(k * 6) % 2 == 0
            sprite(f, ENVELOPE, 0, 2, {"Y": (255, 255, 255) if flash else (255, 200, 0), "D": (40, 25, 0)})
            tw = text_w(self.cur, TXT)
            x = self.X0 + (W - self.X0 - tw) // 2 if tw <= W - self.X0 else W - scroll_px(k, 30)
            f.draw([(px, py) for px, py in text_px(self.cur, x, 0, TXT) if px >= self.X0], (255, 255, 255))
            return
        addr = INBOX.address() if INBOX.is_open() else ""
        if not addr:  # zamknięta albo tunel jeszcze się łączy
            sprite(f, ENVELOPE, 0, 2, {"Y": (90, 60, 0), "D": (20, 12, 0)})
            msg = "connecting" + "." * (int(t * 2) % 4) if INBOX.is_open() else "inbox closed"
            f.text(msg, self.X0 + 2, 0, (120, 120, 140))
            return
        sprite(f, ENVELOPE, 0, 2, {"Y": (255, 200, 0), "D": (40, 25, 0)})
        addr = addr.split("://", 1)[-1]  # sam adres: domena:port (własny port – jeszcze kod w ścieżce)
        tw = text_w(addr, TXT)
        if tw <= W - self.X0:
            f.text(addr, self.X0 + (W - self.X0 - tw) // 2, 0, (80, 200, 255), TXT)
        else:
            scroll_segs(f, [(addr, (80, 200, 255))], t, 30, 0, self.X0, gap=40)


# ================================================================ postacie i zwierzęta (bez zegara)
CAT = {
    "idzie1": ["............O.O.", "O...........OOO.", "O...........OEON", ".O.SOSOSOSOOOOO.", "..OOOOOOOOOOOO..",
               "..OOOOOOOOOOO...", "..O.O.....O.O...", ".O...O...O...O.."],
    "idzie2": ["............O.O.", ".O..........OOO.", "O...........OEON", "O..SOSOSOSOOOOO.", ".OOOOOOOOOOOOO..",
               "..OOOOOOOOOOO...", "...O.O...O.O....", "...O.O...O.O...."],
    "skok": ["............O.O.", "............OOO.", "OO..........OEON", "..OSOSOSOSOOOOO.", "..OOOOOOOOOOOO..",
             ".OOOOOOOOOOOO...", "O..........OO...", "................"],
    "siedzi": ["......O.O.", "......OOO.", "......OEON", ".....OOOO.", "....SOOOO.", "O..OSOOOO.",
               "O.OOOOOOO.", ".OOOOO.OO."],
    "liże": ["..........", "......O.O.", "......OOO.", "......OEOP", ".....OOOP.", "O..SOOOO..",
             "O.OOOOOOO.", ".OOOOO.OO."],
    "śpi": [".........O.O.", "..SOSOSOOOOO.", ".OOOOOOOOCOON", "OOOOOOOOOOOOO"],
}


@reg("kotek")
class Kitten(Clock):
    """Kotek: chodzi po panelu, goni czerwoną kropkę lasera i rzuca się na nią, siada, myje się, zasypia (Zzz)."""
    PAL = {"O": (230, 120, 25), "S": (150, 60, 10), "E": (60, 255, 60), "N": (255, 110, 150), "P": (255, 110, 150),
           "C": (90, 40, 10)}

    def __init__(self):
        self.x, self.dirr, self.state, self.until, self.goal = W / 3, 1, "idzie", 0.0, W / 2
        self.dot, self.jump = None, None

    def pick(self, t):
        self.state = random.choice(("idzie", "laser", "laser", "siedzi", "liże", "śpi"))
        self.until = t + {"idzie": 5, "laser": 10, "siedzi": 3, "liże": 4, "śpi": 8}[self.state] * random.uniform(0.8, 1.4)
        self.goal = random.uniform(5, W - 20)
        if self.state == "laser":
            self.dot = [random.uniform(5, W - 5), random.uniform(4, 10), t]

    def draw(self, f, now, t, dt):
        if t >= self.until and not self.jump:
            self.pick(t)
        pal = {k: visible(v) for k, v in self.PAL.items()}
        for x in range(W):
            f.set(x, 11, visible((20, 14, 30)))  # podłoga
        pose = "siedzi"
        if self.jump:  # skok na kropkę: łuk
            x0, x1, t0 = self.jump
            p = (t - t0) / 0.6
            if p >= 1:
                self.x, self.jump = x1, None
                if self.dot:
                    self.dot = [random.uniform(5, W - 5), random.uniform(4, 10), t]  # kropka ucieka
            else:
                self.x = x0 + (x1 - x0) * p
                sprite(f, CAT["skok"], self.x, 3 - 4 * math.sin(math.pi * p), pal, self.dirr < 0)
                self.draw_dot(f, t)
                return
        if self.state == "laser" and self.dot:
            if t - self.dot[2] > random.uniform(1.2, 2.5) and random.random() < 0.02:
                self.dot = [clamp(self.dot[0] + random.uniform(-40, 40), 5, W - 5), random.uniform(4, 10), t]
            target = self.dot[0] - (12 if self.dot[0] > self.x + 6 else -2)
            if abs(target - self.x) > 14:
                self.walk(f, t, dt, target, 34, pal)
            else:
                self.jump = (self.x, clamp(self.dot[0] - 8, -2, W - 14), t)
                self.dirr = 1 if self.dot[0] > self.x + 6 else -1
            self.draw_dot(f, t)
            return
        self.dot = None
        if self.state == "idzie":
            if abs(self.goal - self.x) > 1:
                self.walk(f, t, dt, self.goal, 9, pal)
                return
            pose = "siedzi"
        elif self.state in ("liże", "śpi"):
            pose = "liże" if self.state == "liże" and int(t * 3) % 2 else self.state if self.state == "śpi" else "siedzi"
        rows = CAT[pose]
        w = len(rows[0])
        sx = self.x + (16 - w if self.dirr > 0 else 0)
        sprite(f, rows, sx, 11 - len(rows), pal, self.dirr < 0)
        if pose == "śpi":  # Zzz
            for k in range(3):
                ph = (t * 0.5 + k / 3) % 1
                zx = sx + (w if self.dirr > 0 else 0) + ph * 8 * self.dirr
                f.text("Z", zx, 4 - ph * 6 - 2, mul((150, 150, 255), 1 - ph), SMALL)

    def walk(self, f, t, dt, goal, v, pal):
        self.dirr = 1 if goal > self.x else -1
        self.x += min(abs(goal - self.x), v * dt) * self.dirr
        sprite(f, CAT["idzie1" if int(t * v / 3) % 2 else "idzie2"], self.x, 3, pal, self.dirr < 0)

    def draw_dot(self, f, t):
        x, y, _ = self.dot
        f.set(x, y, (255, 0, 0))
        for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            f.add(x + ox, y + oy, (60, 0, 0))


DOG = {
    "biegnie1": ["...........OO...", "..........OOEOO.", "O.........DOOOOK", ".O........D.....", "..OOOOOOOOOO....",
                 "..OOOOOOOOOO....", "..O.O.....O.O...", ".O...O...O...O.."],
    "biegnie2": ["...........OO...", "..........OOEOO.", "..........DOOOOK", "OO........D.....", "..OOOOOOOOOO....",
                 "..OOOOOOOOOO....", "...O.O...O.O....", "...O.O...O.O...."],
    "siedzi": [".....OO...", "....OOEOO.", "....DOOOOK", "....DOO...", "...OOOO...", "..OOOOO...", ".OOOOOO...",
               "OOO.OOO..."],
    "kopie1": ["................", "................", "O...............", ".OOOOOOOOOO.....", "..OOOOOOOOOOO...",
               "..OOOOOOOOOOEOO.", "..O.O.....DOOOOK", "..O.O.....O.O..."],
    "kopie2": ["................", "................", ".O..............", ".OOOOOOOOOO.....", "..OOOOOOOOOOO...",
               "..OOOOOOOOOOEOO.", "..O.O.....DOOOOK", "..O.O......O.O.."],
}


@reg("pies")
class Dog(Clock):
    """Pies: goni rzuconą piłkę, przynosi ją w pysku, siada i merda ogonem, czasem kopie dołek, aż leci ziemia."""
    PAL = {"O": (170, 100, 40), "D": (90, 50, 20), "E": (20, 20, 20), "K": (10, 10, 10)}

    def __init__(self):
        self.x, self.dirr, self.state, self.t0 = W / 2, 1, "siedzi", 0.0
        self.ball, self.dirt = None, []

    def draw(self, f, now, t, dt):
        pal = {k: visible(v) for k, v in self.PAL.items()}
        pal["E"], pal["K"] = (230, 230, 230), (60, 30, 30)
        for x in range(W):
            f.set(x, 11, visible((20, 60, 10)))  # trawa
        age = t - self.t0
        if self.state == "siedzi" and age > 3:
            self.state, self.t0 = random.choice(("rzut", "rzut", "kopie")), t
            if self.state == "rzut":  # piłka wpada z boku łukiem i odbija się
                side = random.choice((-1, 1))
                self.ball = [W / 2 - side * 70, 2.0, side * random.uniform(30, 45), -6.0]
        if self.state == "rzut":
            b = self.ball
            b[3] += 30 * dt
            b[0] += b[2] * dt
            b[1] += b[3] * dt
            if b[1] > 9.5:
                b[1], b[3], b[2] = 9.5, -abs(b[3]) * 0.55, b[2] * 0.8
            if abs(b[2]) < 3 and abs(b[3]) < 3:
                b[2] = 0
            b[0] = clamp(b[0], 1, W - 2)
            mouth = self.x + (15 if self.dirr > 0 else 0)
            if abs(b[0] - mouth) > 2:
                goal = b[0] - (15 if b[0] > self.x + 7 else 0)
                self.run(f, t, dt, goal, 30, pal)
            else:
                self.state, self.goal = "niesie", random.uniform(20, W - 36)
            disc(f, b[0], b[1], 1.3, (230, 255, 0))
            return
        if self.state == "niesie":
            if abs(self.goal - self.x) > 1:
                self.run(f, t, dt, self.goal, 18, pal)
                disc(f, self.x + (16 if self.dirr > 0 else -1), 5.5, 1.3, (230, 255, 0))
                return
            self.state, self.t0 = "siedzi", t
        if self.state == "kopie":
            if age > 4:
                self.state, self.t0 = "siedzi", t
            pose = "kopie1" if int(t * 8) % 2 else "kopie2"
            sprite(f, DOG[pose], self.x, 3, pal, self.dirr < 0)
            if random.random() < 0.6:
                bx = self.x + (2 if self.dirr > 0 else 13)
                self.dirt.append([bx, 10, -self.dirr * random.uniform(8, 20), -random.uniform(6, 12)])
        else:
            sx = self.x + (6 if self.dirr > 0 else 0)
            sprite(f, DOG["siedzi"], sx, 3, pal, self.dirr < 0)
            wag = int(t * 10) % 2  # merda
            tx = sx - 1 if self.dirr > 0 else sx + 10
            f.set(tx, 8 + wag, pal["O"])
            f.set(tx - self.dirr, 7 + 2 * wag, pal["O"])
        keep = []
        for p in self.dirt:
            p[3] += 30 * dt
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            if p[1] < 11:
                f.set(p[0], p[1], visible((110, 70, 30)))
                keep.append(p)
        self.dirt = keep[-60:]

    def run(self, f, t, dt, goal, v, pal):
        self.dirr = 1 if goal > self.x else -1
        self.x += min(abs(goal - self.x), v * dt) * self.dirr
        sprite(f, DOG["biegnie1" if int(t * v / 3) % 2 else "biegnie2"], self.x, 3, pal, self.dirr < 0)


HERO = {"biegnie1": ["..RRR.", ".RRRRR", ".SSE..", ".SSSS.", "BRBBR.", ".BBBB.", ".B..B.", "KK..KK"],
        "biegnie2": ["..RRR.", ".RRRRR", ".SSE..", ".SSSS.", ".RBBRB", ".BBBB.", "..BB..", "..KK.."],
        "skok": ["..RRR.", ".RRRRR", ".SSE.S", ".SSSSS", "BRBBR.", ".BBBB.", "B...B.", "K....K"]}
GOOMBA = [["..MMMM..", ".MMMMMM.", "MEMMMMEM", "MMMMMMMM", "..SSSS..", ".KK..KK."],
          ["..MMMM..", ".MMMMMM.", "MEMMMMEM", "MMMMMMMM", "..SSSS..", "..KK.KK."]]


@reg("platformowka")
class Platformer(Clock):
    """Platformówka: ludzik w czerwonej czapce biegnie przez przewijany świat, przeskakuje rury, dziury i grzyby,
    zbiera monety i wybija je z bloków ze znakiem zapytania."""
    SPEED, HX = 22, 24

    def __init__(self):
        self.y, self.vy, self.coins, self.got, self.pops = 2.0, 0.0, 0, set(), []

    @staticmethod
    def tile(i):
        """Co jest w kolumnie świata nr i (co 8 px): None, ("rura", wys), ("dziura",), ("grzyb",), ("blok",)."""
        if i < 6:
            return None
        h = hash1(i * 977)
        if h < 0.14:
            return ("rura", 3 + int(hash1(i * 31) * 3))
        if h < 0.22 and Platformer.tile(i - 1) is None:
            return ("dziura",)
        if h < 0.32:
            return ("grzyb",)
        if h < 0.45:
            return ("blok",)
        return None

    def draw(self, f, now, t, dt):
        off = t * self.SPEED
        sky = visible((10, 20, 60))
        f.fill(sky)
        for k in range(4):  # chmury
            cx = (k * 37 - off * 0.3) % (W + 30) - 15
            disc(f, cx, 2.5 + k % 2, 2.2, visible((80, 90, 120)))
            disc(f, cx + 3, 2.5 + k % 2, 2.6, visible((80, 90, 120)))
        brick, top = visible((150, 70, 20)), visible((40, 160, 30))
        i0 = int(off // 8)
        ground = {}
        for i in range(i0 - 1, i0 + W // 8 + 2):
            x0 = i * 8 - off
            tl = self.tile(i)
            for x in range(int(x0), int(x0) + 8):
                if not 0 <= x < W:
                    continue
                if tl and tl[0] == "dziura":
                    continue
                ground[x] = True
                f.set(x, 10, top)
                f.set(x, 11, brick if (x + int(off)) % 4 else visible((90, 40, 10)))
            if tl and tl[0] == "rura":
                h = tl[1]
                f.rect(x0 + 1, 10 - h, x0 + 6, 9, visible((0, 150, 30)))
                f.rect(x0, 10 - h, x0 + 7, 10 - h, visible((60, 220, 60)))
                f.rect(x0 + 2, 11 - h, x0 + 2, 9, visible((100, 255, 100)))
            if tl and tl[0] == "blok":
                hit = i in self.got
                f.rect(x0 + 2, 2, x0 + 5, 4, visible((120, 70, 20)) if hit else (230, 160, 0))
                if not hit:
                    f.set(x0 + 3, 3, (90, 40, 0))
                if not hit and abs(x0 + 3.5 - (self.HX + 3)) < 3 and self.y < 6:
                    self.got.add(i)
                    self.coins += 1
                    self.pops.append([x0 + 3, 1.0, t])
            if tl and tl[0] == "grzyb" and i not in self.got:
                gx = x0 + 4 - ((t * 6) % 16 if hash1(i) > 0.5 else 0)
                sprite(f, GOOMBA[int(t * 4) % 2], gx - 4, 4, {"M": visible((140, 70, 30)), "E": (255, 255, 255),
                                                            "S": visible((230, 190, 140)), "K": visible((40, 20, 10))})
                if abs(gx - (self.HX + 3)) < 4 and self.y > 0 and self.vy > 0 and self.y < 4:
                    self.got.add(i)  # zgnieciony z góry
                    self.vy = -9
        # sterowanie: skacze, gdy przed nim przeszkoda (patrzy kilka kolumn naprzód)
        ahead = [self.tile(int((off + self.HX + d) // 8)) for d in (6, 12, 18)]
        on_ground = self.y >= 2 and all(ground.get(int(self.HX + k), False) for k in (1, 4))
        if on_ground and any(a and a[0] in ("rura", "dziura", "grzyb", "blok") for a in ahead[:2]):
            self.vy = -15
        self.vy += 40 * dt
        self.y += self.vy * dt
        if self.y >= 2:
            if any(ground.get(int(self.HX + k), False) for k in (1, 4)) or self.y > 12:
                self.y, self.vy = 2.0, 0.0
        if self.y < -6:
            self.y, self.vy = -6, 0
        pal = {"R": (230, 20, 20), "S": visible((240, 180, 130)), "E": (0, 0, 0), "B": (30, 60, 230), "K": visible((90, 40, 10))}
        pose = "skok" if self.y < 1.8 else "biegnie1" if int(t * 8) % 2 else "biegnie2"
        sprite(f, HERO[pose], self.HX, self.y, pal)
        for p in list(self.pops):  # moneta wyskakuje z bloku
            a = t - p[2]
            if a > 0.6:
                self.pops.remove(p)
                continue
            f.rect(p[0], p[1] - a * 6 - 1, p[0] + 1, p[1] - a * 6, (255, 220, 0))
        self.got = {i for i in self.got if i >= i0 - 2}
        f.rect(W - 15, 1, W - 14, 3, (255, 220, 0))  # moneta i licznik
        f.text(str(self.coins % 1000), W - 12, 0, (255, 255, 255), SMALL)


@reg("ptaki")
class Birds(Clock):
    """Ptaki: klucze ptaków lecą przez niebo o zachodzie słońca, machając skrzydłami; słońce chowa się za horyzont."""

    def __init__(self):
        self.flocks, self.next = [], 0.0

    def draw(self, f, now, t, dt):
        for y in range(H):  # zachód: od fioletu u góry do pomarańczu nad horyzontem
            c = lerp((25, 5, 45), (200, 70, 10), (y / (H - 1)) ** 1.4)
            for x in range(W):
                f.set(x, y, visible(c))
        sx = W * 0.7
        disc(f, sx, 10.5, 4.5, (255, 140, 20))
        disc(f, sx, 10.5, 3.2, (255, 200, 60))
        for x in range(W):
            f.set(x, 11, visible((40, 10, 20)))
        if t >= self.next:
            n, d = random.choice((3, 5, 7)), random.choice((-1, 1))
            self.flocks.append({"x": -20 if d > 0 else W + 20, "y": random.uniform(1, 3), "d": d, "n": n,
                                "v": random.uniform(8, 14), "ph": random.random()})
            self.next = t + random.uniform(4, 9)
        dark = (5, 0, 10)
        for fl in list(self.flocks):
            fl["x"] += fl["d"] * fl["v"] * dt
            if (fl["d"] > 0 and fl["x"] > W + 40) or (fl["d"] < 0 and fl["x"] < -40):
                self.flocks.remove(fl)
                continue
            for k in range(fl["n"]):  # klucz: V, przewodnik z przodu
                row = (k + 1) // 2
                side = 1 if k % 2 else -1
                bx = fl["x"] - fl["d"] * row * 6
                by = fl["y"] + 2 + side * row * 1.6 * (0.85 + 0.15 * math.sin(t + k))
                up = math.sin((t * 6 + fl["ph"] * 7 + k * 0.7)) > 0
                f.set(bx, by, dark)
                for s in (-1, 1):  # skrzydła: w górę „V”, w dół „Λ”
                    f.set(bx + s, by - 1 if up else by, dark)
                    f.set(bx + 2 * s, by - 2 if up else by + 1, dark)


@reg("nietoperze")
class Bats(Clock):
    """Nietoperze: noc, wielki księżyc, gwiazdy; nietoperze trzepoczą zygzakiem po niebie, czasem przelatują
    na tle księżyca."""

    def __init__(self):
        self.bats = [self.new(random.uniform(0, W)) for _ in range(6)]

    @staticmethod
    def new(x=None):
        d = random.choice((-1, 1))
        return {"x": (-5 if d > 0 else W + 5) if x is None else x, "y": random.uniform(2, 9), "d": d,
                "v": random.uniform(10, 22), "ph": random.random() * 9, "f": random.uniform(10, 16)}

    def draw(self, f, now, t, dt):
        for k in range(30):
            x, y = int(hash1(k * 17) * W), int(hash1(k * 29) * 10)
            f.set(x, y, mul((160, 160, 200), 0.3 + 0.7 * noise1(t * 0.8 + k * 3)))
        mx = W * 0.68
        for y in range(H):  # księżyc z cieniami
            for x in range(int(mx - 7), int(mx + 8)):
                d = math.hypot(x + 0.5 - mx, (y + 0.5 - 6) * 1.0)
                if d < 5.6:
                    k = 0.75 + 0.25 * noise2(x * 0.6, y * 0.6)
                    f.set(x, y, mul((240, 230, 170), clamp(5.9 - d) * k))
                elif d < 8:
                    f.add(x, y, mul((40, 40, 25), (8 - d) / 2.4))
        for x in range(W):  # sylwetki drzew
            h = 1 + int(noise1(x * 0.15) * 3 + (hash1(x // 5) > 0.85) * 2)
            for y in range(H - h, H):
                f.set(x, y, (0, 0, 0))
        for b in self.bats:
            b["x"] += b["d"] * b["v"] * dt
            b["y"] = clamp(b["y"] + math.sin(t * 3 + b["ph"]) * 6 * dt + random.uniform(-3, 3) * dt, 1, 8)
            if b["x"] < -8 or b["x"] > W + 8:
                b.update(self.new())
            x, y = int(b["x"]), int(b["y"])
            up = math.sin(t * b["f"] + b["ph"]) > 0
            col = (0, 0, 0) if abs(x - mx) < 7 else visible((70, 50, 90))
            for ox, oy in ((0, 0), (0, 1)):
                f.set(x + ox, y + oy, col)
            for s in (-1, 1):
                f.set(x + s, y + (0 if up else 1), col)
                f.set(x + 2 * s, y + (-1 if up else 1), col)
                f.set(x + 3 * s, y + (0 if up else 2), col)


TURTLE = ["...........GGGGG.......", ".........GGHGGGHGG.....", "..F.....GGGGHGGGGGG....",
          "..FF...GGHGGGGGGHGGG.SS", "...FF.GGGGGHGGGGGGGGSSSE", "....FSGGGHGGGGGHGGGGSSSS",
          ".....SSSSSSSSSSSSSSSS.SS", "......FF.........FF....", ".......FF.........FF..."]


@reg("zolw")
class Turtle(Clock):
    """Żółw morski: płynie powoli przez cały panel, macha płetwami; promienie światła z góry, bąbelki,
    falujące wodorosty na dnie."""

    def __init__(self):
        self.bub = []

    def draw(self, f, now, t, dt):
        for y in range(H):
            for x in range(W):
                ray = max(0.0, math.sin(x * 0.12 + y * 0.35 - t * 0.6)) ** 6 * (1 - y / H)  # promienie
                f.set(x, y, visible(lerp((0, 15, 45), (40, 110, 140), ray * 0.7 + 0.1 * (1 - y / H))))
        for k in range(14):  # wodorosty
            bx = (hash1(k * 7) * W)
            hgt = 3 + int(hash1(k * 11) * 5)
            for j in range(hgt):
                f.set(bx + math.sin(t * 1.5 + k + j * 0.6) * j * 0.25, 11 - j, visible((20, 120 + j * 10, 40)))
        span = W + 50
        x = (t * 6) % span - 25
        up = math.sin(t * 2.2)
        pal = {"G": visible((60, 120, 40)), "H": visible((120, 90, 30)), "S": visible((140, 160, 90)),
               "F": visible((110, 140, 80)), "E": (0, 0, 0)}
        rows = [r for r in TURTLE]
        if up > 0:  # płetwy w górę / w dół
            rows = rows[:7] + [".....FF.........FF.....", "......................."]
        sprite(f, rows, x, 1.5 + math.sin(t * 0.7) * 0.8, pal)
        if random.random() < dt * 3:
            self.bub.append([x + 22, 4.0, random.uniform(-0.5, 0.5)])
        keep = []
        for b in self.bub:
            b[1] -= 4 * dt
            b[0] += math.sin(t * 5 + b[2] * 9) * 0.3 * dt
            if b[1] > -1:
                f.add(b[0], b[1], (60, 90, 110))
                keep.append(b)
        self.bub = keep


SNAIL = ["......E...E", ".......E.E.", "..SSSS..BB.", ".SPPPPS.BB.", "SPSSSPPS.B.", "SPSPSSPSBB.",
         "SPPSSPS.BB.", ".SSSSSBBBB.", "BBBBBBBBBBB"]


@reg("slimak")
class Snail(Clock):
    """Ślimak: bardzo powoli pełznie przez łąkę, rusza czułkami, zostawia błyszczący ślad; kwiatki się kołyszą,
    czasem przelatuje motyl."""

    def draw(self, f, now, t, dt):
        for x in range(W):
            f.set(x, 11, visible((20, 70, 10)))
            gh = int(1 + noise1(x * 0.7) * 2)
            for j in range(gh):
                f.set(x + math.sin(t + x) * 0.3 * j, 10 - j, visible((30, 110 + 30 * j, 20)))
        for k in range(7):  # kwiatki
            fx = hash1(k * 13) * W
            sway = math.sin(t * 1.3 + k) * 0.8
            for j in range(4):
                f.set(fx + sway * j / 4, 10 - j, visible((40, 140, 30)))
            c = [(255, 60, 60), (255, 220, 0), (200, 80, 255), (255, 255, 255)][k % 4]
            for ox, oy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
                f.set(fx + sway + ox, 6 + oy, visible(c))
            f.set(fx + sway, 6, (255, 200, 0))
        span = W + 30
        x = (t * 2.2) % span - 15
        for k in range(int(max(0, x + 1))):  # ślad – błyszczy
            if x - k < 0:
                break
            f.set(x - k, 10, mul((90, 110, 130), (0.3 + 0.7 * (math.sin(k * 1.7 + t * 2) > 0.7)) * max(0, 1 - k / 60)))
        ant = int(t * 1.5) % 4 == 0
        rows = SNAIL if not ant else [SNAIL[1], SNAIL[1]] + SNAIL[2:]
        sprite(f, rows, x, 2, {"S": visible((150, 90, 30)), "P": visible((230, 170, 70)), "B": visible((170, 160, 120)),
                               "E": (255, 255, 255)})
        bx = (t * 15) % (W + 40) - 20  # motyl
        by = 3 + math.sin(t * 2.5) * 2
        up = int(t * 12) % 2
        for s in (-1, 1):
            f.set(bx + s, by - up, (255, 120, 220))
        f.set(bx, by, (60, 30, 20))


# ================================================================ światło (bez zegara)
@reg("polarna")
class AuroraCurtain(Clock):
    """Zorza polarna z bliska: falujące kurtyny światła z pionowymi promieniami, zielone u dołu, fioletowe
    u góry; pod nimi ośnieżone góry i gwiazdy."""

    def draw(self, f, now, t, dt):
        for k in range(25):
            f.set(hash1(k * 5) * W, hash1(k * 9) * 7, mul((150, 150, 180), 0.4 + 0.6 * noise1(t + k)))
        for x in range(W):
            for band, (sp, amp, hue) in enumerate(((0.05, 1.0, 0.0), (0.08, 0.7, 0.4))):
                base = 7.5 - band * 2 + math.sin(x * sp + t * 0.4 * (1 + band)) * 1.8 + noise1(x * 0.1 + t * 0.3) * 1.5
                ray = (0.25 + 0.75 * noise2(x * 0.45, t * 0.8 + band * 9) ** 1.5) * amp * 1.8  # pionowe promienie
                for y in range(H):
                    h = base - y  # wysokość nad dolnym brzegiem kurtyny
                    if h < -1 or h > 9:
                        continue
                    k = clamp(1 - abs(h - 0.5) * 0.9) if h < 0.5 else clamp(1 - (h - 0.5) / 8) ** 1.6
                    c = lerp((0, 255, 90), (140, 40, 255), clamp(h / 7 + hue * 0.3))
                    f.add(x, y, mul(c, k * ray * 0.9))
        for x in range(W):  # góry
            top = 9 + int(noise1(x * 0.06) * 2.5) - (hash1(x // 9) > 0.7)
            for y in range(top, H):
                f.set(x, y, visible((60, 70, 90)) if y == top else visible((15, 18, 28)))


@reg("tesla")
class PlasmaBall(Clock):
    """Lampa plazmowa: szklane kule, w środku elektroda, z której biegną do szkła drżące fioletowe wyładowania;
    co jakiś czas „dotyk” – wszystkie pioruny zbiegają się w jednym miejscu."""

    def __init__(self):
        self.touch, self.tx = None, 0

    def draw(self, f, now, t, dt):
        if self.touch is None or t > self.touch + random.uniform(4, 7):
            self.touch, self.tx = t, random.choice((-1, 1))
        touching = t - self.touch < 2.2
        for cx in (W / 2 - 34, W / 2, W / 2 + 34):
            r = 5.7
            for y in range(H):  # szkło – lekka poświata
                for x in range(int(cx - 7), int(cx + 8)):
                    d = math.hypot(x + 0.5 - cx, y + 0.5 - 6)
                    if d < r:
                        f.set(x, y, visible((18, 0, 28)))
                    elif d < r + 0.8:
                        f.set(x, y, visible((40, 30, 60)))
            n = 7
            for k in range(n):
                if touching and cx == W / 2:
                    a = math.pi * (0.5 - 0.5 * self.tx) + noise1(t * 3 + k) * 0.3 - 0.15
                else:
                    a = k / n * 2 * math.pi + noise1(t * 0.6 + k * 5 + cx) * 2.5
                x, y = cx, 6.0
                steps = 9
                for s in range(1, steps + 1):  # pierun: drży poprzecznie
                    p = s / steps
                    jit = (noise2(k * 3 + s, t * 9 + cx) - 0.5) * 1.6 * math.sin(math.pi * p)
                    nx = cx + math.cos(a) * r * p - math.sin(a) * jit
                    ny = 6.0 + math.sin(a) * r * p + math.cos(a) * jit
                    c = lerp((255, 200, 255), (150, 0, 255), p)
                    f.add(nx, ny, mul(c, 0.8))
                    x, y = nx, ny
                f.add(x, y, (255, 120, 255))  # rozbłysk na szkle
            disc(f, cx + 0.5, 6.5, 1.6, (255, 230, 255))
            f.rect(cx - 3, 11, cx + 3, 11, visible((50, 50, 55)))  # podstawka


NEON_SIGNS = [("OPEN", (255, 30, 60)), ("BAR", (0, 200, 255)), ("CAFE", (255, 160, 0)), ("24H", (0, 255, 120)),
              ("LIVE", (255, 0, 200)), ("PIZZA", (255, 220, 0))]


@reg("szyld")
class NeonSign(Clock):
    """Neonowy szyld: świecące rurki z napisem (OPEN, BAR, CAFE, PIZZA…) i ikonką (serce, kubek, strzałka),
    z poświatą; jarzeniówka się zapala z migotaniem, czasem jedna litera przerywa."""
    ICONS = {"serce": [".RR.RR.", "RRRRRRR", "RRRRRRR", ".RRRRR.", "..RRR..", "...R..."],
             "kubek": ["..R.R..", ".R.R...", "RRRRR..", "R...RR.", "R...R.R", "R...RR.", ".RRR..."],
             "strzałka": ["...R...", "...RR..", "RRRRRR.", "RRRRRRR", "RRRRRR.", "...RR..", "...R..."]}

    def __init__(self):
        self.i, self.t0, self.bad = 0, None, 0

    def draw(self, f, now, t, dt):
        if self.t0 is None or t - self.t0 > 12:
            self.i = (self.i + (self.t0 is not None)) % len(NEON_SIGNS)
            self.t0, self.bad = t, random.randint(0, 9)
        word, col = NEON_SIGNS[self.i]
        icon = list(self.ICONS)[self.i % len(self.ICONS)]
        age = t - self.t0
        on = age > 0.8 or hash1(int(t * 20)) > 0.5  # zapalanie z migotaniem
        if age > 11.4:
            on = False
        ic = self.ICONS[icon]
        font = TXT
        tw = text_w(word, font)
        total = tw + 4 + len(ic[0])
        x0 = (W - total) // 2
        glow = Persist()
        pts = text_px(word, x0, 0, font)
        letters = []
        x = x0
        for ch in word:
            letters.append(x)
            x += text_w(ch, font) + 1
        for px, py in pts:
            li = sum(1 for lx in letters if lx <= px) - 1
            dead = li == self.bad % len(word) and hash1(int(t * 6)) < 0.25  # jedna litera przerywa
            if on and not dead:
                f.set(px, py, lerp(col, (255, 255, 255), 0.35))
                for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    glow.add(px + ox, py + oy, mul(col, 0.12))
            else:
                f.set(px, py, visible(mul(col, 0.06)))
        ix = x0 + tw + 4
        c2 = (255, 255, 255) if icon == "kubek" else col
        for r, row in enumerate(ic):
            for k, ch in enumerate(row):
                if ch == "R":
                    f.set(ix + k, 3 + r, mul(c2, 0.9) if on else visible(mul(c2, 0.06)))
        if on:
            for y in range(H):
                for x in range(W):
                    if f.px[y][x] == (0, 0, 0):
                        g = glow.b[y][x]
                        f.px[y][x] = (min(g[0], 60), min(g[1], 60), min(g[2], 60))
        for x in range(x0 - 4, x0 + total + 4):  # rama szyldu
            f.set(x, 11, visible((30, 30, 35)))


@reg("witraz")
class StainedGlass(Clock):
    """Witraż: kolorowe szybki w ołowianych ramkach, przez które przesuwa się słońce – po kolei rozjaśnia
    szkło, a szybki mienią się delikatnie."""
    COLS = [(200, 20, 30), (20, 60, 200), (230, 170, 0), (20, 150, 60), (140, 30, 170), (0, 150, 170)]

    def draw(self, f, now, t, dt):
        sun = (t * 7) % (W + 60) - 30
        for y in range(H):
            for x in range(W):
                # komórki: przesunięta siatka romboidalna z ołowiem na brzegach
                u, v = x / 9 + y / 6, x / 9 - y / 6
                iu, iv = math.floor(u), math.floor(v)
                fu, fv = u - iu, v - iv
                if min(fu, fv, 1 - fu, 1 - fv) < 0.07 or y in (0, 11):
                    f.set(x, y, visible((25, 22, 20)))
                    continue
                c = self.COLS[int(hash1(iu * 131 + iv * 71) * len(self.COLS))]
                light = 0.35 + 0.75 * math.exp(-((x - sun) / 24) ** 2) + 0.1 * noise2(x * 0.3, t * 0.5)
                f.set(x, y, mul(c, clamp(light, 0.08, 1.1)))


@reg("basen")
class Caustics(Clock):
    """Dno basenu w słońcu: falujące świetliste sieci kaustyk na turkusowych kafelkach."""

    def draw(self, f, now, t, dt):
        for y in range(H):
            for x in range(W):
                u, v = x * 0.18, y * 0.3
                a = math.sin(u + t * 1.1 + math.sin(v * 1.3 + t * 0.7) * 1.5)
                b = math.sin(v * 1.7 - t * 0.9 + math.sin(u * 0.8 - t * 0.6) * 1.5)
                c = math.sin((u + v) * 0.9 + t * 0.8)
                k = (1 - abs(a + b + c) / 3) ** 6  # jasne linie tam, gdzie fale się spotykają
                base = (0, 70, 110) if (x // 6 + y // 6) % 2 else (0, 60, 100)
                if x % 6 == 0 or y % 6 == 0:
                    base = (0, 45, 80)  # fugi
                f.set(x, y, lerp(visible(base), (200, 255, 255), clamp(k * 1.3)))


@reg("iskry")
class Sparks(Clock):
    """Szlifierka: tarcza się kręci, strumień rozżarzonych iskier leci łukiem, odbija się od podłogi i gaśnie;
    szlifierka przesuwa się po stalowym pręcie."""

    def __init__(self):
        self.sp, self.acc = [], 0.0

    def draw(self, f, now, t, dt):
        gx = W * 0.25 + math.sin(t * 0.3) * W * 0.15
        f.rect(0, 6, W * 0.45, 7, visible((70, 70, 80)))  # pręt
        for x in range(W):
            f.set(x, 11, visible((25, 25, 30)))
        burst = 0.6 + 0.4 * noise1(t * 2)
        self.acc += 260 * dt * burst
        while self.acc >= 1:
            self.acc -= 1
            a = random.uniform(-0.35, 0.2)
            s = random.uniform(30, 80)
            self.sp.append([gx + 2, 5.5, math.cos(a) * s, math.sin(a) * s - 8, random.uniform(0.5, 1.4)])
        keep = []
        for p in self.sp:
            p[3] += 60 * dt
            ox, oy = p[0], p[1]
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[4] -= dt
            if p[1] > 10.5:
                p[1], p[3], p[2] = 10.5, -abs(p[3]) * 0.35, p[2] * 0.6
            if p[4] > 0 and p[0] < W + 2:
                heat = clamp(p[4])
                c = lerp((255, 40, 0), (255, 200, 60), heat)
                f.line(ox, oy, p[0], p[1], mul(c, heat), add=True)
                keep.append(p)
        self.sp = keep[-500:]
        disc(f, gx, 5.5, 3.5, visible((60, 60, 70)))  # tarcza z kręcącymi się szprychami
        for k in range(3):
            a = t * 25 + k * 2.09
            f.set(gx + math.cos(a) * 2.2, 5.5 + math.sin(a) * 2.2, visible((150, 150, 160)))
        f.rect(gx - 9, 1, gx - 1, 3, visible((20, 80, 160)))  # obudowa
        f.rect(gx - 14, 2, gx - 9, 2, visible((40, 40, 40)))


@reg("swieca")
class Candles(Clock):
    """Świece: kilka świec różnej wysokości, żywe płomienie drżą i chwieją się jak od przeciągu, ciepła poświata;
    wosk powoli spływa."""

    def draw(self, f, now, t, dt):
        cs = [(W * k / 7 + W / 14, 3 + int(hash1(k * 3) * 4), hash1(k * 7)) for k in range(7)]
        for x in range(W):  # ciepła poświata całości
            for y in range(H):
                g = sum(math.exp(-((x - cx) / 9) ** 2 - ((y - (11 - h - 3)) / 5) ** 2) for cx, h, _ in cs)
                f.set(x, y, mul((50, 22, 4), min(1, g) * (0.85 + 0.15 * noise1(t * 4))))
        draft = noise1(t * 0.7) - 0.5
        for k, (cx, h, ph) in enumerate(cs):
            top = 11 - h
            f.rect(cx - 1, top, cx + 1, 11, visible((200, 190, 170)))
            f.set(cx - 1, top + 1 + int(ph * h * 0.6), visible((235, 225, 210)))  # zaciek wosku
            f.set(cx, top - 1, visible((40, 30, 20)))  # knot
            sway = (draft + (noise1(t * 3 + k * 5) - 0.5) * 0.6) * 1.6
            fl = 3.2 + noise1(t * 6 + k) * 1.2
            for j in range(int(fl) + 1):
                p = j / fl
                x = cx + sway * p * p
                c = lerp((255, 240, 160), (255, 90, 0), p)
                f.set(x, top - 1 - j, mul(c, 1 - p * 0.5))
                if j < fl * 0.6:
                    f.add(x - 1, top - 1 - j, mul((120, 40, 0), 0.6))
                    f.add(x + 1, top - 1 - j, mul((120, 40, 0), 0.6))
            f.set(cx, top - 1, (90, 140, 255))  # niebieska nasada płomienia


@reg("lampa")
class LavaLamp(Clock):
    """Lampa lava: w szklanych lampach wielkie krople wosku powoli wznoszą się, łączą, rozciągają i opadają."""

    def __init__(self):
        self.lamps = [[{"x": random.uniform(-3, 3), "y": random.uniform(0, 11), "ph": random.random() * 9,
                        "r": random.uniform(1.6, 2.6)} for _ in range(5)] for _ in range(4)]

    def draw(self, f, now, t, dt):
        cols = [((255, 40, 0), (60, 0, 40)), ((255, 0, 160), (20, 0, 60)), ((0, 255, 120), (0, 20, 50)),
                ((255, 200, 0), (60, 10, 0))]
        for li, blobs in enumerate(self.lamps):
            cx = W * (li + 0.5) / 4
            wax, liquid = cols[li]
            for b in blobs:  # ciepło od dołu: wznoszą się, stygną u góry i opadają
                b["y"] = 5.5 + 6.5 * math.sin(t * 0.25 + b["ph"])
                b["x"] = math.sin(t * 0.3 + b["ph"] * 2) * 3
            for y in range(H):
                half = 4 + 3.5 * (1 - abs(y - 6) / 7)  # kształt lampy: szersza w środku
                for x in range(int(cx - half), int(cx + half) + 1):
                    dx = x + 0.5 - cx
                    if abs(dx) > half:
                        continue
                    field = sum(b["r"] ** 2 / ((dx - b["x"]) ** 2 + ((y + 0.5 - b["y"]) * 0.8) ** 2 + 0.3) for b in blobs)
                    field += 1.4 if y >= 11 else 0  # kałuża wosku na dnie
                    k = clamp((field - 1.0) * 1.5)
                    f.set(x, y, lerp(visible(liquid), mul(wax, 0.6 + 0.4 * clamp(field / 3)), k))
            f.rect(cx - 3, 0, cx + 3, 0, visible((80, 80, 90)))


# ================================================================ fizyka (bez zegara)
@reg("wahadla")
class PendulumWave(Clock):
    """Fala wahadeł: rząd kulek, każda waha się odrobinę wolniej od sąsiadki – powstają węże, fale i chaos, a co
    minutę wszystkie znów zgrywają się w jedną linię. Widok z góry, z tęczowymi smugami."""
    N, CYCLE = 40, 60.0  # w CYCLE sekund wahadło i robi 30 + i wahnięć

    def __init__(self):
        self.buf = Persist()

    def draw(self, f, now, t, dt):
        self.buf.fade(math.exp(-dt * 9))
        step = W / self.N
        for i in range(self.N):
            w = 2 * math.pi * (30 + i) / self.CYCLE
            y = 5.5 + 5 * math.cos(w * t)
            x = step * (i + 0.5)
            c = hsv(i / self.N, 0.85, 1)
            self.buf.add(x, y + 0.5, mul(c, 0.5))
            f.set(x, y + 0.5, lerp(c, (255, 255, 255), 0.3))
        self.buf.blit(f)


@reg("newton")
class NewtonsCradle(Clock):
    """Kołyska Newtona: trzy kołyski z błyszczącymi kulkami na niciach – odchylona kulka uderza w rząd, a z drugiej
    strony odskakuje tyle samo; w każdej kołysce inna liczba kulek w ruchu."""

    def draw(self, f, now, t, dt):
        f.rect(0, 0, W - 1, 0, visible((60, 60, 70)))
        for k, (cx, lift, col) in enumerate(((W / 6, 1, (200, 200, 210)), (W / 2, 2, (230, 180, 60)),
                                             (W * 5 / 6, 3, (120, 200, 255)))):
            n, r, L = 5, 2.0, 7.5
            T = 1.6
            ph = ((t + k * 0.37) % T) / T
            amp = 0.75
            a = amp * math.sin(2 * math.pi * ph)  # >0: lewe uniesione (pierwsza połowa), <0: prawe
            for i in range(n):
                px = cx + (i - (n - 1) / 2) * (2 * r)
                th = 0.0
                if a > 0 and i < lift:
                    th = -a
                elif a < 0 and i >= n - lift:
                    th = -a
                bx, by = px + math.sin(th) * L, 0.5 + math.cos(th) * L
                f.line(px, 0, bx, by - r + 0.5, visible((70, 70, 80)))
                for y in range(int(by - r - 1), int(by + r + 2)):
                    for x in range(int(bx - r - 1), int(bx + r + 2)):
                        d = math.hypot(x + 0.5 - bx, y + 0.5 - by)
                        if d < r + 0.3:
                            sh = clamp(1.1 - math.hypot(x + 0.5 - (bx - 0.7), y + 0.5 - (by - 0.7)) / (r + 0.5))
                            f.set(x, y, mul(col, (0.25 + 0.75 * sh) * clamp(r + 0.3 - d + 0.5)))


@reg("kostki")
class DominoRun(Clock):
    """Domino: długi rząd kolorowych kostek przewraca się jedna po drugiej przez cały panel; po ostatniej kostki
    same wstają (cofnięcie filmu) i od nowa."""
    N, GAP, HGT = 38, 3.1, 7.0

    def draw(self, f, now, t, dt):
        spd = 9.0  # kostek/s
        run = self.N / spd
        cyc = (t % (run + 1.5 + run * 0.5 + 1)) - 1
        rewind = cyc > run + 1.5
        for x in range(W):
            f.set(x, 11, visible((40, 30, 20)))
        for i in range(self.N):
            x0 = 2 + i * self.GAP
            if rewind:
                p = 1 - (cyc - run - 1.5) / (run * 0.5)
                fall = clamp((p * self.N - i) * 1.0)
            else:
                fall = clamp((cyc * spd - i) * 1.4)
            # kąt: do momentu oparcia o następną (asin(GAP/HGT)), ostatnia leży płasko
            lim = math.pi / 2 if i == self.N - 1 else math.asin(min(1, (self.GAP - 0.5) / self.HGT))
            a = fall * lim
            c = hsv(i / self.N, 0.8, 1)
            bx, by = x0 + 1, 10.5
            tx, ty = bx + math.sin(a) * self.HGT, by - math.cos(a) * self.HGT
            f.line(bx - 1, by, tx - 1, ty, mul(c, 0.55))
            f.line(bx, by, tx, ty, c)
            f.set(tx, ty, (255, 255, 255) if fall > 0 and fall < 1 else c)


@reg("kulodrom")
class MarbleRun(Clock):
    """Tor kulkowy: kolorowe kulki toczą się po falistej rynnie, spadają na dół, wracają po podłodze, a winda
    zabiera je z powrotem na górę."""

    def __init__(self):
        self.m = [{"s": -i * 26.0, "c": hsv(i / 8, 0.85, 1)} for i in range(8)]

    @staticmethod
    def top(x):
        return 4.5 + math.sin(x * 0.13) * 1.3

    def pos(self, s):
        """Położenie po drodze s (px): rynna w prawo, spadek, podłoga w lewo, winda w górę."""
        L = W - 8
        if s < 0:
            return None
        if s < L:
            return 4 + s, self.top(4 + s)
        s -= L
        y0 = self.top(W - 4)
        if s < 10.5 - y0:
            return W - 3, y0 + s
        s -= 10.5 - y0
        if s < L:
            return W - 4 - s, 10.5
        s -= L
        return 1.5, max(self.top(4), 10.5 - s)  # winda

    def draw(self, f, now, t, dt):
        rail = visible((90, 75, 55))
        for x in range(4, W - 3):
            f.set(x, self.top(x) + 1, rail)
        for x in range(W):
            f.set(x, 11, rail)
        f.rect(0, 2, 0, 11, visible((50, 50, 60)))
        f.rect(3, 2, 3, 11, visible((50, 50, 60)))
        L = W - 8
        total = 2 * L + (10.5 - self.top(W - 4)) + (10.5 - self.top(4)) + 3
        for mb in self.m:
            mb["s"] += 28 * dt
            if mb["s"] > total:
                mb["s"] -= total
            p = self.pos(mb["s"])
            if p:
                x, y = p
                f.set(x, y, mb["c"])
                f.set(x + 1, y, mul(mb["c"], 0.6))
                f.set(x, y - 1, mul(mb["c"], 0.6))
                f.set(x + 1, y - 1, lerp(mb["c"], (255, 255, 255), 0.5))


@reg("pileczki")
class BouncyBalls(Clock):
    """Piłeczki: kolorowe kauczukowe kulki wpadają z góry, odbijają się od podłogi i od siebie nawzajem,
    tracą energię; co jakiś czas ktoś podrzuca je wszystkie naraz."""

    def __init__(self):
        self.b, self.kick = [], 0.0

    def draw(self, f, now, t, dt):
        if len(self.b) < 22 and random.random() < dt * 3:
            self.b.append([random.uniform(2, W - 2), -1.0, random.uniform(-15, 15), 0.0, random.uniform(1.0, 1.6),
                           hsv(random.random(), 0.85, 1)])
        if t > self.kick:
            for p in self.b:
                p[3] -= random.uniform(14, 22)
            self.kick = t + random.uniform(7, 12)
        for _ in range(2):
            h = dt / 2
            for p in self.b:
                p[3] += 50 * h
                p[0] += p[2] * h
                p[1] += p[3] * h
                if p[1] > 11 - p[4]:
                    p[1], p[3] = 11 - p[4], -abs(p[3]) * 0.82
                    p[2] *= 0.97
                if p[0] < p[4] or p[0] > W - p[4]:
                    p[2] = -p[2]
                    p[0] = clamp(p[0], p[4], W - p[4])
            for i, a in enumerate(self.b):
                for c in self.b[i + 1:]:
                    dx, dy = c[0] - a[0], c[1] - a[1]
                    d = math.hypot(dx, dy)
                    if 0 < d < a[4] + c[4]:  # sprężyste zderzenie równych mas
                        nx, ny = dx / d, dy / d
                        rel = (a[2] - c[2]) * nx + (a[3] - c[3]) * ny
                        if rel > 0:
                            a[2] -= rel * nx
                            a[3] -= rel * ny
                            c[2] += rel * nx
                            c[3] += rel * ny
                        push = (a[4] + c[4] - d) / 2
                        a[0] -= nx * push
                        a[1] -= ny * push
                        c[0] += nx * push
                        c[1] += ny * push
        for p in self.b:
            disc(f, p[0], p[1], p[4] + 0.3, p[5])
            f.set(p[0] - 0.5, p[1] - 0.6, lerp(p[5], (255, 255, 255), 0.6))


@reg("slinky")
class Slinky(Clock):
    """Slinky: tęczowa sprężynka schodzi po schodach – przelewa się łukiem stopień po stopniu, a na końcu
    wraca na górę."""
    STEP_W, STEP_H, N = 15, 0.85, 18

    def draw(self, f, now, t, dt):
        steps = int((W - 8) / self.STEP_W)
        for k in range(steps + 1):  # schody
            x0, y0 = 2 + k * self.STEP_W, 5 + k * self.STEP_H
            f.rect(x0, y0 + 0.5, x0 + self.STEP_W - 1, y0 + 0.5, visible((90, 70, 50)))
            f.rect(x0 + self.STEP_W - 1, y0 + 0.5, x0 + self.STEP_W - 1, min(11, y0 + self.STEP_H), visible((60, 45, 30)))
        T = 1.3
        k, p = int(t / T) % steps, (t / T) % 1
        ax, ay = 2 + k * self.STEP_W + 5, 5 + k * self.STEP_H
        bx, by = ax + self.STEP_W, ay + self.STEP_H
        e, s, h = p * p * (3 - 2 * p), 0.55, 0.17
        for i in range(self.N):  # zwój i przelatuje łukiem ze stosu A na stos B (górny pierwszy)
            g = clamp((e - i / (self.N - 1) * (1 - s)) / s)
            y_a, y_b = ay - (self.N - 1 - i) * h, by - i * h
            x = ax + (bx - ax) * (1 - math.cos(math.pi * g)) / 2
            y = y_a + (y_b - y_a) * g - math.sin(math.pi * g) * 2.5
            c = hsv(i / self.N, 0.9, 1)
            f.set(x - 1, y, mul(c, 0.5))
            f.set(x, y, c)
            f.set(x + 1, y, mul(c, 0.5))


# ================================================================ sceny (bez zegara)
@reg("okno")
class TrainWindow(Clock):
    """Nocą z okna pociągu: daleko powoli suną góry i księżyc, bliżej światła miasteczek, a tuż za szybą migają
    słupy i drzewa (paralaksa); co jakiś czas mija nas oświetlony pociąg z naprzeciwka."""

    def __init__(self):
        self.other = None

    def draw(self, f, now, t, dt):
        for k in range(20):
            f.set((hash1(k * 3) * W * 2 - t * 0.5) % W, hash1(k * 7) * 5, visible((90, 90, 120)))
        mx = (W * 0.8 - t * 0.4) % (W + 20) - 10
        disc(f, mx, 2.5, 1.8, (220, 210, 160))
        for x in range(W):  # góry – bardzo daleko
            h = 3 + noise1((x + t * 2) * 0.04) * 4
            for y in range(int(H - h), H):
                f.set(x, y, visible((18, 18, 35)))
        for k in range(60):  # światła miasteczek – średnio daleko
            wx = k * 23.0
            x = (wx - t * 12) % (60 * 23.0) - 10
            if 0 <= x < W and hash1(k) > 0.35:
                for j in range(int(1 + hash1(k * 5) * 4)):
                    c = (255, 200, 90) if hash1(k * 9 + j) > 0.3 else (180, 220, 255)
                    f.set(x + j * 2, 8 + hash1(k + j) * 2, mul(c, 0.6 + 0.4 * noise1(t * 2 + k + j)))
        for k in range(40):  # drzewa i słupy – tuż za szybą, szybko
            x = (k * 31 - t * 70) % (40 * 31) - 10
            if not -3 <= x < W + 3:
                continue
            if hash1(k * 3) > 0.5:
                f.rect(x, 0, x + 1, 11, visible((25, 22, 20)))  # słup
                f.rect(x - 3, 1, x + 4, 1, visible((25, 22, 20)))
            else:
                for y in range(3, H):
                    hw = (y - 2) * 0.7
                    f.rect(x - hw, y, x + hw, y, visible((5, 20, 8)))
        if self.other is None and random.random() < dt * 0.06:
            self.other = t
        if self.other is not None:  # pociąg z naprzeciwka: rząd okien przelatuje w 2 s
            a = t - self.other
            if a > 2.2:
                self.other = None
            else:
                for x in range(W):
                    f.set(x, 4, visible((40, 40, 45)))
                    f.set(x, 9, visible((40, 40, 45)))
                    lit = ((x + a * 400) % 9) < 6
                    for y in range(5, 9):
                        f.set(x, y, (200, 180, 120) if lit and y < 8 else visible((50, 50, 55)))
        for y in range(H):  # rama okna i odbicie
            f.set(0, y, visible((50, 50, 55)))
            f.set(W - 1, y, visible((50, 50, 55)))


@reg("szyba")
class RainWindow(Clock):
    """Deszcz na szybie: za szybą rozmyte kolorowe światła miasta, po szybie spływają krople – stoją, nabierają
    wody, ruszają zygzakiem, zostawiają ślad i łykają mniejsze krople po drodze."""

    def __init__(self):
        self.still = [[random.uniform(0, W), random.uniform(0, H), random.uniform(0.3, 0.8)] for _ in range(70)]
        self.runs, self.trail = [], Persist()

    def draw(self, f, now, t, dt):
        for k in range(14):  # bokeh: duże miękkie plamy
            bx = (hash1(k * 3) * W + math.sin(t * 0.1 + k) * 3)
            by = hash1(k * 7) * H
            c = hsv(hash1(k * 11) * 0.2 + (0.55 if k % 3 == 0 else 0.05), 0.7, 1)
            r = 3 + hash1(k * 13) * 4
            pulse = 0.18 + 0.08 * noise1(t * 0.5 + k)
            for y in range(H):
                for x in range(int(bx - r), int(bx + r) + 1):
                    d = math.hypot(x + 0.5 - bx, (y + 0.5 - by) * 1.2)
                    if d < r:
                        f.add(x, y, mul(c, pulse * (1 - (d / r) ** 4)))
        if random.random() < dt * 1.2:
            self.runs.append([random.uniform(0, W), -1.0, random.uniform(0.6, 1.0), 0.0])
        self.trail.fade(math.exp(-dt * 0.8))
        for d in self.still:
            f.add(d[0], d[1], mul((140, 160, 190), d[2] * 0.5))
        keep = []
        for r in self.runs:
            r[3] += dt
            if r[3] > 0.3:  # rusza szarpnięciami i trochę w bok
                v = 10 + 10 * noise1(t * 3 + r[0])
                r[1] += v * dt
                r[0] += (noise1(t * 2 + r[0] * 3) - 0.5) * 6 * dt
            for d in list(self.still):  # łyka mniejsze krople
                if abs(d[0] - r[0]) < 1 and abs(d[1] - r[1]) < 1:
                    self.still.remove(d)
                    self.still.append([random.uniform(0, W), random.uniform(0, H), random.uniform(0.3, 0.8)])
                    r[2] = min(1.3, r[2] + 0.1)
            self.trail.add(r[0], r[1], (25, 30, 40))
            if r[1] < H + 1:
                f.add(r[0], r[1], mul((200, 220, 255), r[2]))
                f.add(r[0], r[1] - 1, mul((120, 140, 170), r[2] * 0.6))
                keep.append(r)
        self.runs = keep
        self.trail.blit(f)


@reg("latarnia")
class Lighthouse(Clock):
    """Latarnia morska: biało-czerwona wieża na skale, snop światła obraca się nad ciemnym morzem i omiata niebo,
    fale błyszczą w jego blasku, w oddali przepływa statek."""

    def draw(self, f, now, t, dt):
        lx, ly = W * 0.18, 2.5
        a = t * 1.1  # obrót: snop widać, gdy świeci w bok, przez chwilę świeci prosto na nas
        side = math.cos(a)
        toward = math.sin(a)
        for k in range(20):
            f.set(hash1(k * 5) * W, hash1(k * 3) * 6, visible((70, 70, 100)))
        for y in range(H):
            for x in range(W):
                if y >= 8:  # morze z falami
                    w = math.sin(x * 0.4 + t * 1.5 + y) * math.sin(x * 0.13 - t * 0.7)
                    c = visible((0, 15 + 10 * w, 40 + 15 * w))
                    f.set(x, y, c)
                dx, dy = x + 0.5 - lx, y + 0.5 - ly
                if dx * side > 0:  # snop: wąski stożek w stronę, w którą świeci
                    ang = abs(math.atan2(dy, abs(dx)) - 0.04)
                    k = clamp(1.2 - ang / (0.1 + abs(dx) * 0.0015)) * clamp(1 - abs(dx) / W) * abs(side) ** 0.5
                    if k > 0:
                        f.add(x, y, mul((255, 240, 180), k * (0.8 if y < 8 else 0.45)))
        glare = clamp(1 - abs(side) * 3) * (toward > 0)  # świeci na nas – rozbłysk
        for x in range(int(lx - 5), int(lx + 6)):  # skała
            f.set(x, 11, visible((40, 35, 30)))
            f.set(x, 10, visible((40, 35, 30)) if abs(x - lx) < 4 else f.get(x, 10))
        for y in range(4, 10):  # wieża w paski
            for x in range(int(lx - 1), int(lx + 2)):
                f.set(x, y, visible((200, 30, 30)) if (y // 2) % 2 else visible((200, 200, 200)))
        f.rect(lx - 1, 2, lx + 1, 3, (255, 240, 180))
        f.rect(lx - 1, 1, lx + 1, 1, visible((60, 60, 60)))
        if glare:
            disc(f, lx + 0.5, 2.5, 1 + 3 * glare, mul((255, 250, 220), glare), add=True)
        sx = (W + 20) - (t * 3) % (W + 40)  # statek w oddali
        f.rect(sx, 7, sx + 6, 7, visible((60, 60, 70)))
        f.rect(sx + 2, 6, sx + 3, 6, visible((60, 60, 70)))
        f.set(sx + 5, 6, (255, 200, 80) if int(t) % 2 else visible((60, 60, 70)))


@reg("wulkan")
class Volcano(Clock):
    """Wulkan: stożek na tle nocnego nieba, z krateru tryska lawa, rozżarzone bomby lecą łukiem, strumienie
    lawy spływają po zboczach, w górę bucha dym; co chwilę silniejsza erupcja."""

    def __init__(self):
        self.p, self.boom = [], 0.0

    def draw(self, f, now, t, dt):
        cx = W / 2
        strong = (t % 14) < 2.5
        for y in range(H):  # łuna
            for x in range(W):
                g = math.exp(-((x - cx) / 30) ** 2 - (y / 8) ** 2)
                f.set(x, y, mul((60, 12, 0), g * (1.5 if strong else 1)))
        for x in range(W):  # stożek
            top = 3 + abs(x + 0.5 - cx) * 0.22
            if abs(x + 0.5 - cx) < 3:
                top = 3.5
            for y in range(int(top), H):
                f.set(x, y, visible((70, 40, 30)) if y == int(top) else visible((40, 26, 20)))
        for k in range(5):  # strumienie lawy
            side = 1 if k % 2 else -1
            for j in range(40):
                x = cx + side * (2 + j * 1.0) + math.sin(j * 0.5 + k) * 1.2
                y = 3.5 + j * 0.22 * (1 + k * 0.08)
                if y > 11 or j > (t * 6 + k * 13) % 50:
                    break
                flow = 0.6 + 0.4 * math.sin(j * 0.8 - t * 4 + k)
                f.set(x, y, mul((255, 90, 0), flow))
        rate = 120 if strong else 25
        for _ in range(int(rate * dt + random.random())):
            self.p.append([cx + random.uniform(-1.5, 1.5), 3.0, random.uniform(-14, 14), -random.uniform(8, 20 if strong else 12),
                           random.uniform(1, 2.5), random.random() < 0.3])
        keep = []
        for q in self.p:
            q[4] -= dt
            if q[5]:  # dym: wznosi się i rozpływa
                q[0] += q[2] * 0.2 * dt
                q[1] -= 3 * dt
                if q[4] > 0 and q[1] > -2:
                    f.add(q[0], q[1], mul((50, 45, 45), min(1, q[4])))
                    keep.append(q)
                continue
            q[3] += 22 * dt
            q[0] += q[2] * dt
            q[1] += q[3] * dt
            if q[4] > 0 and q[1] < 11:
                f.set(q[0], q[1], lerp((255, 60, 0), (255, 230, 120), clamp(q[4] - 1)))
                keep.append(q)
        self.p = keep[-400:]
        f.rect(cx - 2, 3, cx + 2, 3, (255, 160, 30))


@reg("start")
class Launch(Clock):
    """Start rakiety z bliska: rakieta na wyrzutni, odliczanie, zapłon, kłęby dymu rozlewają się po ziemi,
    rakieta wznosi się z ognistym ogonem i znika u góry; potem następna."""
    T = 22.0

    def __init__(self):
        self.smoke = []

    def draw(self, f, now, t, dt):
        p = t % self.T
        cx = W / 2
        lift = max(0.0, p - 6) ** 2 * 1.4  # od 6 s w górę z przyspieszeniem
        shake = (random.uniform(-0.4, 0.4) if 5 < p < 9 else 0)
        for y in range(H):
            for x in range(W):
                f.set(x, y, visible((5, 8, 25)))
        f.rect(cx + 8, 1, cx + 9, 11, visible((70, 60, 50)))  # wieża
        for y in range(1, 11, 2):
            f.set(cx + 7, y, visible((70, 60, 50)))
        ry = 1 - lift
        x0 = cx - 2 + shake
        if ry > -14:
            f.rect(x0, ry + 2, x0 + 3, ry + 8, visible((200, 200, 210)))  # kadłub
            f.rect(x0 + 1, ry, x0 + 2, ry + 1, visible((200, 40, 40)))  # czubek
            f.set(x0 - 1, ry + 7, visible((200, 40, 40)))
            f.set(x0 + 4, ry + 7, visible((200, 40, 40)))
            f.set(x0 + 1, ry + 4, (80, 160, 255))
        if p < 5:  # odliczanie
            n = 5 - int(p)
            f.text(str(n), cx - 30, 0, (255, 220, 0), BIG)
        fire = 4.5 < p < 16
        if fire:
            for k in range(int(10 * (1 + (p > 6)))):
                fx = x0 + 1.5 + random.uniform(-1.2, 1.2)
                fy = ry + 9 + random.uniform(0, 3 + min(6, p - 4.5))
                f.add(fx, fy, lerp((255, 240, 150), (255, 60, 0), random.random()))
            if ry + 9 < 12:  # dym rozlewa się po ziemi
                for _ in range(3):
                    self.smoke.append([cx + random.uniform(-2, 2), 10.5, random.choice((-1, 1)) * random.uniform(6, 25),
                                       -random.uniform(0, 3), random.uniform(2, 4)])
        keep = []
        for s in self.smoke:
            s[0] += s[2] * dt
            s[1] += s[3] * dt
            s[2] *= math.exp(-dt * 0.7)
            s[4] -= dt
            if s[4] > 0:
                k = min(1, s[4] / 2)
                disc(f, s[0], s[1], 1.6, mul((150, 140, 130), k * 0.7))
                keep.append(s)
        self.smoke = keep[-300:]
        for x in range(W):
            f.set(x, 11, visible((40, 40, 40)))


@reg("saturn")
class Saturn(Clock):
    """Przelot obok planety z pierścieniami: wielki pasiasty glob z cieniem przesuwa się powoli przez panel,
    pierścienie z przerwą przecinają go ukośnie, w tle gwiazdy w paralaksie."""

    def draw(self, f, now, t, dt):
        for k in range(50):  # gwiazdy dwiema warstwami
            sp = 1.5 if k % 2 else 4
            x = (hash1(k * 7) * W * 2 - t * sp) % (W + 4) - 2
            f.set(x, hash1(k * 3) * H, visible((120, 120, 150) if k % 2 else (200, 200, 230)))
        cx = W + 30 - (t * 3 + W / 2 + 10) % (W + 60)  # zaczyna blisko środka
        cy, R = 6.0, 9.0
        tilt = -0.18
        for y in range(H):
            for x in range(int(cx - 26), int(cx + 27)):
                dx, dy = x + 0.5 - cx, y + 0.5 - cy
                ry = dy - dx * tilt
                rr = math.hypot(dx, ry * 6)  # pierścienie: płaska elipsa
                ring = 12 < rr < 22 and not 16.5 < rr < 17.5
                front = ry > 0
                d = math.hypot(dx, dy)
                if d < R and not (ring and front):
                    lat = dy / R
                    band = 0.75 + 0.25 * math.sin(lat * 14 + math.sin(dx * 0.2 + t * 0.2))
                    light = clamp(0.25 + 0.75 * (dx / R + 0.6))  # słońce z prawej
                    c = lerp((200, 160, 100), (240, 210, 150), band)
                    if ring and not front and abs(ry) < 1.2:  # cień pierścieni na globie
                        light *= 0.5
                    f.set(x, y, mul(c, light * clamp(R - d + 0.5)))
                elif ring:
                    shade = 0.45 if (not front and d < R + 1) else 1
                    k = 0.7 + 0.3 * math.sin(rr * 0.7)
                    f.set(x, y, mul((210, 190, 150), k * shade * 0.8))


# ================================================================ impreza (bez zegara)
@reg("disco")
class Disco(Clock):
    """Disco: obracająca się kula lustrzana z migoczącymi lusterkami, kolorowe plamki światła wędrują po
    panelu, reflektory zmieniają kolor do rytmu."""

    def draw(self, f, now, t, dt):
        beat = (t * 2.1) % 1
        cx, R = W / 2, 4.6
        for k in range(36):  # plamki światła krążą po „ścianach”
            a = k * 2.399 + t * 0.6
            x = (cx + math.cos(a) * (14 + (k * 7) % 46) * 1.0) % W
            y = 6 + math.sin(a * 1.3 + k) * 5
            c = hsv(k / 9 + t * 0.05, 0.6, 1)
            f.add(x, y, mul(c, 0.5 + 0.5 * (hash1(k + int(t * 8)) > 0.3)))
        for side in (-1, 1):  # reflektory z dołu
            sx = cx + side * 45
            c = hsv(int(t * 2.1) * 0.17 + (side > 0) * 0.5, 1, 1)
            ang = math.sin(t * 1.3 * side) * 0.7
            for j in range(12):
                x = sx + math.sin(ang) * j * 2.5
                f.add(x, 11 - j, mul(c, (1 - j / 12) * (0.9 - 0.5 * beat)))
                f.add(x + 1, 11 - j, mul(c, (1 - j / 12) * 0.3))
        f.line(cx, 0, cx, 1, visible((80, 80, 80)))
        for y in range(H):  # kula: lusterka w siatce, obracają się
            for x in range(int(cx - R - 1), int(cx + R + 2)):
                dx, dy = x + 0.5 - cx, y + 0.5 - 6.5
                if math.hypot(dx, dy) < R:
                    lon = math.asin(clamp(dx / math.sqrt(max(0.01, R * R - dy * dy)), -1, 1)) + t * 1.5
                    cell = int(lon * 3) * 7 + int(dy + 10) * 13
                    sparkle = hash1(cell + int(t * 6)) ** 6
                    base = 60 + 60 * hash1(cell)
                    c = lerp((base, base, base + 10), (255, 255, 255), sparkle)
                    f.set(x, y, visible(c))


@reg("vumetr")
class VuMeter(Clock):
    """VU-metry retro: dwa podświetlone wskaźniki wychyłowe ze skalą i czerwonym polem, wskazówki tańczą do
    muzyki (symulowanej), obok słupkowe wskaźniki LED."""

    def __init__(self):
        self.n = [0.0, 0.0]
        self.peak = [0.0, 0.0]

    @staticmethod
    def level(t, ch):
        beat = max(0.0, math.sin(t * 2 * math.pi * 2.0)) ** 8  # stopa
        return clamp(0.35 + 0.35 * noise1(t * 3 + ch * 7) + 0.4 * beat + 0.15 * (noise1(t * 11 + ch) - 0.5))

    def draw(self, f, now, t, dt):
        for ch in (0, 1):
            lv = self.level(t, ch)
            self.n[ch] += (lv - self.n[ch]) * (1 - math.exp(-dt * (12 if lv > self.n[ch] else 4)))  # balistyka
            cx = W * (0.22 + 0.56 * ch)
            for y in range(H):  # podświetlona tarcza
                for x in range(int(cx - 20), int(cx + 21)):
                    f.set(x, y, visible((120, 90, 30)))
            for k in range(21):  # skala łukiem, czerwone pole na końcu
                a = -0.95 + 1.9 * k / 20
                px, py = cx + math.sin(a) * 17, 13.5 - math.cos(a) * 12
                c = (255, 40, 20) if k > 15 else (20, 15, 5)
                f.set(px, py, c)
                if k % 5 == 0:
                    f.set(px, py + 1, c)
            a = -0.95 + 1.9 * self.n[ch]
            for j in range(30):  # wskazówka
                r = j / 29 * 11.5
                f.set(cx + math.sin(a) * r * 1.4, 13.5 - math.cos(a) * r, (0, 0, 0))
            f.rect(cx - 2, 11, cx + 2, 11, visible((30, 30, 30)))
            bx = int(W / 2 - 4 + ch * 6)  # słupki LED
            if self.n[ch] > self.peak[ch]:
                self.peak[ch] = self.n[ch]
            self.peak[ch] -= dt * 0.3
            for j in range(12):
                on = j / 12 < self.n[ch]
                c = (0, 255, 60) if j < 7 else (255, 200, 0) if j < 10 else (255, 30, 0)
                if on or abs(j / 12 - self.peak[ch]) < 0.05:
                    f.rect(bx, 11 - j, bx + 1, 11 - j, c)
                else:
                    f.rect(bx, 11 - j, bx + 1, 11 - j, visible(mul(c, 0.08)))


@reg("sylwester")
class NewYear(Clock):
    """Sylwester: wielkie odliczanie 10… 3, 2, 1, potem fajerwerki i napis z nowym rokiem; w kółko, jak pokaz.
    W ostatniej minucie roku odlicza naprawdę do północy."""

    def __init__(self):
        self.pt, self.buf = [], Persist()

    def draw(self, f, now, t, dt):
        real = now.month == 12 and now.day == 31 and now.hour == 23 and now.minute == 59
        p = (now.second + now.microsecond / 1e6 - 49) if real else t % 24
        year = now.year if (now.month, now.day) == (1, 1) else now.year + 1  # nadchodzący (1 stycznia – już ten)
        self.buf.fade(math.exp(-dt * 5))
        if p < 10:  # odliczanie: cyfra rośnie i gaśnie
            n = 10 - int(p)
            k = p % 1
            s = str(n)
            c = hsv(n / 10, 0.8, 1)
            x = (W - text_w(s, BIG)) // 2
            f.text(s, x, 1, mul(c, 1 - k * 0.7))
            for j in range(10 - n + 1):  # kropki postępu
                f.set(W / 2 - 30 + j * 6, 6, (80, 80, 80))
        else:
            if random.random() < dt * 4:
                x, y = random.uniform(10, W - 10), random.uniform(2, 7)
                hue = random.random()
                for _ in range(40):
                    a, sp = random.uniform(0, 2 * math.pi), random.uniform(4, 15)
                    self.pt.append([x, y, math.cos(a) * sp, math.sin(a) * sp * 0.6, random.uniform(0.8, 1.6),
                                    hsv(hue + random.uniform(-0.05, 0.05), 0.8, 1)])
            if p < 15:
                txt = str(year)
                f.text(txt, (W - text_w(txt, BIG)) // 2, 1, hsv(t * 0.3, 0.6, 1))
            else:
                scroll_segs(f, [("HAPPY NEW YEAR   ", (255, 220, 120)), ("SZCZĘŚLIWEGO NOWEGO ROKU", (120, 220, 255))],
                            t, 30, 0)
        keep = []
        for q in self.pt:
            q[3] += 8 * dt
            q[0] += q[2] * dt
            q[1] += q[3] * dt
            q[4] -= dt
            if q[4] > 0:
                self.buf.add(q[0], q[1], mul(q[5], min(1, q[4])))
                keep.append(q)
        self.pt = keep
        self.buf.blit(f)


@reg("bsod")
class Bsod(Clock):
    """Żart dla widzów: panel „ładuje się” z kręcącym się kółkiem i paskiem postępu, który zwalnia przy 99%,
    potem niebieski ekran :( „your panel ran into a problem”, aktualizacja 0% … i od nowa."""

    def draw(self, f, now, t, dt):
        p = t % 30
        if p < 12:  # ładowanie: pasek postępu, przy końcu zwalnia
            prog = 99 * (1 - math.exp(-p / 3)) if p < 10 else 99
            for k in range(8):  # kółko z kropek
                a = k / 8 * 2 * math.pi + t * 5
                c = mul((200, 200, 255), (k / 8) ** 1.5)
                f.set(8 + math.cos(a) * 3.2, 5.5 + math.sin(a) * 3.2, c)
            f.text("LOADING", 16, 0, (200, 200, 220), SMALL)
            pct = f"{int(prog)}%"
            end = W - text_w(pct, SMALL) - 4
            f.rect(16, 8, end, 9, visible((40, 40, 50)))
            f.rect(16, 8, 16 + (end - 16) * prog / 100, 9, (0, 160, 255))
            f.text(pct, end + 2, 6, (200, 200, 220), SMALL)
            return
        blue = (0, 60, 170)
        f.fill(blue)
        if p < 22:  # niebieski ekran
            f.text(":(", 4, 0, (255, 255, 255), TXT)
            scroll_segs(f, [("YOUR PANEL RAN INTO A PROBLEM AND NEEDS TO RESTART. WE'RE JUST COLLECTING SOME LEDS",
                             (255, 255, 255))], t, 26, 0, 22, gap=40)
            f.rect(22, 11, 22 + (p - 12) / 10 * (W - 23), 11, (255, 255, 255))
            return
        q = (p - 22) / 8  # „aktualizacja”
        for k in range(5):
            a = k * 0.5 - t * 4
            f.set(10 + math.cos(a) * 3, 5.5 + math.sin(a) * 3, (255, 255, 255))
        f.text(f"UPDATING {int(q * q * 37)}%", 20, 3, (255, 255, 255), SMALL)


# ================================================================ oczy (bez zegara): kocie, ludzkie, bajkowe, sowa…
EYES = {"col": None}  # kolor oczu z ustawień (tęczówka, świecenie); None = naturalny dla każdego efektu
EYE_PRESETS = [None, (255, 0, 0), (255, 90, 0), (255, 170, 0), (255, 240, 0), (120, 255, 0), (0, 220, 60),
               (0, 220, 200), (0, 150, 255), (40, 60, 255), (150, 40, 255), (255, 40, 160), (255, 255, 255)]


def eye_hex(c):
    return "#%02x%02x%02x" % tuple(int(v) for v in c) if c else ""


def eye_rgb(h):
    """"#rrggbb" -> (r, g, b); "" albo zły -> None (naturalny)."""
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) if re.fullmatch(r"#[0-9a-fA-F]{6}", h or "") else None


def sd_ellipse(dx, dy, a, b):
    """Przybliżona odległość ze znakiem od brzegu elipsy (ujemna w środku), w pikselach."""
    return (math.hypot(dx / a, dy / b) - 1) * min(a, b)


def sd_almond(dx, dy, a, b):
    """Migdał (kształt oka): część wspólna dwóch kół – półszerokość a, półwysokość b."""
    r = (a * a + b * b) / (2 * b)
    return max(math.hypot(dx, dy - (r - b)), math.hypot(dx, dy + (r - b))) - r


def sd_rbox(dx, dy, hw, hh, r):
    """Prostokąt z zaokrąglonymi rogami."""
    r = min(r, hw, hh)
    qx, qy = abs(dx) - hw + r, abs(dy) - hh + r
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r


def cover(sd):
    """Ile piksela zakrywa kształt (miękki brzeg zamiast schodków)."""
    return clamp(0.5 - sd)


class Eyes(Clock):
    """Wspólne dla oczu: rozglądanie się (szybkie skoki wzroku), mruganie, kolor z ustawień."""
    COL = (255, 255, 255)
    CY = 6.0  # środek oka (środki pikseli: 0,5–11,5)

    def __init__(self):
        self.g, self.aim, self.look_at, self.blink_at, self.b0 = [0.0, 0.0], (0.0, 0.0), None, None, -9.0

    def col(self):
        return EYES["col"] or self.COL

    def update(self, t, dt, wide=1.0):
        if self.look_at is None:
            self.look_at, self.blink_at = t, t + random.uniform(1, 3)
        if t >= self.look_at:  # nowy punkt: zwykle gdzieś w bok, czasem prosto
            self.aim = (0.0, 0.0) if random.random() < 0.3 else (random.uniform(-1, 1) * wide,
                                                                  random.uniform(-0.7, 0.7))
            self.look_at = t + random.uniform(0.6, 3.2)
        k = 1 - math.exp(-dt * 16)
        self.g = [self.g[0] + (self.aim[0] - self.g[0]) * k, self.g[1] + (self.aim[1] - self.g[1]) * k]
        if t >= self.blink_at:
            self.b0 = t
            self.blink_at = t + (0.35 if random.random() < 0.2 else random.uniform(2, 6))  # czasem dwa razy

    def lid(self, t, dur=0.2):
        """0 = otwarte, 1 = zamknięte."""
        p = (t - self.b0) / dur
        return math.sin(math.pi * p) if 0 <= p < 1 else 0.0

    @staticmethod
    def paint(f, x0, x1, fn):
        """fn(x, y) -> kolor albo None dla środków pikseli w kolumnach x0..x1."""
        for x in range(max(0, int(x0)), min(W, int(x1) + 1)):
            for y in range(H):
                c = fn(x + 0.5, y + 0.5)
                if c is not None:
                    f.set(x, y, c)


@reg("kot")
class CatEyes(Eyes):
    """Kocie oczy: bursztynowe tęczówki z pionową źrenicą, która rozszerza się i zwęża; mruga, czasem
    powoli przymyka oczy po kociemu. Kolor oczu – w ustawieniach efektu."""
    COL = (255, 160, 0)

    def __init__(self):
        super().__init__()
        self.pw, self.pw_aim, self.pw_at, self.slow = 1.0, 1.0, 0.0, (-9.0, 0.0)

    def draw(self, f, now, t, dt):
        self.update(t, dt)
        if t >= self.pw_at:  # źrenica: zwykle wąska szparka, czasem szeroka (zaciekawienie)
            self.pw_aim = random.choice((1.0, 1.1, 1.6, 3.4))
            self.pw_at = t + random.uniform(2, 7)
            if random.random() < 0.15:
                self.slow = (t, random.uniform(1.2, 2.2))
        self.pw += (self.pw_aim - self.pw) * (1 - math.exp(-dt * 3))
        s0, sd_ = self.slow
        half = 0.55 * math.sin(math.pi * clamp((t - s0) / sd_)) if t - s0 < sd_ else 0  # powolne przymknięcie
        c = max(self.lid(t, 0.24), half)
        col, a, b = self.col(), 13.0, 5.6 * (1 - c)
        lash = visible(mul(col, 0.12))
        for cx in (W / 2 - 22, W / 2 + 22):
            ox, oy = cx + self.g[0] * 6, self.CY + self.g[1] * 1.2

            def px(x, y, cx=cx, ox=ox, oy=oy):
                dx, dy = x - cx, y - self.CY
                if b < 0.7:  # zamknięte – kreska powieki
                    return lash if abs(dy) < 0.5 and abs(dx) < a * 0.95 else None
                k = cover(sd_almond(dx, dy, a, b))
                if not k:
                    return None
                r = math.hypot((x - ox) / a, (y - oy) / 5.6)
                streak = 0.85 + 0.15 * noise2(math.atan2(y - oy, x - ox) * 4, r * 3)  # prążki tęczówki
                iris = mul(col, (0.35 + 0.65 * clamp(1.1 - r)) * streak)
                p = cover(sd_ellipse(x - ox, y - oy, self.pw, 5.4))
                c_ = lerp(iris, (0, 0, 0), p)
                if abs(x - (ox + self.pw + 1.2)) < 0.5 and abs(y - (oy - 2.5)) < 0.5:
                    c_ = (255, 255, 255)  # błysk
                return mul(c_, k)
            self.paint(f, cx - a - 1, cx + a + 1, px)


@reg("czlowiek")
class HumanEyes(Eyes):
    """Ludzkie oczy: białka, tęczówka z ciemniejszym brzegiem i źrenicą, powieki z rzęsami, brwi, które czasem
    unoszą się ze zdziwienia. Rozgląda się i mruga. Kolor tęczówek – w ustawieniach efektu."""
    COL = (40, 110, 255)
    CY = 6.8

    def __init__(self):
        super().__init__()
        self.brow, self.brow_aim, self.brow_at = 0.0, 0.0, 0.0

    def draw(self, f, now, t, dt):
        self.update(t, dt)
        if t >= self.brow_at:
            self.brow_aim = random.choice((0, 0, 0, 1, -0.6))  # 1 = zdziwienie, -0,6 = marszczy
            self.brow_at = t + random.uniform(1.5, 5)
        self.brow += (self.brow_aim - self.brow) * (1 - math.exp(-dt * 8))
        c = self.lid(t)
        col, a, b = self.col(), 12.0, 4.4
        white, lash, brow = visible((105, 100, 95)), visible((45, 22, 8)), visible((70, 38, 14))
        pr = 1.5 + 0.4 * math.sin(t * 0.7)  # źrenica oddycha
        for side, cx in ((-1, W / 2 - 20), (1, W / 2 + 20)):
            ox, oy = cx + self.g[0] * 6.5, self.CY + self.g[1] * 1.3

            def px(x, y, cx=cx, ox=ox, oy=oy, side=side):
                dx, dy = x - cx, y - self.CY
                u = 1 - (dx / a) ** 2
                by = 1.6 - self.brow * 1.2 + (dx * side / a) * self.brow * -0.9  # brew: łuk nad okiem
                if abs(dx) < a + 1 and abs(y - (by - u * 1.0 + 0.5)) < 0.55:
                    return brow
                lid_y = self.CY + b * (-1 + 1.75 * c) * max(u, 0)  # krawędź górnej powieki
                if abs(y - lid_y) < 0.55 and u > 0.02:
                    return lash
                k = cover(sd_almond(dx, dy, a, b))
                if not k or y < lid_y:
                    return None
                cc = mul(white, 1 - 0.55 * abs(dx / a) ** 3)
                r = math.hypot(x - ox, y - oy)
                if r < 4.2:
                    ring = 0.45 if r > 3.3 else 0.8 + 0.2 * noise2(math.atan2(y - oy, x - ox) * 5, r * 2)
                    cc = lerp(cc, mul(col, ring), cover(r - 4.0))
                    cc = lerp(cc, (0, 0, 0), cover(r - pr))
                    if math.hypot(x - (ox + 1.5), y - (oy - 1.5)) < 0.8:
                        cc = (255, 255, 255)
                return mul(cc, k)
            self.paint(f, cx - a - 2, cx + a + 2, px)


@reg("bajka")
class CartoonEyes(Eyes):
    """Bajkowe oczy jak z kreskówki: duże, z wielkimi tęczówkami i błyskami. Robią miny: radość ^^, zakochanie
    (serduszka), zdziwienie, mrugnięcie. Kolor tęczówek – w ustawieniach efektu."""
    COL = (30, 190, 255)
    MOODS = ("zwykłe", "zwykłe", "radość", "serca", "zdziwienie", "oczko")

    def __init__(self):
        super().__init__()
        self.mood, self.mood_at = "zwykłe", 0.0

    def draw(self, f, now, t, dt):
        self.update(t, dt, 0.8)
        if t >= self.mood_at:
            self.mood = random.choice(self.MOODS) if self.mood == "zwykłe" else "zwykłe"
            self.mood_at = t + (random.uniform(4, 9) if self.mood == "zwykłe" else random.uniform(1.8, 3))
        c = self.lid(t, 0.16) if self.mood != "radość" else 0
        col, a, b = self.col(), 8.0, 5.6
        white = visible((160, 160, 165))
        for side, cx in ((-1, W / 2 - 11), (1, W / 2 + 11)):
            mood = "radość" if self.mood == "oczko" and side > 0 else self.mood
            bb = b * (1 - c)
            ox, oy = cx + self.g[0] * 3, self.CY + self.g[1] * 1.0

            def px(x, y, cx=cx, ox=ox, oy=oy, mood=mood, bb=bb):
                dx, dy = x - cx, y - self.CY
                if mood == "radość":  # ^ ^ – łuk
                    return col if abs(math.hypot(dx / 1.3, dy - 3.5) - 5.0) < 0.6 and dy < 2.5 else None
                if bb < 0.8:
                    return col if abs(dy) < 0.5 and abs(dx) < a else None
                k = cover(sd_ellipse(dx, dy, a, bb))
                if not k:
                    return None
                if mood == "serca":  # serduszko zamiast tęczówki
                    hx, hy = (x - cx) / 4.6, -(y - self.CY - 0.6) / 4.6
                    heart = (hx * hx + hy * hy - 0.6) ** 3 - hx * hx * hy ** 3
                    return mul((255, 30, 110) if heart < 0 else white, k)
                small = mood == "zdziwienie"
                ia, ib = (2.6, 3.0) if small else (4.6, 5.0)
                cc = lerp(white, mul(col, 0.55 + 0.45 * clamp((oy + ib - y) / (2 * ib))),
                          cover(sd_ellipse(x - ox, y - oy, ia, ib)))
                cc = lerp(cc, (0, 0, 0), cover(sd_ellipse(x - ox, y - oy, ia * 0.55, ib * 0.6)))
                if math.hypot(x - (ox - 1.6), y - (oy - 2.0)) < 1.2 or math.hypot(x - (ox + 1.6), y - (oy + 1.8)) < 0.6:
                    cc = (255, 255, 255)
                return mul(cc, k)
            self.paint(f, cx - a - 2, cx + a + 2, px)


@reg("sowa")
class OwlEyes(Eyes):
    """Sowa: dwa wielkie okrągłe oczy obok siebie, dziób i pióra. Sowa nie rusza oczami – obraca głowę (cała twarz
    przesuwa się po panelu), mruga powoli, czasem jednym okiem. Kolor tęczówek – w ustawieniach efektu."""
    COL = (255, 150, 0)

    def __init__(self):
        super().__init__()
        self.hx, self.h_aim, self.h_at, self.wink = 0.0, 0.0, 0.0, 0

    def draw(self, f, now, t, dt):
        self.update(t, dt)
        if t >= self.h_at:
            self.h_aim = random.choice((0, 0, -1, 1)) * random.uniform(0.3, 1) * (W / 2 - 22)
            self.h_at = t + random.uniform(3, 8)
        self.hx += (self.h_aim - self.hx) * (1 - math.exp(-dt * 2.5))
        if t - self.b0 < 0.01:
            self.wink = random.choice((0, 0, 0, -1, 1))
        c = self.lid(t, 0.45)
        col, r = self.col(), 5.6
        feather, rim, beak = visible((48, 30, 14)), visible((70, 40, 12)), visible((150, 110, 40))
        mid = W / 2 + self.hx
        pr = 3.0 + 0.4 * math.sin(t * 0.5)

        def px(x, y):
            dx, dy = x - mid, y - self.CY
            if 0 <= dy - 2.6 < 3 and abs(dx) < (5.6 - (dy - 2.6)) * 0.45:  # dziób
                return beak
            for side in (-1, 1):
                ex = dx - side * 6.4
                d = math.hypot(ex, dy)
                if d < r + 0.6:
                    cc = (side == self.wink or not self.wink) and c
                    if y < self.CY - r + 2 * r * cc:  # powieka z góry
                        return feather
                    if d > r - 0.6:
                        return rim
                    k = clamp(1.05 - d / r) * 0.6 + 0.4
                    cc_ = lerp(mul(col, k), (0, 0, 0), cover(math.hypot(ex - self.g[0] * 0.6, dy - self.g[1] * 0.5) - pr))
                    if math.hypot(ex + 1.3, dy + 1.6) < 0.8:
                        cc_ = (255, 255, 255)
                    return cc_
            ring = sd_ellipse(dx, dy, 17, 6.6)
            if ring < 0 and hash1(int(x) * 31 + int(y) * 7) < 0.55:  # pióra wokół oczu
                return mul(feather, 0.6 + 0.4 * hash1(int(x) * 13 + int(y)))
            return None
        self.paint(f, mid - 18, mid + 18, px)


@reg("robot")
class RobotEyes(Eyes):
    """Oczy robota: świecące zaokrąglone prostokąty jak na ekranie. Robią miny: zadowolenie, złość, smutek,
    senność, zdziwienie, rozglądają się całymi oczami. Kolor świecenia – w ustawieniach efektu."""
    COL = (0, 170, 255)
    MOODS = ("zwykłe", "zwykłe", "radość", "złość", "smutek", "senność", "zdziwienie")

    def __init__(self):
        super().__init__()
        self.mood, self.mood_at, self.m = "zwykłe", 0.0, {}

    def draw(self, f, now, t, dt):
        self.update(t, dt)
        if t >= self.mood_at:
            self.mood = random.choice(self.MOODS) if self.mood == "zwykłe" else "zwykłe"
            self.mood_at = t + (random.uniform(3, 7) if self.mood == "zwykłe" else random.uniform(1.5, 3))
        want = {"hw": 8.0 if self.mood == "zdziwienie" else 7.0, "hh": 5.5 if self.mood != "senność" else 2.0,
                "cut": {"radość": 1, "złość": 2, "smutek": 3}.get(self.mood, 0)}
        for k, v in want.items():  # płynne przejścia między minami
            self.m[k] = v if k == "cut" else self.m.get(k, v) + (v - self.m.get(k, v)) * (1 - math.exp(-dt * 10))
        c = self.lid(t, 0.14)
        col = self.col()
        hw, hh = self.m["hw"], self.m["hh"] * (1 - c)
        sx, sy = self.g[0] * 12, self.g[1] * 1.0
        for side, cx in ((-1, W / 2 - 16 + sx), (1, W / 2 + 16 + sx)):
            cy = self.CY + sy + (5.5 - self.m["hh"]) * 0.6 * (self.mood == "senność")

            def px(x, y, cx=cx, cy=cy, side=side):
                dx, dy = x - cx, y - cy
                d = sd_rbox(dx, dy, hw, max(hh, 0.5), 3)
                cut = self.m["cut"]
                if cut == 1:  # radość: od dołu wycięty łuk
                    d = max(d, -(math.hypot(dx * 0.7, dy - 6.5) - 5.5))
                elif cut in (2, 3):  # złość: skos do środka, smutek: na zewnątrz
                    s = side if cut == 2 else -side
                    d = max(d, -(dy + 2.0 + dx * s * 0.45))
                k = cover(d)
                if not k:
                    return None
                glow = 0.75 + 0.25 * clamp(1 - math.hypot(dx / hw, dy / max(hh, 1)))
                scan = 0.85 if int(y + t * 4) % 4 == 0 else 1.0  # delikatne linie ekranu
                return mul(col, k * glow * scan)
            self.paint(f, cx - hw - 2, cx + hw + 2, px)


@reg("sauron")
class SauronEye(Eyes):
    """Oko Saurona: jedno wielkie ogniste oko z czarną pionową źrenicą, płomienie wokół, powoli wodzi wzrokiem
    po panelu. Kolor ognia – w ustawieniach efektu."""
    COL = (255, 90, 0)

    def draw(self, f, now, t, dt):
        self.update(t, dt)
        col = self.col()
        hot = lerp(col, (255, 240, 170), 0.75)
        a, b, cx = min(42.0, W / 2 - 6), 5.8, W / 2
        ox = cx + self.g[0] * a * 0.55
        pw = 1.3 + 0.5 * math.sin(t * 1.3)

        def px(x, y):
            dx, dy = x - cx, y - self.CY
            d = sd_almond(dx, dy, a, b)
            n = noise2(x * 0.18 - t * 1.2 * (1 if dx > 0 else -1), y * 0.45 + t * 0.7)
            if d > 0:  # płomienie poza okiem, gasną z odległością
                v = clamp((1 - d / 4.5) * (0.4 + 0.8 * n) - 0.25)
                return mul(col, v * 0.8) if v > 0.02 else None
            e = math.hypot((x - ox) / 9, dy / 6)  # najjaśniej przy źrenicy
            v = clamp(0.35 + 0.75 * n * (1 - clamp(-d / b) * 0.3) + 0.5 * clamp(1 - e))
            cc = lerp(mul(col, 0.35 + 0.65 * v), hot, clamp(v - 0.65) * 2.5)
            return lerp(cc, (0, 0, 0), cover(sd_ellipse(x - ox, dy, pw, 6.2)))
        self.paint(f, 0, W - 1, px)


@reg("hal")
class Hal(Eyes):
    """Oko HAL 9000: czerwony obiektyw w czarnej szybie i metalowej oprawie, powoli pulsuje. Kolor – w ustawieniach
    efektu."""
    COL = (255, 0, 0)

    def draw(self, f, now, t, dt):
        col = self.col()
        pulse = 0.8 + 0.2 * math.sin(t * 1.4)
        chrome, plate = visible((80, 80, 88)), visible((16, 16, 18))
        cx = W / 2

        def px(x, y):
            dx, dy = x - cx, y - self.CY
            r = math.hypot(dx, dy)
            if r > 5.9:
                return plate if abs(dx) < 11 else None  # płyta panelu
            if r > 5.0:
                return lerp(chrome, (190, 190, 200), clamp(-dy / 5) * 0.8)  # oprawa, jaśniej u góry
            k = clamp(1 - r / 4.6) ** 1.6 * pulse
            cc = mul(col, k)
            if r < 1.0:
                cc = lerp(cc, (255, 230, 170), (1 - r) * pulse)
            if math.hypot(dx + 2.2, dy + 2.6) < 0.7:
                cc = (70, 70, 80)  # odbicie w szybie
            return cc
        self.paint(f, cx - 12, cx + 12, px)


@reg("mrok")
class DarkEyes(Eyes):
    """Oczy w ciemności: pary świecących oczu pojawiają się w mroku, mrugają, rozglądają się i znikają – jak
    w lesie nocą. Kolor – w ustawieniach efektu (naturalny: różne zwierzęta, różne kolory)."""
    COL = (255, 220, 60)
    KINDS = ((255, 220, 60), (120, 255, 60), (255, 60, 20), (255, 150, 0), (180, 230, 255))

    def __init__(self):
        super().__init__()
        self.pairs, self.spawn = [], 0.0

    def draw(self, f, now, t, dt):
        if t >= self.spawn and len(self.pairs) < 7:
            big = random.random() < 0.35
            gap = random.uniform(7, 10) if big else random.uniform(4.5, 6.5)
            x = random.uniform(3, W - 4 - gap)
            if all(abs(x - p["x"]) > 12 for p in self.pairs):
                self.pairs.append({"x": x, "y": random.uniform(2.5, 9.5), "gap": gap, "big": big, "t0": t,
                                   "life": random.uniform(3, 9), "c": random.choice(self.KINDS),
                                   "blink": t + random.uniform(0.8, 2.5), "dx": 0.0, "aim": 0.0})
            self.spawn = t + random.uniform(0.2, 1.0)
        for p in list(self.pairs):
            age = t - p["t0"]
            if age > p["life"]:
                self.pairs.remove(p)
                continue
            fade = clamp(age / 0.6) * clamp((p["life"] - age) / 0.6)
            if t >= p["blink"]:
                p["b0"], p["blink"] = t, t + random.uniform(1.5, 4)
                p["aim"] = random.uniform(-1.5, 1.5)
            p["dx"] += (p["aim"] - p["dx"]) * (1 - math.exp(-dt * 4))
            bp = (t - p.get("b0", -9)) / 0.18
            open_ = 1 - (math.sin(math.pi * bp) if 0 <= bp < 1 else 0)
            col = mul(EYES["col"] or p["c"], fade)
            a, b = (2.4, 1.3) if p["big"] else (1.6, 0.95)
            for ex in (p["x"] + p["dx"], p["x"] + p["dx"] + p["gap"]):
                for x in range(int(ex - a - 1), int(ex + a + 2)):
                    for y in range(int(p["y"] - 2), int(p["y"] + 3)):
                        k = cover(sd_almond(x + 0.5 - ex, y + 0.5 - p["y"], a, max(b * open_, 0.05)))
                        if k:
                            f.add(x, y, mul(col, k))


CATEGORIES = [  # (nazwa, ikona do panelu WWW, efekty) – w tej kolejności lista, numery i cykl
    ("Na start", "⭐", "ludzik zegar napisz"),
    ("Tarcze i wyświetlacze", "🕰", "analogowy nixie segmenty klapki licznik wahadlo klepsydra maszyna pismo kreskowy "
                                   "neon radar obwod kalendarz postep lustro cien"),
    ("Inne zapisy czasu", "🔢", "binarny hex kolor dziesietny beaty unix rzymski morse slownie domino strefy odliczanie"),
    ("Pogoda", "🌦", "pogoda prognoza opady wiatr termometr smog slonce uv barometr"),
    ("Niebo i kosmos", "🌌", "niebo doba ksiezyc planety iss kosmonauci rakieta zorza gwiazdy hiperskok start saturn"),
    ("Wiadomości i finanse", "📰", "kursy zloto krypto bloki hackernews wiadomosci imieniny zart trzesienia"),
    ("Sceny i przyroda", "🌄", "akwarium swietliki snieg burza ocean miasto las gory pory fajerwerki synthwave pociag "
                              "ogien fala okno szyba latarnia wulkan"),
    ("Gry", "🎮", "pong waz arkanoid najezdzcy pacman dino flappy wyscig labirynt tetris"),
    ("Abstrakcje i symulacje", "🌀", "roj matrix skaner tecza glitch zycie mrowka plazma kalejdoskop wir dna oscyloskop "
                                    "equalizer ekg kule kregi piasek lawa dym"),
    ("Oczy", "👀", "kot czlowiek bajka sowa robot sauron hal mrok"),
    ("Postacie i zwierzęta", "🐾", "kotek pies platformowka ptaki nietoperze zolw slimak"),
    ("Światło", "💡", "polarna tesla szyld witraz basen iskry swieca lampa"),
    ("Fizyka", "⚙", "wahadla newton kostki kulodrom pileczki slinky"),
    ("Impreza", "🎉", "disco vumetr sylwester bsod"),
    ("Narzędzia", "🔧", "kolory"),
]
_ALL = {"licznik": Odometer, "roj": Swarm, "ogien": Fire, "matrix": Matrix, "niebo": Sky, "doba": DayRibbon,
        "skaner": Scanner, "tecza": Rainbow, "hiperskok": Warp, "zycie": Life, "akwarium": Aquarium, "pong": Pong,
        **REG}
CLOCKS = {n: _ALL[n] for _, _, names in CATEGORIES for n in names.split()}
CATEGORY = {n: c for c, _, names in CATEGORIES for n in names.split()}  # efekt -> nazwa kategorii
assert len(CLOCKS) == len(_ALL) == sum(len(x[2].split()) for x in CATEGORIES), "efekt bez kategorii albo w dwóch"


class Cycle(Clock):
    """Wszystkie zegary po kolei z płynnym przenikaniem."""

    def __init__(self, every, fade=1.5, inst=None):
        self.names = list(CLOCKS)
        self.inst = inst if inst is not None else {n: CLOCKS[n]() for n in self.names}
        self.every, self.fade = every, fade
        self.idx, self.acc, self.prev = 0, 0.0, None
        self.shuffle = False
        self.allowed = lambda name: True

    @property
    def current(self):
        return self.names[self.idx]

    def skip(self, d=1):
        ok = [i for i in range(len(self.names)) if i != self.idx and self.allowed(self.names[i])] or \
             [i for i in range(len(self.names)) if i != self.idx]
        if self.shuffle and d == 1:
            nxt = random.choice(ok)
        else:
            nxt = min(ok, key=lambda i: (i - self.idx) * d % len(self.names))
        self.prev, self.idx, self.acc = self.idx, nxt, 0.0

    def draw(self, f, now, t, dt):
        self.acc += dt
        if self.acc >= self.every:
            self.skip()
        a = Frame()
        self.inst[self.current].draw(a, now, t, dt)
        if self.prev is not None and self.acc < self.fade:
            b = Frame()
            self.inst[self.names[self.prev]].draw(b, now, t, dt)
            a = blend(b, a, self.acc / self.fade)
        else:
            self.prev = None
        f.px = a.px


# ================================================================ DDP / main
def wled_state(host, payload):
    """POST /json/state – np. {"bri": 16} albo {"lor": 0}."""
    req = urllib.request.Request(f"http://{host}/json/state", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=4).read()


def send_ddp(sock, host, data, seq):
    step = 1440
    for off in range(0, len(data), step):
        chunk = data[off:off + step]
        last = off + step >= len(data)
        hdr = bytes((0x41 if last else 0x40, seq & 0x0F, 0x01, 0x01)) + off.to_bytes(4, "big") + len(chunk).to_bytes(2, "big")
        sock.sendto(hdr + chunk, (host, 4048))


# ================================================================ silnik (wspólny dla TUI i panelu WWW)
class Engine:
    """Stan i logika sterowania: wybrany efekt, cykl, ustawienia, czas, wysyłanie klatek.
    Bez terminala – TUI (klasa Tui) i serwer WWW to tylko „fronty” do tego samego stanu.
    Inne wątki (serwer WWW) nie ruszają stanu bezpośrednio, tylko wrzucają polecenia do self.cmds;
    tick() wykonuje je na początku klatki."""

    NAMES = list(CLOCKS) + ["cykl"]
    SPEEDS = [1, 10, 60, 600, 3600]
    TEMPOS = [0.25, 0.33, 0.5, 0.67, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0]
    FPSES = [10, 12, 15, 20, 24, 25, 30, 40, 50, 60]  # panel 120x12 na jednym pinie: max ok. 20-22
    FADES = [0.0, 0.3, 0.6, 1.0, 1.5, 2.0, 3.0]
    PREVIEWS = ["włączony", "wyłączony"]
    # ustawienia jednego efektu (widać je tylko, gdy ten efekt jest na panelu); reszta jest wspólna dla wszystkich
    SETTING_FX = {"ciężkie efekty": "cykl", "cykl co": "cykl", "kolejność": "cykl", "ludzik zajęcia": "ludzik",
                  "ludzik co ile": "ludzik", "ludzik postać": "ludzik", "ludzik przestawia": "ludzik",
                  "ludzik strona": "ludzik", "kolor oczu": "kot czlowiek bajka sowa robot sauron hal mrok", "barwa": "zegar", "kolor zegara": "zegar", "czcionka": "zegar", "temperatura": "zegar", "diody: czerwony": "kolory",
                  "diody: zielony": "kolory", "diody: niebieski": "kolory"}

    def __init__(self, a, cfg):
        self.host = a.host or ""
        self.sending = bool(a.host) and cfg.get("sending", True)  # wyłączone wysyłanie przetrwa restart
        self.tempo, self.text = a.tempo, a.text_speed
        self.fps = a.fps
        self.inst = {n: CLOCKS[n]() for n in CLOCKS}
        self.cycle = Cycle(a.every, inst=self.inst)
        self.cycle.shuffle = cfg.get("shuffle", False)
        self.fade = cfg.get("fade", 0.6)
        self.cycle.fade = max(self.fade, 0.01)
        self.mode, self.cursor = a.mode, self.NAMES.index(a.mode)
        self.fade_from, self.fade_acc = None, 0.0
        self.paused, self.running = False, True
        self.preview = cfg.get("preview") if cfg.get("preview") in self.PREVIEWS else "włączony"
        if a.speed not in self.SPEEDS:
            self.SPEEDS = sorted(self.SPEEDS + [a.speed])
        self.speed_i = self.SPEEDS.index(a.speed)
        self.offset = dtm.timedelta()
        if a.start:
            hh, mm, *ss = [int(v) for v in a.start.split(":")]
            real = dtm.datetime.now().astimezone()
            self.offset = real.replace(hour=hh, minute=mm, second=ss[0] if ss else 0, microsecond=0) - real
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.seq, self.pkts, self.err = 1, 0, ""
        self.note, self.note_until = "", 0.0
        self.fps_ema, self.cost_ema = float(self.fps), 0.0
        self.resized = True       # TUI: przerysuj cały ekran
        self.t, self.frame, self.last = 0.0, None, time.monotonic()
        self.cmds = queue.Queue()  # polecenia z innych wątków: funkcje bez argumentów
        self.dirty_at = None       # kiedy coś zmieniono poleceniem (autozapis w trybie bez terminala)
        self.view, self.snap = None, None  # podgląd i stan dla panelu WWW (liczone w tick(), gdy ktoś patrzy)
        self.view_until, self.view_next, self.snap_next = 0.0, 0.0, 0.0
        self.limiter = PowerLimiter()
        self.new_width = None
        self._last_st = None
        self.lor = 0
        self.wled_st = None   # ostatni /json/state z WLED (wątek watch_wled)
        self.wled_on = None   # włącznik WLED: True/False, None = jeszcze nie wiemy – wtedy też nic nie wysyłamy
        self.power_want = None, 0.0  # (on, do kiedy) po przełączeniu z panelu – zanim WLED to przyjmie
        self.watch_wled()
        if self.sending:
            self.wled_post({"lor": 0}, "wyłączyć nadpisywania w WLED")   # WLED ma pokazywać nasz strumień
        self.peak = cfg.get("peaks", {})            # najwyższy szacowany prąd każdego efektu (mA przy danej jasności)
        self.skip_heavy = cfg.get("skip_heavy", True)
        self.cycle.allowed = lambda n: not (self.skip_heavy and self.heavy(n)) and (n != "napisz" or INBOX.is_open())
        self.settings = self.make_settings()
        self.wled_fx, self.wled_ver = [], 0   # efekty wbudowane w WLED: [{"id", "name", "tags", "meta"}], wersja listy
        self.wled_pal, self.wled_seg = [], {}  # palety WLED i bieżące parametry segmentu (sx, ix, …, pal, col)
        self.wled_saved = {k: v for k, v in (cfg.get("wled_fx_cfg") or {}).items() if isinstance(v, dict)}
        self.load_wled_fx()
        if str(cfg.get("mode", "")).startswith("wled:") and a.mode == "cykl":  # ostatnio był efekt WLED
            self.select(cfg["mode"])

    # ---------------------------------------------------------- ustawienia
    @staticmethod
    def step_in(lst, v, d):
        i = min(range(len(lst)), key=lambda k: abs(lst[k] - v))
        return lst[max(0, min(len(lst) - 1, i + d))]

    @staticmethod
    def bar(v, lo, hi, n=12):
        k = round(clamp((v - lo) / (hi - lo)) * n)
        return "█" * k + "░" * (n - k)

    def make_settings(self):
        def s_tempo(d):
            self.tempo = self.step_in(self.TEMPOS, self.tempo, d)

        def s_text(d):
            self.text = self.step_in(self.TEMPOS, self.text, d)

        def s_fps(d):
            self.fps = self.step_in(self.FPSES, self.fps, d)

        def s_every(d):
            self.cycle.every = max(10, self.cycle.every + 10 * d)

        def s_order(d):
            self.cycle.shuffle = not self.cycle.shuffle

        def s_fade(d):
            self.fade = self.step_in(self.FADES, self.fade, d)
            self.cycle.fade = max(self.fade, 0.01)

        def s_speed(d):
            self.speed_i = max(0, min(len(self.SPEEDS) - 1, self.speed_i + d))

        def s_prev(d):
            self.preview = self.PREVIEWS[(self.PREVIEWS.index(self.preview) + d) % len(self.PREVIEWS)]
            self.resized = True

        def s_send(d):
            self.toggle_send()

        def s_host(d):
            self.ask_host()

        levels = [None, 2, 3, 4, 5, 6, 8, 12, 16, 24, 32, 48, 64]
        bris = [1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 160, 192, 224, 255]
        psus = [0, 1000, 1500, 2000, 3000, 4000, 6000, 8500, 12000, 17000, 20000, 35000]

        def put_levels(v):
            PANEL["levels"], PANEL["levels_bri"], PANEL["pe"] = v, PANEL["bri"], 1 / 2.2

        def put_bri(v):
            PANEL["bri"] = v
            self.set_wled_bri(v)

        def s_levels(d):
            cur = PANEL["levels"] if panel_manual() else None
            i = levels.index(cur) if cur in levels else 0
            put_levels(levels[(i + d) % len(levels)])

        def s_wbri(d):
            put_bri(self.step_in(bris, PANEL["bri"], d))

        def s_psu(d):
            POWER["psu"] = self.step_in(psus, POWER["psu"], d)

        def s_autodim(d):
            POWER["auto"] = not POWER["auto"]

        def s_heavy(d):
            self.skip_heavy = not self.skip_heavy

        def s_mirror(d):
            PANEL["mirror"] = not PANEL["mirror"]

        def s_lacts(d):
            self.open_acts()

        def s_lfreq(d):
            LUDZIK["freq"] = max(0, min(len(LUDZIK_FREQ) - 1, LUDZIK["freq"] + d))

        def s_lhow(d):
            LUDZIK["how"] = (LUDZIK["how"] + d) % (len(LUDZIK_HOWS) + 1)

        def s_lchar(d):
            LUDZIK["char"] = (LUDZIK["char"] + d) % len(LUDZIK_CHARS)

        def s_eyecol(d):
            i = EYE_PRESETS.index(EYES["col"]) if EYES["col"] in EYE_PRESETS else 0
            EYES["col"] = EYE_PRESETS[(i + d) % len(EYE_PRESETS)]

        def s_lside(d):
            LUDZIK["side"] = (LUDZIK["side"] + d) % len(LUDZIK_SIDES)

        def s_led(ch):
            return lambda d: COLOR.update({ch: self.step_in(COLOR_STEPS, COLOR[ch], d)})

        def s_fix(d):
            COLOR["fix"] = not COLOR["fix"]

        def s_hue(d):
            CLOCK["hue"], CLOCK["col"] = (CLOCK["hue"] + d) % len(CLOCK_HUES), None

        def s_clkcol(d):
            i = EYE_PRESETS.index(CLOCK["col"]) if CLOCK["col"] in EYE_PRESETS else 0
            CLOCK["col"] = EYE_PRESETS[(i + d) % len(EYE_PRESETS)]

        def s_font(d):
            CLOCK["font"] = (CLOCK["font"] + d) % len(CLOCK_FONTS)

        def s_temp(d):
            CLOCK["temp"] = self.step_in(CLOCK_TEMPS, CLOCK["temp"], d)

        def v_temp():
            k = CLOCK["temp"]
            word = "bez zmian" if not k else "chłodniej" if k > 0 else "cieplej"
            return f"{self.bar(k, CLOCK_TEMPS[0], CLOCK_TEMPS[-1])} {f'{k:+d}' if k else '0'} K ({word})"

        def s_width(d):
            self.new_width = 60 if W != 60 else 120
            self.running = False          # main() zapisze i uruchomi skrypt ponownie z nową szerokością

        def opt(values, get, put, fmt=str, kind="list"):
            """Wybór dla panelu WWW: kind „range” = suwak, „list” = lista rozwijana; values może być funkcją."""
            return {"values": values, "get": get, "put": put, "fmt": fmt, "kind": kind}

        def flag(get, put, on="włączone", off="wyłączone"):
            return opt([True, False], get, put, lambda v: on if v else off)

        def put_width(v):
            if v != W:
                s_width(1)

        x = lambda v: f"x{v:g}"
        led = lambda ch: opt(COLOR_STEPS, lambda: COLOR[ch], lambda v: COLOR.update({ch: v}), x, "range")
        self.choices = {
            "popraw kolory": flag(lambda: COLOR["fix"], lambda v: COLOR.update(fix=v)),
            "diody: czerwony": led("r"),
            "diody: zielony": led("g"),
            "diody: niebieski": led("b"),  # ustawienia z listą wartości – w panelu WWW suwak albo lista zamiast strzałek
            "jasność WLED": opt(bris, lambda: PANEL["bri"], put_bri, lambda v: f"{v}/255", "range"),
            "zasilacz": opt(psus, lambda: POWER["psu"], lambda v: POWER.update(psu=v),
                            lambda v: f"{v / 1000:g} A" if v else "bez limitu"),
            "auto przyciemnianie": flag(lambda: POWER["auto"], lambda v: POWER.update(auto=v)),
            "ciężkie efekty": flag(lambda: self.skip_heavy, lambda v: setattr(self, "skip_heavy", v),
                                   "pomijaj w cyklu", "pokazuj"),
            "tempo anim.": opt(self.TEMPOS, lambda: self.tempo, lambda v: setattr(self, "tempo", v), x, "range"),
            "tempo tekstu": opt(self.TEMPOS, lambda: self.text, lambda v: setattr(self, "text", v), x, "range"),
            "fps": opt(self.FPSES, lambda: self.fps, lambda v: setattr(self, "fps", v), lambda v: f"{v:g}", "range"),
            "cykl co": opt(list(range(10, 601, 10)), lambda: self.cycle.every,
                           lambda v: setattr(self.cycle, "every", v), lambda v: f"{v} s", "range"),
            "kolejność": flag(lambda: self.cycle.shuffle, lambda v: setattr(self.cycle, "shuffle", v), "losowo", "po kolei"),
            "przenikanie": opt(self.FADES, lambda: self.fade, lambda v: (setattr(self, "fade", v),
                               setattr(self.cycle, "fade", max(v, 0.01))), lambda v: f"{v:g} s", "range"),
            "czas": opt(lambda: self.SPEEDS, lambda: self.speed, lambda v: setattr(self, "speed_i", self.SPEEDS.index(v)), x),
            "odbicie lustrz.": flag(lambda: PANEL["mirror"], lambda v: PANEL.update(mirror=v)),
            "ludzik co ile": opt(list(range(len(LUDZIK_FREQ))), lambda: LUDZIK["freq"], lambda v: LUDZIK.update(freq=v),
                                 lambda v: LUDZIK_FREQ[v][0]),
            "ludzik przestawia": opt(list(range(len(LUDZIK_HOWS) + 1)), lambda: LUDZIK["how"],
                                     lambda v: LUDZIK.update(how=v), lambda v: (["losowo"] + LUDZIK_HOWS)[v]),
            "ludzik postać": opt(list(range(len(LUDZIK_CHARS))), lambda: LUDZIK["char"], lambda v: LUDZIK.update(char=v),
                                 lambda v: LUDZIK_CHARS[v][0]),
            "ludzik strona": opt(list(range(len(LUDZIK_SIDES))), lambda: LUDZIK["side"], lambda v: LUDZIK.update(side=v),
                                 lambda v: LUDZIK_SIDES[v]),
            "barwa": opt(lambda: list(range(len(CLOCK_HUES))) + (["własny"] if CLOCK["col"] else []),
                         lambda: "własny" if CLOCK["col"] else CLOCK["hue"],
                         lambda v: v != "własny" and CLOCK.update(hue=v, col=None),
                         lambda v: "własny kolor" if v == "własny" else CLOCK_HUES[v][0]),
            "czcionka": opt(list(range(len(CLOCK_FONTS))), lambda: CLOCK["font"], lambda v: CLOCK.update(font=v),
                            lambda v: CLOCK_FONTS[v][0]),
            "temperatura": opt(CLOCK_TEMPS, lambda: CLOCK["temp"], lambda v: CLOCK.update(temp=v),
                               lambda v: f"{v:+d} K" if v else "0 K", "range"),
            "wysyłanie": flag(lambda: self.sending, lambda v: v != self.sending and self.toggle_send()),
            "szerokość": opt([60, 120], lambda: W, put_width, lambda v: f"{v} kolumn"),
            "poziomy": opt(levels, lambda: PANEL["levels"] if panel_manual() else None, put_levels,
                           lambda v: f"{v} na kanał (ręcznie)" if v else f"auto = {PANEL['bri']}"),
        }

        return [  # (nazwa, wartość do wyświetlenia, zmiana, podpowiedź)
            ("jasność WLED", lambda: f"{self.bar(math.log(PANEL['bri']), 0, math.log(255))} {PANEL['bri']}/255", s_wbri,
             "jedna dla wszystkich efektów (jasność w WLED)"),
            ("zasilacz", lambda: f"{POWER['psu'] / 1000:g} A" if POWER["psu"] else "bez limitu", s_psu,
             "budżet prądu (ok. 85% zasilacza)"),
            ("popraw kolory", lambda: "włączone" if COLOR["fix"] else "wyłączone", s_fix,
             "przelicza kolory pod diody: pomarańczowy wygląda na pomarańczowy, biel neutralna; wyłączone = surowe barwy"),
            ("auto przyciemnianie", lambda: "włączone" if POWER["auto"] else "wyłączone", s_autodim,
             "gdy efekt chce więcej prądu niż zasilacz; wyłączone = pełna jasność – uważaj na zasilacz"),
            ("ciężkie efekty", lambda: "pomijaj w cyklu" if self.skip_heavy else "pokazuj", s_heavy, "⚡ = nie mieszczą się w budżecie"),
            ("tempo anim.", lambda: f"{self.bar(self.tempo, 0.25, 3)} x{self.tempo:g}", s_tempo, "wszystkie ruchy"),
            ("tempo tekstu", lambda: f"{self.bar(self.text, 0.25, 3)} x{self.text:g}", s_text,
             f"{self.text_step()}"),
            ("fps", lambda: f"{self.bar(self.fps, 10, 60)} {self.fps:g}", s_fps, "klatek na sekundę"),
            ("cykl co", lambda: f"{self.cycle.every:.0f} s", s_every, "[ ]"),
            ("kolejność", lambda: "losowo" if self.cycle.shuffle else "po kolei", s_order, "l"),
            ("przenikanie", lambda: f"{self.fade:g} s", s_fade, "przy zmianie efektu"),
            ("czas", lambda: f"x{self.speed:g}", s_speed, "< > r"),
            ("podgląd", lambda: self.preview, s_prev, "v"),
            ("odbicie lustrz.", lambda: "włączone" if PANEL["mirror"] else "wyłączone", s_mirror,
             "m – obraz odbity w poziomie, żeby w kamerce wyglądał dobrze"),
            ("ludzik zajęcia", lambda: f"{len([a for a in LUDZIK_ACTS if ludzik_lvl(a)])}/{len(LUDZIK_ACTS)} włączone",
             s_lacts, "Enter = co robi z nudów i jak często"),
            ("ludzik co ile", lambda: LUDZIK_FREQ[LUDZIK["freq"]][0], s_lfreq, "przerwy między zajęciami"),
            ("ludzik postać", lambda: LUDZIK_CHARS[LUDZIK["char"]][0], s_lchar, "wygląd ludzika"),
            ("ludzik przestawia", lambda: (["losowo"] + LUDZIK_HOWS)[LUDZIK["how"]], s_lhow, "jak zmienia godzinę"),
            ("kolor oczu", lambda: eye_hex(EYES["col"]) or "naturalny", s_eyecol,
             "tęczówki / świecenie; w panelu WWW dowolny kolor, tu gotowe"),
            ("ludzik strona", lambda: LUDZIK_SIDES[LUDZIK["side"]], s_lside,
             "gdzie spaceruje: po obu stronach albo głównie po jednej (na drugą tylko na chwilę)"),
            ("barwa", lambda: "własny kolor" if CLOCK["col"] else CLOCK_HUES[CLOCK["hue"]][0], s_hue,
             "kolor zegara; pora dnia = biały w południe, ciepły wieczorem"),
            ("kolor zegara", lambda: eye_hex(CLOCK["col"]) or "z barwy", s_clkcol,
             "dowolny kolor zamiast barwy; w panelu WWW z próbnika, tu gotowe"),
            ("czcionka", lambda: CLOCK_FONTS[CLOCK["font"]][0], s_font, "krój cyfr godziny"),
            ("temperatura", v_temp, s_temp, "w lewo cieplej, w prawo chłodniej; przy „pora dnia” względem słońca"),
            ("diody: czerwony", lambda: f"x{COLOR['r']:g}", s_led("r"), "jasność kanału w podglądzie – dopasuj do panelu"),
            ("diody: zielony", lambda: f"x{COLOR['g']:g}", s_led("g"),
             "gdy pomarańczowy/żółty na panelu jest czerwieńszy niż w podglądzie – w lewo"),
            ("diody: niebieski", lambda: f"x{COLOR['b']:g}", s_led("b"), "gdy biel na panelu jest bardziej niebieska – w prawo"),
            ("wysyłanie", lambda: "włączone" if self.sending else "wyłączone", s_send, "s"),
            ("host", lambda: self.host or "(brak)", s_host, "h, Enter = zmień"),
            ("szerokość", lambda: f"{W} kolumn", s_width, "Enter = 60/120 (np. gdy działa połowa panelu), restart"),
            ("poziomy", lambda: (f"{PANEL['levels']} na kanał (ręcznie)" if panel_manual() else f"auto = {PANEL['bri']}"),
             s_levels, "ile stopni jasności widać (--kalibracja); auto = z jasności WLED"),
        ]

    def choice(self, name):
        """(wartości, indeks bieżącej) ustawienia z self.choices – bieżąca spoza listy: najbliższa liczbowo."""
        c = self.choices[name]
        vals = c["values"]() if callable(c["values"]) else c["values"]
        cur = c["get"]()
        if cur in vals and not (isinstance(cur, bool) != isinstance(vals[0], bool)):
            return vals, vals.index(cur)
        nums = [i for i, v in enumerate(vals) if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if isinstance(cur, (int, float)) and nums:
            return vals, min(nums, key=lambda i: abs(vals[i] - cur))
        return vals, 0

    def choice_json(self, name):
        if name not in self.choices:
            return {}
        vals, i = self.choice(name)
        fmt = self.choices[name]["fmt"]
        return {"kind": self.choices[name]["kind"], "labels": [fmt(v) for v in vals], "index": i}

    def pick(self, name, i):
        """Panel WWW: ustawienie na i-tą wartość z listy."""
        vals, _ = self.choice(name)
        if not 0 <= i < len(vals):
            raise ValueError(f"zła wartość ustawienia {name!r}")
        self.choices[name]["put"](vals[i])

    def setting_fx(self):
        """Efekty, których ustawienia teraz widać: wybrany, a w cyklu – cykl i to, co właśnie pokazuje."""
        return {"cykl", self.cycle.current} if self.mode == "cykl" else {self.mode}

    def shown_settings(self):
        """Ustawienia wspólne, a pod nimi tylko te od efektu na panelu."""
        fx = self.setting_fx()
        return [st for st in self.settings if self.SETTING_FX.get(st[0]) is None] + \
               [st for st in self.settings if fx & set((self.SETTING_FX.get(st[0]) or "").split())]

    def heavy(self, name):
        pk = self.peak.get(name)
        return bool(POWER["psu"]) and pk is not None and pk[1] == PANEL["bri"] and pk[0] > POWER["psu"] * 1.15

    def wled_post(self, payload, what):
        if not self.host:
            return
        def go():
            try:
                wled_state(self.host, payload)
            except Exception as e:  # noqa: BLE001
                self.say(f"nie udało się {what}: {e}")
        threading.Thread(target=go, daemon=True).start()

    def set_wled_bri(self, bri):
        # samo „bri” zapala wyłączony WLED; z "on": false WLED tylko zapamięta jasność na po włączeniu
        self.wled_post({"bri": bri} if self.wled_on is not False else {"bri": bri, "on": False}, "ustawić jasności")

    WATCH_EVERY = 1.0  # co ile sekund pytamy WLED o stan (włącznik)

    def watch_wled(self):
        """W tle co sekundę /json/state z WLED. Włącznik WLED jest nieprzekraczalny: każda klatka DDP przy
        wyłączonym WLED zapala diody, więc gdy WLED jest wyłączony (przycisk, aplikacja, HA) – nic nie wysyłamy."""
        def go():
            while self.running:
                host = self.host
                if host:
                    try:
                        st = http(f"http://{host}/json/state", timeout=2)
                    except Exception:  # noqa: BLE001 – WLED nie odpowiada: zostaje ostatni znany stan
                        st = None
                    if isinstance(st, dict) and "bri" in st and host == self.host:
                        self.wled_st = st
                time.sleep(self.WATCH_EVERY)
        threading.Thread(target=go, daemon=True).start()

    def wled_state_in(self, st):
        """Nowy stan z WLED (w tick): jasność, nadpisanie, włącznik."""
        PANEL["bri"] = st["bri"]
        self.lor = st.get("lor", 0)
        on = bool(st.get("on", True))
        want, until = self.power_want
        if on == want or time.monotonic() >= until:
            self.power_want = None, 0.0  # WLED przyjął przełączenie (albo nie odpowiedział) – dalej rządzi jego stan
        elif want is not None:
            on = want  # stan sprzed naszego przełączenia – inaczej jedna klatka DDP zapaliłaby WLED z powrotem
        if self.wled_on is not False and not on:
            self.say("WLED wyłączony – nie wysyłam, póki go nie włączysz")
            if self.sending and self.wled_id(self.mode) is None:
                self.wled_post({"live": False}, "zakończyć trybu realtime w WLED")  # gaśnie od razu, bez czekania
        elif self.wled_on is False and on:
            self.say("WLED włączony – wysyłam dalej")
        self.wled_on = on

    def text_step(self):
        """Podpowiedź do „tempo tekstu”: jak przesuwają się napisy i (wolniejszy) transparent ludzika. Płynnie jest
        tylko przy przesuwie co klatkę – wolniej tekst stoi i skacze; wtedy podpowiada najmniejsze płynne tempo."""
        def step(speed, k):  # (px na krok, co ile klatek krok) – jak w scroll_px
            ppf = speed * k * self.tempo / self.fps
            return (round(ppf), 1) if ppf >= 1 else (1, max(1, round(1 / ppf)))

        frames = lambda n: "klatki" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "klatek"
        fmt = lambda px, n: f"{px} px/klatkę" if n == 1 else f"1 px co {n} {frames(n)}"
        txt, ban = step(30, self.text), step(Worker.BANNER_SPEED, self.text)
        out = f"napisy {fmt(*txt)}, transparent ludzika {fmt(*ban)}"
        if txt[1] == 1 and ban[1] == 1:
            return out
        smooth = next((v for v in self.TEMPOS if step(Worker.BANNER_SPEED, v)[1] == 1), None)
        return out + (f" – skacze; płynnie od x{smooth:g}" if smooth else " – skacze; zwiększ tempo tekstu")

    def save(self):
        cfg = {"host": self.host, "tempo": self.tempo,
               "text_speed": self.text, "fps": self.fps, "every": self.cycle.every, "shuffle": self.cycle.shuffle,
               "fade": self.fade, "preview": self.preview, "mode": self.mode, "panel_bri": PANEL["bri"],
               "panel_levels": PANEL["levels"] if panel_manual() else None,
               "panel_levels_bri": PANEL["bri"] if panel_manual() else None, "panel_pe": PANEL["pe"],
               "psu": POWER["psu"], "auto_dim": POWER["auto"], "skip_heavy": self.skip_heavy, "peaks": self.peak, "width": self.new_width or W,
               "mirror": PANEL["mirror"], "ludzik_lvl": LUDZIK["lvl"], "ludzik_len": LUDZIK["len"],
               "ludzik_freq": LUDZIK["freq"], "ludzik_postac": LUDZIK_CHARS[LUDZIK["char"]][0],
               "ludzik_zmiana": (["losowo"] + LUDZIK_HOWS)[LUDZIK["how"]], "ludzik_strona": LUDZIK_SIDES[LUDZIK["side"]],
               "oczy_kolor": eye_hex(EYES["col"]),
               "sending": self.sending, "msg_auto": INBOX.auto, "msg_hours": INBOX.hours,
               "zegar_barwa": CLOCK_HUES[CLOCK["hue"]][0], "zegar_temp": CLOCK["temp"],
               "zegar_kolor": eye_hex(CLOCK["col"]), "zegar_czcionka": CLOCK_FONTS[CLOCK["font"]][0],
               "led_rgb": [COLOR["r"], COLOR["g"], COLOR["b"]], "color_fix": COLOR["fix"],
               "wled_fx_cfg": self.wled_saved}
        try:
            os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
            with open(CONFIG, "w", encoding="utf-8") as fh:
                json.dump(cfg, fh, ensure_ascii=False, indent=1)
        except OSError:
            pass

    # ---------------------------------------------------------- logika
    @property
    def speed(self):
        return self.SPEEDS[self.speed_i]

    def drawer(self, name):
        return self.cycle if name == "cykl" else self.inst[name]

    # ---------------------------------------------------------- efekty wbudowane w WLED
    def load_wled_fx(self):
        """W tle: lista efektów WLED (/json/eff) i ich cechy z /json/fxdata (2D, reaguje na dźwięk)."""
        host = self.host
        if not host:
            return

        def go():
            try:
                names = http(f"http://{host}/json/eff")
                try:
                    data = http(f"http://{host}/json/fxdata")
                except Exception:  # noqa: BLE001 – starsze WLED nie mają fxdata
                    data = []
                try:
                    pal = http(f"http://{host}/json/pal")
                except Exception:  # noqa: BLE001
                    pal = []
            except Exception as e:  # noqa: BLE001
                self.say(f"nie udało się pobrać efektów WLED: {e}")
                return
            fx = []
            for i, n in enumerate(names):
                if not n or n in ("RSVD", "-"):
                    continue
                meta = data[i] if i < len(data) and isinstance(data[i], str) else ""
                flags = (meta.split(";") + [""] * 4)[3]
                tags = ("2D" if "2" in flags else "") + (" ♪" if "v" in flags or "f" in flags else "")
                fx.append({"id": i, "name": n, "tags": tags.strip(), "meta": meta})
            if host == self.host:
                self.wled_fx, self.wled_pal = fx, [str(x) for x in pal]
                self.wled_ver += 1
        threading.Thread(target=go, daemon=True).start()

    @staticmethod
    def wled_id(name):
        """Numer efektu WLED z nazwy trybu „wled:<id>” albo None."""
        m = re.fullmatch(r"wled:(\d+)", str(name))
        return int(m[1]) if m else None

    def wled_name(self, i):
        return next((x["name"] for x in self.wled_fx if x["id"] == i), f"#{i}")

    WLED_SLIDERS = [("sx", "szybkość", 255), ("ix", "intensywność", 255), ("c1", "własny 1", 255),
                    ("c2", "własny 2", 255), ("c3", "własny 3", 31)]  # c3 w WLED ma 5 bitów
    WLED_CHECKS = [("o1", "opcja 1"), ("o2", "opcja 2"), ("o3", "opcja 3")]
    WLED_COLORS = ["kolor efektu", "tło", "kolor 3"]

    def wled_params(self, i):
        """Ustawienia efektu WLED z jego opisu w /json/fxdata („suwaki;kolory;paleta;cechy;domyślne”, „!” = nazwa
        domyślna, puste = efekt tego nie używa). -> lista {"key", "label", "kind", "max"}."""
        meta = next((x["meta"] for x in self.wled_fx if x["id"] == i), "")
        if not meta:  # bez opisu: Solid – sam kolor, starsze efekty – wszystko jak w aplikacji WLED
            meta = ";!;" if i == 0 else "!,!;!,!,!;!"
        parts = (meta.split(";") + [""] * 3)[:3]
        names, cols, pal = parts[0].split(","), parts[1].split(",") if parts[1] else [], parts[2]
        out = []
        for k, (key, default, top) in enumerate(self.WLED_SLIDERS):
            if k < len(names) and names[k]:
                out.append({"key": key, "label": default if names[k] == "!" else names[k], "kind": "range", "max": top})
        for k, (key, default) in enumerate(self.WLED_CHECKS):
            j = len(self.WLED_SLIDERS) + k
            if j < len(names) and names[j]:
                out.append({"key": key, "label": default if names[j] == "!" else names[j], "kind": "check"})
        if pal:
            out.append({"key": "pal", "label": "paleta", "kind": "list"})
        for k, name in enumerate(cols[:3]):
            if name:
                out.append({"key": f"col{k}", "label": self.WLED_COLORS[k] if name == "!" else name, "kind": "color"})
        return out

    def refresh_wled_seg(self, delay=0.5):
        """W tle: bieżące parametry segmentu WLED (po zmianie efektu WLED może ustawić swoje domyślne)."""
        host = self.host

        def go():
            time.sleep(delay)
            try:
                st = http(f"http://{host}/json/state")
                seg = next(g for g in st["seg"] if g.get("id") == st.get("mainseg", 0))
            except Exception:  # noqa: BLE001
                return
            self.wled_seg = {k: seg.get(k) for k in ("fx", "sx", "ix", "c1", "c2", "c3", "o1", "o2", "o3", "pal", "col")}
        threading.Thread(target=go, daemon=True).start()

    def wled_set(self, key, value):
        """Zmiana ustawienia efektu WLED z panelu: od razu do WLED i do pamięci tego efektu."""
        i = self.wled_id(self.mode)
        if i is None:
            return
        seg = (self.wled_st or {}).get("mainseg", 0)
        if key.startswith("col"):
            col = [list(c) for c in (self.wled_seg.get("col") or [[0, 0, 0]] * 3)] + [[0, 0, 0]] * 3
            col = col[:3]
            col[int(key[3])] = list(value)
            self.wled_seg["col"], payload = col, {"col": col}
        else:
            self.wled_seg[key], payload = value, {key: value}
        self.wled_saved.setdefault(str(i), {}).update(payload)
        self.wled_post({"seg": [dict({"id": seg}, **payload)]}, "zmienić ustawienia efektu WLED")

    def wled_snapshot(self):
        """Ustawienia bieżącego efektu WLED z wartościami – do panelu WWW."""
        i = self.wled_id(self.mode)
        if i is None:
            return None
        seg, items = self.wled_seg if self.wled_seg.get("fx") == i else {}, []
        mine = self.wled_saved.get(str(i), {})
        for it in self.wled_params(i):
            key = it["key"]
            if key.startswith("col"):
                cols = mine.get("col") or seg.get("col") or []
                c = cols[int(key[3])] if int(key[3]) < len(cols) and cols[int(key[3])] else [0, 0, 0]
                v = "#%02x%02x%02x" % tuple(int(clamp(x, 0, 255)) for x in c[:3])
            else:
                v = mine.get(key, seg.get(key))
            item = dict(it, value=v)
            if key == "pal":
                item["labels"] = self.wled_pal
            items.append(item)
        return {"id": i, "items": items}

    def select_wled(self, i):
        """Efekt WLED: przestajemy wysyłać (tick nic nie śle), a WLED od razu wychodzi z trybu realtime i gra efekt."""
        if not self.host:
            self.say("najpierw podaj host WLED")
            return
        self.fade_from = None
        self.mode = f"wled:{i}"
        seg = (self.wled_st or {}).get("mainseg", 0)
        mine = self.wled_saved.get(str(i))  # zapamiętane ustawienia tego efektu, a bez nich domyślne z WLED
        # bez "on": wyłączony WLED zostaje wyłączony (włącznik jest nieprzekraczalny), efekt ruszy po włączeniu
        self.wled_post({"live": False, "seg": [dict({"id": seg, "fx": i}, **(mine or {"fxdef": True}))]},
                       "włączyć efektu WLED")
        self.wled_seg = {}
        self.refresh_wled_seg()

    def select(self, name):
        i = self.wled_id(name)
        if i is not None:
            return self.select_wled(i)
        was_wled = self.wled_id(self.mode) is not None
        self.cursor = self.NAMES.index(name)
        if name == self.mode:
            return
        if was_wled:  # z powrotem do naszego strumienia – WLED ma go pokazywać, nie własny efekt
            self.wled_post({"lor": 0}, "wyłączyć nadpisywania w WLED")
            self.fade_from, self.mode = None, name
            return
        same = "cykl" in (name, self.mode) and self.cycle.current in (name, self.mode)
        self.fade_from, self.fade_acc = (None if same or self.fade <= 0 else self.mode), 0.0
        self.mode = name

    def skip(self, d):
        i = self.wled_id(self.mode)
        if i is not None and self.wled_fx:  # ← → po efektach WLED
            ids = [x["id"] for x in self.wled_fx]
            self.select_wled(ids[((ids.index(i) if i in ids else -1) + d) % len(ids)])
        elif self.mode == "cykl":
            self.cycle.skip(d)
        else:
            names = list(CLOCKS)
            self.select(names[(names.index(self.mode) + d) % len(names)])

    def render(self, now, t, dt):
        f = Frame()
        i = self.wled_id(self.mode)
        if i is not None:  # tylko do podglądu (nie wysyłamy) – obrazu efektu WLED skrypt nie widzi
            scroll_segs(f, [("efekt WLED: ", (120, 120, 140)), (self.wled_name(i), (255, 200, 80)),
                            ("  (podgląd tylko na panelu)", (90, 90, 110))], t, 30, 0, gap=40)
            return f
        self.drawer(self.mode).draw(f, now, t, dt)
        if self.fade_from is not None:
            self.fade_acc += dt
            if self.fade_acc < self.fade:
                b = Frame()
                self.drawer(self.fade_from).draw(b, now, t, dt)
                f = blend(b, f, self.fade_acc / self.fade)
            else:
                self.fade_from = None
        return f

    def say(self, msg):
        self.note, self.note_until = msg, time.monotonic() + 3

    def doc(self, name):
        i = self.wled_id(name)
        if i is not None:
            tags = next((x["tags"] for x in self.wled_fx if x["id"] == i), "")
            return "Efekt wbudowany w WLED" + (" (2D)" if "2D" in tags else "") + \
                (" – reaguje na dźwięk (potrzebny mikrofon w WLED)" if "♪" in tags else "") + "."
        return ((CLOCKS[name] if name in CLOCKS else Cycle).__doc__ or "").strip()

    # ---------------------------------------------------------- akcje (klawisze TUI i polecenia z WWW)
    def ask_host(self):
        """Ustawienie „host”: TUI otwiera pole edycji, panel WWW ma własne pole."""

    def open_acts(self):
        """Ustawienie „ludzik zajęcia”: TUI otwiera podlistę, panel WWW ma własną."""

    def toggle_send(self):
        if self.host:
            self.sending = not self.sending
        else:
            self.say("najpierw podaj host WLED")
            self.ask_host()

    def toggle_power(self):
        """Włącznik WLED z panelu: jak przycisk w WLED, tylko zdalnie."""
        if not self.host or self.wled_on is None:
            self.say("WLED nie odpowiada – nie wiem, czy jest włączony")
            return
        on = not self.wled_on
        self.wled_post({"on": on}, "włączyć WLED" if on else "wyłączyć WLED")
        self.power_want = None, 0.0  # nowe kliknięcie zastępuje poprzednie
        self.wled_state_in({**self.wled_st, "on": on})
        self.power_want = on, time.monotonic() + 3 * self.WATCH_EVERY + 4

    def set_host(self, host):
        self.host = host.strip()
        self.sending = bool(self.host)
        self.err = ""
        self.say(f"host: {self.host or '(brak)'}")
        self.wled_st, self.wled_on, self._last_st = None, None, None
        self.power_want = None, 0.0
        self.wled_fx = []
        self.load_wled_fx()

    def toggle_pause(self):
        self.paused = not self.paused

    def toggle_shuffle(self):
        self.cycle.shuffle = not self.cycle.shuffle
        self.say("cykl: " + ("losowa kolejność" if self.cycle.shuffle else "po kolei"))

    def toggle_mirror(self):
        PANEL["mirror"] = not PANEL["mirror"]
        self.say("odbicie lustrzane włączone – obraz odwrócony w poziomie (do kamerki)" if PANEL["mirror"]
                 else "odbicie lustrzane wyłączone")

    def override_off(self):
        self.wled_post({"lor": 0}, "wyłączyć nadpisywania w WLED")
        self.lor = 0
        self.say("WLED znów pokazuje obraz ze skryptu")

    def every_step(self, d):
        self.cycle.every = max(10, self.cycle.every + 10 * d)

    def speed_step(self, d):
        self.speed_i = max(0, min(len(self.SPEEDS) - 1, self.speed_i + d))

    def real_time(self):
        self.offset, self.speed_i = dtm.timedelta(), self.SPEEDS.index(1)
        self.say("czas = prawdziwa godzina")

    def setting(self, name, d):
        for n, _, change, _ in self.settings:
            if n == name:
                change(d)
                return
        raise KeyError(name)

    # ---------------------------------------------------------- pętla
    def send(self, data):
        if not (self.sending and self.host and self.wled_on):  # wyłączony (albo nieznany) WLED – nic
            return
        try:
            send_ddp(self.sock, self.host, data, self.seq)
            self.seq = self.seq % 15 + 1
            self.pkts += 1
            self.err = ""
        except OSError as e:
            self.err = e.strerror or str(e)

    def run_cmds(self):
        while True:
            try:
                fn = self.cmds.get_nowait()
            except queue.Empty:
                return
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                self.say(f"błąd polecenia: {e}")
            self.dirty_at = self.dirty_at or time.monotonic()

    def tick(self):
        """Jedna klatka: polecenia, czas, stan WLED, render, ogranicznik prądu, wysłanie. -> (klatka po ograniczniku, czas)"""
        self.run_cmds()
        if INBOX.check():
            self.say("skrzynka „napisz” zamknęła się sama")
        m = time.monotonic()
        rdt, self.last = m - self.last, m
        self.fps_ema += ((1 / rdt if rdt > 0 else self.fps) - self.fps_ema) * 0.1
        if self.paused:
            self.offset -= dtm.timedelta(seconds=rdt)          # zegar stoi
        else:
            self.offset += dtm.timedelta(seconds=rdt * (self.speed - 1))
        now = dtm.datetime.now().astimezone() + self.offset
        ANIM.update(fps=self.fps, tempo=self.tempo, text=self.text)
        st = self.wled_st
        if st is not None and st is not self._last_st:
            self._last_st = st
            self.wled_state_in(st)
        c0 = time.monotonic()
        if self.frame is None or not self.paused:
            # stały krok animacji = równe ruchy w każdej klatce (bez szarpania przy wahaniach zegara)
            dt = self.tempo / self.fps
            self.t += dt
            self.frame = self.render(now, self.t, dt)
        out, data = self.limiter.apply(self.frame, 1 / self.fps)
        if self.wled_id(self.mode) is None:  # efekt WLED: WLED gra sam, my nic nie wysyłamy
            name = self.cycle.current if self.mode == "cykl" else self.mode
            pk = self.peak.get(name)
            if not pk or pk[1] != PANEL["bri"] or self.limiter.raw > pk[0]:
                self.peak[name] = [round(self.limiter.raw), PANEL["bri"]]
            self.send(data)
        self.cost_ema += (time.monotonic() - c0 - self.cost_ema) * 0.1
        if m < self.view_until:      # ktoś ogląda panel WWW
            if m >= self.view_next:
                self.view_next = m + 0.1
                self.view = bytes(v for row in panel_view(out.rgb_rows()) for c in row for v in c)
            if m >= self.snap_next:
                self.snap_next = m + 0.5
                self.snap = self.snapshot(now)
        return out, now

    def snapshot(self, now):
        """Stan do panelu WWW (tylko typy JSON)."""
        return {
            "w": W, "h": H, "mode": self.mode, "current": self.cycle.current, "paused": self.paused,
            "wled_mode": self.wled_id(self.mode) is not None, "wled_ver": self.wled_ver,
            "wled_settings": self.wled_snapshot(),
            "sending": self.sending, "wled_on": self.wled_on, "host": self.host, "lor": self.lor, "mirror": PANEL["mirror"],
            "time": now.strftime("%H:%M:%S"), "fake_time": bool(self.offset) or self.speed != 1,
            "settings": [dict({"name": n, "value": val(), "hint": self.text_step() if n == "tempo tekstu" else hint,
                               "fx": self.SETTING_FX.get(n, "")}, **self.choice_json(n)) for n, val, _, hint in self.settings],
            "setting_fx": sorted(self.setting_fx()),
            "heavy": [n for n in CLOCKS if self.heavy(n)],
            "ludzik": {a: ludzik_lvl(a) for a in LUDZIK_ACTS}, "ludzik_len": {a: ludzik_len(a) for a in LUDZIK_TIMED},
            "ludzik_next": LUDZIK["next"], "ludzik_status": dict(LUDZIK_STATUS),
            "inbox": INBOX.snapshot(),
            "power": {"est": round(self.limiter.est), "raw": round(self.limiter.raw), "k": round(self.limiter.k, 3),
                      "psu": POWER["psu"], "auto": POWER["auto"]},
            "bri": PANEL["bri"], "levels": panel_levels(),
            "fps": round(self.fps_ema, 1), "fps_set": self.fps, "render_ms": round(self.cost_ema * 1000, 1),
            "pkts": self.pkts, "err": self.err, "net": NET.status(),
            "note": self.note if time.monotonic() < self.note_until else "",
        }

    def run_headless(self):
        """Pętla bez terminala (panel WWW, add-on HA): klatki w rytmie fps, autozapis ustawień."""
        nxt = self.last = time.monotonic()
        try:
            while self.running:
                self.tick()
                if self.dirty_at and time.monotonic() - self.dirty_at > 5:
                    self.dirty_at = None
                    self.save()
                nxt += 1 / self.fps
                if nxt < time.monotonic():      # spóźnienie: nie nadrabiamy serią klatek
                    nxt = time.monotonic()
                time.sleep(max(0.0, nxt - time.monotonic()))
        except KeyboardInterrupt:
            pass
        finally:
            self.save()


# ================================================================ TUI
class Tui(Engine):
    """Interaktywny panel w terminalu: podgląd na żywo (1 dioda = 1 kropka), lista efektów i ustawienia."""

    def __init__(self, a, cfg):
        super().__init__(a, cfg)
        self.edit = None          # tekst wpisywanego hosta albo None
        self.search = None        # tekst wyszukiwania (/) albo None
        self.focus, self.scur, self.acur, self.afilt = "list", 0, 0, ""

    def ask_host(self):
        self.edit = self.host

    def open_acts(self):
        self.focus, self.acur, self.afilt = "acts", 0, ""

    # ---------------------------------------------------------- klawisze
    @staticmethod
    def parse_keys(data):
        i = 0
        while i < len(data):
            ch = data[i]
            if ch == "\x1b" and i + 1 < len(data) and data[i + 1] in "[O":
                j = i + 2
                while j < len(data) and not ("@" <= data[j] <= "~"):
                    j += 1
                seq = data[i + 2:j + 1]
                yield {"A": "up", "B": "down", "C": "right", "D": "left", "H": "home", "F": "end", "5~": "pgup",
                       "6~": "pgdn", "1~": "home", "4~": "end", "Z": "backtab"}.get(seq, "")
                i = j + 1
            else:
                yield "esc" if ch == "\x1b" else ch
                i += 1

    @staticmethod
    def fold(s):
        """Małe litery bez polskich znaków – „glowie” pasuje do „głowie”."""
        s = unicodedata.normalize("NFD", s.lower().replace("ł", "l"))
        return "".join(ch for ch in s if not unicodedata.combining(ch))

    def matches(self):
        q = self.fold(self.search or "")
        return [i for i, n in enumerate(self.NAMES) if q in n or q in self.fold(self.doc(n) or "")]

    def act_matches(self):
        """Zajęcia ludzika pasujące do wpisanego fragmentu nazwy."""
        q = self.fold(self.afilt)
        return [i for i, a in enumerate(LUDZIK_ACTS) if q in self.fold(a)]

    def on_key(self, k):
        if self.search is not None:
            if k in ("\r", "\n"):
                self.search = None
                self.select(self.NAMES[self.cursor])
            elif k == "esc":
                self.search = None
            elif k in ("up", "down"):
                m = self.matches()
                if m:
                    pos = m.index(self.cursor) if self.cursor in m else 0
                    self.cursor = m[(pos + (1 if k == "down" else -1)) % len(m)]
            else:
                if k in ("\x7f", "\b"):
                    self.search = self.search[:-1]
                elif len(k) == 1 and k.isprintable():
                    self.search += k
                m = self.matches()
                if m:
                    self.cursor = m[0]
            return
        if self.edit is not None:
            if k in ("\r", "\n"):
                self.set_host(self.edit)
                self.edit = None
            elif k == "esc":
                self.edit = None
            elif k in ("\x7f", "\b"):
                self.edit = self.edit[:-1]
            elif len(k) == 1 and k.isprintable():
                self.edit += k
            return
        if self.focus == "acts":  # podlista: częstość każdego zajęcia ludzika; litery filtrują po nazwie
            m = self.act_matches()
            pos = m.index(self.acur) if self.acur in m else 0
            act = LUDZIK_ACTS[self.acur] if self.acur in m else None
            if k in ("up", "down") and m:
                self.acur = m[(pos + (1 if k == "down" else -1)) % len(m)]
            elif k in ("left", "right") and act:
                LUDZIK["lvl"][act] = max(0, min(3, ludzik_lvl(act) + (1 if k == "right" else -1)))
            elif k in (" ", "\r", "\n") and act:
                LUDZIK["lvl"][act] = (ludzik_lvl(act) + 1) % 4
            elif k in ("0", "1", "2", "3") and act:
                LUDZIK["lvl"][act] = int(k)
            elif k == "!" and act:  # zrób jako następne (drugi raz – anuluj)
                LUDZIK["next"] = None if LUDZIK["next"] == act else act
            elif k in ("-", "+", "=") and act in LUDZIK_TIMED:  # długość zajęcia
                LUDZIK["len"][act] = max(0, min(len(LUDZIK_LEN) - 1, ludzik_len(act) + (-1 if k == "-" else 1)))
            elif k == "*" and m:  # wszystkie widoczne: wyłącz, a gdy już wyłączone – normalnie
                names = [LUDZIK_ACTS[i] for i in m]
                v = 0 if any(ludzik_lvl(a) for a in names) else 2
                LUDZIK["lvl"].update({a: v for a in names})
            elif k == "esc" and self.afilt:
                self.afilt = ""
            elif k in ("esc", "\t", "backtab"):
                self.focus, self.afilt = "set", ""
            elif k in ("\x7f", "\b") or (len(k) == 1 and k.isprintable()):
                self.afilt = self.afilt[:-1] if k in ("\x7f", "\b") else self.afilt + k
                m = self.act_matches()
                if m and self.acur not in m:
                    self.acur = m[0]
            return
        if k in ("\t", "backtab"):
            self.focus = "set" if self.focus == "list" else "list"
            return
        if self.focus == "set":
            shown = self.shown_settings()
            ns = len(shown)
            self.scur = min(self.scur, ns - 1)
            if k in ("up", "k"):
                self.scur = (self.scur - 1) % ns
                return
            if k in ("down", "j"):
                self.scur = (self.scur + 1) % ns
                return
            if k in ("left", "right", "+", "=", "-", "_", "\r", "\n"):
                d = 1 if k in ("right", "+", "=", "\r", "\n") else -1
                shown[self.scur][2](d)
                return
            if k == "esc":
                self.focus = "list"
                return
        n = len(self.NAMES)
        if k in ("up", "k"):
            self.cursor = (self.cursor - 1) % n
        elif k in ("down", "j"):
            self.cursor = (self.cursor + 1) % n
        elif k == "pgup":
            self.cursor = max(0, self.cursor - 10)
        elif k == "pgdn":
            self.cursor = min(n - 1, self.cursor + 10)
        elif k == "home":
            self.cursor = 0
        elif k == "end":
            self.cursor = n - 1
        elif k == "/":
            self.search, self.focus = "", "list"
        elif k == "l":
            self.toggle_shuffle()
        elif k in ("\r", "\n"):
            self.select(self.NAMES[self.cursor])
        elif k in ("right", "n"):
            self.skip(1)
        elif k in ("left", "p"):
            self.skip(-1)
        elif k == "c":
            self.select("cykl")
        elif k == "]":
            self.every_step(1)
        elif k == "[":
            self.every_step(-1)
        elif k in (">", "."):
            self.speed_step(1)
        elif k in ("<", ","):
            self.speed_step(-1)
        elif k == "r":
            self.real_time()
        elif k == " ":
            self.toggle_pause()
        elif k == "s":
            self.toggle_send()
        elif k == "w":
            self.toggle_power()
        elif k == "h":
            self.ask_host()
        elif k == "o":
            self.override_off()
        elif k == "v":
            self.preview = self.PREVIEWS[(self.PREVIEWS.index(self.preview) + 1) % len(self.PREVIEWS)]
            self.resized = True
        elif k == "m":
            self.toggle_mirror()
        elif k in ("q", "Q", "\x03"):
            self.running = False

    # ---------------------------------------------------------- ekran
    @staticmethod
    def panel_leds(rows):
        """1:1 z panelem: każda dioda to „● ” (2 znaki szerokości ≈ wysokość wiersza), więc piksele są kwadratowe
        i mają przerwy jak prawdziwe diody. Zgaszone diody = ciemne kropki."""
        out = []
        for row in rows:
            s, last = [], None
            for c in row:
                key = "off" if c == (0, 0, 0) else c
                if key != last:
                    s.append("\x1b[38;2;34;34;38m" if key == "off" else "\x1b[38;2;%d;%d;%dm" % c)
                    last = key
                s.append("· " if key == "off" else "● ")
            out.append("".join(s)[:-1] + "\x1b[0m")
        return out, 2 * W - 1

    @staticmethod
    def panel_blocks(rows):
        """Półbloki: 1 znak = 1 piksel szerokości i 2 piksele wysokości – też kwadratowe piksele, ale bez przerw."""
        out = []
        for y in range(0, H, 2):
            top, bot = rows[y], rows[y + 1] if y + 1 < H else [(0, 0, 0)] * W
            s, last = [], None
            for a, b in zip(top, bot):
                if (a, b) != last:
                    s.append("\x1b[38;2;%d;%d;%dm\x1b[48;2;%d;%d;%dm" % (a + b))
                    last = (a, b)
                s.append("▀")
            out.append("".join(s) + "\x1b[0m")
        return out, W

    def screen(self, frame, now):
        cols, rows_n = shutil.get_terminal_size((100, 30))
        B, D, R, G, Y, C, INV = "\x1b[1m", "\x1b[2m", "\x1b[0m", "\x1b[32m", "\x1b[33m", "\x1b[36m", "\x1b[7m"
        L = []
        if self.edit is not None:
            state = f"{Y}wpisz IP WLED, Enter = OK, Esc = anuluj{R}"
        elif self.sending and self.wled_on is False:
            state = f"{Y}⏻ WLED wyłączony{R}"
        elif self.sending:
            state = f"{G}● wysyła{R}"
        else:
            state = f"{D}○ nie wysyła{R}"
        host = (self.edit + "█") if self.edit is not None else (self.host or "(brak – naciśnij h)")
        clock_txt = now.strftime("%H:%M:%S") + (f" {Y}(udawany){R}" if self.offset or self.speed != 1 else "")
        L.append(f" {B}WLED zegary{R}  {D}│{R}  host: {B}{host}{R}  {D}│{R}  {state}  {D}│{R}  {clock_txt}"
                 + (f"  {Y}⏸ pauza{R}" if self.paused else "")
                 + (f"  {C}⇋ odbicie{R}" if PANEL["mirror"] else "")
                 + (f"  \x1b[41m\x1b[97m WLED pokazuje własny efekt (nadpisanie) – naciśnij o {R}" if self.lor and self.sending else ""))
        if self.preview != "wyłączony":
            rows = panel_view(frame.rgb_rows())
            leds = cols >= 2 * W + 3
            lines, pw = self.panel_leds(rows) if leds else self.panel_blocks(rows)
            L.append(f" {D}┌{'─' * pw}┐{R}")
            L += [f" {D}│{R}{ln}{D}│{R}" for ln in lines]
            L.append(f" {D}└{'─' * pw}┘{R}" + ("" if leds else
                     f"  {D}terminal {cols} kol.; od {2 * W + 3} kolumn podgląd pokaże pojedyncze diody (Ctrl + minus){R}"))
        # lewa kolumna: przewijana lista efektów
        lh = max(6, rows_n - len(L) - 5)
        lf = self.focus == "list"
        if self.search is not None:
            head = f"{Y}/{self.search}█{R} {D}({len(self.matches())}){R}"
        else:
            head = ((f"{INV if lf else B} Efekt {R}" if lf else f"{D}Efekt{R}") + f" {D}{self.cursor + 1}/{len(self.NAMES)}"
                    f"  {CATEGORY.get(self.NAMES[self.cursor], 'cykl')}{R}")
        left = [head]
        top = int(clamp(self.cursor - lh // 2, 0, max(0, len(self.NAMES) - lh)))
        for i in range(top, min(len(self.NAMES), top + lh)):
            name = self.NAMES[i]
            cur = "▸" if i == self.cursor and lf else " "
            if name == self.mode:
                mark = f"{G}● {name}{R}"
            elif self.mode == "cykl" and name == self.cycle.current:
                mark = f"{C}↻ {name}{R}"
            else:
                mark = f"  {name}"
            if name in CLOCKS and self.heavy(name):
                mark += f" {Y}⚡{R}"
            if self.search and i not in self.matches():
                mark = f"{D}{strip_ansi(mark)}{R}"
            left.append(f"{Y}{cur}{R} {D}{i + 1:3d}{R} {mark}")
        # prawa kolumna: ustawienia (Tab), potem statystyki i opis
        sf = self.focus == "set"
        if self.focus == "acts":
            right = [f"{INV} Zajęcia ludzika {R} " + (f"{Y}szukaj: {self.afilt}█{R}" if self.afilt else
                                                      f"{D}(←→ jak często, - + jak długo, ! zrób następne; pisz, żeby szukać){R}")]
            m = self.act_matches()
            if not m:
                right.append(f"  {D}nic nie pasuje do „{self.afilt}” (Backspace / Esc){R}")
            for i in m:
                act = LUDZIK_ACTS[i]
                sel = i == self.acur
                lv = ludzik_lvl(act)
                lab = (D, Y, G, C)[lv] + "◂ " + f"{LUDZIK_LVL[lv]:9s}" + " ▸" + R
                if act in LUDZIK_TIMED:
                    lab += f"  {D if not lv else ''}{LUDZIK_LEN[ludzik_len(act)]:12s}{R}"
                if LUDZIK["next"] == act:
                    lab += f"  {G}▶ następne{R}"
                right.append(f"{Y + '▸' if sel else ' '}{R} {(B if sel else '')}{act:20s}{R} {lab}")
        else:
            right = [(f"{INV} Ustawienia {R}" if sf else f"{D}Ustawienia{R}") + f" {D}(Tab){R}"]
            shown = self.shown_settings()
            self.scur = min(self.scur, len(shown) - 1)
            for i, (name, val, _, hint) in enumerate(shown):
                if i and self.SETTING_FX.get(name) and not self.SETTING_FX.get(shown[i - 1][0]):
                    right.append(f"  {D}— efekt: {', '.join(sorted(self.setting_fx()))} —{R}")
                sel = sf and i == self.scur
                hint = self.text_step() if name == "tempo tekstu" else hint
                right.append(f"{Y + '▸' if sel else ' '}{R} {name:15s} {(B if sel else '')}{val()}{R}  {D}{hint}{R}")
        right += [
            "",
            f"{D}prąd ~{self.limiter.est / 1000:.2f} A" + (f" / limit {POWER['psu'] / 1000:g} A" if POWER["psu"] else "")
            + (f"{R}  {Y}przyciemniam do {self.limiter.k * 100:.0f}% (efekt chce {self.limiter.raw / 1000:.1f} A){R}"
               if self.limiter.k < 0.98 else
               f"{R}  {Y}ponad budżet zasilacza (przyciemnianie wyłączone){R}"
               if POWER["psu"] and self.limiter.raw > POWER["psu"] else R),
            f"{D}panel: jasność WLED {PANEL['bri']}/255, model: {panel_levels()} poziomów na kanał{R}"
            + (f"  {Y}fps > 20: panel nie nadąży{R}" if self.fps > 22 else ""),
            f"{D}fps {self.fps_ema:4.1f}/{self.fps:g}  render {self.cost_ema * 1000:4.1f} ms  pakiety {self.pkts}{R}"
            + (f"  {Y}błąd: {self.err}{R}" if self.err else ""),
            f"{D}sieć: {NET.status()[:max(10, cols - 40)] or '—'}{R}",
            "",
            f"{C}{self.NAMES[self.cursor]}{R}" + (f"  {D}(teraz w cyklu: {self.cycle.current}){R}" if self.mode == "cykl" else ""),
        ] + wrap(self.doc(self.NAMES[self.cursor]), max(20, cols - 34))
        L.append("")
        for i in range(max(len(left), len(right))):
            lt = left[i] if i < len(left) else ""
            pad = 26 - len(strip_ansi(lt))
            L.append(" " + lt + " " * max(pad, 1) + (right[i] if i < len(right) else ""))
        L.append("")
        note = self.note if time.monotonic() < self.note_until else ""
        if self.focus == "acts":
            L.append(f" {D}pisz = szukaj  ↑↓ wybór  ←→ lub 0–3 częstość (0 = wył.)  spacja następna  "
                     f"* wył./wł. widoczne  Esc {'czyść' if self.afilt else 'powrót'}{R}")
        elif sf:
            L.append(f" {D}Tab lista  ↑↓ ustawienie  ←→ / + - zmiana  Enter przełącz  spacja pauza  q wyjście{R}")
        else:
            L.append(f" {D}Tab ustawienia  ↑↓ PgUp PgDn Enter wybór  / szukaj  ←→ następny  c cykl  m odbicie  spacja pauza  q wyjście{R}")
        if note:
            L.append(f" {Y}{note}{R}")
        L = L[:rows_n - 1]
        out = ("\x1b[2J" if self.resized else "") + "\x1b[H" + "\x1b[K\r\n".join(L) + "\x1b[K\x1b[J"
        self.resized = False
        sys.stdout.write(out)
        sys.stdout.flush()

    # ---------------------------------------------------------- pętla
    def run(self):
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        signal.signal(signal.SIGWINCH, lambda *_: setattr(self, "resized", True))
        try:
            tty.setcbreak(fd)
            sys.stdout.write("\x1b[?1049h\x1b[?25l")
            nxt = self.last = time.monotonic()
            while self.running:
                out, now = self.tick()
                self.screen(out, now)
                nxt += 1 / self.fps
                if nxt < time.monotonic():      # spóźnienie: nie nadrabiamy serią klatek (panel by ich nie pokazał)
                    nxt = time.monotonic()
                while self.running:
                    wait = nxt - time.monotonic()
                    if wait <= 0:
                        break
                    if select.select([fd], [], [], wait)[0]:
                        for k in self.parse_keys(os.read(fd, 64).decode("utf-8", "ignore")):
                            self.on_key(k)
        except KeyboardInterrupt:
            pass
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()
            self.save()


def strip_ansi(s):
    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", s)


def wrap(text, width):
    return textwrap.wrap(" ".join(text.split()), width) or [""]


# ================================================================ panel WWW (np. Home Assistant Ingress)
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
WEB_FILES = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8",
             "style.css": "text/css; charset=utf-8"}


def web_cmd(e, c):
    """Polecenie z panelu WWW -> funkcja do wykonania w wątku klatek; ValueError = złe polecenie."""
    op = c.get("op")
    d = 1 if int(c.get("d", 1)) > 0 else -1
    simple = {"pause": e.toggle_pause, "send": e.toggle_send, "power": e.toggle_power, "mirror": e.toggle_mirror, "shuffle": e.toggle_shuffle,
              "override": e.override_off, "realtime": e.real_time}
    if op in simple:
        return simple[op]
    if op == "select":
        name = c.get("name")
        i = e.wled_id(name)
        if name not in e.NAMES and (i is None or i not in [x["id"] for x in e.wled_fx]):
            raise ValueError(f"nie ma efektu {name!r}")
        return lambda: e.select(name)
    if op == "skip":
        return lambda: e.skip(d)
    if op == "every":
        return lambda: e.every_step(d)
    if op == "speed":
        return lambda: e.speed_step(d)
    if op == "setting":
        name = c.get("name")
        if name not in [s[0] for s in e.settings]:
            raise ValueError(f"nie ma ustawienia {name!r}")
        if "i" in c:  # suwak / lista w panelu WWW: konkretna wartość
            if name not in e.choices:
                raise ValueError(f"ustawienie {name!r} nie ma listy wartości")
            i = int(c["i"])
            if not 0 <= i < len(e.choice(name)[0]):
                raise ValueError(f"zła wartość ustawienia {name!r}")
            return lambda: e.pick(name, i)
        return lambda: e.setting(name, d)
    if op == "clockcol":
        h = str(c.get("col", ""))
        if h and not eye_rgb(h):
            raise ValueError("kolor zegara: #rrggbb albo pusty (z barwy)")
        return lambda: CLOCK.update(col=eye_rgb(h))
    if op == "eyes":
        h = str(c.get("col", ""))
        if h and not eye_rgb(h):
            raise ValueError("kolor oczu: #rrggbb albo pusty (naturalny)")
        return lambda: EYES.update(col=eye_rgb(h))
    if op == "host":
        host = str(c.get("host", "")).strip()
        if len(host) > 64 or not re.fullmatch(r"[A-Za-z0-9.:\-\[\]]*", host):
            raise ValueError("zły adres hosta")
        return lambda: e.set_host(host)
    if op == "ludzik":  # częstość (lvl), długość (len) zajęcia albo „zrób jako następne” (next; drugi raz = anuluj)
        act = c.get("act")
        if c.get("next"):
            if act not in LUDZIK_ACTS:
                raise ValueError("złe zajęcie ludzika")
            return lambda: LUDZIK.update(next=None if LUDZIK["next"] == act else act)
        if "len" in c:
            n = int(c["len"])
            if act not in LUDZIK_TIMED or not 0 <= n < len(LUDZIK_LEN):
                raise ValueError("zła długość zajęcia ludzika")
            return lambda: LUDZIK["len"].__setitem__(act, n)
        lvl = int(c.get("lvl", 2))
        if act not in LUDZIK_ACTS or not 0 <= lvl <= 3:
            raise ValueError("złe zajęcie ludzika")
        return lambda: LUDZIK["lvl"].__setitem__(act, lvl)
    if op == "wled":  # ustawienie bieżącego efektu WLED
        i = e.wled_id(e.mode)
        key = c.get("key")
        item = next((x for x in e.wled_params(i) if x["key"] == key), None) if i is not None else None
        if item is None:
            raise ValueError(f"efekt WLED nie ma ustawienia {key!r}")
        v = c.get("v")
        if item["kind"] == "range":
            v = int(v)
            if not 0 <= v <= item["max"]:
                raise ValueError("wartość poza zakresem")
        elif item["kind"] == "check":
            v = bool(v)
        elif item["kind"] == "list":
            v = int(v)
            if not 0 <= v < max(1, len(e.wled_pal)):
                raise ValueError("nie ma takiej palety")
        else:
            m = re.fullmatch(r"#([0-9a-fA-F]{6})", str(v))
            if not m:
                raise ValueError("zły kolor")
            v = [int(m[1][k:k + 2], 16) for k in (0, 2, 4)]
        return lambda: e.wled_set(key, v)
    if op == "inbox":
        act = c.get("act")
        if act == "open":
            return INBOX.open
        if act == "close":
            return INBOX.close
        if act == "auto":
            return lambda: setattr(INBOX, "auto", not INBOX.auto)
        if act == "hours":
            h = float(c.get("v", 0))
            if not MSG_HOURS[0] <= h <= MSG_HOURS[1]:
                raise ValueError(f"czas otwarcia skrzynki: od {MSG_HOURS[0]:g} do {MSG_HOURS[1]:g} h")
            h = round(h * 4) / 4  # co kwadrans
            return lambda: INBOX.set_hours(h)
        if act in ("approve", "reject", "block", "again", "clear"):
            mid = int(c.get("id", 0))
            return lambda: INBOX.act(act, mid)
        raise ValueError(f"złe polecenie skrzynki {act!r}")
    raise ValueError(f"nieznane polecenie {op!r}")


class Thumbs:
    """Podglądy na liście efektów w panelu WWW: kilka sekund efektu policzone na boku (ostatnia klatka, w barwach
    diod), trzymane w pamięci minutę (godzina, dane z sieci, które dopiero doszły). Liczone po jednym, żeby nie
    zabierać czasu klatkom na panelu."""

    SECONDS, FPS, KEEP = 3.0, 12, 60

    def __init__(self):
        self.cache, self.lock = {}, threading.Lock()

    def get(self, key, make):
        hit = self.cache.get(key)
        if hit and time.monotonic() - hit[0] < self.KEEP:
            return hit[1]
        with self.lock:
            hit = self.cache.get(key)
            if not (hit and time.monotonic() - hit[0] < self.KEEP):
                THUMB.on = True
                try:
                    f = make()
                finally:
                    THUMB.on = False
                hit = self.cache[key] = (time.monotonic(), bytes(v for row in panel_view(f.rgb_rows()) for c in row for v in c))
        return hit[1]

    def effect(self, name):
        def make():
            fx, n, dt = CLOCKS[name](), int(self.SECONDS * self.FPS), 1 / self.FPS
            start = dtm.datetime.now().astimezone() - dtm.timedelta(seconds=self.SECONDS)  # kończy się na „teraz”
            for i in range(n):
                f = Frame()
                fx.draw(f, start + dtm.timedelta(seconds=i * dt), i * dt, dt)
            return f
        return self.get(("fx", name), make)

    def char(self, i):
        """Postać ludzika: stoi, macha i idzie (pierwsze 30 kolumn klatki)."""
        def make():
            w, f = Worker(), Frame()
            w.char = i
            for x, pose, flip in ((1, "stoi", False), (11, "macha", True), (21, "idzie1", False)):
                w.man(f, pose, x, flip)
            return f
        return self.get(("char", i), make)


THUMBS = Thumbs()


class WebHandler(httpd.BaseHTTPRequestHandler):
    """Ścieżki dopasowujemy po końcówce, bo Ingress HA (i inne proxy) mogą dokładać prefiks – strona używa
    wyłącznie względnych adresów."""

    engine = None
    server_version = "wled-clocks"

    def log_message(self, fmt, *args):  # bez logu każdego zapytania
        pass

    def route(self):
        parts = urllib.parse.urlsplit(self.path).path.split("/")
        if len(parts) >= 3 and parts[-2] == "api":
            return "api", parts[-1]
        return "file", parts[-1] or "index.html"

    def reply(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def watch(self):
        """Ktoś patrzy: silnik liczy podgląd i stan; czeka chwilę na pierwszy."""
        e = self.engine
        e.view_until = time.monotonic() + 3
        end = time.monotonic() + 1.5
        while (e.snap is None or e.view is None) and time.monotonic() < end:
            time.sleep(0.02)

    def do_GET(self):
        kind, name = self.route()
        e = self.engine
        if kind == "file":
            if name not in WEB_FILES:
                return self.reply(404, {"error": "nie ma"})
            try:
                with open(os.path.join(WEB_DIR, name), "rb") as fh:
                    return self.reply(200, fh.read(), WEB_FILES[name])
            except OSError:
                return self.reply(500, {"error": f"brak pliku web/{name}"})
        if name == "clocks":
            return self.reply(200, {"names": e.NAMES, "docs": {n: " ".join(e.doc(n).split()) for n in e.NAMES},
                                    "categories": [{"name": c, "icon": icon, "names": names.split() + (["cykl"] if c == "Narzędzia" else [])}
                                                   for c, icon, names in CATEGORIES],
                                    "ludzik_acts": LUDZIK_ACTS, "ludzik_lvl": LUDZIK_LVL,
                                    "ludzik_timed": LUDZIK_TIMED, "ludzik_len": LUDZIK_LEN,
                                    "wled": e.wled_fx, "wled_ver": e.wled_ver})
        if name == "state":
            self.watch()
            return self.reply(200, e.snap or {})
        if name == "frame":
            self.watch()
            return self.reply(200, e.view or b"", "application/octet-stream")
        if name == "thumb":  # ?fx=nazwa – podgląd efektu, ?char=numer – postać ludzika (surowe RGB, W x H x 3)
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            fx, ch = q.get("fx", [""])[0], q.get("char", [""])[0]
            if fx in CLOCKS:
                return self.reply(200, THUMBS.effect(fx), "application/octet-stream")
            if ch.isdigit() and int(ch) < len(LUDZIK_CHARS):
                return self.reply(200, THUMBS.char(int(ch)), "application/octet-stream")
            return self.reply(404, {"error": "nie ma"})
        if name == "stream":
            return self.stream()
        self.reply(404, {"error": "nie ma"})

    def do_POST(self):
        kind, name = self.route()
        if (kind, name) != ("api", "cmd"):
            return self.reply(404, {"error": "nie ma"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > 4096:
                raise ValueError("za długie")
            fn = web_cmd(self.engine, json.loads(self.rfile.read(n) or b"{}"))
        except (ValueError, TypeError, AttributeError) as ex:
            return self.reply(400, {"ok": False, "error": str(ex)})
        self.engine.cmds.put(fn)
        self.reply(200, {"ok": True})

    def stream(self):
        """Server-Sent Events: podgląd ok. 10 razy na sekundę (base64 RGB, W x H x 3) i stan, gdy się zmieni."""
        e = self.engine
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        last_view, last_snap, ping = None, None, 0.0
        try:
            while e.running:
                e.view_until = time.monotonic() + 2
                out = []
                v, sn = e.view, e.snap
                if v is not None and v is not last_view:
                    last_view = v
                    out.append("event: frame\ndata: " + base64.b64encode(v).decode() + "\n\n")
                if sn is not None:
                    js = json.dumps(sn, ensure_ascii=False)
                    if js != last_snap:
                        last_snap = js
                        out.append("event: state\ndata: " + js + "\n\n")
                if not out and time.monotonic() > ping:
                    out.append(": ping\n\n")
                if out:
                    self.wfile.write("".join(out).encode("utf-8"))
                    self.wfile.flush()
                    ping = time.monotonic() + 15
                time.sleep(0.05)
        except OSError:  # przeglądarka zamknęła połączenie
            pass


def start_web(engine, port, bind="127.0.0.1"):
    WebHandler.engine = engine
    srv = httpd.ThreadingHTTPServer((bind, port), WebHandler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ================================================================ skrzynka na wiadomości z internetu (efekt „napisz”)
MSG_MAX = 80                 # znaków w wiadomości
MSG_BODY = 2048              # bajtów w zapytaniu
MSG_WAIT = 20                # zaległych (do akceptacji i w kolejce); więcej = „kolejka pełna”
MSG_GAP, MSG_PER, MSG_WINDOW = 20, 5, 600   # z jednego adresu: co najmniej 20 s przerwy, najwyżej 5 na 10 minut
MSG_ALL = (12, 60)           # gdy adresu nadawcy nie widać (tunel): wszystkich razem najwyżej 12 na minutę
MSG_MISSES = 10              # tyle prób pod zły adres (zły kod) i adres IP jest blokowany do następnego otwarcia
MSG_CONNS = 16               # równoczesnych połączeń; nadmiarowe są od razu zamykane
MSG_HOURS = (0.25, 24)       # na ile godzin można otworzyć skrzynkę (od–do); potem zamyka się sama
MSG_CODE = "abcdefghjkmnpqrstuvwxyz23456789"  # bez 0/o i 1/l/i – kod odczytuje się z kamerki
HTTP_METHOD = re.compile(rb"(GET|POST|HEAD|PUT|DELETE|OPTIONS|PATCH|CONNECT|TRACE) ")
# filtr celowo prosty (rdzenie słów po zdjęciu ogonków i „leetspeaku”); resztę łapie akceptacja ręczna
MSG_BAD = ["kurw", "chuj", "huj", "pierdol", "jeba", "jebi", "jebn", "pizd", "cwel", "dziwk", "szmat", "pedal",
           "fuck", "shit", "cunt", "bitch", "nigg", "fag"]
MSG_URL = re.compile(r"https?:|www\.|\b[a-z0-9-]+\.(pl|com|net|org|io|ru|xyz|info|me|eu|ly|gg|tk|co)\b", re.I)
_LEET = str.maketrans("013457@$!", "oieastasi")
MSG_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Write on the panel</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:480px;margin:40px auto;padding:0 16px;background:#111;color:#eee}}
form{{display:flex;gap:8px}}input,button{{font:inherit;padding:10px;border-radius:8px;border:1px solid #444;
background:#222;color:#eee}}input{{flex:1;min-width:0}}p{{color:#9a9ca3}}.m{{color:#ffd54f}}</style></head><body>
<h1>Write something on the panel</h1><p class="m">{msg}</p>
<form method="post" accept-charset="utf-8"><input name="message" maxlength="{max}" required autofocus
placeholder="Your message" aria-label="Your message"><button>Send</button></form>
<p>Up to {max} characters, no links. Messages show up on the panel one by one.</p></body></html>"""


def msg_clean(raw):
    """Tekst do pokazania: jedna linia, bez znaków sterujących i takich, których nie ma w czcionce (np. emoji)."""
    out = []
    for c in unicodedata.normalize("NFC", raw):
        if c.isspace() or unicodedata.category(c)[0] == "C":
            out.append(" ")
        elif c in TXT or unicodedata.normalize("NFD", c)[0] in TXT:
            out.append(c)
    return " ".join("".join(out).split())


def msg_bad(s):
    """Powód odrzucenia (link albo wulgaryzm) albo "" – „k.u.r.w.a” i „kuuurwa” też wpadają."""
    if MSG_URL.search(s):
        return "no links, please"
    folded = "".join(c for c in unicodedata.normalize("NFD", s.lower().replace("ł", "l").translate(_LEET))
                     if not unicodedata.combining(c))
    for tok in folded.split():
        w = re.sub(r"[^a-z]", "", tok)
        once = re.sub(r"(.)\1+", r"\1", w)
        if any(b in w or b in once for b in MSG_BAD):
            return "message rejected by the filter"
    return ""


class MsgServer(httpd.ThreadingHTTPServer):
    """Serwer z limitem równoczesnych połączeń (zwykły ThreadingHTTPServer tworzy wątek dla każdego)."""

    daemon_threads = True

    def __init__(self, *a):
        super().__init__(*a)
        self.slots = threading.BoundedSemaphore(MSG_CONNS)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class MsgHandler(httpd.BaseHTTPRequestHandler):
    """Z internetu da się tu zrobić tylko trzy rzeczy: GET /<kod> = formularz, POST /<kod> = wiadomość, a za tunelem
    (bez kodu) także gołe TCP: pierwszy wiersz to wiadomość (echo hi > /dev/tcp/host/port, nc)."""

    server_version, sys_version = "wled-clocks", ""
    timeout = 5  # powolni klienci są rozłączani

    def log_message(self, fmt, *args):
        pass

    def handle(self):
        try:
            head = self.connection.recv(8, socket.MSG_PEEK)
        except OSError:
            return
        if not head or HTTP_METHOD.match(head):
            return super().handle()
        self.raw()

    def raw(self):
        ip = self.ip()
        if not INBOX.check_code("", ip):  # kod w adresie da się podać tylko w HTTP
            INBOX.miss(ip)
            return
        try:
            text = self.rfile.readline(MSG_BODY + 1).decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return  # binarne śmieci (np. skanery portów) – bez odpowiedzi
        if any(unicodedata.category(c) == "Cc" and c not in "\r\n\t" for c in text):
            return
        code, reply = INBOX.submit(text, ip)
        print(f"napisz: tcp {code} {msg_clean(text)[:MSG_MAX]!r}", flush=True)
        try:
            self.wfile.write((reply + "\n").encode("utf-8"))
        except OSError:
            pass

    def ip(self):
        """Adres nadawcy; "" = nie wiadomo (za tunelem bore wszyscy przychodzą z 127.0.0.1)."""
        if INBOX.tunnel:
            return ""
        if INBOX.proxy:  # za tunelem (np. Cloudflare) prawdziwy adres jest w nagłówku – inaczej nagłówkom nie ufamy
            h = self.headers.get("CF-Connecting-IP") or (self.headers.get("X-Forwarded-For") or "").split(",")[0]
            if h.strip():
                return h.strip()[:64]
        return self.client_address[0]

    def answer(self, code, text, page=False):
        if page:
            body = MSG_PAGE.format(msg=html.escape(text), max=MSG_MAX).encode("utf-8")
            ctype = "text/html; charset=utf-8"
        else:
            body, ctype = (text + "\n").encode("utf-8"), "text/plain; charset=utf-8"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; "
                         "form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        """Czy adres jest dobry: skrzynka otwarta, kod się zgadza, nadawca niezablokowany."""
        path = urllib.parse.urlsplit(self.path).path.strip("/")
        if path in ("favicon.ico", "robots.txt"):  # przeglądarki pytają same – to nie zgadywanie kodu
            return False
        ip = self.ip()
        return INBOX.check_code(path, ip) or INBOX.miss(ip)

    def do_GET(self):
        if not self.allowed():
            return self.answer(404, "not found")
        self.answer(200, "", page=True)

    def do_POST(self):
        if not self.allowed():
            return self.answer(404, "not found")
        if self.headers.get("Transfer-Encoding"):
            return self.answer(411, "Content-Length required")
        try:
            n = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self.answer(411, "Content-Length required")
        if not 0 <= n <= MSG_BODY:
            return self.answer(413, f"too long – max {MSG_MAX} characters")
        raw = self.rfile.read(n)
        form = (self.headers.get("Content-Type", "").startswith("application/x-www-form-urlencoded")
                and raw.startswith(b"message="))
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("cp1250", "replace")  # curl z polskiego cmd w Windows
        if form:
            text = urllib.parse.parse_qs(text, max_num_fields=2).get("message", [""])[0]
        code, reply = INBOX.submit(text, self.ip())
        print(f"napisz: {self.ip() or 'http'} {code} {msg_clean(text)[:MSG_MAX]!r}", flush=True)
        self.answer(code, reply, page=form)


class Inbox:
    """Wiadomości z internetu. Serwer działa tylko, gdy skrzynka jest otwarta (zamyka się sama po czasie). Dwa tryby:
    - tunel bore (domyślny w add-onie): `bore local` wystawia serwer na publicznym bore.pub pod losowym portem –
      działa za NAT-em, bez domeny i przekierowań; port zmienia się przy każdym otwarciu i to on jest „kodem”,
      więc działa też gołe TCP; adresu nadawcy nie widać, więc limit jest wspólny dla wszystkich,
    - własny port: adres publiczny załatwia się samemu (tunel, przekierowanie), w ścieżce jest losowy kod.
    Wątki serwera dokładają wiadomości, wątek klatek je zabiera, panel WWW moderuje – stąd zamek."""

    def __init__(self):
        self.lock = threading.Lock()
        self.port, self.bind, self.public, self.proxy = None, "0.0.0.0", "", False
        self.tunnel, self.bore = "", "bore"   # serwer bore (np. bore.pub; pusty = własny port) i program bore
        self.taddr, self.proc, self.gen, self.err = "", None, 0, ""  # adres z tunelu, proces, numer otwarcia
        self.all = []                         # czasy wiadomości od nieznanych nadawców (limit wspólny)
        self.auto, self.hours = False, 2
        self.until, self.opened, self.code, self.srv = 0.0, 0.0, "", None
        self.pending, self.queue, self.shown = [], [], []
        self.hits, self.misses, self.blocked = {}, {}, set()
        self.geo = {}                         # adres nadawcy -> skąd jest (miasto, kraj), sprawdzane w tle
        self.next_id = 1

    def is_open(self):
        return self.until > time.time()

    def address(self):
        """Adres dla widzów; "" = tunel jeszcze się łączy."""
        if self.tunnel:
            return self.taddr
        return f"{self.public.rstrip('/') or f'adres:{self.port}'}/{self.code}"

    def enabled(self):
        return bool(self.tunnel or self.port)

    # ---------------------------------------------------------- sterowanie (wątek klatek)
    def open(self):
        """Otwiera skrzynkę na self.hours godzin z nowym kodem; gdy już otwarta – nowy kod i czas od teraz."""
        if not self.enabled():
            raise ValueError("skrzynka wyłączona – uruchom z --msg-tunnel bore.pub albo --msg-port")
        if self.srv is None:  # za tunelem tylko lokalnie – z internetu wchodzi się przez bore
            self.srv = MsgServer(("127.0.0.1", self.port or 0) if self.tunnel else (self.bind, self.port), MsgHandler)
            threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.stop_tunnel()
        with self.lock:
            self.code = "" if self.tunnel else "".join(secrets.choice(MSG_CODE) for _ in range(4))
            self.misses.clear()
            self.blocked.clear()
            self.opened = time.time()
            self.until = self.opened + self.hours * 3600
        if self.tunnel:
            threading.Thread(target=self.run_tunnel, args=(self.gen, self.srv.server_address[1]), daemon=True).start()
        print(f"napisz: skrzynka otwarta na {self.hours} h" + ("" if self.tunnel else f", adres {self.address()}"),
              flush=True)

    def stop_tunnel(self):
        """Nowy numer otwarcia (stary wątek tunelu się kończy) i koniec procesu bore."""
        self.gen += 1
        self.taddr = ""
        p, self.proc = self.proc, None
        if p is not None and p.poll() is None:
            p.terminate()

    def run_tunnel(self, gen, local):
        """Wątek: `bore local` i odczyt przydzielonego adresu; gdy tunel padnie – od nowa, najpierw o ten sam port."""
        want, delay = 0, 2
        while self.gen == gen and self.is_open():
            cmd = [self.bore, "local", str(local), "--local-host", "127.0.0.1", "--to", self.tunnel]
            try:
                p = subprocess.Popen(cmd + (["--port", str(want)] if want else []), stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, errors="replace")
            except OSError as e:
                self.err = f"nie mogę uruchomić bore: {e}"
                print(f"napisz: {self.err}", flush=True)
                return
            self.proc, got = p, False
            if self.gen != gen:  # zamknięta w międzyczasie
                p.terminate()
                return
            for line in p.stdout:
                line = strip_ansi(line).strip()
                m = re.search(r"listening at ([\w.\-]+):(\d+)", line)
                if m:
                    self.taddr, want, got, delay, self.err = f"{m[1]}:{m[2]}", int(m[2]), True, 2, ""
                    print(f"napisz: tunel {self.taddr}", flush=True)
                elif "ERROR" in line or "error" in line:
                    self.err = "bore: " + line[-160:]
            p.wait()
            if self.gen != gen:
                return
            self.taddr = ""
            print(f"napisz: tunel zerwany ({self.err or 'kod ' + str(p.returncode)}), łączę ponownie", flush=True)
            if not got:
                want = 0  # nie dostał portu (np. zajęty) – następnym razem dowolny
            time.sleep(delay)
            delay = min(60, delay * 2)

    def close(self):
        with self.lock:
            self.until = 0.0
        self.stop_tunnel()
        srv, self.srv = self.srv, None
        if srv:  # shutdown() czeka na pętlę serwera – nie w wątku klatek
            threading.Thread(target=lambda: (srv.shutdown(), srv.server_close()), daemon=True).start()
            print("napisz: skrzynka zamknięta", flush=True)

    def check(self):
        """Co klatkę: czas minął -> zamknij. -> True, gdy właśnie zamknięta."""
        if self.srv is not None and not self.is_open():
            self.close()
            return True
        return False

    def set_hours(self, h):
        """Na ile godzin skrzynka jest otwarta; otwarta teraz – zamknie się po tylu godzinach od otwarcia."""
        self.hours = h
        with self.lock:
            if self.until > time.time():
                self.until = self.opened + h * 3600

    def act(self, action, mid=0):
        """Moderacja z panelu WWW."""
        with self.lock:
            find = lambda *lists: next(((l, m) for l in lists for m in l if m["id"] == mid), (None, None))
            if action == "approve":
                lst, m = find(self.pending)
                if m:
                    lst.remove(m)
                    self.queue.append(m)
            elif action in ("reject", "block"):
                lst, m = find(self.pending, self.queue)
                if m:
                    lst.remove(m)
                    if action == "block" and m["ip"]:  # nadawca nieznany (tunel) – samo odrzucenie
                        self.blocked.add(m["ip"])
                        self.pending = [x for x in self.pending if x["ip"] != m["ip"]]
                        self.queue = [x for x in self.queue if x["ip"] != m["ip"]]
            elif action == "again":
                _, m = find(self.shown)
                if m and not any(x["id"] == mid for x in self.queue):
                    self.queue.append(m)
            elif action == "clear":
                self.pending.clear()
                self.queue.clear()
            else:
                raise ValueError(f"złe polecenie skrzynki {action!r}")

    def take(self):
        """Następna wiadomość do pokazania (efekt „napisz”) albo None."""
        if getattr(THUMB, "on", False):  # podgląd na liście nie zabiera wiadomości
            return None
        with self.lock:
            if not self.queue:
                return None
            m = self.queue.pop(0)
            self.shown = [x for x in self.shown if x["id"] != m["id"]][-19:] + [m]
            return m["text"]

    # ---------------------------------------------------------- z internetu (wątki serwera)
    def check_code(self, code, ip):
        with self.lock:
            ok = self.until > time.time() and ip not in self.blocked
            return ok and hmac.compare_digest(code.encode("utf-8", "replace"), self.code.encode())

    def miss(self, ip):
        """Zły adres: liczymy próby zgadnięcia kodu. -> False (żeby dało się pisać „ok or miss()”)."""
        if not ip:
            return False
        with self.lock:
            if len(self.misses) > 5000:
                self.misses.clear()
            self.misses[ip] = self.misses.get(ip, 0) + 1
            if self.misses[ip] >= MSG_MISSES:
                self.blocked.add(ip)
        return False

    def submit(self, raw, ip):
        """-> (kod HTTP, odpowiedź dla nadawcy)."""
        text, now = msg_clean(raw), time.time()
        if not text:
            return 400, "empty message (letters, digits and plain symbols – no emoji)"
        if len(text) > MSG_MAX:
            return 413, f"too long – max {MSG_MAX} characters"
        with self.lock:
            if self.until <= now or ip in self.blocked:
                return 404, "not found"
            if not ip:  # nadawcy nie widać: limit wspólny dla wszystkich
                self.all = [h for h in self.all if now - h < MSG_ALL[1]]
                if len(self.all) >= MSG_ALL[0]:
                    return 429, "too many messages right now – try again in a minute"
                self.all.append(now)
            hits = [h for h in self.hits.get(ip, []) if now - h < MSG_WINDOW] if ip else []
            if hits and now - hits[-1] < MSG_GAP:
                return 429, f"too fast – try again in {int(MSG_GAP - (now - hits[-1])) + 1} s"
            if len(hits) >= MSG_PER:
                return 429, "too many messages from your address – try again later"
            if len(self.hits) > 5000:
                self.hits = {k: v for k, v in self.hits.items() if now - v[-1] < MSG_WINDOW}
            if ip:
                self.hits[ip] = hits + [now]  # liczą się też odrzucone przez filtr – bez zgadywania słów do skutku
            why = msg_bad(text)
            if why:
                return 422, why
            if any(m["text"].casefold() == text.casefold() for m in self.pending + self.queue + self.shown[-5:]):
                return 409, "this message was already sent"
            if len(self.pending) + len(self.queue) >= MSG_WAIT:
                return 503, "queue is full – try again in a moment"
            m = {"id": self.next_id, "text": text, "ip": ip, "at": now}
            self.locate(ip)
            self.next_id += 1
            if self.auto:
                self.queue.append(m)
                return 200, f"thanks! queued: {len(self.queue)}"
            self.pending.append(m)
            return 202, "thanks! your message is waiting for approval"

    def locate(self, ip):
        """Skąd jest nadawca – w tle, z ipwho.is (wysyła tam tylko adres IP); wynik do self.geo. Pod zamkiem."""
        if not ip or ip in self.geo:
            return
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            self.geo[ip] = "?"
            return
        if not a.is_global:
            self.geo[ip] = "sieć lokalna"
            return
        if len(self.geo) > 500:
            self.geo.clear()
        self.geo[ip] = "…"

        def look():
            try:
                j = http(f"https://ipwho.is/{a}", timeout=8)
                where = ", ".join(x for x in (j.get("city"), j.get("region"), j.get("country")) if x) \
                    if j.get("success") else "?"
            except Exception:  # sieć, limit zapytań – nie wiadomo
                where = "?"
            with self.lock:
                self.geo[ip] = where or "?"
            print(f"napisz: {ip} – {where}", flush=True)

        threading.Thread(target=look, daemon=True).start()

    def snapshot(self):
        """Stan do panelu WWW (tylko typy JSON)."""
        hm = lambda ts: dtm.datetime.fromtimestamp(ts).strftime("%H:%M")
        row = lambda m: {"id": m["id"], "text": m["text"], "ip": m["ip"], "geo": self.geo.get(m["ip"], ""),
                         "at": hm(m["at"])}
        with self.lock:
            op = self.until > time.time()
            return {"enabled": self.enabled(), "open": op, "until": hm(self.until) if op else "",
                    "address": self.address() if op else "", "auto": self.auto, "hours": self.hours,
                    "tunnel": self.tunnel, "public": self.public, "blocked": len(self.blocked), "err": self.err,
                    "pending": [row(m) for m in self.pending], "queue": [row(m) for m in self.queue],
                    "shown": [row(m) for m in reversed(self.shown)]}


INBOX = Inbox()


# ================================================================ zapis podglądu (bez Pillow)
def _scaled(rows, k):
    """Wiersze pikseli powiększone k razy (każda dioda = kwadrat k x k)."""
    return [[c for c in row for _ in range(k)] for row in rows for _ in range(k)]


def save_png(path, rows, k=6):
    rows = _scaled(rows, k)
    w, h = len(rows[0]), len(rows)
    raw = b"".join(b"\0" + bytes(v for c in row for v in c) for row in rows)
    chunk = lambda t, d: len(d).to_bytes(4, "big") + t + d + zlib.crc32(t + d).to_bytes(4, "big")
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", w.to_bytes(4, "big") + h.to_bytes(4, "big") + b"\x08\x02\0\0\0")
                 + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def _palette(rows):
    """Do 256 kolorów na klatkę: wszystkie, a gdy jest ich więcej – podział „median cut” na 256 grup."""
    count = {}
    for row in rows:
        for c in row:
            count[c] = count.get(c, 0) + 1
    if len(count) <= 256:
        return list(count), {c: i for i, c in enumerate(count)}

    def box(cs):
        rng = [max(c[i] for c in cs) - min(c[i] for c in cs) for i in range(3)]
        return max(rng), rng.index(max(rng)), cs

    boxes = [box(list(count))]
    while len(boxes) < 256:
        i = max(range(len(boxes)), key=lambda j: boxes[j][0])
        r, ch, cs = boxes[i]
        if r == 0:
            break
        cs.sort(key=lambda c: c[ch])
        boxes[i:i + 1] = [box(cs[:len(cs) // 2]), box(cs[len(cs) // 2:])]
    pal, index = [], {}
    for i, (_, _, cs) in enumerate(boxes):
        n = sum(count[c] for c in cs)
        pal.append(tuple(round(sum(c[k] * count[c] for c in cs) / n) for k in range(3)))
        index.update((c, i) for c in cs)
    return pal, index


def _lzw(data, min_size):
    """Kompresja LZW obrazka GIF."""
    clear, eoi = 1 << min_size, (1 << min_size) + 1
    size, nxt, table = min_size + 1, eoi + 1, {}
    out, bits, nbits = bytearray(), 0, 0

    def emit(code):
        nonlocal bits, nbits
        bits |= code << nbits
        nbits += size
        while nbits >= 8:
            out.append(bits & 255)
            bits >>= 8
            nbits -= 8

    emit(clear)
    prefix = data[0]
    for k in data[1:]:
        key = prefix << 8 | k
        code = table.get(key)
        if code is not None:
            prefix = code
            continue
        emit(prefix)
        if nxt < 4096:
            if nxt >= 1 << size:
                size += 1
            table[key] = nxt
            nxt += 1
        else:  # słownik pełny – od nowa
            emit(clear)
            size, nxt, table = min_size + 1, eoi + 1, {}
        prefix = k
    emit(prefix)
    emit(eoi)
    if nbits:
        out.append(bits & 255)
    return bytes(out)


def save_gif(path, frames, k=6, ms=100):
    """Animowany GIF w pętli; każda klatka ma własną paletę (do 256 kolorów)."""
    w, h = len(frames[0][0]) * k, len(frames[0]) * k
    out = bytearray(b"GIF89a" + w.to_bytes(2, "little") + h.to_bytes(2, "little") + b"\0\0\0")
    out += b"\x21\xff\x0bNETSCAPE2.0\x03\x01\0\0\0"
    for rows in frames:
        pal, index = _palette(rows)
        bits = max(1, (len(pal) - 1).bit_length())
        data = [index[c] for row in _scaled(rows, k) for c in row]
        out += b"\x21\xf9\x04\0" + max(2, round(ms / 10)).to_bytes(2, "little") + b"\0\0"
        out += b"\x2c\0\0\0\0" + w.to_bytes(2, "little") + h.to_bytes(2, "little") + bytes([0x80 | (bits - 1)])
        out += bytes(v for c in pal for v in c) + bytes(3 * ((1 << bits) - len(pal)))
        lzw = _lzw(data, max(2, bits))
        out.append(max(2, bits))
        for i in range(0, len(lzw), 255):
            out += bytes([len(lzw[i:i + 255])]) + lzw[i:i + 255]
        out += b"\0"
    out += b"\x3b"
    with open(path, "wb") as fh:
        fh.write(out)


def main():
    global LAT, LON
    ap = argparse.ArgumentParser(description="Kreatywne zegary dla WLED 120x12")
    ap.add_argument("--host", help="IP panelu WLED")
    ap.add_argument("--mode", choices=list(CLOCKS) + ["cykl"], default="cykl")
    ap.add_argument("--every", type=float, default=60, help="sekundy na zegar w trybie cykl")
    ap.add_argument("--fps", type=float, default=20, help="klatki na sekundę (panel 120x12 na jednym pinie: max ~20)")
    ap.add_argument("--width", type=int, help="ile kolumn panelu działa (np. 60 dla połowy); zapamiętywane")
    ap.add_argument("--psu", type=int, help="budżet prądu zasilacza w mA (0 = bez limitu; domyślnie 2000)")
    ap.add_argument("--panel-bri", type=int, help="jasność WLED 1-255 do modelu kolorów (domyślnie odczyt z panelu)")
    ap.add_argument("--tempo", type=float, default=0.75, help="tempo animacji, np. 0.5 = dwa razy wolniej (domyślnie 0.75)")
    ap.add_argument("--text-speed", type=float, default=2.0, help="mnożnik prędkości przewijanego tekstu (domyślnie 2)")
    ap.add_argument("--speed", type=float, default=1.0, help="przyspieszenie czasu (test), np. 60")
    ap.add_argument("--start", help="udawana godzina startu HH:MM:SS (test)")
    ap.add_argument("--preview", help="zapisz animację GIF/PNG zamiast wysyłać")
    ap.add_argument("--seconds", type=float, default=6, help="długość podglądu")
    ap.add_argument("--no-tui", action="store_true", help="bez interfejsu, tylko wysyłanie (np. w tle / usłudze)")
    ap.add_argument("--web", type=int, metavar="PORT",
                    help="panel WWW na tym porcie (np. 8099); w terminalu działa razem z TUI, z --no-tui sam")
    ap.add_argument("--web-bind", default="127.0.0.1",
                    help="adres nasłuchu panelu WWW (domyślnie tylko ten komputer; 0.0.0.0 = cała sieć)")
    ap.add_argument("--odbicie", action="store_true", help="obraz odbity w poziomie, np. gdy panel ogląda się przez kamerkę")
    ap.add_argument("--bez-odbicia", dest="odbicie", action="store_false", help="wyłącz odbicie zapamiętane w ustawieniach")
    ap.set_defaults(odbicie=None)
    ap.add_argument("--msg-tunnel", metavar="SERWER", default="",
                    help="wiadomości od widzów (efekt „napisz”) przez tunel bore, np. bore.pub – za NAT-em, bez domeny")
    ap.add_argument("--msg-bore", default="bore", help="program bore (domyślnie z PATH)")
    ap.add_argument("--msg-port", type=int, metavar="PORT",
                    help="port na wiadomości od widzów; słucha tylko, gdy skrzynka jest otwarta w panelu WWW")
    ap.add_argument("--msg-bind", default="0.0.0.0", help="adres nasłuchu skrzynki (domyślnie cała sieć)")
    ap.add_argument("--msg-public", default="",
                    help="adres publiczny pokazywany na panelu, np. moj.duckdns.org:8098 (bez kodu na końcu)")
    ap.add_argument("--msg-proxy", action="store_true",
                    help="skrzynka za tunelem/proxy (np. Cloudflare): adres nadawcy z nagłówka CF-Connecting-IP / X-Forwarded-For")
    ap.add_argument("--lat", type=float, default=LAT, help="szerokość geogr. do pogody i słońca (domyślnie Warszawa)")
    ap.add_argument("--lon", type=float, default=LON, help="długość geogr.")
    ap.add_argument("--list", action="store_true", help="wypisz wszystkie efekty z opisami")
    ap.add_argument("--kalibracja", action="store_true",
                    help="wyślij na panel surowe przejścia jasności (czerwony, zielony, niebieski, biały) do sprawdzenia modelu kolorów")
    cfg = {}
    try:
        with open(CONFIG, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        pass
    ap.set_defaults(**{k: v for k, v in cfg.items() if k in ("host", "tempo", "text_speed", "fps", "every")})
    if cfg.get("mode") in list(CLOCKS) + ["cykl"]:
        ap.set_defaults(mode=cfg["mode"])
    a = ap.parse_args()
    if a.width and a.width != W:
        cfg["width"] = a.width
        try:
            os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
            with open(CONFIG, "w", encoding="utf-8") as fh:
                json.dump(cfg, fh, ensure_ascii=False, indent=1)
        except OSError:
            pass
        os.environ["WLED_W"] = str(a.width)
        os.execv(sys.executable, [sys.executable] + sys.argv)   # efekty liczą układ z szerokości przy starcie
    LAT, LON = a.lat, a.lon
    ANIM.update(fps=a.fps, tempo=a.tempo, text=a.text_speed)
    PANEL["bri"] = a.panel_bri or cfg.get("panel_bri", 255)
    PANEL["levels"] = cfg.get("panel_levels")
    PANEL["levels_bri"] = cfg.get("panel_levels_bri")
    PANEL["pe"] = cfg.get("panel_pe", 1 / 2.2)
    PANEL["mirror"] = a.odbicie if a.odbicie is not None else bool(cfg.get("mirror", False))
    LUDZIK["lvl"] = {n: int(clamp(v, 0, 3)) for n, v in (cfg.get("ludzik_lvl") or {}).items() if n in LUDZIK_ACTS}
    for n in cfg.get("ludzik_off", []):  # starszy zapis: lista wyłączonych
        if n in LUDZIK_ACTS:
            LUDZIK["lvl"].setdefault(n, 0)
    LUDZIK["len"] = {n: int(clamp(v, 0, len(LUDZIK_LEN) - 1)) for n, v in (cfg.get("ludzik_len") or {}).items()
                     if n in LUDZIK_TIMED}
    LUDZIK["freq"] = int(clamp(cfg.get("ludzik_freq", 2), 0, len(LUDZIK_FREQ) - 1))
    LUDZIK["char"] = next((i for i, (n, _) in enumerate(LUDZIK_CHARS) if n == cfg.get("ludzik_postac")), 0)
    hows = ["losowo"] + LUDZIK_HOWS
    LUDZIK["how"] = hows.index(cfg["ludzik_zmiana"]) if cfg.get("ludzik_zmiana") in hows else 0
    EYES["col"] = eye_rgb(cfg.get("oczy_kolor") or "")
    LUDZIK["side"] = LUDZIK_SIDES.index(cfg["ludzik_strona"]) if cfg.get("ludzik_strona") in LUDZIK_SIDES else 0
    CLOCK["hue"] = next((i for i, (n, _) in enumerate(CLOCK_HUES) if n == cfg.get("zegar_barwa")), 0)
    CLOCK["temp"] = cfg.get("zegar_temp") if cfg.get("zegar_temp") in CLOCK_TEMPS else 0
    CLOCK["col"] = eye_rgb(cfg.get("zegar_kolor") or "")
    CLOCK["font"] = next((i for i, (n, _) in enumerate(CLOCK_FONTS) if n == cfg.get("zegar_czcionka")), 0)
    rgb = cfg.get("led_rgb")
    if isinstance(rgb, list) and len(rgb) == 3 and all(v in COLOR_STEPS for v in rgb):
        COLOR.update(r=rgb[0], g=rgb[1], b=rgb[2])
    COLOR["fix"] = bool(cfg.get("color_fix", False))
    POWER["psu"] = a.psu if a.psu is not None else cfg.get("psu", 2000)
    POWER["auto"] = bool(cfg.get("auto_dim", True))
    INBOX.port, INBOX.bind, INBOX.public, INBOX.proxy = a.msg_port, a.msg_bind, a.msg_public.strip(), a.msg_proxy
    INBOX.tunnel, INBOX.bore = a.msg_tunnel.strip(), a.msg_bore
    INBOX.auto = bool(cfg.get("msg_auto", False))
    h = cfg.get("msg_hours")
    INBOX.hours = h if isinstance(h, (int, float)) and MSG_HOURS[0] <= h <= MSG_HOURS[1] else 2
    PANEL["ddp_w"] = W
    if a.host:
        try:
            if not a.panel_bri:
                PANEL["bri"] = http(f"http://{a.host}/json/state")["bri"]
            PANEL["ddp_w"] = max(W, http(f"http://{a.host}/json/info")["leds"]["matrix"]["w"])
        except Exception:  # noqa: BLE001
            pass
    if a.list:
        for i, (n, c) in enumerate(CLOCKS.items(), 1):
            if i == 1 or CATEGORY[n] != CATEGORY[list(CLOCKS)[i - 2]]:
                print(f"\n{CATEGORY[n]}:")
            print(f"{i:3d}. {n:12s} {' '.join((c.__doc__ or '').split())}")
        return

    if a.kalibracja:
        if not a.host:
            ap.error("podaj --host")
        # oszczędnie: jeden wiersz na kolor i co druga dioda (ok. 1/6 prądu pełnego wzoru) – słaby zasilacz
        # nie „przytnie” wtedy jasności i widać prawdziwe stopnie
        data = bytearray()
        rows = {1: (1, 0, 0), 4: (0, 1, 0), 7: (0, 0, 1), 10: (1, 1, 1)}
        for y in range(H):
            for x in range(W):
                v = round(x * 255 / (W - 1)) if y in rows and x % 2 == 0 else 0
                data += bytes(c * v for c in rows.get(y, (0, 0, 0)))
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print("Na panelu: 4 cienkie linie (czerwona, zielona, niebieska, biała), od lewej wartość 0 do 255.\n"
              f"Model: {panel_levels()} stopnie jasności, granice co ok. {W // max(1, panel_levels())} diod.\n"
              "Policz stopnie jasności w białym pasie i sprawdź, czy pierwsza dioda z lewej jest zgaszona. Ctrl+C kończy.")
        try:
            seq = 1
            while True:
                send_ddp(sock, a.host, bytes(data), seq)
                seq = seq % 15 + 1
                time.sleep(0.2)
        except KeyboardInterrupt:
            return

    interactive = not a.no_tui and sys.stdin.isatty() and sys.stdout.isatty()
    if not a.preview and (interactive or a.web):
        eng = Tui(a, cfg) if interactive else Engine(a, cfg)
        if a.web:
            try:
                start_web(eng, a.web, a.web_bind)
            except OSError as e:
                ap.error(f"nie mogę uruchomić panelu WWW na {a.web_bind}:{a.web}: {e}")
        if interactive:
            eng.run()
        else:
            print(f"panel WWW: http://{a.web_bind}:{a.web}/  (host WLED: {eng.host or 'brak – ustaw w panelu'})", flush=True)
            signal.signal(signal.SIGTERM, lambda *_: setattr(eng, "running", False))  # stop add-onu: zapisz i wyjdź
            eng.run_headless()
        if eng.new_width:
            os.environ["WLED_W"] = str(eng.new_width)
            os.execv(sys.executable, [sys.executable] + [x for x in sys.argv if not x.startswith("--width")])
        return

    clock = Cycle(a.every) if a.mode == "cykl" else CLOCKS[a.mode]()
    real0 = dtm.datetime.now().astimezone()
    base = real0
    if a.start:
        hh, mm, *ss = [int(v) for v in a.start.split(":")]
        base = real0.replace(hour=hh, minute=mm, second=ss[0] if ss else 0, microsecond=0)

    def now_at(t):
        return base + dtm.timedelta(seconds=t * a.speed)

    dt = a.tempo / a.fps
    if a.preview:
        imgs, n = [], int(a.seconds * a.fps)
        clock.draw(Frame(), now_at(0), 0, dt)   # rozgrzewka: efekt zgłasza, jakich danych z sieci potrzebuje
        NET.prefetch()
        for i in range(n):
            f = Frame()
            clock.draw(f, now_at(i * dt), i * dt, dt)
            if i % 2 == 0 or n < 3:
                imgs.append(f.rgb_rows())
        if a.preview.lower().endswith(".gif"):
            save_gif(a.preview, imgs, 6, int(2000 / a.fps))
        else:
            save_png(a.preview, imgs[-1], 6)
        return

    if not a.host:
        ap.error("podaj --host albo --preview")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    seq, t, t0, nxt = 1, 0.0, time.monotonic(), time.monotonic()
    limiter = PowerLimiter()
    try:
        wled_state(a.host, {"lor": 0})
    except Exception:  # noqa: BLE001
        pass
    while True:
        t += dt                                       # stały krok animacji – bez szarpania
        f = Frame()
        clock.draw(f, dtm.datetime.now().astimezone() + (base - real0) + dtm.timedelta(
            seconds=(time.monotonic() - t0) * (a.speed - 1)), t, dt)
        f, data = limiter.apply(f, dt)
        send_ddp(sock, a.host, data, seq)
        seq = seq % 15 + 1
        nxt += 1 / a.fps
        time.sleep(max(0, nxt - time.monotonic()))
        if nxt < time.monotonic():
            nxt = time.monotonic()


if __name__ == "__main__":
    main()
