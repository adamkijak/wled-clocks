"use strict";
// Panel WWW dla wled_clocks.py. Wszystkie adresy są względne (Ingress Home Assistant dokłada prefiks).

const $ = (s) => document.querySelector(s);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};
// małe litery bez polskich znaków – „glowie” pasuje do „głowie” (jak w TUI)
const fold = (s) => s.toLowerCase().replace(/ł/g, "l").normalize("NFD").replace(/[̀-ͯ]/g, "");

const HIDDEN_SETTINGS = new Set(["podgląd"]); // podgląd w terminalu – w przeglądarce bez znaczenia
let clocks = null;
let state = null;
let listKey = "";

// ------------------------------------------------------------ polecenia
async function cmd(op, extra = {}) {
  try {
    const r = await fetch("api/cmd", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ op, ...extra }),
    });
    const j = await r.json();
    if (!j.ok) toast(j.error || "błąd");
  } catch (e) {
    toast("brak połączenia ze skryptem");
  }
}

let toastTimer = 0;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 3000);
}

// ------------------------------------------------------------ podgląd panelu
const canvas = $("#panel");
const ctx = canvas.getContext("2d");
let lastFrame = null;

function drawFrame(bytes) {
  lastFrame = bytes;
  const W = state ? state.w : bytes.length / 36;
  const H = state ? state.h : 12;
  const cssW = canvas.clientWidth || 600;
  const cell = (cssW / W) * (window.devicePixelRatio || 1);
  const cw = Math.round(cell * W);
  const ch = Math.round(cell * H);
  if (canvas.width !== cw || canvas.height !== ch) {
    canvas.width = cw;
    canvas.height = ch;
  }
  ctx.fillStyle = "#0b0b0e";
  ctx.fillRect(0, 0, cw, ch);
  const r = cell * 0.4;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const i = (y * W + x) * 3;
      const R = bytes[i], G = bytes[i + 1], B = bytes[i + 2];
      ctx.fillStyle = R || G || B ? `rgb(${R},${G},${B})` : "#222226";
      ctx.beginPath();
      ctx.arc((x + 0.5) * cell, (y + 0.5) * cell, R || G || B ? r : r * 0.45, 0, 6.2832);
      ctx.fill();
    }
  }
}
window.addEventListener("resize", () => lastFrame && drawFrame(lastFrame));

function b64bytes(s) {
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

// ------------------------------------------------------------ lista efektów
function renderList() {
  const q = fold($("#search").value.trim());
  const heavy = new Set(state ? state.heavy : []);
  const key = [q, state && state.mode, state && state.current, [...heavy].join()].join("|");
  if (key === listKey) return;
  listKey = key;
  const ol = $("#list");
  ol.textContent = "";
  clocks.names.forEach((name, i) => {
    const doc = clocks.docs[name] || "";
    if (q && !fold(name).includes(q) && !fold(doc).includes(q)) return;
    const li = el("li");
    if (state && name === state.mode) li.classList.add("sel");
    else if (state && state.mode === "cykl" && name === state.current) li.classList.add("incycle");
    li.append(el("span", "n", String(i + 1)), el("span", "name", name), el("span", "heavy", heavy.has(name) ? "⚡" : ""));
    li.append(el("span", "d", doc));
    li.title = doc;
    li.onclick = () => cmd("select", { name });
    ol.append(li);
  });
  const sel = ol.querySelector("li.sel, li.incycle");
  if (sel && !q) ol.scrollTop = sel.offsetTop - ol.offsetTop - ol.clientHeight / 2 + sel.offsetHeight / 2;
}
$("#search").addEventListener("input", renderList);
$("#search").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const first = $("#list li");
    if (first) first.click();
  } else if (e.key === "Escape") {
    e.target.value = "";
    renderList();
  }
});

// ------------------------------------------------------------ ustawienia
const rows = new Map(); // nazwa -> {val, hint}

