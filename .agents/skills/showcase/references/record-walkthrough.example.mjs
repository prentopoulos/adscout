// Record the walkthrough from the synthetic-only demo app with headless Edge over the DevTools
// protocol. Usage: node record.mjs <preview|record> <app url> <out dir> <brief.html>
// preview: one still per step (step-NN.png). record: screencast frames + frames.json timings.
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { setTimeout as sleep } from "node:timers/promises";
import { join } from "node:path";

const [mode, url, out, briefPath] = process.argv.slice(2);
const W = 1920, H = 1080;
const edge = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const port = 9344;
const profile = join(out, "edge-profile");
rmSync(join(out, "frames"), { recursive: true, force: true });
mkdirSync(join(out, "frames"), { recursive: true });
const browser = spawn(edge, [
  "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--mute-audio",
  `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  `--window-size=${W},${H}`, "about:blank",
], { stdio: "ignore" });

async function target() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await sleep(200);
  }
  throw new Error("no DevTools target");
}

const ws = new WebSocket(await target());
await new Promise((ok) => ws.addEventListener("open", ok, { once: true }));
let next = 0;
const pending = new Map();
const frames = [];
const t0 = performance.now();
ws.addEventListener("message", (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); return; }
  if (msg.method === "Page.screencastFrame") {
    const n = frames.length;
    const file = `frames/${String(n).padStart(6, "0")}.jpg`;
    writeFileSync(join(out, file), Buffer.from(msg.params.data, "base64"));
    frames.push({ file, t: (performance.now() - t0) / 1000 });
    ws.send(JSON.stringify({ id: ++next, method: "Page.screencastFrameAck", params: { sessionId: msg.params.sessionId } }));
  }
});
const send = (method, params = {}) => new Promise((ok) => {
  const id = ++next; pending.set(id, ok); ws.send(JSON.stringify({ id, method, params }));
});
async function js(expression) {
  const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (r.result && r.result.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails).slice(0, 400));
  return r.result && r.result.result ? r.result.result.value : undefined;
}
async function waitText(text, ms = 30000) {
  for (let i = 0; i < ms / 250; i++) {
    if (await js(`document.body ? document.body.innerText.includes(${JSON.stringify(text)}) : false`)) return;
    await sleep(250);
  }
  throw new Error(`timed out waiting for: ${text}`);
}

// Page-side helpers: caption, highlight, pointer and full-screen panels, outside Streamlit's root.
const brief = readFileSync(briefPath, "utf-8");
const OVERLAY = `(() => {
  if (window.wt) return true;
  const font = '"Source Sans", "Source Sans Pro", "Source Sans 3", sans-serif';
  const css = document.createElement('style');
  css.textContent = \`
    #wt-cap { position: fixed; left: 50%; bottom: 44px; transform: translateX(-50%); z-index: 2147483002;
      max-width: 1320px; padding: 18px 30px; border-radius: 12px; background: rgba(9,11,15,0.94);
      border: 1px solid #2c3442; color: #f3f5f9; font: 600 31px/1.35 \${font}; text-align: center;
      box-shadow: 0 10px 40px rgba(0,0,0,0.5); opacity: 0; transition: opacity 350ms ease; }
    #wt-hl { position: fixed; z-index: 2147483001; border: 3px solid #6aa8ff; border-radius: 10px;
      box-shadow: 0 0 0 4000px rgba(0,0,0,0.45); opacity: 0; pointer-events: none;
      transition: left 650ms ease, top 650ms ease, width 650ms ease, height 650ms ease, opacity 400ms ease; }
    #wt-ptr { position: fixed; z-index: 2147483003; width: 34px; height: 34px; left: 1500px; top: 700px;
      pointer-events: none; transition: left 800ms cubic-bezier(.4,0,.2,1), top 800ms cubic-bezier(.4,0,.2,1), transform 120ms; opacity: 0; }
    #wt-panel { position: fixed; inset: 0; z-index: 2147483000; background: #0e1117; opacity: 0;
      transition: opacity 600ms ease; overflow: hidden; color: #e8ebf1; font-family: \${font}; pointer-events: none; }
    #wt-panel .card { position: absolute; inset: 0; display: flex; flex-direction: column;
      align-items: center; justify-content: center; text-align: center; gap: 26px; }
    #wt-panel .t1 { font-size: 76px; font-weight: 700; letter-spacing: -0.5px; }
    #wt-panel .t2 { font-size: 40px; color: #c9cfda; max-width: 1400px; }
    #wt-panel .t3 { font-size: 26px; font-weight: 700; letter-spacing: 1.5px; color: #f2c94c; margin-top: 18px; }
    #wt-panel .t4 { font-size: 34px; color: #8fb8ff; }
    #wt-brief { position: absolute; left: 50%; top: 70px; width: 1240px; transform: translate(-50%, 0);
      transition: transform 1600ms cubic-bezier(.4,0,.2,1); font-size: 27px; line-height: 1.5; }
    #wt-brief h1 { font-size: 46px; margin: 0 0 10px; } #wt-brief h2 { font-size: 33px; margin: 34px 0 8px; color: #fff; }
    #wt-brief p, #wt-brief li { margin: 10px 0; font-size: 27px; line-height: 1.5; } #wt-brief em { color: #aab3c2; }
    #wt-brief td, #wt-brief th { font-size: 24px; }
    #wt-brief strong { color: #f2c94c; } #wt-brief table { border-collapse: collapse; margin: 10px 0; }
    #wt-brief td, #wt-brief th { border-bottom: 1px solid #2c3442; padding: 6px 18px; }
    #wt-brief ul { margin: 8px 0 8px 10px; } \`;
  document.head.appendChild(css);
  const cap = Object.assign(document.createElement('div'), { id: 'wt-cap' });
  const hl = Object.assign(document.createElement('div'), { id: 'wt-hl' });
  const panel = Object.assign(document.createElement('div'), { id: 'wt-panel' });
  const ptr = Object.assign(document.createElement('div'), { id: 'wt-ptr' });
  ptr.innerHTML = '<svg viewBox="0 0 24 24" width="34" height="34"><path d="M4 2 L4 20 L9 15 L12.5 22 L15.5 20.6 L12 13.6 L19 13.6 Z" fill="#fff" stroke="#111" stroke-width="1.4" stroke-linejoin="round"/></svg>';
  document.body.append(hl, panel, cap, ptr);
  function textRect(t, scope) {
    const root = (scope && document.querySelector(scope)) || document.body;
    const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      if (n.parentElement.closest('#wt-cap, #wt-hl')) continue;
      const i = n.data.replace(/[\\s\\u00a0\\u2009\\u202f]/g, " ").toLowerCase().indexOf(t.toLowerCase());
      if (i < 0) continue;
      const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + t.length);
      const b = r.getBoundingClientRect();
      if (b.width > 0 && b.height > 0) return b;
    }
    return null;
  }
  function union(rects, pad) {
    rects = rects.filter(r => r && r.width > 0 && r.height > 0);
    if (!rects.length) return null;
    const l = Math.min(...rects.map(r => r.left)) - pad, t = Math.min(...rects.map(r => r.top)) - pad;
    const r = Math.max(...rects.map(r => r.right)) + pad, b = Math.max(...rects.map(r => r.bottom)) + pad;
    return { left: l, top: t, width: r - l, height: b - t };
  }
  window.wt = {
    caption(text) {
      cap.style.opacity = 0;
      setTimeout(() => { cap.textContent = text; cap.style.opacity = text ? 1 : 0; }, text && cap.textContent ? 300 : 0);
    },
    rect(spec) {
      const rects = [];
      for (const t of spec.texts || []) rects.push(textRect(t, spec.scope));
      for (const [s, k] of spec.nth || []) { const e = [...document.querySelectorAll(s)].filter(x => x.getBoundingClientRect().width > 0).at(k); if (e) rects.push(e.getBoundingClientRect()); }
      for (const s of spec.selectors || []) { const e = document.querySelector(s); if (e) rects.push(e.getBoundingClientRect()); }
      const u = union(rects, spec.pad ?? 12);
      if (u && spec.grow) { u.height += spec.grow; }
      return u;
    },
    highlight(spec) {
      if (!spec) { hl.style.opacity = 0; return true; }
      const r = this.rect(spec);
      if (!r) return false;
      Object.assign(hl.style, { left: r.left + 'px', top: r.top + 'px', width: r.width + 'px', height: r.height + 'px', opacity: 1 });
      return true;
    },
    pointer(x, y, show = true) { ptr.style.opacity = show ? 1 : 0; ptr.style.left = x + 'px'; ptr.style.top = y + 'px'; },
    press() { ptr.style.transform = 'scale(0.82)'; setTimeout(() => ptr.style.transform = '', 160); },
    panel(html) {
      if (html === null) { panel.style.opacity = 0; return; }
      panel.innerHTML = html; panel.style.opacity = 1;
    },
    briefTo(text, top = 120) {
      const box = document.getElementById('wt-brief');
      const r = textRect(text);
      if (!box || !r) return false;
      const current = new DOMMatrix(getComputedStyle(box).transform).m42;
      box.style.transform = 'translate(-50%, ' + (current - (r.top - top)) + 'px)';
      return true;
    },
  };
  return true;
})()`;

async function overlay() { await js(OVERLAY); }
async function center(spec) {
  const r = await js(`(() => { const r = wt.rect(${JSON.stringify({ ...spec, pad: 0 })}); return r && [r.left + r.width / 2, r.top + r.height / 2]; })()`);
  if (!r) throw new Error(`not found: ${JSON.stringify(spec)}`);
  return r;
}
async function click(spec) {
  const [x, y] = await center(spec);
  await js(`wt.pointer(${x - 6}, ${y - 4})`);
  await sleep(900);
  await js("wt.press()");
  for (const type of ["mouseMoved", "mousePressed", "mouseReleased"]) {
    await send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1 });
  }
}
async function key(k, code, vk) {
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: k, code, windowsVirtualKeyCode: vk });
  await send("Input.dispatchKeyEvent", { type: "keyUp", key: k, code, windowsVirtualKeyCode: vk });
}
const readTime = (text) => Math.max(3600, (text.split(/\s+/).length / 2.5) * 1000 + 1400);
let stepNo = 0;
async function still() {
  if (mode !== "preview") return;
  const shot = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(out, `step-${String(++stepNo).padStart(2, "0")}.png`), Buffer.from(shot.result.data, "base64"));
}
async function say(text, highlight, extra = 0) {
  if (highlight !== undefined) {
    const ok = await js(`wt.highlight(${JSON.stringify(highlight)})`);
    if (!ok) throw new Error(`highlight not found: ${JSON.stringify(highlight)}`);
  }
  await js(`wt.caption(${JSON.stringify(text)})`);
  await sleep(mode === "preview" ? 1200 : readTime(text) + extra);
  await still();
}

