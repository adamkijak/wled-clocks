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
// ustawienia z próbnikiem koloru: nazwa -> [rozkaz, przycisk „bez koloru”, jego podpowiedź]
const COLOR_ROWS = {
  "kolor oczu": ["eyes", "naturalny", "Każde oczy w swoim kolorze"],
  "kolor zegara": ["clockcol", "z barwy", "Kolor z listy „barwa” (np. pora dnia)"],
};
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

// tekst tylko po zmianie – inaczej co odświeżenie stanu znika zaznaczenie (nie da się skopiować)
function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
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
let lastFrame = null;

// diody jak kropki: bytes = RGB klatki W x H, rysujemy pierwsze cols kolumn, cssW = szerokość na stronie
function drawLeds(cv, bytes, W, H, cols, cssW) {
  const c2 = cv.getContext("2d");
  const cell = (cssW / cols) * (window.devicePixelRatio || 1);
  const cw = Math.round(cell * cols);
  const ch = Math.round(cell * H);
  if (cv.width !== cw || cv.height !== ch) {
    cv.width = cw;
    cv.height = ch;
  }
  c2.fillStyle = "#0b0b0e";
  c2.fillRect(0, 0, cw, ch);
  const r = cell * 0.4;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < cols; x++) {
      const i = (y * W + x) * 3;
      const R = bytes[i], G = bytes[i + 1], B = bytes[i + 2];
      c2.fillStyle = R || G || B ? `rgb(${R},${G},${B})` : "#222226";
      c2.beginPath();
      c2.arc((x + 0.5) * cell, (y + 0.5) * cell, R || G || B ? r : r * 0.45, 0, 6.2832);
      c2.fill();
    }
  }
}

function drawFrame(bytes) {
  lastFrame = bytes;
  const W = state ? state.w : bytes.length / 36;
  drawLeds(canvas, bytes, W, state ? state.h : 12, W, canvas.clientWidth || 600);
}
window.addEventListener("resize", () => lastFrame && drawFrame(lastFrame));

// podglądy efektów i postaci ludzika (api/thumb): po jednym naraz, odświeżane najwyżej co minutę
const thumbs = new Map(); // zapytanie -> {t, p: Promise<Uint8Array>}
let thumbChain = Promise.resolve();
function thumb(query) {
  const hit = thumbs.get(query);
  if (!hit || Date.now() - hit.t > 60000) {
    const p = thumbChain.then(async () => new Uint8Array(await (await fetch(`api/thumb?${query}`)).arrayBuffer()));
    thumbChain = p.catch(() => {});
    thumbs.set(query, { t: Date.now(), p });
    p.catch(() => thumbs.delete(query)); // skrypt się restartuje – spróbujemy przy następnym pokazaniu
  }
  return thumbs.get(query).p;
}
function showThumb(cv, query, cols, cssW) {
  thumb(query).then((b) => {
    const W = state ? state.w : b.length / 36;
    if (b.length === W * 12 * 3) drawLeds(cv, b, W, 12, cols || W, cssW);
  }).catch(() => {});
}
// podgląd efektu liczy się dopiero, gdy wiersz listy jest widoczny
const thumbSeen = new IntersectionObserver((entries) => {
  for (const en of entries) {
    if (!en.isIntersecting) continue;
    thumbSeen.unobserve(en.target);
    showThumb(en.target, `fx=${encodeURIComponent(en.target.dataset.fx)}`, 0, en.target.clientWidth || 240);
  }
}, { root: null, rootMargin: "200px" });

