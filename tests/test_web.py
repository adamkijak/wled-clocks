"""Testy silnika i panelu WWW (tylko biblioteka standardowa): python3 -m unittest discover tests"""
import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "wled_clocks", "app")
TMP = tempfile.mkdtemp(prefix="wled_clocks_test_")
os.environ["WLED_CONFIG"] = os.path.join(TMP, "cfg.json")  # przed importem – CONFIG liczony przy starcie
os.environ["WLED_W"] = "120"
sys.path.insert(0, APP)
import wled_clocks as wc  # noqa: E402


def args(**kw):
    a = dict(host="", tempo=0.75, text_speed=2.0, fps=20, every=60, mode="zycie", speed=1.0, start=None)
    a.update(kw)
    return argparse.Namespace(**a)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class EngineTest(unittest.TestCase):
    def test_tick_and_queued_commands(self):
        e = wc.Engine(args(), {})
        e.tick()
        e.cmds.put(lambda: e.select("ogien"))
        e.cmds.put(lambda: e.setting("fps", -1))
        e.tick()
        self.assertEqual(e.mode, "ogien")
        self.assertEqual(e.fps, 15)

    def test_ludzik_first(self):
        self.assertEqual(wc.Engine.NAMES[:3], ["ludzik", "zegar", "napisz"])
        self.assertEqual(len(wc.CLOCKS), 104)

    def test_ludzik_rides(self):
        old = dict(wc.LUDZIK["lvl"]), wc.LUDZIK["freq"]
        try:
            wc.LUDZIK["lvl"] = {a: 0 for a in wc.LUDZIK_ACTS}
            wc.LUDZIK["lvl"].update({"rower": 3, "auto": 3})
            wc.LUDZIK["freq"] = 3
            fx, rides = wc.CLOCKS["ludzik"](), set()
            base = wc.dtm.datetime(2026, 10, 16, 12, 0, 2).astimezone()
            wc.random.seed(7)                                           # losowanie zajęć – powtarzalnie
            for i in range(6000):
                if rides == {"rower", "auto"}:
                    break
                t = i * 0.05
                fx.draw(wc.Frame(), base + wc.dtm.timedelta(seconds=t), t, 0.05)
                if fx.ride:
                    rides.add(fx.ride["n"])
                    self.assertTrue(-10 <= fx.x <= wc.W)
            self.assertEqual(rides, {"rower", "auto"})
            self.assertIn("auto", wc.LUDZIK_ACTS)                       # da się wyłączyć w ustawieniach
        finally:
            wc.LUDZIK["lvl"], wc.LUDZIK["freq"] = old

    def test_small_font_polish_marks(self):
        plain = set(wc.small_pl("PIATEK SRODA", 0, 1))
        pl = set(wc.small_pl("PIĄTEK ŚRODA", 0, 1))
        self.assertTrue(plain < pl)                                     # te same litery i coś więcej
        self.assertEqual({y for _, y in pl - plain}, {0, 6})            # kreska nad napisem, ogonek pod nim

    def test_plain_clock_hue_without_dimming(self):
        noon, evening, night = (wc.kelvin_rgb(wc.daylight_k(v)) for v in (40, -2, -30))
        self.assertGreater(min(noon), 245)                                  # w południe biały
        self.assertGreater(evening[0] - evening[2], 100)                    # wieczorem ciepły
        for c in (noon, evening, night):
            self.assertAlmostEqual(max(c), 255)                             # jasność tylko globalna
        now = wc.dtm.datetime.now().astimezone()
        try:
            wc.CLOCK["hue"] = [n for n, _ in wc.CLOCK_HUES].index("niebieski")
            f = wc.Frame()
            wc.CLOCKS["zegar"]().draw(f, now, 0.0, 0.05)
            self.assertEqual({c for row in f.px for c in row} - {(0, 0, 0)}, {(40, 110, 255)})
        finally:
            wc.CLOCK["hue"] = 0

    def test_clock_temperature_offset(self):
        now = wc.dtm.datetime(2026, 10, 16, 19, 0).astimezone()
        try:
            base = wc.clock_color(now)
            wc.CLOCK["temp"] = -1000
            warmer = wc.clock_color(now)
            wc.CLOCK["temp"] = 1000
            cooler = wc.clock_color(now)
            self.assertLess(warmer[2], base[2])                             # mniej niebieskiego = cieplej
            self.assertGreater(cooler[2], base[2])
            wc.CLOCK["hue"] = [n for n, _ in wc.CLOCK_HUES].index("biały")  # stały kolor: balans bieli
            self.assertGreater(wc.clock_color(now)[2], wc.clock_color(now)[0] - 30)
            wc.CLOCK["temp"] = -2000
            self.assertLess(wc.clock_color(now)[2], 200)
            e = wc.Engine(args(mode="zegar"), {})
            self.assertIn("temperatura", [st[0] for st in e.shown_settings()])
            e.setting("temperatura", 1)
            self.assertEqual(wc.CLOCK["temp"], -1500)
        finally:
            wc.CLOCK.update(hue=0, temp=0)

    def test_settings_only_for_current_effect(self):
        e = wc.Engine(args(mode="zegar"), {})
        names = lambda: [st[0] for st in e.shown_settings()]
        self.assertIn("barwa", names())
        self.assertNotIn("ludzik zajęcia", names())
        self.assertEqual(names()[0], "jasność WLED")                       # wspólne na górze
        e.select("ludzik")
        self.assertIn("ludzik co ile", names())
        self.assertNotIn("barwa", names())
        e.select("cykl")
        self.assertIn("cykl co", names())
        e.setting("barwa", 1)
        self.assertEqual(wc.CLOCK_HUES[wc.CLOCK["hue"]][0], "biały")
        e.save()
        with open(wc.CONFIG, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["zegar_barwa"], "biały")
        wc.CLOCK["hue"] = 0
        e.view_until = time.monotonic() + 1
        e.tick()
        self.assertIn("cykl", e.snap["setting_fx"])
        self.assertEqual({x["name"]: x["fx"] for x in e.snap["settings"]}["barwa"], "zegar")

    def test_sending_off_survives_restart(self):
        e = wc.Engine(args(host="127.0.0.1"), {})
        self.assertTrue(e.sending)
        e.toggle_send()
        e.save()
        with open(wc.CONFIG, encoding="utf-8") as fh:
            cfg = json.load(fh)
        self.assertFalse(wc.Engine(args(host="127.0.0.1"), cfg).sending)
        self.assertTrue(wc.Engine(args(host="127.0.0.1"), {}).sending)  # stary plik bez "sending": wysyła

    def test_text_speed_hint(self):
        e = wc.Engine(args(fps=15, tempo=1.0, text_speed=0.33), {})
        self.assertEqual(e.text_step(), "napisy 1 px co 2 klatki, transparent ludzika 1 px co 3 klatki – skacze; "
                                        "płynnie od x0.67")
        e.text = 0.67
        self.assertNotIn("skacze", e.text_step())
        e.fps, e.text = 60, 0.25
        self.assertIn("co 8 klatek", e.text_step())

    def test_auto_dim_switch(self):
        old = dict(wc.POWER)
        try:
            wc.POWER.update(psu=1000, auto=True)
            f = wc.Frame((255, 255, 255))                                       # cały panel na biało: kilkadziesiąt A
            lim = wc.PowerLimiter()
            lim.apply(f, 0.05)
            self.assertLess(lim.k, 0.5)                                          # przyciemnia
            e = wc.Engine(args(), {})
            e.setting("auto przyciemnianie", 1)
            self.assertFalse(wc.POWER["auto"])
            lim = wc.PowerLimiter()
            out, _ = lim.apply(f, 0.05)
            self.assertEqual((lim.k, out), (1.0, f))                             # pełna jasność
            e.save()
            with open(wc.CONFIG, encoding="utf-8") as fh:
                self.assertFalse(json.load(fh)["auto_dim"])
        finally:
            wc.POWER.clear()
            wc.POWER.update(old)

    def test_settings_pick_from_list(self):
        """Suwaki i listy w panelu WWW: każde ustawienie z listą da się ustawić na każdą jej wartość."""
        saved = dict(wc.PANEL), dict(wc.POWER), dict(wc.CLOCK), dict(wc.LUDZIK)
        try:
            e = wc.Engine(args(), {})
            e.set_wled_bri = lambda v: None                                 # bez hosta – nic nie wysyłamy
            for name in e.choices:
                if name in ("szerokość", "wysyłanie"):                     # restart skryptu / wymaga hosta
                    continue
                vals, _ = e.choice(name)
                for i in (len(vals) - 1, 0):
                    e.pick(name, i)
                    self.assertEqual(e.choice(name)[1], i, name)
            e.cmds.put(wc.web_cmd(e, {"op": "setting", "name": "barwa", "i": 8}))
            e.cmds.put(wc.web_cmd(e, {"op": "setting", "name": "fps", "i": 2}))
            e.view_until = time.monotonic() + 1
            e.tick()
            self.assertEqual((wc.CLOCK_HUES[wc.CLOCK["hue"]][0], e.fps), ("niebieski", 15))
            row = {x["name"]: x for x in e.snap["settings"]}
            self.assertEqual((row["fps"]["kind"], row["fps"]["labels"][row["fps"]["index"]]), ("range", "15"))
            self.assertEqual(row["barwa"]["kind"], "list")
            self.assertNotIn("kind", row["host"])                           # pole tekstowe, nie lista
            for bad in ({"op": "setting", "name": "fps", "i": 99}, {"op": "setting", "name": "host", "i": 0}):
                with self.assertRaises(ValueError, msg=bad):
                    wc.web_cmd(e, bad)
        finally:
            for d, old in zip((wc.PANEL, wc.POWER, wc.CLOCK, wc.LUDZIK), saved):
                d.clear()
                d.update(old)

    def test_preview_like_ws2812(self):
        """Podgląd = barwy diod: czerwony z odrobiną zielonego jest na diodach czerwieńszy niż na ekranie, biel
        niebieskawa; „popraw kolory” wysyła tak, żeby panel wyglądał jak zamierzony kolor."""
        import colorsys
        hue = lambda c: colorsys.rgb_to_hsv(*[v / 255 for v in c])[0] * 360
        saved = dict(wc.PANEL), dict(wc.COLOR)
        try:
            wc.PANEL.update(bri=24, levels=None)
            orange, white = (255, 120, 0), (255, 255, 255)
            view = lambda c: wc.panel_view([[c]])[0][0]
            self.assertLess(hue(view(orange)), hue(orange) - 5)            # na diodach czerwieńszy
            self.assertEqual(view((255, 0, 0)), (255, 0, 0))
            w = view(white)
            self.assertGreater(w[2], w[0])                                  # biel WS2812 – niebieskawa
            self.assertEqual(view((0, 0, 0)), (0, 0, 0))
            wc.COLOR["fix"] = True
            self.assertLess(abs(hue(view(orange)) - hue(orange)), 8)        # po poprawce ≈ zamierzony (24 poziomy)
            w = view(white)
            self.assertLess(max(w) - min(w), 25)                            # biel neutralna
            f = wc.Frame(orange)
            wc.COLOR["fix"] = False
            raw = f.to_bytes()
            wc.COLOR["fix"] = True
            self.assertNotEqual(f.to_bytes(), raw)                          # wysyłamy co innego
            wc.COLOR["fix"] = False
            before = hue(view(orange))
            wc.COLOR["g"] = 0.5                                             # kalibracja: słabsza zieleń
            self.assertLess(hue(view(orange)), before)                      # -> pomarańczowy czerwieńszy
            e = wc.Engine(args(mode="kolory"), {})
            self.assertIn("diody: zielony", [st[0] for st in e.shown_settings()])
            e.pick("diody: zielony", 0)
            e.setting("popraw kolory", 1)
            e.save()
            with open(wc.CONFIG, encoding="utf-8") as fh:
                cfg = json.load(fh)
            self.assertEqual((cfg["led_rgb"][1], cfg["color_fix"]), (0.5, True))
        finally:
            for dct, old in zip((wc.PANEL, wc.COLOR), saved):
                dct.clear()
                dct.update(old)

    def test_wled16_brightness_model(self):
        """Arytmetyka color_fade(video) z WLED 16 i stały odcień na panelu przy różnych jasnościach."""
        import colorsys
        self.assertEqual(wc.wled_fade((255, 120, 0), 4), (5, 3, 0))           # +1 tylko > 25% najsilniejszego
        self.assertEqual(wc.wled_fade((255, 40, 0), 24), (25, 4, 0))
        self.assertEqual(wc.wled_fade((255, 120, 0), 255), (255, 120, 0))
        hue = lambda c: colorsys.rgb_to_hsv(*c)[0] * 360
        for c in ((255, 120, 0), (255, 200, 0), (0, 200, 255)):
            hues = []
            for bri in (4, 8, 16, 24, 64, 128, 255):
                o = wc.wled_fade(wc.send_color(c, bri), bri)
                hues.append(hue([(x / wc.wled_top(bri)) ** (1 / 2.2) for x in o]))
            self.assertLess(max(hues) - min(hues), 10, (c, hues))                # kolor nie zależy od jasności

    def test_view_only_when_watched(self):
        e = wc.Engine(args(), {})
        e.tick()
        self.assertIsNone(e.view)
        e.view_until = time.monotonic() + 1
        e.tick()
        self.assertEqual(len(e.view), wc.W * wc.H * 3)
        self.assertEqual(e.snap["mode"], "zycie")
        json.dumps(e.snap)  # stan musi dać się wysłać jako JSON

    def test_bad_commands_rejected(self):
        e = wc.Engine(args(), {})
        for c in ({"op": "select", "name": "nie_ma"}, {"op": "setting", "name": "x"}, {"op": "host", "host": "a; rm"},
                  {"op": "ludzik", "act": "spacer", "lvl": 7}, {"op": "boom"}):
            with self.assertRaises(ValueError, msg=c):
                wc.web_cmd(e, c)

    def test_tui_keys_use_engine_actions(self):
        t = wc.Tui(args(), {})
        t.on_key("s")                  # bez hosta: otwiera pole wpisywania
        self.assertEqual(t.edit, "")
        for k in "192.168.1.5\r":
            t.on_key(k)
        self.assertEqual((t.host, t.sending, t.edit), ("192.168.1.5", True, None))
        t.on_key(" ")
        self.assertTrue(t.paused)
        t.on_key("right")
        self.assertNotEqual(t.mode, "zycie")


class WebTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = wc.Engine(args(), {})
        cls.srv = wc.start_web(cls.e, 0)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}/api/hassio_ingress/token/"  # prefiks jak w Ingress
        cls.loop = threading.Thread(target=cls.e.run_headless, daemon=True)
        cls.loop.start()

    @classmethod
    def tearDownClass(cls):
        cls.e.running = False
        cls.loop.join(5)
        cls.srv.shutdown()
        cls.srv.server_close()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as r:
            return r.status, r.headers.get("Content-Type"), r.read()

    def post(self, body):
        req = urllib.request.Request(self.base + "api/cmd", data=json.dumps(body).encode(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as ex:
            return ex.code, json.loads(ex.read())

    def test_static_files_under_prefix(self):
        st, ct, body = self.get("")
        self.assertEqual(st, 200)
        self.assertIn("text/html", ct)
        self.assertNotIn(b'src="/', body)   # tylko względne adresy
        self.assertNotIn(b'href="/', body)
        for f in ("app.js", "style.css"):
            self.assertEqual(self.get(f)[0], 200)
        with self.assertRaises(urllib.error.HTTPError):
            self.get("../wled_clocks.py")

    def test_clocks_state_frame(self):
        clocks = json.loads(self.get("api/clocks")[2])
        names = clocks["names"]
        self.assertIn("cykl", names)
        in_cats = [n for c in clocks["categories"] for n in c["names"]]
        self.assertEqual(sorted(in_cats), sorted(names))                    # każdy efekt w dokładnie jednej kategorii
        self.assertEqual([n for n in in_cats if n != "cykl"], names[:-1])  # kolejność listy = kolejność kategorii
        state = json.loads(self.get("api/state")[2])
        self.assertIn("settings", state)
        self.assertEqual(len(self.get("api/frame")[2]), wc.W * wc.H * 3)

    def test_command_changes_state(self):
        self.assertEqual(self.post({"op": "select", "name": "matrix"}), (200, {"ok": True}))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and json.loads(self.get("api/state")[2]).get("mode") != "matrix":
            time.sleep(0.1)
        self.assertEqual(json.loads(self.get("api/state")[2])["mode"], "matrix")
        st, j = self.post({"op": "select", "name": "nie_ma"})
        self.assertEqual((st, j["ok"]), (400, False))

    def test_sse_stream(self):
        with urllib.request.urlopen(self.base + "api/stream", timeout=5) as r:
            self.assertIn("text/event-stream", r.headers.get("Content-Type"))
            seen = set()
            deadline = time.monotonic() + 4
            while seen != {"frame", "state"} and time.monotonic() < deadline:
                line = r.readline().decode()
                if line.startswith("event: "):
                    seen.add(line[7:].strip())
        self.assertEqual(seen, {"frame", "state"})


class WledEffectsTest(unittest.TestCase):
    """Efekty wbudowane w WLED: udawany WLED (lista efektów, cechy, polecenia POST /json/state)."""

    def setUp(self):
        self.posted = posted = []
        self.wled = wled = {"on": True}

        class Fake(wc.httpd.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                body = {"/json/eff": ["Solid", "Blink", "RSVD", "Fire 2012"],
                        "/json/fxdata": ["", "!,Duty cycle;!,!;!;01", "", "Cooling,Spark rate,,2D Blur,,Boost;;!;2v"],
                        "/json/pal": ["Default", "Party", "Lava"],
                        "/json/state": {"on": wled["on"], "bri": wc.PANEL["bri"], "mainseg": 0, "lor": 0,
                                        "seg": [{"id": 0, "fx": 3, "sx": 64, "ix": 160, "c1": 128, "c2": 128,
                                                 "c3": 16, "o1": False, "o2": False, "o3": False, "pal": 2,
                                                 "col": [[255, 0, 0], [0, 0, 0], [0, 0, 0]]}]}}.get(self.path)
                data = json.dumps(body).encode()
                self.send_response(200 if body is not None else 404)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                posted.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                wled["on"] = posted[-1].get("on", wled["on"])
                self.do_GET()

        self.srv = wc.httpd.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.host = f"127.0.0.1:{self.srv.server_address[1]}"
        self.old = dict(wc.PANEL)

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        wc.PANEL.clear()
        wc.PANEL.update(self.old)

    def wait(self, cond):
        deadline = time.monotonic() + 5
        while not cond() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(cond())

    def test_switch_off_is_absolute(self):
        """Wyłączony WLED (np. przyciskiem dzwonkowym) – ani jednej klatki DDP, bo każda by go zapaliła."""
        sent, old = [], (wc.send_ddp, wc.Engine.WATCH_EVERY)
        wc.send_ddp, wc.Engine.WATCH_EVERY = (lambda *a: sent.append(1)), 0.05
        engines = []
        try:
            unknown = wc.Engine(args(host="127.0.0.1:9", mode="zegar"), {})  # WLED nie odpowiada – stan nieznany
            e = wc.Engine(args(host=self.host, mode="zegar"), {})
            engines += [unknown, e]
            unknown.tick()
            self.assertEqual(sent, [])
            self.wait(lambda: (e.tick(), e.wled_on)[1])
            self.assertTrue(sent)
            self.wled["on"] = False                                         # przycisk: wyłącz
            self.wait(lambda: (e.tick(), e.wled_on is False)[1])
            sent.clear()
            for _ in range(5):
                e.tick()
            self.assertEqual(sent, [])
            self.assertEqual(e.snapshot(e.tick()[1])["wled_on"], False)
            self.wait(lambda: {"live": False} in self.posted)                # od razu koniec realtime – gaśnie
            e.set_wled_bri(64)                                              # jasność bez zapalania
            self.wait(lambda: {"bri": 64, "on": False} in self.posted)
            e.select("wled:3")
            self.wait(lambda: any("seg" in p and p["seg"][0].get("fx") == 3 for p in self.posted))
            self.assertFalse(any("on" in p and p["on"] for p in self.posted))  # nic nie zapala WLED
            e.select("zegar")
            self.wled["on"] = True                                          # przycisk: włącz
            self.wait(lambda: (e.tick(), e.wled_on)[1])
            e.tick()
            self.assertTrue(sent)
        finally:
            for x in engines:
                x.running = False
            wc.send_ddp, wc.Engine.WATCH_EVERY = old

    def test_power_button(self):
        """Przycisk ⏻ w panelu włącza i wyłącza WLED; po wyłączeniu ani jednej klatki, nawet ze stanem sprzed kliknięcia."""
        sent, old = [], (wc.send_ddp, wc.Engine.WATCH_EVERY)
        wc.send_ddp, wc.Engine.WATCH_EVERY = (lambda *a: sent.append(1)), 0.05
        e = wc.Engine(args(host=self.host, mode="zegar"), {})
        try:
            self.wait(lambda: (e.tick(), e.wled_on)[1])
            stale = e.wled_st                                               # „on”: true sprzed kliknięcia
            e.cmds.put(wc.web_cmd(e, {"op": "power"}))
            e.tick()
            self.assertIs(e.wled_on, False)
            self.wait(lambda: {"on": False} in self.posted and not self.wled["on"])
            e.wled_st = dict(stale)                                         # spóźniona odpowiedź WLED
            sent.clear()
            for _ in range(5):
                e.tick()
            self.assertEqual(sent, [])
            self.assertIs(e.wled_on, False)
            e.cmds.put(wc.web_cmd(e, {"op": "power"}))
            e.tick()
            self.assertTrue(e.wled_on)
            self.wait(lambda: {"on": True} in self.posted and self.wled["on"])
            e.tick()
            self.assertTrue(sent)
            self.wled["on"] = False                                         # potem przycisk w WLED – wygrywa on
            self.wait(lambda: (e.tick(), e.wled_on is False)[1])
        finally:
            e.running = False
            wc.send_ddp, wc.Engine.WATCH_EVERY = old

    def test_wled_effects(self):
        e = wc.Engine(args(host=self.host), {})
        self.wait(lambda: e.wled_fx)
        self.assertEqual([(x["id"], x["name"], x["tags"]) for x in e.wled_fx],
                         [(0, "Solid", ""), (1, "Blink", ""), (3, "Fire 2012", "2D ♪")])  # bez RSVD
        sent = []
        e.send = sent.append
        e.cmds.put(wc.web_cmd(e, {"op": "select", "name": "wled:3"}))
        e.tick()
        self.assertEqual(e.mode, "wled:3")
        self.assertEqual(sent, [])                                          # WLED gra sam – nic nie wysyłamy
        self.wait(lambda: {"live": False, "seg": [{"id": 0, "fx": 3, "fxdef": True}]} in self.posted)
        self.wait(lambda: e.wled_seg.get("fx") == 3)                       # parametry segmentu z WLED
        ws = e.wled_snapshot()
        self.assertEqual([(it["key"], it["label"], it["value"]) for it in ws["items"]],
                         [("sx", "Cooling", 64), ("ix", "Spark rate", 160), ("c2", "2D Blur", 128),
                          ("o1", "Boost", False), ("pal", "paleta", 2)])        # c1 i kolory – efekt ich nie używa
        self.posted.clear()
        e.cmds.put(wc.web_cmd(e, {"op": "wled", "key": "sx", "v": 200}))
        e.cmds.put(wc.web_cmd(e, {"op": "wled", "key": "o1", "v": True}))
        e.tick()
        self.wait(lambda: {"seg": [{"id": 0, "sx": 200}]} in self.posted and {"seg": [{"id": 0, "o1": True}]} in self.posted)
        for bad in ({"op": "wled", "key": "sx", "v": 300}, {"op": "wled", "key": "c1", "v": 1},
                    {"op": "wled", "key": "pal", "v": 9}):
            with self.assertRaises(ValueError, msg=bad):
                wc.web_cmd(e, bad)
        e.select("wled:1")
        e.select("wled:3")                                                  # powrót: zapamiętane, bez fxdef
        self.wait(lambda: {"live": False, "seg": [{"id": 0, "fx": 3, "sx": 200, "o1": True}]} in self.posted)
        e.select("wled:1")
        self.assertEqual([it["key"] for it in e.wled_snapshot()["items"]], ["sx", "ix", "pal", "col0", "col1"])
        e.select("wled:3")
        self.assertIn("WLED", e.doc("wled:3"))
        e.skip(1)                                                           # ← → po efektach WLED
        self.assertEqual(e.mode, "wled:0")
        with self.assertRaises(ValueError):
            wc.web_cmd(e, {"op": "select", "name": "wled:2"})               # RSVD – nie ma
        e.save()
        with open(wc.CONFIG, encoding="utf-8") as fh:
            cfg = json.load(fh)
        restart = wc.Engine(args(host=self.host, mode="cykl"), cfg)          # jak main(): bez --mode = domyślny cykl
        self.assertEqual(restart.mode, "wled:0")                            # zostaje po restarcie
        self.posted.clear()
        e.select("zegar")                                                   # z powrotem do naszego strumienia
        e.tick()
        self.assertEqual(len(sent), 1)
        self.wait(lambda: {"lor": 0} in self.posted)


class InboxTest(unittest.TestCase):
    """Skrzynka na wiadomości z internetu (efekt „napisz”): prawdziwy serwer na wolnym porcie."""

    def setUp(self):
        self.old = wc.INBOX
        wc.INBOX = self.ib = wc.Inbox()
        self.ib.port, self.ib.bind = free_port(), "127.0.0.1"

    def tearDown(self):
        self.ib.close()
        wc.INBOX = self.old

    def send(self, path, text=None, form=False, ip=None):
        data = None if text is None else (urllib.parse.urlencode({"message": text}) if form else text).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.ib.port}/{path}", data=data,
                                     headers={"X-Forwarded-For": ip} if ip else {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as ex:
            return ex.code, ex.read().decode()

    def test_clean_and_filter(self):
        self.assertEqual(wc.msg_clean("  hej\tświat 👋\x00!\n"), "hej świat !")
        for bad in ("k.u.r.w.a", "kuuurwa mać", "CHUJ", "zobacz www.example.com", "http://x", "wejdź na abc.pl"):
            self.assertTrue(wc.msg_bad(bad), bad)
        for ok in ("Cześć Adam, pozdrawiam!", "ach ujęcie", "2+2=4", "o 15:30 przerwa"):
            self.assertEqual(wc.msg_bad(ok), "", ok)

    def test_port_listens_only_while_open(self):
        with self.assertRaises(urllib.error.URLError):
            self.send("x")
        self.ib.open()
        self.assertEqual(self.send(self.ib.code)[0], 200)
        self.ib.until = time.time() - 1          # czas minął
        self.assertTrue(self.ib.check())
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                self.send(self.ib.code)
                time.sleep(0.1)
            except OSError:  # odmowa połączenia (albo reset w trakcie zamykania)
                break
        with self.assertRaises(OSError):
            self.send(self.ib.code)

    def test_manual_flow(self):
        self.ib.open()
        code = self.ib.code
        self.assertEqual(len(code), 4)
        self.assertEqual(self.send("zly")[0], 404)
        st, page = self.send(code)
        self.assertEqual(st, 200)
        self.assertIn('name="message"', page)
        self.assertEqual(self.send(code, "Cześć z calla!")[0], 202)
        self.assertEqual(self.send(code, "i jeszcze")[0], 429)      # za szybko z tego samego adresu
        self.assertIsNone(self.ib.take())                           # czeka na akceptację
        mid = self.ib.snapshot()["pending"][0]["id"]
        self.ib.act("approve", mid)
        self.assertEqual(self.ib.take(), "Cześć z calla!")
        self.assertEqual(self.ib.snapshot()["shown"][0]["text"], "Cześć z calla!")
        self.ib.act("again", mid)
        self.assertEqual(self.ib.take(), "Cześć z calla!")
        json.dumps(self.ib.snapshot())

    def test_limits_auto_and_block(self):
        self.ib.auto, self.ib.proxy = True, True    # za tunelem: adres nadawcy z nagłówka
        self.ib.open()
        code = self.ib.code
        self.assertEqual(self.send(code, "x" * (wc.MSG_MAX + 1), ip="1.1.1.1")[0], 413)
        self.assertEqual(self.send(code, "kurwa", ip="1.1.1.2")[0], 422)
        self.assertEqual(self.send(code, "hej", ip="1.1.1.3")[0], 200)
        self.assertEqual(self.send(code, "HEJ", ip="1.1.1.4")[0], 409)          # duplikat
        st, page = self.send(code, "z formularza", form=True, ip="1.1.1.5")
        self.assertEqual(st, 200)
        self.assertIn("queued: 2", page)
        self.assertEqual([m["text"] for m in self.ib.snapshot()["queue"]], ["hej", "z formularza"])
        mid = self.ib.snapshot()["queue"][0]["id"]
        self.ib.act("block", mid)                                               # ⛔ – nadawca znika i nie wróci
        self.assertEqual(self.send(code, "znowu ja", ip="1.1.1.3")[0], 404)
        for _ in range(wc.MSG_MISSES):                                          # zgadywanie kodu
            self.send("zgaduje", ip="2.2.2.2")
        self.assertEqual(self.send(code, "trafiłem", ip="2.2.2.2")[0], 404)
        self.ib.open()                                                          # nowe otwarcie: nowy kod, czysto
        self.assertNotEqual(self.ib.code, code)
        self.assertEqual(self.send(self.ib.code, "teraz ok", ip="2.2.2.2")[0], 200)

    def test_bore_tunnel(self):
        """Tunel bore (udawany: wypisuje adres jak prawdziwy i czeka): port jest kodem, działa gołe TCP."""
        fake = os.path.join(TMP, "fake_bore")
        args_log = os.path.join(TMP, "fake_bore.args")
        with open(fake, "w") as fh:
            fh.write(f"#!{sys.executable}\nimport sys, time\nopen({args_log!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
                     "print('\\x1b[2m2026\\x1b[0m INFO bore_cli::client: listening at bore.pub:22696', flush=True)\n"
                     "time.sleep(60)\n")
        os.chmod(fake, 0o755)
        self.ib.port, self.ib.tunnel, self.ib.bore = None, "bore.pub", fake
        self.ib.open()
        deadline = time.monotonic() + 5
        while not self.ib.address() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(self.ib.address(), "bore.pub:22696")
        local = self.ib.srv.server_address
        self.assertEqual(local[0], "127.0.0.1")                                  # z internetu tylko przez tunel
        with open(args_log) as fh:
            self.assertIn(f"local {local[1]} --local-host 127.0.0.1 --to bore.pub", fh.read())
        self.ib.port = local[1]
        with socket.create_connection(local, timeout=5) as c:                   # echo hi > /dev/tcp/...
            c.sendall("cześć z basha\n".encode())
            self.assertIn("waiting for approval", c.makefile().readline())
        with socket.create_connection(local, timeout=5) as c:                   # binarne śmieci: cisza
            c.sendall(b"\x16\x03\x01\x00\xa5")
            c.shutdown(socket.SHUT_WR)
            self.assertEqual(c.recv(100), b"")
        self.assertEqual(self.send("", "z curla")[0], 202)                      # HTTP pod "/"
        self.assertEqual(self.send("cokolwiek", "x")[0], 404)
        p = self.ib.snapshot()["pending"]
        self.assertEqual([(m["text"], m["ip"]) for m in p], [("cześć z basha", ""), ("z curla", "")])
        self.ib.act("block", p[0]["id"])                                        # bez adresu: samo odrzucenie
        self.assertEqual(self.ib.blocked, set())
        for i in range(wc.MSG_ALL[0]):                                          # limit wspólny
            self.send("", f"wiadomość {i}")
        self.assertEqual(self.send("", "o jedną za dużo")[0], 429)
        proc = self.ib.proc
        self.ib.close()
        self.assertEqual(proc.wait(5), -signal.SIGTERM)                         # tunel znika razem ze skrzynką

    def test_effect_and_engine(self):
        e = wc.Engine(args(), {})
        self.assertFalse(e.cycle.allowed("napisz"))                             # zamknięta: nie w cyklu
        for c in ({"op": "inbox", "act": "open"}, {"op": "inbox", "act": "auto"}, {"op": "inbox", "act": "hours", "v": 3.5}):
            e.cmds.put(wc.web_cmd(e, c))
        e.tick()
        self.assertTrue(self.ib.is_open() and self.ib.auto and self.ib.hours == 3.5)
        self.assertAlmostEqual(self.ib.until - self.ib.opened, 3.5 * 3600)   # otwarta: czas liczony od otwarcia
        for bad in (0, 0.1, 25, "abc"):
            with self.assertRaises(ValueError):
                wc.web_cmd(e, {"op": "inbox", "act": "hours", "v": bad})
        self.assertTrue(e.cycle.allowed("napisz"))
        with self.assertRaises(ValueError):
            wc.web_cmd(e, {"op": "inbox", "act": "rm"})
        fx = wc.CLOCKS["napisz"]()
        now = wc.dtm.datetime.now().astimezone()
        f = wc.Frame()
        fx.draw(f, now, 0.0, 0.05)                                               # zachęta z adresem
        self.assertTrue(any(c != (0, 0, 0) for row in f.px for c in row))
        self.assertEqual(self.send(self.ib.code, "Zażółć gęślą jaźń")[0], 200)
        fx.draw(wc.Frame(), now, 1.0, 0.05)
        self.assertEqual(fx.cur, "Zażółć gęślą jaźń")
        self.assertIsNone(self.ib.take())


class HeadlessProcessTest(unittest.TestCase):
    def test_sigterm_saves_settings(self):
        cfg = os.path.join(TMP, "proc.json")
        port = free_port()
        env = dict(os.environ, WLED_CONFIG=cfg)
        p = subprocess.Popen([sys.executable, os.path.join(APP, "wled_clocks.py"), "--web", str(port), "--no-tui",
                              "--mode", "pong"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            base = f"http://127.0.0.1:{port}/"
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                try:
                    urllib.request.urlopen(base, timeout=1).read()
                    break
                except OSError:
                    time.sleep(0.2)
            req = urllib.request.Request(base + "api/cmd", data=b'{"op":"select","name":"tecza"}', method="POST")
            urllib.request.urlopen(req, timeout=5).read()
            time.sleep(0.5)
            p.send_signal(signal.SIGTERM)
            self.assertEqual(p.wait(10), 0)
        finally:
            if p.poll() is None:
                p.kill()
            p.stdout.close()
        with open(cfg, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["mode"], "tecza")


if __name__ == "__main__":
    unittest.main()
