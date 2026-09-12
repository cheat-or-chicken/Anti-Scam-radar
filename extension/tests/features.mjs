import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
const profile=await mkdtemp(join(tmpdir(),'radar-features-'));
const context=await chromium.launchPersistentContext(profile,{channel:'chromium',headless:true,args:[`--disable-extensions-except=${resolve('.')}`,`--load-extension=${resolve('.')}`]});
try {
 let [worker]=context.serviceWorkers();
 if(!worker) worker=await context.waitForEvent('serviceworker');
 await worker.evaluate(async()=>{
  await chrome.storage.local.set({settings:{pairingToken:'test-pairing-token-12345678901234567890',backendEnabled:true,llmEnabled:true}});
  globalThis.featureCalls=[];
  const original=globalThis.fetch;
  globalThis.fetch=async(input,init)=>{
   if(String(input).startsWith('http://127.0.0.1:8765/v1/')) {
    const body=JSON.parse(init.body);
    featureCalls.push({screenshot:!!body.screenshot,includeLLM:body.include_llm,text:body.context.text});
    return new Response(JSON.stringify({layers:[
     {layer:'VISION',status:'ok',signals:[{id:'visual_test',detail:'測試畫面冒用',weight:10}]},
     {layer:'GOOGLE_URL_REPUTATION',status:'ok',signals:[{id:'google_test',detail:'測試 Google 威脅',weight:35}]}
    ]}),{headers:{'content-type':'application/json'}});
   }
   return original(input,init);
  };
 });
 const page=await context.newPage();
 await page.route('https://feature-test.example/**',route=>route.fulfill({contentType:'text/html',body:'<title>Feature integration</title><p>Plain website content. alice@example.com 電話0912-345-678</p>'}));
 await page.bringToFront();
 await page.goto('https://feature-test.example/');
 for(let i=0;i<100;i++) {
  if(await worker.evaluate(()=>featureCalls.length>0)) break;
  await new Promise(r=>setTimeout(r,100));
 }
 const calls=await worker.evaluate(()=>featureCalls);
 assert.ok(calls.length>0,'automatic backend analysis');
 assert.equal(calls[0].screenshot,true,'actual visible-tab JPEG included automatically');
 assert.equal(calls[0].includeLLM,true);
 assert.ok(!calls[0].text.includes("alice@example.com"));
 assert.ok(!calls[0].text.includes("0912-345-678"));
 await page.locator('#anti-scam-radar-overlay').waitFor();
 const state=await worker.evaluate(async()=>{
  const [tab]=await chrome.tabs.query({url:'https://feature-test.example/'});
  return (await chrome.storage.session.get(`tab:${tab.id}`))[`tab:${tab.id}`];
 });
 assert.equal(state.result.decision.risk_score,45);
 assert.ok(state.result.layers.some(l=>l.layer==='VISION'));
 assert.ok(state.result.layers.some(l=>l.layer==='GOOGLE_URL_REPUTATION'));
 const settings=await worker.evaluate(async()=>(await chrome.storage.local.get('settings')).settings);
 assert.equal(settings.screenshotEnabled,true);
 assert.equal(settings.backendEnabled,true);
 assert.equal(settings.llmEnabled,true);
 const optionsPage = await context.newPage();
 await optionsPage.goto(`chrome-extension://${new URL(worker.url()).host}/options.html`);
 await optionsPage.locator('#screenshotEnabled').uncheck();
 await optionsPage.locator('button[type="submit"]').click();
 await optionsPage.waitForFunction(() => document.getElementById('status').textContent.includes('已儲存'));
 assert.equal(await worker.evaluate(async () => (await chrome.storage.local.get('settings')).settings.screenshotEnabled),false);
 const disabled = await optionsPage.evaluate(() => chrome.runtime.sendMessage({type:'ANALYZE_SCREENSHOT'}));
 assert.equal(disabled.error,'SCREENSHOT_DISABLED');
 await optionsPage.close();
 await page.bringToFront();
 const count = await worker.evaluate(() => featureCalls.length);
 await page.goto('https://feature-test.example/second');
 for(let i=0;i<100;i++) {
  if(await worker.evaluate(n=>featureCalls.length>n,count)) break;
  await new Promise(r=>setTimeout(r,100));
 }
 assert.ok(await worker.evaluate(n=>featureCalls.length>n,count));
 assert.equal(await worker.evaluate(()=>featureCalls.at(-1).screenshot),false);
 console.log('PASS: user toggle disables manual/automatic screenshot while text analysis continues');
 console.log('PASS: migrated defaults; real automatic screenshot; upload; Google + VISION merge; visible warning (mock providers)');
} finally {await context.close();await rm(profile,{recursive:true,force:true});}