function b64bytes(s) {
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

// ------------------------------------------------------------ lista efektów
// efekty w zwijanych kategoriach; na start rozwinięte tylko „Na start” i kategoria efektu na panelu,
// a co zwinięte/rozwinięte – zapamiętuje przeglądarka
const WLED_GROUPS = [["WLED – reagują na dźwięk", "♪"], ["WLED – 2D", "▦"], ["WLED – 1D", "▬"]];
const wledGroup = (fx) => WLED_GROUPS[fx.tags.includes("♪") ? 0 : fx.tags.includes("2D") ? 1 : 2][0];
let collapsed = {};
try { collapsed = JSON.parse(localStorage.getItem("wc-collapsed")) || {}; } catch (e) { /* bez pamięci */ }
const isCollapsed = (g) => (g in collapsed ? collapsed[g] : g !== "Na start");
// ustawienia wspólne: zwinięte, dopóki ich nie rozwiniesz (przeglądarka pamięta)
try { $("#common").open = localStorage.getItem("wc-common") === "1"; } catch (e) { /* bez pamięci */ }
$("#common").addEventListener("toggle", () => {
  try { localStorage.setItem("wc-common", $("#common").open ? "1" : "0"); } catch (e) { /* bez pamięci */ }
});
// zwijane grupy ustawień: przeglądarka pamięta, które są rozwinięte
document.querySelectorAll("details.grp[data-k]").forEach((d) => {
  try { d.open = localStorage.getItem(`wc-grp-${d.dataset.k}`) === "1"; } catch (e) { /* bez pamięci */ }
  d.addEventListener("toggle", () => {
    try { localStorage.setItem(`wc-grp-${d.dataset.k}`, d.open ? "1" : "0"); } catch (e) { /* bez pamięci */ }
  });
});
let anchor = null; // kliknięty nagłówek kategorii: po przebudowie listy zostaje w tym samym miejscu ekranu
function setCollapsed(g, v, h) {
  collapsed[g] = v;
  try { localStorage.setItem("wc-collapsed", JSON.stringify(collapsed)); } catch (e) { /* bez pamięci */ }
  if (h) anchor = { name: g, top: h.getBoundingClientRect().top };
  listKey = "";
  renderList();
}
let shownMode = null;
let centeredOn = null; // efekt, na którym lista była ostatnio wyśrodkowana – środkujemy tylko przy zmianie

function groups() {
  const out = (clocks.categories || []).map((c) => ({ name: c.name, icon: c.icon, items: c.names.map((name) => ({
    mode: name, n: clocks.names.indexOf(name) + 1, label: name, doc: clocks.docs[name] || "",
    text: [name, clocks.docs[name] || ""] })) }));
  const wled = WLED_GROUPS.map(([name, icon]) => ({ name, icon, items: [] }));
  for (const fx of clocks.wled || []) {
    wled.find((g) => g.name === wledGroup(fx)).items.push({ mode: `wled:${fx.id}`, n: fx.id, label: fx.name,
      tags: fx.tags, text: [fx.name, fx.tags, "wled"] });
  }
  return out.concat(wled.filter((g) => g.items.length));
}

function renderList() {
  const q = fold($("#search").value.trim());
  const heavy = new Set(state ? state.heavy : []);
  const mode = state && state.mode, cur = state && state.current;
  if (mode && mode !== shownMode) { // nowy efekt na panelu – jego kategoria się rozwija
    shownMode = mode;
    const g = groups().find((g) => g.items.some((it) => it.mode === (mode === "cykl" ? cur : mode)));
    if (g && isCollapsed(g.name)) collapsed[g.name] = false;
  }
  const waiting = state && state.inbox ? state.inbox.pending.length : 0; // wiadomości czekające na ✓
  const key = [q, mode, cur, [...heavy].join(), clocks.wled_ver, JSON.stringify(collapsed), waiting].join("|");
  if (key === listKey) return;
  listKey = key;
  const ol = $("#list");
  const keep = [ol.scrollTop, window.scrollY]; // przebudowa nie może przewinąć listy ani strony
  thumbSeen.disconnect(); // stare wiersze znikają – nowe zgłoszą się same
  ol.textContent = "";
  for (const g of groups()) {
    const items = g.items.filter((it) => !q || it.text.some((t) => fold(t).includes(q)));
    if (!items.length) continue;
    const open = q || !isCollapsed(g.name);
    const h = el("li", "sep grp" + (open ? " open" : ""));
    h.append(el("span", "arrow", open ? "▾" : "▸"), el("span", "", `${g.icon} ${g.name}`),
      el("span", "count", q ? `${items.length}/${g.items.length}` : String(g.items.length)));
    h.tabIndex = 0;
    h.dataset.g = g.name;
    h.setAttribute("role", "button");
    h.setAttribute("aria-expanded", String(Boolean(open)));
    const toggle = () => !q && setCollapsed(g.name, open, h);
    h.onclick = toggle;
    h.onkeydown = (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), toggle());
    ol.append(h);
    if (!open) continue;
    for (const it of items) {
      const li = el("li");
      if (it.mode === mode) li.classList.add("sel");
      else if (mode === "cykl" && it.mode === cur) li.classList.add("incycle");
      li.append(el("span", "n", String(it.n)), el("span", "name", it.label));
      if (it.tags !== undefined) {
        li.append(el("span", "tags", it.tags));
        li.title = it.tags.includes("♪") ? "reaguje na dźwięk – potrzebny mikrofon w WLED" : "efekt WLED";
      } else {
        const mail = it.mode === "napisz" && waiting ? `✉ ${waiting}` : "";
        li.append(el("span", "heavy", (mail + " " + (heavy.has(it.mode) ? "⚡" : "")).trim()));
        if (it.mode !== "cykl") { // podgląd efektu
          const cv = el("canvas", "thumb");
          cv.dataset.fx = it.mode;
          if (state) cv.style.aspectRatio = `${state.w} / 12`;
          li.append(cv);
          thumbSeen.observe(cv);
        }
        li.append(el("span", "d", it.doc));
        if (mail) li.title = `${waiting} wiadomości czeka na akceptację – wybierz „napisz”`;
        li.title = li.title || it.doc;
      }
      li.onclick = () => cmd("select", { name: it.mode });
      ol.append(li);
    }
  }
  ol.scrollTop = keep[0];
  if (Math.abs(window.scrollY - keep[1]) > 1) window.scrollTo(0, keep[1]);
  const h = anchor && [...ol.querySelectorAll("li.grp")].find((li) => li.dataset.g === anchor.name);
  const sel = ol.querySelector("li.sel, li.incycle");
  const target = mode === "cykl" ? cur : mode;
  if (h) { // rozwinięta/zwinięta kategoria: jej nagłówek tam, gdzie był, i z fokusem
    ol.scrollTop += h.getBoundingClientRect().top - anchor.top;
    const rest = h.getBoundingClientRect().top - anchor.top; // lista bez własnego przewijania – przewija się strona
    if (Math.abs(rest) > 1) window.scrollBy(0, rest);
    h.focus({ preventScroll: true });
  } else if (sel && !q && target !== centeredOn) { // nowy efekt na panelu – lista pokazuje go na środku
    ol.scrollTop = sel.offsetTop - ol.offsetTop - ol.clientHeight / 2 + sel.offsetHeight / 2;
  }
  if (sel && !q) centeredOn = target;
  anchor = null;
}
$("#search").addEventListener("input", renderList);
$("#search").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const first = $("#list li:not(.sep)");
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
  if (s.name === "ludzik postać") { // postacie z obrazkiem zamiast listy
    const box = el("div", "wide chars");
    const chars = s.labels.map((label, i) => {
      const b = el("button", "char");
      const cv = el("canvas");
      b.append(cv, el("span", "", label));
      b.title = label;
      b.onclick = () => cmd("setting", { name: s.name, i });
      box.append(b);
      showThumb(cv, `char=${i}`, 30, 90);
      return b;
    });
    row.append(box);
    rows.set(s.name, { chars });
    return row;
  }
  const pickCol = COLOR_ROWS[s.name];
  if (pickCol) { // dowolny kolor z próbnika albo przycisk „bez własnego koloru”
    const [op, off, offTitle] = pickCol;
    const box = el("div", "wide pick");
    const inp = el("input");
    inp.type = "color";
    inp.value = "#ff9900";
    inp.setAttribute("aria-label", s.name);
    let wait = 0;
    inp.oninput = () => { // od razu na panelu, także w trakcie wybierania (najwyżej co 80 ms)
      clearTimeout(wait);
      wait = setTimeout(() => cmd(op, { col: inp.value }), 80);
    };
    const nat = el("button", "small", off);
    nat.title = offTitle;
    nat.onclick = () => cmd(op, { col: "" });
    box.append(inp, nat);
    row.append(box);
    rows.set(s.name, { color: inp, nat });
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
    r.row.hidden = Boolean(s.fx) && !s.fx.split(" ").some((n) => fx.has(n)); // ustawienie kilku efektów: „a b c”
    fxShown = fxShown || (Boolean(s.fx) && !r.row.hidden);
    if (r.input) {
      if (document.activeElement !== r.input) r.input.value = state.host;
      continue;
    }
    if (r.ctl) renderPick(r, s);
    if (r.color) {
      const own = s.value.startsWith("#");
      if (own && document.activeElement !== r.color) r.color.value = s.value;
      r.nat.classList.toggle("on", !own);
    }
    if (r.chars) r.chars.forEach((b, i) => b.classList.toggle("on", i === s.index));
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
  $("#fx-none").hidden = renderWled(state.wled_settings) || fxShown || ["napisz", "daily", "rysunek"].some((n) => fx.has(n));
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
      const ctl = el("div", "actl");
      const now = el("button", "small go", "▶");
      now.title = "Zrób to jako następne (drugi raz – anuluj)";
      now.onclick = () => cmd("ludzik", { act, next: true });
      ctl.append(now, seg);
      if (clocks.ludzik_timed.includes(act)) { // długość zajęcia
        const len = el("select", "len");
        len.title = "Jak długo";
        clocks.ludzik_len.forEach((label, i) => len.append(new Option(label, i)));
        len.onchange = () => cmd("ludzik", { act, len: Number(len.value) });
        ctl.append(len);
      }
      row.append(el("span", "", act), ctl);
      row.dataset.act = act;
      box.append(row);
    });
  }
  for (const row of box.children) {
    const act = row.dataset.act, lvl = state.ludzik[act];
    for (const b of row.querySelectorAll(".seg button")) b.classList.toggle("on", Number(b.dataset.lvl) === lvl);
    row.querySelector(".go").classList.toggle("on", state.ludzik_next === act);
    const len = row.querySelector("select");
    if (len && document.activeElement !== len) len.value = String(state.ludzik_len[act]);
    if (len) len.disabled = !lvl;
  }
}
// co ludzik robi teraz i co zrobi następnie (z częstością i długością), jak przestawi godzinę
function renderLudzikStatus() {
  const st = state.ludzik_status;
  $("#lstat").hidden = !st || !st.now || !(state.setting_fx || []).includes("ludzik");
  if ($("#lstat").hidden) return;
  const lvlOf = (a) => (a in state.ludzik ? clocks.ludzik_lvl[state.ludzik[a]] : "");
  const lenOf = (a) => (a in state.ludzik_len ? clocks.ludzik_len[state.ludzik_len[a]] : "");
  const extra = (a, ...more) => ["", lvlOf(a) && `częstość: ${lvlOf(a)}`, lenOf(a) && `długość: ${lenOf(a)}`, ...more]
    .filter((x, i) => !i || x).join("  ·  ");
  const busy = st.now === "przestawia godzinę";
  setText($("#lstat-now"), busy ? `przestawia godzinę: ${st.how_now}` : st.now);
  setText($("#lstat-now-x"), busy ? "" : extra(st.now));
  setText($("#lstat-next"), st.next || "—");
  setText($("#lstat-next-x"), !st.next ? (st.never ? "  ·  „ludzik co ile”: nigdy" : "")
    : extra(st.next, st.forced ? "▶ wymuszone" : st.eta != null ? `za ok. ${st.eta} s` : "po bieżącym"));
  setText($("#lstat-how"), st.how_next);
  setText($("#lstat-how-x"), `  ·  ${busy ? "następna zmiana" : "zmiana"} o ${st.how_at}`);
}
$("#acts-close").onclick = () => ($("#acts").hidden = true);

