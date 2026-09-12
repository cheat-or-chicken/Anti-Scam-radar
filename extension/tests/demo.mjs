// Run against script.demo_server. Real pages + real unpacked extension, isolated profile.
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';
const base = 'http://127.0.0.1:8088';
assert.equal((await fetch(base)).status, 200, 'Start uv run python -m script.demo_server first');
const profile = await mkdtemp(join(tmpdir(), 'radar-demo-'));
await mkdir('artifacts/demo', { recursive: true });
const context = await chromium.launchPersistentContext(profile, {
  channel: 'chromium', headless: true, viewport: { width: 1440, height: 1080 },
  args: [`--disable-extensions-except=${resolve('.')}`, `--load-extension=${resolve('.')}`]
});
const report = [];
try {
  let [worker] = context.serviceWorkers();
  if (!worker) worker = await context.waitForEvent('serviceworker');
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  async function overlayDetails() {
    const {root} = await cdp.send('DOM.getDocument', {depth:-1, pierce:true});
    const host = findOverlay(root);
    const nodes = [];
    function visit(node) {
      if (!node) return;
      nodes.push(node);
      for (const child of [...(node.children || []), ...(node.shadowRoots || [])]) visit(child);
    }
    visit(host);
    return {
      blocking: nodes.some(n => n.attributes?.includes('alertdialog')),
      hostId: host?.backendNodeId,
      items: nodes.filter(n => n.nodeName === 'LI').length,
    };
  }
  const outgoing = [];
  page.on('request', req => { if (req.method() !== 'GET' || !req.url().startsWith(base)) outgoing.push(req.url()); });
  async function state(url) {
    return worker.evaluate(async url => {
      const [tab] = await chrome.tabs.query({ url });
      if (!tab) return null;
      const all = await chrome.storage.session.get(`tab:${tab.id}`);
      return all[`tab:${tab.id}`];
    }, url);
  }
  async function until(fn, label) {
    for (let i = 0; i < 160; i++) {
      const value = await fn();
      if (value) return value;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw Error('Timed out: ' + label);
  }
  await page.goto(base + '/');
  const home = await until(async () => {
    const s = await state(base + '/');
    return s?.result.layers[3].status === 'ok' && s;
  }, 'overview');
  assert.equal(home.result.decision.risk_score, 0, 'Overview is a negative control');
  await page.screenshot({ path: 'artifacts/demo/00-overview.png', fullPage: true });
  for (const [name, signal] of [['traffic', 'brand_domain_mismatch'], ['investment', 'financial_manipulation'], ['support', 'remote_control_request'], ['otp', 'credential_relay_request']]) {
    const url = `${base}/${name}.html`;
    await page.goto(url);
    const s = await until(async () => {
      const s = await state(url);
      return s?.result.layers.flatMap(l => l.signals).some(x => x.id === signal) && s;
    }, name);
    assert.equal(s.result.decision.display_level, 'banner', name);
    await page.locator('#anti-scam-radar-overlay').waitFor();
    await page.screenshot({ path: `artifacts/demo/${name}.png`, fullPage: true });
    assert.equal((await overlayDetails()).items, new Set(s.result.decision.reasons).size, 'banner lists every reason');
    if (name === 'otp') {
      await page.locator('#otp-code').click();
      await page.screenshot({ path: 'artifacts/demo/otp-interruption.png', fullPage: true });
      assert.equal(await page.locator('#otp-code').inputValue(), '');
      assert.equal((await overlayDetails()).blocking, true);
      await worker.evaluate(async url => {
        const [tab] = await chrome.tabs.query({url});
        await chrome.tabs.sendMessage(tab.id, {type:'RADAR_RESCAN', force:true});
      }, url);
      assert.equal((await overlayDetails()).blocking, true, 'rescan must not downgrade an active interruption');
      await page.evaluate(() => document.getElementById('anti-scam-radar-overlay').remove());
      await page.locator('#anti-scam-radar-overlay').waitFor();
      assert.equal((await overlayDetails()).blocking, true, 'removed interruption must return as a modal');
    }
    report.push({ name, score: s.result.decision.risk_score, display: s.result.decision.display_level, signal });
  }
  const url = base + '/prize.html';
  await page.goto(url);
  const initial = await until(async () => {
    const s = await state(url);
    return s?.result.layers[3].status === 'ok' && s;
  }, 'prize baseline');
  assert.equal(initial.result.decision.risk_score, 0);
  await page.screenshot({ path: 'artifacts/demo/prize-before.png', fullPage: true });
  await page.locator('#reveal').click();
  await until(() => page.url().startsWith('chrome-extension://') && page.url().includes('warning.html'), 'dynamic phishing block');
  await page.locator('#proceedBtn').waitFor();
  await page.screenshot({ path: 'artifacts/demo/prize-block.png', fullPage: true });
  report.push({ name: 'prize', initialScore: 0, display: 'block' });
  assert.deepEqual(outgoing.filter(u => !u.startsWith('chrome-extension://')), [], 'No external requests or submissions');
  await page.goto(base + '/');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'artifacts/demo/mobile.png', fullPage: true });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  await page.setViewportSize({ width: 1440, height: 1080 });
  const alertURL = base + '/alerts.html';
  await page.route(alertURL, route => route.fulfill({ contentType: 'text/html; charset=utf-8', body: '<title>Alert regression</title><p>登录 银行卡。</p>' }));
  await page.goto(alertURL);
  await until(async () => (await state(alertURL))?.result.decision.risk_score === 5, 'low score warning');
  await page.locator('#anti-scam-radar-overlay').waitFor();
  // Use Chrome's DOM inspection to click the real button inside the closed shadow root.
  const { root } = await cdp.send('DOM.getDocument', { depth: -1, pierce: true });
  function findOverlay(node) {
    if (node.attributes?.includes('anti-scam-radar-overlay')) return node;
    for (const child of [...(node.children || []), ...(node.shadowRoots || [])]) {
      const found = findOverlay(child); if (found) return found;
    }
  }
  const host = findOverlay(root);
  assert.ok(host?.shadowRoots?.length);
  const { nodeId } = await cdp.send('DOM.querySelector', { nodeId: host.shadowRoots[0].nodeId, selector: 'button.primary' });
  const { model } = await cdp.send('DOM.getBoxModel', { nodeId });
  await page.mouse.click((model.border[0] + model.border[4]) / 2, (model.border[1] + model.border[5]) / 2);
  assert.equal(await page.locator('#anti-scam-radar-overlay').count(), 0);
  await worker.evaluate(async url => {
    const [tab] = await chrome.tabs.query({ url });
    await chrome.tabs.sendMessage(tab.id, { type: 'RADAR_RESCAN', force: true });
  }, alertURL);
  assert.equal(await page.locator('#anti-scam-radar-overlay').count(), 0, 'same dismissed risk stays dismissed');
  await page.evaluate(() => { document.querySelector('p').firstChild.data += '請下載 AnyDesk。'; });
  await until(async () => (await state(alertURL))?.result.decision.risk_score === 50, 'new evidence');
  await page.locator('#anti-scam-radar-overlay').waitFor();
  await page.evaluate(() => document.getElementById('anti-scam-radar-overlay').remove());
  await page.locator('#anti-scam-radar-overlay').waitFor();
  await page.screenshot({ path: 'artifacts/demo/rearmed-warning.png', fullPage: true });
  console.log('PASS: low-score alert; dismissal respected; new warning re-arms; removed overlay restored');
  const cardsURL = base + '/separate-cards.html';
  await page.route(cardsURL, route => route.fulfill({contentType:'text/html; charset=utf-8', body:'<title>Separate cards</title><p>登录 银行卡。請下載 AnyDesk。</p>'}));
  await page.goto(cardsURL);
  await until(async () => (await overlayDetails()).items === 2, 'two separate problem cards');
  const beforeUpdate = await overlayDetails();
  await worker.evaluate(async url => {
    const [tab] = await chrome.tabs.query({url});
    await chrome.tabs.sendMessage(tab.id, {type:'RADAR_RESULT', result:{
      checkedAt:Date.now() + 10000, layers:[],
      decision:{risk_score:20, display_level:'banner', interrupt_triggers:[], reasons:['新增測試提醒']}
    }});
  }, cardsURL);
  const afterUpdate = await overlayDetails();
  assert.equal(afterUpdate.items, 3, 'partial follow-up adds a card without losing previous findings');
  assert.equal(afterUpdate.hostId, beforeUpdate.hostId, 'incremental update preserves the mounted overlay');
  const cardDocument = await cdp.send('DOM.getDocument', {depth:-1,pierce:true});
  const cardHost = findOverlay(cardDocument.root);
  const dismissNode = await cdp.send('DOM.querySelector', {nodeId:cardHost.shadowRoots[0].nodeId, selector:'.dismiss-issue'});
  await cdp.send('DOM.scrollIntoViewIfNeeded', {nodeId:dismissNode.nodeId});
  const box = await cdp.send('DOM.getBoxModel', {nodeId:dismissNode.nodeId});
  await page.mouse.click((box.model.border[0]+box.model.border[4])/2,(box.model.border[1]+box.model.border[5])/2);
  assert.equal((await overlayDetails()).items, 2, 'closing one card leaves the other cards visible');
  await page.screenshot({path:'artifacts/demo/separate-cards.png',fullPage:true});
  console.log('PASS: independent cards; incremental partial results; dismiss only one card');
  const manyURL = base + '/many-risks.html';
  await page.route(manyURL, route => route.fulfill({contentType:'text/html; charset=utf-8', body:'<title>監理服務網</title><p>銀行卡 登录 請下載 AnyDesk。您的裝置感染病毒，請立即下載修復工具。要提領資金，請先支付保證金。</p>'}));
  for (let attempt = 0; attempt < 3; attempt++) {
    await page.goto(manyURL);
    await until(() => page.url().includes('warning.html'), 'repeated high risk block');
    await until(() => page.locator('#reasons li').count().then(n => n > 3), 'all block reasons');
    await until(() => page.locator('#proceedBtn').isEnabled(), 'valid warning record');
  }
  console.log('PASS: all reasons; modal survives rescan/removal; text-node mutation; repeated high-risk redirects');
  await writeFile('artifacts/demo/results.json' , JSON.stringify(report, null, 2));
  console.log('PASS: overview negative control; five real extension cases; sensitive focus; dynamic block; no data sent; mobile layout');
  console.log(JSON.stringify(report, null, 2));
} finally {
  await context.close();
  await rm(profile, { recursive: true, force: true });
}
