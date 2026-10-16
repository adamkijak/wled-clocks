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
  const key = [q, state && state.mode, state && state.current, [...heavy].join(), clocks.wled_ver].join("|");
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
  // efekty wbudowane w WLED – pod naszymi; numer to numer efektu w WLED
  const wled = (clocks.wled || []).filter((fx) => !q || fold(fx.name).includes(q) || fold(fx.tags).includes(q) ||
    fold("wled").includes(q));
  if (wled.length) ol.append(el("li", "sep", "Efekty wbudowane w WLED"));
  for (const fx of wled) {
    const name = `wled:${fx.id}`;
    const li = el("li");
    if (state && state.mode === name) li.classList.add("sel");
    li.append(el("span", "n", String(fx.id)), el("span", "name", fx.name), el("span", "tags", fx.tags));
    li.title = fx.tags.includes("♪") ? "reaguje na dźwięk – potrzebny mikrofon w WLED" : "efekt WLED";
    li.onclick = () => cmd("select", { name });
    ol.append(li);
  }
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
  if (s.kind) return pickRow(s, row); // suwak albo lista rozwijana
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

// ustawienie z listą wartości: suwak (kind "range") albo lista rozwijana ("list"); wysyła numer wybranej wartości
function pickRow(s, row) {
  const box = el("div", "wide pick");
  const label = el("span", "plabel");
  const r = { kind: s.kind, labels: [], label, hint: el("div", "hint"), dragging: false };
  const send = (i) => {
    if (s.name === "szerokość" && !confirm("Zmiana szerokości uruchamia skrypt ponownie. Kontynuować?")) {
      r.ctl.value = String(r.index);
      return;
    }
    cmd("setting", { name: s.name, i });
  };
  if (s.kind === "range") {
    r.ctl = el("input");
    r.ctl.type = "range";
    r.ctl.min = "0";
    r.ctl.step = "1";
    r.ctl.oninput = () => (label.textContent = r.labels[r.ctl.value]); // podgląd wartości w trakcie przesuwania
    r.ctl.onpointerdown = () => (r.dragging = true);
    r.ctl.onchange = () => {
      r.dragging = false;
      send(Number(r.ctl.value));
    };
    box.append(r.ctl, label);
  } else {
    r.ctl = el("select");
    r.ctl.onchange = () => send(Number(r.ctl.value));
    box.append(r.ctl);
  }
  r.ctl.setAttribute("aria-label", s.name);
  row.append(box, r.hint);
  rows.set(s.name, r);
  return row;
}

function renderPick(r, s) {
  if (r.labels.join("\n") !== s.labels.join("\n")) { // lista wartości się zmieniła (np. „poziomy: auto = …”)
    r.labels = s.labels;
    if (r.kind === "range") r.ctl.max = String(s.labels.length - 1);
    else {
      r.ctl.textContent = "";
      s.labels.forEach((l, i) => {
        const o = el("option", "", l);
        o.value = String(i);
        r.ctl.append(o);
      });
    }
  }
  r.index = s.index;
  if (r.dragging) return; // nie przestawiamy suwaka pod palcem
  r.ctl.value = String(s.index);
  r.label.textContent = s.labels[s.index];
}

// ustawienia bieżącego efektu WLED (z jego opisu w WLED): suwaki, opcje, paleta, kolory – każda zmiana od razu do WLED
let wledKey = "";
const wledRows = new Map(); // klucz (sx, ix, …, pal, col0…) -> {ctl, label, kind}