// ------------------------------------------------------------ wiadomości od widzów (efekt „napisz”)
const inboxCmd = (act, extra = {}) => cmd("inbox", { act, ...extra });
$("#inbox-open").onclick = () => inboxCmd("open");
$("#inbox-close").onclick = () => inboxCmd("close");
// czas otwarcia: wpisany – zapisujemy po Enter albo po wyjściu z pola
$("#inbox-hours").addEventListener("change", (e) => {
  const v = Number(String(e.target.value).replace(",", "."));
  if (v >= 0.25 && v <= 24) inboxCmd("hours", { v });
  else toast("czas otwarcia: od 0,25 do 24 h");
});
$("#inbox-hours").addEventListener("keydown", (e) => e.key === "Enter" && e.target.blur());
$("#inbox-auto").addEventListener("change", (e) => {
  if ((e.target.value === "1") !== state.inbox.auto) inboxCmd("auto");
});
$("#inbox-copy").onclick = async () => {
  const text = $("#inbox-addr-text").textContent;
  try {
    await navigator.clipboard.writeText(text); // tylko https/localhost
  } catch (e) {
    const sel = getSelection(); // zwykłe http: zaznacza adres i kopiuje po staremu
    sel.selectAllChildren($("#inbox-addr-text"));
    if (!document.execCommand("copy")) return toast("Zaznaczone – skopiuj Ctrl+C");
  }
  toast(`Skopiowano: ${text}`);
};
$("#inbox-clear").onclick = () => confirm("Usunąć wszystkie czekające wiadomości?") && inboxCmd("clear");
// filtry: wł./wył. od razu; lista słów – przyciskiem; zachęta – po Enter albo wyjściu z pola
for (const key of ["words", "links", "dupes"]) {
  $(`#inbox-f-${key}`).addEventListener("change", (e) => {
    if (e.target.checked !== state.inbox.filters[key]) inboxCmd("filter", { key });
  });
}
// dodatki dla widzów wł./wył.
for (const key of ["reactions", "colors"]) {
  $(`#inbox-x-${key}`).addEventListener("change", (e) => {
    if (e.target.checked !== state.inbox.extras[key]) inboxCmd("extra", { key });
  });
}
$("#inbox-poll-hint").addEventListener("change", (e) => {
  if (e.target.checked !== state.inbox.poll_hint) inboxCmd("poll_hint");
});
// ankieta: pola wypełnia ostatnia ankieta, póki ich nie ruszysz
const POLL_COLS = ["#ff5046", "#3cbeff", "#6ef046", "#ffc828"];
let pollDirty = false;
const pollInputs = () => ["#poll-q", "#poll-o0", "#poll-o1", "#poll-o2", "#poll-o3"].map((id) => $(id));
pollInputs().forEach((inp) => inp.addEventListener("input", () => (pollDirty = true)));
$("#poll-start").onclick = () => {
  const [q, ...opts] = pollInputs().map((i) => i.value.trim());
  if (!q || opts.filter(Boolean).length < 2) return toast("ankieta: pytanie i co najmniej 2 odpowiedzi");
  const p = state.inbox.poll;
  if (p && p.on && p.votes.some(Boolean) && !confirm("Zacząć nową ankietę? Obecne głosy przepadną.")) return;
  pollDirty = false;
  inboxCmd("poll", { q, opts: opts.filter(Boolean) });
};
$("#poll-toggle").onclick = () => state.inbox.poll && inboxCmd(state.inbox.poll.on ? "poll_stop" : "poll_start");
$("#poll-reset").onclick = () => confirm("Wyzerować głosy?") && inboxCmd("poll_reset");

