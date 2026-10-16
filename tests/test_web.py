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
        self.assertEqual(len(wc.CLOCKS), 103)

    def test_ludzik_rides(self):
        old = dict(wc.LUDZIK["lvl"]), wc.LUDZIK["freq"]
        try:
            wc.LUDZIK["lvl"] = {a: 0 for a in wc.LUDZIK_ACTS}
            wc.LUDZIK["lvl"].update({"rower": 3, "auto": 3})
            wc.LUDZIK["freq"] = 3
            fx, rides = wc.CLOCKS["ludzik"](), set()
            base = wc.dtm.datetime(2026, 10, 16, 12, 0, 2).astimezone()
            for i in range(900):
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

    def test_plain_clock_follows_sun(self):
        noon = wc.grad(wc.DAYLIGHT, 40)
        evening = wc.grad(wc.DAYLIGHT, -2)
        night = wc.grad(wc.DAYLIGHT, -30)
        self.assertEqual(noon, (255, 255, 255))
        self.assertGreater(evening[0] - evening[2], 100)          # ciepły
        self.assertLess(sum(night), sum(evening))                   # w nocy przygaszony
        f = wc.Frame()
        wc.CLOCKS["zegar"]().draw(f, wc.dtm.datetime.now().astimezone(), 0.0, 0.05)
        self.assertTrue(any(c != (0, 0, 0) for row in f.px for c in row))

    def test_sending_off_survives_restart(self):
        e = wc.Engine(args(host="127.0.0.1"), {})
        self.assertTrue(e.sending)
        e.toggle_send()
        e.save()
        with open(wc.CONFIG, encoding="utf-8") as fh:
            cfg = json.load(fh)
        self.assertFalse(wc.Engine(args(host="127.0.0.1"), cfg).sending)
        self.assertTrue(wc.Engine(args(host="127.0.0.1"), {}).sending)  # stary plik bez "sending": wysyła

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
        names = json.loads(self.get("api/clocks")[2])["names"]
        self.assertIn("cykl", names)
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
        for c in ({"op": "inbox", "act": "open"}, {"op": "inbox", "act": "auto"}, {"op": "inbox", "act": "hours", "d": 1}):
            e.cmds.put(wc.web_cmd(e, c))
        e.tick()
        self.assertTrue(self.ib.is_open() and self.ib.auto and self.ib.hours == 4)
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
