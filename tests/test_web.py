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