function renderPoll(p) {
  const votes = p ? p.votes.reduce((a, b) => a + b, 0) : 0;
  setText($("#sum-poll"), !p ? "brak" : p.on ? `trwa – głosów: ${votes}` : `zakończona – głosów: ${votes}`);
  $("#poll-toggle").disabled = $("#poll-reset").disabled = !p;
  setText($("#poll-toggle"), p && !p.on ? "Wznów" : "Zakończ");
  if (p && !pollDirty && !pollInputs().includes(document.activeElement)) {
    pollInputs().forEach((inp, i) => (inp.value = i ? p.opts[i - 1] || "" : p.q));
  }
  const key = JSON.stringify(p);
  if (key === renderPoll.key) return;
  renderPoll.key = key;
  const ul = $("#poll-res");
  ul.textContent = "";
  if (!p) return;
  const total = p.votes.reduce((a, b) => a + b, 0);
  p.opts.forEach((o, i) => {
    const li = el("li");
    const bar = el("span", "bar");
    const fill = el("i");
    fill.style.width = `${total ? (100 * p.votes[i]) / total : 0}%`;
    fill.style.background = POLL_COLS[i];
    bar.append(fill);
    li.append(el("span", "", `${String.fromCharCode(65 + i)}: ${o}`), bar,
      el("b", "", `${p.votes[i]}${total ? ` (${Math.round((100 * p.votes[i]) / total)}%)` : ""}`));
    ul.append(li);
  });
}