function renderWled(ws) {
  const box = $("#wled-settings");
  const pal = ws ? (ws.items.find((it) => it.labels) || { labels: [] }).labels.length : 0;
  const key = ws ? `${ws.id}|${ws.items.map((it) => it.key + it.label).join()}|${pal}` : "";
  if (key !== wledKey) { // inny efekt – budujemy wiersze od nowa
    wledKey = key;
    box.textContent = "";
    wledRows.clear();
    for (const it of ws ? ws.items : []) {
      const row = el("div", "srow");
      row.append(el("span", "", it.label));
      const pick = el("div", "wide pick");
      const r = { kind: it.kind, dragging: false };
      const send = (v) => cmd("wled", { key: it.key, v });
      if (it.kind === "range") {
        r.ctl = el("input");
        r.ctl.type = "range";
        r.ctl.min = "0";
        r.ctl.max = String(it.max);
        r.label = el("span", "plabel");
        r.ctl.oninput = () => (r.label.textContent = r.ctl.value);
        r.ctl.onpointerdown = () => (r.dragging = true);
        r.ctl.onchange = () => {
          r.dragging = false;
          send(Number(r.ctl.value));
        };
        pick.append(r.ctl, r.label);
      } else if (it.kind === "check") {
        r.ctl = el("input");
        r.ctl.type = "checkbox";
        r.ctl.onchange = () => send(r.ctl.checked);
        pick.append(r.ctl);
      } else if (it.kind === "list") {
        r.ctl = el("select");
        it.labels.forEach((l, i) => {
          const o = el("option", "", l);
          o.value = String(i);
          r.ctl.append(o);
        });
        r.ctl.onchange = () => send(Number(r.ctl.value));
        pick.append(r.ctl);
      } else {
        r.ctl = el("input");
        r.ctl.type = "color";
        r.ctl.onchange = () => send(r.ctl.value);
        pick.append(r.ctl);
      }
      r.ctl.setAttribute("aria-label", it.label);
      row.append(pick);
      box.append(row);
      wledRows.set(it.key, r);
    }
  }
  for (const it of ws ? ws.items : []) {
    const r = wledRows.get(it.key);
    if (!r || r.dragging || document.activeElement === r.ctl) continue; // nie przestawiamy pod palcem
    const loading = it.value === null || it.value === undefined; // WLED jeszcze nie podał wartości
    r.ctl.disabled = loading;
    if (loading) continue;
    if (r.kind === "check") r.ctl.checked = Boolean(it.value);
    else r.ctl.value = String(it.value);
    if (r.label) r.label.textContent = String(it.value);
  }
  return Boolean(ws && ws.items.length);
}