function settingRow(s) {
  const row = el("div", "srow");
  const name = el("span", "", s.name);
  row.append(name);
  if (s.name === "host") {
    const box = el("div", "wide");
    const inp = el("input");
    inp.placeholder = "IP WLED, np. 192.168.68.81";
    inp.id = "host-input";
    const ok = el("button", "small", "Zapisz");
    const save = () => cmd("host", { host: inp.value });
    ok.onclick = save;
    inp.addEventListener("keydown", (e) => e.key === "Enter" && save());
    box.append(inp, ok);
    row.append(box);
    rows.set(s.name, { input: inp });
    return row;
  }
  if (s.name === "ludzik zajęcia") {
    const box = el("div", "wide");
    const val = el("span", "");
    const open = el("button", "small", "Zmień…");
    open.onclick = () => ($("#acts").hidden = !$("#acts").hidden);
    box.append(val, open);
    row.append(box);
    rows.set(s.name, { val });
    return row;
  }
  const dec = el("button", "small", "◂");
  const inc = el("button", "small", "▸");
  dec.title = "mniej";
  inc.title = "więcej";
  const valBox = el("div", "val");
  const meter = el("div", "meter");
  const fill = el("i");
  meter.append(fill);
  const val = el("span", "");
  valBox.append(meter, val);
  const change = (d) => {
    if (s.name === "szerokość" && !confirm("Zmiana szerokości uruchamia skrypt ponownie. Kontynuować?")) return;
    cmd("setting", { name: s.name, d });
  };
  dec.onclick = () => change(-1);
  inc.onclick = () => change(1);
  const hint = el("div", "hint");
  row.append(dec, valBox, inc, hint);
  rows.set(s.name, { val, meter, fill, hint });
  return row;
}

function renderSettings() {
  const box = $("#settings");
  if (!rows.size) state.settings.filter((s) => !HIDDEN_SETTINGS.has(s.name)).forEach((s) => box.append(settingRow(s)));
  for (const s of state.settings) {
    const r = rows.get(s.name);
    if (!r) continue;
    if (r.input) {
      if (document.activeElement !== r.input) r.input.value = state.host;
      continue;
    }
    // pasek „███░░░ 24” z TUI zamieniamy na wskaźnik + liczbę
    const m = /^([█░]+)\s*(.*)$/.exec(s.value);
    if (r.meter) {
      r.meter.hidden = !m;
      if (m) r.fill.style.width = `${(100 * [...m[1]].filter((c) => c === "█").length) / [...m[1]].length}%`;
    }
    r.val.textContent = m ? m[2] : s.value;
    // podpowiedzi z TUI będące samymi klawiszami („[ ]”, „l”, „< > r”) – skróty działają też tutaj
    if (r.hint) r.hint.textContent = /^[^\s\w]?[\w\[\]<> ]{0,4}$/.test(s.hint) ? `klawisz: ${s.hint}` : s.hint;
  }
}

const LVL_CLASS = ["", "", "on", "on"];
function renderActs() {
  const box = $("#acts-list");
  if (!box.childElementCount) {
    clocks.ludzik_acts.forEach((act) => {
      const row = el("div", "arow");
      const seg = el("div", "seg");
      clocks.ludzik_lvl.forEach((label, lvl) => {
        const b = el("button", "", label);
        b.dataset.lvl = lvl;
        b.onclick = () => cmd("ludzik", { act, lvl });
        seg.append(b);
      });
      row.append(el("span", "", act), seg);
      row.dataset.act = act;
      box.append(row);
    });
  }
  for (const row of box.children) {
    const lvl = state.ludzik[row.dataset.act];
    for (const b of row.querySelectorAll("button")) b.classList.toggle("on", Number(b.dataset.lvl) === lvl);
  }
}
$("#acts-close").onclick = () => ($("#acts").hidden = true);