// ------------------------------------------------------------ daily
let dailyDirty = false;
$("#daily-text").addEventListener("input", () => (dailyDirty = true));
$("#daily-save").onclick = () => { dailyDirty = false; cmd("daily", { act: "set", v: $("#daily-text").value }); };
$("#daily-next").onclick = () => cmd("daily", { act: "next" });
$("#daily-reset").onclick = () => cmd("daily", { act: "reset" });
$("#daily-auto").addEventListener("change", (e) => {
  if (e.target.checked !== state.daily.auto) cmd("daily", { act: "auto" });
});

function renderDaily(d) {
  $("#daily").hidden = !(state.setting_fx || []).includes("daily");
  if ($("#daily").hidden) return;
  const left = d.people.filter((p) => !p.done).length;
  setText($("#daily-state"), d.people.length ? `zostało ${left} z ${d.people.length}` : "pusta lista");
  if (!d.people.length && !renderDaily.opened) { // pusta lista: od razu pole do wpisania osób
    renderDaily.opened = true;
    $("#daily-edit").open = true;
  }
  $("#daily-auto").checked = d.auto;
  if (!dailyDirty && document.activeElement !== $("#daily-text")) {
    $("#daily-text").value = d.people.map((p) => `${p.name} ${p.id}`).join("\n");
  }
  const key = JSON.stringify(d);
  if (key === renderDaily.key) return;
  renderDaily.key = key;
  const ul = $("#daily-list");
  ul.textContent = "";
  d.people.forEach((p, i) => {
    const li = el("li", (p.done ? "done" : "") + (i === d.cur ? " cur" : ""));
    const tick = el("button", "small", p.done ? "↺" : "✓");
    tick.title = p.done ? "Cofnij – jeszcze nie mówił(a)" : "Odhacz – już mówił(a)";
    tick.onclick = () => cmd("daily", { act: p.done ? "undo" : "done", i });
    const now = el("button", "small", "▶");
    now.title = "Teraz mówi";
    now.onclick = () => cmd("daily", { act: "now", i });
    const who = el("span", "who");
    who.append(el("b", "", p.id), document.createTextNode(` ${p.name}${i === d.cur ? " – mówi" : ""}`));
    li.append(tick, now, who);
    ul.append(li);
  });
}

