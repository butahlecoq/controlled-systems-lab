// Exercise the staged lesson in real Chromium viewports; no browser dependencies.
// node tests/reporting/check_native_discrete_layout.mjs LESSON.html OUTPUT_DIRECTORY
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { openSync, closeSync } from 'node:fs';
import { mkdtemp, readFile, writeFile, mkdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const lesson = resolve(process.argv[2]);
const output = resolve(process.argv[3]);
await mkdir(output, { recursive: true });
const profile = await mkdtemp(join(tmpdir(), 'native-discrete-layout-'));
const temporaryDirectory = openSync(tmpdir(), 'r');
const browser = spawn('chromium', ['--headless', '--no-sandbox', '--disable-gpu',
  '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'],
  { stdio: ['ignore', 'ignore', 'pipe', temporaryDirectory],
    env: {...process.env, TMPDIR: '/proc/self/fd/3'} });
closeSync(temporaryDirectory);
let browserLog = '';
browser.stderr.on('data', chunk => { browserLog += chunk.toString(); });
let socket;
try {
  let port;
  for (let n = 0; n < 100; n++) {
    try { port = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]; break; }
    catch { await new Promise(resolve => setTimeout(resolve, 100)); }
  }
  assert(port, 'Chromium did not expose CDP');
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let next = 0;
  const pending = new Map();
  socket.onmessage = event => {
    const reply = JSON.parse(event.data);
    if (pending.has(reply.id)) {
      const { resolve, reject } = pending.get(reply.id);
      pending.delete(reply.id);
      if (reply.error) reject(new Error(JSON.stringify(reply.error))); else resolve(reply.result);
    }
  };
  const cdp = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++next; pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
  const evaluate = async expression => (await cdp('Runtime.evaluate', {
    expression, returnByValue: true, awaitPromise: true,
  })).result.value;
  await cdp('Page.enable');
  const results = [];
  for (const [name, width, height, mobile] of [['mobile', 390, 844, true], ['desktop', 1280, 1000, false]]) {
    await cdp('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile });
    await cdp('Page.navigate', { url: pathToFileURL(lesson).href });
    for (let n = 0; n < 100; n++) {
      if (await evaluate('document.readyState === "complete" && [...document.images].every(i => i.complete)')) break;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    const metrics = await evaluate(`({
      viewport: innerWidth, document: document.documentElement.scrollWidth,
      body: document.body.scrollWidth,
      failedImages: [...document.images].filter(i => !i.naturalWidth).length,
      equations: [...document.querySelectorAll('math[display="block"]')].map(m => ({
        width: m.clientWidth, scroll: m.scrollWidth,
        parentOverflow: getComputedStyle(m.parentElement).overflowX,
        fontSize: getComputedStyle(m).fontSize,
      })),
    })`);
    results.push({ name, ...metrics });
    await writeFile(join(output, `${name}-metrics.json`), JSON.stringify(metrics, null, 2)+'\n');
    const screenshot = await cdp('Page.captureScreenshot', { format: 'png' });
    await writeFile(join(output, `${name}.png`), Buffer.from(screenshot.data, 'base64'));
    assert.equal(metrics.viewport, width, 'CDP must establish the requested actual viewport');
    assert(metrics.document <= width && metrics.body <= width, `${name}: page overflows viewport`);
    assert.equal(metrics.failedImages, 0, 'staged lesson images must load');
    assert(metrics.equations.every(m => parseFloat(m.fontSize) >= 16), 'equations must keep readable text size');
    assert(metrics.equations.every(m => m.scroll <= m.width || m.parentOverflow === 'auto'),
      'long equations must remain fully available in a local scroll region');
    const scroll = await evaluate(`(() => {
      const region = document.querySelector('[aria-label="MPC objective"]');
      if (!region) return null;
      region.scrollIntoView({block:'center', behavior:'instant'});
      region.scrollLeft = region.scrollWidth;
      return {left:region.scrollLeft, max:region.scrollWidth-region.clientWidth,
              verticalOverflow:region.scrollHeight>region.clientHeight,
              accessible:region.tabIndex===0 && region.getAttribute('role')==='region'};
    })()`);
    assert.equal(scroll.verticalOverflow, false, 'the objective must not clip tall MathML symbols');
    assert(scroll?.accessible, 'objective scroll region must be keyboard accessible and labelled');
    assert.equal(scroll.left, scroll.max, 'the terminal term must be reachable by scrolling');
    await writeFile(join(output, `${name}-objective.png`), Buffer.from(
      (await cdp('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
  }
  await cdp('Emulation.setDeviceMetricsOverride', {width:1280,height:1000,deviceScaleFactor:1,mobile:false});
  await cdp('Emulation.setEmulatedMedia', {media:'print'});
  await cdp('Page.navigate', {url:pathToFileURL(lesson).href});
  await evaluate('document.fonts.ready');
  const pdf = await cdp('Page.printToPDF', { printBackground: true, preferCSSPageSize: true });
  await writeFile(join(output, 'lesson-print.pdf'), Buffer.from(pdf.data, 'base64'));
  console.log(JSON.stringify(results));
} finally {
  socket?.close();
  browser.kill();
  if (browser.exitCode === null && browser.signalCode === null)
    await new Promise(resolve => browser.once('exit', resolve));
  await writeFile(join(output, 'chromium.log'), browserLog);
  await rm(profile, {recursive: true, force: true});
}