// ------------------------------------------------------------ stan
function render(s) {
  state = s;
  const send = $("#send-state");
  send.textContent = s.sending ? "● wysyła" : "○ nie wysyła";
  send.classList.toggle("ok", s.sending);
  $("#host").textContent = s.host ? `host ${s.host}` : "brak hosta – wpisz w ustawieniach";
  $("#clock").textContent = s.time + (s.fake_time ? " (udawany)" : "");
  $("#badges").textContent = (s.paused ? "⏸ pauza  " : "") + (s.mirror ? "⇋ odbicie" : "");
  $("#override").hidden = !(s.lor && s.sending);
  $("#btn-pause").textContent = s.paused ? "▶ Wznów" : "⏸ Pauza";
  $("#btn-pause").classList.toggle("on", s.paused);
  $("#btn-cycle").classList.toggle("on", s.mode === "cykl");
  $("#btn-send").classList.toggle("on", s.sending);
  $("#btn-mirror").classList.toggle("on", s.mirror);

  const shown = s.mode === "cykl" ? s.current : s.mode;
  $("#now-name").textContent = shown;
  $("#now-cycle").textContent = s.mode === "cykl" ? "(cykl)" : "";
  $("#now-doc").textContent = clocks.docs[shown] || "";

  const p = s.power;
  const pw = $("#stat-power");
  pw.textContent =
    `prąd ~${(p.est / 1000).toFixed(2)} A` +
    (p.psu ? ` / limit ${p.psu / 1000} A` : "") +
    (p.k < 0.98 ? `  – przyciemniam do ${Math.round(p.k * 100)}% (efekt chce ${(p.raw / 1000).toFixed(1)} A)` : "");
  pw.className = p.k < 0.98 ? "warn" : "";
  $("#stat-panel").textContent = `panel: jasność WLED ${s.bri}/255, model: ${s.levels} poziomów na kanał`;
  const fps = $("#stat-fps");
  fps.textContent =
    `fps ${s.fps}/${s.fps_set}  render ${s.render_ms} ms  pakiety ${s.pkts}` + (s.err ? `  błąd: ${s.err}` : "");
  fps.className = s.err ? "bad" : s.fps_set > 22 ? "warn" : "";
  $("#stat-net").textContent = `sieć: ${s.net || "—"}`;
  if (s.note && s.note !== render.lastNote) toast(s.note);
  render.lastNote = s.note;

  renderList();
  renderSettings();
  renderActs();
}

// ------------------------------------------------------------ przyciski i klawisze (jak w TUI)
document.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-op], button[data-select]");
  if (!b) return;
  if (b.dataset.select) cmd("select", { name: b.dataset.select });
  else cmd(b.dataset.op, b.dataset.d ? { d: Number(b.dataset.d) } : {});
});
document.addEventListener("keydown", (e) => {
  if (e.target.closest("input, textarea") || e.ctrlKey || e.metaKey || e.altKey) return;
  const keys = {
    ArrowRight: ["skip", { d: 1 }], ArrowLeft: ["skip", { d: -1 }], n: ["skip", { d: 1 }], p: ["skip", { d: -1 }],
    " ": ["pause"], s: ["send"], m: ["mirror"], l: ["shuffle"], o: ["override"], r: ["realtime"],
    "]": ["every", { d: 1 }], "[": ["every", { d: -1 }], ">": ["speed", { d: 1 }], "<": ["speed", { d: -1 }],
  };
  if (e.key === "c") cmd("select", { name: "cykl" });
  else if (e.key === "/") $("#search").focus();
  else if (keys[e.key]) cmd(...keys[e.key]);
  else return;
  e.preventDefault();
});

// ------------------------------------------------------------ połączenie: SSE, a gdy proxy go nie przepuszcza – odpytywanie
function startPolling() {
  const frame = async () => {
    try {
      const r = await fetch("api/frame");
      const b = new Uint8Array(await r.arrayBuffer());
      if (b.length) drawFrame(b);
    } catch (e) { /* skrypt się restartuje */ }
    setTimeout(frame, 150);
  };
  const st = async () => {
    try {
      render(await (await fetch("api/state")).json());
    } catch (e) { /* j.w. */ }
    setTimeout(st, 700);
  };
  st().then(frame);
}

function startStream() {
  let got = false;
  const es = new EventSource("api/stream");
  es.addEventListener("state", (e) => {
    got = true;
    render(JSON.parse(e.data));
  });
  es.addEventListener("frame", (e) => {
    got = true;
    drawFrame(b64bytes(e.data));
  });
  es.onerror = () => {
    if (!got) {
      es.close();
      startPolling();
    } // po udanym starcie EventSource sam łączy się ponownie
  };
}

(async function init() {
  clocks = await (await fetch("api/clocks")).json();
  if (new URLSearchParams(location.search).has("poll")) startPolling(); // diagnoza: bez SSE
  else startStream();
})();