// ------------------------------------------------------------ wspólny rysunek
const DRAW_PAL = ["#ff2d23", "#ff8200", "#ffe100", "#3cf046", "#00d2ff", "#326eff", "#aa46ff", "#ff50b4", "#ffffff", ""];
let brush = DRAW_PAL[0];
DRAW_PAL.forEach((c) => {
  const b = el("button");
  b.style.background = c || "#000";
  b.title = c ? c : "gumka";
  if (!c) b.textContent = "⌫";
  b.onclick = () => {
    brush = c;
    $("#draw-pal").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
  };
  if (c === brush) b.classList.add("on");
  $("#draw-pal").append(b);
});
$("#draw-clear").onclick = () => cmd("draw", { act: "clear" });
let painting = false, lastPx = "";
const paintAt = (e) => {
  const cv = $("#draw-cv");
  const r = cv.getBoundingClientRect();
  const x = Math.floor(((e.clientX - r.left) / r.width) * cv.width);
  const y = Math.floor(((e.clientY - r.top) / r.height) * cv.height);
  if (x < 0 || y < 0 || x >= cv.width || y >= cv.height || `${x},${y}` === lastPx) return;
  lastPx = `${x},${y}`;
  const ctx = cv.getContext("2d"); // od razu u siebie, panel dogoni
  ctx.fillStyle = brush || "#000";
  ctx.fillRect(x, y, 1, 1);
  cmd("draw", { act: "px", x, y, c: brush });
};
$("#draw-cv").addEventListener("pointerdown", (e) => { painting = true; lastPx = ""; paintAt(e); });
$("#draw-cv").addEventListener("pointermove", (e) => painting && paintAt(e));
addEventListener("pointerup", () => (painting = false));