// ustawienia efektu (s.fx) widać tylko, gdy ten efekt jest na panelu; wspólne – zawsze
function renderSettings() {
  if (!rows.size) {
    for (const s of state.settings.filter((s) => !HIDDEN_SETTINGS.has(s.name))) {
      const row = settingRow(s);
      rows.get(s.name).row = row;
      (s.fx ? $("#fx-settings") : $("#settings")).append(row);
    }
  }
  const fx = new Set(state.setting_fx);
  let fxShown = false;
  for (const s of state.settings) {
    const r = rows.get(s.name);
    if (!r) continue;
    r.row.hidden = Boolean(s.fx) && !fx.has(s.fx);
    fxShown = fxShown || (Boolean(s.fx) && !r.row.hidden);
    if (r.input) {
      if (document.activeElement !== r.input) r.input.value = state.host;
      continue;
    }
    if (r.ctl) renderPick(r, s);
    // pasek „███░░░ 24” z TUI zamieniamy na wskaźnik + liczbę
    const m = /^([█░]+)\s*(.*)$/.exec(s.value);
    if (r.val) r.val.textContent = m ? m[2] : s.value;
    if (r.meter) {
      r.meter.hidden = !m;
      if (m) r.fill.style.width = `${(100 * [...m[1]].filter((c) => c === "█").length) / [...m[1]].length}%`;
    }
    // podpowiedzi z TUI będące samymi klawiszami („[ ]”, „l”, „< > r”) – skróty działają też tutaj
    if (r.hint) r.hint.textContent = /^[^\s\w]?[\w\[\]<> ]{0,4}$/.test(s.hint) ? `klawisz: ${s.hint}` : s.hint;
    if (r.hint) r.hint.classList.toggle("warn", s.hint.includes("skacze")); // ruch nie będzie płynny
  }
  $("#fx-name").textContent = state.mode === "cykl" ? `cykl (teraz ${state.current})` : $("#now-name").textContent;
  $("#fx-none").hidden = renderWled(state.wled_settings) || fxShown;
  if (!fx.has("ludzik")) $("#acts").hidden = true;
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

// ------------------------------------------------------------ wiadomości od widzów (efekt „napisz”)
const inboxCmd = (act, extra = {}) => cmd("inbox", { act, ...extra });
$("#inbox-open").onclick = () => inboxCmd("open");
$("#inbox-close").onclick = () => inboxCmd("close");
$("#inbox-hours").onclick = () => inboxCmd("hours", { d: 1 });
$("#inbox-hours").oncontextmenu = (e) => (e.preventDefault(), inboxCmd("hours", { d: -1 }));
$("#inbox-auto").onclick = () => inboxCmd("auto");
$("#inbox-clear").onclick = () => confirm("Usunąć wszystkie czekające wiadomości?") && inboxCmd("clear");

// teksty od obcych ludzi – tylko przez textContent (el), nigdy innerHTML
function msgList(id, items, buttons) {
  const ul = $(id);
  ul.textContent = "";
  if (!items.length) ul.append(el("li", "empty", "—"));
  for (const m of items) {
    const li = el("li");
    const box = el("span", "btns");
    for (const [label, act, title] of buttons) {
      if (act === "block" && !m.ip) continue; // nadawca nieznany (tunel) – nie ma kogo blokować
      const b = el("button", "small", label);
      b.title = title;
      b.onclick = () => inboxCmd(act, { id: m.id });
      box.append(b);
    }
    li.append(el("span", "at", m.at), el("span", "txt", m.text), el("span", "ip", m.ip), box);
    ul.append(li);
  }
}

let inboxKey = "";
function renderInbox(ib) {
  if (!ib) return;
  const st = $("#inbox-state");
  st.textContent = !ib.enabled ? "wyłączona" : ib.open ? `otwarta do ${ib.until}` : "zamknięta";
  st.classList.toggle("ok", ib.open);
  const [host, port] = (ib.address || "").split(":");
  $("#inbox-info").textContent = !ib.enabled
    ? "Uruchom skrypt z --msg-tunnel bore.pub albo --msg-port PORT."
    : !ib.open
      ? (ib.tunnel
        ? `Zamknięta skrzynka nic nie wystawia. Otwarcie zestawia tunel ${ib.tunnel} z nowym losowym portem – znają go tylko ci, którzy widzą panel.`
        : "Zamknięta skrzynka nie słucha na porcie. Otwarcie losuje nowy kod w adresie – znają go tylko ci, którzy widzą panel.")
      : ib.tunnel
        ? (ib.address
          ? `Adres: ${ib.address}  –  echo hi > /dev/tcp/${host}/${port}  albo  curl -d hi ${ib.address}  albo przeglądarka.` +
            "  Przez tunel nie widać, kto pisze: limit jest wspólny, ⛔ niedostępne."
          : `Łączę z ${ib.tunnel}…`) + (ib.err ? `  ${ib.err}` : "")
        : `Na panelu: curl -d hi ${ib.address}  –  albo ten adres w przeglądarce.` +
          (ib.public ? "" : "  Ustaw adres publiczny (msg_public), żeby zamiast „adres” było widać prawdziwy.") +
          (ib.blocked ? `  Zablokowane adresy: ${ib.blocked}.` : "");
  $("#inbox-open").textContent = ib.open ? "Nowy kod i czas od teraz" : `Otwórz skrzynkę`;
  $("#inbox-open").disabled = !ib.enabled;
  $("#inbox-close").disabled = !ib.open;
  $("#inbox-hours").textContent = `na ${String(ib.hours).replace(".", ",")} h`;
  $("#inbox-auto").textContent = `Akceptacja: ${ib.auto ? "automatyczna" : "ręczna"}`;
  $("#inbox-auto").classList.toggle("on", !ib.auto);
  const key = JSON.stringify([ib.pending, ib.queue, ib.shown]);
  if (key === inboxKey) return; // listy przebudowujemy tylko po zmianie – inaczej klik mógłby trafić w znikający przycisk
  inboxKey = key;
  msgList("#inbox-pending", ib.pending, [["✓ Pokaż", "approve", "Do kolejki na panel"], ["✕", "reject", "Odrzuć"],
    ["⛔", "block", "Odrzuć i zablokuj ten adres do następnego otwarcia"]]);
  msgList("#inbox-queue", ib.queue, [["✕", "reject", "Usuń z kolejki"], ["⛔", "block", "Usuń i zablokuj ten adres"]]);
  msgList("#inbox-shown", ib.shown, [["↻ Jeszcze raz", "again", "Pokaż ponownie"]]);
}

// ------------------------------------------------------------ stan
async function reloadClocks() {
  clocks = await (await fetch("api/clocks")).json();
  listKey = "";
}

function render(s) {
  state = s;
  if (s.wled_ver !== clocks.wled_ver && !render.loading) { // lista efektów WLED doszła albo się zmieniła
    render.loading = true;
    reloadClocks().finally(() => (render.loading = false));
  }
  const send = $("#send-state");
  send.textContent = s.wled_mode ? "◆ efekt WLED" : s.sending ? "● wysyła" : "○ nie wysyła";
  send.classList.toggle("ok", s.sending && !s.wled_mode);
  $("#host").textContent = s.host ? `host ${s.host}` : "brak hosta – wpisz w ustawieniach";
  $("#clock").textContent = s.time + (s.fake_time ? " (udawany)" : "");
  $("#badges").textContent = (s.paused ? "⏸ pauza  " : "") + (s.mirror ? "⇋ odbicie" : "");
  $("#override").hidden = !(s.lor && s.sending) || s.wled_mode;
  $("#btn-pause").textContent = s.paused ? "▶ Wznów" : "⏸ Pauza";
  $("#btn-pause").classList.toggle("on", s.paused);
  $("#btn-cycle").classList.toggle("on", s.mode === "cykl");
  $("#btn-send").classList.toggle("on", s.sending);
  $("#btn-mirror").classList.toggle("on", s.mirror);

  const shown = s.mode === "cykl" ? s.current : s.mode;
  const wfx = s.wled_mode && (clocks.wled || []).find((fx) => `wled:${fx.id}` === s.mode);
  $("#now-name").textContent = wfx ? wfx.name : shown;
  $("#now-cycle").textContent = s.mode === "cykl" ? "(cykl)" : s.wled_mode ? "(efekt WLED)" : "";
  $("#now-doc").textContent = wfx
    ? "Efekt wbudowany w WLED – skrypt teraz nic nie wysyła, obraz rysuje WLED (podgląd tu niedostępny)." +
      (wfx.tags.includes("♪") ? " Reaguje na dźwięk – potrzebny mikrofon w WLED." : "")
    : clocks.docs[shown] || "";

  const p = s.power;
  const over = !p.auto && p.psu && p.raw > p.psu;
  const pw = $("#stat-power");
  pw.textContent =
    `prąd ~${(p.est / 1000).toFixed(2)} A` +
    (p.psu ? ` / limit ${p.psu / 1000} A` : "") +
    (p.k < 0.98 ? `  – przyciemniam do ${Math.round(p.k * 100)}% (efekt chce ${(p.raw / 1000).toFixed(1)} A)` : "") +
    (over ? "  – ponad budżet zasilacza (przyciemnianie wyłączone)" : "");
  pw.className = p.k < 0.98 ? "warn" : over ? "bad" : "";
  if (s.wled_mode) {
    pw.textContent = "prąd: efekt WLED – limit pilnuje WLED";
    pw.className = "";
  }
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
  renderInbox(s.inbox);
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