const CARD = (lines) => `<div class="card">${lines}</div>`;
try {
  await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await send("Page.navigate", { url });
  await waitText("276,480.00");
  await sleep(2500);
  await overlay();
  await js(`wt.panel(${JSON.stringify(CARD(`<div class="t1">Compute Cost &amp; Risk Monitor</div>
    <div class="t2">What will renting GPUs cost, and what if prices change?</div>
    <div class="t3">DEMO ON INVENTED PRICES — NOT AZURE LIST PRICES</div>`))})`);
  await sleep(800);
  if (mode === "record") await send("Page.startScreencast", { format: "jpeg", quality: 90, maxWidth: W, maxHeight: H, everyNthFrame: 1 });
  await sleep(mode === "preview" ? 300 : 5200);
  await still();
  await js("wt.panel(null)");
  await sleep(900);

  await say("This is the dashboard. The yellow label means these are invented demo prices.",
    { texts: ["COMPUTE COST & RISK MONITOR", "SYNTHETIC DATA", "LIST PRICES"], scope: "[data-testid=\"stMain\"]" });
  await say("On the left, pick the GPU, the machine size, the pricing and the region.",
    { selectors: ['[data-testid="stSidebarUserContent"]'], pad: 4 });
  await say("The answer comes first: 32 H100 GPUs for 720 hours cost USD 276,480.",
    { texts: ["Cost, USD", "276,480.00", "32 × 720"], pad: 16 });
  await say("The grid shows what happens if prices move, from half price to double.",
    { texts: ["SCENARIO GRID", "+46,080"], pad: 14 });
  await say("If prices rise 25%, this job costs USD 69,120 more. It's a what-if, not a forecast.",
    { texts: ["+69,120"], pad: 10 });
  await say("Under every cost, a line lists what it doesn't include, like storage and taxes.",
    { texts: ["EXCL.", "capacity and quota"], pad: 10 });

  // Change the job: 32 GPUs to 64.
  await js(`wt.highlight(${JSON.stringify({ selectors: ['input[aria-label="GPUs"]'], pad: 8 })})`);
  await js(`wt.caption("Change the job and every number updates.")`);
  await sleep(1200);
  await click({ selectors: ['input[aria-label="GPUs"]'] });
  await sleep(300);
  await js(`(() => { const e = document.querySelector('input[aria-label="GPUs"]'); e.focus(); e.select(); return true; })()`);
  for (const ch of "64") { await send("Input.insertText", { text: ch }); await sleep(260); }
  await sleep(400);
  await key("Enter", "Enter", 13);
  await waitText("552,960.00");
  await sleep(1200);
  await js("wt.pointer(1560, 760, false)");
  await say("Change the job and every number updates: 64 GPUs cost USD 552,960.",
    { texts: ["Cost, USD", "552,960.00", "64 × 720"], pad: 16 }, 600);

  await js("wt.highlight(null)");
  await js(`wt.caption("")`);
  await click({ texts: ["Comparable groups"] });
  await waitText("ACROSS REGIONS");
  await sleep(1500);
  await js("wt.pointer(1560, 760, false)");
  await say("Prices are only compared for the same kind of machine.",
    { texts: ["Lowest, USD/GPU-h"], nth: [["[data-testid=\"stDataFrame\"]", 0]], pad: 14 });
  await say("Across 5 regions, this machine lists from 12 to 15 USD per GPU-hour.",
    { texts: ["ACROSS REGIONS"], nth: [["[data-testid=\"stDataFrame\"]", 1], ["[data-testid=\"stDataFrame\"]", 2]], pad: 14 }, 400);

  await js("wt.highlight(null)");
  await js(`wt.caption("")`);
  await click({ texts: ["Data quality"] });
  await sleep(2500);
  await js("wt.pointer(1560, 760, false)");
  await say("The data-quality tab shows how fresh the prices are, and counts every row that was set aside, with the reason.",
    { texts: ["Azure VMs (synthetic)", "Sizes not in the map"], scope: "[data-testid=\"stMain\"]", nth: [["[data-testid=\"stTable\"]", 0], ["[data-testid=\"stDataFrame\"]", 0]], grow: 10, pad: 14 }, 800);

  await js("wt.highlight(null)");
  await js(`wt.panel(${JSON.stringify(`<div id="wt-brief">${brief}</div>`)})`);
  await sleep(900);
  await say("Each snapshot also gets an AI-powered market brief, with the bottom line first.",
    { nth: [["#wt-brief h2", 0], ["#wt-brief p", 2]], pad: 16 });
  await say("Claude (AI) drafts the text of the brief.", undefined, 600);

  await js("wt.highlight(null)");
  await js(`wt.caption("")`);
  await js(`wt.panel(${JSON.stringify(CARD(`<div class="t1">Compute Cost &amp; Risk Monitor</div>
    <div class="t2">GPU cost and price-risk dashboard · AI-powered market brief</div>
    <div class="t4">github.com/prentopoulos/compute-cost-risk-monitor</div>
    <div class="t3">INVENTED PRICES — NOT AZURE LIST PRICES</div>`))})`);
  await sleep(mode === "preview" ? 1000 : 6500);
  await still();
  if (mode === "record") {
    await send("Page.stopScreencast");
    await sleep(300);
    writeFileSync(join(out, "frames.json"), JSON.stringify({ frames, end: (performance.now() - t0) / 1000 }));
    console.log(`frames: ${frames.length}, seconds: ${(frames.at(-1).t - frames[0].t).toFixed(1)}`);
  } else {
    console.log(`stills: ${stepNo}`);
  }
} finally {
  ws.close();
  browser.kill();
}