function renderDraw(hex) {
  $("#draw").hidden = hex == null;
  if (hex == null || painting || hex === renderDraw.key) return;
  renderDraw.key = hex;
  const cv = $("#draw-cv");
  cv.width = state.w;
  cv.style.aspectRatio = `${state.w} / 12`;
  const ctx = cv.getContext("2d");
  const img = ctx.createImageData(cv.width, cv.height);
  for (let k = 0; k < cv.width * cv.height; k++) {
    const h = hex.slice(k * 6, k * 6 + 6);
    if (h === "------") continue;
    img.data.set([parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), 255], k * 4);
  }
  ctx.putImageData(img, 0, 0);
}

let wordsDirty = false; // niezapisane zmiany listy – odświeżenie stanu ich nie nadpisze
$("#inbox-words").addEventListener("input", () => (wordsDirty = true));
$("#inbox-words-save").onclick = () => { wordsDirty = false; inboxCmd("words", { v: $("#inbox-words").value }); };
$("#inbox-words-reset").onclick = () => {
  if (confirm("Przywrócić wbudowaną listę słów?")) { wordsDirty = false; inboxCmd("words", { reset: 1 }); }
};
const saveHint = () => {
  const every = Number($("#inbox-hint-every").value);
  if (!(every >= 0 && every <= 600)) return toast("zachęta: co 0–600 s");
  inboxCmd("hint", { v: $("#inbox-hint").value, every: Math.round(every) });
};
for (const id of ["#inbox-hint", "#inbox-hint-every"]) {
  $(id).addEventListener("change", saveHint);
  $(id).addEventListener("keydown", (e) => e.key === "Enter" && e.target.blur());
}

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
    const ip = el("span", "ip", m.ip ? `${m.ip} · ${m.geo || "…"}` : "IP ukryty (tunel bore)");
    li.append(el("span", "at", m.at), el("span", "txt", m.text), ip, box);
    ul.append(li);
  }
}

let inboxKey = "";
function renderInbox(ib) {
  // skrzynka to ustawienia efektu „napisz” – widać ją, gdy „napisz” jest na panelu
  $("#inbox").hidden = !ib || !(state.setting_fx || []).some((n) => ["napisz", "daily", "rysunek"].includes(n));
  if (!ib || $("#inbox").hidden) return;
  const st = $("#inbox-state");
  setText(st, !ib.enabled ? "wyłączona" : ib.open ? `otwarta do ${ib.until}` : "zamknięta");
  st.classList.toggle("ok", ib.open);
  const [host, port] = (ib.address || "").split(":");
  $("#inbox-addr").hidden = !(ib.open && ib.address);
  setText($("#inbox-addr-text"), ib.address || "");
  setText($("#inbox-info"), !ib.enabled
    ? "Uruchom skrypt z --msg-tunnel bore.pub albo --msg-port PORT."
    : !ib.open
      ? (ib.tunnel
        ? `Zamknięta skrzynka nic nie wystawia. Otwarcie zestawia tunel ${ib.tunnel} z nowym losowym portem – znają go tylko ci, którzy widzą panel.`
        : "Zamknięta skrzynka nie słucha na porcie. Otwarcie losuje nowy kod w adresie – znają go tylko ci, którzy widzą panel.")
      : ib.tunnel
        ? (ib.address
          ? `Wysyła się: echo hi > /dev/tcp/${host}/${port}  albo  curl -d hi ${ib.address}  albo przeglądarka.` +
            "  Przez tunel nie widać, kto pisze: limit jest wspólny, ⛔ niedostępne."
          : `Łączę z ${ib.tunnel}…`) + (ib.err ? `  ${ib.err}` : "")
        : `Na panelu: curl -d hi ${ib.address}  –  albo ten adres w przeglądarce.` +
          (ib.public ? "" : "  Ustaw adres publiczny (msg_public), żeby zamiast „adres” było widać prawdziwy.") +
          (ib.blocked ? `  Zablokowane adresy: ${ib.blocked}.` : ""));
  setText($("#inbox-open"), ib.open ? "Nowy kod i czas od teraz" : "Otwórz skrzynkę");
  $("#inbox-open").disabled = !ib.enabled;
  $("#inbox-close").disabled = !ib.open;
  if (document.activeElement !== $("#inbox-hours")) $("#inbox-hours").value = String(ib.hours);
  if (document.activeElement !== $("#inbox-auto")) $("#inbox-auto").value = ib.auto ? "1" : "0";
  for (const key of ["words", "links", "dupes"]) $(`#inbox-f-${key}`).checked = ib.filters[key];
  $("#inbox-words").disabled = !ib.filters.words;
  if (!wordsDirty) $("#inbox-words").value = ib.words; // niezapisanych zmian nie nadpisujemy
  if (document.activeElement !== $("#inbox-hint")) $("#inbox-hint").value = ib.hint;
  if (document.activeElement !== $("#inbox-hint-every")) $("#inbox-hint-every").value = String(ib.hint_every);
  setText($("#inbox-limits"), ib.limits);
  // podsumowania w nagłówkach zwiniętych grup
  setText($("#inbox-pending-n"), ib.pending.length ? `(${ib.pending.length})` : "– nic nie czeka");
  const ex = [ib.extras.reactions && "reakcje", ib.extras.colors && "kolory i emotki"].filter(Boolean);
  setText($("#sum-extras"), ex.length ? ex.join(", ") : "wyłączone");
  const fl = [ib.filters.words && "słowa", ib.filters.links && "linki", ib.filters.dupes && "powtórki"].filter(Boolean);
  setText($("#sum-filters"), fl.length ? fl.join(", ") : "bez cenzury");
  setText($("#sum-hint"), ib.hint && ib.hint_every ? `„${ib.hint}” co ${ib.hint_every} s` : "wyłączona");
  setText($("#sum-open"), `${String(ib.hours).replace(".", ",")} h, akceptacja ${ib.auto ? "automatyczna" : "ręczna"}`);
  setText($("#sum-msgs"), `w kolejce ${ib.queue.length}, pokazane ${ib.shown.length}`);
  for (const key of ["reactions", "colors"]) $(`#inbox-x-${key}`).checked = ib.extras[key];
  $("#inbox-poll-hint").checked = ib.poll_hint;
  renderPoll(ib.poll);
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
  const off = s.wled_on === false; // włącznik WLED wyłączony – skrypt nic nie wysyła, póki go nie włączysz
  const power = $("#btn-power");
  power.textContent = off ? "⏻ WLED wyłączony" : s.wled_on ? "⏻ WLED włączony" : "⏻ WLED ?";
  power.title = off ? "Włącz WLED (w) – wyłączony WLED skrypt zostawia w spokoju, nic nie wysyła"
    : s.wled_on ? "Wyłącz WLED (w)" : "WLED nie odpowiada";
  power.classList.toggle("off", off);
  power.disabled = s.wled_on == null;
  send.hidden = off;
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
  renderLudzikStatus();
  renderInbox(s.inbox);
  renderDaily(s.daily);
  renderDraw(s.draw);
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
    " ": ["pause"], s: ["send"], w: ["power"], m: ["mirror"], l: ["shuffle"], o: ["override"], r: ["realtime"],
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
